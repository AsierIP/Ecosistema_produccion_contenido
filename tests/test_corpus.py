from pathlib import Path
import tempfile
import unittest
from ecosystem.corpus import Corpus

class CorpusTests(unittest.TestCase):
    def test_index_cache_replacement_and_cross_source_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("Un dato curioso sobre océanos", encoding="utf-8")
            corpus = Corpus(root / "corpus.sqlite3")
            self.assertEqual(corpus.index("book", source)["status"], "INDEXED")
            self.assertEqual(corpus.index("book", source)["status"], "CACHED")
            self.assertEqual(len(corpus.search("book", "océanos")), 1)
            self.assertEqual(corpus.search("other", "océanos"), [])
            source.write_text("Una explicación sobre planetas", encoding="utf-8")
            corpus.index("book", source)
            self.assertEqual(corpus.search("book", "océanos"), [])
            self.assertEqual(len(corpus.search("book", "planetas")), 1)

    def test_bible_locator_and_empty_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.usfm"
            source.write_text("\\id GEN\n\\c 1\n\\v 1 En el principio\n", encoding="utf-8")
            corpus = Corpus(root / "corpus.sqlite3")
            corpus.index("bible", source)
            self.assertIn(":GEN:1:1:", corpus.search("bible", "principio")[0]["locator"])
            source.write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                corpus.index("bible", source)
            self.assertEqual(len(corpus.search("bible", "principio")), 1)

if __name__ == "__main__":
    unittest.main()
