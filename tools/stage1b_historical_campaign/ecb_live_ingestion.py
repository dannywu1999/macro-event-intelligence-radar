"""Opt-in ECB Press RSS discovery; never an Official Evidence writer.

Endpoint/name originate in the existing A1 a1_rss_sources.json profile.
"""
from __future__ import annotations
import os
import ssl
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler
import xml.etree.ElementTree as ET

from .eia_live_ingestion import (BUNDLE, MAX_BYTES, TIMEOUT, FIELDS, IngestionError,
    NoRedirect, now_iso, reference, publication, text, failure_reason, integer_setting)
from .live_source_ingestion import LiveSourceIngestion

SOURCE = 'ECB Press'
ENDPOINT = 'https://www.ecb.europa.eu/rss/press.html'


def ecb_url(value):
    try:
        url = urlsplit(value)
        return (url.scheme == 'https' and url.hostname == 'www.ecb.europa.eu'
                and url.port in (None, 443) and not url.username and not url.password)
    except (ValueError, TypeError):
        return False


def parse_rss(data, observed):
    if not data or len(data) > MAX_BYTES:
        raise IngestionError('EMPTY_OR_OVERSIZED_RESPONSE')
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise IngestionError('UNSAFE_XML_DECLARATION')
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise IngestionError('MALFORMED_RSS') from None
    if root.tag != 'rss' or root.find('channel') is None:
        raise IngestionError('UNEXPECTED_RSS_ROOT')
    items = root.findall('./channel/item')
    if len(items) > 5000:
        raise IngestionError('RSS_ITEM_LIMIT')
    rows = {}
    for item in items:
        title, summary, url = text(item, 'title'), text(item, 'description'), text(item, 'link')
        if not title or not ecb_url(url):
            continue
        headline = title + ' - ' + summary if summary and summary.lower() != title.lower() else title
        # Only a timezone-bearing source pubDate supplies reported time. Missing
        # publication remains blank, independently of collector observed_time.
        row = dict(zip(FIELDS, (observed, publication(text(item, 'pubDate')), headline, SOURCE, url)))
        rows.setdefault(reference(url), row)
    if not rows:
        raise IngestionError('NO_USABLE_ARTICLES')
    return [rows[url] for url in sorted(rows)]


def fetch_ecb():
    request = Request(ENDPOINT, headers={'User-Agent':'GlobalEventRadar/1.0',
        'Accept':'application/rss+xml, application/xml, text/xml'})
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    with opener.open(request, timeout=TIMEOUT) as response:
        if response.status != 200:
            raise IngestionError('HTTP_NON_200')
        if response.geturl() != ENDPOINT or not ecb_url(response.geturl()):
            raise IngestionError('UNEXPECTED_RESPONSE_HOST')
        if response.headers.get_content_type() not in {'application/rss+xml','application/xml','text/xml'}:
            raise IngestionError('INVALID_CONTENT_TYPE')
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise IngestionError('RESPONSE_TOO_LARGE')
    return data


class EcbIngestion(LiveSourceIngestion):
    def __init__(self, *, bundle=BUNDLE, runtime_root=None, interval=1800, max_articles=100, fetcher=None):
        super().__init__(source=SOURCE, bundle=bundle, runtime_root=runtime_root,
                         interval=interval, max_articles=max_articles, parser=parse_rss,
                         fetcher=fetcher or fetch_ecb, pinned={}, prefix='ecb', fallback=None,
                         error_type=IngestionError, now_iso=now_iso, reference=reference,
                         failure_reason=failure_reason)

    @classmethod
    def from_environment(cls):
        interval = integer_setting(os.environ, 'RADAR_ECB_REFRESH_SECONDS', 1800, 300, 86400)
        maximum = integer_setting(os.environ, 'RADAR_ECB_MAX_ARTICLES', 100, 1, 1000)
        return cls(runtime_root=os.environ.get('RADAR_RUNTIME_ROOT') or None,
                   interval=interval, max_articles=maximum)
