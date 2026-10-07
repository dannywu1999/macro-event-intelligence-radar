"""Exact second-authority evidence; no network or changes to source files."""
import copy,csv,hashlib,json,tempfile,unittest,subprocess
from pathlib import Path
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'demo/radar_public'
class EcbOfficialExpansionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.packet=json.loads((BUNDLE/'ecb-official-packet.json').read_text('utf-8'))
  self.before={p.name:p.read_bytes() for p in (BUNDLE/'official-packet.json',BUNDLE/'ecb-official-packet.json')}
  rows=list(csv.DictReader((BUNDLE/'news/rss_headlines_eia_snapshot.csv').read_text('utf-8').splitlines()))
  rows.append(dict(observed_time=self.packet['official_project_first_seen_at'],event_time='',headline_or_text=self.packet['document_title'],source_name='ECB Press',source_url=self.packet['article_reference']))
  self.news=self.root/'news.json';self.news.write_text(json.dumps(rows),'utf-8')
  self.paths=radar.EvidencePaths(news=self.news,official=BUNDLE/'official-packet.json')
  self.view=radar.build_radar_view(self.paths)
  self.event=next(e for e in self.view['events'] if e['event_id']==self.packet['canonical_event_id'])
  self.evidence=next(e for e in self.view['official_evidence'] if e['authority_name']=='European Central Bank')
 def tearDown(self):
  for name,data in self.before.items():self.assertEqual((BUNDLE/name).read_bytes(),data)
  self.temp.cleanup()
 def projection(self,packet):return radar.build_official_evidence_projection([packet],self.view['items'],self.view['events'])
 def test_two_independent_authorities(self):
  self.assertEqual(len(self.view['official_evidence']),2)
  self.assertEqual(self.evidence['evidence_status'],'OFFICIAL_CONFIRMED')
  self.assertEqual(self.event['verification_status'],'UNVERIFIED_NEWS')
 def test_eia_unchanged(self):
  original=radar.build_radar_view(radar.EvidencePaths(news=BUNDLE/'news',official=BUNDLE/'official-packet.json'))
  self.assertEqual(next(e for e in self.view['official_evidence'] if e['authority_name'].startswith('U.S.')),original['official_evidence'][0])
 def test_deterministic_id_excludes_retrieval(self):
  p=copy.deepcopy(self.packet);p['official_retrieved_at']='2099-01-01T00:00:00Z'
  self.assertEqual(self.projection(p)['official_evidence'][0]['official_evidence_id'],self.evidence['official_evidence_id'])
 def test_wrong_event_rejected(self):
  p={**self.packet,'canonical_event_id':'wrong'};self.assertEqual(self.projection(p)['official_evidence'][0]['evidence_status'],'UNLINKED')
 def test_wrong_article_rejected(self):
  p={**self.packet,'article_reference':'https://example.test/wrong'};self.assertEqual(self.projection(p)['official_evidence'][0]['evidence_status'],'UNLINKED')
 def test_conflicting_existing_article_rejected(self):
  p={**self.packet,'article_reference':self.view['events'][-1]['article_references'][0]}
  if p['article_reference']==self.packet['article_reference']:p['article_reference']=self.view['events'][0]['article_references'][0]
  self.assertNotEqual(self.projection(p)['official_evidence'][0]['evidence_status'],'OFFICIAL_CONFIRMED')
 def test_publication_null(self):self.assertIsNone(self.evidence['published_at'])
 def test_timeline_labels_observation(self):
  entry=next(e for e in self.event['timeline'] if e['entry_type']=='OFFICIAL_EVIDENCE')
  self.assertEqual(entry['timestamp_role'],'EVIDENCE_FIRST_SEEN_AT')
 def test_no_geographic_inference(self):self.assertEqual(self.event['geography_status'],'UNKNOWN');self.assertIsNone(self.event['geography'])
 def test_without_exact_news_no_supplement(self):
  v=radar.build_radar_view(radar.EvidencePaths(news=BUNDLE/'news',official=BUNDLE/'official-packet.json'));self.assertEqual(len(v['official_evidence']),1)
 def test_explicit_external_official_input_isolated(self):
  p=self.root/'external.json';p.write_text('[]','utf-8');v=radar.build_radar_view(radar.EvidencePaths(news=self.news,official=p));self.assertEqual(v['official_evidence'],[])
 def test_generic_ui_escapes_and_labels(self):
  s=(ROOT/'ui/radar_public_showcase_v1.html').read_text('utf-8');self.assertIn('value(e.fact_proposition)',s);self.assertIn('proposition only',s);self.assertIn('specificOnly',s)
 def render(self,view=None):
  node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
  payload=dict(view=view or self.view,html=(ROOT/'ui/radar_public_showcase_v1.html').read_text('utf-8'),translations=(ROOT/'ui/radar_demo_translations.js').read_text('utf-8'))
  result=subprocess.run([str(node),str(ROOT/'tests/ui_render_harness.cjs')],input=json.dumps(payload),capture_output=True,text=True,encoding='utf-8',check=True)
  return json.loads(result.stdout)
 def test_actual_bilingual_ui_two_propositions(self):
  result=self.render()
  for lang in ('en','zh'):
   self.assertIn('European Central Bank',result[lang]);self.assertIn(self.packet['official_fact_proposition'],result[lang]);self.assertIn('UNVERIFIED_NEWS',result[lang]);self.assertEqual(result[lang].count('class="official-record"'),2)
  self.assertIn('Unknown',result['en']);self.assertIn('未知',result['zh']);self.assertTrue(result['unchanged'])
 def test_untrusted_proposition_and_title_escape(self):
  v=copy.deepcopy(self.view);v['official_evidence'][0]['fact_proposition']='<img src=x onerror="alert(1)">';v['events'][0]['event_title']='<script>alert(1)</script>'
  result=self.render(v);self.assertNotIn('<img src=x',result['en']);self.assertNotIn('<script>alert(1)</script>',result['en']);self.assertIn('&lt;img',result['en'])
if __name__=='__main__':unittest.main()
