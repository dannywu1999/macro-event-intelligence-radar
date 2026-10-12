"""One licensed daily EX_POST case; separate from A8 point-in-time observations.
No acquisition, private database, provider keys, interpolation or trading. Uses
existing canonical/Official constructors without adding history to current News.
"""
from __future__ import annotations
import csv, hashlib, io, json
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import TypedDict
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign.radar_impact_hypotheses import project as impact
from tools.stage1b_historical_campaign.radar_market_reality import public_observation

ROOT=Path(__file__).resolve().parents[2]
CASE=ROOT/'demo/radar_public/market_reaction/ecb_2025_06_05.json'
DATA=ROOT/'demo/radar_public/market_reaction/ecb_eurusd_2025_06.csv'
EVENT_SOURCE='https://www.ecb.europa.eu/press/pr/date/2025/html/ecb.mp250605~3b5f67d007.en.html'
DATA_SOURCE='https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?startPeriod=2025-06-02&endPeriod=2025-06-10&format=csvdata'
RIGHTS='https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html'
METHODLOGY='https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html'
RESEARCH_CASES=(
    dict(case_id='ecb-2025-03-06', event_date='2025-03-06', effective_date='2025-03-12',
         case_path=ROOT/'demo/radar_public/market_reaction/ecb_2025_03_06.json',
         data_path=ROOT/'demo/radar_public/market_reaction/ecb_eurusd_2025_03.csv',
         event_source='https://www.ecb.europa.eu/press/pr/date/2025/html/ecb.mp250306~d4340800b3.en.html',
         data_source='https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?startPeriod=2025-03-04&endPeriod=2025-03-10&format=csvdata'),
    dict(case_id='ecb-2025-04-17', event_date='2025-04-17', effective_date='2025-04-23',
         case_path=ROOT/'demo/radar_public/market_reaction/ecb_2025_04_17.json',
         data_path=ROOT/'demo/radar_public/market_reaction/ecb_eurusd_2025_04.csv',
         event_source='https://www.ecb.europa.eu/press/pr/date/2025/html/ecb.mp250417~42727d0735.en.html',
         data_source='https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?startPeriod=2025-04-14&endPeriod=2025-04-23&format=csvdata'),
)
FACT_SUMMARIES_ZH_TW={
    '2025-03-06':'ECB 決定將三項主要利率下調 25 個基點；存款便利利率、主要再融資操作利率與邊際貸款便利利率分別降至 2.50%、2.65% 與 2.90%，自 2025 年 3 月 12 日生效。',
    '2025-04-17':'ECB 決定將三項主要利率下調 25 個基點；存款便利利率、主要再融資操作利率與邊際貸款便利利率分別降至 2.25%、2.40% 與 2.65%，自 2025 年 4 月 23 日生效。',
    '2025-06-05':'ECB 決定將三項主要利率下調 25 個基點；存款便利利率、主要再融資操作利率與邊際貸款便利利率分別降至 2.00%、2.15% 與 2.40%，自 2025 年 6 月 11 日生效。',
}
class ReactionReceipt(TypedDict):
    contract: str
    event_id: str
    event_source: str
    event_timestamp_utc: None
    event_timestamp_precision: str
    instrument_id: str
    instrument_name: str
    market_data_source: str
    market_data_provider: str
    market_data_license_status: str
    data_frequency: str
    observation_start_utc: None
    observation_end_utc: None
    observation_start_date: str
    observation_end_date: str
    event_date: str
    source_published_at: None
    event_effective_time: None
    event_effective_date: str
    system_observed_at: str
    knowledge_at: str
    observations: list[dict]
    pre_event_observation: dict
    post_event_observation: dict
    absolute_change: str
    percentage_change: str
    window: str
    elapsed_calendar_days: int
    intervening_unobserved_dates: list[str]
    observed_market_reaction: str
    missing_data_reasons: list[str]
    observation_quality: str
    causal_attribution_status: str
    hypothesis_comparison: str
    time_basis: str
    point_in_time_available: bool
    freshness_status: str
    timezone: str
    session_calendar: str
    adjustment: str
    license: dict
    provenance: dict
    synthetic: bool
    data_usage_scope: str

def day(value):
    if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:raise ValueError('INVALID_DATE')
    return value

def rates(raw):
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    if not 2<=len(rows)<=32:raise ValueError('INVALID_DATA_COUNT')
    result=[];seen=set()
    for row in rows:
        if any(row.get(k)!=v for k,v in {'KEY':'EXR.D.USD.EUR.SP00.A','FREQ':'D','CURRENCY':'USD','CURRENCY_DENOM':'EUR','EXR_TYPE':'SP00','EXR_SUFFIX':'A','UNIT':'USD','UNIT_MULT':'0','SOURCE_AGENCY':'4F0','OBS_STATUS':'A'}.items()):raise ValueError('INSTRUMENT_OR_DATASET_MISMATCH')
        label=day(row['TIME_PERIOD']);value=Decimal(row['OBS_VALUE'])
        if label in seen or not value.is_finite() or value<=0:raise ValueError('INVALID_OBSERVATION')
        seen.add(label)
        result.append(dict(observation_date=label,market_observation_time=None,timestamp_precision='PROVIDER_DATE_ONLY',value=str(value),unit='USD_PER_EUR',provider='European Central Bank',source_observation_id='EXR.D.USD.EUR.SP00.A:'+label,synthetic=False,data_usage_scope='PUBLIC_REDISTRIBUTABLE'))
    if [r['observation_date'] for r in result]!=sorted(seen):raise ValueError('UNORDERED_OBSERVATIONS')
    return result

def calculate(event_date,observations):
    day(event_date)
    pre=[r for r in observations if r['observation_date']<event_date]
    post=[r for r in observations if r['observation_date']>event_date]
    if not pre or not post:raise ValueError('NO_SUPPORTED_BEFORE_AFTER_WINDOW')
    a,b=pre[-1],post[0];x,y=Decimal(a['value']),Decimal(b['value'])
    return dict(pre_event_observation=deepcopy(a),post_event_observation=deepcopy(b),
                absolute_change=str(y-x),percentage_change=str(((y-x)/x*100).quantize(Decimal('0.000001'))),
                window='PREVIOUS_AVAILABLE_PROVIDER_DATE_TO_FIRST_LATER_PROVIDER_DATE',
                elapsed_calendar_days=(date.fromisoformat(b['observation_date'])-date.fromisoformat(a['observation_date'])).days,
                intervening_unobserved_dates=[date.fromordinal(d).isoformat() for d in range(date.fromisoformat(a['observation_date']).toordinal()+1,date.fromisoformat(b['observation_date']).toordinal()) if not any(r['observation_date']==date.fromordinal(d).isoformat() for r in observations)])

def load_case(case_path=CASE,data_path=DATA,*,expected_event_source=EVENT_SOURCE,
              expected_market_data_source=DATA_SOURCE,expected_event_date='2025-06-05',
              expected_effective_date='2025-06-11',case_id='ecb-2025-06-05'):
    try:
        b=Path(case_path).read_bytes();raw=Path(data_path).read_bytes()
        if len(b)>32768 or len(raw)>131072:raise ValueError('CASE_TOO_LARGE')
        p=json.loads(b)
        if p.get('schema')!='ECB_DAILY_REACTION_CASE_V0' or p.get('synthetic') is not False:raise ValueError('INVALID_CASE')
        if p.get('event_source')!=expected_event_source or p.get('market_data_source')!=expected_market_data_source:raise ValueError('SOURCE_MISMATCH')
        if p.get('event_date')!=expected_event_date or p.get('event_effective_date')!=expected_effective_date or p.get('event_timestamp_precision')!='DATE_ONLY' or any(p.get(k) is not None for k in ['event_timestamp_utc','event_effective_time','source_published_at']):raise ValueError('UNSUPPORTED_EVENT_CLOCK')
        if p.get('document_title')!='Monetary policy decisions' or not isinstance(p.get('fact_proposition'),str) or not p['fact_proposition'].strip():raise ValueError('INVALID_OFFICIAL_PROPOSITION')
        license=p['license']
        if license.get('status')!='PUBLIC_REDISTRIBUTABLE_WITH_ATTRIBUTION' or license.get('source')!='European Central Bank' or license.get('url')!=RIGHTS or not license.get('conditions'):raise ValueError('PUBLIC_RIGHTS_UNESTABLISHED')
        for k in ['event_document_sha256','market_data_sha256']:
            if len(p[k])!=64 or any(c not in '0123456789abcdef' for c in p[k]):raise ValueError('INVALID_SOURCE_HASH')
        if hashlib.sha256(raw).hexdigest()!=p['market_data_sha256']:raise ValueError('DATA_HASH_MISMATCH')
        known=radar._utc(p.get('market_data_retrieved_at'));observed=radar._utc(p.get('system_observed_at'))
        if known is None or observed is None:raise ValueError('INVALID_KNOWLEDGE_TIME')
        observations=rates(raw)
        if any(date.fromisoformat(r['observation_date'])>known.date() for r in observations):raise ValueError('FUTURE_OBSERVATION')
        if any(not public_observation(r) for r in observations):raise ValueError('NONPUBLIC_OBSERVATION')
        event_date=day(p['event_date']);effective_date=day(p['event_effective_date'])
        article=dict(article_reference=p['event_source'],discovery_record_id=p['event_source'],title=p['document_title'],observed_at=p['system_observed_at'],discovered_at=p['system_observed_at'],reported_at=None,reported_time_kind='UNKNOWN',event_occurred_at=None,verification_status='UNVERIFIED_NEWS',news_source={'name':'European Central Bank','url':p['event_source'],'published_at':None})
        events=radar.build_canonical_events([article])['events']
        packet=dict(official_confirmation='OFFICIAL_CONFIRMED',authority_role='FACT_AUTHORITY',authority_name='European Central Bank',document_title=p['document_title'],official_source=p['event_source'],official_document_reference=p['event_source'],official_fact_proposition=p['fact_proposition'],official_published_at=None,official_project_first_seen_at=p['system_observed_at'],official_retrieved_at=p['system_observed_at'],article_reference=p['event_source'],document_sha256=p['event_document_sha256'])
        official=radar.build_official_evidence_projection([packet],[article],events)
        event=radar.build_event_timelines([article],official['official_evidence'],official['events'])[0]
        case_view={'items':[article],'events':[event],'official_evidence':official['official_evidence']}
        interpretation=impact(case_view)
        receipt=ReactionReceipt(contract='MARKET_REACTION_RECEIPT_V0',event_id=event['event_id'],event_source=p['event_source'],event_timestamp_utc=None,event_timestamp_precision='DATE_ONLY',instrument_id='EURUSD_ECB_REFERENCE',instrument_name='EUR/USD · ECB daily reference rate',market_data_source=p['market_data_source'],market_data_provider='European Central Bank',market_data_license_status=license['status'],data_frequency='DAILY_REFERENCE_RATE_NOT_TRADED_CLOSE',observation_start_utc=None,observation_end_utc=None,observation_start_date=observations[0]['observation_date'],observation_end_date=observations[-1]['observation_date'],event_date=event_date,source_published_at=None,event_effective_time=None,event_effective_date=effective_date,system_observed_at=p['system_observed_at'],knowledge_at=p['market_data_retrieved_at'],observations=observations,**calculate(event_date,observations),observed_market_reaction='EX_POST_DAILY_REFERENCE_CHANGE',missing_data_reasons=['NO_EXACT_EVENT_PUBLICATION_TIME','NO_EXACT_REFERENCE_OBSERVATION_TIME','NO_INTRADAY_DATA','NO_PUBLIC_POINT_IN_TIME_HISTORY'],observation_quality='OFFICIAL_DAILY_REFERENCE_NOT_EXECUTABLE_QUOTE',causal_attribution_status='NOT_ESTABLISHED',hypothesis_comparison='INCONCLUSIVE_NO_DIRECTIONAL_FORECAST',time_basis='EX_POST_MARKET_OBSERVATION',point_in_time_available=False,freshness_status='HISTORICAL_SAVED_OBSERVATION_NOT_LIVE',timezone='PROVIDER_REFERENCE_DATE;INTRADAY_UTC_UNKNOWN',session_calendar='PROVIDER_OBSERVATION_DATES;NOT_FULL_FX_OR_HOLIDAY_CALENDAR',adjustment='NOT_APPLICABLE_FX;NO_CORPORATE_ACTION_ADJUSTMENT',license=license,provenance={'data_sha256':p['market_data_sha256'],'event_document_sha256':p['event_document_sha256'],'methodology_url':p.get('methodology_url',METHODLOGY)},synthetic=False,data_usage_scope='PUBLIC_REDISTRIBUTABLE')
        if receipt['pre_event_observation']['observation_date']>=event_date or receipt['post_event_observation']['observation_date']<=event_date:raise ValueError('EVENT_WINDOW_NOT_STRICTLY_PRE_POST')
        official_evidence=official['official_evidence']
        if not official_evidence or not all(row.get('evidence_status')=='OFFICIAL_CONFIRMED' for row in official_evidence):raise ValueError('OFFICIAL_PROPOSITION_NOT_VALIDATED')
        case=dict(status='AVAILABLE',research_case_id=case_id,event=event,article=article,official_evidence=official_evidence,impact_intelligence=interpretation,receipt=receipt)
        case['research_summary']={'fact':p['fact_proposition'],'fact_summary_zh_tw':FACT_SUMMARIES_ZH_TW.get(event_date,''),'mechanism_status':'CONDITIONAL_PLAUSIBLE_CHANNEL','causality_status':'NOT_ESTABLISHED'}
        return case
    except (OSError,ValueError,TypeError,KeyError,IndexError,ArithmeticError):
        return dict(status='NOT_MEASURED',reason='PUBLIC_DAILY_CASE_UNAVAILABLE_OR_INVALID',receipt=None)

def load_research_library():
    """Load only fixed, packaged ECB cases; unavailable cases never gain fake rows."""
    configs=[dict(case_id='ecb-2025-06-05',event_date='2025-06-05',effective_date='2025-06-11',case_path=CASE,data_path=DATA,event_source=EVENT_SOURCE,data_source=DATA_SOURCE)]
    configs.extend(RESEARCH_CASES)
    cases=[];unavailable=[]
    for cfg in configs:
        case=load_case(cfg['case_path'],cfg['data_path'],expected_event_source=cfg['event_source'],
            expected_market_data_source=cfg['data_source'],expected_event_date=cfg['event_date'],
            expected_effective_date=cfg['effective_date'],case_id=cfg['case_id'])
        if case['status']=='AVAILABLE':cases.append(case)
        else:unavailable.append(cfg['case_id'])
    pairs=[]
    for i,left in enumerate(cases):
        for right in cases[i+1:]:
            a,b=left['receipt'],right['receipt']
            if (a['instrument_id'],a['market_data_provider'],a['data_frequency'])==(b['instrument_id'],b['market_data_provider'],b['data_frequency']):
                pairs.append([left['research_case_id'],right['research_case_id']])
    status='AVAILABLE' if cases and not unavailable else 'PARTIAL' if cases else 'NOT_MEASURED'
    return dict(status=status,cases=cases,total_case_count=len(configs),observed_price_case_count=sum(c['receipt']['pre_event_observation'] is not None and c['receipt']['post_event_observation'] is not None for c in cases),not_measured_case_count=len(unavailable),official_case_count=sum(bool(c['official_evidence']) for c in cases),pit_replay_case_count=sum(c['receipt']['point_in_time_available'] is True for c in cases),comparable_pairs=pairs,comparable_pair_count=len(pairs),unavailable_case_ids=unavailable)
