from pathlib import Path
import tempfile
import unittest
from ecosystem.cache import file_hash
from ecosystem.config import write_json
from ecosystem.music_allocation import reserve


class MusicAllocationTests(unittest.TestCase):
    def test_restart_nonoverlap_exhaustion_and_historical_collision(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, license_path, history = (root / n for n in ('source.mp3','license.json','history.json'))
            source.write_bytes(b'fixture recording')
            write_json(license_path,{'status':'approved_music_source','asset_id':'track',
                'source_file':{'sha256':file_hash(source),'duration_seconds':100}})
            usage = {'allocations':[{'track_id':'track','start_ms':0,'end_ms':31250}]}
            write_json(history,usage)
            config = {'source_path':str(source),'license_path':str(license_path),'history_path':str(history)}
            first = reserve(root,'one',config)
            self.assertEqual(first['start_ms'],31250)
            self.assertEqual(first,reserve(root,'one',config))
            self.assertEqual(reserve(root,'two',config)['start_ms'],62500)
            with self.assertRaises(ValueError):
                reserve(root,'three',config)
            usage['allocations'].append({'track_id':'track','start_ms':31250,'end_ms':62500})
            write_json(history,usage)
            with self.assertRaises(ValueError):
                reserve(root,'one',config)
