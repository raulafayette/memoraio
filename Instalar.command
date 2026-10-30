#!/bin/zsh
set -eu
cd "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/bin:/bin:$PATH"
if [[ ! -x /opt/homebrew/bin/python3.12 ]]; then
  echo 'Instale Python 3.12 pelo Homebrew: brew install python@3.12'
  exit 1
fi
/opt/homebrew/bin/python3.12 scripts/install_macos.py
