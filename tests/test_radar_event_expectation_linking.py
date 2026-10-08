"""A7.2 actual production functions with explicit synthetic TEMP evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools.stage1b_historical_campaign import radar_event_expectation_linker as linker
from tools.stage1b_historical_campaign import radar_market_expectations as markets
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign.radar_macroview_freeze import build_previews
from tools.stage1b_historical_campaign.radar_intelligence_store import IntelligenceStore
from tools.stage1b_historical_campaign.radar_reality_replay import replay_event_as_of
from tools.stage1b_historical_campaign import radar_web_server as app

ROOT = Path(__file__).resolve().parents[1]
EVENT_TIME = '2026-10-07T10:00:00Z'
MARKET_TIME = '2026-10-07T10:10:00Z'


def base_view(title='ECB interest rate decision at October 15, 2026 meeting'):
    with tempfile.TemporaryDirectory(prefix='a72-news-') as temp:
        path = Path(temp) / 'news.json'
        path.write_text(json.dumps([dict(observed_time=EVENT_TIME, event_time=None,
            headline_or_text=title, source_name='Synthetic fixture',
            source_url='https://example.test/meeting')]), encoding='utf-8')
        return radar.build_radar_view(radar.EvidencePaths(news=path))


def raw_market(mid='test-cut', question='Will ECB cut interest rates at its October 15, 2026 meeting?'):
    return dict(id=mid, question=question, outcomes=['Yes', 'No'], outcomePrices=['0.63', '0.37'],
                endDate='2026-10-16T20:00:00Z', events=[dict(slug='synthetic-meeting')])


class LinkTests(unittest.TestCase):
    def setUp(self):
        self.view = base_view()
        self.event = self.view['events'][0]
        self.eid = self.event['event_id']
        self.raw = raw_market()
        self.market = markets.parse_markets([self.raw], MARKET_TIME)[0]

    def compare(self, title=None, question=None, **changes):
        event = {**self.event, **changes}
        if title is not None:
            event['event_title'] = title
        record = self.market if question is None else markets.parse_markets([raw_market(question=question)], MARKET_TIME)[0]
        return linker.compare(event, record)

    def projected(self, records=None):
        view = copy.deepcopy(self.view)
        view.update(markets.project_expectations(view['events'], records or [self.market]))
        view['macroview_previews'] = build_previews(view)
        return view

    def test_exact_compatible_match(self):
        p = self.compare()
        self.assertEqual(p['link_status'], 'LINKED')
        self.assertEqual(p['confidence_class'], 'HIGH')
        self.assertEqual(p['contract_version'], 'EVENT_EXPECTATION_LINK_V0')
        self.assertIsNone(p['observed_at'])
        self.assertEqual(p['market_observed_at'], MARKET_TIME)

    def test_institution_aliases(self):
        for name in ['European Central Bank', 'ECB']:
            with self.subTest(name=name):
                self.assertEqual(self.compare(title=name+' rate decision October 15 2026')['link_status'], 'LINKED')
        for name in ['Fed', 'Federal Reserve', 'FOMC']:
            with self.subTest(name=name):
                self.assertEqual(self.compare(title=name+' rate decision October 15 2026',
                    question='Will Federal Reserve cut rates October 15 2026?')['link_status'], 'LINKED')

    def test_date_normalization(self):
        for title in ['ECB rate decision 2026-10-15', 'ECB rate decision 15 October 2026']:
            self.assertEqual(self.compare(title=title)['link_status'], 'LINKED')

    def test_month_only_scope_insufficient_for_automatic_link(self):
        self.assertEqual(self.compare(title='ECB rate decision October 2026',
            question='Will ECB cut rates at October 2026 meeting?')['link_status'], 'INSUFFICIENT_EVIDENCE')

    def test_different_date_rejected(self):
        self.assertEqual(self.compare(question='Will ECB cut rates October 20 2026?')['reason'], 'DIFFERENT_DATE_SCOPE')

    def test_deadline_different_date_rejected(self):
        self.assertEqual(self.compare(title='ECB rate decision October 20 2026',
            question='Will ECB cut rates before October 1 2026?')['link_status'], 'NO_MATCH')

    def test_year_not_inferred(self):
        self.assertEqual(self.compare(title='ECB rate decision October 15')['link_status'], 'INSUFFICIENT_EVIDENCE')

    def test_date_precision_not_guessed(self):
        self.assertNotEqual(self.compare(title='ECB rate decision October 2026')['link_status'], 'LINKED')

    def test_invalid_date_rejected(self):
        self.assertNotEqual(self.compare(title='ECB rate decision February 30 2027',
            question='Will ECB cut rates February 30 2027?')['link_status'], 'LINKED')

    def test_keyword_only_and_commentary_rejected(self):
        for title in ['ECB discusses interest rates', 'ECB interview on October 15 2026 about its rate decision',
                      'ECB plans to cut its budget ahead of October 15 2026', 'EIA crude oil production article']:
            with self.subTest(title=title):self.assertNotEqual(self.compare(title=title)['link_status'], 'LINKED')

    def test_different_policy_action(self):
        self.assertEqual(self.compare(title='ECB will raise rates October 15 2026')['reason'], 'DIFFERENT_POLICY_ACTION')

    def test_different_institution(self):
        self.assertEqual(self.compare(question='Will Fed cut rates October 15 2026?')['reason'], 'DIFFERENT_INSTITUTION')

    def test_threshold_compatible_and_incompatible(self):
        title='ECB will cut rates by 25 basis points October 15 2026'
        self.assertEqual(self.compare(title=title, question='Will ECB cut rates by 25bps October 15 2026?')['link_status'], 'LINKED')
        self.assertEqual(self.compare(title='ECB will cut rates 25bps October 15 2026',
            question='Will ECB cut rates 25 basis points October 15 2026?')['link_status'], 'LINKED')
        self.assertEqual(self.compare(title='ECB will cut rates 25bps October 15 2026',
            question='Will ECB cut rates 50bps October 15 2026?')['link_status'], 'NO_MATCH')

    def test_missing_threshold_not_filled(self):
        self.assertNotEqual(self.compare(title='ECB will cut rates October 15 2026',
            question='Will ECB cut rates 25bps October 15 2026?')['link_status'], 'LINKED')

    def test_percent_level_and_percent_change_not_equated(self):
        p=self.compare(title='ECB will cut rates to 2% October 15 2026',
            question='Will ECB cut rates by 2% October 15 2026?')
        self.assertEqual(p['link_status'],'INSUFFICIENT_EVIDENCE')

    def test_explicit_policy_jurisdiction_and_country_aliases(self):
        for alias in ['US','U.S.','United States']:
            self.assertEqual(self.compare(question='Will ECB cut rates in '+alias+' October 15 2026?')['link_status'],'NO_MATCH')
        self.assertEqual(self.compare(title='Bank of England rate decision October 15 2026',
            question='Will BOE cut rates in United Kingdom October 15 2026?')['link_status'],'LINKED')

    def test_multiple_market_outcomes_for_one_event(self):
        records=markets.parse_markets([self.raw,raw_market('test-hold','Will ECB hold rates October 15 2026?')],MARKET_TIME)
        p=self.projected(records)
        self.assertEqual(len(p['events'][0]['market_expectation_ids']),2)
        self.assertEqual(len(p['macroview_previews'][0]['snapshot']['market_expectations']),2)

    def test_competing_events_are_ambiguous(self):
        p=linker.link_events([self.event,{**self.event,'event_id':'another-canonical-event'}],[self.market])
        self.assertEqual({x['link_status'] for x in p},{'AMBIGUOUS'})

    def test_mixed_actors_and_actions_ambiguous(self):
        self.assertEqual(self.compare(title='ECB and Fed rate decision October 15 2026')['link_status'],'AMBIGUOUS')
        self.assertEqual(self.compare(question='Will ECB cut rates or hold rates October 15 2026?')['link_status'],'AMBIGUOUS')

    def test_completed_event_not_future_expectation(self):
        self.assertEqual(self.compare(event_occurred_at='2026-10-06T10:00:00Z')['link_status'],'NO_MATCH')
        self.assertEqual(self.compare(title='ECB cuts rates October 15 2026')['link_status'],'NO_MATCH')

    def test_closed_market_and_old_text_scope(self):
        record={**self.market,'market_close_time':'2026-10-07T10:05:00Z'}
        self.assertEqual(linker.compare(self.event,record)['link_status'],'NO_MATCH')
        self.assertEqual(self.compare(title='ECB rate decision October 1 2026',
            question='Will ECB cut rates October 1 2026?')['link_status'],'NO_MATCH')

    def test_provider_inactive_and_after_scope_refused(self):
        for flag,value in [('closed',True),('active',False)]:
            raw={**self.raw,flag:value}
            self.assertEqual(linker.compare(self.event,markets.parse_markets([raw],MARKET_TIME)[0])['link_status'],'NO_MATCH')
        self.assertNotEqual(self.compare(question='Will ECB cut rates after October 15 2026?')['link_status'],'LINKED')

    def test_missing_or_invalid_clocks(self):
        for clock in [None,'bad','2026-10-07']:
            self.assertNotEqual(linker.compare(self.event,{**self.market,'observed_at':clock})['link_status'],'LINKED')
        self.assertNotEqual(linker.compare(self.event,{**self.market,'market_close_time':None})['link_status'],'LINKED')

    def test_negated_and_conditional_not_guessed(self):
        for title in ['ECB will not cut rates October 15 2026','ECB will cut rates October 15 2026 if inflation falls']:
            self.assertNotEqual(self.compare(title=title)['link_status'],'LINKED')

    def test_resolution_criteria_conflict_rejected(self):
        raw={**self.raw,'resolutionCriteria':'ECB will raise rates October 15 2026'}
        self.assertEqual(linker.compare(self.event,markets.parse_markets([raw],MARKET_TIME)[0])['link_status'],'NO_MATCH')

    def test_complex_resolution_ambiguous(self):
        raw={**self.raw,'description':'ECB cut rates October 15 2026 or ECB cut rates November 15 2026'}
        self.assertEqual(linker.compare(self.event,markets.parse_markets([raw],MARKET_TIME)[0])['link_status'],'AMBIGUOUS')

    def test_description_never_supplies_missing_title_proposition(self):
        raw={**self.raw,'question':'What will happen?','description':self.raw['question']}
        self.assertNotEqual(linker.compare(self.event,markets.parse_markets([raw],MARKET_TIME)[0])['link_status'],'LINKED')

    def test_truncated_resolution_cannot_auto_link(self):
        raw={**self.raw,'description':'x '*4000+'different resolution'}
        p=linker.compare(self.event,markets.parse_markets([raw],MARKET_TIME)[0])
        self.assertEqual(p['link_status'],'INSUFFICIENT_EVIDENCE')

    def test_metadata_public_allowlist(self):
        raw={**self.raw,'description':'Public resolution rules','resolutionSource':'https://example.test/rules',
             'private_secret':'never expose','events':[dict(id='e',title='ECB rate meeting',slug='meeting',private_secret='hidden')]}
        p=markets.parse_markets([raw],MARKET_TIME)[0]
        self.assertEqual(p['proposition_metadata']['description'],'Public resolution rules')
        self.assertNotIn('private_secret',json.dumps(p))

    def test_no_match_is_normal(self):
        self.assertEqual(self.compare(question='Will Trump win the election in 2028?')['link_status'],'NO_MATCH')
        self.assertEqual(self.projected(markets.parse_markets([raw_market(question='Will Trump win?')],MARKET_TIME))['events'][0]['market_expectation_ids'],[])

    def test_stable_identity_input_immutability(self):
        before=copy.deepcopy((self.event,self.market));a=self.compare();b=self.compare()
        self.assertEqual(a,b);self.assertEqual(before,(self.event,self.market))

    def test_official_geography_decision_isolation(self):
        p=self.projected()
        self.assertEqual({k:v for k,v in p['events'][0].items() if k!='market_expectation_ids'},
                         {k:v for k,v in self.event.items() if k!='market_expectation_ids'})
        self.assertEqual(p['official_evidence'],self.view['official_evidence'])
        self.assertEqual(p['events'][0]['verification_status'],'UNVERIFIED_NEWS')
        self.assertEqual(p['events'][0]['geography_status'],'UNKNOWN')
        self.assertFalse(set(p['events'][0]) & {'direction','trade_confidence','order','signal'})

    def test_macroview_link_contract_preserved(self):
        p=self.projected();s=p['macroview_previews'][0]
        self.assertEqual(s['fact_state'],'NEWS_ONLY')
        self.assertEqual(s['snapshot']['market_expectations'][0]['event_expectation_link']['link_status'],'LINKED')

    def test_existing_official_fact_identity_and_authority_unchanged(self):
        fact=dict(official_confirmation='OFFICIAL_CONFIRMED',authority_role='FACT_AUTHORITY',
            authority_name='European Central Bank',official_source='https://example.test/ecb/official',
            official_document_reference='SYNTHETIC-MEETING-NOTICE',official_fact_proposition='Synthetic schedule notice.',
            official_published_at=None,official_project_first_seen_at=EVENT_TIME,official_retrieved_at=EVENT_TIME,
            canonical_event_id=self.eid)
        v=copy.deepcopy(self.view);v.update(radar.build_official_evidence_projection([fact],v['items'],v['events']))
        self.assertEqual(len(v['official_evidence']),1)
        before=copy.deepcopy(v);v.update(markets.project_expectations(v['events'],[self.market]))
        self.assertEqual(before['official_evidence'],v['official_evidence'])
        self.assertEqual(before['events'][0]['official_evidence_ids'],v['events'][0]['official_evidence_ids'])
        self.assertEqual(v['events'][0]['verification_status'],'UNVERIFIED_NEWS')

    def test_replay_cutoff_1010_and_later_probability(self):
        with tempfile.TemporaryDirectory(prefix='a72-ledger-') as t:
            store=IntelligenceStore(Path(t)/'store.db',create=True)
            store.ingest_projection(self.view,observed_at=EVENT_TIME)
            linked=self.projected();store.ingest_projection(linked,observed_at=MARKET_TIME)
            before=replay_event_as_of(store,self.eid,'2026-10-07T10:05:00Z')
            at=replay_event_as_of(store,self.eid,MARKET_TIME)
            self.assertEqual(before['market_expectation_observations'],[])
            self.assertEqual(at['reconstructed_macroview']['snapshot']['market_expectations'][0]['probabilities'][0],'0.63')
            raw={**self.raw,'outcomePrices':['0.70','0.30']}
            store.ingest_projection(self.projected(markets.parse_markets([raw],'2026-10-07T10:20:00Z')),observed_at='2026-10-07T10:20:00Z')
            self.assertNotIn('0.70',json.dumps(replay_event_as_of(store,self.eid,'2026-10-07T10:15:00Z')))

    def test_late_link_never_backdated_to_snapshot(self):
        with tempfile.TemporaryDirectory(prefix='a72-late-link-') as t:
            store=IntelligenceStore(Path(t)/'store.db',create=True)
            unlinked=copy.deepcopy(self.view);unlinked.update(markets.project_expectations(unlinked['events'],[self.market],{}))
            store.ingest_projection(unlinked,observed_at=MARKET_TIME)
            store.ingest_projection(self.projected(),observed_at='2026-10-07T10:30:00Z')
            self.assertEqual(replay_event_as_of(store,self.eid,'2026-10-07T10:20:00Z')['reconstructed_macroview']['expectation_state'],'NONE')
            self.assertEqual(replay_event_as_of(store,self.eid,'2026-10-07T10:30:00Z')['reconstructed_macroview']['expectation_state'],'EXPECTATION_PRESENT')

    def test_explicit_multiple_curated_ids_and_invalid_fence(self):
        records=markets.parse_markets([self.raw,raw_market('test-hold')],MARKET_TIME)
        p=markets.project_expectations([self.event],records,{self.eid:['test-cut','test-hold']})
        self.assertEqual(len(p['events'][0]['market_expectation_ids']),2)
        invalid=markets.project_expectations([self.event],records,{self.eid:['wrong']})
        self.assertEqual(invalid['expectation_link_status'],'INVALID_MAPPING')
        self.assertFalse(any(x['link_status']=='LINKED' for x in invalid['event_expectation_links']))

    def test_configured_unreadable_mapping_disables_autolink(self):
        with tempfile.TemporaryDirectory() as t:
            p=radar.project_market_records([self.event],[self.market],Path(t)/'missing.json')
            self.assertEqual(p['expectation_link_status'],'UNAVAILABLE')
            self.assertEqual(p['events'][0]['market_expectation_ids'],[])

    def test_saved_csv_adapter_to_api_no_provider_and_no_source_write(self):
        with tempfile.TemporaryDirectory(prefix='a72-api-') as t:
            t=Path(t);news=t/'rss_headlines_fixture.csv';raw=t/'markets.json'
            news.write_text('observed_time,event_time,headline_or_text,source_name,source_url\n'+
                EVENT_TIME+',,ECB rate decision October 15 2026,Synthetic fixture,https://example.test/meeting\n',encoding='utf-8')
            raw.write_text(json.dumps([{**self.raw,'observed_at':MARKET_TIME}]),encoding='utf-8')
            before=(news.read_bytes(),raw.read_bytes())
            env=dict(GLOBAL_EVENT_RADAR_NEWS_PATH=str(news),GLOBAL_EVENT_RADAR_POLYMARKET_PATH=str(raw),
                GLOBAL_EVENT_RADAR_OFFICIAL_PATH='',GLOBAL_EVENT_RADAR_EXPECTATION_LINKS_PATH='',
                GLOBAL_EVENT_RADAR_SOURCE_HEALTH_PATH='',GLOBAL_EVENT_RADAR_MACROVIEW_PATH='',GLOBAL_EVENT_RADAR_GEOGRAPHY_PATH='',GLOBAL_EVENT_RADAR_MARKET_REALITY_PATH='')
            with patch.dict(os.environ,env),patch.object(markets,'fetch_gamma',side_effect=AssertionError('NETWORK_FORBIDDEN')):
                handler=object.__new__(app.Handler);handler.path='/api/app/radar'
                handler.server=Mock(radar_only=True,live_ingestion=None,expectation_sensor=None)
                handler.reply=Mock();handler.do_GET()
                status,view=handler.reply.call_args.args
                self.assertEqual(status,200)
            self.assertEqual(view['market_expectations'][0]['link_status'],'LINKED')
            self.assertEqual(view['macroview_previews'][0]['expectation_state'],'EXPECTATION_PRESENT')
            self.assertEqual(before,(news.read_bytes(),raw.read_bytes()))

    def render(self,view):
        node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
        result=subprocess.run([str(node),str(ROOT/'tests/ui_render_harness.cjs')],input=json.dumps(dict(view=view,
            html=(ROOT/'ui/radar_public_showcase_v1.html').read_text('utf-8'),
            translations=(ROOT/'ui/radar_demo_translations.js').read_text('utf-8'))),
            encoding='utf-8',capture_output=True,check=True)
        return json.loads(result.stdout)

    def test_public_and_chinese_rendering_and_xss(self):
        p=self.projected();p['market_expectations'][0]['question']='<img src=x onerror=alert(1)>'
        ui=self.render(p)
        self.assertIn('Market Expectations',ui['en']);self.assertIn('市場預期',ui['zh'])
        self.assertIn('63%',ui['en']);self.assertIn(MARKET_TIME,ui['zh'])
        self.assertIn('do not verify facts',ui['en']);self.assertIn('不代表事實',ui['zh'])
        self.assertIn('https://polymarket.com/event/synthetic-meeting',ui['en'])
        self.assertIn('&lt;img',ui['en']);self.assertNotIn('<img src=x',ui['en'])
        self.assertTrue(ui['unchanged'])

    def test_no_match_panels_hidden(self):
        p=copy.deepcopy(self.view);p['macroview_previews']=build_previews(p)
        ui=self.render(p)
        self.assertNotIn('class="expectation-panel"',ui['en'])
        self.assertNotIn('no-linked-market',ui['zh'])

    def test_missing_probability_stays_unknown(self):
        p=self.projected();p['market_expectations'][0]['probabilities']=None
        ui=self.render(p)
        self.assertIn('Unknown',ui['en']);self.assertIn('未知',ui['zh'])
        self.assertNotIn('Yes: 0%',ui['en'])

    def test_empty_and_duplicate_snapshot_inputs(self):
        self.assertEqual(linker.link_events([],[]),[])
        duplicate=markets.project_expectations([self.event],[self.market,self.market])
        self.assertEqual(len(duplicate['market_expectations']),1)
        conflicting={**self.market,'question':'A different proposition'}
        self.assertEqual(markets.project_expectations([self.event],[self.market,conflicting])['market_expectations'],[])

    def test_empty_curated_mapping_disables_automatic_links(self):
        p=markets.project_expectations([self.event],[self.market],{})
        self.assertEqual(p['expectation_link_status'],'AVAILABLE')
        self.assertEqual(p['events'][0]['market_expectation_ids'],[])


if __name__=='__main__':unittest.main()
