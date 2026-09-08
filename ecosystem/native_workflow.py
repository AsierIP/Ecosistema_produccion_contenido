"""Contain native handoff failures to their job without hiding or retrying them."""
from pathlib import Path
from .config import read_json, write_json
from .native_batch import advance_native_batches
from .native_sequence import advance_native_sequences
from .native_conform import advance_native_conforms
from .religion_captions import advance_native_captions
from .native_timeline import advance_native_visual
from .segment_review import recover_native_rejection, retry_transient_segment_review, resume_saved_segment_review


def advance_native_jobs(root, queue):
    root = Path(root)
    steps = queue.list()
    blocked = set()
    for job_id in sorted({s['job_id'] for s in steps if s['channel_id'] == 'religion'}):
        error_path = root / '.runtime/jobs' / job_id / 'handoffs/error-native.json'
        try:
            for step in steps:
                if step['job_id'] != job_id:
                    continue
                recover_native_rejection(root, step, queue)
                retry_transient_segment_review(root, step, queue)
                resume_saved_segment_review(root, step, queue)
            advance_native_batches(root, queue, only_job=job_id)
            advance_native_sequences(root, queue, only_job=job_id)
            advance_native_conforms(root, queue, only_job=job_id)
            advance_native_visual(root, queue, only_job=job_id)
            advance_native_captions(root, queue, only_job=job_id)
        except (ValueError, KeyError, OSError, RuntimeError, TypeError) as exc:
            blocked.add(job_id)
            problem = {'status': 'blocked', 'job_id': job_id, 'reason': str(exc)}
            if not error_path.exists() or read_json(error_path) != problem:
                write_json(error_path, problem)
        else:
            if error_path.exists() and read_json(error_path).get('status') != 'resolved':
                write_json(error_path, {'status': 'resolved', 'job_id': job_id})
    return blocked
