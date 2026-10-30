"""Counts of available verified files, dated by their first successful publication."""
from datetime import datetime,timedelta,timezone
import json
import time
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from .inventory import assets


def summary(store,zone='UTC',now=None):
    try:tz=ZoneInfo(zone)
    except (ZoneInfoNotFoundError,ValueError,TypeError):tz=timezone.utc
    now=time.time() if now is None else now
    local=datetime.fromtimestamp(now,tz);midnight=local.replace(hour=0,minute=0,second=0,microsecond=0)
    week=(midnight-timedelta(days=local.weekday())).timestamp();month=midnight.replace(day=1).timestamp()
    result={'transcripts':{'total':0,'week':0,'month':0},'media':{'total':0,'week':0,'month':0},'timezone':str(tz)}
    def count(group,created):
        out=result[group];out['total']+=1
        if isinstance(created,(int,float)) and created<=now:
            out['week']+=created>=week;out['month']+=created>=month
    with store.connect() as c:
        items=c.execute('SELECT i.* FROM items i WHERE EXISTS(SELECT 1 FROM active_source_items a WHERE a.item_id=i.id)').fetchall()
        for item in items:
            present=assets(store,c,item);iid=item['id']
            if 'txt' in present:
                created=c.execute("SELECT min(created) FROM transcripts WHERE item_id=? AND quality!='invalid'",(iid,)).fetchone()[0]
                count('transcripts',created)
            if 'mp3' in present:
                row=c.execute('SELECT value FROM service_state WHERE key=?',('mp3:'+iid,)).fetchone()
                try:created=json.loads(row[0]).get('collected_at') if row else None
                except (ValueError,TypeError):created=None
                first=c.execute('SELECT value FROM service_state WHERE key=?',('first_completion:mp3:'+iid,)).fetchone()
                count('media',float(first[0]) if first else created)
            if 'video' in present:
                dates=[]
                for path in (store.root/'metadata'/'assets'/iid).glob('video-*.json'):
                    try:
                        doc=json.loads(path.read_text());date=doc.get('collected_at')
                        if isinstance(date,(int,float)):dates.append(date)
                    except (OSError,ValueError,TypeError):pass
                first=c.execute('SELECT value FROM service_state WHERE key=?',('first_completion:video:'+iid,)).fetchone()
                if first:dates.append(float(first[0]))
                count('media',min(dates) if dates else None)
    return result


def completed_at(store,iid,kind):
    key='first_completion:'+kind+':'+iid
    with store.connect() as c:
        c.execute('INSERT OR IGNORE INTO service_state VALUES(?,?)',(key,str(time.time())))
        return float(c.execute('SELECT value FROM service_state WHERE key=?',(key,)).fetchone()[0])
