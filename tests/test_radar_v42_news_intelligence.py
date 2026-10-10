"""V4.2 real production projection/render functions with isolated synthetic inputs."""
import copy
from datetime import datetime,timedelta,timezone
import unittest
from tools.stage1b_historical_campaign import radar_news_intelligence as n
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as adapter
from tools.stage1b_historical_campaign.radar_context_intelligence import enrich_events
import test_bilingual_visual_ui as bilingual
NOW=datetime(2026,10,10,12,tzinfo=timezone.utc)

def article(i,title='Tariffs affect trade policy',hours=1,kind='REPORTED_TIME',source='Public publisher'):
 return dict(article_reference='https://example.org/'+str(i),title=title,news_source=dict(name=source,url='https://example.org/'+str(i)),reported_at=(NOW-timedelta(hours=hours)).isoformat() if hours is not None else None,reported_time_kind=kind,observed_at=NOW.isoformat(),verification_status='UNVERIFIED_NEWS',event_occurred_at=None)
def view(rows):
 v=dict(items=rows,official_evidence=[],discovery_sources={});v.update(adapter.build_canonical_events(rows));v['events']=enrich_events(v['events'],rows);return v

class NewsIntelligence(unittest.TestCase):
 def test_publication_only_no_stale_filler_or_proxy_future(self):
  v=view([article('new'),article('old',hours=60),article('missing',hours=None),article('proxy',kind='SOURCE_DATE_PROXY'),article('future',hours=-1)])
  self.assertEqual(n.project(v,now=NOW)['brief_article_references'],['https://example.org/new'])
 def test_recent_non_macro_cannot_fill_brief(self):
  self.assertEqual(n.project(view([article('cafe','A new cafe opens')]),now=NOW)['brief_article_references'],[])
 def test_five_max_newest_order_and_no_topic_dedup(self):
  v=view([article(i,hours=i+1) for i in range(8)]);p=n.project(v,now=NOW);self.assertEqual(len(p['brief_article_references']),5);self.assertEqual(p['eligible_development_count'],8);self.assertEqual(p['brief_article_references'][0],'https://example.org/0')
 def test_new_development_on_old_topic_remains_visible(self):
  v=view([article('old',hours=70),article('new','Tariffs raised on semiconductor exports')]);p=n.project(v,now=NOW);self.assertEqual(p['brief_article_references'],['https://example.org/new']);self.assertEqual(len(p['cards']),2)
 def test_same_country_or_institution_not_related(self):
  v=view([article(1,'ECB monetary policy guidelines'),article(2,'ECB monetary policy outlook')]);self.assertEqual(n.project(v,now=NOW)['related_coverage'],[])
 def test_proven_rate_decision_group_and_all_articles_retained(self):
  v=view([article(1,'ECB cuts rates by 25 bps',hours=1),article(2,'ECB lowers interest rates by 25 basis points',hours=2)]);p=n.project(v,now=NOW);self.assertEqual(len(p['related_coverage']),1);self.assertEqual(len(p['brief_article_references']),1);self.assertEqual(len(p['cards']),2);self.assertEqual(p['eligible_article_count'],2)
 def test_fake_event_membership_never_groups(self):
  v=view([article(1),article(2,'Oil supply disrupted')]);v['events'][0]['article_references']=[a['article_reference'] for a in v['items']];v['events']=v['events'][:1];p=n.project(v,now=NOW);self.assertEqual(p['related_coverage'],[]);self.assertEqual(len(p['brief_article_references']),2)
 def test_same_rate_other_day_or_amount_not_related(self):
  for other in [article(2,'ECB cuts rates by 50 bps'),article(2,'ECB cuts rates by 25 bps',hours=25)]:
   self.assertFalse(n.project(view([article(1,'ECB cuts rates by 25 bps'),other]),now=NOW)['related_coverage'])
 def test_exact_proposition_only_not_whole_event_confirmation(self):
  v=view([article(1)]);e=v['events'][0];e['official_evidence_ids']=['fact'];v['official_evidence']=[dict(official_evidence_id='fact',canonical_event_id=e['event_id'],evidence_status='OFFICIAL_CONFIRMED',fact_proposition='One specific fact')];before=copy.deepcopy(v);p=n.project(v,now=NOW);self.assertEqual(p['cards']['https://example.org/1']['official_evidence_count'],1);self.assertEqual(v,before);self.assertEqual(v['events'][0]['verification_status'],'UNVERIFIED_NEWS')
 def test_wrong_link_status_or_empty_fact_never_counted(self):
  for field,value in [('canonical_event_id','wrong'),('evidence_status','UNVERIFIED_NEWS'),('fact_proposition','')]:
   v=view([article(1)]);e=v['events'][0];e['official_evidence_ids']=['fact'];f=dict(official_evidence_id='fact',canonical_event_id=e['event_id'],evidence_status='OFFICIAL_CONFIRMED',fact_proposition='Fact');f[field]=value;v['official_evidence']=[f];self.assertEqual(n.project(v,now=NOW)['cards']['https://example.org/1']['official_evidence_count'],0)
 def test_bad_provenance_not_eligible(self):
  for url in ['javascript:alert(1)','https://user:password@example.org/x','not a url']:
   a=article(1);a['news_source']['url']=url;self.assertFalse(n.project(view([a]),now=NOW)['brief_article_references'])
 def test_reuses_lowercase_curated_institution_context(self):
  v=view([article(1,'Opening remarks',source='ECB Press')]);c=n.project(v,now=NOW)['cards']['https://example.org/1'];self.assertTrue(c['macro_relevant']);self.assertEqual(c['topic'],'MONETARY_POLICY');self.assertIsNotNone(c['context_zh'])
 def test_unsupported_analysis_remains_unknown(self):
  c=n.project(view([article(1,'A local exhibition')]),now=NOW)['cards']['https://example.org/1'];self.assertIsNone(c['relevance_zh']);self.assertEqual(c['novelty_status'],'NOT_ESTABLISHED');self.assertEqual(c['topic'],'UNKNOWN')
 def test_no_mutation_and_no_importance_or_occurrence_claim(self):
  v=view([article(1)]);before=copy.deepcopy(v);p=n.project(v,now=NOW);self.assertEqual(v,before);self.assertNotIn('importance_score',p['cards']['https://example.org/1']);self.assertIsNone(v['items'][0]['event_occurred_at'])
 def test_freshness_clock_reused_for_same_response(self):
  from tools.stage1b_historical_campaign.radar_news_freshness import project
  v=view([article(1)]);v['news_freshness']=project(v,now=NOW);self.assertEqual(n.project(v)['as_of'],v['news_freshness']['as_of']);self.assertEqual(n.project(v)['eligible_article_count'],1)
 def test_official_evidence_only_breaks_equal_publication_ties(self):
  v=view([article('z'),article('a')]);e=next(e for e in v['events'] if e['article_references']==['https://example.org/a']);e['official_evidence_ids']=['fact'];v['official_evidence']=[dict(official_evidence_id='fact',canonical_event_id=e['event_id'],evidence_status='OFFICIAL_CONFIRMED',fact_proposition='Specific fact')];self.assertEqual(n.project(v,now=NOW)['brief_article_references'][0],'https://example.org/a')
 def test_empty_input_has_no_synthetic_events(self):
  p=n.project(view([]),now=NOW);self.assertEqual(p['brief_article_references'],[]);self.assertEqual(p['cards'],{});self.assertEqual(p['eligible_development_count'],0)

class NewsRender(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  bilingual.BilingualVisualTests.setUpClass();cls.ui=bilingual.BilingualVisualTests();cls.ui.html=bilingual.BilingualVisualTests.html;cls.ui.translations=bilingual.BilingualVisualTests.translations;cls.ui.view=bilingual.BilingualVisualTests.view
 @classmethod
 def tearDownClass(cls):bilingual.BilingualVisualTests.tearDownClass()
 def test_served_api_has_projection_and_bilingual_empty_brief(self):
  self.assertIn('news_intelligence',self.ui.view);r=self.ui.render();self.assertIn("Today&#39;s Macro Brief",r['en']);self.assertIn('今日宏觀速覽',r['zh']);self.assertIn('舊稿及日期未知',r['zh']);self.assertTrue(r['unchanged'])
 def test_real_rendered_card_labels_context_button_and_not_translation(self):
  r=self.ui.render();self.assertIn('為何值得查核',r['zh']);self.assertIn('非標題全文翻譯',r['zh']);self.assertIn('後續待查',r['zh']);self.assertIn('具體官方命題',r['zh']);self.assertIn('data-map-event=',r['zh']);self.assertIn('UNVERIFIED_NEWS',r['zh'])
 def test_article_and_interpretation_escape(self):
  v=copy.deepcopy(self.ui.view);a=v['items'][0];a['title']='<img src=x onerror=alert(1)>';c=v['news_intelligence']['cards'][a['article_reference']];c['relevance_zh']='<script>bad()</script>';r=self.ui.render(view=v);self.assertNotIn('<img src=x',r['zh']);self.assertNotIn('<script>bad()',r['zh']);self.assertIn('&lt;script&gt;',r['zh'])
 def test_news_anchor_full_feed_and_map_before_watch(self):
  r=self.ui.render();self.assertIn('<section id="news-items"',r['en']);self.assertEqual(r['en'].count('id="news-items"'),1);self.assertLess(r['en'].index('id="macro-brief"'),r['en'].index('id="latest-developments"'));self.assertLess(r['en'].index('id="world-map"'),r['en'].index('id="prediction-market-watch"'));self.assertNotIn('class="related-news"',r['en'])
