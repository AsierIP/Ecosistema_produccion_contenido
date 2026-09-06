"""Run using an existing CUDA Python runtime, without downloading dependencies."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ecosystem.ambient import render
p=argparse.ArgumentParser()
p.add_argument('manifest')
args=p.parse_args()
r=render(args.manifest, ROOT)
print(json.dumps({k:r[k] for k in ('status','output','frames','render_seconds','gpu')},ensure_ascii=True))
