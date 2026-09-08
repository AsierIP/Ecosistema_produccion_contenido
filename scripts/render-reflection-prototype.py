"""Render the bounded five-minute prototype from completed local provider assets."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ecosystem.config import ROOT, read_json
from ecosystem.cache import file_hash
from ecosystem.reflection_media import slow_block, block_frame_counts, assemble


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--native-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    plan = read_json(workspace / 'prototype-plan.json')
    if plan['profile'] != 'religion-reflection-5m-prototype-v1':
        raise ValueError('Wrong production line')
    narration = Path(plan['narration']['path'])
    if file_hash(narration) != plan['narration']['sha256']:
        raise ValueError('Narration changed')
    import wave
    with wave.open(str(narration)) as audio:
        duration = audio.getnframes() / audio.getframerate()
    counts = block_frame_counts(duration)
    sources = []
    for i in range(1, 11):
        receipt = read_json(args.native_directory / f'animation-{i:02}.json')
        source = Path(receipt['path'])
        if receipt['state'] != 'downloaded' or file_hash(source) != receipt['sha256']:
            raise ValueError(f'Native block {i} is not ready')
        sources.append(source)
    if len({file_hash(p) for p in sources}) != 10:
        raise ValueError('Ten distinct native animations are required')
    blocks = []
    for i, (source, frames) in enumerate(zip(sources, counts), 1):
        destination = workspace / 'slow-blocks' / f'block-{i:02}.mp4'
        result = slow_block(source, destination, frames, root=ROOT)
        blocks.append(destination)
        print(json.dumps({'block': i, 'status': result['status']}), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = assemble(blocks, narration, workspace / 'audio/music-bed-300s.wav',
                      workspace / 'captions/reflection-v1.ass', args.output, root=ROOT)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
