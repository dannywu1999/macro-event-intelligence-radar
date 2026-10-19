from pathlib import Path
import copy,hashlib,importlib.util,json,socket,tempfile,unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('gateway_builder',ROOT/'build_gateway.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
SOURCE=json.loads((ROOT/'source_snapshot.json').read_bytes())
RELEASE=json.loads((ROOT/'release.json').read_bytes())

class GatewayTests(unittest.TestCase):
    def test_reproducible_no_network_build(self):
        with tempfile.TemporaryDirectory() as d,patch.object(socket.socket,'connect',side_effect=AssertionError('NETWORK_FORBIDDEN')),patch('socket.getaddrinfo',side_effect=AssertionError('DNS_FORBIDDEN')):
            a=b.build(Path(d)/'a');c=b.build(Path(d)/'b');self.assertEqual(a,c)
            self.assertEqual(set(a),b.PUBLIC_FILES)
            self.assertEqual(a,{p.name:p.read_bytes() for p in (Path(d)/'a').iterdir()})
    def test_same_data_counts_and_original_fields(self):
        data=b.project(SOURCE,RELEASE)
        self.assertEqual(data['article_count'],7);self.assertEqual(data['event_candidate_count'],7)
        self.assertEqual(data['articles'],SOURCE['snapshot']['articles'])
        self.assertEqual(data['event_candidates'],SOURCE['snapshot']['event_candidates'])
        self.assertEqual(data['latest_observed_data_at'],SOURCE['snapshot']['latest_observed_data_at'])
        self.assertEqual(data['last_successful_update'],SOURCE['snapshot']['last_successful_update'])
    def test_three_clocks_and_build_not_observation(self):
        data=b.project(SOURCE,RELEASE)
        self.assertEqual(data['latest_actual_observation_at'],max((a['observed_at'] for a in data['articles']),key=b.utc))
        self.assertNotEqual(data['latest_actual_observation_at'],RELEASE['gateway_build_at'])
        for a in data['articles']:
            self.assertNotEqual(a['source_reported_at'],a['observed_at'])
            self.assertLessEqual(b.utc(a['observed_at']),b.utc(a['recorded_at']))
    def test_preserved_unknowns_and_authority(self):
        data=b.project(SOURCE,RELEASE)
        self.assertIs(data['live_feed'],False);self.assertIs(data['trading_signal'],False)
        self.assertEqual(data['durable_first_seen_status'],'FIRST_SEEN_NOT_PROVEN')
        self.assertEqual(data['frozen_macroview_status'],'UNAVAILABLE_NO_APPROVED_LEDGER')
        for a in data['articles']:
            self.assertTrue(a['translation_presentation_only'])
            self.assertEqual(a['verification_status'],'UNVERIFIED_NEWS')
            self.assertEqual(a['official_evidence_status'],'NO_OFFICIAL_EVIDENCE_LINKED')
    def test_all_representations_have_original_attribution_and_time(self):
        outputs=b.render(SOURCE,RELEASE)
        self.assertEqual(outputs['events.txt'],outputs['events.md'])
        text=outputs['events.txt'].decode('utf-8')
        for a in SOURCE['snapshot']['articles']:
            for k in ('headline_original','headline_zh','source_url','source_reported_at','observed_at','recorded_at'):
                self.assertIn(a[k],text)
            if a['author']:self.assertIn(a['author'],text)
        self.assertIn('https://creativecommons.org/licenses/by/4.0/',text)
        self.assertIn('unofficial',text)
    def test_public_manifest_and_metadata_integrity(self):
        out=b.render(SOURCE,RELEASE);m=json.loads(out['manifest.json']);metadata=json.loads(out['snapshot-metadata.json'])
        self.assertEqual(set(m['files']),set(out)-{'manifest.json'})
        for name,entry in m['files'].items():
            self.assertEqual(entry['sha256'],hashlib.sha256(out[name]).hexdigest());self.assertEqual(entry['bytes'],len(out[name]))
        self.assertEqual(metadata['events_json_sha256'],hashlib.sha256(out['events.json']).hexdigest())
        self.assertEqual(metadata['compact_source_sha256'],hashlib.sha256((ROOT/'source_snapshot.json').read_bytes()).hexdigest())
    def test_bad_scope_fails_closed(self):
        source=copy.deepcopy(SOURCE);source['snapshot']['live_feed']=True
        with self.assertRaisesRegex(ValueError,'SOURCE_SCOPE_INVALID'):b.render(source,RELEASE)
    def test_false_official_claim_fails_closed(self):
        source=copy.deepcopy(SOURCE);source['snapshot']['articles'][0]['verification_status']='OFFICIAL_CONFIRMED'
        with self.assertRaisesRegex(ValueError,'SOURCE_STATUS_INVALID'):b.render(source,RELEASE)
    def test_missing_author_and_rights_binding_fail_closed(self):
        source=copy.deepcopy(SOURCE);next(r for r in source['rights'] if r['source_id']=='360info')['author']=''
        with self.assertRaisesRegex(ValueError,'ATTRIBUTION_REQUIRED'):b.render(source,RELEASE)
        source=copy.deepcopy(SOURCE);source['rights'][0]['source_url']='https://360info.org/unrelated/'
        with self.assertRaisesRegex(ValueError,'RIGHTS_BINDING_INVALID'):b.render(source,RELEASE)
    def test_timezone_and_url_fail_closed(self):
        source=copy.deepcopy(SOURCE);source['snapshot']['articles'][0]['observed_at']='2026-10-18T13:00:00'
        with self.assertRaisesRegex(ValueError,'SOURCE_TIMEZONE_REQUIRED'):b.render(source,RELEASE)
        source=copy.deepcopy(SOURCE);source['snapshot']['articles'][0]['source_url']='file:///private'
        with self.assertRaisesRegex(ValueError,'SOURCE_URL_INVALID'):b.render(source,RELEASE)
    def test_pinned_source_and_public_allowlist(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'source_snapshot.json').write_bytes(b'{}');(p/'release.json').write_bytes((ROOT/'release.json').read_bytes())
            with patch.object(b,'ROOT',p),self.assertRaisesRegex(ValueError,'PINNED_SOURCE_HASH_MISMATCH'):b.build(p/'public')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'.env').write_text('SYNTHETIC_FAULT_ONLY')
            with self.assertRaisesRegex(ValueError,'UNREVIEWED_PUBLIC_FILE'):b.build(p)
    def test_no_scripts_private_data_or_fake_ux_claims(self):
        out=b.render(SOURCE,RELEASE)
        self.assertNotIn(b'<script',out['index.html']);self.assertNotIn(b'<img',out['index.html'])
        for value in out.values():
            self.assertNotIn(b'C:\\Users\\',value);self.assertNotIn(b'127.0.0.1',value);self.assertNotIn(b'SYNTHETIC_LAB',value)
        self.assertIn(b'NOT_TESTED',out['review-guide.md']);self.assertIn(b'0\xe2\x80\x934',out['review-guide.md'])
        self.assertEqual(out['robots.txt'],b'User-agent: *\nAllow: /\n')

if __name__=='__main__':unittest.main()
