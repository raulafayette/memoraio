"""Streaming source enumeration. Exhaustion of methods is not platform completeness."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
import uuid
from .core import Failure, atomic_json

class SyncEngine:
    def __init__(self,worker):self.w=worker;self.s=worker.store
    def start(self,job):
        from .channels import scope_for_job
        session=scope_for_job(self.s,job['id'])
        with self.s.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            catalog=c.execute('SELECT value FROM service_state WHERE key=?',('catalog_only:'+job['id'],)).fetchone()
            source=dict(c.execute('SELECT * FROM sources WHERE id=?',(job['target'],)).fetchone())
            existing=c.execute("SELECT id FROM scan_runs WHERE source_id=? AND state='running' AND (?=0 OR NOT EXISTS(SELECT 1 FROM channel_sessions cs WHERE cs.scan_id=scan_runs.id AND cs.state='paused')) ORDER BY started DESC LIMIT 1",(source['id'],int(bool(catalog)))).fetchone()
            if existing and session:
                previous=c.execute('SELECT state FROM channel_sessions WHERE scan_id=? ORDER BY created DESC LIMIT 1',(existing['id'],)).fetchone()
                if previous and previous[0]=='cancelled':
                    c.execute("UPDATE scan_runs SET state='partial',finished=? WHERE id=?",(time.time(),existing['id']));existing=None
            if existing:
                if session:c.execute('UPDATE channel_sessions SET scan_id=? WHERE id=?',(existing['id'],session['id']))
                return
            rid=uuid.uuid4().hex
            c.execute('INSERT INTO scan_runs(id,source_id,started,state) VALUES(?,?,?,?)',(rid,source['id'],time.time(),'running'))
            from .channel_ui import begin_review
            begin_review(c,rid,source['id'])
            if session:c.execute('UPDATE channel_sessions SET scan_id=? WHERE id=?',(rid,session['id']))
            if catalog:c.execute('INSERT OR REPLACE INTO service_state VALUES(?,?)',('catalog_run:'+rid,'1'))
            c.execute("UPDATE sources SET status='running',inventory_state='partial',last_scan=? WHERE id=?",(time.time(),source['id']))
            if source['platform']=='instagram':
                if any(x in source['url'] for x in ('/p/','/reel/','/tv/','/stories/')):self.s.add_method(c,rid,'instagram_direct',source['url'])
                else:
                    kinds=('posts','reels') if not session or session['scope']=='public' else ('posts','reels','stories','highlights') if session['scope']=='all' else (session['scope'],)
                    for kind in kinds:self.s.add_method(c,rid,'instagram_'+kind,source['url']+'#'+kind)
            elif '/watch?' in source['url'] or '/playlist?' in source['url']:
                self.s.add_method(c,rid,'youtube_direct',source['url'])
            else:
                pinned=c.execute("SELECT value FROM service_state WHERE key=?",('channel:'+source['id'],)).fetchone()
                root='https://www.youtube.com/channel/'+pinned[0] if pinned else source['url']
                self.s.add_method(c,rid,'youtube_identity',root+'#identity')
                tabs=(('videos','shorts','streams') if session['scope']=='all' else (session['scope'],)) if session else ('videos','shorts','streams') if catalog else ('videos','shorts','streams','playlists')
                for tab in tabs:
                    self.s.add_method(c,rid,'youtube_'+tab,root+'/'+tab)
    def stream(self,args,job,consume,timeout=7200):
        # A producer cursor is acknowledged only after its complete output reaches SQLite.
        checkpoint=Path(args[args.index('--checkpoint')+1]) if '--checkpoint' in args else None
        pending_cursor=checkpoint.with_name(checkpoint.name+'.pending.xz') if checkpoint else None
        if pending_cursor:pending_cursor.unlink(missing_ok=True)
        # Separate file descriptions let the reader consume durable JSONL as the tool emits it.
        with tempfile.TemporaryDirectory(dir=self.s.root/'temporary') as directory:
            output=Path(directory)/'stdout.jsonl';errors=Path(directory)/'stderr.log'
            with open(output,'wb') as out,open(errors,'wb') as err,open(output,'r',encoding='utf-8') as reader:
                p=subprocess.Popen(args,stdout=out,stderr=err,start_new_session=True,pass_fds=(() if getattr(self.w,'lock_fd',None) is None else (self.w.lock_fd,)),env={**os.environ,'PYTHONUNBUFFERED':'1'})
                started=time.monotonic();pending='';last_ping=0
                try:
                    while True:
                        pending+=reader.read(1024*1024)
                        if len(pending)>4*1024*1024:raise Failure('Linha do extrator excedeu4MiB','failed')
                        if __import__('shutil').disk_usage(self.s.root).free<self.w.reserve:raise Failure('Reserva de disco atingida durante enumeração','blocked')
                        while '\n' in pending:
                            line,pending=pending.split('\n',1)
                            if line.strip():consume(json.loads(line))
                        self.s.heartbeat(job['id'],self.w.owner)
                        if time.monotonic()-last_ping>5:self.s.worker_ping(self.w.owner);last_ping=time.monotonic()
                        if p.poll() is not None:
                            rest=reader.read();pending+=rest
                            for line in pending.splitlines():
                                if line.strip():consume(json.loads(line))
                            if pending_cursor and pending_cursor.exists():
                                os.replace(pending_cursor,checkpoint)
                                from .core import sync_directory
                                sync_directory(checkpoint.parent)
                            break
                        if time.monotonic()-started>timeout:raise Failure('Enumeração excedeu '+str(timeout)+' segundos; itens já observados preservados')
                        time.sleep(.25)
                finally:
                    if p.poll() is None:
                        os.killpg(p.pid,signal.SIGTERM)
                        try:p.wait(timeout=3)
                        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
            stderr=errors.read_text(errors='replace')[-6000:]
            if p.returncode or 'ERROR:' in stderr:
                from .worker import classify
                raise classify(stderr)
            return stderr
    def enumerate(self,job):
        import fcntl
        lock=open(self.s.root/'temporary'/('enumerate-'+job['target']+'.lock'),'a')
        try:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise Failure('Enumeração ainda pertence a outro processo')
            self.w.lock_fd=lock.fileno()
            return self._enumerate(job)
        finally:self.w.lock_fd=None;lock.close()
    def _enumerate(self,job):
        with self.s.connect() as c:
            method=dict(c.execute('SELECT * FROM scan_methods WHERE id=?',(job['target'],)).fetchone())
            if c.execute('SELECT 1 FROM excluded_methods WHERE method_id=?',(method['id'],)).fetchone():raise Failure('Método retirado do escopo; não será executado','cancelled')
            run=dict(c.execute('SELECT * FROM scan_runs WHERE id=?',(method['run_id'],)).fetchone())
            source=dict(c.execute('SELECT * FROM sources WHERE id=?',(run['source_id'],)).fetchone())
            c.execute("UPDATE scan_methods SET state='running',error=NULL WHERE id=?",(method['id'],))
        with self.s.connect() as c:count=c.execute('SELECT count(*) FROM method_items WHERE method_id=?',(method['id'],)).fetchone()[0]
        more=False;unresolved=0
        checkpoint=self.s.root/'temporary'/('instagram-'+method['id']+'.json.xz')
        def cursor_position():
            if not checkpoint.exists():return 0
            import lzma
            try:
                with lzma.open(checkpoint,'rt') as f:return int(json.load(f)['node']['total_index'])
            except (ValueError,OSError,KeyError,EOFError,lzma.LZMAError):return 0
        cursor_before=cursor_position()
        def consume(info):
            nonlocal count,more,unresolved
            if info.get('_profile'):
                with self.s.connect() as c:c.execute('INSERT OR REPLACE INTO service_state VALUES(?,?)',('instagram-profile:'+source['id'],json.dumps(info)))
                return
            if info.get('_checkpoint'):
                more=info.get('more',False);return
            oid=str(info.get('id',''))
            # Playlist enumeration adds distinct jobs; source association means appearance, not authorship.
            if method['method']=='youtube_playlists':
                if re.fullmatch(r'[A-Za-z0-9_-]{10,100}',oid) and not oid.startswith('UC'):
                    with self.s.connect() as c:
                        c.execute('BEGIN IMMEDIATE');self.s.add_method(c,run['id'],'youtube_playlist','https://www.youtube.com/playlist?list='+oid)
                return
            iid=self.s.observe(run['id'],info,source['platform'])
            if iid:
                with self.s.connect() as c:
                    c.execute('DELETE FROM excluded_source_items WHERE source_id=? AND item_id=?',(source['id'],iid))
                    inserted=c.execute('INSERT OR IGNORE INTO method_items VALUES(?,?)',(method['id'],iid)).rowcount
                    count+=inserted
                    c.execute('UPDATE scan_methods SET count=? WHERE id=?',(count,method['id']))
            else:
                unresolved+=1
                with self.s.connect() as c:self.s.event(c,job['id'],'unresolved_entry',json.dumps({k:info.get(k) for k in ('id','title','webpage_url','availability')},ensure_ascii=False))
        try:
            if source['platform']=='youtube':
                if method['method']=='youtube_identity':
                    with self.s.connect() as c:pinned=c.execute("SELECT value FROM service_state WHERE key=?",('channel:'+source['id'],)).fetchone()
                    root='https://www.youtube.com/channel/'+pinned[0] if pinned else source['url']
                    info=json.loads(self.w.run_command(self.w.ytdlp()+['--flat-playlist','--playlist-end','1','--dump-single-json','--skip-download','--',root+'/videos'],job))
                    channel=info.get('channel_id') or info.get('id')
                    if not channel or not re.fullmatch(r'UC[A-Za-z0-9_-]{22}',channel):raise Failure('ID permanente do canal não resolvido')
                    if pinned and pinned[0]!=channel:raise Failure('Identidade do canal divergiu do ID permanente registrado','blocked')
                    with self.s.connect() as c:
                        c.execute("INSERT INTO service_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('channel:'+source['id'],channel))
                        session=c.execute('SELECT 1 FROM channel_sessions WHERE scan_id=?',(run['id'],)).fetchone()
                        if not session and not c.execute('SELECT 1 FROM service_state WHERE key=?',('catalog_run:'+run['id'],)).fetchone():self.s.add_method(c,run['id'],'youtube_uploads','https://www.youtube.com/playlist?list=UU'+channel[2:])
                    warnings=''
                else:warnings=self.stream(self.w.ytdlp()+['--flat-playlist','--dump-json','--ignore-errors','--skip-download','--',method['url']],job,consume)
            else:
                from .instagram import enumerate_instagram
                warnings=enumerate_instagram(self.w,job,method,consume)
                if more:raise Failure('Lote de100 posts salvo; continuação pelo cursor persistente','queued')
            if unresolved:raise Failure(str(unresolved)+' entradas sem identificador utilizável; detalhes no histórico','blocked')
        except Exception as error:
            if source['platform']=='instagram' and getattr(error,'state',None)=='retry' and cursor_position()>cursor_before:
                error=Failure('Lote interrompido com avanço de cursor salvo; continuação automática: '+str(error),'queued')
            with self.s.connect() as c:
                if re.search(r'does not have a (?:videos|shorts|streams|playlists) tab',str(error),re.I):
                    c.execute("UPDATE scan_methods SET state='not_applicable',count=?,error=NULL WHERE id=?",(count,method['id']));return
                c.execute('UPDATE scan_methods SET state=?,count=?,error=? WHERE id=?',(getattr(error,'state','retry'),count,str(error)[:4000],method['id']))
            raise error
        else:
            with self.s.connect() as c:c.execute("UPDATE scan_methods SET state='exhausted',count=?,error=? WHERE id=?",(count,warnings or None,method['id']))
    def reconcile(self):
        with self.s.connect() as c:runs=[dict(x) for x in c.execute("SELECT * FROM scan_runs WHERE state='running'")]
        for run in runs:
            with self.s.connect() as c:
                methods=[dict(x) for x in c.execute('SELECT * FROM scan_methods WHERE run_id=?',(run['id'],))]
                jobs=[dict(x) for x in c.execute("SELECT j.* FROM jobs j JOIN scan_methods sm ON sm.id=j.target WHERE j.kind='enumerate' AND sm.run_id=?",(run['id'],))]
                if not methods or any(j['state'] in ('queued','running','retry','paused') for j in jobs):continue
                for method in methods:method['excluded_scope']=bool(c.execute('SELECT 1 FROM excluded_methods WHERE method_id=?',(method['id'],)).fetchone())
                ok=all(x['excluded_scope'] or x['state'] in ('exhausted','not_applicable') for x in methods)
                identified=c.execute('SELECT count(*) FROM run_items ri WHERE run_id=? AND EXISTS(SELECT 1 FROM active_source_items si WHERE si.item_id=ri.item_id AND si.source_id=?)',(run['id'],run['source_id'])).fetchone()[0]
                missing=c.execute('SELECT count(*) FROM active_source_items si WHERE si.source_id=? AND NOT EXISTS(SELECT 1 FROM run_items ri WHERE ri.run_id=? AND ri.item_id=si.item_id)',(run['source_id'],run['id'])).fetchone()[0]
                method_sets={}
                for method in methods:method_sets[method['id']]={r[0] for r in c.execute('SELECT item_id FROM method_items WHERE method_id=?',(method['id'],))}
                tabs=set().union(*(method_sets[m['id']] for m in methods if not m['excluded_scope'] and m['method'] in ('youtube_videos','youtube_shorts','youtube_streams')))
                uploads=set().union(*(method_sets[m['id']] for m in methods if not m['excluded_scope'] and m['method']=='youtube_uploads'))
                comparison={'only_in_tabs':sorted(tabs-uploads),'only_in_uploads':sorted(uploads-tabs)} if any(not m['excluded_scope'] and m['method']=='youtube_uploads' for m in methods) else {'uploads_comparison':'not_available'}
                summary={'method_comparison':comparison,'identified_this_run':identified,'not_seen_this_run':missing,'methods':methods,'platform_total_known':False,'interpretation':'Métodos esgotados sem erro; total real da plataforma desconhecido' if ok else 'Enumeração parcial: há métodos com impedimento; ausência não prova remoção'}
                state='enumerated_accessible' if ok else 'partial'
                c.execute('UPDATE scan_runs SET state=?,finished=?,summary=? WHERE id=?',(state,time.time(),json.dumps(summary,ensure_ascii=False),run['id']))
                c.execute('UPDATE sources SET status=?,inventory_state=?,last_scan=?,last_success=CASE WHEN ? THEN ? ELSE last_success END WHERE id=?',(state,state,time.time(),ok,time.time(),run['source_id']))
            reports=self.s.root/'reports';reports.mkdir(exist_ok=True)
            atomic_json(reports/('scan-'+run['id']+'.json'),{**run,**summary,'state':state,'finished':time.time()})
            self.s.backup()
