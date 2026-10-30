import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
import sys
from .core import sync_file, durable_mkdir, Failure, Interrupted, atomic_json, hash_file, safe_metadata


def classify(stderr):
    stderr=re.sub(r'https?://[^\s]+','[URL omitida]',stderr)
    text=stderr.lower()
    if 'live event will begin' in text or 'premieres in' in text:return Failure('Publicação agendada pela fonte; nova verificação em 24 horas','deferred')
    if '429' in text or 'too many requests' in text:return Failure('Limitação temporária da plataforma: '+stderr[-1800:],'rate_limited')
    if any(x in text for x in ('401','sign in','login required','login_required','cookies','private video','authentication')):
        return Failure('Autenticação/autorização necessária: '+stderr[-1800:],'needs_auth')
    if any(x in text for x in ('429','too many requests','403','forbidden','captcha')):
        return Failure('Restrição da plataforma: '+stderr[-1800:],'blocked')
    if any(x in text for x in ('unavailable','removed','not available','unsupported url','copyright')):
        return Failure('Conteúdo indisponível ou não suportado: '+stderr[-1800:],'failed')
    return Failure('Extrator interrompido: '+stderr[-1800:])

class Worker:
    def __init__(self,store,reserve=5*1024**3,timeout=3600,lane='all'):
        self.store=store; self.reserve=reserve; self.timeout=timeout
        self.lane=lane
        self.owner=str(os.getpid())+'-'+uuid.uuid4().hex
    def run_command(self,args,job,cwd=None):
        # Process group includes ffmpeg child processes. Output goes to private files.
        from .preferences import read
        prefs=read(self.store)
        task_env={**os.environ,'PYTHONUNBUFFERED':'1','OMP_NUM_THREADS':str(prefs['cpu_threads']),'VECLIB_MAXIMUM_THREADS':str(prefs['cpu_threads']),'MEMORIA_CPU_THREADS':str(prefs['cpu_threads']),'MEMORIA_MLX_GIB':str(prefs['mlx_memory_gib'])}
        with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
            proc=subprocess.Popen(args,cwd=cwd,stdout=out,stderr=err,start_new_session=True,pass_fds=(() if getattr(self,'lock_fd',None) is None else (self.lock_fd,)),env=task_env)
            started=time.monotonic(); last_ping=0;last_progress=0
            try:
                while proc.poll() is None:
                    self.store.heartbeat(job['id'],self.owner)
                    if time.monotonic()-last_ping>5:
                        self.store.worker_ping(self.owner);last_ping=time.monotonic()
                    if time.monotonic()-started>self.timeout:raise Failure('Tempo máximo da etapa excedido')
                    if time.monotonic()-last_progress>3:
                        progress={'stage':job['kind'],'elapsed_seconds':round(time.monotonic()-started),'at':time.time()}
                        for stream in (out,err):
                            size=os.fstat(stream.fileno()).st_size
                            tail=os.pread(stream.fileno(),min(size,65536),max(0,size-65536)).decode('utf-8','replace')
                            matches=re.findall(r'MEMORIA_PROGRESS:(\d+):([^:\s]+):([^:\s]+)',tail)
                            if matches:
                                done,estimate,total=matches[-1];known=total if total.isdigit() else estimate
                                progress.update(downloaded_bytes=int(done),total_bytes=int(known) if known.isdigit() else None,estimated=not total.isdigit())
                        if 'memoria.asr' in args and '--output' in args:
                            checkpoint=Path(args[args.index('--output')+1])/'progress.json'
                            if checkpoint.exists():
                                try:progress.update(json.loads(checkpoint.read_text()))
                                except (ValueError,OSError):pass
                        with self.store.connect() as c:c.execute('INSERT INTO service_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('progress:'+job['id'],json.dumps(progress)))
                        last_progress=time.monotonic()
                    if shutil.disk_usage(self.store.root).free<self.reserve:raise Failure('Margem de disco atingida; libere espaço e retome','blocked')
                    time.sleep(.25)
                self.store.heartbeat(job['id'],self.owner)
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid,signal.SIGTERM)
                    try:proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid,signal.SIGKILL); proc.wait()
            out.seek(0);err.seek(0)
            if proc.returncode:raise classify(err.read(2*1024*1024).decode('utf-8','replace'))
            data=out.read(32*1024*1024+1)
            if len(data)>32*1024*1024:raise Failure('Saída excedeu limite de 32 MiB','failed')
            return data.decode('utf-8','replace')
    def tool(self,name):
        local=Path(sys.executable).parent/name
        executable=str(local) if local.is_file() else shutil.which(name)
        if not executable:raise Failure(name+' não instalado','blocked')
        return executable
    def ytdlp(self):
        executable=self.tool('yt-dlp')
        if not executable:raise Failure('yt-dlp não instalado','blocked')
        return [executable,'--ignore-config','--no-cache-dir','--js-runtimes','node','--progress','--newline','--progress-template','download:MEMORIA_PROGRESS:%(progress.downloaded_bytes)s:%(progress.total_bytes_estimate)s:%(progress.total_bytes)s','--sleep-requests','1','--socket-timeout','20','--retries','2','--fragment-retries','2','--extractor-retries','2','--no-warnings']
    def discover(self,job):
        with self.store.connect() as c:source=dict(c.execute('SELECT * FROM sources WHERE id=?',(job['target'],)).fetchone())
        raw=self.run_command(self.ytdlp()+['--flat-playlist','--playlist-end',str(source['scan_limit']),'--dump-single-json','--skip-download','--',source['url']],job)
        info=json.loads(raw)
        entries=info.get('entries')
        if entries is None:entries=[info]
        # Channel roots can return nested tabs: never claim a full inventory.
        count=self.store.ingest(source['id'],entries)
        if not count:raise Failure('Nenhum vídeo direto descoberto; tente /videos, /shorts ou /streams','failed')
    def validate(self,path,job):
        if not path.is_file() or path.stat().st_size==0:raise Failure('Arquivo vazio','failed')
        probe=shutil.which('ffprobe')
        if not probe:raise Failure('ffprobe não instalado','blocked')
        output=self.run_command([probe,'-v','error','-protocol_whitelist','file,pipe','-show_format','-show_streams','-of','json',str(path)],job)
        info=json.loads(output)
        if not any(x.get('codec_type') in ('audio','video') for x in info.get('streams',[])):
            raise Failure('Arquivo sem áudio ou vídeo válido','failed')
        return info
    def download(self,job):
        with self.store.connect() as c:item=dict(c.execute('SELECT * FROM items WHERE id=?',(job['target'],)).fetchone())
        stage=self.store.root/'temporary'/item['id']; stage.mkdir(exist_ok=True)
        # Expired leases cannot share partial files with a stale process: lock held until process exit.
        import fcntl
        lock=open(stage/'.lock','a')
        try:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise Failure('Outro processo ainda possui arquivos temporários')
            self.lock_fd=lock.fileno()
            from .operations import options
            prefs=options(self.store,job['id']);height=prefs.get('max_height',720)
            selector=prefs.get('format_id') or ('b' if item['platform']=='instagram' else f'bv*[ext=mp4][vcodec^=avc1][height<={height}]+ba[ext=m4a]/b[ext=mp4][height<={height}]/bv*[height<={height}]+ba/b[height<={height}]')
            variant=__import__('hashlib').sha256(selector.encode()).hexdigest()[:16]
            manifest=stage/('validated-'+variant+'.json')
            cached=None
            if manifest.exists():
                try:
                    cached=json.loads(manifest.read_text())
                    cached_path=self.store.root/cached['path']
                    if not cached_path.resolve().is_relative_to((self.store.root/'originals').resolve()) or not cached_path.is_file() or hash_file(cached_path)!=cached['hash']:cached=None
                except (OSError,ValueError,KeyError):cached=None
            if cached:
                digest=cached['hash'];target=cached_path; info=cached['metadata']; size=target.stat().st_size
            else:
                if item['platform']=='instagram':
                    from .instagram import media_command
                    received=json.loads(self.run_command(media_command(self.store,item,stage/'media.mp4'),job))
                    atomic_json(stage/'media.info.json',safe_metadata(received));output=str(stage/'media.mp4')
                else:
                    output=self.run_command(self.ytdlp()+['--no-playlist','--continue','--part','--max-filesize','2G','--format',selector,'--merge-output-format','mp4','--write-info-json','--no-write-thumbnail','--no-write-subs','--no-write-auto-subs','--output',str(stage/'media.%(ext)s'),'--print','after_move:filepath','--',item['url']],job)
                paths=[Path(x) for x in output.splitlines() if x.strip()]
                if not paths:raise Failure('Extrator não retornou arquivo','failed')
                candidate=paths[-1].resolve()
                if candidate.parent!=stage.resolve():raise Failure('Caminho inesperado do extrator','failed')
                self.validate(candidate,job)
                # Deliver a conventional MP4 even when the source only offers WebM/other codecs.
                probe=json.loads(self.run_command([self.tool('ffprobe'),'-v','error','-show_streams','-of','json',str(candidate)],job))
                streams=probe.get('streams',[])
                compatible=all(x.get('codec_name') in ('h264','aac') for x in streams if x.get('codec_type') in ('video','audio'))
                if candidate.suffix.lower()!='.mp4' or not compatible:
                    converted=stage/'standard.mp4'
                    codecs=['-c','copy'] if compatible else ['-c:v','libx264','-preset','fast','-crf','23','-threads','2','-c:a','aac','-b:a','160k']
                    self.run_command([self.tool('ffmpeg'),'-nostdin','-y','-v','error','-i',str(candidate),'-map','0:v:0','-map','0:a:0?',*codecs,'-movflags','+faststart',str(converted)],job)
                    self.validate(converted,job);candidate.unlink();candidate=converted
                digest=hash_file(candidate); size=candidate.stat().st_size
                info_path=stage/'media.info.json'
                info=safe_metadata(json.loads(info_path.read_text())) if info_path.exists() else json.loads(item['metadata'])
                target=self.store.root/'originals'/digest[:2]/(digest+candidate.suffix)
                durable_mkdir(target.parent)
                if target.exists():
                    if hash_file(target)!=digest:raise Failure('Objeto existente corrompido; preservado para inspeção','blocked')
                    candidate.unlink()
                else:
                    with open(candidate,'rb') as f:sync_file(f.fileno())
                    os.replace(candidate,target)
                    fd=os.open(target.parent,os.O_RDONLY)
                    try:os.fsync(fd)
                    finally:os.close(fd)
                atomic_json(manifest,{'path':str(target.relative_to(self.store.root)),'hash':digest,'metadata':info})
            self.store.heartbeat(job['id'],self.owner)
            atomic_json(self.store.root/'metadata'/(item['id']+'.json'),{'platform':item['platform'],'original_id':item['original_id'],'url':item['url'],'collected_at':time.time(),'extractor':self.run_command([shutil.which('yt-dlp'),'--version'],job).strip(),'sha256':digest,'size':size,'original':info})
            with self.store.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                owned=c.execute("SELECT id FROM jobs WHERE id=? AND owner=? AND state='running' AND control IS NULL",(job['id'],self.owner)).fetchone()
                if not owned:raise Interrupted('Tarefa não possui autorização de conclusão')
                c.execute("UPDATE items SET status='archived',blob_hash=?,path=?,size=? WHERE id=?",(digest,str(target.relative_to(self.store.root)),size,item['id']))
            assets=self.store.root/'metadata'/'assets'/item['id'];assets.mkdir(parents=True,exist_ok=True)
            from .statistics import completed_at
            atomic_json(assets/('video-'+digest+'.json'),{'kind':'video','path':str(target.relative_to(self.store.root)),'sha256':digest,'size':size,'selector':selector,'collected_at':completed_at(self.store,item['id'],'video')})
            # Sanitized metadata retained; raw info can contain expiring signed URLs.
            for path in stage.glob('*.info.json'):path.unlink()
        finally:
            self.lock_fd=None
            lock.close()
    def once(self):
        self.store.worker_ping(self.owner)
        if self.lane in ('process','transcript'):
            from .channels import advance
            advance(self.store,progress=lambda:self.store.worker_ping(self.owner))
        if self.lane in ('process','transcript','maintenance','all'):
            from .temporary import cleanup
            cleanup(self.store)
        if self.lane in ('acquire','all'):
            from .channels import advance
            from .sync import SyncEngine
            SyncEngine(self).reconcile()
            advance(self.store,progress=lambda:self.store.worker_ping(self.owner))
        with self.store.connect() as c:
            paused=c.execute("SELECT value FROM service_state WHERE key='paused'").fetchone()
        if paused and paused[0]=='1':return False
        kinds={'acquire':('sync','catalog_sync','enumerate','discover','download','audio','formats'),'process':('transcribe','transcribe_asr','embed','export','text_export','oracle'),'transcript':('transcribe','transcribe_asr'),'maintenance':('embed','export','text_export','organize','oracle'),'organizer':('text_export','organize')}.get(self.lane)
        channel_lane='acquire' if self.lane=='acquire' else 'transcript' if self.lane in ('process','transcript') else None
        job=self.store.claim(self.owner,kinds=kinds,channel_lane=channel_lane)
        if not job:return False
        try:
            if shutil.disk_usage(self.store.root).free<self.reserve:raise Failure('Espaço insuficiente: reserva de 5 GiB','blocked')
            if job['kind']=='discover':self.discover(job)
            elif job['kind']=='download':self.download(job)
            elif job['kind']=='audio':
                from .operations import extract_audio
                extract_audio(self,job)
            elif job['kind']=='formats':
                from .operations import probe_formats
                probe_formats(self,job)
            elif job['kind'] in ('sync','catalog_sync'):
                from .sync import SyncEngine
                SyncEngine(self).start(job)
            elif job['kind']=='enumerate':
                from .sync import SyncEngine
                SyncEngine(self).enumerate(job)
            elif job['kind'] in ('transcribe','transcribe_asr'):
                from .transcription import Transcriber
                with self.store.connect() as c:current=c.execute('SELECT created FROM transcripts WHERE item_id=? AND current=1',(job['target'],)).fetchone()
                if not current or current['created']<job['created']:Transcriber(self).run(job)
            elif job['kind']=='oracle':
                from .oracles import run_query
                run_query(self,job)
            elif job['kind']=='organize':
                from .channels import link_files
                link_files(self.store,job['target'])
            elif job['kind']=='text_export':
                from .exports import publish
                sid,iid=job['target'].split(':',1);publish(self.store,sid,iid)
            elif job['kind']=='export':
                from .library import publish_library
                publish_library(self.store,job['target'])
            elif job['kind']=='embed':
                from .semantic import embed_transcript
                embed_transcript(self,job)
            else:raise Failure('Tipo de tarefa desconhecido','failed')
            if job['kind'] in ('download','audio','export'):
                from .channels import link_files
                link_files(self.store,job['target'])
        except Exception as error:
            self.store.finish(job,self.owner,error)
            print(json.dumps({'job':job['id'],'event':'error','type':type(error).__name__,'detail':str(error)},ensure_ascii=False),flush=True)
        else:self.store.finish(job,self.owner)
        from .sync import SyncEngine
        SyncEngine(self).reconcile()
        return True
    def run(self):
        while True:
            try:
                if not self.once():time.sleep(1)
            except KeyboardInterrupt:return
            except Exception as error:
                print(json.dumps({'event':'worker_error','type':type(error).__name__,'detail':str(error)},ensure_ascii=False),flush=True)
                time.sleep(3)
