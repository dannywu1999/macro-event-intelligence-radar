"""V4.3 production impact projection and actual served JS; no provider requests."""
import copy,unittest
from tools.stage1b_historical_campaign import radar_impact_hypotheses as impact
import test_radar_v42_news_intelligence as fixtures
import test_bilingual_visual_ui as bilingual

def projection(title,source='Public publisher'):
 return impact.project(fixtures.view([fixtures.article(1,title,source=source)]))['by_article']['https://example.org/1']

class ImpactContract(unittest.TestCase):
 def test_four_supported_mechanisms_have_complete_conditional_contract(self):
  examples={'ECB cuts rates by 25 bps':'MONETARY_POLICY','Government imposes tariffs on imports':'TRADE_POLICY','Oil pipelines transport crude supply':'OIL_SUPPLY','War disrupts shipping supply through Hormuz':'GEOPOLITICAL_SUPPLY'}
  for title,identifier in examples.items():
   with self.subTest(title=title):
    p=projection(title);m=next(m for m in p['mechanisms'] if m['mechanism_id']==identifier);self.assertEqual(m['evidence_status'],'HYPOTHESIS');self.assertTrue(m['trigger_terms']);self.assertTrue(m['conditions']);self.assertTrue(m['counter_scenario']);self.assertTrue(m['next_observation']);self.assertTrue(m['exposed_markets'])
 def test_institution_only_is_insufficient(self):
  for title in ['Opening remarks','ECB annual exhibition','Piero Cipollone: Interview with Corriere della Sera']:
   self.assertEqual(projection(title,source='ECB Press')['status'],'IMPACT_NOT_ESTABLISHED')
 def test_country_or_war_keyword_alone_is_insufficient(self):
  for title in ['China and Taiwan','War in the Middle East','Markets around the world','Oil paintings displayed']:
   p=projection(title);self.assertEqual(p['mechanisms'],[]);self.assertEqual(p['status'],'IMPACT_NOT_ESTABLISHED')
 def test_food_oil_not_wti_brent(self):self.assertEqual(projection('Olive oil prices and oil supply changes')['mechanisms'],[])
 def test_fed_up_is_not_central_bank(self):self.assertEqual(projection('Fed up with interest rates')['mechanisms'],[])
 def test_fed_rates_use_us_curve_without_gold_dxy_or_index_claim(self):
  p=projection('Fed cuts rates by 25 bps');self.assertEqual(p['article_kind']['status'],'REPORTED_RATE_DECISION');m=p['mechanisms'][0]['exposed_markets'][0];self.assertEqual(m['market_id'],'US_RATES');self.assertEqual(m['observation_instruments'],['US Treasury yields']);self.assertIsNone(m['direction'])
 def test_ecb_operations_not_reported_rate_change(self):
  p=projection('ECB amends monetary policy implementation guidelines as part of regular review',source='ECB Press');self.assertEqual(p['article_kind']['status'],'ANALYSIS_OR_CONTEXT');self.assertFalse(p['article_kind']['breaking_event_established']);self.assertEqual(p['mechanisms'][0]['exposed_markets'][0]['market_id'],'EURO_AREA_RATES')
 def test_real_format_infrastructure_analysis_not_new_disruption(self):
  p=projection('Subsea cables and oil pipelines: The infrastructure linking AI, empire, and occupation');self.assertEqual(p['article_kind']['status'],'ANALYSIS_OR_CONTEXT');self.assertFalse(p['article_kind']['breaking_event_established']);self.assertEqual(p['mechanisms'][0]['mechanism_id'],'OIL_SUPPLY');self.assertIn('not evidence that a disruption',p['mechanisms'][0]['explanation']['en']);self.assertEqual(p['market_reaction']['status'],'NOT_MEASURED')
 def test_trade_equities_no_automatic_spy_qqq(self):
  p=projection('Reciprocal trade agreements threaten internet access');m=p['mechanisms'][0]['exposed_markets'][0];self.assertEqual(m['observation_instruments'],[]);self.assertEqual(p['article_kind']['status'],'ANALYSIS_OR_CONTEXT')
 def test_missing_time_and_proxy_are_not_invented_publication(self):
  for kind,time in [('UNKNOWN',None),('SOURCE_DATE_PROXY','2026-10-10T00:00:00Z')]:
   a=fixtures.article(1,'Oil pipelines');a.update(reported_time_kind=kind,reported_at=time);p=impact.project(fixtures.view([a]))['by_article'][a['article_reference']];self.assertEqual(p['source_fact']['reported_at'],time);self.assertEqual(p['source_fact']['reported_time_kind'],kind)
 def test_exact_official_proposition_does_not_confirm_impact(self):
  v=fixtures.view([fixtures.article(1,'Crude oil prices increased')]);e=v['events'][0];e['official_evidence_ids']=['fact'];v['official_evidence']=[dict(official_evidence_id='fact',canonical_event_id=e['event_id'],evidence_status='OFFICIAL_CONFIRMED',fact_proposition='A specific observed fact',published_at=None)];p=impact.project(v)['by_article']['https://example.org/1'];self.assertEqual(p['official_propositions'][0]['evidence_status'],'OFFICIAL_CONFIRMED');self.assertIsNone(p['official_propositions'][0]['published_at']);self.assertTrue(all(m['evidence_status']=='HYPOTHESIS' for m in p['mechanisms']));self.assertEqual(v['events'][0]['verification_status'],'UNVERIFIED_NEWS')
 def test_wrong_or_empty_official_link_rejected(self):
  for field,value in [('canonical_event_id','wrong'),('fact_proposition',''),('evidence_status','UNVERIFIED_NEWS')]:
   v=fixtures.view([fixtures.article(1,'Crude oil supply')]);e=v['events'][0];e['official_evidence_ids']=['f'];f=dict(official_evidence_id='f',canonical_event_id=e['event_id'],evidence_status='OFFICIAL_CONFIRMED',fact_proposition='Fact');f[field]=value;v['official_evidence']=[f];self.assertFalse(impact.project(v)['by_article']['https://example.org/1']['official_propositions'])
 def test_bad_provenance_has_no_hypothesis(self):
  v=fixtures.view([fixtures.article(1,'Crude oil supply')]);v['items'][0]['news_source']['url']='javascript:alert(1)';self.assertEqual(impact.project(v)['hypothesis_article_count'],0)
 def test_ambiguous_membership_has_no_exposure(self):
  v=fixtures.view([fixtures.article(1,'Crude oil supply')]);v['events'].append(copy.deepcopy(v['events'][0]));p=impact.project(v)['by_article']['https://example.org/1'];self.assertIsNone(p['canonical_event_id']);self.assertFalse(p['mechanisms'])
 def test_empty_data_has_no_synthetic_hypothesis(self):self.assertEqual(impact.project(dict(items=[],events=[]))['by_article'],{})
 def test_inputs_unchanged_and_no_synthetic_market_values(self):
  v=fixtures.view([fixtures.article(1,'Oil pipelines and crude supply')]);before=copy.deepcopy(v);p=impact.project(v);self.assertEqual(v,before);i=p['by_article']['https://example.org/1'];self.assertIsNone(i['market_reaction']['observations']);self.assertIsNone(i['market_reaction']['attributed_return']);self.assertEqual(i['novelty_status'],'NOT_ESTABLISHED');self.assertIsNone(i['mechanisms'][0]['exposed_markets'][0]['direction'])

class ImpactRendering(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  bilingual.BilingualVisualTests.setUpClass();cls.ui=bilingual.BilingualVisualTests();cls.ui.html=bilingual.BilingualVisualTests.html;cls.ui.translations=bilingual.BilingualVisualTests.translations;cls.ui.view=bilingual.BilingualVisualTests.view
 @classmethod
 def tearDownClass(cls):bilingual.BilingualVisualTests.tearDownClass()
 def test_api_and_same_typed_diagram_text(self):
  self.assertEqual(self.ui.view['impact_intelligence']['contract'],'IMPACT_HYPOTHESES_V0');r=self.ui.render();self.assertIn('探索影響',r['zh']);self.assertIn('市場反應尚未量測',r['zh']);self.assertIn('成立所需條件',r['zh']);self.assertIn('反例／抵銷情境',r['zh']);self.assertIn('data-mechanism-id="OIL_SUPPLY"',r['en']);self.assertIn('data-market-family="OIL_BENCHMARKS"',r['en']);self.assertTrue(r['unchanged'])
 def test_diagnostics_collapsed_and_news_before_map_before_watch(self):
  r=self.ui.render();self.assertIn('<details id="data-source-status"',r['en']);self.assertLess(r['en'].index('id="macro-brief"'),r['en'].index('id="world-map"'));self.assertLess(r['en'].index('id="world-map"'),r['en'].index('id="prediction-market-watch"'));self.assertGreater(r['en'].index('class="discovery-source-grid"'),r['en'].index('id="prediction-market-watch"'))
 def test_unknown_impact_has_no_invented_diagram(self):
  v=copy.deepcopy(self.ui.view);i=next(iter(v['impact_intelligence']['by_article'].values()));i['mechanisms']=[];i['status']='IMPACT_NOT_ESTABLISHED';r=self.ui.render(view=v);self.assertIn('影響尚未確立',r['zh']);self.assertIn('No sufficiently specific causal input',r['en'])
 def test_untrusted_headline_and_causal_text_escaped(self):
  v=copy.deepcopy(self.ui.view);i=next(i for i in v['impact_intelligence']['by_article'].values() if i['mechanisms']);i['source_fact']['headline']='<img src=x onerror=alert(1)>';i['mechanisms'][0]['explanation']['zh']='<script>bad()</script>';r=self.ui.render(view=v);self.assertNotIn('<img src=x',r['zh']);self.assertNotIn('<script>bad()',r['zh']);self.assertIn('&lt;script&gt;',r['zh'])
