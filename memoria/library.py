"""Versioned, readable personal library. Original transcript objects stay immutable."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import time
from .core import atomic_json, hash_file, safe_metadata, sync_file, durable_mkdir

UNKNOWN='Indisponível'

def iso(value):
    if value is None:return None
    try:return datetime.fromtimestamp(float(value),timezone.utc).isoformat()
    except (ValueError,TypeError,OverflowError):return None

def segment_stamp(seconds):
    ms=round(float(seconds)*1000);hours,ms=divmod(ms,3600000);minutes,ms=divmod(ms,60000);secs,ms=divmod(ms,1000)
    return f'{hours:02}:{minutes:02}:{secs:02}.{ms:03}'

def rich_text(doc):
    def value(v):return UNKNOWN if v is None or v=='' or v==[] else (json.dumps(v,ensure_ascii=False,indent=2) if isinstance(v,(list,dict)) else str(v))
    parts=['TRANSCRIÇÃO AUDIOVISUAL — EXPORTAÇÃO INTEGRAL','Informações ausentes são marcadas como indisponíveis. A fala não é um resumo.']
    for title,key in [('IDENTIFICAÇÃO','identification'),('DADOS TEMPORAIS','dates'),('DADOS TÉCNICOS','technical'),('METADADOS COMPLEMENTARES','additional'),('HISTÓRICO DE PROCESSAMENTO','history')]:
        parts.extend(['',title])
        for k,v in doc.get(key,{}).items():parts.append(f'{k}: {value(v)}')
    if not doc.get('identification'):
        parts.extend(['', 'IDENTIFICAÇÃO LEGADA',json.dumps({k:v for k,v in doc.items() if k!='segments'},ensure_ascii=False,indent=2)])
    parts.extend(['','TRANSCRIÇÃO INTEGRAL'])
    for seg in doc['segments']:
        speaker=seg.get('speaker') if seg.get('speaker_verified') else None
        parts.extend([f"[{segment_stamp(seg['start'])} - {segment_stamp(seg['end'])}]"+(f' {speaker}' if speaker else ''),seg['text'],''])
    return '\n'.join(parts)+'\n'

def enrich(store,item,doc,info=None):
    meta={**json.loads(item['metadata']),**safe_metadata(info or {})}
    with store.connect() as c:
        sources=[dict(x) for x in c.execute("SELECT s.id,s.name,s.url,si.seen,ss.value AS permanent_id FROM active_source_items si JOIN sources s ON s.id=si.source_id LEFT JOIN service_state ss ON ss.key='channel:'||s.id WHERE si.item_id=? ORDER BY s.rowid",(item['id'],))]
        first_scan=c.execute('SELECT min(r.started) FROM run_items ri JOIN scan_runs r ON r.id=ri.run_id WHERE ri.item_id=?',(item['id'],)).fetchone()[0]
        attempts=[dict(x) for x in c.execute('SELECT at,method,state,detail FROM item_attempts WHERE item_id=? ORDER BY at,id',(item['id'],))]
        versions=[dict(x) for x in c.execute('SELECT id,created,origin,sha256 FROM transcripts WHERE item_id=? ORDER BY created',(item['id'],))]
        audio=c.execute('SELECT * FROM audio_assets WHERE item_id=?',(item['id'],)).fetchone()
    description=meta.get('description');segments=doc['segments'];collected=min((s['seen'] for s in sources),default=None)
    related=[]
    related.extend(doc.get('source_files',[]))
    for manifest in (store.root/'metadata'/'assets'/item['id']).glob('*.json'):
        related.append(json.loads(manifest.read_text()))
    if audio:related.append(dict(audio))
    if item.get('path'):related.append({'path':item['path'],'sha256':item['blob_hash'],'size':item['size'],'kind':'video'})
    # Original dates and UTC conversion are explicit; never infer a source timezone.
    return {**doc,'schema_version':3,
      'identification':{'internal_id':item['id'],'platform':item['platform'],'original_id':item['original_id'],'url':item['url'],'channel':meta.get('channel') or meta.get('uploader'),'permanent_source_id':meta.get('channel_id') or next((s['permanent_id'] for s in sources if s['permanent_id']),None),'author':meta.get('uploader'),'original_title':meta.get('title') or item['title'],'alternative_title':meta.get('alt_title'),'description':description,'publication_type':meta.get('media_type') or meta.get('live_status'),'playlist':meta.get('playlist'),'playlist_id':meta.get('playlist_id'),'sources':sources},
      'dates':{'publication_date_original':meta.get('upload_date'),'publication_timestamp_utc':iso(meta.get('timestamp')),'publication_timezone_original':meta.get('release_timezone'),'first_inventory_scan_utc':iso(first_scan),'collection_observed_utc':iso(collected),'last_human_verification_utc':iso(max((a['at'] for a in attempts if a['method']=='human_review' and a['state']=='verified'),default=None)),'transcribed_utc':iso(doc.get('created')),'last_metadata_verification_utc':iso(meta.get('metadata_collected_at')),'exported_utc':iso(time.time()),'duration_seconds':doc.get('duration')},
      'technical':{'original_language':meta.get('language'),'detected_language':doc.get('language'),'transcript_origin':doc.get('origin'),'provider':doc.get('provider') or ('mlx-whisper' if doc.get('origin')=='local_asr' else 'yt-dlp'),'provider_version':doc.get('provider_version'),'model':doc.get('model'),'configuration':doc.get('configuration'),'caption_tracks':meta.get('caption_tracks'),'segments':len(segments),'words':len(re.findall(r'\w+',' '.join(s['text'] for s in segments))),'validation':doc.get('validation')},
      'additional':{'hashtags':re.findall(r'(?<!\w)#[\w]+',description or ''),'tags':meta.get('tags'),'categories':meta.get('categories'),'chapters':meta.get('chapters'),'thumbnail':meta.get('thumbnail'),'engagement':{k:meta.get(k) for k in ('view_count','like_count','comment_count')},'description_links':re.findall(r'https?://[^\s<>]+',description or ''),'related_files':related},
      'history':{'attempts':attempts,'versions':versions,'corrections':doc.get('corrections',[]),'export_note':'Exportação derivada; objetos originais e revisões anteriores preservados.'}}

def component(value):
    text=str(value)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,150}',text):raise ValueError('Identificador de biblioteca inválido')
    return text

def publish_library(store,iid):
    with store.connect() as c:
        item=c.execute('SELECT * FROM items WHERE id=?',(iid,)).fetchone()
        row=c.execute('SELECT * FROM transcripts WHERE item_id=? AND current=1',(iid,)).fetchone()
    if not item or not row:raise ValueError('Transcrição atual não encontrada')
    source=(store.root/row['path']).resolve()
    if not source.is_relative_to((store.root/'transcripts').resolve()) or hash_file(source)!=row['sha256']:raise ValueError('Transcrição com integridade inválida')
    doc=enrich(store,dict(item),json.loads(source.read_text()))
    source_id=doc['identification']['permanent_source_id'] or (doc['identification']['sources'][0]['id'] if doc['identification']['sources'] else 'unknown')
    from .preferences import read
    preferences=read(store)
    library_root=Path(preferences['export_directory'])/'Memoraio Library' if preferences['export_directory'] else store.root/'library'
    base=library_root/component(item['platform'])/component(source_id)/component(item['original_id'])
    # Derived export revisions must not overwrite an earlier enriched artifact.
    version=base/'versions'/(component(row['id'])+'-'+str(time.time_ns()));durable_mkdir(version)
    atomic_json(version/'metadados.json',doc)
    text=version/'transcricao.txt'
    with text.open('w',encoding='utf-8') as f:f.write(rich_text(doc));f.flush();sync_file(f.fileno())
    manifest={'item_id':iid,'transcript_id':row['id'],'original_json':row['path'],'original_sha256':row['sha256'],'files':{name:{'path':str((version/name).relative_to(base)),'sha256':hash_file(version/name)} for name in ('transcricao.txt','metadados.json')}}
    atomic_json(version/'manifest.json',manifest)
    for name in manifest['files']:
        temp=base/(name+'.next');temp.unlink(missing_ok=True);temp.symlink_to(manifest['files'][name]['path']);os.replace(temp,base/name)
    atomic_json(base/'current.json',manifest)
    return str(base.relative_to(store.root)) if base.is_relative_to(store.root) else str(base)
