"""Bind an observed browser export to its durable reflection animation intent."""
import argparse
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ecosystem.cache import file_hash
from ecosystem.config import read_json, write_json
from ecosystem.media import decode, probe


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--index', type=int, required=True)
    args = parser.parse_args()
    request = read_json(args.request)
    if not 1 <= args.index <= len(request['items']):
        raise ValueError('Invalid animation index')
    directory = Path(request['output']).resolve()
    if directory.drive.casefold() != 'e:':
        raise ValueError('Production media must stay on E:')
    receipt = directory / f'animation-{args.index:02}.json'
    intent = read_json(receipt)
    item = request['items'][args.index - 1]
    if (intent['state'] not in {'submitting', 'submitted', 'generated'}
            or intent['request_sha256'] != file_hash(args.request)
            or intent['source_media_id'] != item['source_media_id']):
        raise ValueError('Browser export does not match the pending intent')
    source = args.source.resolve(strict=True)
    temp_root = Path.home() / 'AppData/Local/Temp/browser-use/assets'
    if not source.is_relative_to(temp_root.resolve()):
        raise ValueError('Expected an explicit browser asset export')
    digest = file_hash(source)
    info = probe(source)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    if (video['width'] <= video['height'] or video['avg_frame_rate'] != '24/1'
            or int(video['nb_frames']) != 125 or not decode(source)['ok']):
        raise ValueError('Export fails native video validation')
    output = directory / f'native-{args.index:02}.mp4'
    with source.open('rb') as inp, output.open('xb') as out:
        shutil.copyfileobj(inp, out)
    if file_hash(output) != digest:
        raise ValueError('Copy differs; preserve both files for reconciliation')
    intent.update(state='downloaded', path=str(output), sha256=digest, frames=125,
                  transfer='Observed editor export; full decode and identical local copy verified')
    write_json(receipt, intent)
    source.unlink()
    print(f'Native {args.index:02}: full decode and hash PASS')


if __name__ == '__main__':
    main()
