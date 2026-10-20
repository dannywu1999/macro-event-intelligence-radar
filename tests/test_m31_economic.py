"""Synthetic fixtures only. Never reads M3/M3.1 real experiment directories."""
import json,socket,subprocess,sys,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from research import m3_discovery as m
from research import m31_access as a,m31_economic as e

PLAN={'version':a.VERSION,'experiment_id':'M31-SYNTHETIC-TEST','interval_seconds':1800,'max_requests':80,'max_bytes':20_000_000,'sources':['bls_api','bea_releases']}
def bls(endpoint='bls_cpi',value='123.450',period='M09',footnotes=None):
    return json.dumps({'status':'REQUEST_SUCCEEDED','message':[],'Results':{'series':[{'seriesID':e.SERIES[endpoint][0],'data':[{'year':'2026','period':period,'value':value,'footnotes':[{}] if footnotes is None else footnotes}]}]}}).encode()
def bea(date='2026-09-30T08:30:00-04:00',title='Personal Income and Outlays, SYNTHETIC test',url='/news/2026/synthetic-pce'):
    return f'<html><table><tr class="release-row"><td><a href="{url}">{title}</a></td><td><time datetime="{date}">September 30, 2026</time></td></tr></table></html>'.encode()
META={'http_status':200,'content_type':'application/json','response_body_status':'COMPLETE_READ'}

class M31Tests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)/'SYNTHETIC';a.setup(self.root)
    def tearDown(self):self.tmp.cleanup()
    def fetch(self,url):
        endpoint=next(k for k,v in a.ENDPOINTS.items() if v==url)
        return dict(META),bea() if endpoint=='bea_releases' else bls(endpoint)
    def capture_fixture(self,request,endpoint,body,when):
        result=e.parse(endpoint,body);stem=self.root/'HTTP'/request;stem.parent.mkdir(exist_ok=True)
        Path(str(stem)+'.body').write_bytes(body)
        m.save(Path(str(stem)+'.ack.json'),{'request_id':request,'endpoint_id':endpoint,'url':a.ENDPOINTS[endpoint],'retrieved_at':when,'recorded_at':when,'http':META,'response_sha256':m.sha(body),'response_bytes':len(body)})
        m.save(Path(str(stem)+'.parsed.json'),{'request_id':request,'endpoint_id':endpoint,'retrieved_at':when,'http_ack_recorded_at':when,'recorded_at':when,'response_sha256':m.sha(body),'result':result})
    def test_valid_bls_values_and_true_series_semantics(self):
        for ep in e.SERIES:
            row=e.parse(ep,bls(ep))['records'][0]
            self.assertEqual(row['series_id'],e.SERIES[ep][0]);self.assertIsNone(row['source_published_at']);self.assertEqual(row['publication_precision'],'UNKNOWN');self.assertEqual(row['reference_period_precision'],'MONTH_ONLY')
    def test_missing_value_and_preliminary_footnote_preserved(self):
        row=e.parse('bls_cpi',bls(value='-',footnotes=[{'code':'X','text':'SYNTHETIC unavailable'}]))['records'][0]
        self.assertIsNone(row['value']);self.assertEqual(row['value_raw'],'-');self.assertEqual(row['value_status'],'SOURCE_UNAVAILABLE');self.assertEqual(row['footnotes'][0]['code'],'X')
        self.assertEqual(e.parse('bls_cpi',bls(period='M13'))['records'][0]['reference_period_precision'],'ANNUAL_AVERAGE')
    def test_error_login_wrong_series_invalid_values_fail(self):
        for body in [b'<html>Login</html>',b'{',b'{}',bls(value='NaN'),bls(value='word'),bls(period='M14'),bls(endpoint='bls_payroll')]:
            with self.assertRaises((ValueError,TypeError)):e.parse('bls_cpi',body)
    def test_bea_pce_is_not_cpi_or_other_state_pce(self):
        row=e.parse('bea_releases',bea())['records'][0]
        self.assertEqual(row['category'],'INFLATION_PCE_NOT_CPI');self.assertEqual(row['source_published_at'],'2026-09-30T12:30:00Z');self.assertEqual(row['record_id'],m.article_identity(row['source_url']))
        self.assertEqual(e.parse('bea_releases',bea(title='State PCE, 2025'))['records'],[])
    def test_missing_invalid_date_only_timezone_are_not_inferred(self):
        for raw,precision in [('', 'UNKNOWN'),('not-a-date','INVALID'),('2026-09-30','DATE_ONLY'),('2026-09-30T08:30:00','TIMEZONE_UNKNOWN')]:
            row=e.parse('bea_releases',bea(date=raw))['records'][0];self.assertEqual(row['publication_precision'],precision)
            if precision!='DATE_ONLY':self.assertIsNone(row['source_published_at'])
    def test_malformed_or_off_host_html_fails(self):
        for body in [b'<html>login</html>',b'<tr class="release-row"><a href="/news/x">broken',bea(url='https://unreviewed.invalid/news/x')]:
            with self.assertRaises(ValueError):e.parse('bea_releases',body)
    def test_default_cli_zero_network_and_no_root_creation(self):
        missing=Path(self.tmp.name)/'NOT_CREATED'
        with patch.object(socket,'create_connection',side_effect=AssertionError('NETWORK')):
            with self.assertRaisesRegex(ValueError,'NETWORK_DISABLED'):a.acquire(missing,'bls_cpi','probe_off',False)
        p=subprocess.run([sys.executable,'-B','-m','research.m31_access','--root',str(missing)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['network_requests'],0);self.assertFalse(missing.exists())
    def test_denial_pauses_family_and_does_not_retry(self):
        calls=[]
        def denied(url):calls.append(url);return {'http_status':403,'response_body_status':'UNREAD_HTTP_ERROR_BODY'},b''
        a.acquire(self.root,'bls_cpi','probe_one',True,denied)
        self.assertEqual(a.acquire(self.root,'bls_payroll','probe_two',True,denied)['status'],'SOURCE_PAUSED_NO_RETRY');self.assertEqual(len(calls),1)
        ack=m.read(self.root/'HTTP/probe_one.ack.json');self.assertIsNone(ack['response_sha256'])
    def test_partial_failure_keeps_other_family_and_resume_zero_get(self):
        def failed(url):
            if 'api.bls.gov' in url:raise TimeoutError('SYNTHETIC')
            return META,bea()
        out=a.run(self.root,PLAN,'cycle_001',True,e.parse,failed)
        self.assertEqual([v['status'] for v in out],['UNKNOWN','SOURCE_PAUSED_NO_RETRY','SUCCESS'])
        count,_=a.accounting(self.root);self.assertEqual(count,2)
        a.run(self.root,PLAN,'cycle_001',True,e.parse,lambda u:(_ for _ in ()).throw(AssertionError('RETRY')))
        self.assertEqual(a.accounting(self.root)[0],2)
    def test_request_and_byte_limits_before_fetch(self):
        p={**PLAN,'max_requests':1};a.pin(self.root,p)
        a.acquire(self.root,'bls_cpi','cycle_001_bls_cpi',True,self.fetch,e.parse)
        with self.assertRaisesRegex(ValueError,'BUDGET_EXHAUSTED'):a.acquire(self.root,'bea_releases','cycle_001_bea_releases',True,lambda u:self.fail('FETCH'))
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'SYNTHETIC';a.pin(root,{**PLAN,'max_bytes':m.MAX_BODY-1})
            with self.assertRaisesRegex(ValueError,'BUDGET_EXHAUSTED'):a.acquire(root,'bls_cpi','cycle_001_bls_cpi',True,lambda u:self.fail('FETCH'))
    def test_direct_path_cycle_grammar_interval_and_pin_hash(self):
        a.acquire(self.root,'bls_cpi','probe_bls_cpi',True,self.fetch,e.parse);a.pin(self.root,PLAN)
        for request in ['probe_bls_cpi_new','cycle_anything','cycle_002_bls_cpi']:
            with self.assertRaises(ValueError):a.acquire(self.root,'bls_cpi',request,True,lambda u:self.fail('FETCH'))
        (self.root/'PLAN_SHA256.json').write_text('{"sha256":"tampered"}')
        with self.assertRaisesRegex(ValueError,'PLAN_HASH_MISMATCH'):a.acquire(self.root,'bls_cpi','cycle_002_bls_cpi',True,lambda u:self.fail('FETCH'))
    def test_no_old_m3_plan_or_third_source_accepted(self):
        for p in [{**PLAN,'version':'M3'},{**PLAN,'sources':['bls_api','bea_releases','third']},{**PLAN,'max_requests':81},{**PLAN,'max_bytes':20_000_001},{**PLAN,'interval_seconds':0}]:
            with self.assertRaises(ValueError):a.validate_plan(p)
    def test_first_seen_duplicate_revision_and_clock_roles(self):
        a.pin(self.root,PLAN)
        self.capture_fixture('a','bls_cpi',bls(), '2026-01-01T00:00:00Z')
        self.capture_fixture('b','bls_cpi',bls(), '2026-01-01T00:30:00Z')
        self.capture_fixture('c','bls_cpi',bls(value='124.000'), '2026-01-01T01:00:00Z')
        p=e.project(self.root);self.assertEqual([r['observation_kind'] for r in p['observations']],['new','duplicate','updated'])
        self.assertTrue(all(r['first_observed_at_in_M31']=='2026-01-01T00:00:00Z' and r['first_observed_scope']=='M31_ONLY_NOT_GLOBAL_FIRST_SEEN' and r['source_to_observation_seconds'] is None for r in p['observations']))
        self.assertEqual(p,e.project(self.root));self.assertFalse(p['global_first_seen_proven'])
    def test_future_source_date_no_negative_latency_and_rights(self):
        a.pin(self.root,PLAN);self.capture_fixture('a','bea_releases',bea(date='2099-01-01T00:00:00Z'),'2026-01-01T00:00:00Z')
        row=e.project(self.root)['latest'][0];self.assertIsNone(row['source_to_observation_seconds']);self.assertEqual(row['source_to_observation_status'],'FUTURE_OR_CLOCK_DISPUTED');self.assertEqual(row['rights'],e.RIGHTS);self.assertIn('NOT_ADJUDICATED',row['authority_status'])
    def test_payload_tamper_and_checkpoint_fault_fail_closed(self):
        a.pin(self.root,PLAN);self.capture_fixture('a','bls_cpi',bls(),'2026-01-01T00:00:00Z');(self.root/'HTTP/a.body').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'RECEIPT_INTEGRITY'):e.project(self.root)
        original=m.save
        def interrupted(path,value):
            if str(path).endswith('.parsed.json'):raise OSError('SYNTHETIC_WRITE_INTERRUPTION')
            return original(path,value)
        with patch.object(m,'save',side_effect=interrupted):out=a.acquire(self.root,'bea_releases','cycle_001_bea_releases',True,self.fetch,e.parse)
        self.assertEqual(out['status'],'LOCAL_WRITE_FAILED');self.assertTrue((self.root/'HTTP/cycle_001_bea_releases.ack.json').exists());self.assertFalse((self.root/'HTTP/cycle_001_bea_releases.parsed.json').exists())
    def test_bls_daily_quota_includes_all_series(self):
        a.pin(self.root,PLAN)
        for i in range(25):
            stem=self.root/'HTTP'/str(i);m.save(Path(str(stem)+'.reserve.json'),{'endpoint_id':'bls_cpi' if i%2 else 'bls_payroll','reserved_at':'2026-10-20T11:00:00Z','request_id':'quota_fixture_'+str(i)})
            m.save(Path(str(stem)+'.ack.json'),{'response_bytes':0});m.save(Path(str(stem)+'.terminal.json'),{'status':'SUCCESS'})
        with patch.object(a,'datetime',wraps=datetime) as clock,patch.object(m,'now',return_value='2026-10-20T12:00:00Z'):
            clock.now.return_value=datetime(2026,10,20,12,tzinfo=timezone.utc)
            with self.assertRaisesRegex(ValueError,'BLS_DAILY_EXPERIMENT_QUOTA'):a.acquire(self.root,'bls_cpi','cycle_001_bls_cpi',True,lambda u:self.fail('FETCH'))

if __name__=='__main__':unittest.main()
