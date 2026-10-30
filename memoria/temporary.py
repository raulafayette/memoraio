"""Remove temporary ASR media only after validated publication, including after restart."""
import fcntl
import json
import shutil
import time
from .core import hash_file


def prepare(store,iid,asset):
    if not asset.get('temporary'):return
    marker={'item_id':iid,'path':asset['path'],'sha256':asset['sha256'],'at':time.time()}
    with store.connect() as c:c.execute('INSERT INTO service_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('temporary_cleanup:'+iid,json.dumps(marker)))

def cleanup(store):
    with store.connect() as c:markers=[dict(x) for x in c.execute("SELECT * FROM service_state WHERE key LIKE 'temporary_cleanup:%'")]
    for row in markers:
        marker=json.loads(row['value']);iid=marker['item_id'];stage=(store.root/'temporary'/iid).resolve()
        path=(store.root/marker['path']).resolve()
        if not stage.is_relative_to((store.root/'temporary').resolve()) or not path.is_relative_to(stage):continue
        with store.connect() as c:
            t=c.execute('SELECT * FROM transcripts WHERE item_id=? AND current=1',(iid,)).fetchone()
            active=c.execute("SELECT 1 FROM jobs WHERE target=? AND kind IN ('transcribe','transcribe_asr') AND state IN ('queued','retry','paused','running')",(iid,)).fetchone()
        published=False
        if t:
            p=(store.root/t['path']).resolve()
            try:
                if p.is_relative_to((store.root/'transcripts').resolve()) and hash_file(p)==t['sha256']:
                    doc=json.loads(p.read_text());published=bool(doc.get('segments') and (doc.get('model') or {}).get('audio_sha256')==marker['sha256'] and p.with_name('transcript.txt').is_file())
            except (OSError,ValueError):pass
        if not published and (active or time.time()-marker['at']<86400):continue
        stage.mkdir(exist_ok=True)
        with (stage/'.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:continue
            try:
                if path.is_file():
                    if hash_file(path)!=marker['sha256']:continue
                    path.unlink()
                asr=stage/'asr'
                if asr.is_dir() and not asr.is_symlink():shutil.rmtree(asr)
                for name in ('audit-input.json','speech-audit.json','compare-input.json','compare-result.json'):(stage/name).unlink(missing_ok=True)
            except OSError:continue
            with store.connect() as c:c.execute('DELETE FROM service_state WHERE key=? AND value=?',(row['key'],row['value']))
            store.attempt(iid,'temporary_cleanup','done','Áudio temporário removido após publicação validada' if published else 'Áudio temporário de tentativa antiga removido após 24 horas')
