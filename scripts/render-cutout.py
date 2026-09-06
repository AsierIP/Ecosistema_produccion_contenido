"""Render a local 2D scene manifest without publishing anything."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ecosystem.cutout import render

parser = argparse.ArgumentParser()
parser.add_argument("manifest")
args = parser.parse_args()
receipt = render(args.manifest, root=ROOT)
print(json.dumps({key: receipt[key] for key in ("status", "output_path", "sha256", "frames", "duration_seconds", "publication")}, ensure_ascii=True, indent=2))
