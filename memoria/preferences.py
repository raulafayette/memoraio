"""Local settings. CPU and MLX limits apply to subsequently launched tasks."""
import json
DEFAULT={'cpu_threads':2,'mlx_memory_gib':4,'prevent_sleep':False,'export_directory':'','theme':'system','instagram_asr':False,'transcript_directory':'','archive_timezone':'local'}
def read(store):
    with store.connect() as c:r=c.execute("SELECT value FROM service_state WHERE key='preferences:v3'").fetchone()
    return {**DEFAULT,**(json.loads(r[0]) if r else {})}
def save(store,data):
    if not isinstance(data,dict) or set(data)-set(DEFAULT):raise ValueError('Ajustes desconhecidos')
    p={**read(store),**data}
    if type(p['cpu_threads'])!=int or not 1<=p['cpu_threads']<=8:raise ValueError('CPU: escolha entre 1 e 8 threads')
    if type(p['mlx_memory_gib'])!=int or not 2<=p['mlx_memory_gib']<=6:raise ValueError('Memória MLX: escolha entre 2 e 6 GiB')
    if type(p['prevent_sleep'])!=bool:raise ValueError('Prevenção de suspensão inválida')
    if p['theme'] not in ('light','dark','system'):raise ValueError('Escolha tema diurno, noturno ou automático')
    if type(p['instagram_asr'])!=bool:raise ValueError('Reconhecimento de voz inválido')
    from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
    if not isinstance(p['archive_timezone'],str):raise ValueError('Fuso horário inválido')
    if p['archive_timezone']!='local':
        try:ZoneInfo(p['archive_timezone'])
        except (ZoneInfoNotFoundError,ValueError):raise ValueError('Fuso horário inválido')
    from pathlib import Path
    directory=p['export_directory']
    if not isinstance(directory,str) or len(directory)>1000:raise ValueError('Pasta inválida')
    if directory:
        path=Path(directory).expanduser()
        if not path.is_absolute() or not path.is_dir():raise ValueError('Escolha uma pasta absoluta já existente')
        path=path.resolve()
        if not (path.is_relative_to(Path.home()) or path.is_relative_to(Path('/Volumes'))):raise ValueError('Escolha uma pasta pessoal ou de um volume externo')
        if any(path.is_relative_to(store.root/x) for x in ('originals','transcripts','models','temporary')):raise ValueError('Escolha uma pasta fora dos objetos internos do acervo')
        p['export_directory']=str(path)
    if not isinstance(p['transcript_directory'],str):raise ValueError('Pasta inválida')
    p['transcript_directory']=validate_directory(store,p['transcript_directory']) if p['transcript_directory'] else ''
    previous=read(store).get('transcript_directory','')
    with store.connect() as c:c.execute("INSERT INTO service_state VALUES('preferences:v3',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(p),))
    if previous!=p['transcript_directory']:
        from .exports import queue_existing
        queue_existing(store)
    return p


def validate_directory(store,value):
    from pathlib import Path
    if not isinstance(value,str) or len(value)>1000 or any(ord(c)<32 for c in value):raise ValueError('Pasta inválida')
    path=Path(value).expanduser()
    if not path.is_absolute() or not path.is_dir():raise ValueError('Escolha uma pasta existente')
    path=path.resolve()
    if not (path.is_relative_to(Path.home()) or path.is_relative_to(Path('/Volumes'))):raise ValueError('Escolha uma pasta pessoal ou de um disco externo')
    if any(path.is_relative_to(store.root/x) for x in ('originals','transcripts','models','temporary','library','backups','indexes')):raise ValueError('Escolha uma pasta fora dos arquivos internos do aplicativo')
    return str(path)
