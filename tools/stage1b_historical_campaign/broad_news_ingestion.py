"""Opt-in title/link discovery. No full articles, media or external redirects.

Global Voices requires author attribution (retained in the five-column source
name). Guardian RSS is only enabled with an explicit non-commercial-use opt-in;
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
 'Guardian World': ('https://www.theguardian.com/world/rss', 'www.theguardian.com'),
}
LICENSE = 'https://creativecommons.org/licenses/by/3.0/'
# Conservative discovery selection, not factual verification or importance scoring.
# Exact phrases/word boundaries avoid counting ordinary health, culture, crime or
# a company name alone as macro intelligence. False negatives remain possible.
MACRO_TITLE = re.compile(r'\b(?:tariffs?|sanctions?|reciprocal trade|export controls?|'
    r'central banks?|interest rates?|inflation|unemployment|employment|'
    r'gross domestic product|GDP|recession|fiscal policy|monetary policy|'
    r'government spending|national budget|sovereign debt|banking crisis|'
    r'financial crisis|oil|crude|gas prices?|fuel shipments?|diesel|energy|'
    r'food security|supply chain|semiconductors?|military affiliate|'
    r'ceasefire|wars?|invasion|ballistic missiles?|nuclear weapons?|'
    r'presidential election|parliamentary election|hurricane|earthquake)\b', re.I)

def macro_relevant_title(title):
    return isinstance(title, str) and bool(MACRO_TITLE.search(title))

def allowed_url(value, host):
    try:
        u = urlsplit(value)
        return u.scheme == 'https' and u.hostname == host and u.port in (None, 443) and not u.username and not u.password
    except (TypeError, ValueError):
        return False

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
    for item in items:
        title, url = text(item, 'title'), text(item, 'link')
        author = unescape(text(item, '{http://purl.org/dc/elements/1.1/}creator') or text(item, 'author'))
        if not title or not allowed_url(url, PROFILES[source][1]): continue
        if source == 'Global Voices' and not author: continue  # attribution is mandatory
        usable += 1
        if not macro_relevant_title(unescape(title)): continue
        name = source + (' · ' + author if author else '')
        row = dict(zip(FIELDS, (observed, publication(text(item, 'pubDate')), title, name, url)))
        rows.setdefault(reference(url), row)
    if not usable: raise IngestionError('NO_USABLE_ARTICLES')
    # A valid feed with no selected macro titles is a successful zero-new cycle.
    return [rows[key] for key in sorted(rows)]

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
        if source == 'Guardian World' and os.environ.get('RADAR_GUARDIAN_NONCOMMERCIAL', '').strip() != '1':
            raise IngestionError('GUARDIAN_NONCOMMERCIAL_USE_ACKNOWLEDGEMENT_REQUIRED')
        return cls(source, runtime_root=os.environ.get('RADAR_RUNTIME_ROOT') or None,
            interval=integer_setting(os.environ, 'RADAR_NEWS_REFRESH_SECONDS', 1800, 300, 86400),
            max_articles=integer_setting(os.environ, 'RADAR_NEWS_MAX_ARTICLES', 100, 1, 1000))
