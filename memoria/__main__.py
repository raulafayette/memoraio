import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from .core import Store,hash_file

def main():
    p=argparse.ArgumentParser(description='Memória audiovisual local')
    p.add_argument('--data',default=os.environ.get('MEMORIA_DATA',str(Path(__file__).resolve().parent.parent/'data')))
    sub=p.add_subparsers(dest='command',required=True)
    serve=sub.add_parser('serve');serve.add_argument('--port',type=int,default=8765);serve.add_argument('--open',action='store_true')
    service_parser=sub.add_parser('service');service_parser.add_argument('--port',type=int,default=8765)
    sub.add_parser('setup');sub.add_parser('install-service');sub.add_parser('open-ui');sub.add_parser('bootstrap');
    worker_parser=sub.add_parser('worker');worker_parser.add_argument('--lane',choices=['all','acquire','process','transcript','maintenance','organizer'],default='all');sub.add_parser('backup');sub.add_parser('verify');sub.add_parser('doctor')
    args=p.parse_args();os.umask(0o077)
    store=Store(args.data)
    if args.command=='serve':
        from .server import Server
        with Server(store,args.port) as server:
            url=f'http://127.0.0.1:{server.server_port}/?token={server.token}'
            from .core import atomic_json
            session={'url':url,'pid':os.getpid(),'created':__import__('time').time()}
            atomic_json(store.root/'ui-session.json',session)
            if os.environ.get('MEMORIA_UI_STATE'):
                ui_state=Path(os.environ['MEMORIA_UI_STATE'])
                ui_state.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                atomic_json(ui_state,session)
            print('Serviço local pronto; abra o aplicativo Memoraio.' if os.environ.get('MEMORIA_SERVICE') else 'Abra a biblioteca: '+url,flush=True)
            if args.open:
                import webbrowser
                webbrowser.open(url)
            try:server.serve_forever()
            except KeyboardInterrupt:pass
    elif args.command=='service':
        from .service import service
        service(store,args.port)
    elif args.command=='setup':
        from .setup import setup
        setup(store)
    elif args.command=='install-service':
        from .service import install
        install(store)
    elif args.command=='open-ui':
        from .service import open_ui
        open_ui(store)
    elif args.command=='bootstrap':print(store.bootstrap_official())
    elif args.command=='worker':
        from .worker import Worker
        import signal
        def stop_worker(*_):raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,stop_worker)
        Worker(store,lane=args.lane).run()
    elif args.command=='backup':print(store.backup())
    elif args.command=='doctor':print(json.dumps({'python':sys.version,'sqlite':sqlite3.sqlite_version,'journal':'DELETE + synchronous FULL','data':str(store.root),'free_bytes':shutil.disk_usage(store.root).free,'tools':{x:(str(Path(sys.executable).parent/x) if (Path(sys.executable).parent/x).is_file() else shutil.which(x)) for x in ('yt-dlp','ffprobe','ffmpeg','node')}},indent=2))
    elif args.command=='verify':
        failures=[];checked=0
        with store.connect() as c:
            integrity=c.execute('PRAGMA integrity_check').fetchone()[0]
            for row in c.execute("SELECT * FROM items WHERE status='archived'"):
                path=(store.root/row['path']).resolve()
                if not path.is_relative_to((store.root/'originals').resolve()) or not path.is_file() or hash_file(path)!=row['blob_hash']:failures.append(row['id'])
                checked+=1
        with store.connect() as c:
            for table,idkey,hashkey,allowed in [('audio_assets','item_id','sha256','originals'),('transcripts','id','sha256','transcripts')]:
                for row in c.execute('SELECT * FROM '+table):
                    path=(store.root/row['path']).resolve()
                    if not path.is_relative_to((store.root/allowed).resolve()) or not path.is_file() or hash_file(path)!=row[hashkey]:failures.append(table+':'+row[idkey])
                    checked+=1
        from .preferences import read
        export_directory=read(store)['export_directory']
        library_roots=[store.root/'library']
        if export_directory:library_roots.append(Path(export_directory)/'Memoraio Library')
        for library_root in library_roots:
            if not library_root.is_dir():continue
            for manifest_path in library_root.rglob('current.json'):
                try:
                    manifest=json.loads(manifest_path.read_text());base=manifest_path.parent.resolve()
                    for name,record in manifest['files'].items():
                        target=(base/record['path']).resolve()
                        if name not in ('metadados.json','transcricao.txt') or not target.is_relative_to(base) or not target.is_file() or hash_file(target)!=record['sha256']:failures.append('library:'+manifest['item_id']+':'+name)
                        checked+=1
                except (ValueError,OSError,KeyError,TypeError):failures.append('library_manifest:'+manifest_path.parent.name)
        print(json.dumps({'database':integrity,'checked':checked,'failed':failures}))
        if failures or integrity!='ok':raise SystemExit(1)

if __name__=='__main__':main()
