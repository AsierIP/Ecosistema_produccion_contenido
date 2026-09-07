"""Offline word timestamps using the already installed Whisper model."""
import argparse
import json
import os
from pathlib import Path
import time
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.audio.is_file() or not (args.model / 'model.bin').is_file() or args.output.exists():
        raise ValueError('Existing audio/model and a new output path are required')
    from faster_whisper import WhisperModel
    started = time.monotonic()
    # CPU ASR leaves the global GPU slot available for animation, with no downloads.
    model = WhisperModel(str(args.model), device='cpu', compute_type='int8', local_files_only=True)
    segments, info = model.transcribe(str(args.audio), language='es', beam_size=5,
                                     word_timestamps=True, vad_filter=False, temperature=0)
    words = [{'word': w.word, 'start': w.start, 'end': w.end, 'probability': w.probability}
             for segment in segments for w in (segment.words or [])]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump({'language': info.language, 'words': words, 'engine': 'faster-whisper-local',
                   'elapsed_seconds': time.monotonic() - started, 'network_calls': 0}, stream, ensure_ascii=False)

if __name__ == '__main__':
    main()
