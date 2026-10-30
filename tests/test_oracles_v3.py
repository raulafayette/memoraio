import json,tempfile,unittest
from memoria.core import Store
from memoria.oracles import configure,list_oracles,fused,enqueue_query,query_status
from memoria.oracle_generate import validate_answer
class Oracles(unittest.TestCase):
 def test_configuration_scope_history_and_queued_query(self):
  with tempfile.TemporaryDirectory() as d:
   s=Store(d);sid=s.register_source('https://youtube.com/@fixture',cadence='manual',auto_process=False)
   oid=configure(s,'Arquivo','Estudar montagem',[sid],'Atribuir opiniões','literal')
   self.assertEqual(list_oracles(s)[0]['sources'],[sid]);configure(s,'Arquivo','Comparar montagem',[sid],oid=oid)
   self.assertEqual(len(list_oracles(s)[0]['history']),2)
   q=enqueue_query(s,oid,'Quais critérios?',True);self.assertEqual(query_status(s,q['query_id'])['job']['state'],'queued')
   self.assertRaises(ValueError,configure,s,'X','Y',[sid],oid='../unsafe')
 def test_rank_fusion_keeps_both_channels(self):
  ranked=fused([{'id':1},{'id':2}],[{'id':2},{'id':3}]);self.assertEqual(ranked[0]['id'],2);self.assertEqual({r['id'] for r in ranked},{1,2,3})
 def test_citations_fail_closed(self):
  evidence=[{'reference':'E1'}];good={'ai_interpretation':'Texto atribuído [E1]','oracle_conclusion':'Limite da evidência [E1]'}
  self.assertEqual(validate_answer(good,evidence),good)
  self.assertRaises(ValueError,validate_answer,{**good,'oracle_conclusion':'Fato sem fonte'},evidence)
  self.assertRaises(ValueError,validate_answer,{**good,'oracle_conclusion':'Inventado [E999]'},evidence)

class ExhaustiveResume(unittest.TestCase):
 def test_81_documents_resume_without_consuming_retry_budget(self):
  from memoria.oracles import exhaustive_step
  from memoria.worker import Worker
  from memoria.core import Failure
  with tempfile.TemporaryDirectory() as d:
   s=Store(d);sid=s.register_source('https://youtube.com/@fixture',cadence='manual',auto_process=False)
   s.ingest(sid,[{'id':f'{n:011d}'} for n in range(81)])
   with s.connect() as c:
    for n in range(81):
     iid='youtube_'+f'{n:011d}';tid='t'+str(n)
     c.execute('INSERT INTO transcripts VALUES(?,?,?,?,?,?,?,?,?,?,1)',(tid,iid,1,'manual_caption','pt','null','fixture.json','fixture','structural_pass','{}'))
     c.execute('INSERT INTO segments(transcript_id,item_id,start,end,text) VALUES(?,?,?,?,?)',(tid,iid,0,1,'evidência consistente'))
   oid=configure(s,'Pesquisa','Examinar todos',[sid],strategy='literal');q=enqueue_query(s,oid,'evidência',True);w=Worker(s);folder=s.root/'oracles'/'queries'/q['query_id'];request=json.loads((folder/'request.json').read_text())
   for expected in (40,80):
    job=s.claim(w.owner,kinds=('oracle',))
    with self.assertRaises(Failure) as error:exhaustive_step(w,job,request,folder)
    self.assertEqual(error.exception.state,'queued');s.finish(job,w.owner,error.exception)
    self.assertEqual(len(list((folder/'documents').glob('*.json'))),expected)
    with s.connect() as c:c.execute('UPDATE jobs SET available=0');self.assertEqual(c.execute("SELECT attempts FROM jobs WHERE kind='oracle'").fetchone()[0],0)
   job=s.claim(w.owner,kinds=('oracle',));hits=exhaustive_step(w,job,request,folder);self.assertTrue(hits);self.assertEqual(len(list((folder/'documents').glob('*.json'))),81)
if __name__=='__main__':unittest.main()
