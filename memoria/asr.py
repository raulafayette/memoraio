"""MLX Whisper chunk checkpoints. Subprocess owns GPU memory only while working."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
from .core import atomic_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--audio',required=True);p.add_argument('--output',required=True);p.add_argument('--model',required=True);p.add_argument('--revision',required=True);p.add_argument('--hash',required=True);args=p.parse_args()
    import mlx_whisper
    import mlx.core as mx
    if hasattr(mx,'set_memory_limit'):mx.set_memory_limit(int(os.environ.get('MEMORIA_MLX_GIB','4'))*1024**3)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',args.audio]))
    duration=float(probe['format']['duration']);directory=Path(args.output)
    version=importlib.metadata.version('mlx-whisper')
    settings={'audio_sha256':args.hash,'model_revision':args.revision,'engine':'mlx-whisper','engine_version':version,'mlx_version':importlib.metadata.version('mlx'),'python_version':__import__('platform').python_version(),'chunk_seconds':600,'overlap_seconds':3,'word_timestamps':True,'condition_on_previous_text':False,'language':None,'task':'transcribe'}
    key=hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()[:20]
    directory=directory/key;directory.mkdir(parents=True,exist_ok=True)
    combined=[];language=None
    for number,offset in enumerate(range(0,int(duration)+1,600)):
        if offset>=duration:break
        start=max(0,offset-3);end=min(duration,offset+603)
        checkpoint=directory/f'chunk-{number:05}.json'
        if checkpoint.exists():raw=json.loads(checkpoint.read_text())
        else:
            wav=directory/f'chunk-{number:05}.wav'
            subprocess.run(['ffmpeg','-v','error','-xerror','-protocol_whitelist','file,pipe','-ss',str(start),'-i',args.audio,'-t',str(end-start),'-ac','1','-ar','16000','-y',str(wav)],check=True)
            raw=mlx_whisper.transcribe(str(wav),path_or_hf_repo=args.model,word_timestamps=True,condition_on_previous_text=False,task='transcribe',verbose=False)
            atomic_json(checkpoint,raw);wav.unlink(missing_ok=True)
        atomic_json(Path(args.output)/'progress.json',{'stage':'local_asr','completed_audio_seconds':min(duration,offset+600),'duration_seconds':duration,'completed_chunks':number+1})
        language=raw.get('language',language)
        for seg in raw.get('segments',[]):
            words=[w for w in seg.get('words',[]) if offset<=start+(w['start']+w['end'])/2<min(duration,offset+600)]
            if words:
                item={k:v for k,v in seg.items() if k not in ('tokens','words')}
                item.update(start=max(0,start+words[0]['start']),end=min(duration,start+words[-1]['end']),text=''.join(w['word'] for w in words).strip())
            elif not seg.get('words') and offset<=start+(seg['start']+seg['end'])/2<min(duration,offset+600):
                item={k:v for k,v in seg.items() if k!='tokens'};item.update(start=start+seg['start'],end=min(duration,start+seg['end']))
            else:continue
            if item['text'] and item['end']>item['start']:combined.append(item)
    combined.sort(key=lambda x:x['start'])
    atomic_json(Path(args.output)/'result.json',{'segments':combined,'language':language,'model':settings,'duration':duration})
if __name__=='__main__':main()
