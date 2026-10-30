"""Instagram public/session-authorized inventory and bounded media transfer."""
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from .core import Failure,sync_file,sync_directory


def session_args(store):
    p=store.root/'instagram-session.json'
    return ['--session',str(p)] if p.is_file() else []

def entries(post,profile='',kind='posts'):
    nodes=list(post.get_sidecar_nodes()) if post.typename=='GraphSidecar' else [post]
    caption=post.caption or ''
    for index,node in enumerate(nodes,1):
        if not node.is_video:continue
        yield {'id':post.shortcode+'_'+str(index),'title':(' '.join(caption.split())[:180] or 'Instagram '+post.shortcode),'description':caption,'webpage_url':'https://www.instagram.com/p/'+post.shortcode+'/','channel':profile or post.owner_username,'upload_date':post.date_utc.strftime('%Y%m%d'),'timestamp':post.date_utc.replace(tzinfo=__import__('datetime').timezone.utc).timestamp(),'instagram_shortcode':post.shortcode,'instagram_child':index,'instagram_kind':kind,'duration':getattr(node,'video_duration',None)}

def story_entry(item,profile='',highlight_id=None,title=None):
    if not item.is_video:return None
    owner=profile or item.owner_username
    mediaid=str(item.mediaid);date=item.date_utc
    return {'id':'story_'+mediaid,'title':title or ('Story '+owner+' · '+date.strftime('%d/%m/%Y %H:%M')),'description':'Vídeo de destaque' if highlight_id else 'Vídeo de story','webpage_url':('https://www.instagram.com/stories/highlights/'+str(highlight_id)+'/') if highlight_id else ('https://www.instagram.com/stories/'+owner+'/'+mediaid+'/'),'channel':owner,'upload_date':date.strftime('%Y%m%d'),'timestamp':date.replace(tzinfo=__import__('datetime').timezone.utc).timestamp(),'instagram_kind':'highlights' if highlight_id else 'stories','instagram_media_id':mediaid,'instagram_owner_id':str(item.owner_id),'instagram_highlight_id':str(highlight_id) if highlight_id else None}

def media_command(store,item,output,audio=False):
    meta=json.loads(item['metadata']) if isinstance(item['metadata'],str) else item['metadata']
    command=[sys.executable,'-m','memoria.instagram',*session_args(store),'--output',str(output)]
    if audio:command.append('--audio')
    if meta.get('instagram_media_id'):
        command+=['--media-id',str(meta['instagram_media_id']),'--owner',str(meta.get('instagram_owner_id') or meta.get('channel') or '')]
        if meta.get('instagram_highlight_id'):command+=['--highlight',str(meta['instagram_highlight_id'])]
    else:command+=['--shortcode',meta.get('instagram_shortcode') or item['original_id'].rsplit('_',1)[0],'--child',str(meta.get('instagram_child') or item['original_id'].rsplit('_',1)[1])]
    return command

def enumerate_instagram(worker,job,method,consume):
    from .sync import SyncEngine
    root=method['url'].split('#')[0]
    command=[sys.executable,'-m','memoria.instagram',*session_args(worker.store)]
    if method['method']=='instagram_direct':
        parts=urlsplit(root).path.strip('/').split('/')
        if parts[0]=='stories':
            if len(parts)>2 and parts[1]=='highlights':command+=['--highlight',parts[2]]
            elif len(parts)>2:command+=['--media-id',parts[2],'--owner',parts[1]]
            else:command+=['--profile',parts[1],'--kind','stories']
        else:command+=['--post',parts[-1]]
    else:
        kind=method['method'].removeprefix('instagram_')
        if kind not in ('posts','reels','stories','highlights'):kind='posts'
        command+=['--profile',root.rstrip('/').split('/')[-1],'--kind',kind,'--checkpoint',str(worker.store.root/'temporary'/('instagram-'+method['id']+'.json.xz'))]
    return SyncEngine(worker).stream(command,job,consume,timeout=min(600,worker.timeout))

def allowed_media(url):
    try:
        p=urlsplit(url);host=(p.hostname or '').lower()
        return p.scheme=='https' and not p.username and not p.password and p.port in (None,443) and any(host==d or host.endswith('.'+d) for d in ('cdninstagram.com','fbcdn.net','instagram.com'))
    except (ValueError,TypeError):return False

def audio_url(node):
    import xml.etree.ElementTree as ET
    meta=getattr(node,'_node',{}) or {}
    manifest=meta.get('video_dash_manifest') or (meta.get('dash_info') or {}).get('video_dash_manifest')
    if not manifest:return None
    try:
        root=ET.fromstring(manifest)
        for group in root.iter():
            mime=group.attrib.get('mimeType','');content=group.attrib.get('contentType','')
            if not (mime.startswith('audio/') or content=='audio'):continue
            for child in group.iter():
                if child.tag.rsplit('}',1)[-1]=='BaseURL' and child.text and allowed_media(child.text):return child.text
    except (ET.ParseError,TypeError):pass
    return None

def transfer(url,destination,session=None):
    """Never persist signed URLs; resume partial data only after validating Range."""
    import os
    import requests
    destination=Path(destination);partial=destination.with_suffix(destination.suffix+'.part')
    offset=partial.stat().st_size if partial.exists() else 0
    client=session or requests.Session();response=None
    try:
        for _ in range(4):
            if not allowed_media(url):raise Failure('CDN Instagram inesperada','blocked')
            response=client.get(url,headers={'Range':'bytes='+str(offset)+'-'} if offset else {},stream=True,timeout=(15,30),allow_redirects=False)
            if response.status_code in (301,302,303,307,308):
                from urllib.parse import urljoin
                url=urljoin(url,response.headers.get('Location',''));response.close();continue
            if response.status_code==416 and offset and response.headers.get('Content-Range')=='bytes */'+str(offset):
                response.close()
                with partial.open('rb') as f:sync_file(f.fileno())
                os.replace(partial,destination);sync_directory(destination.parent);return
            response.raise_for_status();break
        if response is None or response.is_redirect:raise Failure('Redirecionamentos excedidos','blocked')
        resume=offset>0 and response.status_code==206
        if response.status_code==206:
            match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+|\*)',response.headers.get('Content-Range',''))
            if not match or int(match[1])!=(offset if resume else 0):raise Failure('Range de mídia inconsistente','failed')
        expected=int(response.headers.get('Content-Length','0'))
        if expected+(offset if resume else 0)>1024**3:raise Failure('Mídia Instagram excede limite de 1 GiB','blocked')
        received=0
        with response,partial.open('ab' if resume else 'wb') as f:
            for chunk in response.iter_content(1024*1024):
                if chunk:f.write(chunk);received+=len(chunk)
                if f.tell()>1024**3:raise Failure('Mídia Instagram excede limite de 1 GiB','blocked')
            if expected and received!=expected:raise Failure('Transferência incompleta; parcial preservado')
            f.flush();sync_file(f.fileno())
        os.replace(partial,destination);sync_directory(destination.parent)
    finally:
        if response is not None:response.close()
        if session is None:client.close()

def download_post(loader,args):
    import instaloader
    post=instaloader.Post.from_shortcode(loader.context,args.shortcode)
    nodes=list(post.get_sidecar_nodes()) if post.typename=='GraphSidecar' else [post]
    if not 1<=args.child<=len(nodes) or not nodes[args.child-1].is_video:raise Failure('Filho selecionado não é vídeo acessível','failed')
    node=nodes[args.child-1];audio=audio_url(node) if args.audio else None
    transfer(audio or node.video_url,Path(args.output))
    info=next(x for x in entries(post,post.owner_username) if x['instagram_child']==args.child)
    info.update(path=str(args.output),duration=None,received_media='audio' if audio else 'combined_video')
    print(json.dumps(info,ensure_ascii=False),flush=True)

def loader_for(session=None):
    import instaloader
    class StopOnLimit(instaloader.RateController):
        def handle_429(self,query_type):raise instaloader.exceptions.TooManyRequestsException('429: limite da plataforma')
    loader=instaloader.Instaloader(rate_controller=lambda c:StopOnLimit(c),download_pictures=False,download_videos=False,download_video_thumbnails=False,download_geotags=False,save_metadata=False,max_connection_attempts=1,request_timeout=30)
    if session:
        cfg=json.loads(Path(session).read_text())
        cookies=cfg['cookies']
        if not isinstance(cookies,dict) or not cookies.get('sessionid') or not cookies.get('csrftoken'):raise Failure('Sessão Instagram inválida','needs_auth')
        loader.context.load_session(str(cfg.get('username') or cookies.get('ds_user_id') or 'instagram'),cookies)
    return loader

def main():
    import argparse
    import instaloader
    p=argparse.ArgumentParser();p.add_argument('--profile');p.add_argument('--post');p.add_argument('--checkpoint');p.add_argument('--shortcode');p.add_argument('--child',type=int,default=1);p.add_argument('--output');p.add_argument('--kind',choices=('posts','reels','stories','highlights'),default='posts');p.add_argument('--audio',action='store_true');p.add_argument('--session');p.add_argument('--media-id');p.add_argument('--owner');p.add_argument('--highlight');p.add_argument('--limit',type=int,default=100);args=p.parse_args()
    loader=loader_for(args.session)
    try:
        if args.media_id:
            item=resolve_story(loader,args)
            if args.output:download_story(loader,args,item)
            else:
                entry=story_entry(item,highlight_id=args.highlight)
                if entry:print(json.dumps(entry,ensure_ascii=False),flush=True)
            return
        if args.highlight and not args.profile:
            for item,title in direct_highlight(loader,args.highlight):
                entry=story_entry(item,highlight_id=args.highlight,title=title)
                if entry:print(json.dumps(entry,ensure_ascii=False),flush=True)
            return
        if args.shortcode:download_post(loader,args);return
        if args.post:
            post=instaloader.Post.from_shortcode(loader.context,args.post)
            for entry in entries(post):print(json.dumps(entry,ensure_ascii=False),flush=True)
            return
        profile=instaloader.Profile.from_username(loader.context,args.profile)
        print(json.dumps({'_profile':True,'id':profile.userid,'name':profile.username,'publications':profile.mediacount,'private':profile.is_private}),flush=True)
        if args.kind in ('stories','highlights'):
            require_login(loader)
            if args.kind=='stories':
                for group in loader.get_stories(userids=[profile.userid]):
                    for item in group.get_items():
                        entry=story_entry(item,profile.username)
                        if entry:print(json.dumps(entry,ensure_ascii=False),flush=True)
            else:
                for highlight in loader.get_highlights(profile):
                    for item in highlight.get_items():
                        entry=story_entry(item,profile.username,highlight.unique_id,highlight.title)
                        if entry:print(json.dumps(entry,ensure_ascii=False),flush=True)
            return
        iterator=profile.get_reels() if args.kind=='reels' else profile.get_posts()
        checkpoint=Path(args.checkpoint) if args.checkpoint else None
        if checkpoint and checkpoint.exists():
            try:iterator.thaw(instaloader.load_structure_from_file(loader.context,str(checkpoint)))
            except (ValueError,OSError,EOFError,__import__('lzma').LZMAError,instaloader.exceptions.InstaloaderException):checkpoint.unlink(missing_ok=True)
        for count,post in enumerate(iterator,1):
            for entry in entries(post,args.profile,args.kind):print(json.dumps(entry,ensure_ascii=False),flush=True)
            if checkpoint:
                temporary=checkpoint.with_name(checkpoint.name+'.tmp.xz');instaloader.save_structure_to_file(iterator.freeze(),str(temporary))
                with temporary.open('rb') as f:sync_file(f.fileno())
                __import__('os').replace(temporary,checkpoint.with_name(checkpoint.name+'.pending.xz'));sync_directory(checkpoint.parent)
            if count>=args.limit:print(json.dumps({'_checkpoint':True,'more':True}),flush=True);return
        # The parent commits the pending cursor only after all emitted entries are durable.
    except instaloader.exceptions.InstaloaderException as error:
        print('AUTH_OR_ACCESS: '+str(error),file=sys.stderr);raise SystemExit(2)


def connection_status(store):
    from .preferences import read
    return {'configured':(store.root/'instagram-session.json').is_file(),'asr_ready':(store.root/'asr-model.json').is_file(),'asr_enabled':read(store)['instagram_asr']}

def save_session(store,data):
    from .core import atomic_json
    import time
    cookies=data.get('cookies')
    allowed={'sessionid','csrftoken','ds_user_id'}
    if not isinstance(cookies,dict) or set(cookies)-allowed or not cookies.get('sessionid') or not cookies.get('csrftoken'):raise ValueError('Entre na conta do Instagram antes de usar esta sessão')
    for value in cookies.values():
        if not isinstance(value,str) or not 0<len(value)<=8192 or any(ord(c)<32 for c in value):raise ValueError('Sessão inválida')
    atomic_json(store.root/'instagram-session.json',{'cookies':cookies,'connected_at':time.time()})
    return connection_status(store)

def disconnect(store):
    (store.root/'instagram-session.json').unlink(missing_ok=True)
    from .channels import control
    with store.connect() as c:sources=[r[0] for r in c.execute("SELECT id FROM sources WHERE platform='instagram'")]
    for sid in sources:control(store,sid,'pause')
    with store.connect() as c:jobs=[r[0] for r in c.execute("SELECT j.id FROM jobs j JOIN job_platform p ON p.id=j.id WHERE p.platform='instagram' AND j.state IN ('queued','retry','running')")]
    for jid in jobs:store.control(jid,'pause')
    return connection_status(store)


def require_login(loader):
    if not loader.context.is_logged_in:raise Failure('LOGIN_REQUIRED: Conecte sua conta para stories e destaques','needs_auth')

def direct_highlight(loader,highlight_id):
    require_login(loader)
    data=loader.context.graphql_query('45246d3fe16ccc6577e0bd297a5db1ab',{'reel_ids':[],'tag_names':[],'location_ids':[],'highlight_reel_ids':[str(highlight_id)],'precomposed_overlay':False})
    groups=data.get('data',{}).get('reels_media',[])
    for group in groups:
        import instaloader
        owner=group.get('owner') or group.get('user')
        if not owner:raise Failure('Use o link do perfil e escolha Destaques','blocked')
        profile=instaloader.Profile(loader.context,owner)
        for node in group.get('items',[]):yield instaloader.StoryItem(loader.context,node,profile),group.get('title') or 'Destaque'

def resolve_story(loader,args):
    require_login(loader)
    import instaloader
    if args.highlight:
        for item,_ in direct_highlight(loader,args.highlight):
            if str(item.mediaid)==str(args.media_id):return item
    elif args.owner:
        owner=int(args.owner) if args.owner.isdigit() else instaloader.Profile.from_username(loader.context,args.owner).userid
        for group in loader.get_stories(userids=[owner]):
            for item in group.get_items():
                if str(item.mediaid)==str(args.media_id):return item
    else:return instaloader.StoryItem.from_mediaid(loader.context,int(args.media_id))
    raise Failure('Story não está mais disponível para esta conta','failed')

def download_story(loader,args,item):
    if not item.is_video:raise Failure('Este story não é um vídeo','failed')
    audio=audio_url(item) if args.audio else None
    transfer(audio or item.video_url,Path(args.output))
    info=story_entry(item,highlight_id=args.highlight);info.update(path=str(args.output),received_media='audio' if audio else 'combined_video');print(json.dumps(info,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
