"""Pure V0 freeze and actual read-only API/UI preview; explicit synthetic links only."""
import copy,csv,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tools.stage1b_historical_campaign import radar_macroview_freeze as macro
from tools.stage1b_historical_campaign import radar_market_expectations as market
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign import radar_web_server as app
ROOT=Path(__file__).resolve().parents[1];BUNDLE=ROOT/'demo/radar_public';NOW='2026-10-07T03:00:00Z'
class MacroViewTests(unittest.TestCase):
 def setUp(self):
  self.view=radar.build_radar_view(radar.EvidencePaths(news=BUNDLE/'news',official=BUNDLE/'official-packet.json'))
  self.eid=next(e['event_id'] for e in self.view['events'] if e['official_evidence_count']);self.event=next(e for e in self.view['events'] if e['event_id']==self.eid)
 def freeze(self,view=None,**kwargs):return macro.freeze_macroview(view or self.view,self.eid,freeze_key=kwargs.pop('freeze_key','FIXTURE_FREEZE_1'),**kwargs)
 def with_expectation(self):
  raw=json.loads((ROOT/'tests/fixtures/polymarket_expectations.json').read_text('utf-8'));v=copy.deepcopy(self.view);v.update(market.project_expectations(v['events'],market.parse_markets(raw,NOW),{self.eid:'fixture-market-01'}));return v
 def test_deterministic(self):self.assertEqual(self.freeze(),self.freeze(copy.deepcopy(self.view)))
 def test_explicit_key_changes_id(self):self.assertNotEqual(self.freeze()['macroview_id'],self.freeze(freeze_key='FIXTURE_FREEZE_2')['macroview_id'])
 def test_explicit_time_preserved(self):self.assertEqual(self.freeze(frozen_at=NOW)['frozen_at'],NOW)
 def test_no_clock_fallback(self):self.assertIsNone(self.freeze()['frozen_at'])
 def test_missing_key_rejected(self):
  for key in [None,'',123]:
   with self.assertRaises(macro.MacroViewError):self.freeze(freeze_key=key)
 def test_invalid_time_rejected(self):
  for time in ['bad','2026-01-01',123]:
   with self.assertRaises(macro.MacroViewError):self.freeze(frozen_at=time)
 def test_eia_partial_evidence_not_whole_fact(self):f=self.freeze();self.assertEqual(f['fact_state'],'PARTIAL_OFFICIAL_EVIDENCE');self.assertEqual(f['snapshot']['event']['verification_status'],'UNVERIFIED_NEWS');self.assertIsNone(f['snapshot']['official_evidence'][0]['published_at'])
 def test_news_only(self):eid=next(e['event_id'] for e in self.view['events'] if not e['official_evidence_count']);f=macro.freeze_macroview(self.view,eid,freeze_key='fixture');self.assertEqual(f['fact_state'],'NEWS_ONLY');self.assertIn('NO_OFFICIAL_EVIDENCE',f['unknowns'])
 def test_expectation_none(self):self.assertEqual(self.freeze()['expectation_state'],'NONE');self.assertIn('NO_LINKED_MARKET_EXPECTATION',self.freeze()['unknowns'])
 def test_unknowns_preserved(self):f=self.freeze();self.assertIn('EVENT_OCCURRENCE_TIME_UNKNOWN',f['unknowns']);self.assertIn('GEOGRAPHY_UNKNOWN',f['unknowns']);self.assertIn('OFFICIAL_PUBLICATION_TIME_UNKNOWN',f['unknowns']);self.assertIsNone(f['snapshot']['event']['geography'])
 def test_full_copied_contents(self):f=self.freeze();self.assertEqual(f['snapshot']['official_evidence'][0]['fact_proposition'],self.view['official_evidence'][0]['fact_proposition']);self.assertEqual(len(f['snapshot']['news']),len(self.event['article_references']))
 def test_new_news_cannot_mutate_old(self):f=self.freeze();old=copy.deepcopy(f);v=copy.deepcopy(self.view);next(i for i in v['items'] if i['article_reference'] in self.event['article_references'])['title']='Changed fixture reporting';new=self.freeze(v);self.assertEqual(f,old);self.assertNotEqual(f['macroview_id'],new['macroview_id'])
 def test_new_fact_cannot_mutate_old(self):f=self.freeze();old=copy.deepcopy(f);v=copy.deepcopy(self.view);v['official_evidence'][0]['fact_proposition']='Different fixture proposition';new=self.freeze(v);self.assertEqual(f,old);self.assertNotEqual(f['macroview_id'],new['macroview_id'])
 def test_changed_price_cannot_mutate_old(self):v=self.with_expectation();f=self.freeze(v);old=copy.deepcopy(f);v['market_expectations'][0]['probabilities'][0]='0.75';new=self.freeze(v);self.assertEqual(f,old);self.assertNotEqual(f['macroview_id'],new['macroview_id']);self.assertEqual(f['snapshot']['market_expectations'][0]['probabilities'][0],'0.6200')
 def test_nested_source_mutation_isolated(self):f=self.freeze();self.view['items'][0]['news_source']['name']='Mutated';self.view['official_evidence'][0]['fact_proposition']='Mutated';self.assertNotIn('Mutated',json.dumps(f))
 def test_frozen_output_does_not_mutate_source(self):before=copy.deepcopy(self.view);f=self.freeze();f['snapshot']['official_evidence'][0]['fact_proposition']='Mutated';self.assertEqual(self.view,before)
 def test_expectation_does_not_change_facts(self):f=self.freeze(self.with_expectation());self.assertEqual(f['fact_state'],self.freeze()['fact_state']);self.assertEqual(f['expectation_state'],'EXPECTATION_PRESENT');self.assertEqual(f['snapshot']['official_evidence'],self.freeze()['snapshot']['official_evidence'])
 def test_fact_does_not_change_expectation(self):v=self.with_expectation();f=self.freeze(v);v['official_evidence'][0]['fact_proposition']='Updated fixture fact';new=self.freeze(v);self.assertEqual(f['snapshot']['market_expectations'],new['snapshot']['market_expectations'])
 def test_geography_and_timeline_independent(self):before=copy.deepcopy(self.view);self.freeze(self.with_expectation());self.assertEqual(before,self.view)
 def test_changed_geo_snapshot_not_inferred(self):v=copy.deepcopy(self.view);next(e for e in v['events'] if e['event_id']==self.eid)['geography']={'explicit_fixture':True};f=self.freeze(v);self.assertEqual(f['snapshot']['event']['geography'],{'explicit_fixture':True});self.assertIn('GEOGRAPHY_UNKNOWN',f['unknowns'])
 def test_no_decision_fields_even_if_input_injected(self):v=copy.deepcopy(self.view);next(e for e in v['events'] if e['event_id']==self.eid).update(direction='LONG',instrument='fixture',order='fixture',confidence=1);f=self.freeze(v);self.assertTrue(all(k not in f and k not in f['snapshot']['event'] for k in ['direction','instrument','order','confidence','position','contract']));self.assertNotIn('LONG',json.dumps(f))
 def test_exact_event_required(self):
  with self.assertRaises(macro.MacroViewError):macro.freeze_macroview(self.view,'wrong',freeze_key='fixture')
 def test_duplicate_event_rejected(self):v=copy.deepcopy(self.view);v['events'].append(v['events'][0]);eid=v['events'][0]['event_id'];self.assertRaises(macro.MacroViewError,macro.freeze_macroview,v,eid,freeze_key='fixture')
 def test_missing_reference_rejected(self):v=copy.deepcopy(self.view);v['official_evidence']=[];self.assertRaises(macro.MacroViewError,self.freeze,v)
 def test_wrong_authority_rejected(self):v=copy.deepcopy(self.view);v['official_evidence'][0]['authority_role']='EXPECTATION_SENSOR';self.assertRaises(macro.MacroViewError,self.freeze,v)
 def test_cross_event_fact_rejected(self):v=copy.deepcopy(self.view);v['official_evidence'][0]['canonical_event_id']='wrong';self.assertRaises(macro.MacroViewError,self.freeze,v)
 def test_cross_event_expectation_rejected(self):v=self.with_expectation();v['market_expectations'][0]['canonical_event_id']='wrong';self.assertRaises(macro.MacroViewError,self.freeze,v)
 def test_preview_explicit_nonpersisted(self):p=macro.preview_macroview(self.view,self.eid);self.assertTrue(p['preview_only']);self.assertFalse(p['persisted']);self.assertIsNone(p['frozen_at']);self.assertEqual(p['contract_version'],'MACROVIEW_PREVIEW_V0');self.assertTrue(p['macroview_id'].startswith('macroview-preview-v0-'))
 def test_empty_preview_no_fake_event(self):self.assertEqual(macro.build_previews({'events':[]}),[])
 def test_preview_readonly_and_bounded(self):before=copy.deepcopy(self.view);p=macro.build_previews(self.view);self.assertEqual(len(p),5);self.assertEqual(before,self.view)
 def test_ecb_second_authority_example(self):
  packet=json.loads((BUNDLE/'ecb-official-packet.json').read_text('utf-8'));rows=list(csv.DictReader((BUNDLE/'news/rss_headlines_eia_snapshot.csv').read_text('utf-8').splitlines()));rows.append(dict(observed_time=packet['official_project_first_seen_at'],event_time='',headline_or_text=packet['document_title'],source_name='ECB Press',source_url=packet['article_reference']))
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'news.json';p.write_text(json.dumps(rows),'utf-8');v=radar.build_radar_view(radar.EvidencePaths(news=p,official=BUNDLE/'official-packet.json'));f=macro.freeze_macroview(v,packet['canonical_event_id'],freeze_key='ECB_FIXTURE_FREEZE');self.assertEqual(f['fact_state'],'PARTIAL_OFFICIAL_EVIDENCE');self.assertEqual(f['expectation_state'],'NONE');self.assertEqual(f['snapshot']['official_evidence'][0]['authority_name'],'European Central Bank');self.assertIsNone(f['snapshot']['official_evidence'][0]['published_at'])
 def test_api_preview_no_write_no_fetch(self):
  before={n:(BUNDLE/n).read_bytes() for n in ['official-packet.json','ecb-official-packet.json','news/rss_headlines_eia_snapshot.csv']}
  with patch.dict(os.environ,{'RADAR_DATA_ROOT':str(BUNDLE),'GLOBAL_EVENT_RADAR_NEWS_PATH':'news','GLOBAL_EVENT_RADAR_OFFICIAL_PATH':'official-packet.json'}),patch.object(market,'fetch_gamma',side_effect=AssertionError('NETWORK_FORBIDDEN')):v=app.feed_view()
  self.assertEqual(len(v['macroview_previews']),5);self.assertTrue(v['read_only']);self.assertEqual(before,{n:(BUNDLE/n).read_bytes() for n in before})
 def test_actual_bilingual_ui_preview(self):
  v=copy.deepcopy(self.view);v['macroview_previews']=macro.build_previews(v);node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe';payload=dict(view=v,html=(ROOT/'ui/radar_public_showcase_v1.html').read_text('utf-8'),translations=(ROOT/'ui/radar_demo_translations.js').read_text('utf-8'));r=subprocess.run([str(node),str(ROOT/'tests/ui_render_harness.cjs')],input=json.dumps(payload),capture_output=True,text=True,encoding='utf-8',check=True);ui=json.loads(r.stdout);self.assertIn('MacroView Preview',ui['en']);self.assertIn('宏觀視圖預覽',ui['zh']);self.assertIn('not a persisted frozen snapshot',ui['en']);self.assertIn('事實證據',ui['zh']);self.assertIn('未知資訊',ui['zh']);self.assertEqual(ui['en'].count('class="macroview-preview"'),5);self.assertTrue(ui['unchanged'])
 def test_news_reference_required(self):v=copy.deepcopy(self.view);next(e for e in v['events'] if e['event_id']==self.eid)['article_references']=[];self.assertRaises(macro.MacroViewError,self.freeze,v)
 def test_new_official_identity_changes_freeze(self):
  old=self.freeze();v=copy.deepcopy(self.view);fact=copy.deepcopy(v['official_evidence'][0]);fact['official_evidence_id']='fixture-additional-proposition';fact['fact_proposition']='Explicit additional synthetic proposition';v['official_evidence'].append(fact);next(e for e in v['events'] if e['event_id']==self.eid)['official_evidence_ids'].append(fact['official_evidence_id']);new=self.freeze(v);self.assertNotEqual(old['macroview_id'],new['macroview_id']);self.assertEqual(len(old['snapshot']['official_evidence']),1);self.assertEqual(len(new['snapshot']['official_evidence']),2)
if __name__=='__main__':unittest.main()
