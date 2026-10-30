"""Bounded caption retrieval. Never rotates IPs or bypasses platform restrictions."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

HOSTS={'www.youtube.com','youtube.com','video.google.com','timedtext.googleapis.com'}
LIMIT=8*1024*1024

def allowed(url):
    p=urlsplit(url)
    return p.scheme=='https' and p.hostname in HOSTS and p.port in (None,443) and not p.username and p.path in ('/api/timedtext','/timedtext')

class Redirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not allowed(newurl):raise ValueError('Redirecionamento de legenda recusado')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch_url(url):
    if not allowed(url):raise ValueError('Endpoint de legenda não permitido')
    with build_opener(Redirect()).open(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=20) as response:
        raw=response.read(LIMIT+1)
    if len(raw)>LIMIT:raise ValueError('Legenda excede 8 MiB')
    data=json.loads(raw)
    if not isinstance(data,dict) or not isinstance(data.get('events'),list):raise ValueError('Resposta de legenda inválida')
    return data

def alternative(video_id,preferred=None):
    from youtube_transcript_api import YouTubeTranscriptApi
    from requests import Session
    class TimedSession(Session):
        def request(self,*args,**kwargs):
            kwargs.setdefault('timeout',20)
            return super().request(*args,**kwargs)
    # New instance per subprocess: the API explicitly is not thread safe.
    with TimedSession() as session:
        tracks=list(YouTubeTranscriptApi(http_client=session).list(video_id))
        candidates=[t for t in tracks if preferred and t.language_code==preferred] or [t for t in tracks if t.language_code in ('pt','pt-BR','en')] or tracks
        candidates.sort(key=lambda t:(t.is_generated,0 if t.language_code.startswith('pt') else 1))
        if not candidates:return None
        track=candidates[0];result=track.fetch()
        return {'segments':[{'start':x.start,'end':x.start+x.duration,'text':x.text} for x in result if x.text.strip() and x.duration>0], 'language':track.language_code,'origin':'automatic_caption' if track.is_generated else 'manual_caption','provider':'youtube-transcript-api','provider_version':'1.2.4'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--request');p.add_argument('--video');p.add_argument('--language');p.add_argument('--output',required=True);a=p.parse_args()
    try:
        data=fetch_url(json.loads(Path(a.request).read_text())['url']) if a.request else alternative(a.video,a.language)
        if data is None:raise ValueError('Nenhuma legenda elegível disponível')
        Path(a.output).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    except Exception as e:
        # Do not leak signed URLs into job logs.
        status=getattr(e,'code',None);name=type(e).__name__
        if status==429 or name in ('RequestBlocked','IpBlocked','TooManyRequests'):
            print('429: limite da plataforma; aguardar',file=sys.stderr)
        elif status in (401,403):print(str(status)+': acesso restrito',file=sys.stderr)
        else:print('Legendas indisponíveis: '+name,file=sys.stderr)
        raise SystemExit(1)
if __name__=='__main__':main()
