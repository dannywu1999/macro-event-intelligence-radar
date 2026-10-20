"""SYNTHETIC fault fixtures only; no external HTTP or historical first-seen claim."""
import copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from research import m34_bea as b,m3_discovery as m,m31_access as a

URL='https://www.bea.gov/news/2026/personal-income-and-outlays-august-2026'
TITLE='Personal Income and Outlays, August 2026'
TERMS=b'information posted on this web site is in the public domain'
def html(title=TITLE,url=URL,text='SYNTHETIC BODY '+('test evidence '*10)):
    return f'<link rel="canonical" href="{url}"><h1>News Release</h1><h1>{title}</h1><div class="field--name-body"><p>{text}</p></div><footer>unrelated</footer>'.encode()
def listing(title=TITLE,url=URL,raw='2026-09-30T08:30:00-04:00'):
    time='' if raw is None else f'<time datetime="{raw}">date</time>'
    return f'<table><tr class="release-row"><td><a href="{url}">{title}</a></td><td>{time}</td></tr></table>'.encode()
def entry(clock='2026-10-20T10:00:00Z',content='a'*64,title=TITLE,url=URL,published='2026-09-30T12:30:00Z'):
    return {'release_family':b.family(title),'source_url':url,'source_title_original':title,'source_reported_published_at':published,'publication_precision':'EXACT_SOURCE_REPORTED' if published else 'UNKNOWN','request_started_at':clock,'response_observed_at':clock,'retrieved_at':clock,'recorded_at':clock,'receipt_sha256':m.sha((clock+content).encode()),'content_sha256':content}

class BEA(unittest.TestCase):
    def test_family_separation(self):
        self.assertEqual(b.family(b.TARGETS['GDP_Q3_2026_ADVANCE']),'GDP_Q3_2026_ADVANCE')
        self.assertEqual(b.family(b.TARGETS['PIO_SEPTEMBER_2026']),'PIO_SEPTEMBER_2026')
        self.assertIsNone(b.family('Real Personal Consumption Expenditures by State, 2024'))
        self.assertIsNone(b.family('CPI, September 2026'))
    def test_actual_list_shape(self):
        r=b.release_list('current',listing());self.assertEqual(r[0]['release_family'],'PIO_AUGUST_2026');self.assertEqual(r[0]['source_reported_published_at'],'2026-09-30T12:30:00Z')
    def test_missing_publication(self):
        r=b.release_list('current',listing(raw=None))[0];self.assertIsNone(r['source_reported_published_at']);self.assertEqual(r['publication_precision'],'UNKNOWN')
    def test_invalid_naive_time(self):
        for raw in ('bad','2026-09-30T08:30:00'):
            with self.assertRaises(ValueError):b.release_list('current',listing(raw=raw))
    def test_conflicting_source_clocks(self):
        body=listing().replace(b'</td></tr>',b'<time datetime="2026-09-29T08:30:00-04:00">other</time></td></tr>')
        with self.assertRaises(ValueError):b.release_list('current',body)
        rss=b'<rss><channel><item><title>Personal Income and Outlays, August 2026</title><link>'+URL.encode()+b'</link><pubDate>Wed, 30 Sep 2026 08:30:00 EDT</pubDate><pubDate>Tue, 29 Sep 2026 08:30:00 EDT</pubDate></item></channel></rss>'
        with self.assertRaises(ValueError):b.release_list('rss',rss)
    def test_date_only_preserved(self):
        self.assertEqual(b.timestamp('2026-09-30'),('2026-09-30','DATE_ONLY'))
    def test_wrong_host(self):
        with self.assertRaises(ValueError):b.release_list('current',listing(url='https://evil.example/news/2026/test'))
    def test_malformed_list(self):
        with self.assertRaises(ValueError):b.release_list('current',b'<html>Error</html>')
    def test_unsafe_rss(self):
        with self.assertRaises(ValueError):b.release_list('rss',b'<!DOCTYPE rss><rss/>')
    def test_new_duplicate_update_and_first_seen(self):
        rr=b.transitions([entry(),entry('2026-10-20T10:31:00Z'),entry('2026-10-20T11:02:00Z','b'*64)],synthetic=True)
        self.assertEqual([x['observation_kind'] for x in rr],['NEW','DUPLICATE','UPDATED'])
        self.assertEqual(len({x['first_observed_in_experiment'] for x in rr}),1)
        self.assertTrue(all(x['availability_scope']=='SYNTHETIC_HISTORICAL_REHEARSAL' for x in rr))
    def test_conflicting_times(self):
        e=entry();e['recorded_at']='2026-10-20T09:00:00Z'
        with self.assertRaises(ValueError):b.transitions([e])
        e=entry(published='2026-10-21T00:00:00Z')
        with self.assertRaises(ValueError):b.transitions([e])
    def test_url_family_conflict(self):
        e=entry('2026-10-20T10:31:00Z');e['release_family']='GDP_Q3_2026_ADVANCE'
        with self.assertRaises(ValueError):b.transitions([entry(),e])
    def test_asof_excludes_future_revision(self):
        rr=b.transitions([entry(),entry('2026-10-20T10:31:00Z','b'*64)],as_of='2026-10-20T10:15:00Z')
        self.assertEqual(len(rr),1);self.assertEqual(rr[0]['content_sha256'],'a'*64)
    def test_original_body_only_changes(self):
        one=b.document(html(),URL);two=b.document(html().replace(b'unrelated',b'new footer'),URL)
        self.assertEqual(one['content_sha256'],two['content_sha256'])
        self.assertNotEqual(one['content_sha256'],b.document(html(text='SYNTHETIC REVISED '+('word '*20)),URL)['content_sha256'])
    def test_original_identity(self):
        with self.assertRaises(ValueError):b.document(html(url='https://www.bea.gov/news/2026/wrong'),URL)
    def test_empty_original(self):
        with self.assertRaises(ValueError):b.document(html(text=''),URL)
    def test_gdp_renderer_punctuation_not_revision(self):
        title='GDP (Third Estimate), Industries, Corporate Profits, State GDP, and State Personal Income, 2nd Quarter 2026; State PCE, 2025'
        x={'release_family':b.family(title),'source_title_original':title,'source_url':URL,'source_reported_published_at':None,'publication_precision':'UNKNOWN'}
        y={**x,'source_title_original':title.replace('GDP (','GDP, (')}
        self.assertEqual(b.metadata_hash(x),b.metadata_hash(y))
    def test_disabled_default(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'absent';r=subprocess.run([sys.executable,'-m','research.m34_bea','--root',str(root)],capture_output=True,check=True)
            self.assertEqual(json.loads(r.stdout)['network_requests'],0);self.assertFalse(root.exists())
            mock=Mock()
            with self.assertRaises(ValueError):b.acquire(root,'ACCESS',b.contract(),'terms','test',False,mock)
            mock.assert_not_called()
    def test_denial_pause_and_no_retry(self):
        with tempfile.TemporaryDirectory() as d:
            f=Mock(return_value=({'http_status':403,'response_body_status':'UNREAD_HTTP_ERROR_BODY'},b''))
            self.assertEqual(b.acquire(d,'ACCESS',b.contract(),'terms','denied',True,f)['status'],'SOURCE_DENIED')
            with self.assertRaises(ValueError):b.acquire(d,'ACCESS',b.contract(),'current','later',True,f)
            self.assertEqual(f.call_count,1)
    def test_spent_id_immutable(self):
        with tempfile.TemporaryDirectory() as d:
            f=Mock(return_value=({'http_status':200},TERMS));b.acquire(d,'ACCESS',b.contract(),'terms','once',True,f)
            before={p.name:m.sha(p.read_bytes()) for p in Path(d).glob('ACCESS/HTTP/*')}
            self.assertEqual(b.acquire(d,'ACCESS',b.contract(),'terms','once',True,f)['status'],'ALREADY_RESERVED_NO_RETRY')
            self.assertEqual(before,{p.name:m.sha(p.read_bytes()) for p in Path(d).glob('ACCESS/HTTP/*')});self.assertEqual(f.call_count,1)
    def test_unknown_ack_recovery_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            f=Mock(side_effect=TimeoutError());self.assertEqual(b.acquire(d,'ACCESS',b.contract(),'terms','unknown',True,f)['status'],'UNKNOWN')
            with self.assertRaises(ValueError):b.acquire(d,'ACCESS',b.contract(),'current','later',True,f)
            self.assertEqual(f.call_count,1)
    def test_interrupted_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            b.base(d);m.save(Path(d)/'ACCESS/HTTP/interrupted.reserve.json',{'url':b.URLS['terms']})
            f=Mock()
            with self.assertRaises(ValueError):b.acquire(d,'ACCESS',b.contract(),'terms','later',True,f)
            f.assert_not_called()
    def test_budget_and_resource_cadence(self):
        with tempfile.TemporaryDirectory() as d:
            f=Mock(return_value=({'http_status':200},TERMS));b.acquire(d,'ACCESS',b.contract(),'terms','once',True,f)
            with self.assertRaises(ValueError):b.acquire(d,'ACCESS',b.contract(),'terms','too_soon',True,f)
            with patch.object(b,'budget',return_value=(15,10)):
                with self.assertRaises(ValueError):b.acquire(d,'ACCESS',b.contract(),'current','over_count',True,f)
            with patch.object(b,'budget',return_value=(1,4_000_000)):
                with self.assertRaises(ValueError):b.acquire(d,'ACCESS',b.contract(),'current','over_bytes',True,f)
            self.assertEqual(f.call_count,1)
    def test_receipt_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            b.acquire(d,'ACCESS',b.contract(),'terms','once',True,lambda _:({'http_status':200},TERMS))
            stem=Path(d)/'ACCESS/HTTP/once';b.receipt(stem,b.contract())
            Path(str(stem)+'.body').write_bytes(b'evil')
            with self.assertRaises(ValueError):b.receipt(stem,b.contract())
    def test_original_requires_discovery(self):
        with tempfile.TemporaryDirectory() as d:
            f=Mock()
            with self.assertRaises((ValueError,FileNotFoundError)):b.original(d,'missing',URL,'doc',True,f)
            f.assert_not_called()
    def test_plan_not_announcement(self):
        self.assertEqual(b.transitions([]),[])
        s='<div>2026</div><table>'+''.join('<tr class="scheduled-releases-type-press"><td>October 29 8:30 AM</td><td>'+t+'</td></tr>' for t in b.TARGETS.values())+'</table>'
        self.assertEqual(len(b.schedule(s.encode())),2)
        with self.assertRaises(ValueError):b.schedule(s.replace('8:30','9:30').encode())
    def test_malformed_http200_is_not_success(self):
        with tempfile.TemporaryDirectory() as d:
            r=b.acquire(d,'ACCESS',b.contract(),'current','malformed',True,lambda _:({'http_status':200},b'<html>error</html>'))
            self.assertEqual(r['status'],'PARSE_FAILED')
    def test_exact_historical_proposition_scope(self):
        d={**b.document(html(text='Personal income increased $66.6 billion (0.2 percent at a monthly rate) in August, according to estimates. '+('text '*20)),URL),'evidence_layer':'ORIGINAL_DOCUMENT_NOT_AUTOMATIC_PROPOSITION_VERIFICATION','receipt_sha256':'a'*64,'retrieved_at':'2026-10-20T10:00:00Z','recorded_at':'2026-10-20T10:00:01Z','source_reported_published_at':'2026-09-30T12:30:00Z'}
        f=b.income_fact(d);self.assertEqual(f['change_usd_billion'],'66.6');self.assertEqual(f['macroview']['surprise'],'UNKNOWN');self.assertEqual(f['macroview']['status'],'RESEARCH_PREVIEW_NOT_FROZEN')
        with self.assertRaises(ValueError):b.income_fact({**d,'receipt_sha256':None})
        with self.assertRaises(ValueError):b.income_fact({**d,'body_text':'No income proposition here'})

    def test_full_offline_pipeline_and_failure_preserves_last_good(self):
        with tempfile.TemporaryDirectory() as d:
            def get(url):
                if url==b.URLS['schedule']:
                    data=('<div>2026</div><table>'+''.join('<tr class="scheduled-releases-type-press"><td>October 29 8:30 AM</td><td>'+t+'</td></tr>' for t in b.TARGETS.values())+'</table>').encode()
                elif url==b.URLS['terms']:data=TERMS
                elif url==b.URLS['rss_doc']:data=b.URLS['rss'].encode()
                elif url==b.URLS['current']:data=listing()
                elif url==URL:data=html()
                else:raise AssertionError('UNEXPECTED_ENDPOINT')
                return {'http_status':200,'content_type':'text/html; charset=utf-8'},data
            for ep in ('schedule','terms','rss_doc','current'):self.assertEqual(b.acquire(d,'ACCESS',b.contract(),ep,ep,True,get)['status'],'SUCCESS')
            b.pin(d,'schedule','terms','rss_doc');before=b.project(d)
            self.assertTrue(all(t['status']=='PLANNED_NOT_OBSERVED' for t in before['targets']))
            b.original(d,'current',URL,'doc',True,get);p=b.project(d)
            self.assertEqual(len(p['documents']),1);self.assertEqual(p['documents'][0]['observation_kind'],'NEW')
            self.assertEqual(b.project(d,as_of='2026-10-20T00:00:00Z')['status'],'UNAVAILABLE_BEFORE_PLAN')
            cutoff=m.now()
            b.acquire(d,'ACCESS',b.contract(),'rss','denied',True,lambda _:({'http_status':406,'response_body_status':'UNREAD_HTTP_ERROR_BODY'},b''))
            failed=b.project(d);self.assertEqual(len(failed['observations']),len(p['observations']));self.assertEqual(failed['source_failures'][0]['status'],'SOURCE_DENIED')
            past=b.project(d,as_of=cutoff);self.assertEqual(past['source_failures'],[]);self.assertIsNone(past['network_accounting'])
    def test_all_failed_http_stops_even_after_cadence(self):
        for code in (302,404,406,429):
            with tempfile.TemporaryDirectory() as d:
                f=Mock(return_value=({'http_status':code,'response_body_status':'UNREAD_HTTP_ERROR_BODY'},b''))
                b.acquire(d,'ACCESS',b.contract(),'current','failure',True,f)
                with patch.object(m,'now',return_value='2026-10-29T22:00:00Z'):
                    with self.assertRaises(ValueError):b.acquire(d,'ACCESS',b.contract(),'current','unauthorized_retry',True,f)
                self.assertEqual(f.call_count,1)

if __name__=='__main__':unittest.main()
