import os
"""Local VAD audit of speech not overlapped by transcript intervals."""
import argparse
import json
from pathlib import Path
import subprocess
import numpy as np
import torch
from silero_vad import load_silero_vad,get_speech_timestamps
from .core import atomic_json

def uncovered_speech(speech,segments):
    uncovered=[];speech_seconds=0;missing_seconds=0
    intervals=sorted((float(x['start']),float(x['end'])) for x in segments)
    for span in speech:
        start,end=span['start'],span['end'];speech_seconds+=end-start;cursor=start
        for a,b in intervals:
            if b<=cursor:continue
            if a>=end:break
            if a>cursor:
                gap=min(a,end)-cursor
                if gap>.35:uncovered.append([cursor,min(a,end)]);missing_seconds+=gap
            cursor=max(cursor,min(b,end))
            if cursor>=end:break
        if cursor<end and end-cursor>.35:uncovered.append([cursor,end]);missing_seconds+=end-cursor
    return {'speech_seconds':round(speech_seconds,2),'uncovered_speech_seconds':round(missing_seconds,2),'uncovered_speech_ratio':round(missing_seconds/speech_seconds,4) if speech_seconds else None,'uncovered_speech':uncovered,'method':'silero-vad6.2.3 threshold0.5; tolerance350ms','warning':'VAD é heurístico; música/ruído e fala podem ser confundidos. Não comprova texto correto.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--audio',required=True);p.add_argument('--transcript',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    # Audit in10-minute pieces, avoiding whole-file audio in RAM.
    duration=float(json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',args.audio]))['format']['duration'])
    model=load_silero_vad();speech=[]
    torch.set_num_threads(int(os.environ.get('MEMORIA_CPU_THREADS','2')))
    for start in range(0,int(duration)+1,600):
        if start>=duration:break
        raw=subprocess.check_output(['ffmpeg','-v','error','-protocol_whitelist','file,pipe','-ss',str(start),'-i',args.audio,'-t','600','-ac','1','-ar','16000','-f','f32le','pipe:1'])
        wave=torch.from_numpy(np.frombuffer(raw,dtype=np.float32).copy())
        spans=get_speech_timestamps(wave,model,sampling_rate=16000,return_seconds=True)
        speech.extend({'start':x['start']+start,'end':x['end']+start} for x in spans)
    doc=json.loads(Path(args.transcript).read_text())
    report=uncovered_speech(speech,doc['segments']);report['duration']=duration
    atomic_json(Path(args.output),report)
if __name__=='__main__':main()
