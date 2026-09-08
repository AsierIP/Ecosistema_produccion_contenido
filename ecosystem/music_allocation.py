"""Durable non-overlapping music ranges, with read-only historical reconciliation."""
import json
from pathlib import Path
import sqlite3
from contextlib import closing

from .config import read_json
from .cache import file_hash
from .native_batch import ref


def reserve(root, job_id, config):
    source, license_path, history_path = (Path(config[k]) for k in ('source_path','license_path','history_path'))
    license_record = read_json(license_path)
    if (license_record.get('status') != 'approved_music_source'
            or file_hash(source).lower() != license_record['source_file']['sha256'].lower()):
        raise ValueError('Music source is not the approved recording')
    history = read_json(history_path)
    track = license_record['asset_id']
    occupied = [(a['start_ms'], a['end_ms']) for a in history['allocations'] if a['track_id'] == track]
    duration = int(license_record['source_file']['duration_seconds'] * 1000)
    if any(not isinstance(a,int) or not isinstance(b,int) or not 0 <= a < b <= duration for a,b in occupied):
        raise ValueError('Invalid historical music allocation')
    database = Path(root) / '.runtime/music-allocations.sqlite3'
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as con, con:
        con.execute('CREATE TABLE IF NOT EXISTS allocations(job TEXT PRIMARY KEY, track TEXT, start INTEGER, end INTEGER, payload TEXT)')
        con.execute('BEGIN IMMEDIATE')
        rows = con.execute('SELECT job,start,end,payload FROM allocations WHERE track=?',(track,)).fetchall()
        prior = next((row for row in rows if row[0] == job_id),None)
        if prior:
            value = json.loads(prior[3])
            if (value['source'] != ref(source) or value['license'] != ref(license_path)
                    or any(prior[1] < b and a < prior[2] for a,b in occupied)):
                raise ValueError('Reserved music changed or overlaps new historical activity')
            return value
        if con.execute('SELECT 1 FROM allocations WHERE job=?',(job_id,)).fetchone():
            raise ValueError('Job already reserved another recording')
        occupied += [(row[1],row[2]) for row in rows]
        start = 0
        for a,b in sorted(occupied):
            if start + 31250 <= a:
                break
            start = max(start,b)
        if start + 31250 > duration:
            raise ValueError('Approved music has no unused complete range')
        value = {'kind':'music_allocation_v1','status':'reserved','job_id':job_id,
            'track_id':track,'source':ref(source),'license':ref(license_path),
            'historical_observation':ref(history_path),'start_ms':start,'duration_ms':31250}
        con.execute('INSERT INTO allocations VALUES(?,?,?,?,?)',
            (job_id,track,start,start+31250,json.dumps(value,sort_keys=True)))
        return value
