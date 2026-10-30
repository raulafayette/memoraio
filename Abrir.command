#!/bin/zsh
set -eu
cd "${0:A:h}"
export PATH="/Library/Frameworks/Python.framework/Versions/3.10/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
if [[ -x .service-venv/bin/python3 ]]; then
  export PATH="$PWD/.service-venv/bin:$PATH"
elif [[ -x .venv/bin/python3 ]]; then
  export PATH="$PWD/.venv/bin:$PATH"
fi
export MEMORIA_DATA="${MEMORIA_DATA:-$PWD/data}"
mkdir -p "$MEMORIA_DATA"
chmod 700 "$MEMORIA_DATA"
if [[ -f "$MEMORIA_DATA/service-health.json" ]]; then
  python3 -m memoria open-ui
  exit 0
fi
# Worker has its own lifetime; closing the browser has no effect on it.
if ! mkdir "$MEMORIA_DATA/launcher.lock" 2>/dev/null; then
  echo 'Outra sessão pode estar aberta. Consulte docs/operacao.md antes de remover launcher.lock.'
  exit 1
fi
python3 -m memoria worker >> "$MEMORIA_DATA/worker.log" 2>&1 &
worker_pid=$!
trap 'kill "$worker_pid" 2>/dev/null || true; rmdir "$MEMORIA_DATA/launcher.lock" 2>/dev/null || true' EXIT INT TERM
python3 -m memoria serve --open --port "${MEMORIA_PORT:-8765}"
