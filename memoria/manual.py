"""One-time transition from legacy scheduled acquisition to manual batches."""
import time

def enable(store):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        previous=c.execute("SELECT value FROM service_state WHERE key='manual_mode'").fetchone()
        if previous and previous[0]=='1':return False
        c.execute("UPDATE sources SET cadence='manual',next_sync=NULL,auto_process=0")
        # Explicit operation requests have saved preferences; preserve those batches.
        c.execute("""UPDATE jobs SET state='cancelled',control=NULL,owner=NULL,lease_until=NULL,
            error='Automação desativada; inicie um lote manual',updated=?
            WHERE state IN ('queued','retry','paused','running')
            AND kind IN ('discover','sync','enumerate','download','audio','formats','transcribe','transcribe_asr')
            AND NOT EXISTS(SELECT 1 FROM service_state ss WHERE ss.key='job_options:'||jobs.id)""",(time.time(),))
        c.execute("INSERT INTO service_state VALUES('manual_mode','1') ON CONFLICT(key) DO UPDATE SET value='1'")
    return True
