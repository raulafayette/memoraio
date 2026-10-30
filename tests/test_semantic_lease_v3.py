import array,json,tempfile,time,unittest
from pathlib import Path
from memoria.core import Store,atomic_json
from memoria.semantic import search_semantic
class SemanticLease(unittest.TestCase):
 def test_encoder_runner_and_keyset_batches_release_read_lock_for_heartbeat(self):
  with tempfile.TemporaryDirectory() as d:
   s=Store(d);sid=s.register_source('https://youtube.com/@fixture',cadence='manual',auto_process=False);s.ingest(sid,[{'id':'BaW_jenozKc'}]);iid='youtube_BaW_jenozKc';atomic_json(s.root/'semantic-model.json',{'path':'fixture-model','revision':'fixture'})
   with s.connect() as c:
    c.execute('INSERT INTO transcripts VALUES(?,?,?,?,?,?,?,?,?,?,1)',('t',iid,time.time(),'manual_caption','pt','null','fixture.json','fixture','structural_pass','{}'))
    for n in range(2100):
     cur=c.execute('INSERT INTO segments(transcript_id,item_id,start,end,text) VALUES(?,?,?,?,?)',('t',iid,n,n+1,'Fonte controlada'));c.execute('INSERT INTO vectors VALUES(?,?,?)',(cur.lastrowid,'fixture',array.array('f',[1,0]).tobytes()))
   calls=[];beats=[]
   def runner(args):calls.append(args);Path(args[args.index('--output')+1]).write_text(json.dumps([[1,0]]))
   def heartbeat():
    with s.connect() as c:c.execute("INSERT INTO service_state VALUES('test_lease','alive') ON CONFLICT(key) DO UPDATE SET value=excluded.value")
    beats.append(True)
   rows=search_semantic(s,'fonte',runner=runner,progress=heartbeat)
   self.assertEqual(len(calls),1);self.assertEqual(len(beats),2);self.assertEqual(len(rows),30);self.assertTrue(all(r['score']==1 for r in rows))
if __name__=='__main__':unittest.main()
