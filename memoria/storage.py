"""Per-source content storage and explicitly approximate text estimates."""
from pathlib import Path
import json
from .inventory import assets,library_texts


def metrics(store,c,items,source_id=None,asset_cache=None):
    seen=set();occupied=0;ready=0;known_duration=0;unknown_duration=0;pending=0
    def add(path):
        nonlocal occupied
        try:
            p=Path(path)
            if p.is_symlink() or not p.is_file():return
            st=p.stat();key=(st.st_dev,st.st_ino)
            if key not in seen:seen.add(key);occupied+=st.st_size
        except OSError:pass
    def tree(path):
        p=Path(path)
        if p.is_dir() and not p.is_symlink():
            for child in p.rglob('*'):add(child)
        else:add(p)
    if source_id:
        for row in c.execute('SELECT path FROM text_exports WHERE source_id=?',(source_id,)).fetchall():add(row[0])
    libraries=library_texts(store)
    for item in items:
        if asset_cache is not None and item['id'] in asset_cache:real=asset_cache[item['id']]
        else:
            real=assets(store,c,item)
            if asset_cache is not None:asset_cache[item['id']]=real
        has_text='txt' in real;ready+=has_text
        for asset in real.values():add(asset['path'])
        for directory in ('transcripts','temporary'):tree(store.root/directory/item['id'])
        tree(store.root/'metadata'/'assets'/item['id']);add(store.root/'metadata'/(item['id']+'.json'))
        ref=libraries.get(item['id'])
        if ref:
            file=store.root/ref[1]
            if len(file.parents)>2:tree(file.parents[2])
        if not has_text:
            pending+=1
            try:duration=float(json.loads(item['metadata']).get('duration') or 0)
            except (ValueError,TypeError):duration=0
            if duration>0:known_duration+=duration
            else:unknown_duration+=1
    minutes=known_duration/60+unknown_duration*10
    low=int(pending*20*1024+minutes*6*1024);high=int(pending*60*1024+minutes*18*1024)
    samples=[]
    if source_id:
        for row in c.execute("SELECT j.updated-(SELECT max(e.at) FROM events e WHERE e.job_id=j.id AND e.kind='claimed') AS seconds FROM jobs j JOIN active_source_items a ON a.item_id=j.target WHERE a.source_id=? AND j.kind IN ('transcribe','transcribe_asr') AND j.state='done' ORDER BY j.updated DESC LIMIT 30",(source_id,)).fetchall():
            if row[0] and 0<row[0]<3600:samples.append(row[0])
    if len(samples)>=3:
        rate=__import__('statistics').median(samples);time_low=int(pending*rate*.7);time_high=int(pending*rate*1.6);time_basis='observed'
    elif items and items[0]['platform']=='instagram':
        time_low=int(minutes*60*.2+pending*5);time_high=int(minutes*60*.65+pending*20);time_basis='approximate'
    else:time_low=pending*8;time_high=pending*30;time_basis='approximate'
    return {'estimated_seconds_min':time_low,'estimated_seconds_max':time_high,'time_estimate_basis':time_basis,'ready':ready,'identified':len(items),'remaining':len(items)-ready,'occupied_bytes':occupied,'estimated_pending_text_bytes_min':low,'estimated_pending_text_bytes_max':high,'estimated_unknown_duration_items':unknown_duration,'estimate_kind':'text_and_metadata','estimate_assumptions':'6–18 KiB por minuto e 20–60 KiB por conteúdo; duração ausente estimada em 10 minutos. Não inclui vídeo, áudio nem modelo compartilhado.'}
