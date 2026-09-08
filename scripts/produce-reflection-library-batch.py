"""Resume the remaining first-video sequences; all masters stay unpublished."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ecosystem.config import ROOT,read_json,write_json
from ecosystem.browser import browser_command
from ecosystem.reflection_media import build_library_sequence


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--groups',type=int,nargs='+',choices=[2,3,4],default=[2,3,4])
    parser.add_argument('--use-uploaded-references',action='store_true')
    args=parser.parse_args()
    p=args.workspace.resolve(strict=True)
    plan=read_json(p/'plan.json')
    poses=plan['first_video']['pose_plan']
    command,env=browser_command('religion','check',root=ROOT)
    progress=p/'remaining-progress.json'
    def run(script,request,label):
        write_json(progress,dict(stage=label,status='running',publication='hold_for_review'))
        for retry in range(3):
            with (p/(label+'.log')).open('a',encoding='utf-8') as log:
                result=subprocess.run([command[0],str(ROOT/'scripts'/script),str(ROOT),str(request)],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=3600)
            if result.returncode == 0 or script != 'upro-reflection-upload.cjs':
                break
            upload_request=read_json(request)
            receipts=[Path(upload_request['output'])/(item['id']+'.json') for item in upload_request['items']]
            states=[read_json(file) for file in receipts if file.exists()]
            failed=[state for state in states if state.get('state')=='failed_confirmed' and state.get('attempts',1)<3]
            uncertain=[state for state in states if state.get('state') not in {'uploaded','failed_confirmed'}]
            if not failed or uncertain:
                break
            write_json(progress,dict(stage=label,status='retrying_confirmed_upload_failure',publication='hold_for_review'))
            time.sleep(10)
        if result.returncode:
            write_json(progress,dict(stage=label,status='needs_reconciliation',log=str(p/(label+'.log')),publication='hold_for_review'))
            raise RuntimeError(label+' requires reconciliation; no automatic resubmission')
    def save_request(path,data):
        if path.exists():
            if read_json(path)!=data: raise ValueError('Existing batch request changed')
        else: write_json(path,data)
    if not args.use_uploaded_references:
        run('upro-reflection-upload.cjs',p/'upload-batch-02.json','upload-remaining')
    groups=[['coast','courtyard','mountain-lake'],['village-garden','desert-oasis','waterfall'],['vineyard']]
    motions={'coast':'Waves continuously break into foam; beach grasses sway.',
        'courtyard':'Water pours steadily from the fountain; vines and curtain sway gently.',
        'mountain-lake':'Small natural ripples cross the lake; reeds and pine branches sway softly.',
        'village-garden':'Fig leaves and flowering shrubs sway gently in the breeze.',
        'desert-oasis':'Palm fronds sway slowly and ripples cross the oasis pool.',
        'waterfall':'Water continuously falls with drifting spray; ferns move softly.',
        'vineyard':'Vine leaves and loose mantle fabric sway naturally in the breeze.'}
    completed=[]
    for group_index,scenes in enumerate(groups,2):
        if group_index not in args.groups:
            continue
        items=[]
        for scene in scenes:
            for take,camera in enumerate(['Very slow optical zoom in.','Locked-off static camera.','Very slow optical zoom out.'],1):
                receipt=read_json(p/'uploads-batch-02'/f'v1-{scene}-pose2-shot{take}.json')
                if receipt['state']!='uploaded': raise ValueError('Reference not uploaded')
                prompt=f"Photorealistic single continuous silent shot. Preserve this exact Jesus identity, clothing, body posture and location. His posture is {poses[scene]}. Keep the same natural position of torso, arms, hands and legs. Maintain direct eye contact with camera, lips closed and motionless, silent peaceful presence, gentle breathing. {motions[scene]} {camera} Stable anatomy, rocks and architecture. No duplicated objects, no extra people, no cuts, no gestures."
                items.append(dict(source_media_id=receipt['source_media_id'],source_filename=Path(receipt['file']).name,prompt=prompt,environment=scene,body_pose=poses[scene]))
        output=p/f'native-batch-{group_index:02}'
        request=p/f'animate-batch-{group_index:02}.json'
        save_request(request,dict(profile='religion-reflection-5m-library-v2',project_url=read_json(p/'upload-batch-02.json')['project_url'],output=str(output),items=items))
        run('upro-reflection-vibes.cjs',request,f'animate-{group_index:02}')
        for scene_index,scene in enumerate(scenes):
            write_json(progress,dict(stage='local-assembly',environment=scene,status='running',publication='hold_for_review'))
            sources=[output/f'native-{scene_index*3+i:02}.mp4' for i in [1,2,3]]
            result=build_library_sequence(sources,p.parent/'sequence-library'/f'{scene}-pose2-v1.mp4')
            completed.append(dict(environment=scene,path=result['path'],sha256=result['sha256'],body_pose=poses[scene],quality_review='pending'))
            write_json(p/('remaining-sequences-'+ '-'.join(map(str,args.groups))+'.json'),dict(sequences=completed))
            print(json.dumps(dict(environment=scene,status='TECHNICAL_PASS',review='pending')),flush=True)
    write_json(progress,dict(stage='sequences_rendered',status='independent_review_pending',publication='hold_for_review'))

if __name__=='__main__':
    main()
