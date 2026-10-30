import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import urlsplit,parse_qs

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,store,port=8765):
        self.store=store; self.token=secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1',port),Handler)
        self.allowed_hosts={f'127.0.0.1:{self.server_port}',f'localhost:{self.server_port}'}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):
        # Do not put the bootstrap token in access logs.
        pass
    def send(self,status,data,ctype='application/json',extra=None):
        if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',ctype)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; media-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for k,v in (extra or {}).items():self.send_header(k,v)
        try:
            self.end_headers()
            if self.command!='HEAD':self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass
    def authorized(self):
        if self.headers.get('Host') not in self.server.allowed_hosts:return False
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception:return False
        return 'memoria' in cookie and hmac.compare_digest(cookie['memoria'].value,self.server.token)
    def do_GET(self):
        p=urlsplit(self.path)
        if self.headers.get('Host') not in self.server.allowed_hosts:
            return self.send(403,{'error':'Host não permitido'})
        if p.path=='/' and hmac.compare_digest(parse_qs(p.query).get('token',[''])[0],self.server.token):
            return self.send(303,b'',extra={'Location':'/','Set-Cookie':'memoria='+self.server.token+'; HttpOnly; SameSite=Strict; Path=/'})
        if not self.authorized():return self.send(403,{'error':'Abra pelo endereço informado pelo aplicativo no início da sessão'})
        try:
            if p.path=='/api/statistics':
                from .statistics import summary
                return self.send(200,summary(self.server.store,parse_qs(p.query).get('timezone',['UTC'])[0]))
            if p.path=='/api/directories':
                from .exports import default_directory
                return self.send(200,{'default_directory':str(default_directory(self.server.store))})
            if p.path=='/api/channel-files':
                from .exports import locations
                return self.send(200,{'locations':locations(self.server.store,parse_qs(p.query).get('id',[''])[0],parse_qs(p.query).get('item',[None])[0])})
            if p.path=='/api/directory':
                from .exports import default_directory,ensure_directory
                sid=parse_qs(p.query).get('id',[''])[0]
                if sid:
                    with self.server.store.connect() as c:source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
                    if not source:raise ValueError('Canal desconhecido')
                    path=ensure_directory(self.server.store,source)
                else:
                    path=default_directory(self.server.store);path.mkdir(parents=True,exist_ok=True)
                return self.send(200,{'path':str(path)})
            if p.path=='/api/instagram':
                from .instagram import connection_status
                return self.send(200,connection_status(self.server.store))
            if p.path=='/api/channel-state':
                from .channel_ui import control_state
                return self.send(200,control_state(self.server.store,parse_qs(p.query).get('id',[''])[0]))
            if p.path=='/api/channel-news':
                from .channel_ui import news
                q=parse_qs(p.query)
                return self.send(200,news(self.server.store,q.get('id',[''])[0],int(q.get('limit',['100'])[0]),int(q.get('offset',['0'])[0])))
            if p.path=='/api/channels':
                from .channels import status
                return self.send(200,status(self.server.store))
            if p.path=='/api/batches':
                from .channels import batches
                return self.send(200,batches(self.server.store))
            if p.path=='/api/branding':
                return self.send(200,json.loads((Path(__file__).parent.parent/'branding.json').read_text()))
            if p.path=='/api/state':return self.send(200,self.server.store.snapshot())
            if p.path=='/api/inventory':
                from .inventory import inventory
                return self.send(200,inventory(self.server.store,parse_qs(p.query)))
            if p.path=='/api/oracle-history':
                from .oracles import history
                return self.send(200,{'queries':history(self.server.store,parse_qs(p.query).get('id',[None])[0])})
            if p.path=='/api/oracles':
                from .oracles import list_oracles
                return self.send(200,{'oracles':list_oracles(self.server.store)})
            if p.path.startswith('/api/oracle-queries/'):
                from .oracles import query_status
                return self.send(200,query_status(self.server.store,p.path.split('/')[-1]))
            if p.path=='/api/preferences':
                from .preferences import read
                return self.send(200,read(self.server.store))
            if p.path in ('/api/items','/api/select'):
                q=parse_qs(p.query);offset=max(0,int(q.get('offset',['0'])[0]));limit=min(200,max(1,int(q.get('limit',['100'])[0])))
                sql='SELECT i.*,EXISTS(SELECT 1 FROM audio_assets a WHERE a.item_id=i.id) AS audio_available,EXISTS(SELECT 1 FROM service_state ss WHERE ss.key=\'mp3:\'||i.id) AS mp3_available,t.quality AS transcript_quality,t.origin AS transcript_origin FROM items i LEFT JOIN transcripts t ON t.item_id=i.id AND t.current=1 WHERE EXISTS(SELECT 1 FROM active_source_items asi WHERE asi.item_id=i.id)';params=[]
                if q.get('source'):sql+=' AND EXISTS(SELECT 1 FROM active_source_items si WHERE si.item_id=i.id AND si.source_id=?)';params.append(q['source'][0])
                if q.get('title'):sql+=' AND i.title LIKE ?';params.append('%'+q['title'][0]+'%')
                for key,op in [('after','>='),('before','<=')]:
                    if q.get(key):
                        value=q[key][0].replace('-','')
                        if not re.fullmatch(r'\d{8}',value):raise ValueError('Data inválida')
                        sql+=" AND json_extract(i.metadata,'$.upload_date')"+op+'?';params.append(value)
                for key,op in [('min_seconds','>='),('max_seconds','<=')]:
                    if q.get(key):
                        value=int(q[key][0])
                        if not 0<=value<=604800:raise ValueError('Duração inválida')
                        sql+=" AND json_extract(i.metadata,'$.duration')"+op+'?';params.append(value)
                shorts="EXISTS(SELECT 1 FROM method_items mi JOIN scan_methods sm ON sm.id=mi.method_id WHERE mi.item_id=i.id AND sm.method='youtube_shorts' AND NOT EXISTS(SELECT 1 FROM excluded_methods em WHERE em.method_id=sm.id))"
                if q.get('type')==['shorts']:sql+=' AND '+shorts
                elif q.get('type')==['regular']:sql+=' AND NOT '+shorts
                if p.path=='/api/select':
                    with self.server.store.connect() as c:ids=[x['id'] for x in c.execute(sql+' ORDER BY i.id LIMIT 10001',params)]
                    if len(ids)>10000:raise ValueError('Refine os filtros: limite de seleção de 10.000 conteúdos')
                    return self.send(200,{'ids':ids})
                sql+=' ORDER BY i.rowid DESC LIMIT ? OFFSET ?';params.extend([limit,offset])
                with self.server.store.connect() as c:rows=[dict(x) for x in c.execute(sql,params)]
                return self.send(200,{'items':rows,'offset':offset,'limit':limit})
            if p.path.startswith('/api/exports/'):
                parts=p.path.split('/');iid,fmt=parts[-2:]
                if fmt not in ('txt','json','srt','vtt'):raise ValueError('Formato inválido')
                with self.server.store.connect() as c:
                    item=c.execute('SELECT * FROM items WHERE id=?',(iid,)).fetchone()
                    row=c.execute('SELECT * FROM transcripts WHERE item_id=? AND current=1',(iid,)).fetchone()
                if not row or not item:return self.send(404,{'error':'Transcrição indisponível'})
                from .core import hash_file
                from .library import enrich,rich_text
                path=(self.server.store.root/row['path']).resolve()
                if not path.is_relative_to((self.server.store.root/'transcripts').resolve()) or hash_file(path)!=row['sha256']:return self.send(409,{'error':'Integridade inválida'})
                doc=enrich(self.server.store,dict(item),json.loads(path.read_text()))
                if fmt=='json':body=json.dumps(doc,ensure_ascii=False,indent=2)
                elif fmt=='txt':body=rich_text(doc)
                else:body=(path.parent/('transcript.'+fmt)).read_text()
                return self.send(200,body.encode('utf-8'),'text/plain; charset=utf-8',{'Content-Disposition':('inline' if parse_qs(p.query).get('open')==['1'] else 'attachment')+'; filename="'+iid+'.'+fmt+'"'})
            if p.path=='/api/formats':
                q=parse_qs(p.query);iid=q.get('id',[''])[0]
                with self.server.store.connect() as c:r=c.execute('SELECT value FROM service_state WHERE key=?',('formats:'+iid,)).fetchone()
                return self.send(200,json.loads(r[0]) if r else {'formats':[],'pending':True})
            if p.path=='/api/search':
                q=parse_qs(p.query);query=q.get('q',[''])[0]
                if len(query)>1000:return self.send(400,{'error':'Consulta muito longa'})
                if q.get('mode')==['hybrid']:
                    from .oracles import retrieve
                    results=retrieve(self.server.store,query,q.get('palace',[None])[0],'hybrid')
                elif q.get('mode')==['semantic']:
                    from .semantic import search_semantic
                    results=search_semantic(self.server.store,query,q.get('palace',[None])[0],q.get('source',[None])[0])
                else:results=self.server.store.search(query,q.get('palace',[None])[0],q.get('source',[None])[0])
                return self.send(200,{'results':results,'generated_answer':False,'warning':'Trechos recuperados; sem certificação de integralidade ou resposta gerada.'})
            if p.path.startswith('/api/transcripts/'):
                iid=p.path.split('/')[-1]
                with self.server.store.connect() as c:
                    row=c.execute('SELECT * FROM transcripts WHERE item_id=? AND current=1',(iid,)).fetchone()
                    attempts=[dict(x) for x in c.execute('SELECT * FROM item_attempts WHERE item_id=? ORDER BY at DESC LIMIT 50',(iid,))]
                    audio=c.execute('SELECT item_id FROM audio_assets WHERE item_id=?',(iid,)).fetchone()
                if not row:return self.send(200,{'transcript':None,'attempts':attempts,'audio':bool(audio)})
                from .core import hash_file
                path=(self.server.store.root/row['path']).resolve()
                if not path.is_relative_to((self.server.store.root/'transcripts').resolve()) or hash_file(path)!=row['sha256']:return self.send(409,{'error':'Transcrição ausente ou com hash divergente'})
                return self.send(200,{'transcript':json.loads(path.read_text()),'record':dict(row),'attempts':attempts,'audio':bool(audio)})
            if p.path.startswith(('/media/','/audio/')):
                iid=p.path.split('/')[-1]
                with self.server.store.connect() as c:
                    r=c.execute('SELECT path FROM audio_assets WHERE item_id=?',(iid,)).fetchone() if p.path.startswith('/audio/') else c.execute("SELECT path FROM items WHERE id=? AND status='archived'",(iid,)).fetchone()
                if p.path.startswith('/audio/') and parse_qs(p.query).get('format')==['mp3']:
                    with self.server.store.connect() as c:converted=c.execute('SELECT value FROM service_state WHERE key=?',('mp3:'+iid,)).fetchone()
                    r=json.loads(converted[0]) if converted else None
                if not r or not r['path']:return self.send(404,{'error':'Arquivo não encontrado'})
                target=(self.server.store.root/r['path']).resolve()
                if not target.is_relative_to((self.server.store.root/'originals').resolve()) or not target.is_file():return self.send(404,{'error':'Arquivo ausente'})
                size=target.stat().st_size;start=0;end=size-1;status=200
                req=self.headers.get('Range')
                if req:
                    match=re.fullmatch(r'bytes=(\d+)-(\d*)',req)
                    if not match:return self.send(416,b'')
                    start=int(match[1]);end=min(size-1,int(match[2])) if match[2] else size-1;status=206
                    if start>end:return self.send(416,b'')
                self.send_response(status)
                self.send_header('Content-Type',mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
                self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes')
                self.send_header('Cache-Control','no-store')
                if parse_qs(p.query).get('download')==['1']:self.send_header('Content-Disposition','attachment; filename="'+iid+target.suffix+'"')
                self.send_header('X-Content-Type-Options','nosniff')
                if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                self.end_headers()
                with open(target,'rb') as f:
                    f.seek(start);left=end-start+1
                    while left:
                        chunk=f.read(min(left,1024*1024))
                        if not chunk:break
                        self.wfile.write(chunk);left-=len(chunk)
                return
            files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
            if p.path not in files:return self.send(404,{'error':'Não encontrado'})
            target=Path(__file__).parent/'static'/files[p.path]
            return self.send(200,target.read_bytes(),mimetypes.guess_type(target.name)[0] or 'text/plain')
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception:return self.send(500,{'error':'Falha interna; consulte o diagnóstico'})
    def do_POST(self):
        if not self.authorized():return self.send(403,{'error':'Acesso local não autorizado'})
        origin=self.headers.get('Origin')
        if origin not in {f'http://{h}' for h in self.server.allowed_hosts}:return self.send(403,{'error':'Origem não permitida'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=128*1024:raise ValueError('Corpo ausente ou muito grande')
            if self.headers.get('Content-Type')!='application/json':raise ValueError('Use JSON')
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):raise ValueError('Objeto JSON esperado')
            if self.path=='/api/shutdown':
                self.send(200,{'result':'Sessão encerrada. Reabra o aplicativo para retomar.'})
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            if self.path=='/api/channel-directory':
                from .exports import set_source_directory
                result=set_source_directory(self.server.store,data.get('id'),data.get('directory',''))
            elif self.path=='/api/instagram/session':
                from .instagram import save_session
                result=save_session(self.server.store,data)
            elif self.path=='/api/instagram/disconnect':
                from .instagram import disconnect
                result=disconnect(self.server.store)
            elif self.path=='/api/catalog-refresh':
                from .channels import refresh_catalog,status
                ids=data.get('ids') or [s['id'] for s in status(self.server.store)['channels']]
                if not isinstance(ids,list) or not 1<=len(ids)<=100:raise ValueError('Selecione até 100 fontes')
                result=[refresh_catalog(self.server.store,sid) for sid in ids]
            elif self.path=='/api/channel-batch':
                from .channel_ui import batch_start
                return self.send(200,{'results':batch_start(self.server.store,data.get('ids'),data.get('scopes'))})
            elif self.path=='/api/channel-start':
                from .channels import start
                result=start(self.server.store,data.get('id'),'transcript',data.get('scope','all'))
                from .channel_ui import control_state
                return self.send(200,{'result':result,'state':control_state(self.server.store,data.get('id'))})
            elif self.path=='/api/channel-control':
                from .channels import control
                result=control(self.server.store,data.get('id'),data.get('action'))
                from .channel_ui import control_state
                return self.send(200,{'result':result,'state':control_state(self.server.store,data.get('id'))})
            elif self.path=='/api/download-start':
                from .channels import start
                sid=self.server.store.register_source(data.get('url'),queue_paused=True)
                result=start(self.server.store,sid,data.get('mode','video'),data.get('scope','all'))
            elif self.path=='/api/oracles':
                from .oracles import configure
                result=configure(self.server.store,data.get('name'),data.get('purpose',''),data.get('sources'),data.get('rules',''),data.get('strategy','hybrid'),data.get('id'))
            elif self.path=='/api/oracle-query':
                from .oracles import enqueue_query
                result=enqueue_query(self.server.store,data.get('id'),data.get('query'),bool(data.get('exhaustive')))
            elif self.path=='/api/preferences':
                from .preferences import save
                result=save(self.server.store,data)
            elif self.path=='/api/import':
                from .core import canonical
                urls=data.get('urls')
                if not isinstance(urls,list) or not 1<=len(urls)<=100:raise ValueError('Informe entre 1 e 100 URLs')
                urls=list(dict.fromkeys(canonical(url) for url in urls));result=[];source_ids=[]
                for url in urls:
                    from .exports import register_channel
                    from .channels import refresh_catalog
                    sid=register_channel(self.server.store,url)
                    result.append(refresh_catalog(self.server.store,sid));source_ids.append(sid)
                return self.send(200,{'result':result,'sources':source_ids})
            elif self.path=='/api/sources':
                from .exports import register_channel
                result=register_channel(self.server.store,data.get('url'),data.get('name'))
            elif self.path=='/api/register':
                from .exports import register_channel
                result=register_channel(self.server.store,data.get('url'),data.get('name'))
            elif self.path=='/api/sync':result=self.server.store.sync_now(data.get('id'))
            elif self.path=='/api/schedule':
                if data.get('cadence')!='manual':raise ValueError('Os downloads são manuais; não há agenda automática')
                result=self.server.store.schedule_source(data.get('id'),'manual')
            elif self.path=='/api/reprocess':result=self.server.store.reprocess(data.get('ids'),bool(data.get('force_asr')))
            elif self.path=='/api/palaces':result=self.server.store.palace(data.get('name'),data.get('description',''),data.get('sources',[]))
            elif self.path=='/api/review':
                import time
                with self.server.store.connect() as c:
                    row=c.execute('SELECT id,item_id FROM transcripts WHERE item_id=? AND current=1',(data.get('id'),)).fetchone()
                    if not row:raise ValueError('Transcrição não encontrada')
                    c.execute("UPDATE transcripts SET quality='human_verified' WHERE id=?",(row['id'],))
                    c.execute("INSERT INTO item_attempts(item_id,at,method,state,detail) VALUES(?,?,'human_review','verified',?)",(row['item_id'],time.time(),'Revisão confirmada explicitamente pela interface local'))
                result=row['id']
            elif self.path=='/api/service':
                from .service import set_paused
                result=set_paused(self.server.store,data.get('paused'),bool(data.get('interrupt_running')))
            elif self.path=='/api/operations':
                from .operations import request
                result=request(self.server.store,data.get('ids'),data.get('operations'),data.get('preferences'))
            elif self.path=='/api/archive':result=self.server.store.archive(data.get('ids'))
            elif self.path=='/api/control':result=self.server.store.control(data.get('id'),data.get('action'))
            elif self.path=='/api/backup':result=str(self.server.store.backup().relative_to(self.server.store.root))
            else:return self.send(404,{'error':'Não encontrado'})
            return self.send(200,{'result':result})
        except (ValueError,TypeError,KeyError) as error:return self.send(400,{'error':str(error)})
        except Exception:return self.send(503,{'error':'Operação não concluída; banco ocupado ou recurso indisponível. Tente novamente.'})
