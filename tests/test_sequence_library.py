import json
from pathlib import Path
import tempfile
import unittest
from ecosystem.sequence_library import SequenceLibrary
from ecosystem.cache import file_hash


class SequencePlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.library=SequenceLibrary(self.root)
        for i, environment in enumerate(('coast','garden','courtyard')):
            media=self.root/f'{i}.mp4';media.write_bytes(f'fixture-{i}'.encode())
            evidence=self.root/f'{i}.json';evidence.write_text('{}')
            meta={'quality_status':'PASS','evidence_path':str(evidence),'evidence_sha256':file_hash(evidence)}
            with self.library.connect() as db:
                db.execute('INSERT INTO sequences VALUES (?,?,?,?,?,?,?,?)',
                    (str(i),'religion','photo',environment,str(media),file_hash(media),json.dumps(meta),i))

    def plan(self, name='job', seed='seed'):
        return self.library.plan(plan_id=name,channel='religion',profile='photo',duration=308.28,seed=seed)

    def test_balanced_selection_changes_environment_and_covers_tail(self):
        plan=self.plan();items=plan['items']
        self.assertEqual(len(items),11)
        self.assertAlmostEqual(sum(i['duration_seconds'] for i in items),308.28)
        self.assertTrue(all(a['environment']!=b['environment'] for a,b in zip(items,items[1:])))
        counts=[sum(i['sequence_id']==str(n) for i in items) for n in range(3)]
        self.assertLessEqual(max(counts)-min(counts),1)

    def test_retry_preserves_plan_and_rejects_changed_request(self):
        first=self.plan()
        self.assertEqual(first,self.plan())
        with self.assertRaises(ValueError):self.plan(seed='different')

    def test_corrupt_asset_invalidates_even_a_saved_plan(self):
        self.plan();(self.root/'0.mp4').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.plan()

    def test_pending_quality_and_other_channel_are_not_selected(self):
        with self.library.connect() as db:
            row=db.execute('SELECT * FROM sequences WHERE id="0"').fetchone()
            meta=json.loads(row['metadata']);meta['quality_status']='PENDING'
            db.execute('UPDATE sequences SET metadata=? WHERE id="0"',(json.dumps(meta),))
            db.execute('UPDATE sequences SET channel="other" WHERE id="1"')
        with self.assertRaises(ValueError):self.plan()


class PosePlanningTests(unittest.TestCase):
    plan = SequencePlanningTests.plan
    def setUp(self):
        SequencePlanningTests.setUp(self)
        config=self.root/'config/profiles'
        config.mkdir(parents=True)
        (config/'photo.json').write_text(json.dumps({'visual':{'avoid_adjacent_body_pose':True}}))
        with self.library.connect() as db:
            for i,pose in enumerate(['seated','seated','standing']):
                row=db.execute('SELECT metadata FROM sequences WHERE id=?',(str(i),)).fetchone()
                meta=json.loads(row['metadata']);meta['body_pose']=pose
                db.execute('UPDATE sequences SET metadata=? WHERE id=?',(json.dumps(meta),str(i)))

    def test_posture_changes_even_when_environments_differ(self):
        items=self.plan()['items']
        self.assertTrue(all(a['body_pose']!=b['body_pose'] for a,b in zip(items,items[1:])))
        self.assertTrue(all(a['environment']!=b['environment'] for a,b in zip(items,items[1:])))

    def test_unknown_posture_is_not_selected(self):
        with self.library.connect() as db:
            row=db.execute('SELECT metadata FROM sequences WHERE id="0"').fetchone()
            meta=json.loads(row['metadata']);meta.pop('body_pose')
            db.execute('UPDATE sequences SET metadata=? WHERE id="0"',(json.dumps(meta),))
        self.assertNotIn('0',[x['sequence_id'] for x in self.plan()['items']])

    def test_cached_plan_checks_corrected_posture(self):
        self.plan()
        with self.library.connect() as db:
            row=db.execute('SELECT metadata FROM sequences WHERE id="2"').fetchone()
            meta=json.loads(row['metadata']);meta['body_pose']='seated'
            db.execute('UPDATE sequences SET metadata=? WHERE id="2"',(json.dumps(meta),))
        with self.assertRaises(ValueError): self.plan()
