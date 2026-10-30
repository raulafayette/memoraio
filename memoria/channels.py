"""Explicit, durable channel runs: inventory -> discovery -> selected downloads."""
import json
from pathlib import Path
import re
import time
import uuid
from .core import atomic_json
from .inventory import assets

ACTIVE=('discovering','planning','downloading','paused')
SCHEMA='''
CREATE TABLE IF NOT EXISTS channel_sessions(id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(id),mode TEXT NOT NULL,scope TEXT NOT NULL,state TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,scan_job TEXT,scan_id TEXT,existing_count INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS one_channel_session ON channel_sessions(source_id) WHERE state IN ('discovering','planning','downloading','paused');
CREATE TABLE IF NOT EXISTS channel_queue(source_id TEXT PRIMARY KEY REFERENCES sources(id),added REAL NOT NULL);
CREATE TABLE IF NOT EXISTS session_items(session_id TEXT REFERENCES channel_sessions(id),item_id TEXT REFERENCES items(id),job_id TEXT,PRIMARY KEY(session_id,item_id));
'''

def folder(store,source):
    slug=re.sub(r'[^\w .-]','',source['name'] or 'Canal',flags=re.UNICODE).strip()[:70] or 'Canal'
    return store.root/'channels'/(slug+' - '+source['id'][:8])

def start(store,sid,mode='transcript',scope='all'):
    if mode not in ('transcript','video','mp3'):raise ValueError('Escolha TXT, MP3 ou MP4')
    if scope not in ('all','videos','streams','shorts','posts','reels','public','stories','highlights'):raise ValueError('Escolha um tipo de conteúdo válido')
    # File verification must not hold the SQLite writer lock. Claims/publication continue.
    with store.connect() as inventory_connection:
        old_inventory=inventory_connection.execute("SELECT 1 FROM channel_sessions WHERE source_id=? AND state IN ('discovering','planning','downloading','paused')",(sid,)).fetchone()
        items=inventory_connection.execute('SELECT i.* FROM items i JOIN active_source_items a ON a.item_id=i.id WHERE a.source_id=?',(sid,)).fetchall() if not old_inventory else []
        kind='txt' if mode=='transcript' else 'video' if mode=='video' else 'mp3'
        existing=sum(kind in assets(store,inventory_connection,item) for item in items)
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
        if not source:raise ValueError('Canal desconhecido')
        allowed=('all','public','posts','reels','stories','highlights') if source['platform']=='instagram' else ('all','videos','streams','shorts')
        if scope not in allowed:raise ValueError('Este tipo de conteúdo não pertence à plataforma escolhida')
        if source['platform']=='instagram' and (scope in ('stories','highlights') or scope=='all') and not (store.root/'instagram-session.json').is_file():raise ValueError('Para stories, destaques ou todos os conteúdos, conecte sua conta pelo botão Conectar Instagram. Para acesso público, escolha Feed e reels.')
        if source['platform']=='instagram' and mode=='transcript':
            from .preferences import read
            if not read(store)['instagram_asr']:raise ValueError('Autorize a transcrição de áudio do Instagram nos Ajustes')
            if not (store.root/'asr-model.json').is_file():raise ValueError('O modelo de voz está sendo preparado. Aguarde para iniciar o Instagram.')
        old=c.execute("SELECT * FROM channel_sessions WHERE source_id=? AND state IN ('discovering','planning','downloading','paused')",(sid,)).fetchone()
        if old:
            if old['mode']!=mode or old['scope']!=scope:raise ValueError('Já existe um lote deste canal em andamento. Pause ou encerre o lote antes de mudar o conteúdo ou formato.')
            return old['id']
        stopping=c.execute("SELECT 1 FROM jobs j LEFT JOIN scan_methods sm ON sm.id=j.target LEFT JOIN scan_runs r ON r.id=sm.run_id WHERE j.state='running' AND (j.target=? OR r.source_id=?) AND j.control IN ('pause','cancel')",(sid,sid)).fetchone()
        if stopping:raise ValueError('O lote anterior está encerrando. Aguarde alguns segundos e inicie novamente.')
        # Check physical files afresh on every user-initiated run.
        now=time.time();session=uuid.uuid4().hex
        if mode=='transcript':c.execute('DELETE FROM channel_queue WHERE source_id=?',(sid,))
        jid=store.enqueue(c,'sync',sid);c.execute('UPDATE jobs SET priority=100 WHERE id=?',(jid,))
        c.execute('INSERT INTO channel_sessions VALUES(?,?,?,?,?,?,?,?,?,?)',(session,sid,mode,scope,'discovering',now,now,jid,None,existing))
        c.execute("UPDATE sources SET auto_process=0,cadence='manual',next_sync=NULL WHERE id=?",(sid,))
        store.event(c,jid,'manual_channel_start',json.dumps({'session':session,'scope':scope,'mode':mode,'existing':existing}))
    folder(store,source).mkdir(parents=True,exist_ok=True)
    from .exports import ensure_directory
    ensure_directory(store,source)
    return session

def scope_for_job(store,jid):
    with store.connect() as c:r=c.execute('SELECT * FROM channel_sessions WHERE scan_job=?',(jid,)).fetchone()
    return dict(r) if r else None

def candidates(store,c,session,source,limit=64):
    scope=session['scope'];platform=source['platform']
    methods=['youtube_'+s for s in (('videos','streams','shorts') if scope=='all' else (scope,))]
    if platform=='instagram':methods=['instagram_'+s for s in (('posts','reels','stories','highlights') if scope=='all' else ('posts','reels') if scope=='public' else (scope,))]
    direct=('/watch?' in source['url'] or '/playlist?' in source['url'] or (platform=='instagram' and any(x in source['url'] for x in ('/p/','/reel/','/tv/','/stories/'))))
    sql='SELECT DISTINCT i.id FROM items i JOIN active_source_items a ON a.item_id=i.id WHERE a.source_id=? AND NOT EXISTS(SELECT 1 FROM session_items si WHERE si.session_id=? AND si.item_id=i.id)';params=[source['id'],session['id']]
    if not direct and scope!='all':
        sql+=' AND EXISTS(SELECT 1 FROM method_items mi JOIN scan_methods sm ON sm.id=mi.method_id JOIN scan_runs sr ON sr.id=sm.run_id WHERE mi.item_id=i.id AND sr.source_id=? AND sm.method IN ('+','.join('?' for _ in methods)+') AND NOT EXISTS(SELECT 1 FROM excluded_methods e WHERE e.method_id=sm.id)'
        params.extend([source['id'],*methods])
        if scope in ('stories','highlights'):sql+=' AND sm.run_id=?';params.append(session['scan_id'])
        sql+=')'
    sql+=' LIMIT ?';params.append(limit)
    return [r[0] for r in c.execute(sql,params)]

def advance(store,progress=None):
    """A single planner publishes idempotent tasks while other workers keep processing."""
    import fcntl
    with (store.root/'temporary'/'.channel-planning.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        return _advance(store,progress)

def _advance(store,progress=None):
    """Queue known eligible items while discovery continues; never wait for the whole channel."""
    with store.connect() as c:sessions=[dict(r) for r in c.execute("SELECT * FROM channel_sessions WHERE state IN ('discovering','planning','downloading')")]
    last_ping=time.monotonic()
    from .operations import request
    for session in sessions:
        with store.connect() as c:
            source=c.execute('SELECT * FROM sources WHERE id=?',(session['source_id'],)).fetchone()
            scan=c.execute('SELECT state FROM scan_runs WHERE id=?',(session['scan_id'],)).fetchone()
            scan_done=bool(scan and scan[0] in ('enumerated_accessible','partial'))
            ids=candidates(store,c,session,source)
        for iid in ids:
            if progress and time.monotonic()-last_ping>5:progress();last_ping=time.monotonic()
            with store.connect() as c:
                state=c.execute('SELECT state FROM channel_sessions WHERE id=?',(session['id'],)).fetchone()[0]
                if state not in ('discovering','planning','downloading'):break
            operation={'transcript':'transcript','video':'video','mp3':'audio'}[session['mode']]
            jobs=request(store,[iid],[operation],{'audio_format':'mp3','max_height':720,'only_missing':True,'captions_only':source['platform']!='instagram'},session_id=session['id'])
            if not jobs:link_files(store,iid,invalidate=False)
        with store.connect() as c:
            remaining=candidates(store,c,session,source,1)
            pending=c.execute("SELECT 1 FROM session_items si JOIN jobs j ON j.id=si.job_id WHERE si.session_id=? AND j.state IN ('queued','running','retry','paused') LIMIT 1",(session['id'],)).fetchone()
            state='finished' if scan_done and not remaining and not pending else 'downloading' if scan_done else 'discovering'
            c.execute("UPDATE channel_sessions SET state=?,updated=? WHERE id=? AND state IN ('discovering','planning','downloading')",(state,time.time(),session['id']))

def control(store,sid,action):
    if action not in ('pause','resume','cancel'):raise ValueError('Ação inválida')
    from .channel_ui import session_jobs
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        session=c.execute("SELECT * FROM channel_sessions WHERE source_id=? AND state IN ('discovering','planning','downloading','paused')",(sid,)).fetchone()
        if not session:return
        now=time.time();state='cancelled' if action=='cancel' else 'paused' if action=='pause' else 'discovering' if not session['scan_id'] else 'planning'
        c.execute('UPDATE channel_sessions SET state=?,updated=? WHERE id=?',(state,now,session['id']))
        if session['mode']=='transcript':
            if action=='pause':c.execute('INSERT OR IGNORE INTO channel_queue VALUES(?,?)',(sid,now))
            else:c.execute('DELETE FROM channel_queue WHERE source_id=?',(sid,))
        changed=[]
        for job in session_jobs(c,session):
            shared=c.execute("SELECT 1 FROM session_items si JOIN channel_sessions cs ON cs.id=si.session_id WHERE si.job_id=? AND cs.id!=? AND cs.state IN ('discovering','planning','downloading')",(job['id'],session['id'])).fetchone()
            if shared:continue
            jid=job['id'];changed.append(jid)
            if action=='resume':
                if job['state']=='paused':c.execute("UPDATE jobs SET state='queued',control=NULL,attempts=0,available=?,updated=? WHERE id=?",(now,now,jid))
                elif job['state']=='running' and job['control']=='pause':
                    c.execute('UPDATE jobs SET control=NULL,updated=? WHERE id=?',(now,jid))
                    c.execute('INSERT OR REPLACE INTO service_state VALUES(?,?)',('resume_after_pause:'+jid,'1'))
            elif job['state'] in ('queued','retry','running','paused'):
                c.execute('DELETE FROM service_state WHERE key=?',('resume_after_pause:'+jid,))
                if job['state']=='running':c.execute('UPDATE jobs SET control=?,updated=? WHERE id=?',(action,now,jid))
                else:c.execute('UPDATE jobs SET state=?,control=NULL,updated=? WHERE id=?',(state,now,jid))
            store.event(c,jid,'control',action)
        group=c.execute("SELECT value FROM service_state WHERE key='global_pause_jobs'").fetchone()
        if group:c.execute("UPDATE service_state SET value=? WHERE key='global_pause_jobs'",(json.dumps([j for j in json.loads(group[0]) if j not in set(changed)]),))

def link_files(store,iid,invalidate=True):
    """Readable per-channel folders without duplicating media bytes."""
    from .inventory import _LIBRARIES
    if invalidate:_LIBRARIES.pop(str(store.root),None)
    with store.connect() as c:
        item=c.execute('SELECT * FROM items WHERE id=?',(iid,)).fetchone()
        if not item:return
        real=assets(store,c,item)
        sources=c.execute('SELECT s.* FROM sources s JOIN active_source_items a ON a.source_id=s.id WHERE a.item_id=?',(iid,)).fetchall()
    for source in sources:
        base=folder(store,source);base.mkdir(parents=True,exist_ok=True)
        for kind,asset in real.items():
            if kind=='txt':
                from .exports import publish
                publish(store,source['id'],iid);continue
            if kind not in ('video','mp3'):continue
            name=('transcricoes' if kind=='txt' else 'videos' if kind=='video' else 'musicas')
            from .monthly import month,asset_date
            target=base/name/month(store,asset_date(store,iid,kind));target.mkdir(parents=True,exist_ok=True)
            ext='.txt' if kind=='txt' else Path(asset['path']).suffix
            safe=re.sub(r'[^\w .-]','',item['title'] or item['original_id'])[:100].strip() or item['original_id']
            link=target/(safe+' - '+item['original_id']+ext);temp=target/('.'+uuid.uuid4().hex+'.next')
            if not (link.is_symlink() and link.resolve()==Path(asset['path']).resolve()):
                temp.symlink_to(Path(asset['path']));__import__('os').replace(temp,link)
            flat=base/name/link.name
            if flat.is_symlink() and flat.resolve()==Path(asset['path']).resolve():flat.unlink()
            fd=__import__('os').open(target,__import__('os').O_RDONLY)
            try:__import__('os').fsync(fd)
            finally:__import__('os').close(fd)
        manifest={'name':source['name'],'url':source['url'],'source_id':source['id']};path=base/'canal.json'
        try:unchanged=path.is_file() and json.loads(path.read_text())==manifest
        except (OSError,ValueError):unchanged=False
        if not unchanged:atomic_json(path,manifest)

def status(store):
    result=[];asset_cache={};identified=set();ready=set()
    with store.connect() as c:
        for source in c.execute('SELECT * FROM sources ORDER BY rowid').fetchall():
            if '/watch?' in source['url'] or '/playlist?' in source['url'] or (source['platform']=='instagram' and any(x in source['url'] for x in ('/p/','/reel/','/tv/','/stories/'))):continue
            result.append(source_status(store,c,source,asset_cache))
            identified.update(r[0] for r in c.execute('SELECT item_id FROM active_source_items WHERE source_id=?',(source['id'],)))
    with store.connect() as c:paused=c.execute("SELECT value FROM service_state WHERE key='paused'").fetchone()
    from .instagram import connection_status
    ready={iid for iid in identified if 'txt' in asset_cache.get(iid,{})}
    return {'overview':{'identified':len(identified),'ready':len(ready),'partial':any(x['catalog_state']!='complete' for x in result)},'channels':result,'instagram':connection_status(store),'paused':bool(paused and paused[0]=='1')}

def source_status(store,c,source,asset_cache=None):
    items=c.execute('SELECT i.* FROM items i JOIN active_source_items a ON a.item_id=i.id WHERE a.source_id=?',(source['id'],)).fetchall()
    from .storage import metrics
    storage=metrics(store,c,items,source['id'],asset_cache);ready=storage['ready']
    session=c.execute("SELECT * FROM channel_sessions WHERE source_id=? AND mode='transcript' ORDER BY created DESC LIMIT 1",(source['id'],)).fetchone()
    media=c.execute("SELECT mode,state FROM channel_sessions WHERE source_id=? AND mode!='transcript' AND state IN ('discovering','planning','downloading','paused') ORDER BY created DESC LIMIT 1",(source['id'],)).fetchone()
    progress=session_status(store,c,session,asset_cache) if session else None
    latest=c.execute('SELECT id,state,finished FROM scan_runs WHERE source_id=? ORDER BY started DESC LIMIT 1',(source['id'],)).fetchone()
    checking=c.execute("SELECT j.state,j.control FROM jobs j LEFT JOIN scan_methods sm ON sm.id=j.target LEFT JOIN scan_runs sr ON sr.id=sm.run_id WHERE j.state IN ('queued','running','retry') AND (j.target=? OR sr.source_id=?) ORDER BY (j.state='running') DESC LIMIT 1",(source['id'],source['id'])).fetchone()
    methods={r[0] for r in c.execute("SELECT method FROM scan_methods WHERE run_id=? AND state IN ('exhausted','not_applicable')",(latest['id'],))} if latest else set()
    required={'instagram_posts','instagram_reels'} if source['platform']=='instagram' else {'youtube_videos','youtube_streams','youtube_shorts'}
    complete=bool(latest and latest['state']=='enumerated_accessible' and required<=methods)
    running=c.execute("SELECT j.*,i.title FROM jobs j JOIN items i ON i.id=j.target JOIN active_source_items a ON a.item_id=i.id WHERE a.source_id=? AND j.kind IN ('transcribe','transcribe_asr') AND j.state='running' AND j.control IS NULL ORDER BY j.updated DESC LIMIT 1",(source['id'],)).fetchone()
    current=None
    if running and active_transcript(progress):
        row=c.execute('SELECT value FROM service_state WHERE key=?',('progress:'+running['id'],)).fetchone();p=json.loads(row[0]) if row else {}
        done=p.get('completed_audio_seconds') or p.get('downloaded_bytes');total=p.get('duration_seconds') or p.get('total_bytes')
        current={'id':running['target'],'title':running['title'],'stage':p.get('stage',running['kind']),'fraction':min(1,done/total) if done is not None and total else None}
    from .channel_ui import review
    changes=review(c,source['id'])
    queued=c.execute('SELECT added FROM channel_queue WHERE source_id=?',(source['id'],)).fetchone()
    queue_paused=bool(queued or (session and session['state']=='paused'))
    from .exports import directory_status
    return {**dict(source),**storage,**directory_status(store,source),'news':changes,'queue_paused':queue_paused,'queued_at':queued[0] if queued else session['updated'] if queue_paused else None,'current_work':current,'catalog_state':(('counting' if checking['state']=='running' and not checking['control'] else 'waiting') if checking else 'complete' if complete else 'partial' if latest else 'unknown'),'catalog_scanned_at':latest['finished'] if latest else None,'folder':str(folder(store,source)),'identified':len(items),'ready':ready,'remaining':len(items)-ready,'session':progress,'media_session':dict(media) if media else None}

def session_status(store,c,session,asset_cache=None):
    modekey={'transcript':'txt','mp3':'mp3','video':'video'}[session['mode']]
    rows=c.execute('SELECT i.*,j.state AS job_state,j.id AS job_id FROM session_items si JOIN items i ON i.id=si.item_id LEFT JOIN jobs j ON j.id=si.job_id WHERE si.session_id=?',(session['id'],)).fetchall()
    counts={'ready':0,'running':0,'queued':0,'unavailable':0};work=[]
    for row in rows:
        present=modekey in (asset_cache[row['id']] if asset_cache is not None and row['id'] in asset_cache else assets(store,c,row))
        if present:counts['ready']+=1
        elif row['job_state']=='running':counts['running']+=1
        elif row['job_state'] in ('queued','retry','paused'):counts['queued']+=1
        else:counts['unavailable']+=1
        work.append({'id':row['id'],'title':row['title'] or row['original_id'],'state':'ready' if present else 'running' if row['job_state']=='running' else 'queued' if row['job_state'] in ('queued','retry','paused') else 'unavailable'})
    scan=c.execute('SELECT state FROM scan_runs WHERE id=?',(session['scan_id'],)).fetchone()
    scanning=c.execute("SELECT 1 FROM jobs WHERE state='running' AND control IS NULL AND (id=? OR (kind='enumerate' AND target IN (SELECT id FROM scan_methods WHERE run_id=?))) LIMIT 1",(session['scan_job'],session['scan_id'])).fetchone()
    return {**dict(session),'scan_running':bool(scanning),'counts':counts,'total':len(rows),'items':work,'scan_partial':bool(scan and scan[0]=='partial')}

def batches(store):
    with store.connect() as c:
        sessions=c.execute("SELECT cs.*,s.name,s.url FROM channel_sessions cs JOIN sources s ON s.id=cs.source_id WHERE mode IN ('video','mp3') ORDER BY created DESC LIMIT 30").fetchall()
        return {'batches':[session_status(store,c,s) for s in sessions]}


def active_transcript(progress):
    return bool(progress and progress['state'] in ACTIVE)

def refresh_catalog(store,sid):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
        if not source:raise ValueError('Fonte desconhecida')
        current=c.execute("SELECT scan_job FROM channel_sessions WHERE source_id=? AND state IN ('discovering','planning','downloading','paused')",(sid,)).fetchone()
        if current:
            state=c.execute('SELECT state FROM channel_sessions WHERE scan_job=?',(current[0],)).fetchone()[0]
            scan=c.execute('SELECT r.state FROM scan_runs r JOIN channel_sessions cs ON cs.scan_id=r.id WHERE cs.scan_job=?',(current[0],)).fetchone()
            if state!='paused' and (not scan or scan[0]=='running'):return current[0]
        running=c.execute("SELECT r.id FROM scan_runs r WHERE r.source_id=? AND r.state='running' ORDER BY r.started DESC LIMIT 1",(sid,)).fetchone()
        if running:
            stopping=c.execute("SELECT 1 FROM jobs j JOIN scan_methods sm ON sm.id=j.target WHERE sm.run_id=? AND j.state='running' AND j.control='pause'",(running[0],)).fetchone()
            if stopping:raise ValueError('A tentativa anterior está encerrando. Atualize novamente em alguns segundos.')
            paused=c.execute("SELECT j.id FROM jobs j JOIN scan_methods sm ON sm.id=j.target WHERE sm.run_id=? AND j.state='paused'",(running[0],)).fetchall()
            if paused and c.execute('SELECT 1 FROM service_state WHERE key=?',('catalog_run:'+running[0],)).fetchone():
                for job in paused:c.execute("UPDATE jobs SET state='queued',control=NULL,owner=NULL,lease_until=NULL,available=?,updated=? WHERE id=?",(time.time(),time.time(),job[0]))
                return paused[0][0]
            pending=c.execute("SELECT j.id FROM jobs j JOIN scan_methods sm ON sm.id=j.target WHERE sm.run_id=? AND j.state IN ('queued','running','retry') LIMIT 1",(running[0],)).fetchone()
            if pending:return pending[0]
        c.execute("UPDATE sources SET auto_process=0,cadence='manual',next_sync=NULL WHERE id=?",(sid,))
        jid=store.enqueue(c,'catalog_sync' if current else 'sync',sid);c.execute('UPDATE jobs SET priority=75 WHERE id=?',(jid,))
        c.execute('INSERT INTO service_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('catalog_only:'+jid,json.dumps({'scope':'all'})))
        return jid
