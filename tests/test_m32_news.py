"""Synthetic offline M3.2 regression. Does not open real experiment receipts."""
import json,socket,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research import m3_discovery as m,m31_access as a,m32_news as n

META={'http_status':200,'content_type':'application/rss+xml','response_body_status':'COMPLETE_READ'}
def rss(title='SYNTHETIC Bank of Japan may hold interest rates, sources say',published='Tue, 20 Oct 2026 06:00:00 GMT',url='https://www.channelnewsasia.com/business/synthetic-1',author=''):
    return f'<rss><channel><item><title>{title}</title><link>{url}</link><pubDate>{published}</pubDate><author>{author}</author></item></channel></rss>'.encode()

class M32Tests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.study=Path(self.tmp.name);self.root=self.study/'RUN_V2'
    def tearDown(self):self.tmp.cleanup()
    def capture(self,request,body=None):return n.acquire(self.root,'cna_business',request,True,fetcher=lambda url:(dict(META),body or rss()))
    def test_default_cli_is_offline_and_creates_nothing(self):
        r=subprocess.run([sys.executable,'-m','research.m32_news','--root',str(self.root)],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(r.stdout),{'mode':'OFFLINE','network_requests':0});self.assertFalse(self.root.exists())
        with self.assertRaisesRegex(ValueError,'NETWORK_DISABLED'):n.acquire(self.root,'cna_business','x')
    def test_parser_metadata_rights_and_authority(self):
        row=n.parse('cna_business',rss())['records'][0]
        self.assertFalse(row['public_export_allowed']);self.assertEqual(row['authority_role'],'NEWS_DISCOVERY_NOT_OFFICIAL_VERIFICATION')
        self.assertIsNone(row['license_url']);self.assertEqual(row['source_published_at'],'2026-10-20T06:00:00Z');self.assertNotIn('content',row)
    def test_missing_invalid_date_only_and_timezone_not_inferred(self):
        for raw,want in [('', 'UNKNOWN'),('not-time','INVALID'),('2026-10-20','DATE_ONLY'),('2026-10-20T06:00:00','TIMEZONE_UNKNOWN')]:
            r=n.parse('cna_business',rss(published=raw))['records'][0];self.assertEqual(r['publication_precision'],want)
            if want!='DATE_ONLY':self.assertIsNone(r['source_published_at'])
    def test_safe_url_malformed_xml_and_cc_attribution(self):
        self.assertEqual(n.parse('cna_business',rss(url='https://unreviewed.invalid/a'))['records'],[])
        for bad in (b'<html>login</html>',b'<rss',b'<!DOCTYPE rss><rss/>'):
            with self.assertRaises(Exception):n.parse('cna_business',bad)
        self.assertEqual(n.parse('globalvoices',rss(url='https://globalvoices.org/a'))['summary']['rejected_by_reason'],{'MISSING_ATTRIBUTION':1})
    def test_market_wrap_excluded_and_hypotheses_not_decisions(self):
        self.assertIsNone(n.relevance({'title':'SYNTHETIC equities slide and oil rises ahead of fictional earnings'}))
        self.assertIsNone(n.relevance({'title':'SYNTHETIC tech company announces IPO'}))
        self.assertEqual(n.relevance({'title':'SYNTHETIC OPEC cuts oil production'}),'ENERGY_SUPPLY')
        self.capture('first');c=n.project(self.root)['event_candidates'][0]
        self.assertEqual(c['official_status'],'OFFICIAL_VERIFICATION_PENDING');self.assertFalse(c['trade_ready']);self.assertEqual(c['detection_latency'],'UNKNOWN');self.assertEqual(c['claim_type'],'REPORTED_EXPECTATION_OR_ANONYMOUS_REPORT')
    def test_duplicate_updates_and_tracking_identity_preserve_firstseen(self):
        self.capture('first');r1=n.project(self.root);old=r1['articles'][0]
        self.capture('second',rss(url='https://www.channelnewsasia.com/business/synthetic-1?utm_source=test'))
        # normalized article identity is stable, but content uses normalized URL too.
        self.assertEqual(n.project(self.root)['observations'][-1]['status'],'DUPLICATE')
        self.capture('third',rss(title='SYNTHETIC Bank of Japan raises rate forecast'))
        r=n.project(self.root);self.assertEqual(r['observations'][-1]['status'],'UPDATED');self.assertEqual(r['articles'][0]['first_observed_at'],old['first_observed_at']);self.assertEqual(r['article_count'],1)
    def test_similar_headlines_different_urls_not_merged(self):
        self.capture('first');self.capture('second',rss(url='https://www.channelnewsasia.com/business/synthetic-2'))
        r=n.project(self.root);self.assertEqual(r['article_count'],2);self.assertEqual(len({x['event_candidate_id'] for x in r['event_candidates']}),2)
    def test_asof_excludes_later_correction_and_future_source(self):
        self.capture('first');r=n.project(self.root);cut=r['as_of']
        self.capture('second',rss(title='SYNTHETIC Bank of Japan corrected forecast'))
        old=n.project(self.root,cut);self.assertEqual(old['articles'][0]['title'],r['articles'][0]['title']);self.assertEqual(len(old['observations']),1)
        self.assertEqual(n.project(self.root,'2000-01-01T00:00:00Z')['articles'],[])
        with self.assertRaises(ValueError):n.project(self.root,'2026-10-20T00:00:00')
        self.capture('third',rss(published='Wed, 20 Oct 2099 06:00:00 GMT'))
        self.assertEqual(n.project(self.root)['candidate_count'],0)
    def test_hash_ack_identity_clock_tampering_rejected(self):
        self.capture('first');p=self.root/'HTTP/first.body';p.write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'RECEIPT_INTEGRITY'):n.project(self.root)
    def test_resume_spent_and_unknown_never_retries(self):
        self.capture('first');calls=[]
        r=n.acquire(self.root,'cna_business','first',True,fetcher=lambda u:calls.append(u));self.assertEqual(r['status'],'ALREADY_RESERVED_NO_RETRY');self.assertEqual(calls,[])
        def timeout(url):raise TimeoutError('synthetic')
        r=n.acquire(self.root,'cna_business','second',True,fetcher=timeout);self.assertEqual(r['status'],'UNKNOWN')
        r=n.acquire(self.root,'cna_business','third',True,fetcher=lambda u:calls.append(u));self.assertEqual(r['status'],'SOURCE_PAUSED_NO_RETRY');self.assertEqual(calls,[])
    def test_denial_isolated_and_parse_failure_keeps_ack(self):
        r=n.acquire(self.root,'cna_business','deny',True,fetcher=lambda u:({'http_status':403,'response_body_status':'UNREAD_HTTP_ERROR_BODY'},b''));self.assertEqual(r['status'],'SOURCE_DENIED')
        r=n.acquire(self.root,'globalvoices','bad',True,fetcher=lambda u:(META,b'<html>Login</html>'));self.assertEqual(r['status'],'PARSE_FAILED');self.assertTrue((self.root/'HTTP/bad.ack.json').exists())
    def test_shared_budget_includes_other_namespace(self):
        a.setup(self.root,n.CONTRACT)
        with patch.object(a,'accounting',return_value=(40,0)):
            with self.assertRaisesRegex(ValueError,'STUDY_BUDGET'):self.capture('over')
        with patch.object(a,'accounting',return_value=(0,7_000_000)):
            with self.assertRaisesRegex(ValueError,'STUDY_BUDGET'):self.capture('bytes')
    def test_plan_and_registry_cannot_drift(self):
        plan={'version':n.VERSION,'experiment_id':'M32-SYNTHETIC','interval_seconds':1800,'max_requests':8,'max_bytes':8_000_000,'sources':['cna_business']}
        self.capture('selection_cna_business');a.pin(self.root,plan,n.CONTRACT)
        with self.assertRaisesRegex(ValueError,'MINIMUM_INTERVAL'):self.capture('cycle_002_cna_business')
        with self.assertRaisesRegex(ValueError,'NO_NEW_PROBES'):self.capture('arbitrary')
        with self.assertRaisesRegex(ValueError,'FROZEN_PLAN'):a.pin(self.root,dict(plan,max_requests=9),n.CONTRACT)
        other=a.AccessContract(n.VERSION,'M32','M32_IDENTITY.json',n.CONTRACT.scope,118,16_000_000,5,dict(n.ENDPOINTS,cna_business='https://invalid.test'),dict(n.CONTRACT.sources),dict(n.CONTRACT.families))
        with self.assertRaisesRegex(ValueError,'ROOT_IDENTITY'):a.setup(self.root,other)
    def test_no_network_for_offline_projection(self):
        self.capture('first')
        with patch.object(socket,'create_connection',side_effect=AssertionError('network')):
            self.assertEqual(n.project(self.root)['article_count'],1)
        self.assertFalse(any(self.study.rglob('*.sqlite')))
    def test_projection_is_read_only_and_requires_success_checkpoint(self):
        with self.assertRaises(FileNotFoundError):n.project(self.root)
        self.assertFalse(self.root.exists());self.capture('first')
        p=self.root/'HTTP/first.terminal.json';p.unlink()
        with self.assertRaises(FileNotFoundError):n.project(self.root)
    def test_stem_and_scope_are_bound(self):
        self.capture('first');p=self.root/'HTTP/first.ack.json';v=m.read(p);v['scope']='WRONG';p.write_text(json.dumps(v))
        with self.assertRaisesRegex(ValueError,'VERSION_BINDING'):n.project(self.root)
    def test_wrong_stem_version_and_clock_rejected(self):
        self.capture('first');base=self.root/'HTTP'
        p=base/'first.parsed.json';p.rename(base/'moved.parsed.json')
        with self.assertRaisesRegex(ValueError,'STEM_BINDING'):n.project(self.root)
        (base/'moved.parsed.json').rename(p)
        reserve=base/'first.reserve.json';v=m.read(reserve);v['experiment_version']='M3';reserve.write_text(json.dumps(v))
        with self.assertRaisesRegex(ValueError,'VERSION_BINDING'):n.project(self.root)
        v['experiment_version']=n.VERSION;reserve.write_text(json.dumps(v))
        ack=base/'first.ack.json';v=m.read(ack);v['started_at']='2099-01-01T00:00:00Z';ack.write_text(json.dumps(v))
        with self.assertRaisesRegex(ValueError,'CLOCK_OR_ACK'):n.project(self.root)
    def test_m31_default_ack_schema_remains_unchanged(self):
        root=self.study/'LEGACY_M31'
        a.acquire(root,'bea_releases','first',True,fetcher=lambda u:(META,b'x'))
        self.assertEqual(m.read(root/'HTTP/first.ack.json')['scope'],'M31_ISOLATED_RESEARCH')
    def test_official_calendar_scope_asof_and_tampering(self):
        self.capture('first');before=n.project(self.root)['as_of']
        official=self.study/'OFFICIAL'
        body=b'<html><h2 id="p2026">2026</h2><table><tr><td>Oct. 29 (Thurs.), 30 (Fri.)</td></tr></table><h2>2027</h2></html>'
        n.acquire(official,'boj_schedule','handoff_boj_schedule',True,fetcher=lambda u:({'http_status':200,'content_type':'text/html'},body),official=True)
        self.assertEqual(n.official_context(official,'boj_schedule',before)['status'],'UNAVAILABLE_AS_OF')
        packet=n.handoff(n.project(self.root),official)[0]
        self.assertEqual(packet['reported_rate_or_forecast_status'],'OFFICIAL_VERIFICATION_PENDING');self.assertEqual(packet['official_context']['status'],'OFFICIAL_CONTEXT_VERIFIED');self.assertTrue(packet['official_context']['does_not_verify_news_forecast'])
        p=official/'HTTP/handoff_boj_schedule.body';p.write_bytes(body+b'changed')
        with self.assertRaisesRegex(ValueError,'OFFICIAL_BODY'):n.official_context(official,'boj_schedule',m.now())
    def test_wrong_year_is_not_verified(self):
        body=b'<html><h2 id="p2026">2026</h2><p>Jan. 1</p><h2 id="p2027">2027</h2><p>Oct. 29 (Thurs.), 30 (Fri.)</p></html>'
        root=self.study/'OFFICIAL';n.acquire(root,'boj_schedule','handoff_boj_schedule',True,fetcher=lambda u:({'http_status':200},body),official=True)
        self.assertEqual(n.official_context(root,'boj_schedule',m.now())['status'],'OFFICIAL_VERIFICATION_PENDING')
    def test_windows_cli_json_is_encoding_independent(self):
        self.capture('first',rss(title='SYNTHETIC interest rates in \u6e2c\u8a66 \U0001f310'))
        r=subprocess.run([sys.executable,'-m','research.m32_news','--root',str(self.root),'--project'],capture_output=True,check=True)
        self.assertTrue(all(b<128 for b in r.stdout));self.assertIn('\U0001f310',json.loads(r.stdout)['articles'][0]['title'])

if __name__=='__main__':unittest.main()
