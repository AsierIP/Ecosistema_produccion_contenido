"""Reusable silent 30-second sequences with durable, deterministic random plans."""
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sqlite3
import time
from contextlib import contextmanager

from .cache import file_hash
from .config import ROOT, read_json
from .media import probe, decode


class SequenceLibrary:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.path = self.root / '.runtime/sequence-library.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS sequences (
              id TEXT PRIMARY KEY, channel TEXT NOT NULL, profile TEXT NOT NULL,
              environment TEXT NOT NULL, path TEXT NOT NULL, sha256 TEXT NOT NULL,
              metadata TEXT NOT NULL, created REAL NOT NULL,
              UNIQUE(channel,profile,sha256));
            CREATE TABLE IF NOT EXISTS sequence_plans (
              id TEXT PRIMARY KEY, binding TEXT NOT NULL, plan TEXT NOT NULL,
              created REAL NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, path, *, channel, profile, environment, evidence):
        path, evidence = Path(path).resolve(strict=True), Path(evidence).resolve(strict=True)
        digest = file_hash(path)
        qa = read_json(evidence)
        if (qa.get('decision') not in {'PENDING','PASS'} or qa.get('sha256') != digest
                or qa.get('style') != 'photorealistic' or not qa.get('provenance')):
            raise ValueError('A bound photorealistic sequence review is required')
        media = probe(path)
        streams = media.get('streams', [])
        videos = [s for s in streams if s['codec_type'] == 'video']
        if len(videos) != 1 or any(s['codec_type'] == 'audio' for s in streams):
            raise ValueError('Library sequences must be silent visual assets')
        v = videos[0]
        if (v['width'], v['height'], v['avg_frame_rate'], int(v.get('nb_frames', 0))) != (1920,1080,'24/1',720):
            raise ValueError('Library sequences require exactly 30 seconds at 1080p24')
        if not decode(path)['ok']:
            raise ValueError('Library sequence fails full decoding')
        ident = hashlib.sha256(f'{channel}\0{profile}\0{digest}'.encode()).hexdigest()[:24]
        meta = {'duration_seconds':30, 'frames':720, 'style':'photorealistic',
                'quality_status':qa['decision'], 'body_pose':qa.get('body_pose'),
                'evidence_path':str(evidence), 'evidence_sha256':file_hash(evidence),
                'voice':False, 'music':False, 'captions':False}
        with self.connect() as db:
            previous = db.execute('SELECT * FROM sequences WHERE id=?',(ident,)).fetchone()
            if previous:
                if previous['environment'] != environment or previous['path'] != str(path):
                    raise ValueError('Existing sequence identity changed')
                return dict(previous)
            db.execute('INSERT INTO sequences VALUES (?,?,?,?,?,?,?,?)',
                       (ident,channel,profile,environment,str(path),digest,json.dumps(meta),time.time()))
        return self.get(ident)

    def get(self, ident):
        with self.connect() as db:
            row = db.execute('SELECT * FROM sequences WHERE id=?',(ident,)).fetchone()
        if not row:
            raise KeyError(ident)
        return dict(row)

    def qualify(self, ident, evidence):
        row = self.get(ident)
        self.verify(row)
        evidence = Path(evidence).resolve(strict=True)
        review = read_json(evidence)
        if review.get('decision') != 'PASS' or review.get('sha256') != row['sha256']:
            raise ValueError('A matching passed sequence review is required')
        meta = json.loads(row['metadata'])
        meta.update(quality_status='PASS', evidence_path=str(evidence), evidence_sha256=file_hash(evidence))
        if review.get('body_pose'):
            meta['body_pose'] = review['body_pose']
        with self.connect() as db:
            db.execute('UPDATE sequences SET metadata=? WHERE id=?',(json.dumps(meta),ident))
        return self.get(ident)

    def list(self, channel=None, profile=None):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM sequences ORDER BY created,id').fetchall()
        return [dict(r) for r in rows if (channel is None or r['channel']==channel)
                and (profile is None or r['profile']==profile)]

    @staticmethod
    def verify(row):
        meta = json.loads(row['metadata'])
        if (file_hash(Path(row['path'])) != row['sha256']
                or file_hash(Path(meta['evidence_path'])) != meta['evidence_sha256']):
            raise ValueError('Library media or its quality evidence changed')

    def plan(self, *, plan_id, channel, profile, duration, seed):
        if not math.isfinite(duration) or not 0 < duration <= 3600:
            raise ValueError('Invalid bounded timeline duration')
        policy_file = self.root/'config/profiles'/f'{profile}.json' if re.fullmatch(r'[a-z0-9-]+',profile) else None
        vary_pose = bool(policy_file and policy_file.exists() and read_json(policy_file).get('visual',{}).get('avoid_adjacent_body_pose'))
        binding_parts = [channel,profile,duration,str(seed)]
        if vary_pose:
            binding_parts.append('vary-body-pose-v1')
        binding = json.dumps(binding_parts)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            saved = db.execute('SELECT * FROM sequence_plans WHERE id=?',(plan_id,)).fetchone()
            if saved:
                if saved['binding'] != binding:
                    raise ValueError('Timeline request changed; use a new plan id')
                result = json.loads(saved['plan'])
                previous_pose = None
                for item in result['items']:
                    row = self.get(item['sequence_id'])
                    self.verify(row)
                    pose = json.loads(row['metadata']).get('body_pose')
                    if vary_pose and (not pose or pose == previous_pose or pose != item.get('body_pose')):
                        raise ValueError('Saved sequence postures changed or repeat')
                    previous_pose = pose
                return result
            assets = [dict(r) for r in db.execute('SELECT * FROM sequences WHERE channel=? AND profile=?',(channel,profile))
                      if json.loads(r['metadata']).get('quality_status')=='PASS']
            if vary_pose:
                assets = [a for a in assets if json.loads(a['metadata']).get('body_pose')]
                if duration>30 and len({json.loads(a['metadata'])['body_pose'] for a in assets})<2:
                    raise ValueError('At least two verified body postures are required')
            if not assets or (duration>30 and len({r['environment'] for r in assets})<2):
                raise ValueError('At least two environments are required to avoid adjacent repetition')
            for row in assets:
                self.verify(row)
            rng, items, counts, previous = random.Random(str(seed)), [], {}, None
            previous_pose = None
            for i in range(math.ceil(duration/30)):
                eligible = [a for a in assets if a['environment'] != previous and
                            (not vary_pose or json.loads(a['metadata'])['body_pose'] != previous_pose)]
                if not eligible:
                    raise ValueError('No compatible environment and posture for the next sequence')
                fewest = min(counts.get(a['id'],0) for a in eligible)
                chosen = rng.choice([a for a in eligible if counts.get(a['id'],0)==fewest])
                counts[chosen['id']] = counts.get(chosen['id'],0)+1
                previous = chosen['environment']
                previous_pose = json.loads(chosen['metadata']).get('body_pose')
                items.append({'sequence_id':chosen['id'], 'path':chosen['path'],
                              'sha256':chosen['sha256'], 'environment':previous, 'body_pose':previous_pose,
                              'start_seconds':i*30, 'duration_seconds':min(30,duration-i*30)})
            result = {'plan_id':plan_id,'channel':channel,'profile':profile,
                      'duration_seconds':duration,'seed':str(seed),'items':items}
            db.execute('INSERT INTO sequence_plans VALUES (?,?,?,?)',
                       (plan_id,binding,json.dumps(result),time.time()))
            return result
