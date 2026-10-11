import copy,csv,hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools.stage1b_historical_campaign import radar_market_reaction as r
from tools.stage1b_historical_campaign import radar_web_server as web
import test_bilingual_visual_ui as bilingual

class DailyCase(unittest.TestCase):
 def setUp(self):self.packet=json.loads(r.CASE.read_bytes());self.raw=r.DATA.read_bytes()
 def case(self,packet=None,raw=None):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'case.json').write_text(json.dumps(self.packet if packet is None else packet),encoding='utf-8');(p/'data.csv').write_bytes(self.raw if raw is None else raw);return r.load_case(p/'case.json',p/'data.csv')
 def test_real_bundled_values_and_calculation(self):
  c=r.load_case();self.assertEqual(c['status'],'AVAILABLE');x=c['receipt'];self.assertEqual(len(x['observations']),7);self.assertEqual(x['pre_event_observation']['value'],'1.1384');self.assertEqual(x['post_event_observation']['value'],'1.1411');self.assertEqual(x['absolute_change'],'0.0027');self.assertEqual(x['percentage_change'],'0.237175')
 def test_event_day_excluded_from_baseline_and_post(self):
  x=r.load_case()['receipt'];self.assertEqual(x['pre_event_observation']['observation_date'],'2025-06-04');self.assertEqual(x['post_event_observation']['observation_date'],'2025-06-06');self.assertEqual(x['elapsed_calendar_days'],2)
 def test_daily_not_intraday_and_clocks_null(self):
  x=r.load_case()['receipt'];self.assertEqual(x['data_frequency'],'DAILY_REFERENCE_RATE_NOT_TRADED_CLOSE');self.assertIsNone(x['event_timestamp_utc']);self.assertIsNone(x['observation_start_utc']);self.assertTrue(all(o['market_observation_time'] is None for o in x['observations']));self.assertIn('NO_INTRADAY_DATA',x['missing_data_reasons'])
 def test_reference_units_not_corporate_action_price(self):
  x=r.load_case()['receipt'];self.assertEqual(x['instrument_id'],'EURUSD_ECB_REFERENCE');self.assertTrue(all(o['unit']=='USD_PER_EUR' for o in x['observations']));self.assertIn('NOT_APPLICABLE_FX',x['adjustment'])
 def test_expost_never_historical_pit(self):
  x=r.load_case()['receipt'];self.assertFalse(x['point_in_time_available']);self.assertEqual(x['time_basis'],'EX_POST_MARKET_OBSERVATION');self.assertGreater(x['knowledge_at'][:10],x['event_date']);self.assertEqual(x['causal_attribution_status'],'NOT_ESTABLISHED')
 def test_no_retroactive_hypothesis_or_event_confirmation(self):
  c=r.load_case();self.assertEqual(c['event']['verification_status'],'UNVERIFIED_NEWS');self.assertEqual(c['official_evidence'][0]['evidence_status'],'OFFICIAL_CONFIRMED');self.assertIsNone(c['official_evidence'][0]['published_at']);i=c['impact_intelligence']['by_article'][c['article']['article_reference']];self.assertEqual(i['market_reaction']['status'],'NOT_MEASURED');self.assertFalse(i['mechanisms'])
 def test_source_bytes_unchanged(self):
  before=[hashlib.sha256(p.read_bytes()).hexdigest() for p in [r.CASE,r.DATA]];r.load_case();self.assertEqual(before,[hashlib.sha256(p.read_bytes()).hexdigest() for p in [r.CASE,r.DATA]])
 def test_missing_data_no_fake_receipt(self):
  with tempfile.TemporaryDirectory() as d:self.assertIsNone(r.load_case(Path(d)/'none',r.DATA)['receipt'])
 def test_hash_drift_no_fake_data(self):self.assertEqual(self.case(raw=self.raw+b'\n')['status'],'NOT_MEASURED')
 def test_unlicensed_input_withheld(self):
  for status in ['UNKNOWN','PRIVATE_RESEARCH_ONLY','PUBLIC_REDISTRIBUTABLE']:
   p=copy.deepcopy(self.packet);p['license']['status']=status;self.assertIsNone(self.case(p)['receipt'])
 def test_synthetic_input_withheld(self):
  p=copy.deepcopy(self.packet);p['synthetic']=True;self.assertIsNone(self.case(p)['receipt'])
 def test_wrong_source_withheld(self):
  for k in ['event_source','market_data_source']:
   p=copy.deepcopy(self.packet);p[k]='https://example.org';self.assertIsNone(self.case(p)['receipt'])
 def test_invented_publication_clock_withheld(self):
  for k in ['event_timestamp_utc','source_published_at','event_effective_time']:
   p=copy.deepcopy(self.packet);p[k]='2025-06-05T12:15:00Z';self.assertIsNone(self.case(p)['receipt'])
 def test_future_knowledge_time_withheld(self):
  p=copy.deepcopy(self.packet);p['market_data_retrieved_at']='2025-06-01T00:00:00Z';self.assertIsNone(self.case(p)['receipt'])
 def test_wrong_instrument_and_frequency_rejected(self):
  for old,new in [('EXR.D.USD.EUR.SP00.A','EXR.D.JPY.EUR.SP00.A'),(',D,USD,EUR,',',M,USD,EUR,'),(',USD,0',',EUR,0')]:
   with self.assertRaises(ValueError):r.rates(self.raw.replace(old.encode(),new.encode()))
 def test_duplicate_provider_date_rejected(self):
  lines=self.raw.splitlines();bad=b'\n'.join([lines[0],lines[1],lines[1],*lines[2:]])
  with self.assertRaises(ValueError):r.rates(bad)
 def test_nonfinite_or_negative_rejected(self):
  for bad in [b'NaN',b'-1',b'0']:
   with self.assertRaises(ValueError):r.rates(self.raw.replace(b'1.1419',bad))
 def test_missing_baseline_or_post_refuses_window(self):
  for rows in [[{'observation_date':'2025-06-05','value':'1'}],[{'observation_date':'2025-06-06','value':'1'}]]:
   with self.assertRaises(ValueError):r.calculate('2025-06-05',rows)
 def test_weekend_gap_explicit_no_interpolation(self):
  observations=r.rates(self.raw);x=r.calculate('2025-06-07',observations);self.assertEqual(x['intervening_unobserved_dates'],['2025-06-07','2025-06-08']);self.assertEqual(x['post_event_observation']['observation_date'],'2025-06-09')
 def test_no_mutation_calculation(self):
  rows=r.rates(self.raw);before=copy.deepcopy(rows);r.calculate('2025-06-05',rows);self.assertEqual(rows,before)

class ReactionUI(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  bilingual.BilingualVisualTests.setUpClass();cls.ui=bilingual.BilingualVisualTests();cls.ui.html=bilingual.BilingualVisualTests.html;cls.ui.translations=bilingual.BilingualVisualTests.translations;cls.ui.view=bilingual.BilingualVisualTests.view
 @classmethod
 def tearDownClass(cls):bilingual.BilingualVisualTests.tearDownClass()
 def test_api_receipt_and_current_counts_separate(self):
  v=self.ui.view;self.assertEqual(v['market_reaction_research']['status'],'AVAILABLE');self.assertNotIn(v['market_reaction_research']['event']['event_id'],[e['event_id'] for e in v['events']]);self.assertEqual(v['news_item_count'],len(v['items']))
 def test_real_graph_dates_units_and_localized_boundaries(self):
  x=self.ui.render();self.assertIn('class="reaction-chart"',x['en']);self.assertIn('1.1384',x['en']);self.assertIn('0.237175',x['en']);self.assertIn('EX_POST_MARKET_OBSERVATION',x['zh']);self.assertIn('盤中反應尚未量測',x['zh']);self.assertIn('不宣稱因果效果',x['zh']);self.assertIn('2025/6/5',x['zh']);self.assertIn('data-reaction-index="6"',x['en'])
 def test_missing_case_no_chart(self):
  v=copy.deepcopy(self.ui.view);v['market_reaction_research']={'status':'NOT_MEASURED','receipt':None};x=self.ui.render(view=v);self.assertNotIn('class="reaction-chart"',x['en']);self.assertIn('No prices or chart are fabricated',x['en'])
 def test_existing_product_preserved(self):
  x=self.ui.render();self.assertLess(x['en'].index('id="world-map"'),x['en'].index('id="prediction-market-watch"'));self.assertIn('PREVIEW',x['en']);self.assertIn('NO_RECORDED_HISTORY',x['en']);self.assertIn('id="data-source-status"',x['en']);self.assertTrue(x['unchanged'])

 def test_current_empty_feed_does_not_gain_historical_counts(self):
  v=copy.deepcopy(self.ui.view);v.update(items=[],events=[],news_item_count=0,item_count=0,distinct_event_count=None)
  x=self.ui.render(view=v)
  self.assertNotIn('data-event-id=',bilingual.current_event_markup(x['en']))
  self.assertIn('id="market-reaction-research"',x['en'])
  self.assertIn('Separate from current News counts',x['en'])
