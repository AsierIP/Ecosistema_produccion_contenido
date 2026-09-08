"""Conform only independently accepted native clips with the installed GPU model."""
from pathlib import Path
from .cache import file_hash
from .config import read_json
from .native_batch import immutable, ref

CHECKS = {'full_decode_pass', 'normal_speed_playback_pass', 'start_reference_metrics_pass',
          'first_half_second_continuity_pass', 'direct_camera_gaze_absent', 'portrait_pose_absent',
          'narration_action_alignment_pass', 'causal_emotion_progression_pass', 'exit_state_achieved'}


def accepted_source(selection_ref):
    path = Path(selection_ref['path'])
    if file_hash(path) != selection_ref['sha256']:
        raise ValueError('Native selection changed before GPU processing')
    selection = read_json(path)
    if selection.get('decision') != 'ACCEPT' or selection.get('defects'):
        raise ValueError('GPU conform requires independent native acceptance')
    source = Path(selection['candidate']['path'])
    if file_hash(source) != selection['candidate']['sha256']:
        raise ValueError('Accepted native source changed')
    visual = Path(selection['visual_review_receipt_path'])
    if file_hash(visual) != selection['visual_review_receipt_sha256'].lower():
        raise ValueError('Independent native review changed')
    report = read_json(visual)
    if (report.get('decision') != 'PASS' or report.get('candidate_sha256') != file_hash(source)
            or report.get('reviewer') != {'role': 'quality', 'model': 'gpt-5.6-sol', 'reasoning_effort': 'medium', 'independent': True}
            or set(report.get('claims', {})) != CHECKS
            or any(value is not True for value in report['claims'].values())):
        raise ValueError('Native review does not pass every mandatory check')
    last = selection['native_last_frame']
    if (last['frame_index'] != 124 or last['source_mp4_sha256'].lower() != file_hash(source)
            or file_hash(Path(last['path'])) != last['file_sha256'].lower()
            or last['quality_receipt_sha256'].lower() != file_hash(visual) or not last.get('accepted_at')):
        raise ValueError('Accepted native endpoint lost its source or review binding')
    return selection, source


def conform(request_path, *, root):
    request = read_json(request_path)
    if request.get('kind') != 'native_conform_v1' or request.get('channel_id') != 'religion':
        raise ValueError('Native interpolation is scoped to Religion')
    selection, source = accepted_source(request['selection'])
    output = Path(request['output']).resolve()
    if output.drive.lower() != 'e:':
        raise ValueError('Religion native media must remain on E:')
    from .rife import conform_segment
    result = conform_segment(source, output, root=root)
    if result.get('status') != 'TECHNICAL_PASS' or result['source_sha256'] != selection['candidate']['sha256']:
        raise ValueError('Native GPU conform did not preserve its accepted source')
    return result


def advance_native_conforms(root, queue, *, only_job=None):
    root = Path(root)
    for batch_path in (root / '.runtime/upro/native-batches').glob('*/batch.json'):
        if only_job is not None and read_json(batch_path).get('job_id') != only_job:
            continue
        state_path = batch_path.parent / 'state.json'
        if not state_path.exists():
            continue
        state = read_json(state_path)
        if state.get('status') != 'ACCEPTED':
            continue
        batch = read_json(batch_path)
        if state['batch_sha256'] != file_hash(batch_path):
            raise ValueError('Accepted native batch changed')
        selection, source = accepted_source(state['selected'])
        folder = root / '.runtime/jobs' / batch['job_id'] / 'native-conform' / batch['segment_id']
        request_path = immutable(folder / 'request.json', {'kind': 'native_conform_v1', 'channel_id': batch['channel_id'],
            'selection': state['selected'], 'output': str(source.parent / (batch['segment_id'] + '-conformed.mp4'))})
        queue.register({'schema_version': 1, 'channel_id': batch['channel_id'], 'job_id': batch['job_id'],
                        'adapter': 'native_conform', 'mode': batch['mode'], 'inputs': [ref(request_path)]})
