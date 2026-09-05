"""Local source indexing and bounded retrieval: books are not reread per agent."""
from __future__ import annotations
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from .cache import file_hash

class Corpus:
    def __init__(self, database):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, path TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(source_id UNINDEXED, locator UNINDEXED, text, tokenize='unicode61 remove_diacritics 2');''')
            con.execute("CREATE TABLE IF NOT EXISTS source_audits(id TEXT PRIMARY KEY, details TEXT NOT NULL)")
            con.commit()

    def _connect(self):
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _pages(path):
        if path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise RuntimeError("PDF requiere pypdf en el Python elegido; no se omite la extracción") from exc
            for number, page in enumerate(PdfReader(str(path)).pages, 1):
                text = page.extract_text() or ""
                yield f"{path.name}:pdf-page-{number}", text
        elif path.suffix.lower() in {".txt", ".md", ".usfm", ".sfm"}:
            text = path.read_text(encoding="utf-8-sig")
            # Preserve explicit Bible chapter and verse locators when available.
            chapter = ""
            book = ""
            for line_no, line in enumerate(text.splitlines(), 1):
                if line.startswith("\\id "):
                    book = line[4:].split()[0]
                if line.startswith("\\c "):
                    chapter = line[3:].split()[0]
                match = re.match(r"\\v\s+(\S+)\s+(.*)", line)
                if match:
                    yield f"{path.name}:{book}:{chapter}:{match[1]}", match[2]
                elif line.strip() and not line.startswith("\\"):
                    yield f"{path.name}:line-{line_no}", line
        else:
            raise ValueError(f"Unsupported source format: {path.suffix}")

    def index(self, source_id, source_path):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", source_id):
            raise ValueError("invalid source_id")
        source = Path(source_path).resolve(strict=True)
        files = sorted(p for p in source.rglob("*") if p.suffix.lower() in {".txt", ".md", ".usfm", ".sfm"}) if source.is_dir() else [source]
        if not files:
            raise ValueError("No hay fuentes compatibles")
        identity = hashlib.sha256("\n".join(str(p.relative_to(source) if source.is_dir() else p.name) + ":" + file_hash(p) for p in files).encode()).hexdigest()
        with closing(self._connect()) as con:
            old = con.execute("SELECT sha256 FROM sources WHERE id=?", (source_id,)).fetchone()
            if old and old["sha256"] == identity:
                audit = con.execute("SELECT details FROM source_audits WHERE id=?", (source_id,)).fetchone()
                return {"status": "CACHED", "source_id": source_id, "sha256": identity, "extraction": json.loads(audit[0]) if audit else None}
            count = 0
            empty_pages = []
            page_count = 0
            with con:
                con.execute("DELETE FROM passages WHERE source_id=?", (source_id,))
                for path in files:
                    for locator, text in self._pages(path):
                        if path.suffix.lower() == ".pdf":
                            page_count += 1
                            if not text.strip():
                                empty_pages.append(locator)
                        for start in range(0, len(text), 1600):
                            chunk = text[start:start + 1800]
                            if not chunk.strip():
                                continue
                            con.execute("INSERT INTO passages VALUES(?,?,?)", (source_id, locator + f":offset-{start}", chunk))
                            count += 1
                if not count:
                    raise ValueError("No se extrajo texto; no se registra un índice vacío")
                if page_count and len(empty_pages) / page_count > 0.05:
                    raise ValueError("Más del 5% del PDF carece de texto; completar OCR antes de indexar")
                extraction = {"pdf_pages": page_count, "pages_without_text": empty_pages, "passages": count}
                con.execute("INSERT INTO sources VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET sha256=excluded.sha256,path=excluded.path", (source_id, identity, str(source)))
                con.execute("INSERT INTO source_audits VALUES(?,?) ON CONFLICT(id) DO UPDATE SET details=excluded.details", (source_id, json.dumps(extraction)))
            return {"status": "INDEXED", "source_id": source_id, "passages": count, "sha256": identity, "extraction": extraction}

    def search(self, source_id, query, limit=5):
        if not 1 <= limit <= 8:
            raise ValueError("Retrieval limit must be between 1 and 8")
        terms = re.findall(r"\w+", query, flags=re.UNICODE)
        if not terms:
            return []
        safe_query = " OR ".join('"' + term + '"' for term in terms[:15])
        with closing(self._connect()) as con:
            return [dict(row) for row in con.execute("SELECT source_id,locator,text FROM passages WHERE passages MATCH ? AND source_id=? ORDER BY rank LIMIT ?", (safe_query, source_id, limit))]
