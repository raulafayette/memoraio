"""Install a fresh personal macOS engine outside the source checkout."""
from pathlib import Path
import json
import shutil
import subprocess
import sys


def main():
    if sys.platform != 'darwin':
        raise SystemExit('Este instalador exige macOS.')
    source = Path(__file__).resolve().parent.parent
    home = Path.home() / 'Library/Application Support/Memoraio'
    engine = home / 'engine'
    if engine.exists():
        raise SystemExit('Já existe uma instalação. Preserve o acervo e use o procedimento de atualização em docs/installation.md.')
    for tool in ('ffmpeg', 'node', 'xcrun'):
        if not shutil.which(tool):
            raise SystemExit('Instale a dependência antes de continuar: ' + tool)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copytree(source, engine, ignore=shutil.ignore_patterns('.git', 'data', '.venv', '.service-venv', '__pycache__', '*.pyc', '*.app', '*.log', '.env', '.env.*'))
    subprocess.run([sys.executable, '-m', 'venv', str(home / 'runtime')], check=True)
    python = home / 'runtime/bin/python'
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(engine / 'requirements-acquisition.txt')], check=True)
    subprocess.run([str(python), str(engine / 'macos/build.py')], check=True)
    app = Path.home() / 'Applications/Memoraio.app'
    if app.exists():
        raise SystemExit('Aplicativo já existente preservado. Revise a instalação antes de substituí-lo.')
    app.parent.mkdir(exist_ok=True)
    shutil.copytree(engine / 'Memoraio.app', app)
    subprocess.run([str(python), '-m', 'memoria', '--data', str(home / 'data'), 'install-service'], cwd=engine, check=True)
    (home / 'installation.json').write_text(json.dumps({'version': 1, 'engine': str(engine), 'runtime': str(home / 'runtime'), 'data': str(home / 'data')}, indent=2))
    print('Instalado em Aplicativos da sua conta. Abra Memoraio. Nenhum modelo de IA foi baixado.')


if __name__ == '__main__':
    main()
