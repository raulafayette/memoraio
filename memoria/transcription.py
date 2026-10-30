"""Immutable caption/ASR artifacts, timing checks and incremental lexical indexing."""
import fcntl
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import uuid
from .core import Failure, atomic_json, atomic_text, hash_file, safe_metadata, sync_file, sync_directory, durable_mkdir

def parse_json3(payload):
    result=[]
    for event in payload.get('events',[]):
        text=''.join(x.get('utf8','') for x in event.get('segs',[])).strip()
        if text:
            start=event.get('tStartMs',0)/1000;end=start+event.get('dDurationMs',0)/1000
            if end<=start:end=start+.1
            result.append({'start':start,'end':end,'text':text})
    return result

def validate_transcript(segments,duration):
    flags=[];previous=-1;covered=0;right=0;text=[];gaps=[]
    for seg in segments:
        a=seg.get('start');b=seg.get('end');t=seg.get('text','').strip()
        if not isinstance(a,(float,int)) or not isinstance(b,(float,int)) or not math.isfinite(a+b) or a<0 or b<=a or not t:
            return {'quality':'invalid','flags':['Segmento inválido'],'segments':len(segments),'duration':duration}
        if a<previous:flags.append('Segmentos fora de ordem')
        if a-right>90:gaps.append([right,a])
        covered+=max(0,b-max(a,right));right=max(right,b);previous=a;text.append(t)
        if seg.get('avg_logprob',0)<-1:flags.append('Confiança ASR baixa')
        if seg.get('compression_ratio',0)>2.4:flags.append('Repetição suspeita')
    if not text:return {'quality':'invalid','flags':['Nenhum texto reconhecido; não prova ausência de fala'],'duration':duration,'segments':0}
    if duration:
        if right>duration+5:flags.append('Timestamp excede duração')
        if duration-right>max(30,duration*.1):flags.append('Trecho final sem texto: verificar se é silêncio')
        if segments[0]['start']>30:flags.append('Trecho inicial sem texto: verificar se é silêncio')
    if gaps:flags.append('Intervalos internos sem texto superiores a90s: possível silêncio ou omissão')
    normalized=re.findall(r'\w+',' '.join(text).lower())
    if len(normalized)>30 and len(set(normalized))/len(normalized)<.08:flags.append('Vocabulário repetitivo suspeito')
    if duration and duration>120 and len(' '.join(text))<100:flags.append('Pouco texto para a duração')
    return {'quality':'needs_review' if flags else 'structural_pass','flags':list(dict.fromkeys(flags)),'segments':len(segments),'duration':duration,'last_timestamp':right,'text_interval_seconds':round(covered,2),'text_interval_ratio':round(covered/duration,4) if duration else None,'uncovered_intervals':gaps,'human_verified':False,'warning':'Validação automática não certifica integralidade semântica; intervalos sem texto podem ser silêncio.'}

def stamp(seconds,sep=','):
    millis=round(seconds*1000);hours,millis=divmod(millis,3600000);minutes,millis=divmod(millis,60000);secs,millis=divmod(millis,1000)
    return f'{hours:02}:{minutes:02}:{secs:02}{sep}{millis:03}'

def export_transcript(directory,document):
    durable_mkdir(directory)
    atomic_json(directory/'transcript.json',document)
    segments=document['segments']
    from .library import rich_text
    files={'transcript.txt':rich_text(document),
           'transcript.srt':'\n\n'.join(f"{i}\n{stamp(x['start'])} --> {stamp(x['end'])}\n{x['text']}" for i,x in enumerate(segments,1))+'\n',
           'transcript.vtt':'WEBVTT\n\n'+'\n\n'.join(f"{stamp(x['start'],'.')} --> {stamp(x['end'],'.')}\n{x['text']}" for x in segments)+'\n'}
    for name,text in files.items():atomic_text(directory/name,text)

def audio_extension(probe):
    codec=next((s.get('codec_name') for s in probe.get('streams',[]) if s.get('codec_type')=='audio'),None)
    return {'aac':'.m4a','mp3':'.mp3','opus':'.ogg','vorbis':'.ogg','flac':'.flac','pcm_s16le':'.wav'}.get(codec,'.mka')

class Transcriber:
    def __init__(self,worker):self.w=worker;self.s=worker.store
    def language(self,available,original):
        # Only explicit source/original language or common nontranslated pt/en candidates.
        for candidate in (original,(original+'-orig') if original else None,'pt-orig','pt','pt-BR','en-orig','en'):
            if candidate and candidate in available and any(x.get('ext')=='json3' for x in available[candidate]):return candidate
        return None
    def captions(self,item,info,job,directory,automatic=False):
        mapping=info.get('automatic_captions' if automatic else 'subtitles',{})
        language=self.language(mapping,info.get('language'))
        if not language:
            self.s.attempt(item['id'],'automatic_caption' if automatic else 'manual_caption','not_available','Nenhuma legenda json3 elegível no idioma original/pt/en');return None
        dest=directory/('automatic' if automatic else 'manual');dest.mkdir(exist_ok=True)
        origin='automatic_caption' if automatic else 'manual_caption'
        started=time.monotonic()
        try:
            # Reuse the extractor's signed caption URL only in a private temporary request.
            # No second player extraction, no video download, no persistent signed URL.
            track=next(t for t in mapping[language] if t.get('ext')=='json3')
            request=dest/'request.json';target=dest/'source.json3'
            atomic_json(request,{'url':track['url']})
            try:self.w.run_command([sys.executable,'-m','memoria.caption_fetch','--request',str(request),'--output',str(target)],job)
            finally:request.unlink(missing_ok=True)
            files=[target]
            segments=parse_json3(json.loads(files[0].read_text()))
            report=validate_transcript(segments,info.get('duration'))
            self.s.attempt(item['id'],origin,report['quality'],json.dumps({**report,'elapsed_seconds':round(time.monotonic()-started,3),'provider':'yt-dlp caption URL'},ensure_ascii=False))
            return {'segments':segments,'language':language,'origin':origin,'report':report,'model':None}
        except (Failure,ValueError,OSError) as error:
            self.s.attempt(item['id'],origin,getattr(error,'state','failed'),str(error))
            if getattr(error,'state',None)=='rate_limited':raise
            # Audio can still be permitted even when a captions endpoint is rate limited.
            return None
    def audio(self,item,job,format_id=None,temporary=False):
        with self.s.connect() as c:cached=c.execute('SELECT * FROM audio_assets WHERE item_id=?',(item['id'],)).fetchone()
        if cached and not format_id:
            path=(self.s.root/cached['path']).resolve()
            if path.is_relative_to((self.s.root/'originals').resolve()) and path.is_file() and hash_file(path)==cached['sha256']:return dict(cached)
        stage=self.s.root/'temporary'/item['id'];stage.mkdir(exist_ok=True)
        if item.get('path'):
            video=(self.s.root/item['path']).resolve()
            if video.is_relative_to((self.s.root/'originals').resolve()) and video.is_file() and hash_file(video)==item['blob_hash']:
                source_probe=self.w.validate(video,job)
                dest=stage/('audio-reused'+audio_extension(source_probe))
                self.w.run_command([self.w.tool('ffmpeg'),'-nostdin','-y','-v','error','-protocol_whitelist','file,pipe','-i',str(video),'-vn','-codec:a','copy',str(dest)],job)
                output=str(dest)+'\n'
            else:raise Failure('Vídeo arquivado com integridade divergente','blocked')
        elif item['platform']=='instagram':
            if not (stage/'audio.mp4').is_file():
                from .instagram import media_command
                self.w.run_command(media_command(self.s,item,stage/'audio.mp4',audio=True),job)
            output=str(stage/'audio.mp4')+'\n'
        else:
            output=self.w.run_command(self.w.ytdlp()+['--no-playlist','--continue','--part','--max-filesize','1G','--format',format_id or 'ba/b','--output',str(stage/'audio.%(ext)s'),'--print','after_move:filepath','--',item['url']],job)
        lines=[x for x in output.splitlines() if x.strip()]
        if not lines:raise Failure('Áudio não retornado pelo extrator')
        path=Path(lines[-1]).resolve()
        if path.parent!=stage.resolve():raise Failure('Caminho de áudio inválido','failed')
        probe=self.w.validate(path,job)
        if not any(x.get('codec_type')=='audio' for x in probe.get('streams',[])):raise Failure('Mídia não possui stream de áudio; revisão necessária','failed')
        if any(stream.get('codec_type')=='video' for stream in probe.get('streams',[])):
            extracted=stage/('audio-extracted'+audio_extension(probe))
            self.w.run_command([self.w.tool('ffmpeg'),'-nostdin','-y','-v','error','-protocol_whitelist','file,pipe','-i',str(path),'-vn','-codec:a','copy',str(extracted)],job)
            probe=self.w.validate(extracted,job);path.unlink();path=extracted
            self.s.attempt(item['id'],'audio_extract','available','Arquivo recebido continha vídeo; conservada somente a faixa de áudio para esta operação')
        if temporary:
            return {'item_id':item['id'],'path':str(path.relative_to(self.s.root)),'sha256':hash_file(path),'duration':float(probe.get('format',{}).get('duration',0)),'size':path.stat().st_size,'temporary':True}
        digest=hash_file(path);target=self.s.root/'originals'/digest[:2]/(digest+path.suffix);durable_mkdir(target.parent)
        if target.exists():
            if hash_file(target)!=digest:raise Failure('Áudio existente com hash divergente','blocked')
        else:
            with open(path,'rb') as f:sync_file(f.fileno())
            os.replace(path,target);sync_directory(target.parent)
        asset={'item_id':item['id'],'path':str(target.relative_to(self.s.root)),'sha256':digest,'duration':float(probe.get('format',{}).get('duration',0)),'size':target.stat().st_size}
        with self.s.connect() as c:c.execute('INSERT OR REPLACE INTO audio_assets VALUES(:item_id,:path,:sha256,:duration,:size)',asset)
        assets=self.s.root/'metadata'/'assets'/item['id'];assets.mkdir(parents=True,exist_ok=True)
        atomic_json(assets/('audio-'+digest+'.json'),{**asset,'kind':'audio','format_id':format_id,'collected_at':time.time()})
        self.s.attempt(item['id'],'audio','available',json.dumps(asset))
        return asset
    def run(self,job):
        with self.s.connect() as c:item=dict(c.execute('SELECT * FROM items WHERE id=?',(job['target'],)).fetchone())
        from .operations import options
        captions_only=job['kind']!='transcribe_asr' and options(self.s,job['id']).get('captions_only',True)
        if captions_only and item['platform']!='youtube':raise Failure('Legendas indisponíveis para esta fonte no modo econômico; nenhuma mídia baixada','blocked')
        stage=self.s.root/'temporary'/item['id'];stage.mkdir(exist_ok=True)
        lock=open(stage/'.lock','a')
        try:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise Failure('Item ainda pertence a outro processo')
            self.w.lock_fd=lock.fileno()
            tid=uuid.uuid4().hex;directory=self.s.root/'transcripts'/item['id']/tid;directory.mkdir(parents=True)
            with self.s.connect() as c:forced_asset=c.execute('SELECT * FROM audio_assets WHERE item_id=?',(item['id'],)).fetchone() if job['kind']=='transcribe_asr' else None
            if forced_asset:
                forced_path=(self.s.root/forced_asset['path']).resolve()
                if not forced_path.is_relative_to((self.s.root/'originals').resolve()) or not forced_path.is_file() or hash_file(forced_path)!=forced_asset['sha256']:raise Failure('Áudio preservado inválido; não foi feita nova requisição à plataforma','blocked')
                info={**json.loads(item['metadata']),'duration':forced_asset['duration'],'used_archived_metadata':True}
            elif item['platform']=='instagram':
                info={**json.loads(item['metadata']),'title':item['title']}
            else:
                try:info=json.loads(self.w.run_command(self.w.ytdlp()+['--no-playlist','--skip-download','--dump-single-json','--',item['url']],job))
                except Failure as error:
                    self.s.attempt(item['id'],'source_metadata',error.state,str(error))
                    with self.s.connect() as c:preserved=c.execute('SELECT * FROM audio_assets WHERE item_id=?',(item['id'],)).fetchone()
                    if preserved:
                        preserved_path=(self.s.root/preserved['path']).resolve()
                        if not preserved_path.is_relative_to((self.s.root/'originals').resolve()) or not preserved_path.is_file() or hash_file(preserved_path)!=preserved['sha256']:raise
                        info={**json.loads(item['metadata']),'duration':preserved['duration'],'used_archived_metadata':True}
                    elif error.state in ('blocked','needs_auth','rate_limited','deferred'):raise
                    else:info={**json.loads(item['metadata']),'metadata_fetch_failed':True}
            info={**json.loads(item['metadata']),**info}
            if not info.get('metadata_fetch_failed') and not info.get('used_archived_metadata'):info['metadata_collected_at']=time.time()
            info['caption_tracks']={family:list(info.get(key,{})) for family,key in [('manual','subtitles'),('automatic','automatic_captions')]}
            manual=self.captions(item,info,job,directory,False)
            automatic=None if manual and manual['report']['quality']=='structural_pass' else self.captions(item,info,job,directory,True)
            selected=manual if manual and manual['report']['quality']!='invalid' else automatic
            if not selected and item['platform']=='youtube' and job['kind']!='transcribe_asr' and not info.get('used_archived_metadata'):
                try:
                    alternate=directory/'alternative.json'
                    self.w.run_command([sys.executable,'-m','memoria.caption_fetch','--video',item['original_id'],'--language',str(info.get('language') or ''),'--output',str(alternate)],job)
                    result=json.loads(alternate.read_text());report=validate_transcript(result['segments'],info.get('duration'))
                    self.s.attempt(item['id'],'youtube-transcript-api',report['quality'],'Sem áudio/vídeo transferido')
                    if report['quality']!='invalid':selected={**result,'report':report,'model':None}
                except Failure as error:
                    self.s.attempt(item['id'],'youtube-transcript-api',error.state,str(error))
                    if error.state in ('rate_limited','blocked','needs_auth'):raise
            duration=info.get('duration')
            if captions_only and not selected:raise Failure('Sem legenda disponível no modo econômico; nenhum vídeo ou áudio baixado','blocked')
            if not captions_only and (job['kind']=='transcribe_asr' or not selected or selected['report']['quality'] in ('invalid','needs_review') or (duration and duration>120 and len(' '.join(x['text'] for x in selected['segments']))<100)):
                asset=self.audio(item,job,temporary=item['platform']=='instagram')
                from .temporary import prepare
                prepare(self.s,item['id'],asset)
                model_file=self.s.root/'asr-model.json'
                if not model_file.exists():raise Failure('Modelo ASR local não configurado; áudio preservado','blocked')
                model=json.loads(model_file.read_text())
                destination=stage/'asr';destination.mkdir(exist_ok=True)
                args=[sys.executable,'-m','memoria.asr','--audio',str(self.s.root/asset['path']),'--output',str(destination),'--model',model['path'],'--revision',model['revision'],'--hash',asset['sha256']]
                self.w.run_command(args,job)
                result=json.loads((destination/'result.json').read_text())
                segments=result['segments'];duration=asset['duration'] or duration
                report=validate_transcript(segments,duration)
                if report['quality']=='invalid':
                    self.s.attempt(item['id'],'local_asr','needs_review',json.dumps(report,ensure_ascii=False))
                    raise Failure('ASR não produziu texto estruturalmente válido; áudio e checkpoints preservados','failed')
                selected={'segments':segments,'language':result.get('language'),'origin':'local_asr','model':result['model'],'report':report}
                self.s.attempt(item['id'],'local_asr',report['quality'],json.dumps(report,ensure_ascii=False))
            if selected['origin']=='local_asr' and (manual or automatic):
                compare_input=stage/'compare-input.json';compare_output=stage/'compare-result.json'
                atomic_json(compare_input,{'original':(manual or automatic)['segments'],'recognized':selected['segments']})
                self.w.run_command([sys.executable,'-m','memoria.speech_compare','--input',str(compare_input),'--output',str(compare_output)],job)
                comparison=json.loads(compare_output.read_text());disagreement=comparison['weighted_disagreement']
                selected['report']['caption_asr_comparison']=comparison
                selected['report']['caption_asr_disagreement']=disagreement
                if disagreement is None or disagreement>.12 or comparison['uncompared_windows']:
                    selected['report']['quality']='needs_review';selected['report']['flags'].append('Divergência ou comparação incompleta entre legenda e ASR: revisar diferenças')
            if selected['origin']=='local_asr':
                audit_input=stage/'audit-input.json';audit_output=stage/'speech-audit.json'
                atomic_json(audit_input,{'segments':selected['segments']})
                self.w.run_command([sys.executable,'-m','memoria.speech_audit','--audio',str(self.s.root/asset['path']),'--transcript',str(audit_input),'--output',str(audit_output)],job)
                vad=json.loads(audit_output.read_text());selected['report']['speech_audit']=vad
                if (vad.get('uncovered_speech_ratio') or 0)>.08 or vad['uncovered_speech_seconds']>15:
                    selected['report']['quality']='needs_review';selected['report']['flags'].append('Fala detectada sem sobreposição suficiente de texto')
            document={'id':tid,'item_id':item['id'],'url':item['url'],'title':info.get('title') or item['title'],'channel':info.get('channel'),'created':time.time(),'duration':duration,'origin':selected['origin'],'language':selected.get('language'),'model':selected.get('model'),'validation':selected['report'],'segments':selected['segments']}
            import importlib.metadata
            document['source_files']=[{'path':str(p.relative_to(self.s.root)),'sha256':hash_file(p),'size':p.stat().st_size,'kind':'original_caption'} for p in directory.rglob('*') if p.is_file() and p.name!='request.json']
            document['provider_version']=selected.get('provider_version') or importlib.metadata.version('mlx-whisper' if selected['origin']=='local_asr' else 'yt-dlp')
            document['configuration']=selected.get('model') or {'translation':False,'caption_language_selection':'original, pt, en','validation':'structural'}
            from .library import enrich
            document=enrich(self.s,item,{**document,'provider':selected.get('provider','yt-dlp' if selected['origin']!='local_asr' else 'mlx-whisper'),'provider_version':document['provider_version']},info)
            export_transcript(directory,document)
            path=directory/'transcript.json';digest=hash_file(path)
            self.s.heartbeat(job['id'],self.w.owner)
            with self.s.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                if not c.execute("SELECT id FROM jobs WHERE id=? AND owner=? AND state='running' AND control IS NULL",(job['id'],self.w.owner)).fetchone():raise Failure('Lease perdido na publicação')
                c.execute('UPDATE transcripts SET current=0 WHERE item_id=?',(item['id'],))
                c.execute('INSERT INTO transcripts VALUES(?,?,?,?,?,?,?,?,?,?,1)',(tid,item['id'],time.time(),selected['origin'],selected.get('language'),json.dumps(selected.get('model')),str(path.relative_to(self.s.root)),digest,selected['report']['quality'],json.dumps(selected['report'],ensure_ascii=False)))
                for seg in selected['segments']:
                    cursor=c.execute('INSERT INTO segments(transcript_id,item_id,start,end,text) VALUES(?,?,?,?,?)',(tid,item['id'],seg['start'],seg['end'],seg['text']))
                    c.execute('INSERT INTO transcript_fts(rowid,text) VALUES(?,?)',(cursor.lastrowid,seg['text']))
                c.execute('UPDATE items SET title=?,metadata=? WHERE id=?',(document['title'],json.dumps({**json.loads(item['metadata']),**{k:v for k,v in safe_metadata(info).items() if v is not None},'duration':duration,'channel':info.get('channel'),'language':info.get('language')},ensure_ascii=False),item['id']))
                export_job=self.s.enqueue(c,'export',item['id']);c.execute('UPDATE jobs SET priority=80 WHERE id=?',(export_job,))
                if (self.s.root/'semantic-model.json').exists():
                    embedding_job=self.s.enqueue(c,'embed',tid);c.execute('UPDATE jobs SET priority=95 WHERE id=?',(embedding_job,))
            self.s.attempt(item['id'],'publish','done',tid)
        except Exception as error:
            self.s.attempt(item['id'],'pipeline',getattr(error,'state','retry'),str(error));raise
        finally:self.w.lock_fd=None;lock.close()
