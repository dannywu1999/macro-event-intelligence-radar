"""Opt-in, process-owned EIA RSS acquisition. Stdlib; no legacy runtime imports.

Immutable bundled rows win by exact source URL. Preserve every bundled row;
retain newest additional articles up to the configured limit. Runtime is ephemeral.
"""
from __future__ import annotations
import csv
from dataclasses import replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import io
import os
from pathlib import Path
import re
import ssl
import tempfile
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler
import xml.etree.ElementTree as ET

FIELDS = ('observed_time', 'event_time', 'headline_or_text', 'source_name', 'source_url')
SOURCE = 'EIA Today in Energy'
ENDPOINT = 'https://www.eia.gov/rss/todayinenergy.xml'
MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 10
ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / 'demo/radar_public'

class IngestionError(ValueError):
    pass

def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

def eia_url(value):
    try:
        url = urlsplit(value)
        return url.scheme == 'https' and url.hostname in {'www.eia.gov', 'eia.gov'} and url.port in (None, 443) and not url.username and not url.password
    except (ValueError, TypeError):
        return False

def reference(value):
    url = urlsplit(value)
    return urlunsplit((url.scheme.lower(), url.netloc.lower(), url.path, url.query, ''))

def publication(value):
    if not value:
        return ''
    try:
        dt = parsedate_to_datetime(value)
    except (ValueError, TypeError, IndexError):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return ''
    if dt.tzinfo is None:
        return ''
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

def text(element, name):
    return ' '.join((element.findtext(name) or '').split())

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
        if not title or not eia_url(url):
            continue
        # Same title/summary whitespace/composition as V47; no observed-time fallback.
        headline = title + ' - ' + summary if summary and summary.lower() != title.lower() else title
        row = dict(zip(FIELDS, (observed, publication(text(item, 'pubDate')), headline, SOURCE, url)))
        rows.setdefault(reference(url), row)
    if not rows:
        raise IngestionError('NO_USABLE_ARTICLES')
    return [rows[url] for url in sorted(rows)]

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # One request per cycle, including failures; never follow another endpoint.
        raise IngestionError('REDIRECT_REJECTED')

def fetch_eia():
    request = Request(ENDPOINT, headers={'User-Agent': 'GlobalEventRadar/1.0', 'Accept': 'application/rss+xml, application/xml, text/xml'})
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context()), NoRedirect())
    with opener.open(request, timeout=TIMEOUT) as response:
        if response.status != 200:
            raise IngestionError('HTTP_NON_200')
        if response.geturl() != ENDPOINT or not eia_url(response.geturl()):
            raise IngestionError('UNEXPECTED_RESPONSE_HOST')
        if response.headers.get_content_type() not in {'application/rss+xml', 'application/xml', 'text/xml'}:
            raise IngestionError('INVALID_CONTENT_TYPE')
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise IngestionError('RESPONSE_TOO_LARGE')
    return data

def failure_reason(error):
    if isinstance(error, IngestionError):
        return str(error)[:80]
    if isinstance(error, HTTPError):
        return 'HTTP_' + str(error.code)
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, ssl.SSLError):
        return 'TLS_VERIFICATION_FAILED'
    if isinstance(reason, TimeoutError):
        return 'REQUEST_TIMEOUT'
    return 'SOURCE_REQUEST_OR_RUNTIME_UNAVAILABLE'

def integer_setting(env, name, default, minimum, maximum):
    try:
        value = int(env.get(name, str(default)))
    except ValueError:
        raise IngestionError('INVALID_' + name) from None
    if not minimum <= value <= maximum:
        raise IngestionError('INVALID_' + name)
    return value

from .live_source_ingestion import LiveSourceIngestion

class EiaIngestion(LiveSourceIngestion):
    @staticmethod
    def snapshot_rows(bundle):
        snapshot = Path(bundle) / 'news/rss_headlines_eia_snapshot.csv'
        with snapshot.open(encoding='utf-8', newline='') as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != FIELDS:
                raise IngestionError('SNAPSHOT_SCHEMA_INVALID')
            baseline = list(reader)
        if not baseline or any(not row['headline_or_text'] or not eia_url(row['source_url'])
                               or row['source_name'] != SOURCE for row in baseline):
            raise IngestionError('SNAPSHOT_INVALID')
        if len({reference(row['source_url']) for row in baseline}) != len(baseline):
            raise IngestionError('SNAPSHOT_INVALID')
        return baseline

    def __init__(self, *, bundle=BUNDLE, runtime_root=None, interval=1800, max_articles=100, fetcher=None):
        self.snapshot = Path(bundle).resolve() / 'news/rss_headlines_eia_snapshot.csv'
        pinned = {reference(row['source_url']): row for row in self.snapshot_rows(bundle)}
        super().__init__(source=SOURCE, bundle=bundle, runtime_root=runtime_root,
                         interval=interval, max_articles=max_articles, parser=parse_rss,
                         fetcher=fetcher or fetch_eia, pinned=pinned, prefix='eia',
                         fallback='SNAPSHOT_FALLBACK', error_type=IngestionError,
                         now_iso=now_iso, reference=reference, failure_reason=failure_reason)

    @classmethod
    def from_environment(cls):
        interval = integer_setting(os.environ, 'RADAR_EIA_REFRESH_SECONDS', 1800, 300, 86400)
        maximum = integer_setting(os.environ, 'RADAR_EIA_MAX_ARTICLES', 100, 5, 1000)
        return cls(runtime_root=os.environ.get('RADAR_RUNTIME_ROOT') or None, interval=interval, max_articles=maximum)
