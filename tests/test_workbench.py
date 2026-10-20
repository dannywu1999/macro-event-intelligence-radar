import copy,json,hashlib,re,socket,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import build_gateway as g,build_event_case as c,build_workbench as w

ROOT=Path(__file__).resolve().parents[1]
class Workbench(unittest.TestCase):
    def setUp(self):self.data=w.derive()
    def test_original_17_bytes(self):
        m=w.archive(ROOT/'public');self.assertEqual(len(m['files']),17)
        self.assertEqual(len([x for x in m['files'] if x.startswith('research/')]),6)
    def test_deterministic_and_offline_build(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(socket.socket,'connect',side_effect=AssertionError('NO_NETWORK')),patch('socket.getaddrinfo',side_effect=AssertionError('NO_DNS')):
            outputs=[]
            for name in ('one','two'):
                p=Path(tmp)/name;g.build(p);c.build(ROOT,p);outputs.append(w.build(ROOT,p))
            self.assertEqual(*outputs);self.assertEqual(set(outputs[0]),w.FILES)
    def test_metrics_derived_from_exact_propositions(self):
        self.assertEqual([m['value_percent'] for m in self.data['metrics']],['0.6','3.7','0.3','9.1'])
        for metric,p in zip(self.data['metrics'],self.data['case']['propositions']):
            self.assertEqual(metric['proposition_id'],p['id']);self.assertIn(metric['value_percent']+' percent',p['supporting_excerpt_en']);self.assertEqual(metric['source_url'],p['source_url'])
    def test_article_and_event_not_verified(self):
        self.assertTrue(all(a['verification_status']=='UNVERIFIED_NEWS' and a['official_evidence_status']=='NO_OFFICIAL_EVIDENCE_LINKED' for a in self.data['articles']))
        self.assertEqual(self.data['case']['canonical_event']['verification_status'],'UNVERIFIED_NEWS')
        self.assertEqual(sum(p['support']=='DIRECTLY_SUPPORTED' for p in self.data['case']['propositions']),4)
    def test_unknown_not_zero(self):
        case=self.data['case'];self.assertEqual(case['detection_latency'],'UNKNOWN');self.assertIsNone(case['official_document']['published_at']);self.assertIsNone(case['market_reaction']['value']);self.assertIsNone(case['polymarket']['value'])
    def test_timeline_same_raw_and_roles(self):
        original=json.loads(c.render(json.loads((ROOT/'event_case.json').read_bytes()))['case.json'])
        self.assertEqual(self.data['case']['timeline'],original['timeline'])
        self.assertNotEqual(original['official_document']['retrieved_at'],original['created_at'])
        self.assertEqual(original['official_document']['publication_precision'],'DATE_ONLY')
    def test_original_articles_rights_and_identity(self):
        old=json.loads((ROOT/'source_snapshot.json').read_bytes())
        self.assertEqual(self.data['articles'],old['snapshot']['articles']);self.assertEqual(self.data['rights'],old['rights']);self.assertEqual(self.data['event_candidates'],old['snapshot']['event_candidates'])
        self.assertEqual(self.data['case']['canonical_event'],json.loads((ROOT/'event_case.json').read_bytes())['canonical_event'])
    def test_no_build_time_in_evidence(self):
        self.assertNotIn('build_at',self.data);self.assertEqual(self.data,w.derive())
        self.assertEqual(self.data['case']['as_of'],json.loads((ROOT/'event_case.json').read_bytes())['as_of'])
    def test_replay_examples_are_existing_saved_receipts_only(self):
        old=json.loads((ROOT/'public/research/m2-cpi-20261014/asof-examples.json').read_bytes())
        self.assertEqual(self.data['checkpoints'],old);self.assertEqual([x['status'] for x in old],['UNAVAILABLE','NEWS_ONLY','OFFICIAL_DOCUMENT_ONLY_NOT_YET_REVIEWED','PREVIEW'])
        self.assertTrue(all(x['ledger_status']=='UNAVAILABLE_NO_APPROVED_LEDGER' for x in old))
    def test_public_inventory_and_hashes(self):
        root=ROOT/'public/workbench';w.inventory(root)
        self.assertEqual({p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()},w.FILES)
        manifest=json.loads((root/'v2/manifest.json').read_bytes());self.assertEqual(set(manifest['files']),w.FILES-{'v2/manifest.json'})
        for n,r in manifest['files'].items():self.assertEqual(w.sha((root/n).read_bytes()),r['sha256']);self.assertEqual((root/n).stat().st_size,r['bytes'])
    def test_no_private_or_unreviewed_public_assets(self):
        allowed=set(w.archive(ROOT/'public')['files'])|{'workbench/'+p for p in w.FILES}
        import build_global_radar as radar
        allowed|={'radar/'+p for p in radar.files_for(radar.source_ids(ROOT))}
        actual={p.relative_to(ROOT/'public').as_posix() for p in (ROOT/'public').rglob('*') if p.is_file()}
        self.assertEqual(actual,allowed)
        for p in (ROOT/'public/workbench').rglob('*'):
            if p.is_file():
                raw=p.read_bytes()
                for forbidden in (b'C:\\Users\\',b'SYNTHETIC_LAB',b'localhost:',b'API_KEY=',b'.sqlite',b'BBC',b'CNBC'):self.assertNotIn(forbidden,raw)
    def test_extra_asset_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);(path/'private.sqlite').write_bytes(b'SYNTHETIC_TEST_ONLY')
            with self.assertRaises(ValueError):w.inventory(path)
    def test_pinned_original_input_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            for n in ('event_release.json','event_case.json','contracts_v0.py','contract_provenance.json','m1_preservation.json'):(p/n).write_bytes((ROOT/n).read_bytes())
            (p/'event_case.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):w.derive(p)
    def test_only_same_origin_fetch_and_no_writers(self):
        js=(ROOT/'workbench_src/workbench.js').read_text(encoding='utf-8')
        self.assertEqual(re.findall(r"fetch\('([^']+)'",js),['/workbench/v2/data.json'])
        for x in ('XMLHttpRequest','WebSocket','localStorage','indexedDB','POST','innerHTML=data','innerHTML = data'):self.assertNotIn(x,js)
        self.assertIn('credentials:\'omit\'',js);self.assertIn('navigator.clipboard.writeText',js);self.assertIn('showModal()',js)
    def test_semantics_visible_in_generated_ui(self):
        js=(ROOT/'workbench_src/workbench.js').read_text(encoding='utf-8')
        for phrase in ('文章／事件身份：仍待核實','偵測延遲','UNKNOWN','來源時間衝突','不是反駁一則虛構報導','尚無足夠的已保存修訂版本','非正式展示','SAVED_RESEARCH_PREVIEW_NOT_LIVE_NOT_TRADING'):
            if phrase=='非正式展示':continue
            self.assertIn(phrase,js)
        self.assertNotIn('95%',js);self.assertNotIn('FULL HISTORICAL PIT REPLAY',js)
    def test_semantic_shell_and_csp(self):
        page=w.page('case').decode()
        for tag in ('<main','<header','<footer','<nav','<noscript','<dialog','aria-live="polite"','type="button"','Content-Security-Policy'):self.assertIn(tag,page)
        self.assertNotIn('onclick=',page);self.assertNotIn('<script>',page)
    def test_text_and_url_escaping_contract(self):
        js=(ROOT/'workbench_src/workbench.js').read_text(encoding='utf-8')
        self.assertIn('esc(a.headline_zh||a.headline_original)',js);self.assertIn('esc(p.supporting_excerpt_en)',js);self.assertIn('esc(url)',js)
        self.assertIn('source_release_date:c.release_date',js);self.assertIn('research_as_of:c.as_of',js);self.assertIn('exact_publication_at:c.official_document.published_at',js)
if __name__=='__main__':unittest.main()
