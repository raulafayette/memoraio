#!/usr/bin/env bash
set -euo pipefail
source_root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
install_root="$HOME/.local/share/Memoraio"
for tool in python3 ffmpeg node; do
  command -v "$tool" >/dev/null || { echo "Dependência ausente: $tool. Consulte docs/windows.md."; exit 1; }
done
python3 -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12 ou superior necessário"'
node -e 'if (Number(process.versions.node.split(".")[0]) < 22) { console.error("Node.js 22 ou superior necessário. Consulte docs/windows.md."); process.exit(1); }'
if [[ -e "$install_root/engine" ]]; then
  echo 'Instalação existente preservada. Consulte o procedimento de atualização.'
  exit 1
fi
mkdir -p "$install_root"
chmod 700 "$install_root"
python3 - "$source_root" "$install_root/engine" <<'COPY'
from pathlib import Path
import shutil,sys
source,target=map(Path,sys.argv[1:])
shutil.copytree(source,target,ignore=shutil.ignore_patterns('.git','data','.venv','.service-venv','__pycache__','*.pyc','*.app','.env','.env.*','*.log'))
COPY
python3 -m venv "$install_root/runtime"
"$install_root/runtime/bin/python" -m pip install -r "$install_root/engine/requirements-acquisition.txt"
echo 'Instalação concluída; nenhum modelo de IA baixado.'
