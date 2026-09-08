"""Generate a bounded continuation from a user-approved synthetic voice reference."""
import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--request',type=Path,required=True)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    request=json.loads(args.request.read_text(encoding='utf-8-sig'))
    reference=Path(request['reference_audio'])
    if digest(reference)!=request['reference_sha256'] or not request.get('user_approved_reference'):
        raise ValueError('Missing approved, intact synthetic voice reference')
    if len(request['text'].split())>250 or not request['reference_text'].strip():
        raise ValueError('Expected a short continuation and exact reference transcript')
    if args.output.exists() or not (args.model/'model.safetensors').is_file():
        raise ValueError('Require an installed model and a new output')
    import torch
    import soundfile as sf
    from qwen_tts import Qwen3TTSModel
    torch.manual_seed(42)
    torch.set_num_threads(4)
    model=Qwen3TTSModel.from_pretrained(str(args.model),device_map='cuda:0',
        dtype=torch.bfloat16,attn_implementation='sdpa',local_files_only=True)
    print('Local voice-reference model loaded',flush=True)
    prompt=model.create_voice_clone_prompt(ref_audio=str(reference),
        ref_text=request['reference_text'],x_vector_only_mode=False)
    waves,rate=model.generate_voice_clone(text=request['text'],language='Spanish',
        voice_clone_prompt=prompt,non_streaming_mode=True,max_new_tokens=1800,
        do_sample=True,subtalker_dosample=True,temperature=0.9,top_p=1.0)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    sf.write(str(args.output),waves[0],rate,subtype='PCM_16')
    receipt={'path':str(args.output.resolve()),'sha256':digest(args.output),
             'reference_sha256':request['reference_sha256'],'request_sha256':digest(args.request),
             'duration_seconds':len(waves[0])/rate,'sample_rate':rate,
             'provider':'local Qwen3-TTS Base','network_calls':0,'voice_identity_review':'pending'}
    args.output.with_suffix('.json').write_text(json.dumps(receipt,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'status':'AUDIO_GENERATED','duration_seconds':receipt['duration_seconds']}),flush=True)


if __name__=='__main__':
    main()
