import tempfile
from pathlib import Path
import unittest
from memoria.core import Store
from memoria.operations import request,options
class Operations(unittest.TestCase):
 def test_independent_combined_reuse_and_scope(self):
  with tempfile.TemporaryDirectory() as d:
   s=Store(Path(d)/'data');s.add_source('https://youtu.be/BaW_jenozKc')
   with s.connect() as c:sid=c.execute('SELECT id FROM sources').fetchone()[0]
   s.ingest(sid,[{'id':'BaW_jenozKc'}]);iid='youtube_BaW_jenozKc'
   jobs=request(s,[iid],['video','audio','transcript'],{'audio_format':'mp3','max_height':1080})
   self.assertEqual(len(jobs),3);self.assertEqual(options(s,jobs[0])['max_height'],1080)
   self.assertEqual(request(s,[iid],['audio'],{'audio_format':'mp3','max_height':1080}),[jobs[1]])
   self.assertRaises(ValueError,request,s,[iid],['audio'],{'audio_format':'original'})
   self.assertRaises(ValueError,request,s,['youtube_private'],['video'])
   self.assertRaises(ValueError,request,s,[iid],['video'],{'format_id':'unsupported'})

class AudioReuse(unittest.TestCase):
 def test_real_video_reuse_and_mp3_without_network(self):
  import subprocess,json,shutil
  from memoria.core import hash_file
  from memoria.worker import Worker
  from memoria.operations import extract_audio
  if not shutil.which('ffmpeg'):self.skipTest('FFmpeg necessário')
  with tempfile.TemporaryDirectory() as d:
   s=Store(d);s.add_source('https://youtu.be/BaW_jenozKc')
   with s.connect() as c:sid=c.execute('SELECT id FROM sources').fetchone()[0]
   s.ingest(sid,[{'id':'BaW_jenozKc'}]);iid='youtube_BaW_jenozKc';video=s.root/'originals'/'controlled.mp4'
   subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=black:s=64x64:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-c:a','aac','-shortest',str(video)],check=True)
   digest=hash_file(video)
   with s.connect() as c:c.execute("UPDATE items SET status='archived',path=?,blob_hash=?,size=? WHERE id=?",(str(video.relative_to(s.root)),digest,video.stat().st_size,iid))
   request(s,[iid],['audio'],{'audio_format':'mp3'});w=Worker(s,reserve=0);job=s.claim(w.owner,kinds=('audio',))
   extract_audio(w,job);s.finish(job,w.owner)
   with s.connect() as c:original=c.execute('SELECT * FROM audio_assets WHERE item_id=?',(iid,)).fetchone();mp3=json.loads(c.execute('SELECT value FROM service_state WHERE key=?',('mp3:'+iid,)).fetchone()[0])
   self.assertTrue(original['path'].endswith('.m4a'));self.assertTrue((s.root/original['path']).is_file());self.assertTrue((s.root/mp3['path']).is_file());self.assertEqual(hash_file(video),digest)
   probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(s.root/original['path'])]));self.assertEqual([x['codec_name'] for x in probe['streams']],['aac'])

class ScheduledMedia(unittest.TestCase):
 def test_upcoming_media_defers_without_retry_budget_or_platform_cooldown(self):
  import time
  from memoria.worker import classify
  with tempfile.TemporaryDirectory() as d:
   s=Store(d);s.add_source('https://youtu.be/BaW_jenozKc');j=s.claim('worker');error=classify('ERROR: This live event will begin in 19 days.')
   s.finish(j,'worker',error)
   with s.connect() as c:row=c.execute('SELECT * FROM jobs WHERE id=?',(j['id'],)).fetchone();self.assertEqual(row['state'],'queued');self.assertEqual(row['attempts'],0);self.assertGreater(row['available'],time.time()+86000)
   self.assertIsNone(s.claim('other'))

class GlobalPause(unittest.TestCase):
 def test_resume_restores_only_global_interruptions(self):
  from memoria.service import set_paused
  from memoria.core import Interrupted
  with tempfile.TemporaryDirectory() as d:
   s=Store(d);s.add_source('https://youtu.be/BaW_jenozKc');job=s.claim('worker')
   s.add_source('https://youtu.be/00000000001')
   with s.connect() as c:other=c.execute("SELECT id FROM jobs WHERE state='queued'").fetchone()[0]
   s.control(other,'pause');set_paused(s,True,True);s.finish(job,'worker',Interrupted('pause'));set_paused(s,False)
   with s.connect() as c:self.assertEqual(c.execute('SELECT state FROM jobs WHERE id=?',(job['id'],)).fetchone()[0],'queued');self.assertEqual(c.execute('SELECT state FROM jobs WHERE id=?',(other,)).fetchone()[0],'paused')
if __name__=='__main__':unittest.main()
