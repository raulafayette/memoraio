"""Record the real interface against disposable synthetic data; no provider workers."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid
from memoria.core import Store, atomic_json, hash_file
from memoria.exports import register_channel
from memoria.library import publish_library
from memoria.channels import link_files
from memoria.server import Server


def seed(store):
    sid = store.register_source('https://youtube.com/@memoraio_fixture_a', 'Canal de exemplo A', queue_paused=True)
    register_channel(store, 'https://youtube.com/@memoraio_fixture_b', 'Canal de exemplo B')
    register_channel(store, 'https://www.instagram.com/memoraio_fixture_c/', 'Perfil de exemplo C')
    store.ingest(sid, [{'id': 'demo0000001', 'title': 'Exemplo fictício: organizar referências', 'duration': 8}, {'id': 'demo0000002', 'title': 'Exemplo fictício: uma nova conversa', 'duration': 8}, {'id': 'demo0000003', 'title': 'Exemplo fictício: revisão do acervo', 'duration': 8}])
    iid = 'youtube_demo0000001'
    tid = uuid.uuid4().hex
    path = store.root / 'transcripts' / iid / tid / 'transcript.json'
    path.parent.mkdir(parents=True)
    atomic_json(path, {'id': tid, 'segments': [{'start': 0, 'end': 8, 'text': 'Este texto foi escrito exclusivamente para uma demonstração fictícia do Memoraio. Nenhum vídeo real foi transcrito. Você pode consultar referências e continuar de onde parou.'}], 'origin': 'manual_caption', 'duration': 8})
    with store.connect() as conn:
        conn.execute('INSERT INTO transcripts VALUES(?,?,?,?,?,?,?,?,?,?,1)', (tid, iid, time.time(), 'manual_caption', 'pt', 'null', str(path.relative_to(store.root)), hash_file(path), 'structural_pass', '{}'))
    publish_library(store, iid)
    link_files(store, iid)
    return sid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit('Escolha uma pasta vazia para os artefatos da demonstração.')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='memoraio-demo-fiction-', dir='/private/tmp' if Path('/private/tmp').is_dir() else '/tmp') as temp:
        store = Store(temp)
        source = seed(store)
        server = Server(store, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = {**os.environ, 'DEMO_URL': f'http://127.0.0.1:{server.server_port}/?token={server.token}', 'DEMO_OUTPUT': str(output), 'DEMO_SOURCE': source}
            script = Path(__file__).with_name('demo.js')
            subprocess.run(['node', str(script)], env=env, check=True, timeout=120)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    recording = next(output.glob('*.webm'))
    movie = output / 'memoraio-demo-sintetica.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(recording), '-an', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '24', '-preset', 'fast', '-movflags', '+faststart', str(movie)], check=True)
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-of', 'json', str(movie)]))
    manifest = {'synthetic': True, 'personal_data_used': False, 'provider_requests_started': False, 'progress': 'simulated and labeled', 'interface': 'actual local application against disposable fixtures', 'duration_seconds': round(float(probe['format']['duration']), 2), 'video_sha256': hash_file(movie), 'video_file': movie.name, 'poster_sha256': hash_file(output / 'memoraio-demo-sintetica.png'), 'recording_has_no_browser_chrome': True}
    (output / 'demo-provenance.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'demo': 'generated', 'duration_seconds': manifest['duration_seconds'], 'synthetic': True}))


if __name__ == '__main__':
    main()
