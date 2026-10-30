import tempfile,time,unittest
from types import SimpleNamespace
from memoria.core import Store
from memoria.service import check_worker_health
class Watchdog(unittest.TestCase):
 def test_stalled_worker_terminated_and_fresh_worker_kept(self):
  with tempfile.TemporaryDirectory() as d:
   s=Store(d);events=[];now=time.time();child=SimpleNamespace(pid=12345,poll=lambda:None,terminate=lambda:events.append('terminate'))
   check_worker_health(s,{'processing':child},{'processing':now-10},now);self.assertEqual(events,[])
   started={'processing':now-200};check_worker_health(s,{'processing':child},started,now);self.assertEqual(events,['terminate'])
   with s.connect() as c:c.execute('INSERT INTO workers VALUES(?,?,?)',('fresh',now,12345))
   events.clear();check_worker_health(s,{'processing':child},{'processing':now-200},now);self.assertEqual(events,[])
if __name__=='__main__':unittest.main()
