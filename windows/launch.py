"""Start the POSIX engine in WSL; return its local session to PowerShell."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit


def ready(data):
    try:
        session = json.loads((data / 'ui-session.json').read_text())
        url = urlsplit(session['url'])
        if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.port != 8765:
            return None
        with urllib.request.urlopen(session['url'], timeout=2) as response:
            if response.status == 200:
                return session['url']
    except (OSError, ValueError, KeyError):
        pass
    return None


def main():
    engine = Path(__file__).resolve().parent.parent
    data = engine.parent / 'data'
    data.mkdir(mode=0o700, exist_ok=True)
    url = ready(data)
    if not url:
        log = os.open(data / 'launcher.log', os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            subprocess.Popen([sys.executable, '-m', 'memoria', '--data', str(data), 'service'], cwd=engine, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        finally:
            os.close(log)
        for _ in range(45):
            url = ready(data)
            if url:
                break
            time.sleep(1)
    if not url:
        raise SystemExit('O serviço não respondeu. Consulte launcher.log; preserve data.')
    print(url)


if __name__ == '__main__':
    main()
