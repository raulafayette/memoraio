from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest
from memoria.core import Store,Failure,atomic_json,hash_file,canonical
from memoria.channels import start,advance,status,refresh_catalog
from memoria.instagram import entries,allowed_media,audio_url,transfer
from memoria.preferences import save,read
from memoria.sync import SyncEngine
from memoria.worker import Worker
from memoria.operations import options
from memoria.transcription import export_transcript
from memoria.temporary import prepare,cleanup

class Node:
    def __init__(self,video=True):self.is_video=video
class Post:
    shortcode='Fixture';typename='GraphSidecar';caption='Descrição do post, não a fala';owner_username='example';date_utc=datetime(2026,10,29,tzinfo=timezone.utc)
    def get_sidecar_nodes(self):return [Node(False),Node(),Node()]

class InstagramIntegration(unittest.TestCase):
    def test_carousel_keeps_child_identity_and_does_not_treat_description_as_speech(self):
        rows=list(entries(Post(),'example'));self.assertEqual([r['id'] for r in rows],['Fixture_2','Fixture_3']);self.assertEqual(rows[0]['instagram_child'],2);self.assertNotIn('segments',rows[0]);self.assertEqual(rows[0]['description'],Post.caption)
    def test_cdn_rules_and_audio_only_manifest(self):
        for url in ['http://cdninstagram.com/a','https://user@cdninstagram.com/a','https://cdninstagram.com.evil.test/a','https://127.0.0.1/a']:self.assertFalse(allowed_media(url))
        self.assertTrue(allowed_media('https://a.cdninstagram.com/a'))
        node=Node();node._node={'video_dash_manifest':'<MPD><Period><AdaptationSet mimeType="audio/mp4"><Representation><BaseURL>https://a.cdninstagram.com/audio.m4a</BaseURL></Representation></AdaptationSet></Period></MPD>'}
        self.assertEqual(audio_url(node),'https://a.cdninstagram.com/audio.m4a')
        self.assertEqual(canonical('https://www.instagram.com/reels/Fixture/'),'https://www.instagram.com/reel/Fixture/')
    def test_profile_scope_plans_local_asr_only_for_instagram(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);sid=s.register_source('https://instagram.com/example/','Instagram teste')
            self.assertRaises(ValueError,start,s,sid)
            save(s,{'instagram_asr':True});atomic_json(s.root/'asr-model.json',{'repo':'test'})
            start(s,sid,scope='reels');w=Worker(s,reserve=0);job=s.claim(w.owner,kinds=('sync',));SyncEngine(w).start(job);s.finish(job,w.owner)
            with s.connect() as c:
                self.assertEqual([r[0] for r in c.execute('SELECT method FROM scan_methods')],['instagram_reels']);rid=c.execute('SELECT id FROM scan_runs').fetchone()[0];mid=c.execute('SELECT id FROM scan_methods').fetchone()[0]
            iid=s.observe(rid,list(entries(Post()))[0],'instagram')
            with s.connect() as c:
                c.execute('INSERT INTO method_items VALUES(?,?)',(mid,iid));c.execute("UPDATE scan_runs SET state='enumerated_accessible'");c.execute("UPDATE jobs SET state='done' WHERE kind='enumerate'")
            advance(s)
            with s.connect() as c:j=c.execute("SELECT id FROM jobs WHERE kind='transcribe'").fetchone()
            self.assertFalse(options(s,j[0])['captions_only']);self.assertEqual(status(s)['channels'][0]['platform'],'instagram')
    def test_counting_never_enqueues_captions_or_recursive_playlists(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);sid=s.register_source('https://youtube.com/@fixture');jid=refresh_catalog(s,sid);w=Worker(s,reserve=0);job=s.claim(w.owner);self.assertEqual(job['id'],jid);SyncEngine(w).start(job)
            with s.connect() as c:
                self.assertEqual({r[0] for r in c.execute('SELECT method FROM scan_methods')},{'youtube_identity','youtube_videos','youtube_shorts','youtube_streams'})
                self.assertEqual(c.execute("SELECT count(*) FROM jobs WHERE kind IN ('transcribe','download','audio')").fetchone()[0],0);self.assertEqual(c.execute('SELECT count(*) FROM channel_sessions').fetchone()[0],0)
            self.assertEqual(status(s)['channels'][0]['catalog_state'],'counting')
    def test_display_totals_are_local_counts_not_guessed_platform_totals(self):
        from tests.test_channels_v5 import fixture,publish,A,B
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);sid,_=fixture(s);s.ingest(sid,[{'id':A},{'id':B}]);publish(s,'youtube_'+A);c=status(s)['channels'][0]
            self.assertEqual((c['ready'],c['identified'],c['remaining']),(1,2,1));self.assertNotEqual(c['catalog_state'],'complete')
    def test_theme_and_authorization_settings_survive_restart(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);save(s,{'theme':'dark','instagram_asr':True});save(s,{'theme':'light'});p=read(Store(d));self.assertEqual(p['theme'],'light');self.assertTrue(p['instagram_asr']);self.assertRaises(ValueError,save,s,{'theme':'green'})

class Response:
    is_redirect=False
    def __init__(self,body,headers,status=200):self.body=body;self.headers=headers;self.status_code=status
    def raise_for_status(self):pass
    def iter_content(self,_):yield self.body
    def close(self):pass
    def __enter__(self):return self
    def __exit__(self,*_):pass
class Client:
    def __init__(self,responses):self.responses=iter(responses);self.requests=[]
    def get(self,url,**kwargs):self.requests.append(kwargs);return next(self.responses)

class TransferSafety(unittest.TestCase):
    def test_incomplete_transfer_is_not_promoted_and_resumes_exact_offset(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'video.mp4';client=Client([Response(b'abc',{'Content-Length':'6'}),Response(b'def',{'Content-Length':'3','Content-Range':'bytes 3-5/6'},206)])
            self.assertRaises(Failure,transfer,'https://a.cdninstagram.com/video',p,client)
            self.assertFalse(p.exists());self.assertEqual(p.with_suffix('.mp4.part').read_bytes(),b'abc')
            transfer('https://a.cdninstagram.com/video',p,client);self.assertEqual(p.read_bytes(),b'abcdef');self.assertEqual(client.requests[1]['headers']['Range'],'bytes=3-')
    def test_invalid_range_keeps_the_existing_partial(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'v.mp4';p.with_suffix('.mp4.part').write_bytes(b'abc');client=Client([Response(b'xx',{'Content-Length':'2','Content-Range':'bytes 0-1/6'},206)])
            self.assertRaises(Failure,transfer,'https://a.cdninstagram.com/v',p,client);self.assertEqual(p.with_suffix('.mp4.part').read_bytes(),b'abc');self.assertFalse(p.exists())

class TemporaryMedia(unittest.TestCase):
    def test_audio_survives_failure_then_is_removed_after_validated_publication_and_restart(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);sid=s.register_source('https://youtube.com/@fixture');s.ingest(sid,[{'id':'BaW_jenozKc'}]);iid='youtube_BaW_jenozKc';stage=s.root/'temporary'/iid;stage.mkdir();audio=stage/'audio.m4a';audio.write_bytes(b'controlled audio')
            digest=hash_file(audio);prepare(s,iid,{'temporary':True,'path':str(audio.relative_to(s.root)),'sha256':digest});cleanup(Store(d));self.assertTrue(audio.exists())
            doc={'id':'t','segments':[{'start':0,'end':1,'text':'Fala real reconhecida'}],'model':{'audio_sha256':digest},'origin':'local_asr'};directory=s.root/'transcripts'/iid/'t';export_transcript(directory,doc);path=directory/'transcript.json'
            with s.connect() as c:c.execute('INSERT INTO transcripts VALUES(?,?,?,?,?,?,?,?,?,?,1)',('t',iid,1,'local_asr','pt','{}',str(path.relative_to(s.root)),hash_file(path),'structural_pass','{}'))
            cleanup(Store(d));self.assertFalse(audio.exists())
            with s.connect() as c:self.assertEqual(c.execute("SELECT count(*) FROM service_state WHERE key LIKE 'temporary_cleanup:%'").fetchone()[0],0)
    def test_path_outside_the_temporary_item_folder_is_never_deleted(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);p=s.root/'originals'/'keep.m4a';p.write_bytes(b'keep')
            with s.connect() as c:c.execute('INSERT INTO service_state VALUES(?,?)',('temporary_cleanup:any',json.dumps({'item_id':'any','path':str(p.relative_to(s.root)),'sha256':hash_file(p),'at':0})))
            cleanup(s);self.assertTrue(p.exists())


class AuthenticatedStories(unittest.TestCase):
    def test_story_identity_and_media_command_keep_explicit_owner_and_highlight(self):
        from memoria.instagram import story_entry,media_command
        item=type('Story',(),{'is_video':True,'owner_username':'example','owner_id':123,'mediaid':987,'date_utc':datetime(2026,10,29,tzinfo=timezone.utc)})()
        row=story_entry(item,highlight_id=456,title='Destaque');self.assertEqual(row['id'],'story_987');self.assertEqual(row['instagram_kind'],'highlights')
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);command=media_command(s,{'metadata':json.dumps(row),'original_id':row['id']},s.root/'temporary'/'story.mp4')
            self.assertEqual(command[command.index('--media-id')+1],'987');self.assertEqual(command[command.index('--owner')+1],'123');self.assertEqual(command[command.index('--highlight')+1],'456')
        self.assertEqual(canonical('https://instagram.com/stories/example/987/'),'https://www.instagram.com/stories/example/987/')
        self.assertEqual(canonical('https://instagram.com/stories/highlights/456/'),'https://www.instagram.com/stories/highlights/456/')
    def test_session_is_explicit_private_and_not_returned_in_status(self):
        from memoria.instagram import save_session,connection_status,disconnect
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);self.assertRaises(ValueError,save_session,s,{'cookies':{'password':'not-accepted'}})
            save_session(s,{'cookies':{'sessionid':'test-session','csrftoken':'test-csrf','ds_user_id':'123'}})
            self.assertTrue(connection_status(s)['configured']);self.assertNotIn('cookies',connection_status(s));self.assertEqual((s.root/'instagram-session.json').stat().st_mode&0o777,0o600)
            disconnect(s);self.assertFalse(connection_status(s)['configured'])
    def test_stories_require_a_connection_and_queue_no_download_if_missing(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);sid=s.register_source('https://instagram.com/example/')
            self.assertRaises(ValueError,start,s,sid,'video','stories')
            with s.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
    def test_story_and_highlight_scopes_use_only_the_selected_collector(self):
        from memoria.instagram import save_session
        for scope in ('stories','highlights'):
            with tempfile.TemporaryDirectory() as d:
                s=Store(d);sid=s.register_source('https://instagram.com/example/');save_session(s,{'cookies':{'sessionid':'test-session','csrftoken':'test-csrf'}})
                start(s,sid,'video',scope);w=Worker(s,reserve=0);j=s.claim(w.owner);SyncEngine(w).start(j)
                with s.connect() as c:self.assertEqual([r[0] for r in c.execute('SELECT method FROM scan_methods')],['instagram_'+scope])

class StorageMetrics(unittest.TestCase):
    def test_measured_bytes_are_deduplicated_and_estimates_are_named_ranges(self):
        from tests.test_channels_v5 import fixture,A
        with tempfile.TemporaryDirectory() as d:
            s=Store(d);sid,_=fixture(s);s.ingest(sid,[{'id':A,'duration':60}]);p=s.root/'originals'/'video.mp4';p.write_bytes(b'controlled-size')
            with s.connect() as c:c.execute('UPDATE items SET path=?,blob_hash=?,size=?',(str(p.relative_to(s.root)),hash_file(p),p.stat().st_size))
            row=status(s)['channels'][0];self.assertEqual(row['occupied_bytes'],p.stat().st_size);self.assertEqual(row['remaining'],1);self.assertGreater(row['estimated_pending_text_bytes_max'],row['estimated_pending_text_bytes_min']);self.assertEqual(row['estimate_kind'],'text_and_metadata')
