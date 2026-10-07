"""Actual A8 pure adapter + TEMP ledger + actual HTTP/renderer, no providers."""
import copy,json,os,tempfile,unittest,hashlib
from pathlib import Path
from unittest.mock import patch
from tools.stage1b_historical_campaign import radar_market_reality as market
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign.radar_intelligence_store import IntelligenceStore,StoreError
from tools.stage1b_historical_campaign.radar_reality_replay import replay_event_as_of
from tools.stage1b_historical_campaign.radar_macroview_freeze import freeze_macroview
ROOT=Path(__file__).resolve().parents[1]
EID='canonical-event-v0-'+'a'*64
def at(t):return '2026-10-07T'+t+':00Z'
def raw():return json.loads((ROOT/'tests/fixtures/market_reality_v0.json').read_bytes())['observations']
def rows():return [market.normalize_record(r) for r in raw()]
def item(snapshot,symbol):return next(i for i in snapshot['instruments'] if i['symbol']==symbol)
class SnapshotTests(unittest.TestCase):
 def snapshot(self,t,**kw):return market.project_snapshot(EID,at('10:00'),rows(),as_of=at(t),**kw)
 def test_1002_only_prior_prices(self):
  s=self.snapshot('10:02');self.assertEqual(item(s,'SPY')['price_or_level'],500);self.assertEqual(item(s,'VIX')['price_or_level'],15);self.assertEqual(s['snapshot_status'],'PARTIAL');self.assertNotIn('10:05',json.dumps(s));self.assertNotIn('10:30',json.dumps(s))
 def test_1010_may_see_1005(self):self.assertEqual(item(self.snapshot('10:10'),'SPY')['price_or_level'],499)
 def test_1020_cannot_see_1030(self):self.assertEqual(item(self.snapshot('10:20'),'SPY')['price_or_level'],499)
 def test_1030_sees_1030(self):self.assertEqual(item(self.snapshot('10:30'),'SPY')['price_or_level'],497)
 def test_missing_symbols_stay_null(self):
  s=self.snapshot('10:02')
  for symbol in ('QQQ','DXY','US10Y'):
   i=item(s,symbol);self.assertIsNone(i['price_or_level']);self.assertIsNone(i['source']);self.assertEqual(i['availability_status'],'NO_POINT_IN_TIME_SOURCE')
 def test_event_not_yet_known(self):self.assertEqual(self.snapshot('09:59')['snapshot_status'],'UNAVAILABLE')
 def test_no_system_event_observation(self):
  s=market.project_snapshot(EID,None,rows(),as_of=at('10:10'));self.assertEqual(s['reason'],'NO_EVENT_SYSTEM_OBSERVATION');self.assertIsNone(s['observed_at'])
 def test_empty_market_projection_does_not_manufacture_clock_drift(self):
  a=market.project_snapshot(EID,at('10:00'),[],as_of=at('10:10'))
  b=market.project_snapshot(EID,at('10:00'),[],as_of=at('10:20'))
  self.assertEqual(a,b);self.assertIsNone(a['as_of']);self.assertIsNone(a['window_timestamp'])
 def test_window_t0(self):self.assertEqual(item(self.snapshot('10:30',window='T0'),'SPY')['price_or_level'],500)
 def test_future_window_does_not_fill_prior_price(self):
  s=self.snapshot('10:02',window='T+5m');self.assertEqual(s['reason'],'WINDOW_NOT_YET_OBSERVED');self.assertIsNone(item(s,'SPY')['price_or_level'])
 def test_5m_window(self):self.assertEqual(item(self.snapshot('10:10',window='T+5m'),'SPY')['price_or_level'],499)
 def test_30m_window(self):self.assertEqual(item(self.snapshot('10:30',window='T+30m'),'SPY')['price_or_level'],497)
 def test_trading_day_is_not_calendar_day_guess(self):self.assertEqual(self.snapshot('10:30',window='T+1_TRADING_DAY')['reason'],'TRADING_DAY_AUTHORITY_UNAVAILABLE')
 def test_bad_window(self):self.assertRaises(market.MarketRealityError,self.snapshot,'10:30',window='WRONG')
 def test_stale_is_not_current_market(self):self.assertIsNone(item(self.snapshot('11:00'),'SPY')['price_or_level'])
 def test_source_known_later_cannot_backfill(self):
  r=rows();r[1]['observed_at']=at('10:20');s=market.project_snapshot(EID,at('10:00'),r,as_of=at('10:10'));self.assertEqual(item(s,'SPY')['price_or_level'],500)
 def test_previous_close_not_inferred(self):self.assertIsNone(item(self.snapshot('10:10'),'SPY')['change_from_previous_close'])
 def test_change_since_event_is_observation_only(self):self.assertAlmostEqual(item(self.snapshot('10:10'),'SPY')['change_since_event'],-0.2);self.assertEqual(self.snapshot('10:10')['authority_role'],'MARKET_OBSERVATION_ONLY')
 def test_yield_change_uses_basis_points(self):
  r=raw()[0];r.update(symbol='US10Y',value_unit='YIELD_PERCENT',price_or_level=4.06,previous_close=dict(price_or_level=4,market_timestamp=at('09:00'),observed_at=at('09:00'),source_observation_id='prior-yield'))
  s=market.project_snapshot(EID,at('10:00'),[market.normalize_record(r)],as_of=at('10:02'));self.assertAlmostEqual(item(s,'US10Y')['change_from_previous_close'],6);self.assertEqual(item(s,'US10Y')['change_unit'],'BASIS_POINTS')
 def test_future_previous_close_rejected(self):
  r=raw()[0];r['previous_close']=dict(price_or_level=480,market_timestamp=at('09:00'),observed_at=at('10:30'),source_observation_id='future-revision');self.assertRaises(market.MarketRealityError,market.normalize_record,r)
 def test_malformed_naive_times_rejected(self):
  for t in (None,'bad','2026-10-07','2026-10-07T10:00:00'):
   r=raw()[0];r['observed_at']=t;self.assertRaises(market.MarketRealityError,market.normalize_record,r)
 def test_values_and_units(self):
  for value in (True,float('nan'),float('inf'),None,'500',-1):
   r=raw()[0];r['price_or_level']=value;self.assertRaises(market.MarketRealityError,market.normalize_record,r)
  r=raw()[0];r['value_unit']='INDEX_LEVEL';self.assertRaises(market.MarketRealityError,market.normalize_record,r)
 def test_market_time_after_knowledge_rejected(self):
  r=raw()[0];r['market_timestamp']=at('10:05');self.assertRaises(market.MarketRealityError,market.normalize_record,r)
 def test_no_price_only_csv_authority(self):
  r=raw()[0];r.pop('time_basis');self.assertRaises(market.MarketRealityError,market.normalize_record,r)
 def test_symbol_is_not_proxy_substitution(self):
  r=raw()[0];r['symbol']='NASDAQ100';self.assertRaises(market.MarketRealityError,market.normalize_record,r)
 def test_malformed_symbol_is_typed_failure(self):
  for symbol in ([],{},None,False):
   r=raw()[0];r['symbol']=symbol;self.assertRaises(market.MarketRealityError,market.normalize_record,r)
 def test_pure_projection_does_not_mutate(self):
  r=rows();before=copy.deepcopy(r);market.project_snapshot(EID,at('10:00'),r,as_of=at('10:10'));self.assertEqual(r,before)
class ReaderReplayTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory(prefix='a8-market-');self.root=Path(self.tmp.name);self.path=self.root/'input.json'
 def tearDown(self):self.tmp.cleanup()
 def packet(self,records=None):self.path.write_text(json.dumps(dict(schema=market.INPUT,observations=raw() if records is None else records)),encoding='utf8')
 def test_missing_unreadable_empty(self):
  self.assertEqual(market.read_observations(None),([], 'NOT_CONFIGURED'));self.assertEqual(market.read_observations(self.path),([], 'UNAVAILABLE'));self.packet([]);self.assertEqual(market.read_observations(self.path),([], 'EMPTY'))
 def test_read_bytes_unchanged_and_deduplicated(self):
  self.packet(raw()+[raw()[0]]);before=self.path.read_bytes();r,s=market.read_observations(self.path);self.assertEqual(s,'AVAILABLE');self.assertEqual(len(r),5);self.assertEqual(self.path.read_bytes(),before)
 def test_conflicting_source_identity_rejected(self):
  r=raw();bad=copy.deepcopy(r[0]);bad['price_or_level']=800;self.packet(r+[bad]);self.assertEqual(market.read_observations(self.path),([], 'UNAVAILABLE'))
 def test_conflicting_event_anchor_rejected(self):
  r=raw();r[1]['event_observed_at']=at('10:01');self.packet(r);self.assertEqual(market.read_observations(self.path),([], 'UNAVAILABLE'))
 def test_declared_synthetic_fixture_rejected_even_with_exact_event_binding(self):
  news=self.root/'news.json';news.write_text(json.dumps([dict(observed_time=at('10:00'),headline_or_text='Synthetic audit news',source_name='Test',source_url='https://example.test/audit')]),encoding='utf8')
  base=radar.build_radar_view(radar.EvidencePaths(news=news),now=market.utc(at('10:10')))
  packet=json.loads((ROOT/'tests/fixtures/market_reality_v0.json').read_bytes())
  for row in packet['observations']:row['event_id']=base['events'][0]['event_id']
  self.path.write_text(json.dumps(packet),encoding='utf8');before=self.path.read_bytes()
  view=radar.build_radar_view(radar.EvidencePaths(news=news,market_reality=self.path),now=market.utc(at('10:10')))
  self.assertEqual(view['market_reality_source_status'],'UNAVAILABLE');self.assertEqual(view['market_reality_observations'],[])
  self.assertTrue(all(i['price_or_level'] is None for i in view['events'][0]['market_reality']['instruments']))
  self.assertEqual(self.path.read_bytes(),before)
 def test_ambiguous_synthetic_marker_is_not_ignored(self):
  for flag in (True,'true',1,None):
   self.path.write_text(json.dumps(dict(schema=market.INPUT,synthetic=flag,observations=raw())),encoding='utf8')
   self.assertEqual(market.read_observations(self.path),([], 'UNAVAILABLE'))
 def view(self,records):
  event=dict(event_id=EID,event_title='Synthetic market context',article_references=['https://example.test/news'],verification_status='UNVERIFIED_NEWS',first_detected_at=at('09:00'),geography_status='UNKNOWN')
  return dict(status='AVAILABLE',events=[event],items=[dict(article_reference='https://example.test/news',title='Synthetic market context',observed_at=at('09:00'),verification_status='UNVERIFIED_NEWS')],market_reality_observations=records)
 def test_replay_ledger_boundaries(self):
  store=IntelligenceStore(self.root/'ledger.db',create=True);r=rows();store.ingest_projection(self.view([r[0],r[3]]),observed_at=at('10:00'))
  old=store.read_as_of(EID,at('10:02'));f=store.freeze_event(EID,freeze_key='before',as_of=at('10:02'),created_at=at('10:02'))
  store.ingest_projection(self.view([r[1],r[4]]),observed_at=at('10:05'));store.ingest_projection(self.view([r[2]]),observed_at=at('10:30'))
  for t,price in [('10:02',500),('10:10',499),('10:20',499),('10:30',497)]:
   with self.subTest(time=t),patch.object(market,'read_observations',side_effect=AssertionError('CURRENT_FILE_FORBIDDEN')):
    result=replay_event_as_of(store,EID,at(t));snap=result['reconstructed_macroview']['snapshot']['market_reality'];self.assertEqual(item(snap,'SPY')['price_or_level'],price);self.assertEqual(snap['observed_at'],at('10:00'))
  self.assertEqual(store.read_as_of(EID,at('10:02')),old);self.assertEqual(store.freezes(EID),[f])
 def test_imported_old_prices_not_known_before_ledger_recording(self):
  store=IntelligenceStore(self.root/'ledger.db',create=True);store.ingest_projection(self.view([rows()[0]]),observed_at=at('10:05'))
  self.assertEqual(replay_event_as_of(store,EID,at('10:02'))['replay_status'],'NO_OBSERVATIONS');snap=replay_event_as_of(store,EID,at('10:10'))['reconstructed_macroview']['snapshot']['market_reality'];self.assertEqual(snap['observed_at'],at('10:05'));self.assertEqual(item(snap,'SPY')['observed_at'],'2026-10-07T10:05:00.000000Z')
 def test_future_market_knowledge_cannot_enter_store(self):
  store=IntelligenceStore(self.root/'ledger.db',create=True);self.assertRaises(StoreError,store.ingest_projection,self.view([rows()[1]]),observed_at=at('10:00'))
 def test_api_adapter_additive_and_input_hash_unchanged(self):
  news=self.root/'news.json';news.write_text(json.dumps([dict(observed_time=at('10:00'),headline_or_text='Taiwan exports',source_name='Synthetic',source_url='https://example.test/news')]),encoding='utf8')
  baseline=radar.build_radar_view(radar.EvidencePaths(news=news),now=market.utc(at('10:10')));eid=baseline['events'][0]['event_id'];r=raw();[x.update(event_id=eid) for x in r];self.packet(r);before=self.path.read_bytes()
  view=radar.build_radar_view(radar.EvidencePaths(news=news,market_reality=self.path),now=market.utc(at('10:10')))
  self.assertEqual(view['items'],baseline['items']);self.assertEqual(view['events'][0]['verification_status'],'UNVERIFIED_NEWS');self.assertEqual(view['events'][0]['market_reality']['snapshot_status'],'PARTIAL');self.assertEqual(self.path.read_bytes(),before)
  self.assertEqual(view['macroview_previews'][0]['snapshot']['market_reality'],view['events'][0]['market_reality'])
 def test_env_portable_optional_path(self):
  with patch.dict(os.environ,{'RADAR_DATA_ROOT':str(self.root),'GLOBAL_EVENT_RADAR_MARKET_REALITY_PATH':'input.json'}):self.assertEqual(radar.EvidencePaths.from_environment().market_reality,self.path)
if __name__=='__main__':unittest.main()
