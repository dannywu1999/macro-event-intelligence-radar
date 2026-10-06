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

class EiaIngestion:
    def __init__(self, *, bundle=BUNDLE, runtime_root=None, interval=1800, max_articles=100, fetcher=None):
        self.bundle = Path(bundle).resolve()
        self.snapshot = self.bundle / 'news/rss_headlines_eia_snapshot.csv'
        with self.snapshot.open(encoding='utf-8', newline='') as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != FIELDS:
                raise IngestionError('SNAPSHOT_SCHEMA_INVALID')
            baseline = list(reader)
        if not baseline or any(not row['headline_or_text'] or not eia_url(row['source_url']) for row in baseline):
            raise IngestionError('SNAPSHOT_INVALID')
        self.pinned = {reference(row['source_url']): row for row in baseline}
        if len(self.pinned) != len(baseline) or max_articles < len(baseline) or interval < 300:
            raise IngestionError('UNSAFE_RETENTION_OR_INTERVAL')
        base = Path(runtime_root) if runtime_root else Path(tempfile.gettempdir()) / 'global-event-radar'
        base = base.expanduser().resolve()
        # Do not let a configuration turn bundled data into writable runtime state.
        if base.is_relative_to(self.bundle):
            raise IngestionError('RUNTIME_ROOT_INSIDE_BUNDLE')
        base.mkdir(parents=True, exist_ok=True)
        self.session = Path(tempfile.mkdtemp(prefix='eia-', dir=base))
        self.news_path = self.session / 'rss_headlines_eia_runtime.csv'
        self.interval, self.max_articles = interval, max_articles
        self.fetcher = fetcher or fetch_eia
        self.lock, self.refresh_lock = threading.RLock(), threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.rows = dict(self.pinned)
        self.status = dict(enabled=True, source=SOURCE, status='STARTING', last_attempt_at=None,
                           last_success_at=None, refresh_interval_seconds=interval,
                           article_count=len(self.rows), new_article_count=0, reason=None)
        self._write(self.rows)

    @classmethod
    def from_environment(cls):
        interval = integer_setting(os.environ, 'RADAR_EIA_REFRESH_SECONDS', 1800, 300, 86400)
        maximum = integer_setting(os.environ, 'RADAR_EIA_MAX_ARTICLES', 100, 5, 1000)
        return cls(runtime_root=os.environ.get('RADAR_RUNTIME_ROOT') or None, interval=interval, max_articles=maximum)

    def _write(self, rows):
        # A single atomic replace publishes the complete five-column CSV.
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='', dir=self.session, delete=False) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows[url] for url in sorted(rows))
        try:
            os.replace(temporary, self.news_path)
        finally:
            temporary.unlink(missing_ok=True)

    def read_view(self, adapter, paths):
        with self.lock:
            # The lock binds a read to its acquisition status; replace is also atomic.
            view = adapter.build_radar_view(replace(paths, news=self.news_path,
                    official=paths.official or self.bundle / 'official-packet.json'))
            view['live_ingestion'] = dict(self.status)
            return view

    def refresh(self):
        if not self.refresh_lock.acquire(blocking=False):
            return False
        try:
            observed = now_iso()
            with self.lock:
                self.status['last_attempt_at'] = observed
            try:
                incoming = parse_rss(self.fetcher(), observed)
                with self.lock:
                    merged = dict(self.rows)
                    for row in incoming:
                        merged.setdefault(reference(row['source_url']), row)
                    extras = [row for url, row in merged.items() if url not in self.pinned]
                    extras.sort(key=lambda row: (row['event_time'] or row['observed_time'], row['source_url']), reverse=True)
                    kept = dict(self.pinned)
                    kept.update((reference(row['source_url']), row) for row in extras[:self.max_articles-len(self.pinned)])
                    added = len(kept.keys() - self.rows.keys())
                    self._write(kept)
                    self.rows = kept
                    self.status.update(status='LIVE', last_success_at=now_iso(), article_count=len(kept),
                                       new_article_count=added, reason=None)
                return True
            except Exception as error:
                with self.lock:
                    self.status.update(status='SNAPSHOT_FALLBACK', new_article_count=0, reason=failure_reason(error))
                return False
        finally:
            self.refresh_lock.release()

    def start(self):
        with self.lock:
            if self.thread is not None:
                return
            self.thread = threading.Thread(target=self._loop, name='radar-eia-refresh', daemon=True)
            self.thread.start()

    def _loop(self):
        while not self.stop_event.is_set():
            self.refresh()
            if self.stop_event.wait(self.interval):
                break

    def close(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=TIMEOUT + 2)
