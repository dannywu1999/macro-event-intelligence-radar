"""Mandatory leakage matrix, newest visible state and no current-input reads."""
import copy,json,sqlite3,tempfile,time,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
from tools.stage1b_historical_campaign.radar_intelligence_store import IntelligenceStore,StoreError
from tools.stage1b_historical_campaign.radar_reality_replay import replay_event_as_of
from radar_replay_fixture import projection,at
class ReplayTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory(prefix='radar-a6-replay-');self.store=IntelligenceStore(Path(self.temp.name)/'store.db',create=True);self.v,self.eid=projection()
 def tearDown(self):self.temp.cleanup()
 def seed(self):
  for stage in ['09:00','09:10','09:30','10:00','10:15']:
   v,_=projection(stage);self.store.ingest_projection(v,observed_at=at(stage))
 def replay(self,stage):return replay_event_as_of(self.store,self.eid,at(stage))
 def test_synthetic_timeline_all_boundaries(self):
  self.seed()
  for stage,news_count,market_count,fact_count,price in [('08:59',0,0,0,None),('09:05',1,0,0,None),('09:20',1,1,0,'0.55'),('09:45',1,1,1,'0.55'),('10:05',1,2,1,'0.70'),('10:30',2,2,1,'0.70')]:
   with self.subTest(stage=stage):
    r=self.replay(stage);self.assertEqual((len(r['news_observations']),len(r['market_expectation_observations']),len(r['official_evidence_observations'])),(news_count,market_count,fact_count));self.assertTrue(all(row['observed_at']<=r['as_of'] for key in ['news_observations','market_expectation_observations','official_evidence_observations','source_states'] for row in r[key]))
    if price:self.assertEqual(r['reconstructed_macroview']['snapshot']['market_expectations'][0]['probabilities'][0],price)
 def test_published_0800_observed_1100_not_visible_1059(self):
  self.store.ingest_projection(self.v,observed_at=at('09:00'));v,_=projection('09:30')
  for fact in v['official_evidence']:fact['published_at']=at('08:00');fact['first_seen_at']=at('11:00');fact['retrieved_at']=at('11:00')
  self.store.ingest_projection(v,observed_at=at('11:00'));self.assertEqual(self.replay('10:59')['official_evidence_observations'],[]);self.assertEqual(len(self.replay('11:00')['official_evidence_observations']),1);self.assertEqual(self.replay('11:00')['official_evidence_observations'][0]['source_timestamp'],'2026-10-07T08:00:00.000000Z')
 def test_polymarket_market_close_does_not_backdate(self):self.seed();self.assertEqual(self.replay('09:09')['market_expectation_observations'],[]);self.assertEqual(self.replay('09:10')['market_expectation_observations'][0]['payload']['market_close_time'],at('08:30'))
 def test_exact_boundary(self):self.seed();self.assertEqual(self.replay('09:29')['official_evidence_observations'],[]);self.assertEqual(len(self.replay('09:30')['official_evidence_observations']),1)
 def test_unknown_event_not_current_catalogue(self):self.seed();r=replay_event_as_of(self.store,'canonical-event-v0-'+'f'*64,at('12:00'));self.assertEqual(r['replay_status'],'NO_OBSERVATIONS');self.assertEqual(r['source_states'],[]);self.assertEqual(r['observation_ids'],[])
 def test_empty_store(self):self.assertEqual(self.replay('09:00')['replay_status'],'NO_OBSERVATIONS')
 def test_source_states_not_future(self):self.store.ingest_projection(self.v,observed_at=at('11:00'));self.assertEqual(self.replay('10:59')['source_states'],[])
 def test_ordering_system_time_stable_id(self):self.seed();r=self.replay('10:30');all_rows=[row for k in ['news_observations','market_expectation_observations','official_evidence_observations'] for row in r[k]];self.assertEqual(r,self.replay('10:30'));self.assertTrue(all(row['observed_at']<=r['as_of'] for row in all_rows))
 def test_future_title_not_in_earlier_replay(self):self.seed();self.assertNotIn('later update',json.dumps(self.replay('10:05')));self.assertIn('later update',json.dumps(self.replay('10:30')))
 def test_future_price_not_in_earlier_macroview(self):self.seed();r=self.replay('09:45');self.assertEqual(r['reconstructed_macroview']['snapshot']['market_expectations'][0]['probabilities'][0],'0.55');self.assertNotIn('0.70',json.dumps(r))
 def test_replay_no_files_or_network(self):
  self.seed()
  with patch('urllib.request.urlopen',side_effect=AssertionError('NETWORK_FORBIDDEN')),patch('builtins.open',side_effect=AssertionError('SOURCE_FILE_READ_FORBIDDEN')):self.assertEqual(self.replay('09:45')['replay_status'],'AVAILABLE')
 def test_no_internal_projection_in_public_result(self):self.seed();self.assertNotIn('_projection',self.replay('10:30'))
 def test_asof_timezone_normalization(self):self.seed();r=replay_event_as_of(self.store,self.eid,'2026-10-07T17:45:00+08:00');self.assertEqual(r,self.replay('09:45'))
 def test_bad_time(self):
  for t in ['','bad','2026-10-07T09:00:00',None]:
   with self.assertRaises(StoreError):replay_event_as_of(self.store,self.eid,t)
 def test_sql_injection_is_literal(self):self.seed();r=replay_event_as_of(self.store,"' OR 1=1 --",at('10:30'));self.assertEqual(r['replay_status'],'NO_OBSERVATIONS')
 def test_news_only_partial_fact_state(self):self.seed();self.assertEqual(self.replay('09:20')['reconstructed_macroview']['fact_state'],'NEWS_ONLY');self.assertEqual(self.replay('09:45')['reconstructed_macroview']['fact_state'],'PARTIAL_OFFICIAL_EVIDENCE');self.assertEqual(self.replay('09:45')['reconstructed_macroview']['snapshot']['event']['verification_status'],'UNVERIFIED_NEWS')
 def test_unknowns_not_filled(self):self.seed();r=self.replay('09:45');self.assertIn('GEOGRAPHY_UNKNOWN',r['unknowns']);self.assertIn('OFFICIAL_PUBLICATION_TIME_UNKNOWN',r['unknowns']);self.assertIsNone(r['reconstructed_macroview']['snapshot']['official_evidence'][0]['published_at'])
 def test_link_added_later_does_not_backdate(self):
  v,_=projection('09:10');market=v['market_expectations'][0];market['canonical_event_id']=None;market['link_status']='UNLINKED'
  for event in v['events']:event['market_expectation_ids']=[]
  self.store.ingest_projection(v,observed_at=at('09:10'));linked,_=projection('09:10');self.store.ingest_projection(linked,observed_at=at('09:30'));self.assertEqual(self.replay('09:20')['market_expectation_observations'],[]);self.assertEqual(self.replay('09:45')['reconstructed_macroview']['expectation_state'],'EXPECTATION_PRESENT')
 def test_unlink_later_not_stale_active_expectation(self):
  v,_=projection('09:10');self.store.ingest_projection(v,observed_at=at('09:10'))
  for market in v['market_expectations']:market.update(canonical_event_id=None,link_status='UNLINKED',link_method=None)
  for event in v['events']:event['market_expectation_ids']=[]
  self.store.ingest_projection(v,observed_at=at('09:30'));r=self.replay('09:45');self.assertEqual(r['reconstructed_macroview']['expectation_state'],'NONE');self.assertTrue(all(not row['active_at_as_of'] for row in r['market_expectation_observations']))
 def test_sql_filter_rejects_injected_future_boundary(self):
  self.seed();rows=self.store.read_as_of(self.eid,at('10:30'))
  with patch.object(self.store,'read_as_of',return_value=rows),self.assertRaises(StoreError):self.replay('09:05')
 def test_ten_thousand_observations(self):
  self.store.ingest_projection(self.v,observed_at=at('09:00'));item=next(i for i in self.v['items'] if i['article_reference']=='https://example.test/eia');records=[];base=datetime(2026,10,7,9,tzinfo=timezone.utc)
  # Each batch append has one timestamp, so use distinct entities for a 10K
  # storage/read load; payloads are explicitly synthetic, not real history.
  for i in range(10000):records.append(dict(observation_kind='NEWS_ARTICLE',entity_id='https://example.test/perf/'+str(i),canonical_event_id=self.eid,payload={**item,'article_reference':'https://example.test/perf/'+str(i),'title':'Synthetic perf '+str(i),'news_source':{'name':'Synthetic performance fixture','url':'https://example.test/perf/'+str(i)}}))
  t=time.perf_counter();self.store.append(records,observed_at=at('09:01'));write=time.perf_counter()-t;t=time.perf_counter();r=self.replay('09:05');read=time.perf_counter()-t;self.assertEqual(len(r['news_observations']),10001);self.assertLess(read,10);print('A6_PERFORMANCE observations=10000 write_seconds=%.3f replay_seconds=%.3f'%(write,read))
 def test_cannot_record_knowledge_before_embedded_system_observation(self):
  v,_=projection('09:30')
  self.assertRaises(StoreError,self.store.ingest_projection,v,observed_at=at('09:00'))
 def test_later_market_observation_not_imported_into_earlier_time(self):
  v,_=projection('10:00');self.assertRaises(StoreError,self.store.ingest_projection,v,observed_at=at('09:59'))
if __name__=='__main__':unittest.main()
