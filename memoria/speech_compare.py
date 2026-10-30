"""Bounded caption/ASR disagreement; no quadratic full-document character diff."""
import argparse
import difflib
import json
from pathlib import Path
import re
from .core import atomic_json

def compare(original,recognized,window_seconds=120,max_tokens=3500):
    def group(segments):
        windows={}
        for s in segments:
            key=int(max(0,s['start'])//window_seconds)
            words=re.findall(r'\w+',s['text'].lower())
            windows.setdefault(key,[]).extend(words)
        return windows
    left=group(original);right=group(recognized);weight=0;matched=0;skipped=[]
    for key in sorted(left.keys()|right.keys()):
        a=left.get(key,[]);b=right.get(key,[])
        if len(a)>max_tokens or len(b)>max_tokens:
            skipped.append({'window_start':key*window_seconds,'original_tokens':len(a),'asr_tokens':len(b)});continue
        n=len(a)+len(b)
        if n:matched+=difflib.SequenceMatcher(None,a,b,autojunk=False).ratio()*n;weight+=n
    return {'metric':'temporal_token_disagreement_v1','window_seconds':window_seconds,'max_tokens_per_window':max_tokens,'weighted_disagreement':round(1-matched/weight,4) if weight else None,'compared_tokens':weight,'uncompared_windows':skipped,'warning':'Diferença lexical por janelas; não mede precisão semântica nem substitui revisão humana. Fronteiras temporais podem aumentar diferenças.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args();r=json.loads(Path(a.input).read_text())
    atomic_json(Path(a.output),compare(r['original'],r['recognized']))
if __name__=='__main__':main()
