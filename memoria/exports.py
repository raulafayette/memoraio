"""User-selected TXT folders and durable, traceable standalone exports."""
import json
from pathlib import Path
import re
import time
import uuid
from .core import atomic_text,hash_file,durable_mkdir,sync_directory

SCHEMA='''CREATE TABLE IF NOT EXISTS text_exports(source_id TEXT,item_id TEXT,transcript_id TEXT,path TEXT,sha256 TEXT,created REAL,current INTEGER NOT NULL DEFAULT 1,PRIMARY KEY(source_id,item_id,path));CREATE INDEX IF NOT EXISTS text_exports_item ON text_exports(source_id,item_id,current);'''

def default_directory(store):
    from .preferences import read
    chosen=read(store).get('transcript_directory','')
    if chosen:return Path(chosen)
    root=store.root/'channels';durable_mkdir(root);return root

def source_directory(store,source):
    with store.connect() as c:r=c.execute('SELECT value FROM service_state WHERE key=?',('text_directory:'+source['id'],)).fetchone()
    if r:return Path(json.loads(r[0]))
    slug=re.sub(r'[^\w .-]','',source['name'] or 'Canal').strip() or 'Canal'
    while len(slug.encode())>180:slug=slug[:-1]
    return default_directory(store)/(slug+' - '+source['id'][:8])/'transcricoes'

def directory_status(store,source):
    with store.connect() as c:r=c.execute('SELECT 1 FROM service_state WHERE key=?',('text_directory:'+source['id'],)).fetchone()
    path=source_directory(store,source);base=path if r else default_directory(store)
    return {'transcript_directory':str(path),'directory_custom':bool(r),'directory_available':base.is_dir()}

def ensure_directory(store,source):
    directory=source_directory(store,source)
    if not directory_status(store,source)['directory_available']:raise ValueError('A pasta configurada não está disponível. Escolha outra pasta nos Ajustes.')
    durable_mkdir(directory)
    return directory

def queue_existing(store,sid=None):
    with store.connect() as c:
        sql='SELECT DISTINCT a.source_id,t.item_id FROM transcripts t JOIN active_source_items a ON a.item_id=t.item_id WHERE t.current=1'
        params=[]
        if sid:sql+=' AND a.source_id=?';params.append(sid)
        rows=c.execute(sql,params).fetchall()
        for row in rows:
            jid=store.enqueue(c,'text_export',row['source_id']+':'+row['item_id']);c.execute('UPDATE jobs SET priority=82 WHERE id=?',(jid,))
    return len(rows)

def set_source_directory(store,sid,path):
    from .preferences import validate_directory
    if not isinstance(path,str):raise ValueError('Pasta inválida')
    with store.connect() as c:source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
    if not source:raise ValueError('Canal desconhecido')
    if path:
        chosen=validate_directory(store,path)
        with store.connect() as c:c.execute('INSERT INTO service_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('text_directory:'+sid,json.dumps(chosen)))
    else:
        with store.connect() as c:c.execute('DELETE FROM service_state WHERE key=?',('text_directory:'+sid,))
    ensure_directory(store,source);queue_existing(store,sid)
    return directory_status(store,source)

def register_channel(store,url,name=None):
    sid=store.register_source(url,name,queue_paused=True)
    with store.connect() as c:source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
    ensure_directory(store,source)
    return sid

def publish(store,sid,iid):
    from .library import enrich,rich_text
    with store.connect() as c:
        source=c.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone();item=c.execute('SELECT * FROM items WHERE id=?',(iid,)).fetchone();t=c.execute('SELECT * FROM transcripts WHERE item_id=? AND current=1',(iid,)).fetchone()
        associated=c.execute('SELECT 1 FROM active_source_items WHERE source_id=? AND item_id=?',(sid,iid)).fetchone()
    if not source or not item or not t or not associated:return
    original=(store.root/t['path']).resolve()
    if not original.is_relative_to((store.root/'transcripts').resolve()) or hash_file(original)!=t['sha256']:raise ValueError('O TXT não pode ser exportado antes da conferência de integridade')
    with store.connect() as c:copies=c.execute('SELECT path,sha256 FROM text_exports WHERE source_id=? AND item_id=? AND transcript_id=? ORDER BY current DESC,created DESC',(sid,iid,t['id'])).fetchall()
    text=None
    for copy in copies:
        try:
            previous=Path(copy['path'])
            if previous.is_file() and hash_file(previous)==copy['sha256']:
                text=previous.read_text();break
        except OSError:pass
    if text is None:
        doc=enrich(store,dict(item),json.loads(original.read_text()));text=rich_text(doc)
    base=ensure_directory(store,source)
    from .monthly import month
    directory=base/month(store,t['created']);durable_mkdir(directory)
    title=re.sub(r'[^\w .-]','',item['title'] or item['original_id']).strip() or item['original_id'];suffix=' - '+item['original_id']+'.txt'
    while len((title+suffix).encode())>235:title=title[:-1]
    target=directory/(title+suffix)
    with store.connect() as c:known=c.execute('SELECT sha256 FROM text_exports WHERE source_id=? AND item_id=? AND path=?',(sid,iid,str(target))).fetchone()
    if target.exists() and not target.is_symlink():
        actual=hash_file(target)
        expected=__import__('hashlib').sha256(text.encode()).hexdigest()
        if actual!=expected and (not known or actual!=known[0]):target=directory/(title+' - '+item['original_id']+'-'+uuid.uuid4().hex[:8]+'.txt')
    expected=__import__('hashlib').sha256(text.encode()).hexdigest()
    if not target.is_file() or target.is_symlink() or hash_file(target)!=expected:atomic_text(target,text)
    digest=hash_file(target)
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE');c.execute('UPDATE text_exports SET current=0 WHERE source_id=? AND item_id=?',(sid,iid))
        c.execute('INSERT INTO text_exports VALUES(?,?,?,?,?,?,1) ON CONFLICT(source_id,item_id,path) DO UPDATE SET transcript_id=excluded.transcript_id,sha256=excluded.sha256,created=excluded.created,current=1',(sid,iid,t['id'],str(target),digest,time.time()))
    # Remove only byte-identical managed flat copies after the monthly copy is durable.
    with store.connect() as c:old=c.execute('SELECT path,sha256 FROM text_exports WHERE source_id=? AND item_id=? AND path!=?',(sid,iid,str(target))).fetchall()
    for record in old:
        flat=Path(record['path'])
        try:
            if flat.parent==base and flat.is_file() and not flat.is_symlink() and record['sha256']==digest and hash_file(flat)==digest:flat.unlink();sync_directory(base)
        except OSError:pass
    return {'path':str(target),'sha256':digest,'directory':str(directory)}

def locations(store,sid,iid=None):
    with store.connect() as c:rows=[dict(r) for r in c.execute('SELECT e.* FROM text_exports e JOIN transcripts t ON t.id=e.transcript_id AND t.current=1 WHERE e.source_id=? AND (? IS NULL OR e.item_id=?) ORDER BY e.current DESC,e.created DESC',(sid,iid,iid))]
    result={}
    for row in rows:
        if row['item_id'] in result:continue
        p=Path(row['path'])
        try:
            if p.is_file() and hash_file(p)==row['sha256']:result[row['item_id']]={'path':str(p),'directory':str(p.parent)}
        except OSError:pass
    return result
