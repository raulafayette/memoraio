import os
import time
from pathlib import Path
import subprocess
import tempfile
import threading
from memoria.core import Store
from memoria.server import Server
from tests.test_channels_v5 import fixture,publish,A

def run():
    with tempfile.TemporaryDirectory() as d:
        store=Store(d);one,two=fixture(store);store.ingest(one,[{'id':A,'title':'Vídeo controlado'}]);publish(store,'youtube_'+A);store.ingest(two,[{'id':A,'title':'Vídeo controlado'}])
        from memoria.channel_ui import begin_review
        with store.connect() as c:
            c.execute("INSERT INTO scan_runs(id,source_id,started,finished,state) VALUES(?,?,?,?,?)",('ui-review',one,time.time(),time.time(),'enumerated_accessible'))
            begin_review(c,'ui-review',one)
        store.observe('ui-review',{'id':'abcdefghijk','title':'Conteúdo novo identificado','duration':2})
        server=Server(store,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            env={**os.environ,'TEST_URL':f'http://127.0.0.1:{server.server_port}/?token={server.token}','TEST_SCREENSHOT':str(Path('docs/interface-canais-v5.png').resolve())}
            subprocess.run(['node','tests/ui_channels_v5.js'],env=env,check=True,timeout=90)
            subprocess.run(['node','tests/ui_controls_v11.js'],env=env,check=True,timeout=60)
        finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':run()
