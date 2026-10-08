"""Actual A7.3 parser/cache/API/UI with deterministic local inputs only."""
import copy
from email.message import Message
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from tools.stage1b_historical_campaign import radar_prediction_market_watch as watch
from tools.stage1b_historical_campaign import radar_market_expectations as market
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign import radar_web_server as app
from tools.stage1b_historical_campaign.radar_intelligence_store import IntelligenceStore, configured_db
from tools.stage1b_historical_campaign.radar_reality_replay import replay_event_as_of

ROOT = Path(__file__).resolve().parents[1]
NOW, LATER = '2026-10-08T16:00:00Z', '2026-10-08T16:10:00Z'


def raw(question='Will ECB cut interest rates October 15 2026?', identity='1', **values):
    return dict(id=identity, question=question, outcomes=['No', 'Yes'], outcomePrices=['0.37', '0.63'],
                active=True, closed=False, endDate='2026-10-16T20:00:00Z', updatedAt='2026-10-08T15:50:00Z',
                events=[dict(id='101', slug='synthetic-fixture-meeting', title=question)], **values)


def response(row=None):
    return dict(events=[dict(id='101', slug='synthetic-fixture-meeting', title='ECB rates October 15 2026',
                            markets=[row or raw()])])


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.row = raw()
        self.records = watch.normalized_rows([self.row], NOW)
        self.t = tempfile.TemporaryDirectory(prefix='radar-watch-test-')
        self.root = Path(self.t.name)
        self.news = self.root/'rss_headlines_fixture.csv'
        self.news.write_text('observed_time,event_time,headline_or_text,source_name,source_url\n'
                             '2026-10-08T15:00:00Z,,ECB interest rate decision October 15 2026,Synthetic fixture,https://example.test/ecb\n', encoding='utf8')
        self.base = radar.build_radar_view(radar.EvidencePaths(news=self.news))
        self.eid = self.base['events'][0]['event_id']
        self.tick = 0

    def tearDown(self):
        self.t.cleanup()

    def sensor(self, fetcher=None, **kwargs):
        return watch.PredictionMarketWatch(enabled=True, fetcher=fetcher or Mock(return_value=response()),
                                          clock=lambda: NOW, monotonic=lambda: self.tick, **kwargs)

    def project(self, records=None):
        view = copy.deepcopy(self.base)
        view.update(market.project_expectations(view['events'], records or self.records))
        view['prediction_market_watch'] = watch.build_watch(view['market_expectations'], now=NOW)
        return view

    def test_gamma_shape_and_allowlisted_metadata(self):
        row=raw(liquidity='123.45',volume=890,description='Provider settlement description',resolutionSource='https://www.ecb.europa.eu')
        row.update(wallet='TESTX',api_key='TESTX')
        record=watch.normalized_rows([row],NOW)[0]
        output=watch.build_watch([record],now=NOW)['markets'][0]
        self.assertEqual((output['liquidity'],output['volume']),('123.45',890))
        self.assertEqual(output['provider_updated_at'],'2026-10-08T15:50:00Z')
        self.assertEqual(output['provider_event_ids'],['101'])
        self.assertNotIn('TESTX',json.dumps(output))

    def test_provider_outcome_identifiers_follow_labels_only_when_aligned(self):
        row=raw();row['clobTokenIds']='["111", "222"]'
        record=watch.build_watch(watch.normalized_rows([row],NOW),now=NOW)['markets'][0]
        self.assertEqual(list(zip(record['outcomes'],record['outcome_identifiers'])),[('No','111'),('Yes','222')])
        self.assertEqual(record['outcome_identifier_kind'],'CLOB_TOKEN_ID')
        row['clobTokenIds']='["111"]'
        row['positionIds']=['333','444']
        record=watch.build_watch(watch.normalized_rows([row],NOW),now=NOW)['markets'][0]
        self.assertEqual(record['outcome_identifiers'],['333','444'])
        self.assertEqual(record['outcome_identifier_kind'],'POSITION_ID')
        row['positionIds']=['333']
        record=watch.build_watch(watch.normalized_rows([row],NOW),now=NOW)['markets'][0]
        self.assertIsNone(record['outcome_identifiers'])

    def test_reversed_binary_labels_never_first_is_yes(self):
        record=watch.build_watch(self.records,now=NOW)['markets'][0]
        self.assertEqual(record['outcome_type'],'BINARY_YES_NO')
        self.assertEqual(list(zip(record['outcomes'],record['probabilities'])),[('No','0.37'),('Yes','0.63')])

    def test_multi_outcomes_no_sum_normalization_or_exclusivity(self):
        row=raw();row.update(outcomes=['Cut','Hold','Hike'],outcomePrices=['0.2','0.2','0.3'])
        record=watch.build_watch(watch.normalized_rows([row],NOW),now=NOW)['markets'][0]
        self.assertEqual(record['outcome_type'],'MULTI_OUTCOME')
        self.assertEqual(record['probabilities'],['0.2','0.2','0.3'])
        self.assertNotIn('mutually_exclusive',record)

    def test_two_non_binary_labels_are_categorical(self):
        row=raw();row['outcomes']=['Cut','Hold']
        self.assertEqual(watch.build_watch(watch.normalized_rows([row],NOW),now=NOW)['markets'][0]['outcome_type'],'CATEGORICAL')

    def test_invalid_probability_null(self):
        for value in [True,'NaN','inf',-1,1.1,None,{}]:
            with self.subTest(value=value):
                row=raw();row['outcomePrices']=[value,'0.3']
                self.assertIsNone(watch.normalized_rows([row],NOW)[0]['probabilities'][0])

    def test_missing_values_stay_null(self):
        row=raw()
        for field in ['outcomes','outcomePrices','updatedAt','endDate','events']:row.pop(field)
        record=watch.build_watch(watch.normalized_rows([row],NOW),now=NOW)['markets'][0]
        for key in ['outcomes','probabilities','provider_updated_at','market_close_time','market_url','liquidity','volume']:
            self.assertIsNone(record[key])

    def test_amounts_invalid_remain_unknown(self):
        for value in [-1,True,'NaN',float('inf'),{}]:
            row=raw(liquidity=value,volume=value)
            self.assertIsNone(watch.build_watch(watch.normalized_rows([row],NOW),now=NOW)['markets'][0]['liquidity'])

    def test_duplicate_market_dedup(self):
        self.assertEqual(watch.normalized_rows([self.row,self.row],NOW),self.records)

    def test_conflicting_duplicate_excluded(self):
        other=copy.deepcopy(self.row);other['outcomePrices']=['0.3','0.7']
        self.assertEqual(watch.normalized_rows([self.row,other],NOW),[])

    def test_supported_macro_categories(self):
        cases={'Will Fed cut rates?':'MONETARY_POLICY','Will China tariffs increase?':'ECONOMY_TRADE',
               'Will OPEC reduce oil production?':'ENERGY','Will US strike Iran?':'GEOPOLITICS'}
        for q,category in cases.items():
            self.assertEqual(watch.category(market.parse_markets(raw(q),NOW)[0]),category)

    def test_relevance_reason_names_actual_question_cue(self):
        row=watch.build_watch(watch.normalized_rows([raw('Will the Fed cut interest rates?')],NOW),now=NOW)['markets'][0]
        self.assertEqual(row['relevance_reason'],'QUESTION:fed')

    def test_active_macro_categories_survive_twenty_market_limit(self):
        questions=['Will Fed cut rates?','Will China tariffs rise?','Will OPEC cut oil production?','Will US strike Iran?']
        rows=[]
        for index in range(32):
            row=raw(questions[index//8],identity=str(index+1))
            if index%8==0:row['closed']=True
            rows.append(row)
        records=watch.normalized_rows(rows,NOW)
        self.assertEqual(len(records),20)
        self.assertEqual({watch.category(record) for record in records},set(watch.CATEGORIES))
        self.assertTrue(all(record['proposition_metadata']['closed'] is False for record in records))
        self.assertEqual(records,watch.normalized_rows(list(reversed(rows)),NOW))

    def test_unrelated_elections_sports_crypto_entertainment_rejected(self):
        for q in ['Who wins the election?','Xi Jinping out before 2027?','NBA champion?',
                  'Bitcoin above 100000?','New album this year?','Fed cup tennis winner?']:
            with self.subTest(q=q):self.assertEqual(watch.normalized_rows([raw(q)],NOW),[])

    def test_political_policy_question_can_qualify(self):
        self.assertEqual(watch.category(market.parse_markets(raw('Will Trump impose tariffs on China?'),NOW)[0]),'ECONOMY_TRADE')

    def test_active_closed_unknown_are_separate(self):
        row=raw();row['closed']=True
        self.assertEqual(watch.build_watch(watch.normalized_rows([row],NOW),now=NOW)['markets'][0]['market_status'],'CLOSED')
        row.pop('closed');row.pop('active')
        self.assertEqual(watch.build_watch(watch.normalized_rows([row],NOW),now=NOW)['markets'][0]['market_status'],'UNKNOWN')
        self.assertEqual(watch.build_watch(self.records,now=NOW)['markets'][0]['market_status'],'ACTIVE')

    def test_saved_is_never_live(self):
        self.assertEqual(watch.build_watch(self.records,now=NOW)['markets'][0]['source_status'],'SAVED_SNAPSHOT')

    def test_stale_snapshot_not_hidden(self):
        r=watch.build_watch(self.records,now='2026-10-09T16:00:00Z')['markets'][0]
        self.assertEqual((r['source_status'],r['freshness']),('STALE','STALE'))

    def test_missing_observation_not_live(self):
        r=copy.deepcopy(self.records);r[0]['observed_at']=None
        row=watch.build_watch(r,now=NOW,provider={'status':'LIVE_FETCHED'})['markets'][0]
        self.assertIsNone(row['observed_at']);self.assertEqual(row['freshness'],'UNKNOWN');self.assertNotEqual(row['source_status'],'LIVE_FETCHED')

    def test_default_disabled_no_provider(self):
        f=Mock();s=watch.PredictionMarketWatch(fetcher=f)
        self.assertFalse(s.refresh());self.assertEqual(s.snapshot()[0],[]);f.assert_not_called()

    def test_success_cached_shared_no_repeat_requests(self):
        f=Mock(return_value=response());s=self.sensor(f)
        first,state=s.snapshot();self.assertEqual(state['status'],'LIVE_FETCHED');self.assertEqual(f.call_count,4)
        second,state=s.snapshot();self.assertEqual(state['status'],'CACHED');self.assertEqual(first,second);self.assertEqual(f.call_count,4)
        self.assertIsNone(getattr(s,'thread',None))

    def test_ttl_refresh_learns_later_time(self):
        s=self.sensor();first=s.snapshot()[0][0]['expectation_id'];self.tick=1801;s.clock=lambda:LATER
        self.assertNotEqual(s.snapshot()[0][0]['expectation_id'],first)

    def test_timeout_failure_no_retry_and_no_fake_rows(self):
        f=Mock(side_effect=TimeoutError());s=self.sensor(f)
        self.assertFalse(s.refresh());self.assertEqual(s.snapshot()[0],[]);self.assertEqual(f.call_count,1)

    def test_rate_limited_default_six_hour_hold(self):
        f=Mock(side_effect=HTTPError('https://gamma-api.polymarket.com/public-search',429,'rate',Message(),None));s=self.sensor(f)
        self.assertFalse(s.refresh());self.tick=1801;s.snapshot();self.assertEqual(f.call_count,1)
        self.assertEqual(s.state['reason'],'RATE_LIMITED');self.assertEqual(s.next_attempt,21600)

    def test_rate_limit_actual_numeric_header(self):
        headers=Message();headers['Retry-After']='3600'
        s=self.sensor(Mock(side_effect=HTTPError('url',429,'rate',headers,None)))
        s.refresh();self.assertEqual(s.next_attempt,3600)

    def test_failure_retains_explicit_stale_cache(self):
        f=Mock(return_value=response());s=self.sensor(f);original=s.snapshot()[0]
        self.tick=1801;f.side_effect=TimeoutError();rows,state=s.snapshot()
        self.assertEqual(rows,original);self.assertEqual(state['status'],'STALE')

    def test_invalid_provider_payload_fail_isolated(self):
        s=self.sensor(Mock(return_value={'html':'wrong'}));self.assertFalse(s.refresh());self.assertEqual(s.records,[])

    def test_event_detail_binds_provider_group(self):
        f=Mock(side_effect=[{'events':[{'id':'101'}]},{'events':[]},{'events':[]},{'events':[]},response()['events'][0]]);s=self.sensor(f)
        self.assertTrue(s.refresh());self.assertEqual(f.call_args_list[4].args[0],'/events/101')
        self.assertEqual(s.records[0]['market_url'],'https://polymarket.com/event/synthetic-fixture-meeting')

    def test_detail_wrong_id_rejected(self):
        f=Mock(side_effect=[{'events':[{'id':'101'}]},{'events':[]},{'events':[]},{'events':[]},{'id':'102','markets':[]}]);s=self.sensor(f)
        self.assertFalse(s.refresh());self.assertEqual(f.call_count,5)

    def test_search_round_robin_keeps_later_geopolitical_query(self):
        labels=['Will Fed cut rates?','Will China tariffs rise?','Will OPEC cut oil production?','Will US strike Iran?']
        counter={'value':0}
        def fetch(path,params):
            self.assertEqual(path,'/public-search')
            query_index=watch.QUERIES.index(params['q'])
            counter['value']+=1
            return {'events':[{'id':str(100+query_index*3+i),'title':labels[query_index],
                              'slug':'fixture','markets':[raw(labels[query_index],identity=str(100+query_index*3+i))]}
                             for i in range(3)]}
        sensor=self.sensor(fetch)
        self.assertTrue(sensor.refresh());self.assertEqual(counter['value'],4)
        self.assertEqual(len(sensor.records),8)
        self.assertEqual(watch.build_watch(sensor.records,now=NOW)['category_counts'],
                         {kind:2 for kind in watch.CATEGORIES})

    def test_maximum_twelve_requests(self):
        index=iter(range(101,120))
        def fetch(path,params):
            if path=='/public-search':return {'events':[{'id':str(next(index))} for _ in range(3)]}
            eid=path.split('/')[-1];return {'id':eid,'slug':'fixture','markets':[raw(identity=eid)]}
        s=self.sensor(fetch);self.assertTrue(s.refresh());self.assertEqual(s.total_requests,12);self.assertEqual(len(s.records),8)

    def test_concurrent_snapshot_does_not_duplicate_batch(self):
        f=Mock(return_value=response());s=self.sensor(f)
        threads=[threading.Thread(target=s.snapshot) for _ in range(16)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(5)
        self.assertTrue(all(not t.is_alive() for t in threads));self.assertEqual(f.call_count,4)

    def test_readonly_discovery_paths_only(self):
        for path in ['/orders','/wallet','/markets/../orders','http://bad.test','/events/a']:
            with self.assertRaises(market.ExpectationError):watch.fetch_json(path)

    def test_transport_uses_verified_tls_and_no_redirect(self):
        result=Mock();result.status=200;result.geturl.return_value='https://gamma-api.polymarket.com/public-search?q=Fed'
        result.headers=Message();result.headers['Content-Type']='application/json';result.read.return_value=b'{"events":[]}'
        result.__enter__=Mock(return_value=result);result.__exit__=Mock(return_value=False)
        opener=Mock();opener.open.return_value=result
        with patch.object(watch,'build_opener',return_value=opener) as build:
            self.assertEqual(watch.fetch_json('/public-search',{'q':'Fed'}),{'events':[]})
        handler=build.call_args.args[0];self.assertEqual(handler._context.verify_mode,ssl.CERT_REQUIRED);self.assertTrue(handler._context.check_hostname)
        self.assertIsInstance(build.call_args.args[1],market.NoRedirect)

    def test_no_match_visible_independent_of_event(self):
        records=watch.normalized_rows([raw('Will OPEC cut oil output?')],NOW);view=self.project(records)
        self.assertEqual(view['prediction_market_watch']['market_count'],1)
        self.assertEqual(view['prediction_market_watch']['markets'][0]['link_status'],'NO_MATCH')
        self.assertFalse(view['events'][0]['market_expectation_ids'])

    def test_valid_link_and_official_geography_isolation(self):
        view=self.project();r=view['prediction_market_watch']['markets'][0]
        self.assertEqual(r['link_status'],'LINKED');self.assertEqual(r['canonical_event_id'],self.eid)
        for before,after in zip(self.base['events'],view['events']):
            self.assertEqual(before['event_geography'],after['event_geography']);self.assertEqual(after['verification_status'],'UNVERIFIED_NEWS')
        self.assertEqual(view['official_evidence'],self.base['official_evidence'])

    def test_api_feed_uses_watch_same_contract_and_failures_leave_news(self):
        env={'GLOBAL_EVENT_RADAR_NEWS_PATH':str(self.news),'GLOBAL_EVENT_RADAR_OFFICIAL_PATH':'',
             'GLOBAL_EVENT_RADAR_POLYMARKET_PATH':'','GLOBAL_EVENT_RADAR_SOURCE_HEALTH_PATH':'','GLOBAL_EVENT_RADAR_MACROVIEW_PATH':''}
        s=self.sensor(Mock(side_effect=TimeoutError()))
        with patch.dict(os.environ,env):view=app.feed_view(market_watch=s)
        self.assertEqual(len(view['events']),1);self.assertEqual(view['prediction_market_watch']['status'],'UNAVAILABLE')

    def test_freeze_immutable_and_replay_no_future_probability(self):
        db=IntelligenceStore(self.root/'private.sqlite3',create=True);view=self.project();db.ingest_projection(view,observed_at=NOW)
        old=db.freeze_event(self.eid,freeze_key='fixture',as_of=NOW,created_at=NOW)
        row=raw();row['outcomePrices']=['0.30','0.70'];later=self.project(watch.normalized_rows([row],LATER));db.ingest_projection(later,observed_at=LATER)
        self.assertEqual(db.freezes(self.eid)[0],old)
        self.assertEqual(replay_event_as_of(db,self.eid,'2026-10-08T15:59:59Z')['replay_status'],'NO_OBSERVATIONS')
        self.assertEqual(replay_event_as_of(db,self.eid,NOW)['reconstructed_macroview']['snapshot']['market_expectations'][0]['probabilities'][1],'0.63')
        self.assertEqual(replay_event_as_of(db,self.eid,LATER)['reconstructed_macroview']['snapshot']['market_expectations'][0]['probabilities'][1],'0.70')

    def test_private_variable_cannot_enable_public_store(self):
        with patch.dict(os.environ,{'RADAR_PRIVATE_INTELLIGENCE_DB':str(self.root/'private.sqlite3')},clear=True):self.assertIsNone(configured_db())

    def test_actual_bilingual_ui_and_escaping(self):
        from test_bilingual_visual_ui import NODE
        row=raw('Will oil supply fall? <img src=x onerror=alert(1)>');row['outcomePrices']=[None,'0.63']
        view=self.project(watch.normalized_rows([row],NOW))
        payload={'html':(ROOT/'ui/radar_public_showcase_v1.html').read_text('utf8'),'view':view,
                 'translations':(ROOT/'ui/radar_demo_translations.js').read_text('utf8')}
        result=subprocess.run([str(NODE),str(ROOT/'tests/ui_render_harness.cjs')],input=json.dumps(payload),capture_output=True,text=True,encoding='utf8',timeout=10,check=True)
        rendered=json.loads(result.stdout)
        for label in ['Prediction Market Watch','Energy','Observed At','Provider Updated At','63%','Unknown','NO_MATCH']:
            self.assertIn(label,rendered['en'])
        for label in ['預測市場觀察','能源','觀察時間','來源更新時間','63%','未知']:
            self.assertIn(label,rendered['zh'])
        self.assertNotIn('<img src=x',rendered['en']);self.assertIn('&lt;img',rendered['en']);self.assertTrue(rendered['unchanged'])

    def test_empty_and_unavailable_are_truthful(self):
        self.assertEqual(watch.build_watch([],provider={'status':'UNAVAILABLE'},now=NOW)['status'],'UNAVAILABLE')
        self.assertEqual(watch.build_watch([],provider={'status':'SAVED_SNAPSHOT'},now=NOW)['status'],'EMPTY')

    def test_category_counts_are_bounded_to_visible_markets(self):
        records=[]
        for i in range(30):records+=market.parse_markets(raw(identity=str(i)),NOW)
        view=watch.build_watch(records,now=NOW)
        self.assertEqual(view['market_count'],20);self.assertEqual(sum(view['category_counts'].values()),20)

    def test_wrong_market_link_not_advertised(self):
        view=self.project();record=view['market_expectations'][0]
        record['event_expectation_link']['expectation_market_id']='wrong'
        result=watch.build_watch([record],now=NOW)['markets'][0]
        self.assertEqual(result['link_status'],'NO_MATCH');self.assertIsNone(result['canonical_event_id'])


if __name__=='__main__':
    unittest.main()
