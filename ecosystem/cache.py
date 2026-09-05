"""Content-addressed local cache; channel and policy revisions isolate decisions."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def cache_key(*, channel_id, stage, policy, inputs, model=None):
    value = {"channel": channel_id, "stage": stage, "policy": policy, "inputs": inputs, "model": model}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()

class Cache:
    def __init__(self, root):
        self.root = Path(root)

    def put(self, key, value, artifacts):
        if not key.isalnum() or len(key) != 64:
            raise ValueError("invalid cache key")
        self.root.mkdir(parents=True, exist_ok=True)
        record = {"value": value, "artifacts": [{"path": str(Path(p).resolve()), "sha256": file_hash(Path(p))} for p in artifacts]}
        target = self.root / (key + ".json")
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        temporary.replace(target)

    def get(self, key):
        if not key.isalnum() or len(key) != 64:
            raise ValueError("invalid cache key")
        path = self.root / (key + ".json")
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if any(file_hash(Path(a["path"])) != a["sha256"] for a in data["artifacts"]):
                return None
            return data["value"]
        except (OSError, ValueError, KeyError):
            return None
