"""Readable archive folders follow completion month, never the date of a later copy."""
from datetime import datetime
import json
from zoneinfo import ZoneInfo

def month(store,created):
    if not created:return 'sem-data'
    from .preferences import read
    zone=read(store).get('archive_timezone','local')
    dt=datetime.fromtimestamp(float(created),ZoneInfo(zone)) if zone!='local' else datetime.fromtimestamp(float(created)).astimezone()
    return dt.strftime('%Y-%m')

def asset_date(store,iid,kind):
    dates=[]
    with store.connect() as c:
        row=c.execute('SELECT value FROM service_state WHERE key=?',('first_completion:'+kind+':'+iid,)).fetchone()
        if row:dates.append(float(row[0]))
    for p in (store.root/'metadata'/'assets'/iid).glob(kind+'-*.json'):
        try:
            stamp=json.loads(p.read_text()).get('collected_at')
            if isinstance(stamp,(int,float)):dates.append(stamp)
        except (OSError,ValueError,TypeError):pass
    return min(dates) if dates else None


def queue_organization(store):
    from .exports import queue_existing
    texts=queue_existing(store)
    with store.connect() as c:
        ids={r[0] for r in c.execute('SELECT id FROM items WHERE path IS NOT NULL')}
        ids.update(r[0].split(':',1)[1] for r in c.execute("SELECT key FROM service_state WHERE key LIKE 'mp3:%'"))
        for iid in ids:
            jid=store.enqueue(c,'organize',iid);c.execute('UPDATE jobs SET priority=82 WHERE id=?',(jid,))
    return {'txt_copies':texts,'media_items':len(ids)}
