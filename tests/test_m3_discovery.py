import io, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

from research import m3_discovery as m

def plan():
    return {'experiment_id':'test','interval_seconds':1800,'max_requests':20,'max_total_bytes':50_000_000,
      'sources':[{'id':i,'name':i,'url':u,'kind':'rss','article_hosts':[url_host(u)],'terms_status':'research'} for i,u in m.REGISTRY.items()]}
def url_host(url): return url.split('/')[2]
def pin(root,p):
    m.save(root/'plan.json',p);m.save(root/'plan.sha256',{'sha256':m.sha(m.canonical(p).encode())})
FEED=b'<rss><channel><item><title>Inflation report</title><link>https://www.ecb.europa.eu/story/1</link><pubDate>2026-10-19</pubDate><author>Reporter</author></item></channel></rss>'

class FakeResponse:
    status=200
    class Headers:
        def get(self,k): return 'application/rss+xml'
    headers=Headers()
    def __init__(self, chunks): self.chunks=iter(chunks); self.fp=None
    def read(self,n): return next(self.chunks,b'')
    def __enter__(self): return self
    def __exit__(self,*a): pass

class M3Tests(unittest.TestCase):
    def test_reader_survives_eof_with_fp_none(self):
        response=FakeResponse([b'abc',b''])
        with patch.object(m.urllib.request,'build_opener',return_value=type('O',(),{'open':lambda *_a,**_k:response})()):
            meta,body=m.bounded_get('https://example.org/feed')
        with self.assertRaises(AttributeError): _=response.fp.raw._sock.gettimeout()
        self.assertEqual(body,b'abc');self.assertEqual(meta['http_status'],200)
        self.assertTrue(meta['legacy_private_socket_access_would_fail'])
        self.assertEqual(m.sha(body),m.sha(b'abc'))

    def test_http_error_body_is_unread_and_never_falsely_hashed(self):
        from email.message import Message
        body_stream=io.BytesIO(b'denial body')
        error=m.urllib.error.HTTPError('https://example.org/feed',403,'Forbidden',Message(),body_stream)
        with patch.object(m.urllib.request,'build_opener',return_value=type('O',(),{'open':lambda *_a,**_k:(_ for _ in ()).throw(error)})()):
            meta,body=m.bounded_get('https://example.org/feed')
        self.assertEqual(body,b'');self.assertTrue(body_stream.closed)
        self.assertEqual(meta['response_body_status'],'UNREAD_HTTP_ERROR_BODY')
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as d:
            root=Path(d);pin(root,plan());success=b'<rss><channel/></rss>'
            def fetch(url):
                return ({'http_status':403,'response_body_status':'UNREAD_HTTP_ERROR_BODY'} if url==m.REGISTRY['ecb'] else {'http_status':200,'response_body_status':'COMPLETE_READ'},b'' if url==m.REGISTRY['ecb'] else success)
            m.run(root,plan(),'c',True,fetch)
            receipts=[m.read(p) for p in (root/'cycles'/'c').glob('*.ack.json')]
            denied=next(x for x in receipts if x['source_id']=='ecb')
            good=next(x for x in receipts if x['source_id']=='globalvoices')
            self.assertEqual(denied['response_body_status'],'UNREAD_HTTP_ERROR_BODY');self.assertIsNone(denied['response_sha256'])
            self.assertEqual(good['response_body_status'],'COMPLETE_READ');self.assertEqual(good['response_sha256'],m.sha(success))
            terminal=m.read(next((root/'cycles'/'c').glob('ecb.*.terminal.json')))
            self.assertEqual(terminal['failure_class'],'HTTP_STATUS_SOURCE_DENIAL')

    def test_denial_and_malformed_feed(self):
        parsed,diag=m.parse_metadata(b'<rss><channel><item><title>x</title><link>https://attacker.test/x</link></item></channel></rss>',plan()['sources'][0]);self.assertEqual(parsed,[]);self.assertEqual(diag['rejected_by_reason']['UNSAFE_OR_OFF_HOST_URL'],1)
        with self.assertRaises(Exception):m.parse_metadata(b'<rss><broken></rss>',plan()['sources'][0])
        with self.assertRaises(ValueError):m.parse_metadata(b'<!DOCTYPE x><rss/>',plan()['sources'][0])

    def test_date_precision_and_bad_dates(self):
        self.assertEqual(m.date('2026-10-19'),('2026-10-19','DATE_ONLY'))
        self.assertEqual(m.date('not a date'),(None,'INVALID'))
        self.assertEqual(m.date('2026-10-19T12:00:00'),(None,'TIMEZONE_UNKNOWN'))

    def test_bls_cpi_named_indicator_is_research_only(self):
        row={'source_id':'bls_cpi','title':'CPI for all items increases 0.4 percent in September'}
        self.assertFalse(m.macro_relevant_title(row['title']))
        self.assertEqual(m.research_relevance(row),(True,'NAMED_BLS_CPI_SOURCE_INFLATION_INDICATOR'))

    def test_fed_policy_minutes_named_context_is_research_only(self):
        titles=("Minutes of the Board’s discount rate meetings on August 17, September 9, and September 16, 2026",
                'Minutes of the Federal Open Market Committee, September 15-16, 2026')
        for title in titles:
            with self.subTest(title=title):
                self.assertEqual(m.research_relevance({'source_id':'fed_monetary','title':title}),
                                 (True,'NAMED_FED_POLICY_MINUTES_CONTEXT_NOT_NEW_RATE_DECISION'))
        self.assertFalse(m.research_relevance({'source_id':'fed_monetary','title':'Minutes of the hiking club meeting'} )[0])
        self.assertFalse(m.research_relevance({'source_id':'globalvoices','title':titles[1]})[0])

    def test_default_network_off(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as d:
            pin(Path(d),plan())
            with self.assertRaisesRegex(ValueError,'NETWORK_DISABLED'):m.run(d,plan(),'c1')

    def test_resume_does_not_repeat_and_project_deterministic(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as d:
            root=Path(d);pin(root,plan());calls=[]
            def fetch(url): calls.append(url);return {'http_status':200},FEED
            # Avoid all 6 requests on fixture: first source succeeds, later sources independently parse as off-host.
            out=m.run(root,plan(),'c1',True,fetch);self.assertEqual(len(calls),6)
            m.run(root,plan(),'c1',True,lambda _:self.fail('completed source was fetched again'))
            self.assertEqual(out,m.project(root));self.assertEqual(m.project(root),m.project(root))
            self.assertEqual(out['new_count'],1)

    def test_append_only_unknown_reservation_and_source_isolation(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as d:
            root=Path(d);pin(root,plan());c=root/'cycles'/'crash';c.mkdir(parents=True)
            m.save(c/'ecb.0.reserve.json',{'source_id':'ecb','request_count':1,'reserved_bytes':m.MAX_BODY,'reserved_at':'2026-01-01T00:00:00Z'})
            # interrupted reservation remains uncompleted and a later cycle still proceeds
            calls=[]
            def fetch(url):
                calls.append(url)
                if url==m.REGISTRY['globalvoices']:return {'http_status':200},b'<bad'
                if url==m.REGISTRY['fed_monetary']:return {'http_status':403,'retry_after':'3600'},b''
                return {'http_status':403,'retry_after':'3600'},b''
            result=m.run(root,plan(),'next',True,fetch)
            self.assertEqual(len(calls),5) # malformed source remains isolated; denied feeds are paused but later sources continue
            self.assertEqual(result['source_states']['ecb'],'UNKNOWN')
            self.assertTrue(any(p.name.endswith('.ack.json') for p in (root/'cycles'/'next').glob('*')))

    def test_budget_reserved_before_request(self):
        tiny=plan();tiny['max_requests']=1
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as d:
            root=Path(d);pin(root,tiny);calls=[]
            with self.assertRaises(ValueError):m.run(root,tiny,'c',True,lambda url:(calls.append(url) or ({'http_status':200},b'')))
            self.assertEqual(len(calls),1)

    def test_auxiliary_reservations_share_request_and_byte_budgets(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as d:
            root=Path(d);limited=plan();limited['max_requests']=1;pin(root,limited)
            aux=root/'auxiliary';aux.mkdir()
            stem=aux/'fed_minutes'
            m.save(Path(str(stem)+'.reserve.json'),{'request_count':1,'reserved_at':'2026-01-01T00:00:00Z'})
            m.save(Path(str(stem)+'.ack.json'),{'response_bytes':73})
            calls=[]
            with self.assertRaisesRegex(ValueError,'BUDGET_EXHAUSTED'):m.run(root,limited,'next',True,lambda u:(calls.append(u) or ({'http_status':200},b'')))
            self.assertEqual(calls,[])
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as d:
            root=Path(d);limited=plan();limited['max_total_bytes']=m.MAX_BODY;limited['max_requests']=2;pin(root,limited)
            aux=root/'auxiliary';aux.mkdir()
            m.save(aux/'fed_minutes.reserve.json',{'request_count':1,'reserved_at':'2026-01-01T00:00:00Z'})
            calls=[]
            with self.assertRaisesRegex(ValueError,'BUDGET_EXHAUSTED'):m.run(root,limited,'next',True,lambda u:(calls.append(u) or ({'http_status':200},b'')))
            self.assertEqual(calls,[])

    def test_unknown_ack_keeps_hash_before_parser_failure(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as d:
            root=Path(d);pin(root,plan())
            def bad(url):return {'http_status':200},b'<broken'
            m.run(root,plan(),'c',True,bad)
            ack=next((root/'cycles'/'c').glob('*.ack.json'))
            value=m.read(ack);self.assertEqual(value['response_sha256'],m.sha(b'<broken'));self.assertEqual(value['response_bytes'],7)
            self.assertEqual(m.read(next((root/'cycles'/'c').glob('*.terminal.json')))['status'],'PARSER_DEFECT')

    def test_pause_persists_and_denial_does_not_block_other_sources(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as d:
            root=Path(d);pin(root,plan());old=root/'cycles'/'old';old.mkdir(parents=True)
            stem=old/'ecb.0'
            m.save(Path(str(stem)+'.reserve.json'),{'source_id':'ecb','reserved_at':'2026-01-01T00:00:00Z','request_count':1,'reserved_bytes':m.MAX_BODY})
            m.save(Path(str(stem)+'.ack.json'),{'response_bytes':0})
            m.save(Path(str(stem)+'.terminal.json'),{'source_id':'ecb','status':'PAUSED_HTTP_403','completed_at':'2026-01-01T00:00:01Z'})
            calls=[]
            def fetch(url):
                calls.append(url)
                return ({'http_status':406} if url==m.REGISTRY['globalvoices'] else {'http_status':200},b'<rss><channel/></rss>')
            m.run(root,plan(),'next',True,fetch)
            self.assertEqual(len(calls),5);self.assertNotIn(m.REGISTRY['ecb'],calls)
            self.assertFalse(list((root/'cycles'/'next').glob('ecb.*.reserve.json')))

    def test_first_observation_stays_stable_and_clock_dispute_is_unknown(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as d:
            root=Path(d);pin(root,plan())
            row={'source_id':'bls_cpi','source_name':'BLS CPI','title':'CPI for all items increases 0.4 percent','url':'https://www.bls.gov/news.release/archives/cpi_10142026.htm','author':None,'source_published_raw':'2026-10-19T12:00:00Z','source_published_at':'2026-10-19T12:00:00Z','publication_precision':'EXACT_SOURCE_REPORTED','terms_status':'research'}
            for cycle,retrieved in [('one','2026-10-20T00:00:00.000001Z'),('two','2026-10-20T00:30:00.000002Z')]:
                dpath=root/'cycles'/cycle;dpath.mkdir(parents=True)
                m.save(dpath/'bls.parsed.json',{'source_id':'bls_cpi','cycle_id':cycle,'source_url':m.REGISTRY['bls_cpi'],'plan_fingerprint':m.sha(m.canonical(plan()).encode()),'provenance_scope':'M3_ISOLATED_RESEARCH','retrieved_at':retrieved,'recorded_at':retrieved,'articles':[row]})
            out=m.project(root); repeats=[x for x in out['observations'] if x['observation_kind']=='duplicate']
            self.assertEqual(len(repeats),1);self.assertEqual(repeats[0]['first_observed_at'],'2026-10-20T00:00:00.000001Z')
            self.assertEqual(repeats[0]['retrieved_at'],'2026-10-20T00:30:00.000002Z')
            self.assertEqual(repeats[0]['source_to_observation_status'],'CLOCK_DISPUTED');self.assertIsNone(repeats[0]['source_to_observation_seconds'])

if __name__=='__main__':unittest.main()
