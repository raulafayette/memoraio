from .catalog import Catalog
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import sqlite3
import time
from urllib.parse import urlsplit, parse_qs
import uuid

SCHEMA = '''
PRAGMA journal_mode=DELETE;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,url TEXT UNIQUE NOT NULL,status TEXT NOT NULL DEFAULT 'pending',last_scan REAL,scan_limit INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY,platform TEXT NOT NULL,original_id TEXT NOT NULL,url TEXT NOT NULL,title TEXT,metadata TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'discovered',blob_hash TEXT,path TEXT,size INTEGER,UNIQUE(platform,original_id));
CREATE TABLE IF NOT EXISTS source_items(source_id TEXT REFERENCES sources(id),item_id TEXT REFERENCES items(id),seen REAL,PRIMARY KEY(source_id,item_id));
CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,kind TEXT NOT NULL,target TEXT NOT NULL,state TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,max_attempts INTEGER NOT NULL DEFAULT 4,available REAL NOT NULL,lease_until REAL,owner TEXT,control TEXT,error TEXT,created REAL NOT NULL,updated REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS active_job ON jobs(kind,target) WHERE state IN ('queued','running','retry','paused');
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT,at REAL NOT NULL,kind TEXT NOT NULL,detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS workers(id TEXT PRIMARY KEY,last_seen REAL NOT NULL,pid INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY,item_id TEXT NOT NULL,at REAL NOT NULL,metadata TEXT NOT NULL);

'''
TERMINAL = {'done','failed','blocked','needs_auth','cancelled'}

class Failure(Exception):
    def __init__(self, message, state='retry'):
        super().__init__(message)
        self.state = state

class Interrupted(Exception):
    pass

def canonical(raw):
    if not isinstance(raw,str) or len(raw)>2048 or any(ord(c)<32 for c in raw):
        raise ValueError('URL inválida')
    p=urlsplit(raw.strip())
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443):
        raise ValueError('Use uma URL HTTPS do YouTube, sem credenciais ou porta especial')
    host=(p.hostname or '').lower()
    if host in ('instagram.com','www.instagram.com'):
        if not re.fullmatch(r'/(?:[A-Za-z0-9_.]{1,30}|(?:p|reel|reels|tv)/[A-Za-z0-9_-]{1,100}|stories/[A-Za-z0-9_.]{1,30}(?:/[0-9]{1,30})?)/?',p.path):raise ValueError('URL Instagram inválida')
        return 'https://www.instagram.com'+p.path.replace('/reels/','/reel/',1).rstrip('/')+'/'
    if host not in ('youtube.com','www.youtube.com','m.youtube.com','youtu.be'):
        raise ValueError('Esta versão aceita apenas YouTube')
    q=parse_qs(p.query)
    video=None
    if host=='youtu.be': video=p.path.strip('/')
    elif p.path=='/watch': video=q.get('v',[''])[0]
    elif p.path.startswith(('/shorts/','/live/','/embed/')): video=p.path.split('/')[2]
    if video is not None:
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}',video): raise ValueError('Identificador de vídeo inválido')
        return 'https://www.youtube.com/watch?v='+video
    if p.path=='/playlist' and re.fullmatch(r'[A-Za-z0-9_-]{10,100}',q.get('list',[''])[0]):
        return 'https://www.youtube.com/playlist?list='+q['list'][0]
    if re.fullmatch(r'/(?:@[\w.\-]{1,100}|channel/UC[A-Za-z0-9_-]{22})(?:/(?:videos|shorts|streams|playlists))?/?',p.path):
        return 'https://www.youtube.com'+p.path.rstrip('/')
    raise ValueError('Use vídeo, playlist, @canal ou /channel/ID do YouTube')

def safe_metadata(info):
    keys=('id','title','description','channel','channel_id','uploader','upload_date','timestamp','duration','thumbnail','webpage_url','availability','live_status','language','instagram_shortcode','instagram_child','instagram_kind','instagram_media_id','instagram_owner_id','instagram_highlight_id','alt_title','uploader_id','channel_url','release_timestamp','release_date','release_timezone','media_type','playlist','playlist_id','playlist_index','tags','categories','chapters','view_count','like_count','comment_count','metadata_collected_at','caption_tracks')
    return {k:info[k] for k in keys if k in info}

class Store(Catalog):
    def __init__(self,root):
        self.root=Path(root).resolve()
        durable_mkdir(self.root)
        for x in ('originals','metadata','temporary','transcripts','generated','indexes','backups'):
            (self.root/x).mkdir(exist_ok=True,mode=0o700)
        sync_directory(self.root)
        self.db=self.root/'catalog.sqlite3'
        with self.connect() as c:
            c.executescript(SCHEMA)
            if c.execute('PRAGMA user_version').fetchone()[0]==0:c.execute('PRAGMA user_version=1')
        self.migrate()
        from .channels import SCHEMA as channel_schema
        from .exports import SCHEMA as export_schema
        from .channel_ui import SCHEMA as ui_schema
        with self.connect() as c:c.executescript(channel_schema+export_schema+ui_schema)
        os.chmod(self.db,0o600)
    def connect(self):
        c=sqlite3.connect(self.db,timeout=5)
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA synchronous=FULL')
        c.execute('PRAGMA fullfsync=ON')
        return c
    def event(self,c,jid,kind,detail):
        c.execute('INSERT INTO events(job_id,at,kind,detail) VALUES(?,?,?,?)',(jid,time.time(),kind,str(detail)[:4000]))
    def enqueue(self,c,kind,target):
        found=c.execute("SELECT id FROM jobs WHERE kind=? AND target=? AND state IN ('queued','running','retry','paused')",(kind,target)).fetchone()
        if found:return found['id']
        jid=uuid.uuid4().hex; now=time.time()
        c.execute('INSERT INTO jobs(id,kind,target,state,available,created,updated) VALUES(?,?,?,?,?,?,?)',(jid,kind,target,'queued',now,now,now))
        self.event(c,jid,'queued',kind)
        return jid
    def add_source(self,url,limit=50):
        url=canonical(url)
        if type(limit)!=int or not 1<=limit<=2000:raise ValueError('Limite deve estar entre 1 e 2000')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT OR IGNORE INTO sources(id,url,scan_limit) VALUES(?,?,?)',(uuid.uuid4().hex,url,limit))
            row=c.execute('SELECT * FROM sources WHERE url=?',(url,)).fetchone()
            c.execute('UPDATE sources SET scan_limit=? WHERE id=?',(limit,row['id']))
            return self.enqueue(c,'discover',row['id'])
    def ingest(self,source_id,entries):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            count=0
            for info in entries:
                oid=info.get('id','')
                if not re.fullmatch(r'[\w-]{11}',oid,flags=re.ASCII):continue
                meta=json.dumps(safe_metadata(info),ensure_ascii=False,sort_keys=True)
                iid='youtube_'+oid
                old=c.execute('SELECT metadata FROM items WHERE id=?',(iid,)).fetchone()
                if old and old['metadata']!=meta:
                    c.execute('INSERT INTO versions VALUES(?,?,?,?)',(uuid.uuid4().hex,iid,time.time(),old['metadata']))
                c.execute('INSERT INTO items(id,platform,original_id,url,title,metadata) VALUES(?,?,?,?,?,?) ON CONFLICT(platform,original_id) DO UPDATE SET title=excluded.title,metadata=excluded.metadata',(iid,'youtube',oid,'https://www.youtube.com/watch?v='+oid,info.get('title',oid),meta))
                c.execute('INSERT INTO source_items VALUES(?,?,?) ON CONFLICT(source_id,item_id) DO UPDATE SET seen=excluded.seen',(source_id,iid,time.time()))
                count+=1
            c.execute("UPDATE sources SET status='sampled',last_scan=? WHERE id=?",(time.time(),source_id))
            return count
    def archive(self,ids):
        if not isinstance(ids,list) or not 1<=len(ids)<=2000:raise ValueError('Selecione entre 1 e 2000 itens')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            result=[]
            for iid in ids:
                row=c.execute('SELECT * FROM items WHERE id=? AND EXISTS(SELECT 1 FROM active_source_items si WHERE si.item_id=items.id)',(iid,)).fetchone()
                if not row:raise ValueError('Item desconhecido')
                if row['status']=='archived':continue
                result.append(self.enqueue(c,'download',iid))
            return result
    def claim(self,owner,lease=45,kinds=None,channel_lane=None):
        now=time.time()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            expired=c.execute("SELECT * FROM jobs WHERE state='running' AND lease_until<?",(now,)).fetchall()
            for r in expired:
                state='cancelled' if r['control']=='cancel' else 'paused' if r['control']=='pause' else 'retry' if r['attempts']<r['max_attempts'] else 'failed'
                c.execute('UPDATE jobs SET state=?,owner=NULL,lease_until=NULL,control=NULL,available=?,updated=? WHERE id=?',(state,now,now,r['id']))
                self.event(c,r['id'],'lease_expired',state)
                if r['kind']=='enumerate':c.execute('UPDATE scan_methods SET state=?,error=? WHERE id=?',(state,'Lease expirou; tarefa recuperada',r['target']))
            paused=c.execute("SELECT value FROM service_state WHERE key='paused'").fetchone()
            if paused and paused[0]=='1':return None
            sql="SELECT * FROM jobs WHERE state IN ('queued','retry') AND available<=?"
            sql+=""" AND (NOT EXISTS(SELECT 1 FROM channel_sessions cs WHERE cs.state IN ('paused','cancelled') AND
                (cs.scan_job=jobs.id OR (jobs.kind='enumerate' AND EXISTS(SELECT 1 FROM scan_methods sm WHERE sm.id=jobs.target AND sm.run_id=cs.scan_id)) OR EXISTS(SELECT 1 FROM session_items si WHERE si.session_id=cs.id AND si.job_id=jobs.id)))
                OR EXISTS(SELECT 1 FROM session_items si JOIN channel_sessions cs ON cs.id=si.session_id WHERE si.job_id=jobs.id AND cs.state IN ('planning','downloading')))"""
            params=[now]
            if kinds:
                sql+=" AND kind IN ("+",".join("?" for _ in kinds)+")";params.extend(kinds)
            cooling=[]
            for cooldown in c.execute("SELECT key,value FROM service_state WHERE key LIKE 'cooldown:%'"):
                if float(cooldown['value'])>now:cooling.append(cooldown['key'].split(':',1)[1])
            if cooling:
                sql+=" AND (kind IN ('embed','export','text_export','organize','oracle') OR (kind='transcribe_asr' AND EXISTS(SELECT 1 FROM audio_assets a WHERE a.item_id=jobs.target)) OR id NOT IN (SELECT id FROM job_platform WHERE platform IN ("+','.join('?' for _ in cooling)+')))'
                params.extend(cooling)
            if channel_lane:
                # Reserve at most one job per channel in this lane, atomically with claiming.
                same_kinds=','.join('?' for _ in kinds)
                sql+=" AND NOT EXISTS(SELECT 1 FROM job_sources_v2 own JOIN job_sources_v2 other ON other.source_id=own.source_id JOIN jobs running ON running.id=other.id WHERE own.id=jobs.id AND running.state='running' AND running.kind IN ("+same_kinds+"))"
                params.extend(kinds)
                sql+=" ORDER BY coalesce((SELECT max(t.at) FROM job_sources_v2 js JOIN channel_turns t ON t.source_id=js.source_id AND t.lane=? WHERE js.id=jobs.id),0),priority DESC,updated,created LIMIT 1"
                params.append(channel_lane)
            else:sql+=" ORDER BY priority DESC,updated,created LIMIT 1"
            row=c.execute(sql,params).fetchone()
            if not row:return None
            c.execute("UPDATE jobs SET state='running',owner=?,lease_until=?,attempts=attempts+1,updated=? WHERE id=?",(owner,now+lease,now,row['id']))
            if channel_lane:
                c.execute('INSERT INTO channel_turns SELECT source_id,?,? FROM job_sources_v2 WHERE id=? ON CONFLICT(source_id,lane) DO UPDATE SET at=excluded.at',(channel_lane,now,row['id']))
            self.event(c,row['id'],'claimed',owner)
            if row['kind']=='discover':c.execute("UPDATE sources SET status='running' WHERE id=?",(row['target'],))
            return dict(c.execute('SELECT * FROM jobs WHERE id=?',(row['id'],)).fetchone())
    def heartbeat(self,jid,owner):
        with self.connect() as c:
            r=c.execute("SELECT control,lease_until FROM jobs WHERE id=? AND owner=? AND state='running'",(jid,owner)).fetchone()
            if not r:raise Interrupted('Lease perdido')
            if r['control']:raise Interrupted(r['control'])
            if r['lease_until']<time.time()+35:
                c.execute('UPDATE jobs SET lease_until=?,updated=? WHERE id=? AND owner=?',(time.time()+45,time.time(),jid,owner))
    def finish(self,job,owner,error=None):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute("SELECT * FROM jobs WHERE id=? AND owner=? AND state='running'",(job['id'],owner)).fetchone()
            if not r:return
            if r['control']:state='paused' if r['control']=='pause' else 'cancelled'
            elif error:
                state=getattr(error,'state','retry')
                if state=='rate_limited':state='retry'
                if state=='retry' and r['attempts']>=r['max_attempts']:state='failed'
            else:state='done'
            delay=min(900,5*2**min(r['attempts'],8))+random.uniform(0,5)
            if getattr(error,'state',None)=='rate_limited':
                delay=min(6*3600,900*2**min(r['attempts'],4))+random.uniform(0,30)
                platform=c.execute('SELECT platform FROM job_platform WHERE id=?',(job['id'],)).fetchone()
                if platform and platform[0]:c.execute("INSERT INTO service_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('cooldown:'+platform[0],str(time.time()+delay)))
            resume=c.execute('SELECT 1 FROM service_state WHERE key=?',('resume_after_pause:'+job['id'],)).fetchone()
            if resume and not r['control'] and isinstance(error,Interrupted):
                state='queued';delay=0
            c.execute('DELETE FROM service_state WHERE key=?',('resume_after_pause:'+job['id'],))
            if state=='deferred':
                state='queued';delay=86400
                c.execute('UPDATE jobs SET attempts=max(0,attempts-1) WHERE id=?',(job['id'],))
            elif state=='queued':
                c.execute('UPDATE jobs SET attempts=max(0,attempts-1) WHERE id=?',(job['id'],));delay=0 if resume else 2
            c.execute('UPDATE jobs SET state=?,error=?,available=?,owner=NULL,lease_until=NULL,control=NULL,updated=? WHERE id=?',(state,str(error)[:4000] if error else None,time.time()+delay,time.time(),job['id']))
            if job['kind']=='download' and state!='done':
                c.execute("UPDATE items SET status=? WHERE id=? AND status!='archived'",(state,job['target']))
            if job['kind'] in ('discover','sync') and state!='done':c.execute('UPDATE sources SET status=? WHERE id=?',(state,job['target']))
            self.event(c,job['id'],state,str(error) if error else 'Etapa concluída')
    def control(self,jid,action):
        if action not in ('pause','resume','cancel'):raise ValueError('Ação inválida')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
            if not r:raise ValueError('Tarefa desconhecida')
            group=c.execute("SELECT value FROM service_state WHERE key='global_pause_jobs'").fetchone()
            if group:c.execute("UPDATE service_state SET value=? WHERE key='global_pause_jobs'",(json.dumps([x for x in json.loads(group[0]) if x!=jid]),))
            if action=='resume' and r['kind']=='enumerate' and c.execute('SELECT 1 FROM excluded_methods WHERE method_id=?',(r['target'],)).fetchone():raise ValueError('Tarefa retirada do escopo: retomada recusada')
            if action=='resume':
                if r['state'] not in ('paused','cancelled','failed','blocked','needs_auth'):raise ValueError('Tarefa não pode ser retomada nesse estado')
                active=c.execute("SELECT id FROM jobs WHERE kind=? AND target=? AND id!=? AND state IN ('queued','retry','running','paused')",(r['kind'],r['target'],jid)).fetchone()
                if active:raise ValueError('Já existe tarefa ativa para este item')
                c.execute("UPDATE jobs SET state='queued',control=NULL,attempts=0,available=?,updated=? WHERE id=?",(time.time(),time.time(),jid))
            elif r['state']=='running':c.execute('UPDATE jobs SET control=?,updated=? WHERE id=?',(action,time.time(),jid))
            elif r['state'] not in TERMINAL:c.execute('UPDATE jobs SET state=?,updated=? WHERE id=?',('paused' if action=='pause' else 'cancelled',time.time(),jid))
            self.event(c,jid,'control',action)
    def worker_ping(self,owner):
        with self.connect() as c:c.execute('INSERT INTO workers VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen',(owner,time.time(),os.getpid()))
    def snapshot(self):
        with self.connect() as c:
            c.execute('BEGIN')
            sources=[dict(x) for x in c.execute('SELECT * FROM sources ORDER BY rowid DESC')]
            items=[dict(x) for x in c.execute('SELECT i.*,EXISTS(SELECT 1 FROM audio_assets a WHERE a.item_id=i.id) AS audio_available,EXISTS(SELECT 1 FROM service_state ss WHERE ss.key=\'mp3:\'||i.id) AS mp3_available,t.quality AS transcript_quality,t.origin AS transcript_origin FROM items i LEFT JOIN transcripts t ON t.item_id=i.id AND t.current=1 WHERE EXISTS(SELECT 1 FROM active_source_items asi WHERE asi.item_id=i.id) ORDER BY i.rowid DESC LIMIT 500')]
            jobs=[dict(x) for x in c.execute("SELECT * FROM jobs ORDER BY CASE WHEN state='running' THEN 0 WHEN state IN ('queued','retry','paused') THEN 1 ELSE 2 END,priority DESC,created DESC LIMIT 200")]
            for job in jobs:
                progress=c.execute('SELECT value FROM service_state WHERE key=?',('progress:'+job['id'],)).fetchone()
                job['progress']=json.loads(progress[0]) if progress else None
            events=[dict(x) for x in c.execute('SELECT * FROM events ORDER BY id DESC LIMIT 50')]
            worker_seen=c.execute('SELECT max(last_seen) FROM workers').fetchone()[0]
            worker_health={}
            try:
                service_health=json.loads((self.root/'service-health.json').read_text())
                for lane,pid in service_health.get('children',{}).items():
                    if lane=='web':continue
                    seen=c.execute('SELECT max(last_seen) FROM workers WHERE pid=?',(pid,)).fetchone()[0]
                    worker_health[lane]={'online':bool(seen and time.time()-seen<20),'age_seconds':round(time.time()-seen,1) if seen else None}
            except (OSError,ValueError,TypeError):pass
            palaces=[dict(x) for x in c.execute('SELECT * FROM palaces')]
            transcript_count=c.execute('SELECT count(*) FROM transcripts WHERE current=1').fetchone()[0]
            audit=self.audit(c)
            stats=dict(c.execute("SELECT count(*) AS items,coalesce(sum(status='archived'),0) AS archived,coalesce(sum(size),0) AS bytes FROM items i WHERE EXISTS(SELECT 1 FROM active_source_items si WHERE si.item_id=i.id)").fetchone())
            stats['bytes']=c.execute("SELECT coalesce(sum(size),0) FROM (SELECT hash,max(size) AS size FROM (SELECT blob_hash AS hash,size FROM items i WHERE blob_hash IS NOT NULL AND EXISTS(SELECT 1 FROM active_source_items si WHERE si.item_id=i.id) UNION ALL SELECT a.sha256,a.size FROM audio_assets a WHERE EXISTS(SELECT 1 FROM active_source_items si WHERE si.item_id=a.item_id)) GROUP BY hash)").fetchone()[0]
            stats['quarantined_records']=c.execute('SELECT count(*) FROM items i WHERE EXISTS(SELECT 1 FROM excluded_source_items e WHERE e.item_id=i.id) AND NOT EXISTS(SELECT 1 FROM active_source_items si WHERE si.item_id=i.id)').fetchone()[0]
        with self.connect() as c:paused=c.execute("SELECT value FROM service_state WHERE key='paused'").fetchone()
        stats['transcripts']=transcript_count
        from .oracles import list_oracles
        return dict(worker_health=worker_health,oracles=list_oracles(self),service_mode=os.environ.get('MEMORIA_SERVICE')=='1',paused=bool(paused and paused[0]=='1'),palaces=palaces,audit=audit,sources=sources,items=items,jobs=jobs,events=events,stats=stats,free_bytes=shutil.disk_usage(self.root).free,worker_online=bool(worker_seen and time.time()-worker_seen<15))
    def backup(self):
        target=self.root/'backups'/('catalog-'+str(time.time_ns())+'.sqlite3')
        with self.connect() as c,sqlite3.connect(target) as dest:
            c.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise Failure('Backup inválido','failed')
        os.chmod(target,0o600)
        with target.open('rb') as f:sync_file(f.fileno())
        sync_directory(target.parent)
        return target

def hash_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def sync_file(fd):
    os.fsync(fd)
    if __import__('sys').platform=='darwin':
        import fcntl
        import errno
        try:fcntl.fcntl(fd,getattr(fcntl,'F_FULLFSYNC',51))
        except OSError as error:
            if error.errno not in (errno.EINVAL,errno.ENOTSUP):raise

def sync_directory(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def durable_mkdir(path):
    path=Path(path);missing=[p for p in (path,*path.parents) if not p.exists()]
    path.mkdir(parents=True,exist_ok=True,mode=0o700)
    for p in reversed(missing):sync_directory(p.parent)

def atomic_text(path,text):
    path=Path(path);tmp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('x',encoding='utf-8') as f:
            os.chmod(tmp,0o600);f.write(text);f.flush();sync_file(f.fileno())
        os.replace(tmp,path);sync_directory(path.parent)
    finally:tmp.unlink(missing_ok=True)

def atomic_json(path,data):
    atomic_text(path,json.dumps(data,ensure_ascii=False,indent=2))
