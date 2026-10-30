"""Versioned catalog, schedules, coverage and source-to-palace relationships."""
import calendar
from datetime import datetime, timedelta, timezone
import json
import re
import time
import uuid

CADENCES = {'manual','daily','weekly','fortnightly','monthly'}

def next_due(stamp,cadence):
    if cadence=='manual':return None
    dt=datetime.fromtimestamp(stamp,timezone.utc)
    if cadence=='monthly':
        year=dt.year+(dt.month==12);month=dt.month%12+1
        return dt.replace(year=year,month=month,day=min(dt.day,calendar.monthrange(year,month)[1])).timestamp()
    return (dt+timedelta(days={'daily':1,'weekly':7,'fortnightly':14}[cadence])).timestamp()

class Catalog:
    def migrate(self):
        with self.connect() as c:
            version=c.execute('PRAGMA user_version').fetchone()[0]
        if version>=4:
            with self.connect() as c:self.ensure_indexes(c)
            return
        if version>=1:self.backup()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            additions={'platform':"TEXT NOT NULL DEFAULT 'youtube'",'name':"TEXT NOT NULL DEFAULT ''",'cadence':"TEXT NOT NULL DEFAULT 'manual'",'next_sync':'REAL','last_success':'REAL','auto_process':'INTEGER NOT NULL DEFAULT 0','inventory_state':"TEXT NOT NULL DEFAULT 'unknown'"}
            columns={x['name'] for x in c.execute('PRAGMA table_info(sources)')}
            for name,definition in additions.items():
                if name not in columns:c.execute(f'ALTER TABLE sources ADD COLUMN {name} {definition}')
            if 'priority' not in {x['name'] for x in c.execute('PRAGMA table_info(jobs)')}:
                c.execute('ALTER TABLE jobs ADD COLUMN priority INTEGER NOT NULL DEFAULT 0')
            statements=[
              "CREATE TABLE IF NOT EXISTS excluded_methods(method_id TEXT PRIMARY KEY REFERENCES scan_methods(id),reason TEXT,at REAL)",
              "CREATE TABLE IF NOT EXISTS excluded_source_items(source_id TEXT,item_id TEXT,reason TEXT,at REAL,PRIMARY KEY(source_id,item_id))",
              "CREATE TABLE IF NOT EXISTS scan_runs(id TEXT PRIMARY KEY,source_id TEXT REFERENCES sources(id),started REAL NOT NULL,finished REAL,state TEXT NOT NULL,summary TEXT)",
              "CREATE TABLE IF NOT EXISTS scan_methods(id TEXT PRIMARY KEY,run_id TEXT REFERENCES scan_runs(id),method TEXT,url TEXT,state TEXT NOT NULL DEFAULT 'queued',count INTEGER NOT NULL DEFAULT 0,error TEXT,UNIQUE(run_id,url))",
              "CREATE TABLE IF NOT EXISTS method_items(method_id TEXT REFERENCES scan_methods(id),item_id TEXT REFERENCES items(id),PRIMARY KEY(method_id,item_id))",
              "CREATE TABLE IF NOT EXISTS run_items(run_id TEXT REFERENCES scan_runs(id),item_id TEXT REFERENCES items(id),PRIMARY KEY(run_id,item_id))",
              "CREATE TABLE IF NOT EXISTS item_attempts(id INTEGER PRIMARY KEY,item_id TEXT,at REAL,method TEXT,state TEXT,detail TEXT)",
              "CREATE TABLE IF NOT EXISTS transcripts(id TEXT PRIMARY KEY,item_id TEXT REFERENCES items(id),created REAL,origin TEXT,language TEXT,model TEXT,path TEXT,sha256 TEXT,quality TEXT,report TEXT,current INTEGER NOT NULL DEFAULT 1)",
              "CREATE UNIQUE INDEX IF NOT EXISTS current_transcript ON transcripts(item_id) WHERE current=1",
              "CREATE TABLE IF NOT EXISTS segments(id INTEGER PRIMARY KEY,transcript_id TEXT REFERENCES transcripts(id),item_id TEXT,start REAL,end REAL,text TEXT)",
              "CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(text,content='segments',content_rowid='id',tokenize='unicode61 remove_diacritics 2')",
              "CREATE TABLE IF NOT EXISTS audio_assets(item_id TEXT PRIMARY KEY,path TEXT,sha256 TEXT,duration REAL,size INTEGER)",
              "CREATE TABLE IF NOT EXISTS palaces(id TEXT PRIMARY KEY,name TEXT,description TEXT)",
              "CREATE TABLE IF NOT EXISTS palace_sources(palace_id TEXT REFERENCES palaces(id),source_id TEXT REFERENCES sources(id),PRIMARY KEY(palace_id,source_id))",
              "CREATE TABLE IF NOT EXISTS service_state(key TEXT PRIMARY KEY,value TEXT)",
              "CREATE TABLE IF NOT EXISTS vectors(segment_id INTEGER PRIMARY KEY REFERENCES segments(id),model TEXT,vector BLOB)",
            ]
            for statement in statements:c.execute(statement)
            self.ensure_indexes(c)
            c.execute('PRAGMA user_version=4')
    def ensure_indexes(self,c):
        for sql in ['CREATE INDEX IF NOT EXISTS events_by_job ON events(job_id,kind,at)','CREATE INDEX IF NOT EXISTS jobs_history ON jobs(target,kind,created DESC)','CREATE INDEX IF NOT EXISTS source_items_reverse ON source_items(item_id,source_id)','CREATE INDEX IF NOT EXISTS segments_by_transcript ON segments(transcript_id)','CREATE INDEX IF NOT EXISTS vectors_by_model ON vectors(model)','CREATE INDEX IF NOT EXISTS method_items_by_item ON method_items(item_id,method_id)']:c.execute(sql)
        c.execute('CREATE VIEW IF NOT EXISTS active_source_items AS SELECT si.* FROM source_items si WHERE NOT EXISTS(SELECT 1 FROM excluded_source_items e WHERE e.source_id=si.source_id AND e.item_id=si.item_id)')
        c.execute('CREATE VIEW IF NOT EXISTS job_platform AS SELECT j.id,coalesce(i.platform,src.platform,ss.platform) AS platform FROM jobs j LEFT JOIN items i ON i.id=j.target LEFT JOIN sources src ON src.id=j.target LEFT JOIN scan_methods sm ON sm.id=j.target LEFT JOIN scan_runs r ON r.id=sm.run_id LEFT JOIN sources ss ON ss.id=r.source_id')
        c.execute('CREATE TABLE IF NOT EXISTS channel_turns(source_id TEXT,lane TEXT,at REAL,PRIMARY KEY(source_id,lane))')
        c.execute("""CREATE VIEW IF NOT EXISTS job_sources_v2 AS
            SELECT j.id,a.source_id FROM jobs j JOIN active_source_items a ON a.item_id=j.target WHERE j.kind IN ('download','audio','transcribe','transcribe_asr','export','formats')
            UNION SELECT j.id,s.id FROM jobs j JOIN sources s ON s.id=j.target WHERE j.kind IN ('sync','catalog_sync','discover')
            UNION SELECT j.id,r.source_id FROM jobs j JOIN scan_methods sm ON sm.id=j.target JOIN scan_runs r ON r.id=sm.run_id WHERE j.kind='enumerate'
            UNION SELECT j.id,a.source_id FROM jobs j JOIN transcripts t ON t.id=j.target JOIN active_source_items a ON a.item_id=t.item_id WHERE j.kind='embed'
            UNION SELECT j.id,substr(j.target,1,instr(j.target,':')-1) FROM jobs j WHERE j.kind='text_export' AND instr(j.target,':')>0""")
        c.execute('CREATE VIEW IF NOT EXISTS job_sources AS SELECT * FROM job_sources_v2')
    def register_source(self,url,name=None,cadence='manual',auto_process=False,queue_paused=False):
        from .core import canonical
        if cadence not in CADENCES:raise ValueError('Frequência inválida')
        url=canonical(url)
        if 'youtube.com/@' in url or '/channel/' in url:url=re.sub(r'/(videos|shorts|streams|playlists)$','',url)
        platform='instagram' if 'instagram.com/' in url else 'youtube'
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            created=c.execute('INSERT OR IGNORE INTO sources(id,url,scan_limit,platform,name,cadence,next_sync,auto_process) VALUES(?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,url,2000,platform,name or url,cadence,time.time() if cadence!='manual' else None,int(auto_process))).rowcount
            sid=c.execute('SELECT id FROM sources WHERE url=?',(url,)).fetchone()[0]
            if created and queue_paused:c.execute('INSERT INTO channel_queue VALUES(?,?)',(sid,time.time()))
            return sid
    def bootstrap_official(self):
        seed=self.root/'bootstrap-sources.json'
        official=json.loads(seed.read_text()) if seed.exists() else []
        ids=[self.register_source(url,name) for name,url in official]
        if not ids:return []
        return ids
    def schedule_source(self,sid,cadence):
        if cadence not in CADENCES:raise ValueError('Frequência inválida')
        with self.connect() as c:
            if not c.execute('SELECT id FROM sources WHERE id=?',(sid,)).fetchone():raise ValueError('Fonte desconhecida')
            c.execute('UPDATE sources SET cadence=?,next_sync=? WHERE id=?',(cadence,next_due(time.time(),cadence),sid))
    def sync_now(self,sid):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT id FROM sources WHERE id=?',(sid,)).fetchone():raise ValueError('Fonte desconhecida')
            jid=self.enqueue(c,'sync',sid)
            c.execute('UPDATE jobs SET priority=100 WHERE id=?',(jid,))
            return jid
    def tick(self,now=None):
        now=now or time.time();queued=[]
        with self.connect() as c:
            paused=c.execute("SELECT value FROM service_state WHERE key='paused' OR key='manual_mode' ORDER BY value DESC LIMIT 1").fetchone()
        if paused and paused[0]=='1':return []
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            for source in c.execute("SELECT * FROM sources WHERE cadence!='manual' AND next_sync<=?",(now,)).fetchall():
                jid=self.enqueue(c,'sync',source['id']);queued.append(jid)
                c.execute('UPDATE jobs SET priority=100 WHERE id=?',(jid,))
                c.execute('UPDATE sources SET next_sync=? WHERE id=?',(next_due(now,source['cadence']),source['id']))
            c.execute("INSERT INTO service_state VALUES('scheduler_seen',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(now),))
        return queued
    def add_method(self,c,run_id,method,url):
        if method=='youtube_uploads':
            row=c.execute("SELECT ss.value FROM scan_runs r JOIN service_state ss ON ss.key='channel:'||r.source_id WHERE r.id=?",(run_id,)).fetchone()
            if not row or url!='https://www.youtube.com/playlist?list=UU'+row[0][2:]:raise ValueError('Uploads fora do canal original da fonte: enumeração recusada')
        existing=c.execute('SELECT id FROM scan_methods WHERE run_id=? AND url=?',(run_id,url)).fetchone()
        if existing:return existing[0]
        mid=uuid.uuid4().hex
        c.execute('INSERT INTO scan_methods(id,run_id,method,url) VALUES(?,?,?,?)',(mid,run_id,method,url))
        jid=self.enqueue(c,'enumerate',mid);c.execute('UPDATE jobs SET priority=90 WHERE id=?',(jid,))
        return mid
    def observe(self,run_id,info,platform='youtube'):
        oid=str(info.get('id',''))
        if platform=='youtube' and not re.fullmatch(r'[A-Za-z0-9_-]{11}',oid):return None
        if platform=='instagram' and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',oid):return None
        from .core import safe_metadata
        meta=safe_metadata(info);iid=platform+'_'+oid
        url='https://www.youtube.com/watch?v='+oid if platform=='youtube' else info.get('webpage_url')
        if platform=='instagram':
            from .core import canonical
            try:url=canonical(url)
            except (ValueError,TypeError):return None
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            run=c.execute('SELECT source_id FROM scan_runs WHERE id=?',(run_id,)).fetchone()
            if not run:raise ValueError('Execução desconhecida')
            old=c.execute('SELECT metadata FROM items WHERE id=?',(iid,)).fetchone()
            if old:
                previous=json.loads(old['metadata']);merged={**previous,**{k:v for k,v in meta.items() if v is not None}}
                payload=json.dumps(merged,ensure_ascii=False,sort_keys=True)
                if json.loads(old['metadata'])!=merged:c.execute('INSERT INTO versions VALUES(?,?,?,?)',(uuid.uuid4().hex,iid,time.time(),old['metadata']))
            else:payload=json.dumps(meta,ensure_ascii=False,sort_keys=True)
            c.execute('INSERT INTO items(id,platform,original_id,url,title,metadata) VALUES(?,?,?,?,?,?) ON CONFLICT(platform,original_id) DO UPDATE SET title=coalesce(excluded.title,items.title),metadata=excluded.metadata',(iid,platform,oid,url,info.get('title'),payload))
            c.execute('INSERT OR IGNORE INTO run_items VALUES(?,?)',(run_id,iid))
            c.execute('INSERT INTO source_items VALUES(?,?,?) ON CONFLICT(source_id,item_id) DO UPDATE SET seen=excluded.seen',(run['source_id'],iid,time.time()))
            auto=c.execute('SELECT auto_process FROM sources WHERE id=?',(run['source_id'],)).fetchone()[0]
            current=c.execute('SELECT id FROM transcripts WHERE item_id=? AND current=1',(iid,)).fetchone()
            # A monthly scan doesn't turn an authentication restriction into an endless loop.
            blocked=c.execute("SELECT id FROM jobs WHERE kind='transcribe' AND target=? AND state IN ('blocked','needs_auth')",(iid,)).fetchone()
            if auto and not current and not blocked:
                jid=self.enqueue(c,'transcribe',iid);c.execute('UPDATE jobs SET priority=10 WHERE id=?',(jid,))
        return iid
    def audit(self,connection=None):
        import contextlib
        with (self.connect() if connection is None else contextlib.nullcontext(connection)) as c:
            if connection is None:c.execute('BEGIN')
            result=[]
            for source in c.execute('SELECT * FROM sources ORDER BY rowid'):
                row=dict(source)
                counts=dict(c.execute('''SELECT count(*) AS identified,
                  sum(t.id IS NOT NULL) AS transcribed,
                  sum(t.origin='local_asr') AS ai,
                  sum(t.origin IN ('manual_caption','automatic_caption')) AS captions,
                  sum(t.quality='structural_pass') AS structural_pass,
                  sum(t.quality='human_verified') AS human_verified,
                  sum(t.quality='needs_review') AS review
                  FROM active_source_items si JOIN items i ON i.id=si.item_id
                  LEFT JOIN transcripts t ON t.item_id=i.id AND t.current=1 WHERE si.source_id=?''',(source['id'],)).fetchone())
                counts={k:v or 0 for k,v in counts.items()}
                failures=dict(c.execute('''SELECT sum(j.state='failed') AS failed,sum(j.state IN ('blocked','needs_auth')) AS inaccessible
                  FROM active_source_items si JOIN jobs j ON j.target=si.item_id AND j.kind IN ('transcribe','transcribe_asr')
                  WHERE si.source_id=? AND NOT EXISTS(SELECT 1 FROM transcripts t WHERE t.item_id=j.target AND t.current=1) AND j.created=(SELECT max(j2.created) FROM jobs j2 WHERE j2.kind IN ('transcribe','transcribe_asr') AND j2.target=j.target)''',(source['id'],)).fetchone())
                counts.update({k:v or 0 for k,v in failures.items()});counts['pending']=max(0,counts['identified']-counts['transcribed']-counts['failed']-counts['inaccessible'])
                counts['coverage_available']=round(100*counts['transcribed']/counts['identified'],2) if counts['identified'] else None
                counts['coverage_human_verified']=round(100*counts['human_verified']/counts['identified'],2) if counts['identified'] else None
                row.update(counts)
                row['quarantined_associations']=c.execute('SELECT count(*) FROM excluded_source_items WHERE source_id=?',(source['id'],)).fetchone()[0]
                row['runs']=[dict(x) for x in c.execute('SELECT * FROM scan_runs WHERE source_id=? ORDER BY started DESC LIMIT 5',(source['id'],))]
                row['errors']=[dict(x) for x in c.execute('SELECT sm.* FROM scan_methods sm JOIN scan_runs r ON r.id=sm.run_id WHERE r.source_id=? AND sm.error IS NOT NULL ORDER BY r.started DESC LIMIT 10',(source['id'],))]
                row['errors'].extend(dict(x) for x in c.execute("SELECT kind AS method,error FROM jobs WHERE target=? AND kind IN ('sync','discover') AND error IS NOT NULL ORDER BY updated DESC LIMIT 5",(source['id'],)))
                result.append(row)
            return result
    def reprocess(self,ids,force_asr=False):
        if not isinstance(ids,list) or not 1<=len(ids)<=2000:raise ValueError('Selecione entre1 e2000 itens')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE');result=[]
            for iid in ids:
                if not c.execute('SELECT id FROM items WHERE id=? AND EXISTS(SELECT 1 FROM active_source_items si WHERE si.item_id=items.id)',(iid,)).fetchone():raise ValueError('Item desconhecido')
                result.append(self.enqueue(c,'transcribe_asr' if force_asr else 'transcribe',iid))
            return result
    def attempt(self,iid,method,state,detail):
        with self.connect() as c:c.execute('INSERT INTO item_attempts(item_id,at,method,state,detail) VALUES(?,?,?,?,?)',(iid,time.time(),method,state,str(detail)[:4000]))
    def palace(self,name,description,source_ids):
        if not isinstance(name,str) or not name.strip() or len(name)>200:raise ValueError('Nome inválido')
        if not isinstance(source_ids,list):raise ValueError('Fontes inválidas')
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE');pid=uuid.uuid4().hex;c.execute('INSERT INTO palaces VALUES(?,?,?)',(pid,name.strip(),str(description)[:4000]))
            for sid in source_ids:c.execute('INSERT INTO palace_sources VALUES(?,?)',(pid,sid))
        return pid
    def search(self,query,palace_id=None,source_id=None):
        words=re.findall(r'\w+',query,flags=re.UNICODE)[:20]
        if not words:return []
        match=' AND '.join('"'+x+'"' for x in words)
        sql='''SELECT DISTINCT s.id,s.item_id,s.start,s.end,s.text,i.title,i.url,json_extract(i.metadata,'$.channel') AS channel,t.quality,t.origin
          FROM transcript_fts f JOIN segments s ON s.id=f.rowid JOIN items i ON i.id=s.item_id
          JOIN transcripts t ON t.id=s.transcript_id WHERE transcript_fts MATCH ? AND t.current=1 AND EXISTS(SELECT 1 FROM active_source_items asi WHERE asi.item_id=i.id)'''
        params=[match]
        if palace_id:
            sql+=' AND EXISTS(SELECT 1 FROM active_source_items si JOIN palace_sources ps ON ps.source_id=si.source_id WHERE si.item_id=i.id AND ps.palace_id=?)';params.append(palace_id)
        if source_id:sql+=' AND EXISTS(SELECT 1 FROM active_source_items si WHERE si.item_id=i.id AND si.source_id=?)';params.append(source_id)
        sql+=' LIMIT 50'
        with self.connect() as c:return [dict(x) for x in c.execute(sql,params)]

    def repair_scope(self):
        reason='Correção0.2: uploads de autores encontrados em playlists não pertencem automaticamente à fonte'
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            bad=[]
            for m in c.execute("SELECT sm.id,sm.url,r.source_id,ss.value AS channel FROM scan_methods sm JOIN scan_runs r ON r.id=sm.run_id LEFT JOIN service_state ss ON ss.key='channel:'||r.source_id WHERE sm.method='youtube_uploads'").fetchall():
                if not m['channel']:raise ValueError('Confirme o ID permanente de cada canal antes da correção')
                if m['url']!='https://www.youtube.com/playlist?list=UU'+m['channel'][2:]:bad.append(m['id'])
            for mid in bad:
                c.execute('INSERT OR IGNORE INTO excluded_methods VALUES(?,?,?)',(mid,reason,time.time()))
                c.execute("UPDATE scan_methods SET error=? WHERE id=?",(reason,mid))
                for job in c.execute("SELECT id FROM jobs WHERE target=? AND kind='enumerate' AND state IN ('queued','running','retry','paused')",(mid,)).fetchall():
                    c.execute("UPDATE jobs SET state='cancelled',control=NULL,owner=NULL,lease_until=NULL,error=?,updated=? WHERE id=?",(reason,time.time(),job['id']))
                    self.event(c,job['id'],'scope_quarantine',reason)
            c.execute('''INSERT OR IGNORE INTO excluded_source_items
              SELECT DISTINCT r.source_id,mi.item_id,?,? FROM method_items mi
              JOIN excluded_methods ex ON ex.method_id=mi.method_id JOIN scan_methods sm ON sm.id=mi.method_id JOIN scan_runs r ON r.id=sm.run_id
              WHERE NOT EXISTS(SELECT 1 FROM method_items good JOIN scan_methods gm ON gm.id=good.method_id JOIN scan_runs gr ON gr.id=gm.run_id
                WHERE good.item_id=mi.item_id AND gr.source_id=r.source_id AND NOT EXISTS(SELECT 1 FROM excluded_methods ge WHERE ge.method_id=gm.id))''',(reason,time.time()))
            removed_jobs=0
            rows=c.execute('''SELECT j.id FROM jobs j WHERE j.kind IN ('transcribe','transcribe_asr','download') AND j.state IN ('queued','retry','paused','running')
              AND EXISTS(SELECT 1 FROM excluded_source_items e WHERE e.item_id=j.target)
              AND NOT EXISTS(SELECT 1 FROM active_source_items si WHERE si.item_id=j.target)''').fetchall()
            for row in rows:
                c.execute("UPDATE jobs SET state='cancelled',control=NULL,owner=NULL,lease_until=NULL,error=?,updated=? WHERE id=?",(reason,time.time(),row['id']))
                self.event(c,row['id'],'scope_quarantine',reason);removed_jobs+=1
            quarantined=c.execute('SELECT count(*) FROM excluded_source_items').fetchone()[0]
            affected_transcripts=c.execute('SELECT count(*) FROM transcripts t WHERE current=1 AND NOT EXISTS(SELECT 1 FROM active_source_items si WHERE si.item_id=t.item_id)').fetchone()[0]
        return {'excluded_methods':len(bad),'quarantined_associations':quarantined,'cancelled_processing_jobs':removed_jobs,'transcripts_outside_scope':affected_transcripts,'data_deleted':False}
