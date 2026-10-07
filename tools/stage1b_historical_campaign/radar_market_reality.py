"""Read-only market observations, never predictions or inferred event causality.

No provider, broker, calendar or legacy dataset imports. A supplied observation
needs both market time and actual system knowledge time; a daily date alone is
insufficient. Replay calls the pure projector with visible ledger rows only.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

CONTRACT = 'MARKET_REALITY_SNAPSHOT_V0'
INPUT = 'MARKET_REALITY_INPUT_V0'
UNIVERSE = {'SPY': ('BROAD_US_EQUITIES', 'PRICE'), 'QQQ': ('US_GROWTH_EQUITIES', 'PRICE'),
            'VIX': ('VOLATILITY_INDEX', 'INDEX_LEVEL'), 'DXY': ('DOLLAR_INDEX', 'INDEX_LEVEL'),
            'US10Y': ('US_TREASURY_10Y_YIELD', 'YIELD_PERCENT')}
WINDOWS = {'T0': 0, 'T+5m': 300, 'T+30m': 1800, 'T+1h': 3600, 'T+1_TRADING_DAY': None}
MAX_AGE_SECONDS = 900
class MarketRealityError(ValueError): pass

def utc(value):
    if not isinstance(value, str): raise MarketRealityError('INVALID_MARKET_TIME')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None: raise ValueError('timezone required')
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise MarketRealityError('INVALID_MARKET_TIME') from error

def iso(value): return value.isoformat().replace('+00:00', 'Z')
def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise MarketRealityError('INVALID_MARKET_VALUE')
    return float(value)

def normalize_record(row):
    if not isinstance(row, dict) or not isinstance(row.get('symbol'),str) or row['symbol'] not in UNIVERSE:
        raise MarketRealityError('INVALID_MARKET_SYMBOL')
    symbol = row['symbol']; event = row.get('event_id')
    if not isinstance(event, str) or not event.startswith('canonical-event-v0-') or len(event) != 83 or any(c not in '0123456789abcdef' for c in event[19:]):
        raise MarketRealityError('INVALID_MARKET_EVENT')
    if row.get('time_basis') != 'SYSTEM_RECORDED_TIME':
        raise MarketRealityError('NO_POINT_IN_TIME_SOURCE')
    anchor, market, known = (utc(row.get(k)) for k in ('event_observed_at', 'market_timestamp', 'observed_at'))
    if market > known: raise MarketRealityError('MARKET_TIME_AFTER_KNOWLEDGE')
    source = row.get('source'); reference = row.get('source_observation_id')
    if (not isinstance(source, dict) or not isinstance(source.get('name'), str) or not source['name'].strip()
            or len(source['name']) > 200 or not isinstance(reference, str) or not reference or len(reference) > 300):
        raise MarketRealityError('MARKET_PROVENANCE_REQUIRED')
    url = source.get('url')
    if url is not None:
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password: raise ValueError()
        except (TypeError, ValueError): raise MarketRealityError('INVALID_MARKET_SOURCE_URL')
    value = number(row.get('price_or_level'))
    if symbol != 'US10Y' and value <= 0: raise MarketRealityError('INVALID_MARKET_VALUE')
    if row.get('value_unit') != UNIVERSE[symbol][1]: raise MarketRealityError('MARKET_UNIT_MISMATCH')
    prior = row.get('previous_close')
    if prior is not None:
        if not isinstance(prior, dict): raise MarketRealityError('INVALID_PREVIOUS_CLOSE')
        prior_market, prior_known = utc(prior.get('market_timestamp')), utc(prior.get('observed_at'))
        prior_value = number(prior.get('price_or_level'))
        prior_reference=prior.get('source_observation_id')
        if prior_market > prior_known or prior_market > market or prior_known > known or not isinstance(prior_reference,str) or not prior_reference or len(prior_reference)>300:
            raise MarketRealityError('INVALID_PREVIOUS_CLOSE')
        if symbol != 'US10Y' and prior_value <= 0: raise MarketRealityError('INVALID_PREVIOUS_CLOSE')
        prior = dict(price_or_level=prior_value, market_timestamp=iso(prior_market), observed_at=iso(prior_known), source_observation_id=prior['source_observation_id'])
    result = dict(event_id=event, symbol=symbol, event_observed_at=iso(anchor), market_timestamp=iso(market),
                  observed_at=iso(known), time_basis='SYSTEM_RECORDED_TIME', price_or_level=value,
                  value_unit=UNIVERSE[symbol][1], source={'name': source['name'], 'url': url},
                  source_observation_id=reference, previous_close=prior)
    result['observation_id'] = 'market-reality-observation-v0-' + hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return result

def read_observations(path):
    if path is None: return [], 'NOT_CONFIGURED'
    try:
        path = Path(path)
        if path.stat().st_size > 8*1024*1024: raise MarketRealityError('MARKET_INPUT_TOO_LARGE')
        packet = json.loads(path.read_bytes())
        if not isinstance(packet, dict) or packet.get('schema') != INPUT or not isinstance(packet.get('observations'), list) or len(packet['observations']) > 4096:
            raise MarketRealityError('INVALID_MARKET_INPUT')
        # Declared test data must never become current public observations.
        # No serving flag or environment setting can bypass this boundary.
        if packet.get('synthetic', False) is not False:
            raise MarketRealityError('SYNTHETIC_MARKET_INPUT_FORBIDDEN')
        records = {}; references = {}; anchors = {}
        for row in packet['observations']:
            record = normalize_record(row)
            if record['event_id'] in anchors and anchors[record['event_id']] != record['event_observed_at']:
                raise MarketRealityError('CONFLICTING_EVENT_OBSERVATION_TIME')
            anchors[record['event_id']] = record['event_observed_at']
            key = (record['event_id'], record['symbol'], record['source']['name'], record['source_observation_id'])
            if key in references and references[key] != record: raise MarketRealityError('CONFLICTING_MARKET_OBSERVATION')
            references[key] = record; records[record['observation_id']] = record
        return list(records.values()), 'AVAILABLE' if records else 'EMPTY'
    except (OSError, ValueError, TypeError, OverflowError):
        return [], 'UNAVAILABLE'

def project_snapshot(event_id, anchor, records, *, as_of, window='AS_OF', trading_day_target=None, source_status='AVAILABLE'):
    cutoff = utc(as_of); anchor_time = utc(anchor) if anchor is not None else None
    target = cutoff; reason = None
    if anchor_time is None: reason = 'NO_EVENT_SYSTEM_OBSERVATION'
    elif anchor_time > cutoff: reason = 'EVENT_NOT_OBSERVED_AT_AS_OF'
    elif window != 'AS_OF':
        if window not in WINDOWS: raise MarketRealityError('INVALID_MARKET_WINDOW')
        if window == 'T+1_TRADING_DAY':
            if trading_day_target is None: reason = 'TRADING_DAY_AUTHORITY_UNAVAILABLE'
            else:
                target = utc(trading_day_target)
                if target <= anchor_time: raise MarketRealityError('INVALID_TRADING_DAY_TARGET')
        else: target = anchor_time + timedelta(seconds=WINDOWS[window])
        if target > cutoff: reason = 'WINDOW_NOT_YET_OBSERVED'
    eligible = [] if reason else [r for r in records if r['event_id']==event_id and utc(r['observed_at'])<=target and utc(r['market_timestamp'])<=target]
    def latest(rows): return max(rows,key=lambda r:(utc(r['market_timestamp']),utc(r['observed_at']),r['observation_id'])) if rows else None
    instruments = []; references = set()
    for symbol,(role,unit) in UNIVERSE.items():
        row = latest([r for r in eligible if r['symbol']==symbol])
        baseline = latest([r for r in eligible if r['symbol']==symbol and utc(r['observed_at'])<=anchor_time and utc(r['market_timestamp'])<=anchor_time]) if anchor_time else None
        state = reason or ('STALE' if row and (target-utc(row['market_timestamp'])).total_seconds()>MAX_AGE_SECONDS else 'AVAILABLE' if row else 'NO_POINT_IN_TIME_SOURCE')
        item = dict(symbol=symbol,asset_role=role,value_unit=unit,market_timestamp=row['market_timestamp'] if row else None,
                    observed_at=row['observed_at'] if row else None,price_or_level=None,change_from_previous_close=None,
                    change_since_event=None,change_unit='BASIS_POINTS' if symbol=='US10Y' else 'PERCENT',source=row['source'] if row else None,availability_status=state)
        if state=='AVAILABLE':
            value=row['price_or_level']; item['price_or_level']=value; references.add(row['source_observation_id'])
            def change(previous): return (value-previous)*100 if symbol=='US10Y' else (value/previous-1)*100 if previous else None
            prior=row['previous_close']
            if prior and utc(prior['observed_at'])<=target and utc(prior['market_timestamp'])<=target:
                item['change_from_previous_close']=change(prior['price_or_level']);references.add(prior['source_observation_id'])
            if baseline and (anchor_time-utc(baseline['market_timestamp'])).total_seconds()<=MAX_AGE_SECONDS:
                item['change_since_event']=change(baseline['price_or_level']);references.add(baseline['source_observation_id'])
        instruments.append(item)
    available=sum(i['availability_status']=='AVAILABLE' for i in instruments)
    # No source observation means no changing market snapshot/cutoff to freeze.
    # Keep unavailable projections stable; the enclosing Replay still reports
    # its requested as_of independently.
    return dict(contract_version=CONTRACT,event_id=event_id,observed_at=iso(anchor_time) if anchor_time else None,
                as_of=iso(cutoff) if records and anchor_time else None,window=window,window_timestamp=iso(target) if records and not reason else None,
                time_basis='SYSTEM_RECORDED_TIME',instruments=instruments,
                snapshot_status='COMPLETE' if available==len(UNIVERSE) else 'PARTIAL' if available else 'UNAVAILABLE',
                reason=reason or (None if available else 'NO_SUITABLE_POINT_IN_TIME_SOURCE'),
                source_status=source_status,source_observation_ids=sorted(references),max_age_seconds=MAX_AGE_SECONDS,
                supported_windows=list(WINDOWS),authority_role='MARKET_OBSERVATION_ONLY')

def add_projection(view, path, *, as_of):
    records,status=read_observations(path); cutoff=utc(as_of)
    records=[r for r in records if utc(r['observed_at'])<=cutoff and utc(r['event_observed_at'])<=cutoff]
    result=dict(view); result['events']=deepcopy(view.get('events',[]))
    valid_ids={e['event_id'] for e in result['events']};records=[r for r in records if r['event_id'] in valid_ids]
    for event in result['events']:
        related=[r for r in records if r['event_id']==event['event_id']]
        anchors={r['event_observed_at'] for r in related}
        if len(anchors)>1: related=[]; anchor=None; event_status='UNAVAILABLE'
        else: anchor=next(iter(anchors),None);event_status=status
        event['market_reality']=project_snapshot(event['event_id'],anchor,related,as_of=as_of,source_status=event_status)
    result.update(market_reality_contract=CONTRACT,market_reality_source_status=status,market_reality_observations=records)
    if records:
        from tools.stage1b_historical_campaign.radar_macroview_freeze import build_previews
        result['macroview_previews']=build_previews(result)
    return result
