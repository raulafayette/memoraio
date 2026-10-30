"""Local multilingual semantic index; source text and time remain authoritative."""
import array
import json
import os
from pathlib import Path
import subprocess
import sys
from .core import Failure,atomic_json

def model_config(store):
    path=store.root/'semantic-model.json'
    if not path.exists():raise Failure('Modelo semântico ainda não configurado','blocked')
    return json.loads(path.read_text())

def embed_transcript(worker,job):
    store=worker.store;model=model_config(store)
    with store.connect() as c:
        rows=[dict(x) for x in c.execute('SELECT id,text FROM segments WHERE transcript_id=?',(job['target'],))]
    stage=store.root/'temporary'/('embedding-'+job['target']);stage.mkdir(exist_ok=True)
    request=stage/'request.json';output=stage/'vectors.json'
    atomic_json(request,{'model':model['path'],'mode':'passage','texts':[x['text'] for x in rows]})
    worker.run_command([sys.executable,'-m','memoria.semantic','--input',str(request),'--output',str(output)],job)
    vectors=json.loads(output.read_text())
    if len(vectors)!=len(rows):raise Failure('Quantidade de embeddings inválida','failed')
    store.heartbeat(job['id'],worker.owner)
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        for row,vector in zip(rows,vectors):c.execute('INSERT OR REPLACE INTO vectors VALUES(?,?,?)',(row['id'],model['revision'],array.array('f',vector).tobytes()))

def search_semantic(store,query,palace_id=None,source_id=None,runner=None,progress=None):
    if not isinstance(query,str) or not 1<=len(query)<=1000:raise ValueError('Consulta inválida')
    model=model_config(store)
    import tempfile
    with tempfile.TemporaryDirectory(dir=store.root/'temporary') as d:
        request=Path(d)/'query.json';output=Path(d)/'vector.json'
        atomic_json(request,{'model':model['path'],'mode':'query','texts':[query]})
        args=[sys.executable,'-m','memoria.semantic','--input',str(request),'--output',str(output)]
        if runner:runner(args)
        else:subprocess.run(args,check=True,timeout=120,env={**os.environ,'HF_HUB_OFFLINE':'1'})
        q=json.loads(output.read_text())[0]
    sql='''SELECT s.id,s.item_id,s.start,s.end,s.text,i.title,i.url,json_extract(i.metadata,'$.channel') AS channel,t.quality,t.origin,v.vector FROM vectors v
      JOIN segments s ON s.id=v.segment_id JOIN transcripts t ON t.id=s.transcript_id JOIN items i ON i.id=s.item_id WHERE t.current=1 AND v.model=? AND EXISTS(SELECT 1 FROM active_source_items asi WHERE asi.item_id=i.id)'''
    params=[model['revision']]
    if palace_id:sql+=' AND EXISTS(SELECT 1 FROM active_source_items si JOIN palace_sources ps ON ps.source_id=si.source_id WHERE si.item_id=i.id AND ps.palace_id=?)';params.append(palace_id)
    if source_id:sql+=' AND EXISTS(SELECT 1 FROM active_source_items si WHERE si.item_id=i.id AND si.source_id=?)';params.append(source_id)
    import heapq
    import numpy as np
    query_vector=np.asarray(q,dtype=np.float32);best=[]
    last_id=0
    while True:
        # Finish each read before the heartbeat writer: DELETE-mode SQLite readers
        # must not hold a cursor while updating the lease through another connection.
        with store.connect() as c:rows=c.execute(sql+' AND s.id>? ORDER BY s.id LIMIT 2048',[*params,last_id]).fetchall()
        if not rows:break
        last_id=rows[-1]['id']
        if progress:progress()
        valid=[];vectors=[]
        for row in rows:
            v=np.frombuffer(row['vector'],dtype=np.float32)
            if len(v)==len(q):valid.append(row);vectors.append(v)
        if not valid:continue
        scores=np.stack(vectors)@query_vector
        for row,score in zip(valid,scores):
            record={k:row[k] for k in row.keys() if k!='vector'};record['score']=round(float(score),5)
            heapq.heappush(best,(float(score),row['id'],record))
            if len(best)>30:heapq.heappop(best)
    return [x[2] for x in sorted(best,reverse=True)]

def main():
    import argparse
    import torch
    torch.set_num_threads(int(os.environ.get('MEMORIA_CPU_THREADS','2')));torch.set_num_interop_threads(1)
    from sentence_transformers import SentenceTransformer
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    request=json.loads(Path(args.input).read_text())
    model=SentenceTransformer(request['model'],device='cpu',local_files_only=True,trust_remote_code=False)
    prefix='query: ' if request['mode']=='query' else 'passage: '
    # E5 has512 token context; preserving all long segment text for literal search, cap encoder input transparently.
    vectors=model.encode([prefix+x for x in request['texts']],batch_size=16,normalize_embeddings=True,show_progress_bar=False).tolist()
    atomic_json(Path(args.output),vectors)
if __name__=='__main__':main()
