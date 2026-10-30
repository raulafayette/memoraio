"""Independent source-scoped oracles, bounded retrieval and resumable textual audits."""
import json
import re
import sys
import time
import unicodedata
import uuid
from .core import Failure,atomic_json

def configure(store,name,purpose,sources,rules='',strategy='hybrid',oid=None):
    if not isinstance(name,str) or not name.strip() or len(name)>200:raise ValueError('Nome inválido')
    if not isinstance(purpose,str) or len(purpose)>4000 or not isinstance(rules,str) or len(rules)>8000:raise ValueError('Descrição ou regras muito longas')
    if strategy not in ('hybrid','literal','semantic'):raise ValueError('Estratégia inválida')
    if not isinstance(sources,list) or not sources or len(sources)>1000:raise ValueError('Escolha ao menos uma fonte')
    oid=oid or uuid.uuid4().hex
    if not re.fullmatch(r'[a-f0-9]{32}',oid):raise ValueError('Identificador de oráculo inválido')
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        for sid in sources:
            if not c.execute('SELECT 1 FROM sources WHERE id=?',(sid,)).fetchone():raise ValueError('Fonte desconhecida')
        previous=c.execute('SELECT value FROM service_state WHERE key=?',('oracle:'+oid,)).fetchone()
        cfg={'id':oid,'name':name.strip(),'purpose':purpose,'rules':rules,'strategy':strategy,'sources':list(dict.fromkeys(sources)),'updated':time.time(),'revision':uuid.uuid4().hex}
        history=json.loads(previous[0]).get('history',[]) if previous else []
        cfg['history']=history+[{'revision':cfg['revision'],'at':cfg['updated']}]
        c.execute('INSERT INTO palaces VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,description=excluded.description',(oid,name.strip(),purpose))
        c.execute('DELETE FROM palace_sources WHERE palace_id=?',(oid,))
        c.executemany('INSERT INTO palace_sources VALUES(?,?)',[(oid,sid) for sid in cfg['sources']])
        folder=store.root/'oracles'/oid/'config';folder.mkdir(parents=True,exist_ok=True)
        atomic_json(folder/(cfg['revision']+'.json'),cfg)
        c.execute('INSERT INTO service_state VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('oracle:'+oid,json.dumps(cfg,ensure_ascii=False)))
        store.event(c,None,'oracle_updated',oid+' '+cfg['revision'])
    return oid

def list_oracles(store):
    with store.connect() as c:
        configs={r['key'][7:]:json.loads(r['value']) for r in c.execute("SELECT key,value FROM service_state WHERE key LIKE 'oracle:%'")}
        result=[]
        for p in c.execute('SELECT * FROM palaces'):
            sources=[r[0] for r in c.execute('SELECT source_id FROM palace_sources WHERE palace_id=?',(p['id'],))]
            result.append(configs.get(p['id'],{'id':p['id'],'name':p['name'],'purpose':p['description'],'sources':sources,'rules':'','strategy':'hybrid','history':[]}))
    return result

def fused(lexical,semantic,limit=30):
    scores={};records={}
    for rows in (lexical,semantic):
        for rank,row in enumerate(rows):
            key=row['id'];scores[key]=scores.get(key,0)+1/(60+rank+1);records[key]=row
    return [{**records[key],'fusion_score':score} for key,score in sorted(scores.items(),key=lambda x:x[1],reverse=True)[:limit]]

def retrieve(store,query,oid,strategy='hybrid',worker=None,job=None):
    lexical=store.search(query,oid) if strategy!='semantic' else []
    semantic=[]
    if strategy!='literal':
        from .semantic import search_semantic
        def heartbeat():
            store.heartbeat(job['id'],worker.owner);store.worker_ping(worker.owner)
        semantic=search_semantic(store,query,oid,runner=(lambda args:worker.run_command(args,job)) if worker else None,progress=heartbeat if worker else None)
    return fused(lexical,semantic)

def context(store,rows,char_budget=18000):
    # Document hierarchy first, then nearby source segments; bounded by actual characters.
    groups={}
    for row in rows:groups.setdefault(row['item_id'],[]).append(row)
    ordered=sorted(groups.values(),key=lambda g:max(x.get('fusion_score',x.get('score',0)) for x in g),reverse=True)
    evidence=[];used=set();remaining=char_budget
    with store.connect() as c:
        for group in ordered:
            for anchor in group[:2]:
                row=c.execute('SELECT s.*,t.sha256,t.path,i.url,i.title FROM segments s JOIN transcripts t ON t.id=s.transcript_id JOIN items i ON i.id=s.item_id WHERE s.id=? AND EXISTS(SELECT 1 FROM active_source_items asi WHERE asi.item_id=i.id)',(anchor['id'],)).fetchone()
                if not row:continue
                nearby=c.execute('SELECT * FROM segments WHERE transcript_id=? AND start>=? AND start<=? ORDER BY start,id',(row['transcript_id'],max(0,row['start']-15),row['end']+15)).fetchall()
                for seg in nearby:
                    if seg['id'] in used:continue
                    text=seg['text'];excerpt=False
                    if len(text)>2400:text=text[:2400];excerpt=True
                    if len(text)+300>remaining:continue
                    evidence.append({'reference':'E'+str(len(evidence)+1),'segment_id':seg['id'],'item_id':row['item_id'],'transcript_id':row['transcript_id'],'transcript_sha256':row['sha256'],'title':row['title'],'url':row['url'],'start':seg['start'],'end':seg['end'],'text':text,'excerpt':excerpt})
                    remaining-=len(text)+300;used.add(seg['id'])
                    if len(evidence)>=12:return evidence
    return evidence

def enqueue_query(store,oid,query,exhaustive=False):
    if not isinstance(query,str) or not query.strip() or len(query)>1000:raise ValueError('Pergunta inválida')
    cfg=next((x for x in list_oracles(store) if x['id']==oid),None)
    if not cfg:raise ValueError('Oráculo desconhecido')
    qid=uuid.uuid4().hex
    with store.connect() as c:
        snapshot=[dict(x) for x in c.execute('SELECT DISTINCT t.id,t.item_id,t.path,t.sha256 FROM transcripts t JOIN active_source_items asi ON asi.item_id=t.item_id JOIN palace_sources ps ON ps.source_id=asi.source_id WHERE ps.palace_id=? AND t.current=1 ORDER BY t.item_id',(oid,))] if exhaustive else None
        total=c.execute('SELECT count(DISTINCT asi.item_id) FROM active_source_items asi JOIN palace_sources ps ON ps.source_id=asi.source_id WHERE ps.palace_id=?',(oid,)).fetchone()[0]
        payload={'id':qid,'oracle':cfg,'query':query,'exhaustive':bool(exhaustive),'snapshot':snapshot,'available_transcripts':len(snapshot) if snapshot is not None else None,'identified_items':total,'created':time.time(),'state':'queued'}
        folder=store.root/'oracles'/'queries'/qid;folder.mkdir(parents=True,exist_ok=True);atomic_json(folder/'request.json',payload)
        jid=store.enqueue(c,'oracle',qid);c.execute('UPDATE jobs SET priority=85 WHERE id=?',(jid,))
    return {'query_id':qid,'job_id':jid}

def fold(text):return ''.join(c for c in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(c)!='Mn')

def exhaustive_step(worker,job,request,folder):
    words=set(re.findall(r'\w+',fold(request['query'])))
    done=0;matches=[];processed=0
    checkpoint=folder/'documents';checkpoint.mkdir(exist_ok=True)
    for row in request['snapshot']:
        path=checkpoint/(row['id']+'.json')
        if path.exists():part=json.loads(path.read_text())
        else:
            if processed>=40:raise Failure('Consulta textual sistemática: checkpoint salvo; próxima etapa','queued')
            hits=[];scanned=0
            with worker.store.connect() as c:
                for seg in c.execute('SELECT id,item_id,start,end,text FROM segments WHERE transcript_id=? ORDER BY id',(row['id'],)):
                    scanned+=1;score=len(words.intersection(re.findall(r'\w+',fold(seg['text']))))
                    if score:hits.append({'id':seg['id'],'item_id':seg['item_id'],'score':score})
            hits=sorted(hits,key=lambda x:x['score'],reverse=True)[:20]
            part={'transcript_id':row['id'],'sha256':row['sha256'],'scanned_segments':scanned,'hits':hits};atomic_json(path,part);processed+=1
            worker.store.heartbeat(job['id'],worker.owner)
        done+=1;matches.extend(part['hits'])
        atomic_json(folder/'progress.json',{'scanned_documents':done,'available_transcripts':len(request['snapshot']),'identified_items':request['identified_items'],'scope':'Todas as transcrições disponíveis no snapshot; correspondência textual, não leitura semântica de todo o acervo'})
    return sorted(matches,key=lambda x:x['score'],reverse=True)[:40]

def run_query(worker,job):
    store=worker.store;folder=store.root/'oracles'/'queries'/job['target'];request=json.loads((folder/'request.json').read_text())
    evidence_file=folder/'evidence.json'
    if evidence_file.exists():evidence=json.loads(evidence_file.read_text())
    else:
        rows=exhaustive_step(worker,job,request,folder) if request['exhaustive'] else retrieve(store,request['query'],request['oracle']['id'],request['oracle']['strategy'],worker,job)
        evidence=context(store,rows);atomic_json(evidence_file,evidence)
    if not evidence:
        result={'state':'done','original_evidence':[],'ai_interpretation':None,'oracle_conclusion':'Não foram localizadas evidências suficientes no conjunto consultado.','generated':False}
    else:
        config=store.root/'oracle-model.json'
        if not config.exists():raise Failure('Modelo local do oráculo não instalado; evidências preservadas','blocked')
        cfg=json.loads(config.read_text());input_file=folder/'generation-input.json'
        atomic_json(input_file,{'oracle':request['oracle'],'query':request['query'],'evidence':evidence,'model':cfg,'max_prompt_tokens':6000,'max_tokens':1200})
        worker.run_command([sys.executable,'-m','memoria.oracle_generate','--input',str(input_file),'--output',str(folder/'generation.json')],job)
        generated=json.loads((folder/'generation.json').read_text());result={'state':'done','original_evidence':evidence,**generated,'generated':True,'model':{k:v for k,v in cfg.items() if k!='path'},'warning':'Interpretação por IA local; citações validadas por identificador, conteúdo não certificado por revisão humana.'}
    result.update(query=request['query'],oracle_id=request['oracle']['id'],oracle_revision=request['oracle'].get('revision'),completed=time.time(),exhaustive=request['exhaustive'])
    atomic_json(folder/'result.json',result)

def query_status(store,qid):
    if not re.fullmatch(r'[a-f0-9]{32}',qid or ''):raise ValueError('Consulta inválida')
    folder=store.root/'oracles'/'queries'/qid
    if not (folder/'request.json').exists():raise ValueError('Consulta desconhecida')
    with store.connect() as c:job=c.execute("SELECT state,error FROM jobs WHERE kind='oracle' AND target=? ORDER BY created DESC LIMIT 1",(qid,)).fetchone()
    out={'query_id':qid,'job':dict(job) if job else None}
    for name in ('progress','result'):
        if (folder/(name+'.json')).exists():out[name]=json.loads((folder/(name+'.json')).read_text())
    return out

def history(store,oid=None):
    entries=[]
    with store.connect() as c:jobs=[dict(x) for x in c.execute("SELECT id,target,state,created,error FROM jobs WHERE kind='oracle' ORDER BY created DESC LIMIT 500")]
    for job in jobs:
        path=store.root/'oracles'/'queries'/job['target']/'request.json'
        if not path.is_file():continue
        request=json.loads(path.read_text())
        if oid and request['oracle']['id']!=oid:continue
        entries.append({'query_id':job['target'],'job_id':job['id'],'state':job['state'],'created':job['created'],'query':request['query'],'oracle_id':request['oracle']['id'],'exhaustive':request['exhaustive']})
        if len(entries)>=50:break
    return entries
