"""Opt-in title/link discovery. No full articles, media or external redirects.

Global Voices requires author attribution (retained in the five-column source
name). UN News requires an operator acknowledgement of credit and UN notification.
Guardian RSS is only enabled with an explicit non-commercial-use opt-in;
this does not grant a commercial redistribution licence.
"""
from __future__ import annotations
import os, re, ssl
from functools import partial
from html import unescape
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler
import xml.etree.ElementTree as ET
from .eia_live_ingestion import (BUNDLE, MAX_BYTES, TIMEOUT, FIELDS, IngestionError,
    NoRedirect, now_iso, reference, publication, text, failure_reason, integer_setting)
from .live_source_ingestion import LiveSourceIngestion

PROFILES = {
 'Global Voices': ('https://globalvoices.org/feed/', 'globalvoices.org'),
 'UN News': ('https://news.un.org/feed/subscribe/en/news/all/rss.xml', 'news.un.org'),
 'Guardian World': ('https://www.theguardian.com/world/rss', 'www.theguardian.com'),
}
LICENSE = 'https://creativecommons.org/licenses/by/3.0/'
# Conservative discovery selection, not factual verification or importance scoring.
# Exact phrases/word boundaries avoid counting ordinary health, culture, crime or
# a company name alone as macro intelligence. Context rules also admit specific
# military escalation/monetary-policy headlines. False negatives remain possible.
MACRO_TITLE = re.compile(r'\b(?:tariffs?|sanctions?|reciprocal trade|export controls?|'
    r'central banks?|interest rates?|inflation|unemployment|employment|'
    r'gross domestic product|GDP|recession|fiscal policy|monetary policy|'
    r'government spending|national budget|sovereign debt|banking crisis|'
    r'financial crisis|oil|crude|gas prices?|fuel shipments?|diesel|energy|'
    r'food security|supply chain|semiconductors?|military affiliate|'
    r'ceasefire|wars?|invasion|ballistic missiles?|nuclear weapons?|'
    r'presidential election|parliamentary election|hurricane|earthquake|'
    r'FOMC|Federal Reserve|rate cuts?|rate hikes?|rate decisions?|'
    r'nonfarm payrolls?|jobs report|trade deal|embargo|sovereign default|'
    r'bank failures?|bank runs?|liquidity crisis|capital controls?|Nord Stream|'
    r'global trade|trade volumes?|flooding disaster|humanitarian crisis|famine|'
    r'funding cuts.*refugees|'
    r'airstrikes?|air strikes?|military strikes?|missiles?|naval blockade|coup)\b', re.I)
GEOPOLITICAL_CONTEXT = re.compile(r'\b(?:Russia|Russian|Ukraine|Ukrainian|Iran|Iranian|Israel|Israeli|Houthi|Saudi|Ethiopia|Eritrea|Taiwan|NATO|Sudan|Syria|Syrian|Gaza|Myanmar|Security Council|troops|army|military)\b', re.I)
ESCALATION = re.compile(r'\b(?:attacks?|strikes?|cross(?:es|ed)? (?:the )?border|invades?|invasions?|mobiliz(?:e|es|ation)|bombardment|escalation|incursions?)\b', re.I)
POLICY_CONTEXT = re.compile(r'\b(?:government|governments|central bank|White House|finance minister)\b', re.I)
POLICY_DEVELOPMENT = re.compile(r'\b(?:internet.*protest|internet shutdown|budget|tax(?:es)?|spending|debt|deficit|trade|tariff|sanction|rates?)\b', re.I)
FED_CONTEXT = re.compile(r'\b(?:Fed|Powell)\b', re.I)
MONETARY_CONTEXT = re.compile(r'\b(?:rates?|inflation|monetary|jobs|employment|economy|recession|bonds?)\b', re.I)
RATE_MARKET = re.compile(r'\b(?:rigging rates|rate rigging|yield curve|bond yields?|housing crisis)\b', re.I)

def macro_relevant_title(title):
    return isinstance(title, str) and bool(MACRO_TITLE.search(title) or RATE_MARKET.search(title)
        or (FED_CONTEXT.search(title) and MONETARY_CONTEXT.search(title))
        or (GEOPOLITICAL_CONTEXT.search(title) and ESCALATION.search(title))
        or (POLICY_CONTEXT.search(title) and POLICY_DEVELOPMENT.search(title)))

def allowed_url(value, host):
    try:
        u = urlsplit(value)
        return u.scheme == 'https' and u.hostname == host and u.port in (None, 443) and not u.username and not u.password
    except (TypeError, ValueError):
        return False

class ParsedNews(list):
    """Five-column rows plus bounded cycle metrics; no raw provider bodies."""
    def __init__(self, rows, diagnostics):
        super().__init__(rows)
        self.diagnostics = diagnostics


def parse_rss(data, observed, *, source):
    if source not in PROFILES: raise IngestionError('UNKNOWN_NEWS_PROFILE')
    if not data or len(data) > MAX_BYTES: raise IngestionError('EMPTY_OR_OVERSIZED_RESPONSE')
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper(): raise IngestionError('UNSAFE_XML_DECLARATION')
    try: root = ET.fromstring(data)
    except ET.ParseError: raise IngestionError('MALFORMED_RSS') from None
    if root.tag != 'rss' or root.find('channel') is None: raise IngestionError('UNEXPECTED_RSS_ROOT')
    items = root.findall('./channel/item')
    if len(items) > 5000: raise IngestionError('RSS_ITEM_LIMIT')
    rows, usable = {}, 0
    rejected = {}
    def reject(reason): rejected[reason] = rejected.get(reason, 0) + 1
    for item in items:
        title, url = text(item, 'title'), text(item, 'link')
        author = unescape(text(item, '{http://purl.org/dc/elements/1.1/}creator') or text(item, 'author'))
        if not title: reject('MISSING_TITLE'); continue
        if not allowed_url(url, PROFILES[source][1]): reject('UNSAFE_SOURCE_URL'); continue
        if source == 'Global Voices' and not author: reject('MISSING_ATTRIBUTION'); continue
        usable += 1
        if not macro_relevant_title(unescape(title)): reject('NOT_MACRO_RELEVANT'); continue
        if source == 'UN News':
            # Prefer the explicitly provided original URL only when it names
            # the same story as the feed link; never infer an article identity.
            guid = text(item, 'guid')
            if allowed_url(guid, PROFILES[source][1]) and urlsplit(guid).path == urlsplit(url).path.replace('/feed/view/', '/'):
                url = guid
        name = source + (' · ' + author if author else '')
        row = dict(zip(FIELDS, (observed, publication(text(item, 'pubDate')), title, name, url)))
        key = reference(url)
        if key in rows: reject('DUPLICATE_URL'); continue
        rows[key] = row
    if not usable: raise IngestionError('NO_USABLE_ARTICLES')
    # A valid feed with no selected macro titles is a successful zero-new cycle.
    from .radar_news_freshness import timestamp
    checked = timestamp(observed)
    dates = [timestamp(row['event_time']) for row in rows.values()]
    ages = [(checked - date).total_seconds() for date in dates if date and checked]
    diagnostics = dict(input_item_count=len(items), accepted_item_count=len(rows),
        rejected_by_reason=rejected, publication_unknown_count=sum(date is None for date in dates),
        last_24h_selected_count=sum(0 <= age <= 86400 for age in ages) if checked else None,
        last_48h_selected_count=sum(0 <= age <= 172800 for age in ages) if checked else None,
        observed_at=observed)
    return ParsedNews([rows[key] for key in sorted(rows)], diagnostics)

def fetch_rss(source):
    endpoint, host = PROFILES[source]
    request = Request(endpoint, headers={'User-Agent':'GlobalEventRadar/1.0', 'Accept':'application/rss+xml, application/xml, text/xml'})
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    with opener.open(request, timeout=TIMEOUT) as response:
        if response.status != 200: raise IngestionError('HTTP_NON_200')
        if response.geturl() != endpoint or not allowed_url(response.geturl(), host): raise IngestionError('UNEXPECTED_RESPONSE_HOST')
        if response.headers.get_content_type() not in {'application/rss+xml','application/xml','text/xml'}: raise IngestionError('INVALID_CONTENT_TYPE')
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES: raise IngestionError('RESPONSE_TOO_LARGE')
    return data

class BroadNewsIngestion(LiveSourceIngestion):
    def __init__(self, source, *, runtime_root=None, interval=1800, max_articles=100, fetcher=None, bundle=BUNDLE):
        if source not in PROFILES: raise IngestionError('UNKNOWN_NEWS_PROFILE')
        super().__init__(source=source, bundle=bundle, runtime_root=runtime_root, interval=interval,
            max_articles=max_articles, parser=partial(parse_rss, source=source), fetcher=fetcher or partial(fetch_rss, source),
            pinned={}, prefix=source.lower().replace(' ', '-'), fallback=None, error_type=IngestionError,
            now_iso=now_iso, reference=reference, failure_reason=failure_reason)

    @classmethod
    def from_environment(cls, source):
        if source == 'UN News' and os.environ.get('RADAR_UN_NEWS_REUSE_ACKNOWLEDGED', '').strip() != '1':
            raise IngestionError('UN_NEWS_CREDIT_AND_NOTIFICATION_ACKNOWLEDGEMENT_REQUIRED')
        if source == 'Guardian World' and os.environ.get('RADAR_GUARDIAN_NONCOMMERCIAL', '').strip() != '1':
            raise IngestionError('GUARDIAN_NONCOMMERCIAL_USE_ACKNOWLEDGEMENT_REQUIRED')
        return cls(source, runtime_root=os.environ.get('RADAR_RUNTIME_ROOT') or None,
            interval=integer_setting(os.environ, 'RADAR_NEWS_REFRESH_SECONDS', 1800, 300, 86400),
            max_articles=integer_setting(os.environ, 'RADAR_NEWS_MAX_ARTICLES', 100, 1, 1000))
