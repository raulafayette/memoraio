"""Remove only this user's service registration; never delete library data."""
from pathlib import Path
import os,subprocess,sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from memoria.service import LABEL
agent=Path.home()/'Library'/'LaunchAgents'/(LABEL+'.plist')
if agent.exists():
 subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}',str(agent)],capture_output=True)
 agent.unlink()
 print('Serviço removido. Catálogo, mídia, modelos e exportações preservados.')
else:print('Serviço não registrado neste usuário; nenhum arquivo de biblioteca alterado.')
