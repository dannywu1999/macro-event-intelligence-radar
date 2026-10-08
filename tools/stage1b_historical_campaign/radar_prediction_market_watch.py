"""Read-only macro discovery and presentation. No thread, disk write or trading API.

One opted-in process shares an in-memory TTL cache. A batch has at most four
searches and eight event detail reads, stops at the first error, and never retries.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import re
import ssl
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPSHandler

from . import radar_market_expectations as expectations

CONTRACT = 'PREDICTION_MARKET_WATCH_V1'
QUERIES = ('Fed', 'tariffs', 'oil', 'Iran')
MAX_REQUESTS, MAX_EVENTS, MAX_MARKETS = 12, 8, 20
TTL = 1800
CATEGORIES = ('MONETARY_POLICY', 'ECONOMY_TRADE', 'ENERGY', 'GEOPOLITICS')


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def category(record):
    """Conservative discovery label, never event identity or factual authority."""
    metadata = record.get('proposition_metadata') or {}
    question = record.get('question') or ''
    context = ' '.join(e.get('title') or '' for e in metadata.get('provider_events', []))
    text = (question + ' ' + context).casefold()
    if re.search(r'\b(nba|nfl|mlb|nhl|soccer|tennis|super bowl|world cup|oscar|grammy|gta|movie|album)\b', text):
        return None
    if re.search(r'\b(bitcoin|ethereum|btc|eth|solana|crypto)\b', text):
        return None
    if re.search(r'\b(federal reserve|fomc|fed|ecb|boe|boj|bank of japan|bank of england|european central bank|interest rates?|rate cuts?|rate hikes?)\b', text):
        return 'MONETARY_POLICY'
    if re.search(r'\b(inflation|cpi|gdp|unemployment|nonfarm|payrolls?|recession|tariffs?|sanctions?|export controls?|trade (deal|policy|war|agreement)|fiscal|government shutdown|debt ceiling)\b', text):
        return 'ECONOMY_TRADE'
    if re.search(r'\b(oil|crude|opec|energy supply|natural gas|refiner(y|ies)|petroleum)\b', text):
        return 'ENERGY'
    if re.search(r'\b(ceasefire|invasion|military|nuclear (deal|agreement|negotiations)|strait of hormuz|blockade)\b', text) or re.search(r'\b(war|strike|attack)\b.*\b(iran|israel|taiwan|china|russia|ukraine|us|united states)\b|\b(iran|israel|taiwan|china|russia|ukraine|us|united states)\b.*\b(war|strike|attack)\b', text):
        return 'GEOPOLITICS'
    return None


def relevance_reason(record):
    """Name the actual text cue used for this conservative discovery label."""
    kind = category(record)
    if kind is None:
        return None
    patterns = {
        'MONETARY_POLICY': r'\b(federal reserve|fomc|fed|ecb|boe|boj|bank of japan|bank of england|european central bank|interest rates?|rate cuts?|rate hikes?)\b',
        'ECONOMY_TRADE': r'\b(inflation|cpi|gdp|unemployment|nonfarm|payrolls?|recession|tariffs?|sanctions?|export controls?|trade (deal|policy|war|agreement)|fiscal|government shutdown|debt ceiling)\b',
        'ENERGY': r'\b(oil|crude|opec|energy supply|natural gas|refiner(y|ies)|petroleum)\b',
        'GEOPOLITICS': r'\b(ceasefire|invasion|military|nuclear (deal|agreement|negotiations)|strait of hormuz|blockade|war|strike|attack)\b',
    }
    metadata = record.get('proposition_metadata') or {}
    sources = [('QUESTION', record.get('question') or '')]
    sources += [('PROVIDER_EVENT_TITLE', event.get('title') or '') for event in metadata.get('provider_events', [])]
    for source, value in sources:
        match = re.search(patterns[kind], value.casefold())
        if match:
            return source + ':' + match.group(0)
    return 'CONSERVATIVE_MACRO_TOPIC_MATCH'


def _market_phase(record):
    metadata = record.get('proposition_metadata') or {}
    if metadata.get('closed') is True or metadata.get('archived') is True:
        return 2
    if metadata.get('active') is True and metadata.get('closed') is False:
        return 0
    return 1


def _select_markets(records):
    """Favor active questions while keeping all four queries able to contribute."""
    pools = {(phase, kind): [] for phase in range(3) for kind in CATEGORIES}
    for record in records:
        kind = category(record)
        if kind is not None:
            pools[(_market_phase(record), kind)].append(record)
    for pool in pools.values():
        pool.sort(key=lambda row: str(row['market_id']))
    selected = []
    for phase in range(3):
        while len(selected) < MAX_MARKETS and any(pools[(phase, kind)] for kind in CATEGORIES):
            for kind in CATEGORIES:
                pool = pools[(phase, kind)]
                if pool and len(selected) < MAX_MARKETS:
                    selected.append(pool.pop(0))
    return selected


def normalized_rows(raw, observed_at):
    if not isinstance(raw, list) or len(raw) > 500:
        raise expectations.ExpectationError('WATCH_ROW_BOUND_EXCEEDED')
    records = {}
    conflicts = set()
    for row in raw:
        for record in expectations.parse_markets(row, observed_at):
            if category(record) is None:
                continue
            mid = record['market_id']
            if mid in records and records[mid] != record:
                conflicts.add(mid)
            else:
                records[mid] = record
    return _select_markets(records[mid] for mid in sorted(records) if mid not in conflicts)


def build_watch(records, *, provider=None, now=None, ttl=TTL):
    current = expectations.timestamp(now or utc_now())
    current_dt = datetime.fromisoformat(current.replace('Z', '+00:00'))
    state = deepcopy(provider or {'enabled': False, 'status': 'SAVED_SNAPSHOT'})
    source = state.get('status')
    if source not in {'LIVE_FETCHED', 'CACHED', 'SAVED_SNAPSHOT', 'STALE', 'UNAVAILABLE'}:
        source = 'SAVED_SNAPSHOT' if records else 'UNAVAILABLE'
    markets = []
    seen = set()
    candidates = []
    for record in records[:100]:
        if record.get('market_id') in seen:
            continue
        seen.add(record['market_id'])
        candidates.append(record)
    for record in _select_markets(candidates):
        kind = category(record)
        row = deepcopy(record)
        metadata = row.get('proposition_metadata') or {}
        labels = row.get('outcomes')
        names = [str(label).casefold() for label in labels] if labels else []
        row['outcome_type'] = ('BINARY_YES_NO' if len(names) == 2 and set(names) == {'yes', 'no'}
                               else 'MULTI_OUTCOME' if len(names) > 2 else 'CATEGORICAL' if names else 'UNKNOWN')
        row['category'] = kind
        row['relevance_reason'] = relevance_reason(record)
        row['market_status'] = ('CLOSED' if metadata.get('closed') is True or metadata.get('archived') is True
                                 else 'ACTIVE' if metadata.get('active') is True and metadata.get('closed') is False else 'UNKNOWN')
        observed = expectations.timestamp(row.get('observed_at'))
        age = (current_dt - datetime.fromisoformat(observed.replace('Z', '+00:00'))).total_seconds() if observed else None
        row['freshness'] = 'UNKNOWN' if age is None or age < 0 else 'STALE' if age > ttl else 'FRESH'
        row['source_status'] = 'STALE' if row['freshness'] == 'STALE' or source == 'STALE' else source
        if row['freshness'] != 'FRESH' and row['source_status'] == 'LIVE_FETCHED':
            row['source_status'] = 'CACHED'
        row['provider_updated_at'] = metadata.get('provider_updated_at')
        row['outcome_identifiers'] = metadata.get('outcome_identifiers')
        row['outcome_identifier_kind'] = metadata.get('outcome_identifier_kind')
        row['provider_event_ids'] = [e['id'] for e in metadata.get('provider_events', []) if e.get('id')]
        row['liquidity'] = metadata.get('liquidity')
        row['volume'] = metadata.get('volume')
        link = row.get('event_expectation_link') or {}
        if not (row.get('link_status') == 'LINKED' and link.get('contract_version') == 'EVENT_EXPECTATION_LINK_V0'
                and link.get('expectation_market_id') == row.get('market_id')
                and link.get('link_status') == 'LINKED' and link.get('canonical_event_id') == row.get('canonical_event_id')):
            row.update(link_status='NO_MATCH', canonical_event_id=None, link_method=None)
            row.pop('event_expectation_link', None)
        markets.append(row)
    markets = markets[:MAX_MARKETS]
    return dict(contract_version=CONTRACT, read_only=True, authority_role='EXPECTATION_SENSOR',
                status='AVAILABLE' if markets else 'UNAVAILABLE' if source == 'UNAVAILABLE' else 'EMPTY',
                source_status=source, provider=state, markets=markets[:MAX_MARKETS],
                market_count=len(markets[:MAX_MARKETS]), categories=[c for c in CATEGORIES if any(m['category'] == c for m in markets)],
                category_counts=dict(Counter(m['category'] for m in markets)),
                reason=state.get('reason') if not markets else None)


def fetch_json(path, params=None):
    """Only documented Gamma public search/event GETs, normal verified TLS."""
    if path != '/public-search' and not re.fullmatch(r'/events/[0-9]{1,30}', path):
        raise expectations.ExpectationError('UNSUPPORTED_DISCOVERY_PATH')
    if params and (path != '/public-search' or set(params) - {'q', 'limit_per_type', 'search_tags', 'search_profiles', 'events_status'}):
        raise expectations.ExpectationError('UNSUPPORTED_DISCOVERY_QUERY')
    url = 'https://gamma-api.polymarket.com' + path + ('?' + urlencode(params) if params else '')
    request = Request(url, headers={'User-Agent': 'EventCentricDynamicDiscovery/1.0', 'Accept': 'application/json'})
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), expectations.NoRedirect())
    with opener.open(request, timeout=8) as response:
        if response.status != 200 or response.geturl() != url or response.headers.get_content_type() != 'application/json':
            raise expectations.ExpectationError('INVALID_RESPONSE')
        data = response.read(expectations.MAX_BYTES + 1)
    if len(data) > expectations.MAX_BYTES:
        raise expectations.ExpectationError('RESPONSE_TOO_LARGE')
    try:
        return json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise expectations.ExpectationError('INVALID_JSON') from exc


class PredictionMarketWatch:
    def __init__(self, *, enabled=False, fetcher=fetch_json, ttl=TTL, clock=utc_now, monotonic=time.monotonic):
        if type(ttl) is not int or not 300 <= ttl <= 86400:
            raise expectations.ExpectationError('INVALID_WATCH_TTL')
        self.enabled, self.fetcher, self.ttl, self.clock, self.monotonic = enabled, fetcher, ttl, clock, monotonic
        self.lock, self.refresh_lock = threading.RLock(), threading.Lock()
        self.records, self.raw_rows, self.next_attempt, self.total_requests = [], [], 0, 0
        self.state = dict(enabled=enabled, status='UNAVAILABLE', reason='NOT_ENABLED' if not enabled else 'NOT_FETCHED',
                          last_attempt_at=None, last_success_at=None, requests_last_batch=0, cache_ttl_seconds=ttl)

    def refresh(self):
        if not self.enabled or not self.refresh_lock.acquire(blocking=False):
            return False
        attempted, raw, groups = 0, [], set()
        try:
            start = self.monotonic()
            with self.lock:
                if start < self.next_attempt:
                    return False
                self.next_attempt = start + self.ttl
                self.state['last_attempt_at'] = self.clock()
            def request(path, params=None):
                nonlocal attempted
                if attempted >= MAX_REQUESTS or self.monotonic() - start >= 30:
                    raise expectations.ExpectationError('DISCOVERY_BUDGET_EXCEEDED')
                attempted += 1
                return self.fetcher(path, params)
            search_batches = []
            for query in QUERIES:
                payload = request('/public-search', {'q': query, 'limit_per_type': 3, 'search_tags': 'false',
                                                      'search_profiles': 'false', 'events_status': 'active'})
                events = payload.get('events') if isinstance(payload, dict) else None
                if events is None:
                    events = [] if isinstance(payload, dict) and 'events' in payload else None
                if not isinstance(events, list) or len(events) > 100:
                    raise expectations.ExpectationError('INVALID_SEARCH_RESPONSE')
                search_batches.append(events[:3])
            for depth in range(3):
                for batch in search_batches:
                    if len(groups) >= MAX_EVENTS or depth >= len(batch):
                        continue
                    event = batch[depth]
                    if not isinstance(event, dict):
                        raise expectations.ExpectationError('INVALID_EVENT_ROW')
                    identity = str(event.get('id', ''))
                    if not re.fullmatch(r'[0-9]{1,30}', identity) or identity in groups or len(groups) >= MAX_EVENTS:
                        continue
                    groups.add(identity)
                    if not isinstance(event.get('markets'), list):
                        event = request('/events/' + identity)
                        if not isinstance(event, dict) or str(event.get('id')) != identity:
                            raise expectations.ExpectationError('EVENT_ID_MISMATCH')
                    rows = event.get('markets')
                    if not isinstance(rows, list) or len(rows) > 60:
                        raise expectations.ExpectationError('INVALID_EVENT_MARKETS')
                    for row in rows:
                        if not isinstance(row, dict):
                            raise expectations.ExpectationError('INVALID_MARKET_ROW')
                        raw.append({**row, 'events': [{k: event.get(k) for k in ('id', 'slug', 'title', 'category')}]})
            observed = self.clock()  # Learned after the provider responses, never backdated.
            records = normalized_rows(raw, observed)
            with self.lock:
                self.records, self.raw_rows = records, raw
                self.state.update(status='LIVE_FETCHED', reason=None, last_success_at=observed, failure_type=None, http_status=None)
            return True
        except Exception as exc:
            delay, reason = self.ttl, 'PROVIDER_REQUEST_FAILED'
            if isinstance(exc, HTTPError) and exc.code == 429:
                reason, delay = 'RATE_LIMITED', 21600
                header = exc.headers.get('Retry-After') if exc.headers else None
                if header and header.isdigit():
                    delay = max(self.ttl, min(int(header), 86400))
            with self.lock:
                self.next_attempt = max(self.next_attempt, self.monotonic() + delay)
                self.state.update(status='STALE' if self.records else 'UNAVAILABLE', reason=reason,
                                  failure_type=type(exc).__name__, http_status=exc.code if isinstance(exc, HTTPError) else None)
            return False
        finally:
            with self.lock:
                self.total_requests += attempted
                self.state['requests_last_batch'] = attempted
            self.refresh_lock.release()

    def snapshot(self):
        due = self.enabled and self.monotonic() >= self.next_attempt
        fetched = self.refresh() if due else False
        with self.lock:
            state = deepcopy(self.state)
            if state['status'] == 'LIVE_FETCHED' and not fetched:
                state['status'] = 'CACHED'
            return deepcopy(self.records), state
