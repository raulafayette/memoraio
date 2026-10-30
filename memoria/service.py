"""Own persistent scheduler and supervised processes, independent of AI chats."""
import fcntl
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
from .core import atomic_json

LABEL='local.memoria.audiovisual'
CHANNEL_CONCURRENCY=3

def service_commands(port):
    commands=[]
    for index in range(CHANNEL_CONCURRENCY):
        suffix='' if index==0 else '-'+str(index+1)
        commands.extend([('acquisition'+suffix,['worker','--lane','acquire']),('processing'+suffix,['worker','--lane','transcript'])])
    return [*commands,('maintenance',['worker','--lane','maintenance']),('web',['serve','--port',str(port)])]


def environment(store):
    return {**os.environ,'PATH':os.pathsep.join([str(Path(sys.executable).parent),'/opt/homebrew/bin',os.environ.get('PATH','/usr/bin:/bin')]),'MEMORIA_DATA':str(store.root),'HF_HOME':str(store.root/'models'),'HF_HUB_DISABLE_TELEMETRY':'1','PYANNOTE_METRICS_ENABLED':'0','DO_NOT_TRACK':'1','MEMORIA_SERVICE':'1','MEMORIA_UI_STATE':str(Path.home()/'Library'/'Application Support'/'MemoriaAudiovisual'/'ui-session.json'),'OMP_NUM_THREADS':'2','VECLIB_MAXIMUM_THREADS':'2','TOKENIZERS_PARALLELISM':'false','NUMBA_CACHE_DIR':str(store.root/'cache')}

def service(store,port=8765):
    lock=open(store.root/'service.lock','a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return
    from .manual import enable
    enable(store)
    children={};files={};last_tick=0;sleep_guard=None;started={};last_loop_wall=time.time()
    env=environment(store)
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    try:
        while True:
            wall=time.time()
            if wall-last_loop_wall>60:started={k:wall for k in children}
            last_loop_wall=wall
            for kind,command in service_commands(port):
                if kind not in children or children[kind].poll() is not None:
                    if kind in files:files[kind].close()
                    files[kind]=open(store.root/(kind+'.log'),'ab')
                    children[kind]=subprocess.Popen([sys.executable,'-m','memoria','--data',str(store.root),*command],env=env,stdout=files[kind],stderr=subprocess.STDOUT,start_new_session=True)
                    started[kind]=time.time()
                    time.sleep(.3)
            check_worker_health(store,children,started)
            from .preferences import read
            preferences=read(store)
            with store.connect() as c:
                running=c.execute("SELECT count(*) FROM jobs WHERE state='running'").fetchone()[0]
                paused=c.execute("SELECT value FROM service_state WHERE key='paused'").fetchone()
            keep_awake=preferences['prevent_sleep'] and running and not (paused and paused[0]=='1')
            if sys.platform=='darwin' and keep_awake and (sleep_guard is None or sleep_guard.poll() is not None):
                sleep_guard=subprocess.Popen(['/usr/bin/caffeinate','-i','-w',str(os.getpid())])
            elif not keep_awake and sleep_guard is not None:
                if sleep_guard.poll() is None:sleep_guard.terminate();sleep_guard.wait(timeout=3)
                sleep_guard=None
            if time.monotonic()-last_tick>=30:
                store.tick();last_tick=time.monotonic()
                backup_if_due(store)
                reports=store.root/'reports';reports.mkdir(exist_ok=True)
                audit=store.audit();metrics=[{k:v for k,v in x.items() if k not in ('runs',)} for x in audit]
                atomic_json(reports/'coverage-latest.json',{'at':time.time(),'sources':metrics,'platform_total_known':False,'status':'Operação manual; não constitui cobertura integral certificada'})
                atomic_json(store.root/'service-health.json',{'at':time.time(),'pid':os.getpid(),'children':{k:v.pid for k,v in children.items()},'next_check_seconds':30,'parallel_channels':CHANNEL_CONCURRENCY})
            time.sleep(1)
    except KeyboardInterrupt:pass
    finally:
        if sleep_guard is not None and sleep_guard.poll() is None:sleep_guard.terminate();sleep_guard.wait(timeout=3)
        for child in children.values():
            if child.poll() is None:child.terminate()
        for child in children.values():
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
        for file in files.values():file.close()
        lock.close()


def backup_if_due(store,now=None):
    now=now or time.time()
    with store.connect() as c:
        values=dict((r['key'],r['value']) for r in c.execute("SELECT * FROM service_state WHERE key IN ('last_backup','last_backup_attempt')"))
    if now-float(values.get('last_backup','0'))<86400 or now-float(values.get('last_backup_attempt','0'))<3600:return
    status='ok';detail='Backup do catálogo concluído'
    try:
        if shutil.disk_usage(store.root).free<5*1024**3+2*store.db.stat().st_size:
            raise RuntimeError('Backup adiado para preservar reserva de5GiB; libere espaço ou configure volume externo')
        store.backup()
    except Exception as error:status='blocked';detail=type(error).__name__+': '+str(error)
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        updates={'last_backup_attempt':str(now),'backup_status':json.dumps({'state':status,'at':now,'detail':detail},ensure_ascii=False)}
        if status=='ok':updates['last_backup']=str(now)
        for key,value in updates.items():c.execute('INSERT INTO service_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
        store.event(c,None,'backup_'+status,detail)
    return status

def install(store,port=8765):
    import plistlib
    root=Path(__file__).resolve().parent.parent
    agent=Path.home()/'Library'/'LaunchAgents'/(LABEL+'.plist')
    agent.parent.mkdir(parents=True,exist_ok=True)
    settings={'Label':LABEL,'ProgramArguments':[sys.executable,'-m','memoria','--data',str(store.root),'service','--port',str(port)],'WorkingDirectory':str(root),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,'ProcessType':'Background','Nice':10,'EnvironmentVariables':environment(store),'StandardOutPath':str(store.root/'supervisor.log'),'StandardErrorPath':str(store.root/'supervisor-error.log')}
    # Save only explicit needed variables; never persist ambient secrets into a plist.
    settings['EnvironmentVariables']={k:v for k,v in settings['EnvironmentVariables'].items() if k in ('PATH','MEMORIA_DATA','HF_HOME','HF_HUB_DISABLE_TELEMETRY','PYANNOTE_METRICS_ENABLED','DO_NOT_TRACK','MEMORIA_SERVICE','MEMORIA_UI_STATE','NUMBA_CACHE_DIR','OMP_NUM_THREADS','VECLIB_MAXIMUM_THREADS','TOKENIZERS_PARALLELISM')}
    if agent.exists():
        previous=store.root/'backups'/('launchagent-'+str(time.time_ns())+'.plist');previous.write_bytes(agent.read_bytes())
        subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}',str(agent)],capture_output=True)
    tmp=agent.with_suffix('.tmp');tmp.write_bytes(plistlib.dumps(settings));os.chmod(tmp,0o600);os.replace(tmp,agent)
    subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(agent)],check=True)
    print(agent)

def open_ui(store):
    import webbrowser
    session=json.loads((store.root/'ui-session.json').read_text())
    import http.client
    from urllib.parse import urlsplit
    url=urlsplit(session['url'])
    if url.hostname!='127.0.0.1':raise ValueError('Endereço local inválido')
    connection=http.client.HTTPConnection('127.0.0.1',url.port,timeout=3)
    try:
        connection.request('GET',url.path+'?'+url.query);response=connection.getresponse();response.read()
        if response.status!=303:raise RuntimeError('Sessão expirada; tente novamente após reinício do serviço')
    finally:connection.close()
    webbrowser.open(session['url'])

def set_paused(store,paused,interrupt_running=False):
    """Resume only tasks interrupted by this global action, not individual pauses."""
    if type(paused)!=bool:raise ValueError('Estado de pausa inválido')
    now=time.time()
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute("INSERT INTO service_state VALUES('paused',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('1' if paused else '0',))
        previous=c.execute("SELECT value FROM service_state WHERE key='global_pause_jobs'").fetchone();ids=json.loads(previous[0]) if previous else []
        if paused and interrupt_running:
            newly=[r[0] for r in c.execute("SELECT id FROM jobs WHERE state='running' AND control IS NULL")]
            for jid in newly:c.execute("UPDATE jobs SET control='pause' WHERE id=? AND state='running'",(jid,))
            ids=list(dict.fromkeys(ids+newly))
        elif not paused:
            for jid in ids:
                c.execute("UPDATE jobs SET state='queued',control=NULL,attempts=0,available=?,updated=? WHERE id=? AND state='paused'",(now,now,jid))
                c.execute("UPDATE jobs SET control=NULL WHERE id=? AND state='running' AND control='pause'",(jid,))
            ids=[]
        c.execute("INSERT INTO service_state VALUES('global_pause_jobs',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(ids),))
    return paused

def check_worker_health(store,children,started,now=None):
    """Terminate a stalled worker after a startup/wake grace period; leases recover it."""
    now=time.time() if now is None else now
    for kind,child in children.items():
        if kind.split('-')[0] not in ('acquisition','processing','maintenance'):continue
        if child is None or child.poll() is not None or now-started.get(kind,now)<=120:continue
        with store.connect() as c:seen=c.execute('SELECT max(last_seen) FROM workers WHERE pid=?',(child.pid,)).fetchone()[0]
        if seen is None or now-seen>120:
            child.terminate()
            with store.connect() as c:store.event(c,None,'worker_stalled',kind+' sem heartbeat; reinício solicitado com checkpoints preservados')
            # Avoid repeated signals while the process releases its lock/helper.
            started[kind]=now
