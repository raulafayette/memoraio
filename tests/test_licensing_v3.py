import json,tempfile,unittest
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from licensing.ledger import Ledger,SandboxProvider,verify_license
class Licensing(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.now=1793290000;self.provider=SandboxProvider();self.key=Ed25519PrivateKey.generate();self.ledger=Ledger(Path(self.tmp.name)/'license.db',self.provider,b'a-test-secret-longer-than-32-bytes!',self.key,lambda:self.now);self.device='test-installation-123';self.token=self.ledger.register(self.device)['token']
 def tearDown(self):self.tmp.cleanup()
 def event(self,order,event='event-1',claimed_status='approved'):
  raw=json.dumps({'event_id':event,'payment_id':order['provider_id'],'status':claimed_status}).encode();return self.ledger.webhook(raw,self.now,self.ledger.signature(raw,self.now))
 def test_never_trusts_client_success_and_idempotent_48h_expiration(self):
  order=self.ledger.create(self.token,'request-key-123456');self.assertEqual(self.ledger.create(self.token,'request-key-123456')['id'],order['id'])
  self.assertEqual(self.event(order),'pending');self.assertEqual(self.ledger.entitlement(self.token)['plan'],'free')
  self.provider.simulate(order['provider_id'],'approved',self.now);self.assertEqual(self.event(order,'event-2'),'approved');self.assertEqual(self.event(order,'event-2'),'duplicate')
  license=self.ledger.signed_license(self.token);self.assertEqual(verify_license(self.key.public_key(),license,self.device,self.now)['expires_at'],self.now+48*3600)
  self.assertRaises(PermissionError,verify_license,self.key.public_key(),license,'wrong-installation',self.now)
  self.now+=48*3600;self.assertEqual(self.ledger.entitlement(self.token)['plan'],'free');self.assertRaises(PermissionError,verify_license,self.key.public_key(),license,self.device,self.now)
 def test_refund_revocation_and_payment_mismatch(self):
  order=self.ledger.create(self.token,'request-key-123456');self.provider.records[order['provider_id']]['amount_cents']=1
  self.assertRaises(ValueError,self.event,order);self.provider.records[order['provider_id']]['amount_cents']=1990;self.provider.simulate(order['provider_id'],'approved',self.now);self.event(order)
  self.assertEqual(self.ledger.entitlement(self.token)['plan'],'temporary');self.provider.simulate(order['provider_id'],'refunded',self.now);self.event(order,'refund');self.assertEqual(self.ledger.entitlement(self.token)['plan'],'free')
 def test_forged_expired_webhook_and_daily_distinct_video_quota(self):
  self.assertRaises(PermissionError,self.ledger.webhook,b'{}',self.now,'fake')
  raw=b'{}';self.assertRaises(PermissionError,self.ledger.webhook,raw,self.now-301,self.ledger.signature(raw,self.now-301))
  for n in range(10):self.assertTrue(self.ledger.consume(self.token,'owned_'+str(n)))
  self.assertTrue(self.ledger.consume(self.token,'owned_0'));self.assertFalse(self.ledger.consume(self.token,'owned_11'));self.now+=86400;self.assertTrue(self.ledger.consume(self.token,'owned_11'))
 def test_unvalidated_commercial_features_disabled(self):
  self.assertRaises(ValueError,self.ledger.create,self.token,'request-key-123456','unrestricted_youtube_downloader')
if __name__=='__main__':unittest.main()
