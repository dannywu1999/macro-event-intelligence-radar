"""Additional focused SYNTHETIC projection/budget checks; never live observations."""
from pathlib import Path
import copy,tempfile,unittest
from tests.test_m3_discovery import plan,pin
from research import m3_discovery as m

class ResearchResultsTests(unittest.TestCase):
    def test_hard_caps_and_semantic_registry_fail_closed(self):
        for field,value in [('max_requests',201),('max_total_bytes',50_000_001),('max_requests',True)]:
            p=plan();p[field]=value
            with self.assertRaises(ValueError):m.validate_plan(p)
        p=plan();p['sources'][0]['url']='https://example.invalid/'
        with self.assertRaises(ValueError):m.validate_plan(p)

    def test_future_and_updated_title_preserve_first_observation(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as tmp:
            root=Path(tmp);pin(root,plan())
            original={'source_id':'fed_monetary','source_name':'Fed','title':'Federal Reserve issues FOMC statement','url':'https://www.federalreserve.gov/newsevents/pressreleases/SYNTHETIC.htm','author':None,'source_published_raw':'2026-01-01T12:00:00Z','source_published_at':'2026-01-01T12:00:00Z','publication_precision':'EXACT_SOURCE_REPORTED','terms_status':'SYNTHETIC_TEST_ONLY'}
            for cycle,at,title in [('one','2026-01-01T00:00:00Z',original['title']),('two','2026-01-01T00:30:00Z',original['title']+' corrected')]:
                directory=root/'cycles'/cycle;directory.mkdir(parents=True)
                m.save(directory/'fed.parsed.json',{'source_id':'fed_monetary','cycle_id':cycle,'source_url':m.REGISTRY['fed_monetary'],'plan_fingerprint':m.sha(m.canonical(plan()).encode()),'provenance_scope':'SYNTHETIC_TEST_ONLY','retrieved_at':at,'recorded_at':at,'articles':[{**original,'title':title}]})
            p=m.project(root)
            self.assertEqual(p['updated_count'],1);self.assertEqual(p['new_count'],1)
            self.assertEqual({r['first_observed_at'] for r in p['observations']},{'2026-01-01T00:00:00Z'})
            self.assertTrue(all(r['source_to_observation_seconds'] is None and r['source_to_observation_status']=='FUTURE_OR_CLOCK_DISPUTED' for r in p['observations']))
            self.assertEqual(p['canonical_candidates']['events'][0]['first_detected_at'],'2026-01-01T00:00:00Z')

    def test_same_title_different_release_urls_not_fuzzy_merged(self):
        items=[{'article_reference':'https://www.federalreserve.gov/SYNTHETIC_'+str(i),'title':'Federal Reserve issues FOMC statement','reported_at':'2026-01-0'+str(i)+'T00:00:00Z','reported_time_kind':'REPORTED_TIME','observed_at':'2026-01-03T00:00:00Z','news_source':{'name':'Fed'}} for i in (1,2)]
        p=m.build_canonical_events(items)
        self.assertEqual(len(p['events']),2)
        self.assertEqual(p,m.build_canonical_events(list(reversed(items))))

    def test_retry_after_is_not_an_immediate_retry(self):
        self.assertEqual(m._retry_until('1800','2026-01-01T00:00:00Z'),'2026-01-01T00:30:00Z')
        self.assertEqual(m._retry_until('Thu, 01 Jan 2026 01:00:00 GMT','2026-01-01T00:00:00Z'),'2026-01-01T01:00:00Z')
        self.assertIsNone(m._retry_until('not a timestamp','2026-01-01T00:00:00Z'))

    def test_article_identity_does_not_use_translations(self):
        self.assertEqual(m.article_identity('https://www.federalreserve.gov/x?utm_source=chatgpt.com'),m.article_identity('https://www.federalreserve.gov/x'))
        self.assertNotEqual(m.article_identity('https://www.federalreserve.gov/x?release=1'),m.article_identity('https://www.federalreserve.gov/x?release=2'))

if __name__=='__main__':unittest.main()
