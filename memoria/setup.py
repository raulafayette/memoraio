"""Explicit one-time local installation: no cloud AI or session dependency."""
import json
import os
from pathlib import Path
import shutil
from .core import atomic_json

def setup(store):
    if shutil.disk_usage(store.root).free<10*1024**3:raise RuntimeError('Instalação exige10GiB livres para dependências/modelos e reserva operacional')
    os.environ['HF_HOME']=str(store.root/'models');os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    for tool in ('ffmpeg','ffprobe','node'):
        if not shutil.which(tool):raise RuntimeError(tool+' não encontrado; consulte instalação')
    from huggingface_hub import snapshot_download
    manifest=json.loads((Path(__file__).parent.parent/'model-revisions.json').read_text())
    for repo,spec in manifest.items():
        path=snapshot_download(repo,revision=spec['revision'],allow_patterns=spec['allow_patterns'])
        atomic_json(store.root/spec['config_file'],{'repo':repo,'path':path,'revision':spec['revision']})
    store.bootstrap_official()
    print('Modelos locais configurados; fontes pessoais existentes preservadas. Instale o serviço com install-service.')
