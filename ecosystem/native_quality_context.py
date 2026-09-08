"""Compact, hash-bound timeline evidence for the independent final reviewer."""
from pathlib import Path
from .config import read_json
from .native_master import checked
from .native_batch import immutable, ref
from .quality import validate_timeline


def prepare(root, steps, review_step):
    parents = [s for s in steps if s['id'] in review_step['payload']['depends_on']
               and s['adapter'] == 'native_master' and s['state'] == 'accepted']
    if len(parents) != 1:
        raise ValueError('Native review needs its accepted master parent')
    parent = parents[0]
    visuals = [s for s in steps if s['id'] in parent['payload']['depends_on']
               and s['adapter'] == 'native_visual' and s['state'] == 'accepted']
    if len(visuals) != 1:
        raise ValueError('Native review needs its accepted visual parent')
    visual = visuals[0]
    request = read_json(checked(visual['payload']['inputs'][0]))
    segments, references = [], []
    for scene in request['scenes']:
        conform_path = checked(scene['conform_receipt'])
        conform = read_json(conform_path)
        selection_path = checked(scene['selection'])
        if (conform.get('status') != 'TECHNICAL_PASS' or conform.get('gpu_execution') is not True
                or conform.get('native_frames_preserved') != 125):
            raise ValueError('Native scene lost its conform evidence')
        segment = {key:conform[key] for key in ('source_path','source_sha256','output_path','output_sha256',
            'input_frames','output_frames','output_fps','interpolation','speed_factor','interpolated_across_cuts')}
        segment['source_id'] = scene['segment_id']
        segments.append(segment)
        references.extend([ref(conform_path),ref(selection_path)])
    timeline = {'mode':'rife_2x_por_segmento','voice_speed_factor':1.0,
                'interpolated_across_cuts':False,'segments':segments}
    errors = validate_timeline(timeline,{'segment_count':3,'input_frames_per_segment':125,
        'output_frames_per_segment':250,'output_fps':24,'total_output_frames':750})
    if errors:
        raise ValueError('; '.join(errors))
    checked(parent['result']); checked(visual['result'])
    folder = Path(root) / '.runtime/jobs' / parent['job_id'] / 'native-master'
    return immutable(folder / 'timeline-evidence.json', {'kind':'native_master_timeline_evidence_v1',
        'master':ref(Path(parent['result']['path'])),'timeline':timeline,'scene_evidence':references,
        'visual_master':ref(Path(visual['result']['path'])),
        'boundary_normalization':visual['result']['boundary_pairs'],
        'boundary_scope':'Decoded YUV of visual master before final caption burn and lossy encoding',
        'final_render_rgb_boundary_check':'not performed','semantic_review':'independent reviewer required'})
