"""Observed channel changes and lightweight, truthful control acknowledgement."""
import time
from .inventory import assets

SCHEMA='''
CREATE TABLE IF NOT EXISTS scan_reviews(run_id TEXT PRIMARY KEY REFERENCES scan_runs(id),initial INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS scan_baseline(run_id TEXT REFERENCES scan_runs(id),item_id TEXT,PRIMARY KEY(run_id,item_id));
CREATE INDEX IF NOT EXISTS session_items_job ON session_items(job_id,session_id);
'''

def begin_review(c,rid,sid):
    count=c.execute('SELECT count(*) FROM active_source_items WHERE source_id=?',(sid,)).fetchone()[0]
    previous=c.execute('SELECT 1 FROM scan_runs WHERE source_id=? AND id!=? LIMIT 1',(sid,rid)).fetchone()
    c.execute('INSERT INTO scan_reviews VALUES(?,?)',(rid,int(not count and not previous)))
    c.execute('INSERT INTO scan_baseline SELECT ?,item_id FROM active_source_items WHERE source_id=?',(rid,sid))

def review(c,sid):
    r=c.execute('SELECT r.*,v.initial FROM scan_runs r JOIN scan_reviews v ON v.run_id=r.id WHERE r.source_id=? ORDER BY r.started DESC LIMIT 1',(sid,)).fetchone()
    checked=c.execute("SELECT max(finished) FROM scan_runs WHERE source_id=? AND state IN ('enumerated_accessible','partial')",(sid,)).fetchone()[0]
    if not r:return {'new_count':None,'initial':False,'checked_at':checked,'run_id':None,'partial':True}
    count=c.execute('SELECT count(*) FROM run_items ri WHERE ri.run_id=? AND NOT EXISTS(SELECT 1 FROM scan_baseline b WHERE b.run_id=ri.run_id AND b.item_id=ri.item_id)',(r['id'],)).fetchone()[0]
    return {'new_count':count,'initial':bool(r['initial']),'checked_at':checked,'started_at':r['started'],'run_id':r['id'],'partial':r['state']!='enumerated_accessible'}

def news(store,sid,limit=100,offset=0):
    with store.connect() as c:
        info=review(c,sid)
        rows=c.execute('SELECT i.* FROM items i JOIN run_items ri ON ri.item_id=i.id WHERE ri.run_id=? AND NOT EXISTS(SELECT 1 FROM scan_baseline b WHERE b.run_id=ri.run_id AND b.item_id=ri.item_id) ORDER BY i.rowid DESC LIMIT ? OFFSET ?',(info['run_id'],min(200,max(1,limit)),max(0,offset))).fetchall()
        out=[{'id':r['id'],'title':r['title'] or r['original_id'],'ready':'txt' in assets(store,c,r)} for r in rows]
    return {'items':out,'total':info['new_count'] or 0,'review':info}

def session_jobs(c,s):
    return c.execute("SELECT j.* FROM jobs j WHERE j.id=? OR j.id IN (SELECT job_id FROM session_items WHERE session_id=?) OR (j.kind='enumerate' AND j.target IN (SELECT id FROM scan_methods WHERE run_id=?))",(s['scan_job'],s['id'],s['scan_id'])).fetchall()

def control_state(store,sid):
    with store.connect() as c:
        s=c.execute('SELECT * FROM channel_sessions WHERE source_id=? ORDER BY created DESC LIMIT 1',(sid,)).fetchone()
        queued=c.execute('SELECT added FROM channel_queue WHERE source_id=?',(sid,)).fetchone()
        pending=0
        if s:
            for j in session_jobs(c,s):
                if j['state']!='running' or j['control'] not in ('pause','cancel'):continue
                shared=c.execute("SELECT 1 FROM session_items si JOIN channel_sessions cs ON cs.id=si.session_id WHERE si.job_id=? AND cs.id!=? AND cs.state IN ('discovering','planning','downloading')",(j['id'],s['id'])).fetchone()
                if not shared:pending+=1
        global_pause=c.execute("SELECT value FROM service_state WHERE key='paused'").fetchone()
    return {'source_id':sid,'session_id':s['id'] if s else None,'state':s['state'] if s else None,'scope':s['scope'] if s else None,'mode':s['mode'] if s else None,'queue_paused':bool(queued or (s and s['state']=='paused')),'queued_at':queued[0] if queued else None,'stopping':pending,'global_paused':bool(global_pause and global_pause[0]=='1'),'at':time.time()}


def batch_start(store,ids=None,scopes=None):
    from .channels import start,control
    if ids is None:
        with store.connect() as c:
            ids=[r['id'] for r in c.execute('SELECT * FROM sources') if '/watch?' not in r['url'] and '/playlist?' not in r['url'] and not (r['platform']=='instagram' and any(x in r['url'] for x in ('/p/','/reel/','/tv/','/stories/')))]
    if not isinstance(ids,list) or not ids or len(ids)>100 or any(not isinstance(i,str) for i in ids):raise ValueError('Selecione entre 1 e 100 canais')
    scopes=scopes or {}
    if not isinstance(scopes,dict):raise ValueError('Seleção de conteúdos inválida')
    results=[]
    for sid in dict.fromkeys(ids):
        try:
            with store.connect() as c:
                source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
                session=c.execute('SELECT * FROM channel_sessions WHERE source_id=? ORDER BY created DESC LIMIT 1',(sid,)).fetchone()
            if not source:raise ValueError('Canal desconhecido')
            if session and session['state'] in ('discovering','planning','downloading','paused'):
                if session['mode']!='transcript':raise ValueError('Este canal possui um lote de vídeo ou música em andamento')
                if session['state']=='paused':control(store,sid,'resume')
            else:start(store,sid,scope=scopes.get(sid) or (session['scope'] if session else 'public' if source['platform']=='instagram' else 'all'))
            results.append({'id':sid,'ok':True,'state':control_state(store,sid)})
        except (ValueError,OSError) as error:results.append({'id':sid,'ok':False,'error':str(error)})
    return results
