"""Read-only publication recency; observation and fetch clocks never substitute.

Counts reference actual Canonical Event V0 membership, not claimed real-world
clustering. Date proxies, absent dates and future dates are never recent news.
"""
from datetime import datetime, timezone
from urllib.parse import urlsplit

def timestamp(value):
    if not isinstance(value, str): return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None
    except ValueError: return None

def project(view, *, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None: raise ValueError('AWARE_NOW_REQUIRED')
    buckets, publications, attributions = {}, {}, {}
    for article in view.get('items', []):
        ref = article.get('article_reference')
        published = timestamp(article.get('reported_at')) if article.get('reported_time_kind') == 'REPORTED_TIME' else None
        age = (now - published).total_seconds() if published else None
        bucket = 'UNKNOWN' if age is None else 'INVALID_FUTURE' if age < 0 else 'LAST_24H' if age <= 86400 else 'LAST_48H' if age <= 172800 else 'OLDER'
        buckets[ref] = bucket
        publications[ref] = published.isoformat().replace('+00:00','Z') if published else None
        source = article.get('news_source') or {}
        name, url = source.get('name') or '', source.get('url') or ''
        host = urlsplit(url).hostname
        if host == 'globalvoices.org' and name.startswith('Global Voices · '):
            attributions[ref] = dict(source='Global Voices', author=name.split(' · ',1)[1], license_url='https://creativecommons.org/licenses/by/3.0/')
        elif host == 'www.theguardian.com' and name.startswith('Guardian World'):
            attributions[ref] = dict(source='Guardian World', author=name.split(' · ',1)[1] if ' · ' in name else None, license_url=None)
    source_checks = {}
    for name, state in view.get('discovery_sources', {}).items():
        checked = timestamp(state.get('last_success_at'))
        age = (now - checked).total_seconds() if checked else None
        ttl = state.get('refresh_interval_seconds')
        cache = 'UNKNOWN' if age is None or age < 0 or type(ttl) not in (int, float) or ttl <= 0 else 'STALE_CACHE' if age >= ttl else 'FRESH_CACHE'
        source_checks[name] = dict(last_successful_fetch_at=state.get('last_success_at'), acquisition_status=state.get('status'), cache_freshness=cache)
    refs24 = {ref for ref,b in buckets.items() if b == 'LAST_24H'}
    refs48 = {ref for ref,b in buckets.items() if b in {'LAST_24H','LAST_48H'}}
    events = view.get('events', [])
    count = lambda refs: sum(bool(refs.intersection(e.get('article_references', []))) for e in events)
    return dict(as_of=now.isoformat().replace('+00:00','Z'), basis='SOURCE_REPORTED_PUBLICATION_TIME_ONLY',
        article_recency=buckets, published_at=publications, attribution=attributions, source_checks=source_checks,
        last_24h_article_count=len(refs24), last_48h_article_count=len(refs48),
        last_24h_event_count=count(refs24), last_48h_event_count=count(refs48),
        event_count_basis='CANONICAL_EVENT_V0_MEMBERSHIP_NOT_REAL_WORLD_CLUSTERING',
        older_article_count=sum(b=='OLDER' for b in buckets.values()),
        unknown_article_count=sum(b in {'UNKNOWN','INVALID_FUTURE'} for b in buckets.values()))
