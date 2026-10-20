"""Entirely synthetic offline receipts, including publisher-policy fixtures."""
import json,subprocess,sys,tempfile,unittest,socket
from pathlib import Path
from unittest.mock import patch
from research import m33_public as n,m3_discovery as m,m31_access as a

URL=n.ITEMS['360_energy_capture']
TITLE='SYNTHETIC fossil fuel lobby analysis, not a policy announcement'
PUB='2026-10-15T11:51:22+00:00'
META={'http_status':200,'content_type':'application/rss+xml','response_body_status':'COMPLETE_READ'}
def rss(title=TITLE,author='<strong>Synthetic Alpha</strong><br>Synthetic University',published='Thu, 15 Oct 2026 11:51:22 GMT',url=URL):
    return f'<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><item><title>{title}</title><link>{url}</link><pubDate>{published}</pubDate><dc:creator><![CDATA[{author}]]></dc:creator></item></channel></rss>'.encode()
def item(title=TITLE,author='Synthetic Alpha Synthetic University',license=True,wire=False):
    license_html='<p>Originally published under <a href="https://creativecommons.org/licenses/by/4.0/">Creative Commons</a> by 360info</p>' if license else ''
    return f'<html><meta name="author" content="Synthetic CMS Person"><script>{{"datePublished":"{PUB}"}}</script><h1>{title}</h1><div class="post-meta-authors">Authors <strong>{author}</strong></div><div class="copy main-copy">SYNTHETIC analysis {"Reuters" if wire else ""}{license_html}</div></html>'.encode()

class M33Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.study=Path(self.tmp.name)/'SYNTHETIC_STUDY';self.study.mkdir()
        self.capture('selection_360info')
        a.acquire(self.study/'QUALIFICATION','360_terms','rights_360_terms',True,fetcher=lambda u:(META,b'SYNTHETIC licence all content created and distributed by 360info Creative Commons Attribution 4.0'),contract=n.DOC_CONTRACT)
        a.acquire(self.study/'ITEMS','360_energy_capture','item_360_energy_capture',True,fetcher=lambda u:(META,item()),contract=n.ITEM_CONTRACT)
        row=n.parse('360info',rss())['records'][0];ib=n.bundle(self.study/'ITEMS',n.ITEM_CONTRACT,'item_360_energy_capture');pol=n.bundle(self.study/'QUALIFICATION',n.DOC_CONTRACT,'rights_360_terms')
        self.review={'version':n.VERSION,'reviewed_at':m.now(),'items':{m.article_identity(URL):{'metadata_sha256':n.fingerprint(row),'item_endpoint':'360_energy_capture','item_body_sha256':ib['ack']['response_sha256'],'policy_endpoint':'360_terms','policy_body_sha256':pol['ack']['response_sha256'],'kind':'ANALYSIS_CONTEXT','previous_experiment_presence':'ALREADY_PRESENT_IN_M32_RAW_FEED'}}}
        self.pin_review()
    def tearDown(self):self.tmp.cleanup()
    def pin_review(self):
        (self.study/'PUBLIC_ITEM_REVIEW.json').write_text(json.dumps(self.review),encoding='utf-8');(self.study/'PUBLIC_ITEM_REVIEW_SHA256.json').write_text(json.dumps({'sha256':n.fingerprint(self.review)}))
    def capture(self,request,body=None):return a.acquire(self.study/'DATA','360info',request,True,fetcher=lambda u:(META,body or rss()),parser=n.parse,contract=n.DATA_CONTRACT)
    def proof(self):return n.bundle(self.study/'QUALIFICATION',n.DOC_CONTRACT,'rights_360_terms'),n.bundle(self.study/'ITEMS',n.ITEM_CONTRACT,'item_360_energy_capture')
    def test_default_cli_zero_network_no_creation(self):
        missing=self.study/'NOT_CREATED'
        p=subprocess.run([sys.executable,'-m','research.m33_public','--study',str(missing)],capture_output=True,check=True)
        self.assertEqual(json.loads(p.stdout),{'mode':'OFFLINE','network_requests':0});self.assertFalse(missing.exists())
        with self.assertRaisesRegex(ValueError,'NETWORK_DISABLED'):n.acquire(missing,'360info','cycle_001')
    def test_positive_item_rights_and_real_author_not_cms(self):
        p=n.public_projection(self.study);row=p['records'][0]
        self.assertEqual(row['author_attribution'],'Synthetic Alpha Synthetic University');self.assertNotIn('CMS',row['author_attribution']);self.assertEqual(row['rights']['classification'],'PUBLIC_COMMERCIAL_ELIGIBLE');self.assertEqual(row['kind'],'ANALYSIS_CONTEXT');self.assertFalse(row['trade_ready'])
        self.assertEqual(p['audit']['independent_news_48h'],0);self.assertEqual(p['audit']['analysis_48h'],0);self.assertEqual(p['audit']['analysis_7d'],1)
    def test_missing_license_thirdparty_and_cms_attribution_fail_closed(self):
        row=n.parse('360info',rss())['records'][0];policy,proof=self.proof()
        for content in [item(license=False),item(wire=True),item(author='Synthetic CMS Person')]:
            with self.assertRaises(ValueError):n.item_rights(row,policy,dict(proof,body=content))
    def test_title_publication_and_url_are_bound(self):
        row=n.parse('360info',rss())['records'][0];policy,proof=self.proof()
        for changed in [dict(row,title='SYNTHETIC changed'),dict(row,source_published_at='2026-10-16T00:00:00Z'),dict(row,url='https://360info.org/unreviewed/')]:
            with self.assertRaises(ValueError):n.item_rights(changed,policy,proof)
    def test_private_wire_and_unreviewed_source_rejected(self):
        for ep in ('cna_business','voa_economy','globalvoices','bea_releases'):
            with self.assertRaisesRegex(ValueError,'SELECTED_SOURCE_ONLY'):n.acquire(self.study,ep,'cycle_002',True)
        self.review['items']={};self.pin_review();self.assertEqual(n.project(self.study)['records'],[])
    def test_missing_required_attribution_excluded_by_parser(self):
        self.assertEqual(n.parse('360info',rss(author=''))['records'],[])
    def test_malformed_or_offhost_feed_rejected(self):
        self.assertEqual(n.parse('360info',rss(url='https://restricted.invalid/a'))['records'],[])
        for body in (b'<html>Login</html>',b'<rss',b'<!DOCTYPE rss><rss/>'):
            with self.assertRaises(Exception):n.parse('360info',body)
    def test_timestamp_precision_is_not_inferred(self):
        for text,expected in [('', 'UNKNOWN'),('2026-10-15','DATE_ONLY'),('bad','INVALID'),('2026-10-15T01:00:00','TIMEZONE_UNKNOWN')]:
            row=n.parse('360info',rss(published=text))['records'][0];self.assertEqual(row['publication_precision'],expected)
    def test_duplicate_and_content_change_preserve_first_observation(self):
        first=n.project(self.study)['records'][0]['first_observed_in_M33'];self.capture('again')
        p=n.project(self.study);self.assertEqual(p['audit']['observations']['DUPLICATE'],1);self.assertEqual(p['records'][0]['first_observed_in_M33'],first)
        self.capture('revision',rss(title='SYNTHETIC revised analysis'))
        p=n.project(self.study);self.assertEqual(p['audit']['observations']['UPDATED'],1);self.assertEqual(p['records'],[])
        self.assertEqual(p['audit']['excluded_by_reason']['UNREVIEWED_OR_UPDATED_ITEM'],1)
    def test_asof_hides_later_rights_and_revision(self):
        before=m.read(self.study/'DATA/HTTP/selection_360info.terminal.json')['completed_at']
        self.assertEqual(n.project(self.study,before)['records'],[])
        cut=m.now();old=n.public_projection(self.study,cut);self.capture('later',rss(title='SYNTHETIC later correction'))
        self.assertEqual(n.public_projection(self.study,cut),old)
        self.assertEqual(n.project(self.study,'2000-01-01T00:00:00Z')['records'],[])
        with self.assertRaises(ValueError):n.project(self.study,'2026-10-20T00:00:00')
    def test_review_manifest_mutation_without_new_pin_fails(self):
        p=self.study/'PUBLIC_ITEM_REVIEW.json';p.write_text('{}')
        with self.assertRaisesRegex(ValueError,'REVIEW_MANIFEST_HASH'):n.project(self.study)
    def test_receipt_tamper_or_checkpoint_incomplete_rejected(self):
        p=self.study/'DATA/HTTP/selection_360info.body';p.write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'BODY_INTEGRITY'):n.project(self.study)
    def test_checkpoint_scope_and_request_are_bound(self):
        p=self.study/'ITEMS/HTTP/item_360_energy_capture.ack.json';v=m.read(p);v['scope']='WRONG';p.write_text(json.dumps(v))
        with self.assertRaisesRegex(ValueError,'RECEIPT_IDENTITY'):n.project(self.study)
    def test_request_and_byte_budgets_before_fetch(self):
        with patch.object(a,'accounting',return_value=(34,0)):
            with self.assertRaisesRegex(ValueError,'STUDY_BUDGET'):n.acquire(self.study,'360info','cycle_002',True)
        with patch.object(a,'accounting',return_value=(0,7_000_000)):
            with self.assertRaisesRegex(ValueError,'STUDY_BUDGET'):n.acquire(self.study,'360info','cycle_002',True)
    def test_denial_no_retry_and_other_source_isolation(self):
        result=n.acquire(self.study,'360info','cycle_002',True,fetcher=lambda u:({'http_status':403,'response_body_status':'UNREAD_HTTP_ERROR_BODY'},b''));self.assertEqual(result['status'],'SOURCE_DENIED')
        result=n.acquire(self.study,'360info','cycle_003',True,fetcher=lambda u:(_ for _ in ()).throw(AssertionError('retry')));self.assertEqual(result['status'],'SOURCE_PAUSED_NO_RETRY')
        self.assertEqual(len(n.project(self.study)['records']),1)
    def test_unknown_transport_and_same_reservation_never_retried(self):
        result=n.acquire(self.study,'fed_monetary','cycle_002',True,fetcher=lambda u:(_ for _ in ()).throw(TimeoutError('SYNTHETIC')));self.assertEqual(result['status'],'UNKNOWN')
        result=n.acquire(self.study,'fed_monetary','cycle_002',True,fetcher=lambda u:(_ for _ in ()).throw(AssertionError('retry')));self.assertEqual(result['status'],'ALREADY_RESERVED_NO_RETRY')
    def test_plan_pinning_and_interval(self):
        plan={'version':n.DATA_CONTRACT.version,'experiment_id':'M33-SYNTHETIC','interval_seconds':1800,'max_requests':9,'max_bytes':8_000_000,'sources':['360info','fed_monetary']};a.pin(self.study/'DATA',plan,n.DATA_CONTRACT)
        with self.assertRaisesRegex(ValueError,'MINIMUM_INTERVAL'):n.acquire(self.study,'360info','cycle_002',True)
        with self.assertRaisesRegex(ValueError,'FROZEN_PLAN'):a.pin(self.study/'DATA',dict(plan,max_requests=8),n.DATA_CONTRACT)
    def test_public_allowlist_no_local_receipts_or_paths(self):
        p=n.public_projection(self.study);s=json.dumps(p)
        for forbidden in ('per_request_counts','SYNTHETIC_STUDY','raw_body','receipt_path','secret','C:\\Users'):
            self.assertNotIn(forbidden,s)
        self.assertFalse(p['records'][0]['rights']['images_and_body_included']);self.assertEqual(p['capture'],'OFF')
    def test_restart_offline_projection_no_network_no_write(self):
        before={str(p.relative_to(self.study)):m.sha(p.read_bytes()) for p in self.study.rglob('*') if p.is_file()}
        r=subprocess.run([sys.executable,'-m','research.m33_public','--study',str(self.study),'--public'],capture_output=True,check=True)
        self.assertEqual(len(json.loads(r.stdout)['records']),1)
        self.assertTrue(all(m.sha((self.study/name).read_bytes())==v for name,v in before.items()))
    def test_official_original_policy_positive_scope_and_negative_license(self):
        title='SYNTHETIC Board discount-rate minutes'
        row={'source_id':'fed_monetary','title':title,'url':n.ITEMS['fed_discount_minutes']}
        policy={'body':b"Unless otherwise indicated, information on Board's website is in the public domain and may be copied and distributed without permission."}
        proof={'body':('Board of Governors of the Federal Reserve System '+title).encode(),'ack':{'url':row['url']}}
        self.assertEqual(n.item_rights(row,policy,proof)[3],'OFFICIAL_ORIGIN_DISCOVERY')
        with self.assertRaisesRegex(ValueError,'POLICY_LICENSE'):n.item_rights(row,{'body':b'This material is not in the public domain.'},proof)
    def test_resume_tampered_plan_and_missing_terminal_fail_closed(self):
        plan={'version':n.DATA_CONTRACT.version,'experiment_id':'M33-SYNTHETIC','interval_seconds':1800,'max_requests':9,'max_bytes':8_000_000,'sources':['360info','fed_monetary']}
        a.pin(self.study/'DATA',plan,n.DATA_CONTRACT)
        p=self.study/'DATA/PLAN_SHA256.json';p.write_text('{}')
        # Existing reserved cycle cannot bypass the pinned-plan gate.
        existing=self.study/'DATA/HTTP/cycle_002_360info.reserve.json';m.save(existing,dict(m.read(self.study/'DATA/HTTP/selection_360info.reserve.json'),request_id='cycle_002_360info'))
        with self.assertRaisesRegex(ValueError,'PLAN_HASH'):n.acquire(self.study,'360info','cycle_002',True)
        p.write_text(json.dumps({'sha256':m.sha(m.canonical(plan).encode())}))
        (self.study/'ITEMS/HTTP/item_360_energy_capture.terminal.json').unlink()
        with self.assertRaises(FileNotFoundError):n.project(self.study)
    def test_handoff_preserves_all_required_attribution(self):
        source=n.public_projection(self.study)['records'][0];packet=n.handoff(self.study)['packets'][0]
        for key in ('headline_original','original_url','publisher','author_attribution','rights'):
            self.assertEqual(packet[key],source[key])
        self.assertEqual(packet['rights']['license_url'],'https://creativecommons.org/licenses/by/4.0/');self.assertIn('changes',packet['rights']);self.assertTrue(packet['official_verification_pending'])

if __name__=='__main__':unittest.main()
