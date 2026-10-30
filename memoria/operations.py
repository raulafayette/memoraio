"""Independent persistent video, audio and transcript requests."""
import json
import os
import time
from .core import Failure,atomic_json,hash_file,sync_file,sync_directory,durable_mkdir

def options(store,jid):
    with store.connect() as c:r=c.execute('SELECT value FROM service_state WHERE key=?',('job_options:'+jid,)).fetchone()
    return json.loads(r[0]) if r else {}

def request(store,ids,operations,preferences=None,session_id=None):
    if not isinstance(ids,list) or not 1<=len(ids)<=2000 or any(not isinstance(i,str) for i in ids):raise ValueError('Selecione entre 1 e 2000 conteúdos')
    if not isinstance(operations,list) or not operations or not set(operations)<={'video','audio','transcript','export','formats'}:raise ValueError('Operação inválida')
    preferences=preferences or {}
    if not isinstance(preferences,dict):raise ValueError('Preferências inválidas')
    height=preferences.get('max_height',720)
    if type(height)!=int or height not in (360,480,720,1080,1440,2160):raise ValueError('Qualidade inválida')
    audio_format=preferences.get('audio_format','original')
    if audio_format not in ('original','mp3'):raise ValueError('Formato de áudio inválido')
    fmt=preferences.get('format_id')
    result=[]
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        if session_id:
            session=c.execute('SELECT state FROM channel_sessions WHERE id=?',(session_id,)).fetchone()
            if not session or session[0] not in ('discovering','planning','downloading'):return []
        def attach(iid,jid):
            if session_id:c.execute('INSERT OR IGNORE INTO session_items VALUES(?,?,?)',(session_id,iid,jid))
        for iid in dict.fromkeys(ids):
            item=c.execute('SELECT * FROM items WHERE id=? AND EXISTS(SELECT 1 FROM active_source_items asi WHERE asi.item_id=items.id)',(iid,)).fetchone()
            if not item:raise ValueError('Conteúdo fora do catálogo ativo')
            if fmt is not None:
                cached=c.execute('SELECT value FROM service_state WHERE key=?',('formats:'+iid,)).fetchone()
                formats=json.loads(cached[0]) if cached else {}
                if time.time()-formats.get('at',0)>86400 or fmt not in [f['format_id'] for f in formats.get('formats',[])]:raise ValueError('Consulte os formatos disponíveis antes de selecionar um formato específico')
            if fmt is not None:
                chosen=next(f for f in formats['formats'] if f['format_id']==fmt)
                if 'video' in operations and chosen.get('vcodec')=='none':raise ValueError('Formato selecionado não contém vídeo')
                if 'audio' in operations and 'video' not in operations and chosen.get('vcodec')!='none':raise ValueError('Escolha um formato somente de áudio para esta operação')
            for op in dict.fromkeys(operations):
                kind={'video':'download','audio':'audio','transcript':'transcribe','export':'export','formats':'formats'}[op]
                if preferences.get('only_missing',True):
                    from .inventory import assets
                    present=assets(store,c,item)
                    if op=='video' and 'video' in present:attach(iid,None);continue
                    if op=='transcript' and 'txt' in present:attach(iid,None);continue
                    if op=='audio' and ('mp3' if audio_format=='mp3' else 'audio') in present:attach(iid,None);continue
                existing=c.execute("SELECT id FROM jobs WHERE kind=? AND target=? AND state IN ('queued','running','retry','paused')",(kind,iid)).fetchone()
                opts={'max_height':height,'audio_format':audio_format,'format_id':fmt,'captions_only':bool(preferences.get('captions_only',True))}
                if existing:
                    previous=c.execute('SELECT value FROM service_state WHERE key=?',('job_options:'+existing['id'],)).fetchone()
                    if previous and json.loads(previous[0])!=opts:raise ValueError('Este conteúdo já possui uma operação com outras preferências; aguarde ou cancele a anterior')
                    attach(iid,existing['id']);result.append(existing['id']);continue
                jid=store.enqueue(c,kind,iid);c.execute('UPDATE jobs SET priority=70 WHERE id=?',(jid,))
                c.execute('INSERT INTO service_state VALUES(?,?)',('job_options:'+jid,json.dumps(opts)))
                attach(iid,jid);result.append(jid)
    return result

def probe_formats(worker,job):
    with worker.store.connect() as c:item=c.execute('SELECT * FROM items WHERE id=?',(job['target'],)).fetchone()
    raw=worker.run_command(worker.ytdlp()+['--no-playlist','--skip-download','--dump-single-json','--',item['url']],job)
    info=json.loads(raw)
    fields=('format_id','ext','format_note','height','width','fps','vcodec','acodec','filesize','filesize_approx','audio_channels','abr')
    formats=[{k:f.get(k) for k in fields} for f in info.get('formats',[]) if not f.get('has_drm') and f.get('format_id')]
    with worker.store.connect() as c:c.execute('INSERT INTO service_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('formats:'+item['id'],json.dumps({'at':time.time(),'formats':formats})))

def extract_audio(worker,job):
    import fcntl
    from .transcription import Transcriber
    store=worker.store
    with store.connect() as c:item=dict(c.execute('SELECT * FROM items WHERE id=?',(job['target'],)).fetchone())
    stage=store.root/'temporary'/item['id'];stage.mkdir(exist_ok=True)
    with (stage/'.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Failure('Conteúdo pertence a outra tarefa')
        worker.lock_fd=lock.fileno()
        try:
            prefs=options(store,job['id']);fmt=prefs.get('format_id')
            if fmt:
                with store.connect() as c:cached=c.execute('SELECT value FROM service_state WHERE key=?',('formats:'+item['id'],)).fetchone()
                record=next((f for f in json.loads(cached[0])['formats'] if f['format_id']==fmt),None) if cached else None
                if record and record.get('vcodec')!='none':fmt=None
            asset=Transcriber(worker).audio(item,job,format_id=fmt)
            if options(store,job['id']).get('audio_format')=='mp3':
                source=store.root/asset['path'];manifest=stage/'mp3.json'
                if manifest.exists():
                    cached=json.loads(manifest.read_text());path=store.root/cached['path']
                    if path.resolve().is_relative_to((store.root/'originals').resolve()) and cached['source_sha256']==asset['sha256'] and path.is_file() and hash_file(path)==cached['sha256']:return
                target=stage/'converted.mp3'
                worker.run_command([worker.tool('ffmpeg'),'-nostdin','-y','-v','error','-protocol_whitelist','file,pipe','-i',str(source),'-vn','-codec:a','libmp3lame','-q:a','2',str(target)],job)
                worker.validate(target,job)
                with target.open('rb') as f:sync_file(f.fileno())
                digest=hash_file(target);dest=store.root/'originals'/digest[:2]/(digest+'.mp3');durable_mkdir(dest.parent);os.replace(target,dest);sync_directory(dest.parent)
                from .statistics import completed_at
                conversion={'path':str(dest.relative_to(store.root)),'sha256':digest,'source_sha256':asset['sha256'],'kind':'mp3','collected_at':completed_at(store,item['id'],'mp3')}
                atomic_json(manifest,conversion)
                with store.connect() as c:c.execute('INSERT INTO service_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('mp3:'+item['id'],json.dumps(conversion)))
                assets=store.root/'metadata'/'assets'/item['id'];assets.mkdir(parents=True,exist_ok=True);atomic_json(assets/('mp3-'+digest+'.json'),conversion)
        finally:worker.lock_fd=None
