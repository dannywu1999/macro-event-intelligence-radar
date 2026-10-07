"""Small process-owned RSS state stores and one multi-source scheduler.

Only explicit opt-ins create writable ephemeral state. No import-time workers,
legacy lifecycle imports, mutation endpoints, or cross-source title matching.
"""
from __future__ import annotations
import csv
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import threading
import time

# Reuse the existing bounded EIA transport/parser utilities. Imported lazily by
# the source classes to keep the runtime-store module independent of providers.
FIELDS = ('observed_time', 'event_time', 'headline_or_text', 'source_name', 'source_url')
EIA_SOURCE = 'EIA Today in Energy'
ECB_SOURCE = 'ECB Press'
TIMEOUT = 10


def disabled_status(source, article_count=0):
    return dict(enabled=False, source=source, status='DISABLED', last_attempt_at=None,
                last_success_at=None, refresh_interval_seconds=None,
                article_count=article_count, new_article_count=0, reason=None)


class LiveSourceIngestion:
    """Provider-specific parsing/fetching, shared exact-URL retention and publishing."""
    def __init__(self, *, source, bundle, runtime_root, interval, max_articles,
                 parser, fetcher, pinned, prefix, fallback, error_type,
                 now_iso, reference, failure_reason):
        self.bundle = Path(bundle).resolve()
        self.pinned = dict(pinned)
        if max_articles < max(1, len(self.pinned)) or interval < 300:
            raise error_type('UNSAFE_RETENTION_OR_INTERVAL')
        base = Path(runtime_root) if runtime_root else Path(tempfile.gettempdir()) / 'global-event-radar'
        base = base.expanduser().resolve()
        if base.is_relative_to(self.bundle):
            raise error_type('RUNTIME_ROOT_INSIDE_BUNDLE')
        base.mkdir(parents=True, exist_ok=True)
        self.session = Path(tempfile.mkdtemp(prefix=prefix+'-', dir=base))
        self.news_path = self.session / ('rss_headlines_'+prefix+'_runtime.csv')
        self.source, self.interval, self.max_articles = source, interval, max_articles
        self.parser, self.fetcher, self.fallback = parser, fetcher, fallback
        self.now_iso, self.reference, self.failure_reason = now_iso, reference, failure_reason
        self.lock, self.refresh_lock = threading.RLock(), threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.rows = dict(self.pinned)
        self.status = dict(enabled=True, source=source, status='STARTING', last_attempt_at=None,
                           last_success_at=None, refresh_interval_seconds=interval,
                           article_count=len(self.rows), new_article_count=0, reason=None)
        self._write(self.rows)

    def _write(self, rows):
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='', dir=self.session, delete=False) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows[key] for key in sorted(rows))
        try:
            os.replace(temporary, self.news_path)
        finally:
            temporary.unlink(missing_ok=True)

    def read_view(self, adapter, paths):
        with self.lock:
            view = adapter.build_radar_view(replace(paths, news=self.news_path,
                    official=paths.official or self.bundle / 'official-packet.json'))
            view['discovery_sources'] = {EIA_SOURCE: disabled_status(EIA_SOURCE),
                                         ECB_SOURCE: disabled_status(ECB_SOURCE)}
            view['discovery_sources'][self.source] = dict(self.status)
            view['live_ingestion'] = dict(view['discovery_sources'][EIA_SOURCE])
            return view

    def refresh(self):
        if not self.refresh_lock.acquire(blocking=False):
            return False
        try:
            observed = self.now_iso()
            with self.lock:
                self.status['last_attempt_at'] = observed
            try:
                incoming = self.parser(self.fetcher(), observed)
                with self.lock:
                    merged = dict(self.rows)
                    for row in incoming:
                        merged.setdefault(self.reference(row['source_url']), row)
                    extras = [row for key, row in merged.items() if key not in self.pinned]
                    extras.sort(key=lambda row: (row['event_time'] or row['observed_time'], row['source_url']), reverse=True)
                    kept = dict(self.pinned)
                    kept.update((self.reference(row['source_url']), row)
                                for row in extras[:self.max_articles-len(self.pinned)])
                    added = len(kept.keys() - self.rows.keys())
                    self._write(kept)
                    self.rows = kept
                    self.status.update(status='LIVE', last_success_at=self.now_iso(), article_count=len(kept),
                                       new_article_count=added, reason=None)
                return True
            except Exception as error:
                with self.lock:
                    state = self.fallback or ('LAST_VALID_FALLBACK' if self.rows else 'UNAVAILABLE')
                    self.status.update(status=state, new_article_count=0, reason=self.failure_reason(error))
                return False
        finally:
            self.refresh_lock.release()

    def start(self):
        with self.lock:
            if self.thread is not None:
                return
            self.thread = threading.Thread(target=self._loop, name='radar-'+self.source+'-refresh', daemon=True)
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


class DiscoveryIngestion:
    """One owned worker; isolated source stores, deadlines and last-valid states.

    Source fetches are sequential and individually bounded. API reads only the
    atomically published combined CSV/status snapshot; reads never fetch/write.
    """
    def __init__(self, sources, *, bundle, runtime_root=None, clock=time.monotonic):
        from .eia_live_ingestion import EiaIngestion, IngestionError, reference
        self.bundle = Path(bundle).resolve()
        self.sources = {source.source: source for source in sources}
        if not self.sources or len(self.sources) != len(sources) or not set(self.sources) <= {EIA_SOURCE, ECB_SOURCE}:
            raise IngestionError('DISCOVERY_SOURCE_CONFIGURATION_INVALID')
        # The existing immutable EIA bundle remains the product restart fallback.
        self.baseline = EiaIngestion.snapshot_rows(self.bundle)
        self.reference = reference
        base = Path(runtime_root) if runtime_root else Path(tempfile.gettempdir()) / 'global-event-radar'
        base = base.expanduser().resolve()
        if base.is_relative_to(self.bundle):
            raise IngestionError('RUNTIME_ROOT_INSIDE_BUNDLE')
        base.mkdir(parents=True, exist_ok=True)
        self.session = Path(tempfile.mkdtemp(prefix='discovery-', dir=base))
        self.news_path = self.session/'rss_headlines_discovery_runtime.csv'
        self.lock, self.refresh_lock = threading.RLock(), threading.Lock()
        self.clock, self.deadlines = clock, {name: 0.0 for name in self.sources}
        self.stop_event, self.thread = threading.Event(), None
        self.statuses = {}
        self._publish()

    @classmethod
    def from_environment(cls):
        from .eia_live_ingestion import EiaIngestion, BUNDLE
        from .ecb_live_ingestion import EcbIngestion
        sources = []
        try:
            if os.environ.get('RADAR_LIVE_EIA', '').strip() == '1':
                sources.append(EiaIngestion.from_environment())
            if os.environ.get('RADAR_LIVE_ECB', '').strip() == '1':
                sources.append(EcbIngestion.from_environment())
            return cls(sources, bundle=BUNDLE, runtime_root=os.environ.get('RADAR_RUNTIME_ROOT') or None)
        except BaseException:
            for source in sources:
                source.close()
            raise

    def _write(self, rows):
        # Reuse exactly the source store's atomic five-column CSV publisher.
        LiveSourceIngestion._write(self, rows)

    def _publish(self):
        rows = {(row['source_name'], self.reference(row['source_url'])): row for row in self.baseline}
        statuses = {EIA_SOURCE: disabled_status(EIA_SOURCE, len(self.baseline)), ECB_SOURCE: disabled_status(ECB_SOURCE)}
        for name, source in self.sources.items():
            with source.lock:
                rows.update(((name, key), dict(row)) for key, row in source.rows.items())
                statuses[name] = dict(source.status)
        with self.lock:
            self._write(rows)
            self.statuses = statuses

    def refresh(self, name=None):
        if not self.refresh_lock.acquire(blocking=False):
            return False
        results = []
        try:
            names = [name] if name is not None else list(self.sources)
            for current in names:
                if current not in self.sources:
                    raise ValueError('SOURCE_NOT_ENABLED')
                source = self.sources[current]
                succeeded = source.refresh()
                self.deadlines[current] = self.clock() + source.interval
                try:
                    self._publish()
                except Exception:
                    # Keep the last atomically published view/status on IO failure.
                    with self.lock:
                        old = dict(self.statuses[current])
                        old.update(status='SNAPSHOT_FALLBACK' if current==EIA_SOURCE else
                                   ('LAST_VALID_FALLBACK' if old['article_count'] else 'UNAVAILABLE'),
                                   last_attempt_at=source.status['last_attempt_at'], new_article_count=0,
                                   reason='RUNTIME_PUBLISH_FAILED')
                        self.statuses = {**self.statuses, current: old}
                    succeeded = False
                results.append(succeeded)
            return all(results)
        finally:
            self.refresh_lock.release()

    def read_view(self, adapter, paths):
        with self.lock:
            view = adapter.build_radar_view(replace(paths, news=self.news_path,
                    official=paths.official or self.bundle/'official-packet.json'))
            view['discovery_sources'] = {name: dict(state) for name, state in self.statuses.items()}
            # Historical consumers keep EIA acquisition semantics and EIA counts.
            view['live_ingestion'] = dict(self.statuses[EIA_SOURCE])
            return view

    def start(self):
        with self.lock:
            if self.thread is not None:
                return
            self.thread = threading.Thread(target=self._loop, name='radar-discovery-refresh', daemon=True)
            self.thread.start()

    def _loop(self):
        while not self.stop_event.is_set():
            for name in self.sources:
                if self.stop_event.is_set():
                    break
                if self.clock() >= self.deadlines[name]:
                    self.refresh(name)
            delay = max(0.1, min(self.deadlines.values()) - self.clock())
            if self.stop_event.wait(delay):
                break

    def close(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=len(self.sources)*TIMEOUT + 2)
        for source in self.sources.values():
            source.close()
