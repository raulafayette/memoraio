"""Inventory of real, checksum-verified files; discovery is never a download."""
import json
import hashlib
import time
from pathlib import Path
from .core import hash_file
_CACHE={}
_DOCS={}
_LIBRARIES={}

def verified(store,path,digest,folder):
    if not path or not digest:return None
    try:
        p=(store.root/path).resolve()
        if not p.is_relative_to((store.root/folder).resolve()):return None
        st=p.stat()
        if not p.is_file() or not st.st_size:return None
        signature=(str(p),st.st_size,st.st_mtime_ns,st.st_ctime_ns,digest)
        if signature not in _CACHE:
            if len(_CACHE)>20000:_CACHE.clear()
            _CACHE[signature]=hash_file(p)==digest
        return {'path':str(p),'bytes':st.st_size,'sha256':digest} if _CACHE[signature] else None
    except (OSError,ValueError):return None

def library_texts(store):
    key=str(store.root);cached=_LIBRARIES.get(key)
    if cached and time.monotonic()-cached[0]<5:return cached[1]
    refs={}
    for manifest in (store.root/'library').glob('*/*/*/current.json'):
        try:
            m=json.loads(manifest.read_text());entry=m['files']['transcricao.txt']
            path=manifest.parent/entry['path']
            refs[m['item_id']]=(m['transcript_id'],str(path.relative_to(store.root)),entry['sha256'])
        except (OSError,ValueError,KeyError,TypeError):continue
    _LIBRARIES[key]=(time.monotonic(),refs)
    return refs

def assets(store,c,item):
    iid=item['id'];out={}
    video=verified(store,item['path'],item['blob_hash'],'originals')
    if video:out['video']=video
    a=c.execute('SELECT * FROM audio_assets WHERE item_id=?',(iid,)).fetchone()
    if a:
        audio=verified(store,a['path'],a['sha256'],'originals')
        if audio:out['audio']=audio
    r=c.execute('SELECT value FROM service_state WHERE key=?',('mp3:'+iid,)).fetchone()
    if r:
        try:
            a=json.loads(r[0]);audio=verified(store,a.get('path'),a.get('sha256'),'originals')
            if audio:out['mp3']=audio
        except (ValueError,TypeError):pass
    t=c.execute('SELECT * FROM transcripts WHERE item_id=? AND current=1',(iid,)).fetchone()
    if t:
        text=verified(store,t['path'],t['sha256'],'transcripts')
        if text:
            try:
                if t['sha256'] not in _DOCS:
                    from .library import rich_text
                    doc=json.loads(Path(text['path']).read_text())
                    if len(_DOCS)>10000:_DOCS.clear()
                    _DOCS[t['sha256']]=(bool(doc.get('segments')),hashlib.sha256(rich_text(doc).encode()).hexdigest())
                has_segments,txt_digest=_DOCS[t['sha256']]
                if has_segments and t['quality']!='invalid':
                    txt=Path(text['path']).with_name('transcript.txt')
                    ref=library_texts(store).get(iid)
                    published=verified(store,ref[1],ref[2],'library') if ref and ref[0]==t['id'] else None
                    if published:out['txt']={**published,'origin':t['origin'],'quality':t['quality']}
                    else:
                        original=verified(store,str(txt.relative_to(store.root)),txt_digest,'transcripts')
                        if original:out['txt']={**original,'origin':t['origin'],'quality':t['quality']}
            except (ValueError,OSError):pass
    return out

def inventory(store,query):
    with store.connect() as c:
        sql='SELECT i.* FROM items i WHERE EXISTS(SELECT 1 FROM active_source_items a WHERE a.item_id=i.id)'
        if query.get('media_only')==['1']:
            sql+=" AND (i.path IS NOT NULL OR EXISTS(SELECT 1 FROM audio_assets a WHERE a.item_id=i.id) OR EXISTS(SELECT 1 FROM service_state ss WHERE ss.key='mp3:'||i.id))"
        items=c.execute(sql+' ORDER BY i.rowid DESC').fetchall()
        source_map={}
        for r in c.execute('SELECT a.item_id,s.id,s.name FROM active_source_items a JOIN sources s ON s.id=a.source_id'):
            source_map.setdefault(r['item_id'],[]).append({'id':r['id'],'name':r['name']})
        jobs={r['target']:dict(r) for r in c.execute("SELECT j.*,i.title FROM jobs j LEFT JOIN items i ON i.id=j.target WHERE j.state IN ('running','queued','retry','paused') ORDER BY j.created")}
        hidden={r[0] for r in c.execute("SELECT target FROM jobs WHERE kind IN ('transcribe','transcribe_asr') AND state IN ('failed','blocked','needs_auth') AND target NOT IN (SELECT target FROM jobs WHERE kind IN ('transcribe','transcribe_asr') AND state IN ('queued','running','retry'))")}
        rows=[];counts={'ready':0,'pending':0,'saved':0,'video':0,'mp3':0};objects={}
        for item in items:
            a=assets(store,c,item);ready='txt' in a;saved=any(k in a for k in ('video','audio','mp3'))
            eligible=item['platform']=='youtube' and item['id'] not in hidden
            counts['ready']+=ready;counts['pending']+=not ready and eligible;counts['saved']+=saved
            counts['video']+='video' in a;counts['mp3']+='mp3' in a
            for v in a.values():objects[v['path']]=v['bytes']
            group=query.get('group',['ready'])[0]
            if group=='ready' and not ready:continue
            if group=='pending' and (ready or not eligible):continue
            if group=='saved' and not saved:continue
            if query.get('source') and not set(query['source']).intersection(s['id'] for s in source_map.get(item['id'],[])):continue
            if query.get('title') and query['title'][0].casefold() not in (item['title'] or '').casefold():continue
            rows.append({'id':item['id'],'title':item['title'] or item['original_id'],'url':item['url'],'sources':source_map.get(item['id'],[]),'assets':a,'job':jobs.get(item['id'])})
    counts['bytes']=sum(objects.values());offset=max(0,int(query.get('offset',['0'])[0]));limit=min(200,max(1,int(query.get('limit',['60'])[0])))
    return {'items':rows[offset:offset+limit],'total':len(rows),'counts':counts,'offset':offset,'limit':limit}
