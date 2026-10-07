"""Actual loopback handler: no provider request, no public writes, no DB leakage."""
import copy,hashlib,http.client,json,os,tempfile,threading,unittest
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import patch,Mock
from tools.stage1b_historical_campaign import radar_web_server as app
from tools.stage1b_historical_campaign.radar_intelligence_store import IntelligenceStore,IntelligenceRecorder,StoreError
from radar_replay_fixture import projection,at,ROOT
class ReplayApiTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='radar-a6-api-');self.db=Path(self.temp.name)/'store.sqlite3';self.store=IntelligenceStore(self.db,create=True);self.v,self.eid=projection()
  for stage in ['09:00','09:10','09:30','10:00','10:15']:
   v,_=projection(stage);self.store.ingest_projection(v,observed_at=at(stage))
  self.env=patch.dict(os.environ,{'RADAR_INTELLIGENCE_DB':str(self.db),'RADAR_PERSIST_INTELLIGENCE':'0','RADAR_DATA_ROOT':str(ROOT/'demo/radar_public'),'GLOBAL_EVENT_RADAR_NEWS_PATH':'news','GLOBAL_EVENT_RADAR_OFFICIAL_PATH':'official-packet.json','RADAR_DEMO_MODE':'1'});self.env.start()
  with patch.object(app,'PORT',0):self.server=app.bind_server()
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join(5);self.env.stop();self.temp.cleanup()
 def request(self,path,method='GET'):
  c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
  try:c.request(method,path);r=c.getresponse();return r.status,r.read()
  finally:c.close()
 def url(self,**kw):return '/api/app/replay?'+urlencode({'event_id':self.eid,'as_of':at('09:45'),**kw})
 def test_valid_actual_route(self):status,body=self.request(self.url());r=json.loads(body);self.assertEqual(status,200);self.assertEqual(r['contract_version'],'POINT_IN_TIME_REPLAY_V0');self.assertEqual(r['reconstructed_macroview']['snapshot']['market_expectations'][0]['probabilities'][0],'0.55')
 def test_empty_replay(self):status,body=self.request(self.url(as_of=at('08:59')));self.assertEqual(status,200);self.assertEqual(json.loads(body)['replay_status'],'NO_OBSERVATIONS')
 def test_unknown_event(self):status,body=self.request(self.url(event_id='canonical-event-v0-'+'f'*64));self.assertEqual(status,200);self.assertEqual(json.loads(body)['replay_status'],'NO_OBSERVATIONS')
 def test_bad_event(self):self.assertEqual(self.request(self.url(event_id="' OR 1=1"))[0],400)
 def test_bad_time(self):
  for value in ['bad','2026-10-07','2026-10-07T09:00:00','']:
   with self.subTest(value=value):self.assertEqual(self.request(self.url(as_of=value))[0],400)
 def test_missing_or_duplicate_query(self):
  for url in ['/api/app/replay','/api/app/replay?event_id='+self.eid,self.url()+'&event_id='+self.eid,self.url()+'&extra=1',self.url()+'&x=1&y=2&z=3']:
   with self.subTest(url=url):self.assertEqual(self.request(url)[0],400)
 def test_query_size_bound(self):self.assertEqual(self.request(self.url(as_of='x'*5000))[0],400)
 def test_public_writes_forbidden(self):
  for method in ['POST','PUT','PATCH','DELETE']:self.assertEqual(self.request(self.url(),method)[0],405)
 def test_replay_reads_do_not_write(self):
  before=self.db.read_bytes();self.request(self.url());self.request(self.url());self.assertEqual(before,self.db.read_bytes())
 def test_missing_db_current_radar_still_200(self):
  p=Path(self.temp.name)/'absent.sqlite3'
  with patch.dict(os.environ,{'RADAR_INTELLIGENCE_DB':str(p)}):status,body=self.request(self.url());self.assertEqual(status,503);self.assertEqual(self.request('/api/app/radar')[0],200)
  self.assertFalse(p.exists());self.assertNotIn(str(p),body.decode())
 def test_corrupt_db_current_radar_still_200(self):
  p=Path(self.temp.name)/'corrupt.db';p.write_bytes(b'broken')
  with patch.dict(os.environ,{'RADAR_INTELLIGENCE_DB':str(p)}):status,body=self.request(self.url());self.assertEqual(status,503);self.assertEqual(self.request('/api/app/radar')[0],200)
  self.assertEqual(json.loads(body)['error'],'INTELLIGENCE_REPLAY_UNAVAILABLE');self.assertNotIn('sqlite',body.decode());self.assertNotIn('Traceback',body.decode())
 def test_health_independent(self):self.assertEqual(self.request('/healthz')[0],200)
 def test_current_ui_has_bilingual_replay(self):status,body=self.request('/');s=body.decode();self.assertEqual(status,200);self.assertIn('Reality Replay',s);self.assertIn('現實重播',s);self.assertIn('replayObserved',s);self.assertIn('aria-live="polite"',s)
 def test_no_network_inside_replay(self):
  with patch('urllib.request.urlopen',side_effect=AssertionError('PROVIDER_FORBIDDEN')):self.assertEqual(self.request(self.url())[0],200)
 def test_recorder_failure_does_not_loop(self):
  rec=IntelligenceRecorder(Path(self.temp.name)/'failure.db',Mock(side_effect=StoreError('unavailable')),interval=5);rec.start();rec.thread.join(3);self.assertFalse(rec.thread.is_alive());self.assertEqual(rec.projection.call_count,1);rec.close()
 def test_server_store_startup_failure_preserves_serving(self):
  with patch.dict(os.environ,{'RADAR_PERSIST_INTELLIGENCE':'1','RADAR_LIVE_EIA':'0','RADAR_LIVE_ECB':'0','RADAR_LIVE_POLYMARKET':'0'}),patch('tools.stage1b_historical_campaign.radar_intelligence_store.IntelligenceRecorder',side_effect=StoreError('unavailable')),patch.object(app.ThreadingHTTPServer,'serve_forever',side_effect=KeyboardInterrupt),patch.object(app,'PORT',0):app.serve()
if __name__=='__main__':unittest.main()
