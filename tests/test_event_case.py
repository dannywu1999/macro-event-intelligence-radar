import copy,hashlib,json,socket,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import build_event_case as m
import build_gateway
from contracts_v0 import build_canonical_events

ROOT=Path(__file__).resolve().parents[1]
class CaseTests(unittest.TestCase):
    def setUp(self):self.c=json.loads((ROOT/'event_case.json').read_bytes())
    def test_pinned_inputs(self):
        for n,h in json.loads((ROOT/'event_release.json').read_bytes())['inputs'].items():self.assertEqual(m.sha((ROOT/n).read_bytes()),h)
    def test_m1_byte_preservation(self):
        for n,h in json.loads((ROOT/'m1_preservation.json').read_bytes())['files'].items():self.assertEqual(m.sha((ROOT/'public'/n).read_bytes()),h)
    def test_no_network_build(self):
        with patch.object(socket.socket,'connect',side_effect=AssertionError('NETWORK_NOT_ALLOWED')):
            self.assertEqual(m.render(self.c),m.render(copy.deepcopy(self.c)))
    def test_before_observation_unavailable(self):
        p=m.project_as_of(self.c,'2026-10-14T12:30:00Z')
        self.assertEqual(p['status'],'UNAVAILABLE');self.assertIsNone(p['discovery']);self.assertFalse(p['propositions'])
    def test_news_before_official(self):
        p=m.project_as_of(self.c,self.c['discovery']['recorded_at'])
        self.assertEqual(p['status'],'NEWS_ONLY');self.assertIsNone(p['official_document']);self.assertFalse(p['propositions']);self.assertIsNone(p['title_zh'])
    def test_raw_document_before_review(self):
        p=m.project_as_of(self.c,self.c['official_document']['recorded_at'])
        self.assertEqual(p['status'],'OFFICIAL_DOCUMENT_ONLY_NOT_YET_REVIEWED');self.assertIsNotNone(p['official_document']);self.assertFalse(p['propositions']);self.assertIsNone(p['title_zh']);self.assertIsNone(p['preview'])
    def test_current_preview(self):
        p=m.project_as_of(self.c,self.c['as_of'])
        self.assertEqual(p['status'],'PREVIEW');self.assertEqual(len(p['propositions']),4);self.assertEqual(p['ledger_status'],'UNAVAILABLE_NO_APPROVED_LEDGER')
    def test_canonical_no_inflation_or_translation_identity(self):
        i=self.c['discovery']['item'];single=build_canonical_events([i])['events'];duplicate=build_canonical_events([i,copy.deepcopy(i)])['events']
        self.assertEqual(single,duplicate);self.assertEqual(single[0]['event_id'],self.c['canonical_event']['event_id'])
        c=copy.deepcopy(self.c);c['title_zh']='另一展示翻譯';self.assertEqual(m.validate(c)['canonical_event']['event_id'],single[0]['event_id'])
    def test_no_whole_news_verification_upgrade(self):
        self.assertEqual(self.c['canonical_event']['verification_status'],'UNVERIFIED_NEWS');self.assertEqual(len(self.c['official_evidence']),4)
    def test_explicit_local_first_seen(self):
        self.assertFalse(self.c['canonical_event']['durable_first_seen_proven']);self.assertIn('LOCAL',self.c['canonical_event']['first_detected_scope'])
        for row in self.c['official_packets']:self.assertEqual(row['official_project_first_seen_scope'],'THIS_M2_DOCUMENT_OBSERVATION_ONLY')
        for row in self.c['official_evidence']:self.assertFalse(row['durable_first_seen_proven'])
    def test_conflicting_time_no_latency(self):
        self.assertIsNone(self.c['official_document']['published_at']);self.assertEqual(self.c['detection_latency'],'UNKNOWN')
        self.assertLess(m.instant(self.c['time_conflict']['feed_reported_publication']),m.instant(self.c['time_conflict']['document_scheduled_embargo_release']))
    def test_missing_or_forged_rights_fails(self):
        c=copy.deepcopy(self.c);c['rights']['policy_status']='PENDING'
        with self.assertRaises(ValueError):m.validate(c)
    def test_tampered_proposition_link_fails(self):
        c=copy.deepcopy(self.c);c['propositions'][0]['source_url']='https://example.com/'
        with self.assertRaises(ValueError):m.validate(c)
    def test_unknown_market_values_preserved(self):
        self.assertIsNone(self.c['market_reaction']['value']);self.assertIsNone(self.c['polymarket']['value']);self.assertEqual(self.c['causality'],'NOT_ESTABLISHED')
    def test_nested_public_asset_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'unreviewed.sqlite').write_bytes(b'x')
            with self.assertRaises(ValueError):m.inventory(p)
    def test_manifests_exact_and_match(self):
        path=ROOT/'public/research'/m.SLUG
        self.assertEqual({p.name for p in path.iterdir()},m.CASE_FILES)
        for n,d in json.loads((path/'manifest.json').read_bytes())['files'].items():self.assertEqual(m.sha((path/n).read_bytes()),d['sha256']);self.assertEqual((path/n).stat().st_size,d['bytes'])
    def test_unknown_asof_and_naive_times_fail(self):
        with self.assertRaises(ValueError):m.project_as_of(self.c,'UNKNOWN')
        with self.assertRaises(ValueError):m.project_as_of(self.c,'2026-10-19T18:00:00')
    def test_unsupported_claims_not_official(self):
        self.assertTrue(all(x['status'] in ('UNKNOWN','UNSUPPORTED') and x['value'] is None for x in self.c['unsupported_claims']))
if __name__=='__main__':unittest.main()
