import json
from pathlib import Path
import tempfile
import unittest
from memoria.core import Store,atomic_json,hash_file
from memoria.library import rich_text,publish_library,component
from memoria.caption_fetch import allowed

class LibraryTests(unittest.TestCase):
 def test_unknown_values_timing_and_no_invented_speaker(self):
  text=rich_text({'identification':{'author':None},'segments':[{'start':3600.123,'end':3601.456,'text':'Fala integral sem resumo','speaker':'Nome não comprovado'}]})
  self.assertIn('Indisponível',text);self.assertIn('[01:00:00.123 - 01:00:01.456]',text);self.assertNotIn('Nome não comprovado',text);self.assertIn('Fala integral sem resumo',text)
 def test_endpoints_reject_redirects_and_credentials(self):
  for u in ['http://youtube.com/api/timedtext','https://evil.test/api/timedtext','https://www.youtube.com.evil.test/api/timedtext','https://user@www.youtube.com/api/timedtext','https://www.youtube.com/watch','https://127.0.0.1/api/timedtext']:
   self.assertFalse(allowed(u),u)
  self.assertTrue(allowed('https://www.youtube.com/api/timedtext?v=abc'))
 def test_library_preserves_original_and_previous_derived_revision(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store(Path(tmp)/'data');s.add_source('https://youtu.be/BaW_jenozKc')
   with s.connect() as c:sid=c.execute('SELECT id FROM sources').fetchone()[0]
   s.ingest(sid,[{'id':'BaW_jenozKc','title':'Original','description':'Descrição integral #arquivo https://example.com','upload_date':'20260101','channel_id':'UCfixture','duration':2}])
   iid='youtube_BaW_jenozKc';p=s.root/'transcripts'/iid/'t';p.mkdir(parents=True);source=p/'transcript.json';atomic_json(source,{'id':'t','segments':[{'start':0,'end':2,'text':'Conhecimento integral'}],'created':1790000000,'origin':'manual_caption','duration':2})
   digest=hash_file(source)
   with s.connect() as c:c.execute('INSERT INTO transcripts VALUES(?,?,?,?,?,?,?,?,?,?,1)',('t',iid,1790000000,'manual_caption','pt','null',str(source.relative_to(s.root)),digest,'structural_pass','{}'))
   rel=publish_library(s,iid);base=s.root/rel;one=(base/'transcricao.txt').resolve();publish_library(s,iid)
   self.assertNotEqual(one,(base/'transcricao.txt').resolve());self.assertTrue(one.is_file());self.assertEqual(hash_file(source),digest)
   d=json.loads((base/'metadados.json').read_text());self.assertEqual(d['identification']['description'],'Descrição integral #arquivo https://example.com');self.assertIsNone(d['dates']['publication_timezone_original']);self.assertEqual(d['dates']['publication_date_original'],'20260101');self.assertEqual(d['additional']['hashtags'],['#arquivo'])
 def test_stable_paths_cannot_escape(self):
  for value in ['../private','/tmp','a/b','a\\b','', 'á']:self.assertRaises(ValueError,component,value)
if __name__=='__main__':unittest.main()
