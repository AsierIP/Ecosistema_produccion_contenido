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
