"""Read-only, fail-closed adapter for the first Global Event Radar feed.

Read contract: one feed entry represents one supplied News discovery record,
not one deduplicated world event. News supplies discovery context only. An
News entries remain UNVERIFIED_NEWS. Only a separate, explicitly linked fact
proposition may carry OFFICIAL_CONFIRMED after the Official packet's authority,
document, URL and ordered first-seen/retrieval evidence validate. Publication
may be null; a supplied publication time must validate and precede first-seen.
Article-level source identity is preserved. A separate conservative Canonical
Event V0 projection groups only explicit, compatible rate-decision headlines.
Its IDs identify grouped article sets, not verified facts. Missing data stays null.

Local defaults read the bounded headlines inbox and optional development
MacroView. Explicit RADAR_DATA_ROOT selects a portable news directory and
disables the development MacroView fallback. All inputs can be overridden with
GLOBAL_EVENT_RADAR_*_PATH; no input is written or migrated.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[2]
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_NEWS_FILES = 64
MAX_NEWS_TOTAL_BYTES = 32 * 1024 * 1024
DEFAULT_NEWS_INBOX = ROOT / "event_sources" / "headlines_inbox"
DEFAULT_DEVELOPMENT_MACROVIEW = ROOT / "handoff" / "stage1b_historical_campaign" / "MACRO_VIEW_V1_CANONICAL.json"
CONTRACT_VERSION = "GLOBAL_EVENT_RADAR_READ_V1"
NEWS_FILE_PREFIXES = ("rss_headlines_", "gdelt_headlines_", "federal_register_headlines_")


@dataclass(frozen=True)
class EvidencePaths:
    news: Path | None = None
    official: Path | None = None
    macroview: Path | None = None
    polymarket: Path | None = None
    source_health: Path | None = None
    geography: Path | None = None
    expectation_links: Path | None = None
    market_reality: Path | None = None

    @classmethod
    def from_environment(cls) -> "EvidencePaths":
        root_value = os.environ.get("RADAR_DATA_ROOT", "").strip()
        data_root = Path(root_value).expanduser().resolve() if root_value else None

        def configured(name: str) -> Path | None:
            value = os.environ.get(name, "").strip()
            if not value:
                return None
            path = Path(value).expanduser()
            return data_root / path if data_root and not path.is_absolute() else path

        macroview = configured("GLOBAL_EVENT_RADAR_MACROVIEW_PATH")
        if not data_root and macroview is None:
            macroview = DEFAULT_DEVELOPMENT_MACROVIEW
        return cls(
            news=configured("GLOBAL_EVENT_RADAR_NEWS_PATH") or (
                data_root / "news" if data_root else DEFAULT_NEWS_INBOX),
            official=configured("GLOBAL_EVENT_RADAR_OFFICIAL_PATH"),
            macroview=macroview,
            polymarket=configured("GLOBAL_EVENT_RADAR_POLYMARKET_PATH"),
            source_health=configured("GLOBAL_EVENT_RADAR_SOURCE_HEALTH_PATH"),
            geography=configured("GLOBAL_EVENT_RADAR_GEOGRAPHY_PATH"),
            expectation_links=configured("GLOBAL_EVENT_RADAR_EXPECTATION_LINKS_PATH"),
            market_reality=configured("GLOBAL_EVENT_RADAR_MARKET_REALITY_PATH"),
        )


class EvidenceReadError(ValueError):
    """A configured read path is absent, oversized, or malformed."""


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


class _NewsTextParser(HTMLParser):
    """Extract inert text; block boundaries separate table cells/paragraphs."""

    _BLOCKS = {"br", "hr", "p", "div", "table", "thead", "tbody", "tfoot",
               "tr", "td", "th", "li", "ul", "ol", "section", "h1", "h2",
               "h3", "h4", "h5", "h6", "pre", "blockquote"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self._BLOCKS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCKS:
            self.parts.append(" ")

    def handle_entityref(self, name: str) -> None:
        # Already unescaped once before parsing; retain nested literal entities.
        self.parts.append("&" + name + ";")

    def handle_charref(self, name: str) -> None:
        self.parts.append("&#" + name + ";")

    def unknown_decl(self, data: str) -> None:
        if data.startswith("CDATA["):
            content = _NewsTextParser()
            content.feed(data[len("CDATA["):])
            content.close()
            self.parts.extend(content.parts)


def normalize_news_text(value: Any) -> str | None:
    """Plain presentation text only; never changes acquisition/dedup evidence."""
    if not isinstance(value, str) or not value.strip():
        return None
    parser = _NewsTextParser()
    parser.feed(unescape(value))
    parser.close()
    return " ".join("".join(parser.parts).split()) or None


def _raw_text(*values: Any) -> str | None:
    return next((v for v in values if isinstance(v, str) and v.strip()), None)


def _feed_order_key(item: Mapping[str, Any]) -> tuple[datetime, datetime, str]:
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    observed = _utc(item.get("observed_at"))
    reported = _utc(item.get("reported_at")) if item.get("reported_time_kind") == "REPORTED_TIME" else None
    return (reported or observed or minimum, observed or minimum,
            item.get("article_reference") or item.get("raw_title") or "")


_RATE_DECISION = re.compile(
    r"^(ECB|European Central Bank|Fed|Federal Reserve) "
    r"(cuts|lowers|reduces|raises|hikes|increases) (?:interest )?rates by "
    r"([0-9]{1,3}(?:\.[0-9]{1,2})?)\s*(?:basis points|bps?|bp)[.!]?$", re.IGNORECASE)


def _rate_signature(item: Mapping[str, Any]) -> tuple[str, str, str] | None:
    match = _RATE_DECISION.fullmatch(item.get("title") or "")
    if not match:
        return None
    actor, action, amount = match.groups()
    amount = Decimal(amount)
    if not 0 < amount <= 100:
        return None
    return ("ECB" if actor.casefold() in {"ecb", "european central bank"} else "FED",
            "CUT" if action.casefold() in {"cuts", "lowers", "reduces"} else "RAISE",
            format(amount.normalize(), "f"))


def canonical_merge_evidence(a: Mapping[str, Any], b: Mapping[str, Any]) -> dict[str, Any]:
    """Explain the deliberately narrow V0 rule; observed/proxy dates cannot merge."""
    signature = _rate_signature(a)
    if not signature or signature != _rate_signature(b):
        return {"merge": False, "reason": "NO_MATCHING_EXPLICIT_RATE_DECISION"}
    if any(item.get("reported_time_kind") != "REPORTED_TIME" for item in (a, b)):
        return {"merge": False, "reason": "GENUINE_REPORTED_TIMES_REQUIRED"}
    left, right = _utc(a.get("reported_at")), _utc(b.get("reported_at"))
    if not left or not right or left.date() != right.date() or abs((left - right).total_seconds()) > 21600:
        return {"merge": False, "reason": "INCOMPATIBLE_REPORTED_WINDOW"}
    return {"merge": True, "rule": "EXPLICIT_RATE_DECISION_SAME_DAY_6H_V0",
            "actor": signature[0], "action": signature[1], "basis_points": signature[2],
            "reported_day": left.date().isoformat(), "span_seconds": abs((left - right).total_seconds())}


def build_canonical_events(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic read-only article-set identity. Membership changes change ID.

    No fuzzy/transitive/source-based merge. All members must agree pairwise.
    Missing title/reference or conflicting reuse of a reference remains unassigned.
    Source-supplied item event IDs are not overwritten or used as V0 grouping proof.
    """
    by_ref: dict[str, list[dict[str, Any]]] = {}
    unassigned = 0
    for item in items:
        ref = _text(item.get("article_reference"))
        if not ref or not item.get("title"):
            unassigned += 1
        else:
            by_ref.setdefault(ref, []).append(item)
    representatives = []
    for ref, copies in sorted(by_ref.items()):
        # Multiple observations of identical article content are one membership.
        signatures = {(i["title"], i.get("reported_at"), i.get("reported_time_kind"),
                       (i.get("news_source") or {}).get("name")) for i in copies}
        if len(signatures) != 1:
            unassigned += len(copies)
            continue
        representative = dict(copies[0])
        observed = [_utc(i.get("observed_at")) for i in copies]
        representative["observed_at"] = _iso(min(t for t in observed if t)) if any(observed) else None
        representative["_canonical_latest_at"] = max(_feed_order_key(i)[0] for i in copies)
        representatives.append(representative)
    groups: list[list[dict[str, Any]]] = []
    for item in representatives:
        group = next((g for g in groups if all(canonical_merge_evidence(item, member)["merge"] for member in g)), None)
        if group is None:
            groups.append([item])
        else:
            group.append(item)
    events = []
    for group in groups:
        refs = sorted(i["article_reference"] for i in group)
        identity = json.dumps(["CANONICAL_EVENT_V0", refs], ensure_ascii=False, separators=(",", ":"))
        observed = [_utc(i.get("observed_at")) for i in group]
        chronology = [i["_canonical_latest_at"] for i in group]
        minimum = datetime.min.replace(tzinfo=timezone.utc)
        pairs = [{"article_references": [a["article_reference"], b["article_reference"]],
                  **canonical_merge_evidence(a, b)}
                 for index, a in enumerate(group) for b in group[index + 1:]]
        events.append({
            "event_id": "canonical-event-v0-" + hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            "event_title": min((i["title"] for i in group), key=lambda t: (len(t), t.casefold(), t)),
            "article_count": len(refs), "article_references": refs,
            "source_names": sorted({i["news_source"]["name"] for i in group if i.get("news_source", {}).get("name")}),
            "first_detected_at": _iso(min(t for t in observed if t)) if any(observed) else None,
            "latest_article_at": _iso(max(chronology)) if max(chronology) != minimum else None,
            "verification_status": "UNVERIFIED_NEWS", "event_occurred_at": None,
            "grouping": {"rule": pairs[0]["rule"] if pairs else "SINGLE_ARTICLE_INSUFFICIENT_MERGE_EVIDENCE",
                         "pair_evidence": pairs},
        })
    events.sort(key=lambda e: (e["latest_article_at"] or "", e["event_id"]), reverse=True)
    return {"events": events, "canonical_event_contract": "CANONICAL_EVENT_V0",
            "canonical_event_projection_status": "PARTIAL" if unassigned else "AVAILABLE",
            "unassigned_article_count": unassigned,
            "distinct_event_count": None if unassigned else len(events)}


def _read_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    try:
        if not path.is_file():
            raise EvidenceReadError("CONFIGURED_EVIDENCE_FILE_UNAVAILABLE")
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise EvidenceReadError("CONFIGURED_EVIDENCE_FILE_TOO_LARGE")
        suffix = path.suffix.lower()
        if suffix == ".csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]
        raw = path.read_text(encoding="utf-8")
        if suffix in {".jsonl", ".ndjson"}:
            rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        else:
            payload = json.loads(raw)
            if isinstance(payload, list):
                rows = payload
            elif isinstance(payload, dict) and isinstance(payload.get("items"), list):
                rows = payload["items"]
            elif isinstance(payload, dict) and isinstance(payload.get("records"), list):
                rows = payload["records"]
            elif isinstance(payload, dict):
                rows = [payload]
            else:
                raise EvidenceReadError("CONFIGURED_EVIDENCE_SCHEMA_INVALID")
        if not all(isinstance(row, dict) for row in rows):
            raise EvidenceReadError("CONFIGURED_EVIDENCE_SCHEMA_INVALID")
        return rows
    except EvidenceReadError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, csv.Error) as exc:
        raise EvidenceReadError("CONFIGURED_EVIDENCE_READ_FAILED:" + type(exc).__name__) from None


def _collector_kind(path: Path) -> str | None:
    name = path.name.lower()
    if name.startswith("rss_headlines_"):
        return "rss"
    if name.startswith("gdelt_headlines_"):
        return "gdelt"
    if name.startswith("federal_register_headlines_"):
        return "federal_register"
    return None


def _news_dedupe_key(row: Mapping[str, Any], collector: str | None) -> str | None:
    """Use the matching existing collector article key for its real CSV format."""
    reference = _text(row.get("source_item_reference"), row.get("item_reference"), row.get("discovery_record_id"))
    if reference:
        material = "article-reference|" + reference.strip()
        return hashlib.sha256(material.encode("utf-8")).hexdigest()
    source = _text(row.get("source_name"), row.get("source_publisher"))
    headline = _text(row.get("headline_or_text"), row.get("title"), row.get("headline"))
    event_time = _text(row.get("event_time"))
    url = _text(row.get("source_url"), row.get("url"))
    if not source or not headline:
        return None
    normalized_headline = " ".join(headline.strip().lower().split())
    if event_time:
        parts = [source.strip().lower(), event_time.strip(), normalized_headline]
        if collector == "gdelt":
            parts.append((url or "").strip().lower())
        material = "|".join(parts)
    elif url:
        material = "article-url|" + source.strip().lower() + "|" + url.strip().lower()
    else:
        return None
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _article_url_key(row: Mapping[str, Any]) -> str | None:
    value = _text(row.get("source_url"), row.get("url"))
    if not _valid_url(value):
        return None
    parsed = urlsplit(value.strip())
    normalized = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))
    return normalized


def _read_news_rows(path: Path | None) -> list[dict[str, Any]]:
    """Read one configured file or a bounded, deterministic collector inbox."""
    if path is None:
        return []
    if not path.is_dir():
        kind = _collector_kind(path)
        rows = _read_rows(path)
        return [{**row, "_radar_collector": kind} for row in rows]
    try:
        files = sorted(
            (candidate for candidate in path.iterdir()
             if candidate.is_file() and candidate.name.lower().startswith(NEWS_FILE_PREFIXES)
             and candidate.suffix.lower() == ".csv"),
            key=lambda candidate: candidate.name.lower(),
        )
        if len(files) > MAX_NEWS_FILES:
            raise EvidenceReadError("NEWS_INBOX_FILE_LIMIT_EXCEEDED")
        total_bytes = sum(candidate.stat().st_size for candidate in files)
        if total_bytes > MAX_NEWS_TOTAL_BYTES:
            raise EvidenceReadError("NEWS_INBOX_SIZE_LIMIT_EXCEEDED")
        result: list[dict[str, Any]] = []
        for candidate in files:
            kind = _collector_kind(candidate)
            result.extend({**row, "_radar_collector": kind} for row in _read_rows(candidate))
        return result
    except EvidenceReadError:
        raise
    except OSError as exc:
        raise EvidenceReadError("NEWS_INBOX_READ_FAILED:" + type(exc).__name__) from None


def _dedupe_news_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_urls: set[str] = set()
    for row in rows:
        url_key = _article_url_key(row)
        if url_key and url_key in seen_urls:
            continue
        key = _news_dedupe_key(row, row.get("_radar_collector"))
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        if url_key:
            seen_urls.add(url_key)
        kept.append(row)
    return kept


def _artifact_fingerprint_valid(row: Mapping[str, Any]) -> bool:
    supplied = row.get("artifact_fingerprint")
    if not isinstance(supplied, str) or not supplied:
        return False
    body = {key: value for key, value in row.items() if key != "artifact_fingerprint"}
    encoded = (json.dumps(body, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest() == supplied


def _valid_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _official_link(row: Mapping[str, Any]) -> str | None:
    return _text(row.get("event_reference"), row.get("discovery_record_id"))


def _official_evidence(row: Mapping[str, Any], discovery_id: str | None) -> dict[str, Any] | None:
    if not discovery_id or _official_link(row) != discovery_id:
        return None
    return _official_packet(row)


def _official_packet(row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Publication may be unknown; supplied times must validate, never fall back to observation."""
    is_event_reality = row.get("artifact_type") == "EVENT_REALITY_V1" and _artifact_fingerprint_valid(row)
    is_packet = row.get("official_confirmation") == "OFFICIAL_CONFIRMED"
    if not (is_event_reality or is_packet) or row.get("authority_role") != "FACT_AUTHORITY":
        return None
    source_url = _text(row.get("official_source"), row.get("source_url"), row.get("document_url"))
    document = _text(row.get("official_document_reference"), row.get("document_reference"))
    proposition = _text(row.get("official_fact_proposition"), row.get("fact_proposition"))
    # Preserve null/omitted publication, but do not silently turn a malformed
    # non-null value (including wrong types or naive/date-only strings) into null.
    published = next((row[key] for key in ("official_published_at", "published_at")
                      if row.get(key) is not None), None)
    first_seen = _text(row.get("official_project_first_seen_at"), row.get("project_first_seen_at"))
    retrieved = _text(row.get("official_retrieved_at"), row.get("retrieved_at"))
    published_dt, first_seen_dt, retrieved_dt = _utc(published), _utc(first_seen), _utc(retrieved)
    if published is not None and published_dt is None:
        return None
    if not (_valid_url(source_url) and document and proposition and first_seen_dt and retrieved_dt):
        return None
    if first_seen_dt > retrieved_dt or (published_dt is not None and published_dt > first_seen_dt):
        return None
    return {
        "source_url": source_url,
        "document_reference": document,
        "fact_proposition": proposition,
        "published_at": _iso(published_dt),
        "first_seen_at": _iso(first_seen_dt),
        "retrieved_at": _iso(retrieved_dt),
        "event_occurred_at": _iso(_utc(_text(row.get("event_occurred_at"), row.get("event_timestamp"), row.get("occurrence_timestamp")))),
        "artifact_fingerprint": row.get("artifact_fingerprint") if is_event_reality else None,
    }


def _resolve_official_event(row: Mapping[str, Any], event_ids: set[str],
                            by_reference: Mapping[str, set[str]]) -> tuple[str | None, str]:
    """All supplied identities must resolve uniquely and agree; never fuzzy-match."""
    resolved: set[str] = set()
    supplied = False
    for key in ("canonical_event_id", "article_reference", "source_item_reference",
                "item_reference", "discovery_record_id", "event_reference"):
        value = row.get(key)
        if value is None or value == "":
            continue
        supplied = True
        if not isinstance(value, str) or not value.strip():
            return None, "INVALID_LINK_REFERENCE"
        reference = value.strip()
        matches = ({reference} if reference in event_ids else set()) if key == "canonical_event_id" else by_reference.get(reference, set())
        if len(matches) != 1:
            return None, "AMBIGUOUS_REFERENCE" if matches else "REFERENCE_NOT_FOUND"
        resolved.update(matches)
    if len(resolved) == 1:
        return next(iter(resolved)), "EXPLICIT_UNIQUE_LINK"
    return None, "CONFLICTING_REFERENCES" if supplied else "NO_EXPLICIT_REFERENCE"


def build_official_evidence_projection(rows: list[dict[str, Any]], items: list[dict[str, Any]],
                                       events: list[dict[str, Any]]) -> dict[str, Any]:
    """Read-only Official Evidence V0; a confirmed proposition is not a confirmed headline.

    Inputs retain the existing Official packet / sealed EVENT_REALITY_V1 contract.
    Missing authority name/title are null, never inferred from a URL or News publisher.
    Invalid packets remain visible as INCOMPLETE and cannot attach to any event.
    """
    event_ids = {e["event_id"] for e in events}
    article_events: dict[str, set[str]] = {}
    for event in events:
        for reference in event["article_references"]:
            article_events.setdefault(reference, set()).add(event["event_id"])
    by_reference = {ref: set(ids) for ref, ids in article_events.items()}
    for item in items:
        ids = article_events.get(item.get("article_reference"), set())
        for key in ("article_reference", "discovery_record_id"):
            reference = _text(item.get(key))
            if reference:
                by_reference.setdefault(reference, set()).update(ids)
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        packet = _official_packet(row)
        authority = _text(row.get("authority_name"), row.get("official_authority_name"))
        url = _text(row.get("official_source"), row.get("source_url"), row.get("document_url"))
        url = url if _valid_url(url) else None
        proposition = _raw_text(row.get("official_fact_proposition"), row.get("fact_proposition"))
        document = _text(row.get("official_document_reference"), row.get("document_reference"))
        published = _iso(_utc(_text(row.get("official_published_at"), row.get("published_at"))))
        identity = json.dumps(["OFFICIAL_EVIDENCE_V0", authority, url, document, proposition, published],
                              ensure_ascii=False, separators=(",", ":"))
        evidence_id = "official-evidence-v0-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
        event_id, link_status = _resolve_official_event(row, event_ids, by_reference)
        if packet is None:
            event_id, link_status = None, "PACKET_VALIDATION_FAILED"
        evidence = {
            "official_evidence_id": evidence_id, "authority_name": authority,
            "document_title": _text(row.get("official_document_title"), row.get("document_title")),
            "document_url": url, "document_reference": document, "published_at": published,
            "fact_proposition": proposition, "canonical_event_id": event_id,
            "evidence_status": "OFFICIAL_CONFIRMED" if packet and event_id else ("UNLINKED" if packet else "INCOMPLETE"),
            "link_status": link_status, "authority_role": _text(row.get("authority_role")),
            "first_seen_at": packet["first_seen_at"] if packet else None,
            "retrieved_at": packet["retrieved_at"] if packet else None,
            "artifact_fingerprint": packet["artifact_fingerprint"] if packet else None,
            "effective_at": _iso(_utc(_text(row.get("official_effective_at"), row.get("effective_at")))),
            "document_type": _text(row.get("document_type")),
        }
        existing = evidence_by_id.get(evidence_id)
        if existing is not None and existing != evidence:
            # Do not choose between conflicting copies or let input order pick a link.
            evidence_by_id[evidence_id] = {
                **existing, "authority_name": authority, "document_title": None,
                "canonical_event_id": None, "evidence_status": "AMBIGUOUS_EVIDENCE",
                "link_status": "CONFLICTING_EVIDENCE_COPIES", "first_seen_at": None,
                "retrieved_at": None, "artifact_fingerprint": None, "effective_at": None,
                "document_type": None,
                "authority_role": existing["authority_role"] if existing["authority_role"] == evidence["authority_role"] else None,
            }
        else:
            evidence_by_id[evidence_id] = evidence
    evidence = [evidence_by_id[key] for key in sorted(evidence_by_id)]
    enriched = []
    for event in events:
        ids = [e["official_evidence_id"] for e in evidence
               if e["canonical_event_id"] == event["event_id"] and e["evidence_status"] == "OFFICIAL_CONFIRMED"]
        enriched.append({**event, "official_evidence_count": len(ids), "official_evidence_ids": ids,
                         "official_evidence_status": "FACT_PROPOSITIONS_LINKED" if ids else "NO_OFFICIAL_EVIDENCE_LINKED"})
    return {"official_evidence_contract": "OFFICIAL_EVIDENCE_V0", "official_evidence": evidence, "events": enriched}


def _source_status(path: Path | None, *, rows: list[dict[str, Any]] | None = None, default_development: bool = False) -> dict[str, Any]:
    if path is None:
        return {"status": "NOT_CONFIGURED", "last_success_at": None}
    if default_development and path == DEFAULT_DEVELOPMENT_MACROVIEW:
        try:
            doc = _read_rows(path)[0]
        except (EvidenceReadError, IndexError):
            return {"status": "DEVELOPMENT_EXAMPLE_UNAVAILABLE", "last_success_at": None}
        if doc.get("status") != "FROZEN" and doc.get("status") != "CANONICAL":
            return {"status": "DEVELOPMENT_CONTRACT_NOT_FROZEN", "last_success_at": None}
    if rows is None:
        try:
            rows = _read_news_rows(path) if path.is_dir() else _read_rows(path)
        except EvidenceReadError:
            return {"status": "UNAVAILABLE", "last_success_at": None}
    return {"status": "AVAILABLE" if rows else "EMPTY", "last_success_at": None}


def _health_rows(rows: list[dict[str, Any]], now: datetime, stale_after_seconds: int) -> tuple[list[dict[str, Any]], str | None]:
    health: list[dict[str, Any]] = []
    successes: list[datetime] = []
    for row in rows:
        source = _text(row.get("source_name"), row.get("source_id"), row.get("provider_id"))
        last = _utc(row.get("last_success_at"))
        if last is None or last > now:
            status = "UNKNOWN"
            last_success = None
        else:
            age = (now - last).total_seconds()
            status = "STALE" if age > stale_after_seconds else "FRESH"
            last_success = _iso(last)
            successes.append(last)
        health.append({"source": source, "status": status, "last_success_at": last_success})
    last_update = _iso(max(successes)) if successes else None
    return health, last_update


def build_radar_view(
    paths: EvidencePaths | None = None,
    *,
    now: str | datetime | None = None,
    stale_after_seconds: int = 24 * 60 * 60,
) -> dict[str, Any]:
    """Build an immutable API-ready Feed projection from explicitly configured files."""
    paths = paths or EvidencePaths.from_environment()
    current = _utc(now) if isinstance(now, str) else (now.astimezone(timezone.utc) if now else datetime.now(timezone.utc))
    if current is None:
        raise ValueError("INVALID_NOW")

    sources = {
        "news": _source_status(paths.news),
        "official": _source_status(paths.official),
        "macroview": _source_status(paths.macroview, default_development=paths.macroview == DEFAULT_DEVELOPMENT_MACROVIEW),
        "polymarket": _source_status(paths.polymarket),
        "source_health": _source_status(paths.source_health),
    }
    if paths.news is None:
        return {
            "contract_version": CONTRACT_VERSION, "read_only": True, "status": "UNAVAILABLE",
            "reason": "NEWS_EVIDENCE_PATH_NOT_CONFIGURED", "items": [], "item_count": 0,
            "events": [], "canonical_event_contract": "CANONICAL_EVENT_V0",
            "official_evidence": [], "official_evidence_contract": "OFFICIAL_EVIDENCE_V0",
            "geography_contract": "EVENT_GEOGRAPHY_V1", "mapped_event_count": 0, "unmapped_event_count": 0,
            "geography_metadata_status": "NOT_EVALUATED",
            "canonical_event_projection_status": "UNAVAILABLE", "unassigned_article_count": 0,
            "distinct_event_count": None, "last_successful_update": None,
            "source_health": [], "sources": sources,
        }
    try:
        raw_news_rows = _read_news_rows(paths.news)
        news_rows = _dedupe_news_rows(raw_news_rows)
        official_rows = _read_rows(paths.official)
        # Curated second-authority packet is a supplement to this exact bundle,
        # never a fallback for explicitly configured external Official inputs.
        # It is considered only while its exact News reference is present.
        if paths.official and paths.official.resolve() == (ROOT / "demo/radar_public/official-packet.json").resolve():
            supplement = paths.official.with_name("ecb-official-packet.json")
            if supplement.is_file():
                references = {_text(row.get("article_reference"), row.get("source_url")) for row in news_rows}
                official_rows.extend(row for row in _read_rows(supplement)
                                     if row.get("article_reference") in references)
        macro_rows = _read_rows(paths.macroview) if paths.macroview and sources["macroview"]["status"] in {"AVAILABLE", "EMPTY"} else []
        try:
            poly_rows = _read_rows(paths.polymarket)
        except EvidenceReadError:
            poly_rows = []
            sources["polymarket"] = {"status": "UNAVAILABLE", "last_success_at": None}
        health_rows = _read_rows(paths.source_health)
    except EvidenceReadError as exc:
        return {
            "contract_version": CONTRACT_VERSION, "read_only": True, "status": "UNAVAILABLE",
            "reason": str(exc), "items": [], "item_count": 0, "distinct_event_count": None,
            "events": [], "canonical_event_contract": "CANONICAL_EVENT_V0",
            "official_evidence": [], "official_evidence_contract": "OFFICIAL_EVIDENCE_V0",
            "geography_contract": "EVENT_GEOGRAPHY_V1", "mapped_event_count": 0, "unmapped_event_count": 0,
            "geography_metadata_status": "NOT_EVALUATED",
            "canonical_event_projection_status": "UNAVAILABLE", "unassigned_article_count": 0,
            "last_successful_update": None, "source_health": [], "sources": sources,
        }

    sources["news"] = {"status": "AVAILABLE" if news_rows else "EMPTY", "last_success_at": None}
    sources["official"] = {"status": "AVAILABLE" if official_rows else ("EMPTY" if paths.official else "NOT_CONFIGURED"), "last_success_at": None}
    if sources["polymarket"]["status"] != "UNAVAILABLE":
        sources["polymarket"] = {"status": "AVAILABLE" if poly_rows else ("EMPTY" if paths.polymarket else "NOT_CONFIGURED"), "last_success_at": None}
    sources["source_health"] = {"status": "AVAILABLE" if health_rows else ("EMPTY" if paths.source_health else "NOT_CONFIGURED"), "last_success_at": None}
    if macro_rows:
        trusted_macroview = any(
            row.get("artifact_type") == "REAL_BASE_MACROVIEW_V1" and _artifact_fingerprint_valid(row)
            for row in macro_rows
        )
        development_macroview = any(
            row.get("status") == "DEVELOPMENT_CONTRACT_NOT_FROZEN" for row in macro_rows
        )
        if not trusted_macroview and development_macroview:
            sources["macroview"] = {"status": "DEVELOPMENT_CONTRACT_NOT_FROZEN", "last_success_at": None}

    officials_by_ref: dict[str, list[dict[str, Any]]] = {}
    for row in official_rows:
        link = _official_link(row)
        if link:
            officials_by_ref.setdefault(link, []).append(row)
    expectations = {
        _text(row.get("discovery_record_id"), row.get("event_reference")): row
        for row in poly_rows
        if _text(row.get("discovery_record_id"), row.get("event_reference"))
    }
    macro_by_ref = {
        _text(row.get("event_reference"), row.get("discovery_record_id")): row
        for row in macro_rows
        if _text(row.get("event_reference"), row.get("discovery_record_id"))
        and row.get("artifact_type") == "REAL_BASE_MACROVIEW_V1"
        and _artifact_fingerprint_valid(row)
    }

    items: list[dict[str, Any]] = []
    for news in news_rows:
        discovery_id = _text(news.get("discovery_record_id"))
        linked = officials_by_ref.get(discovery_id, []) if discovery_id else []
        confirmed = [_official_evidence(row, discovery_id) for row in linked]
        confirmed = [row for row in confirmed if row is not None]
        official = confirmed[0] if len(confirmed) == 1 else None
        # A packet supports its proposition, never every claim in a News headline.
        verification = "UNVERIFIED_NEWS"

        canonical_id = _text(news.get("canonical_event_id"))
        identity_ref = _text(news.get("identity_evidence_ref"))
        identity_status = "VERIFIED_BY_SOURCE" if canonical_id and identity_ref and news.get("identity_status") == "CANONICAL" else "UNKNOWN"
        if identity_status != "VERIFIED_BY_SOURCE":
            canonical_id = None

        observed_at = _utc(_text(news.get("observed_time"), news.get("project_first_seen_at"), news.get("observed_at")))
        reported_value = _text(news.get("source_published_at"), news.get("source_published_at_utc"), news.get("published_at"))
        reported_dt = _utc(reported_value) if reported_value else None
        event_time = _utc(news.get("event_time"))
        observed_fallback = event_time is not None and observed_at is not None and event_time == observed_at
        is_proxy_date = (str(news.get("event_time_is_proxy", "")).strip().lower() == "true"
                         or news.get("_radar_collector") == "federal_register"
                         or (not reported_dt and (news.get("_radar_collector") == "gdelt"
                             or (_text(news.get("source_name")) or "").casefold() == "gdelt")))
        if reported_dt is None and event_time is not None and not observed_fallback:
            reported_dt = event_time
        reported_kind = "SOURCE_DATE_PROXY" if reported_dt and is_proxy_date else ("REPORTED_TIME" if reported_dt else "UNKNOWN")
        raw_title = _raw_text(news.get("title"), news.get("headline_or_discovery_text"), news.get("headline_or_text"), news.get("headline"))
        raw_summary = _raw_text(news.get("summary"), news.get("headline_or_discovery_text"), news.get("headline_or_text"))
        source_url = _text(news.get("source_url"), news.get("url"))
        if not _valid_url(source_url):
            source_url = None
        source_name = _text(news.get("source_publisher"), news.get("source_name"), news.get("source_provider"))
        article_reference = _text(news.get("article_reference"), news.get("source_item_reference"), news.get("item_reference"), discovery_id) or source_url
        macro = macro_by_ref.get(discovery_id) if official and discovery_id else None
        if macro and (not official.get("artifact_fingerprint") or macro.get("event_reality_reference") != official["artifact_fingerprint"]):
            macro = None
        expectation = expectations.get(discovery_id) if discovery_id else None
        family = _text(news.get("provisional_event_family"), news.get("event_family"))
        items.append({
            "event_id": canonical_id,
            "identity_status": identity_status,
            "identity_evidence_ref": identity_ref if identity_status == "VERIFIED_BY_SOURCE" else None,
            "discovery_record_id": discovery_id,
            "article_reference": article_reference,
            "title": normalize_news_text(raw_title),
            "news_summary": normalize_news_text(raw_summary),
            "raw_title": raw_title,
            "raw_news_summary": raw_summary,
            "event_family": family,
            "event_family_status": "PROVISIONAL" if family else "UNKNOWN",
            "observed_at": _iso(observed_at),
            "reported_at": _iso(reported_dt),
            "reported_time_kind": reported_kind,
            "discovered_at": _iso(observed_at),
            "event_occurred_at": official["event_occurred_at"] if official else None,
            "verification_status": verification,
            "news_source": {"name": source_name, "url": source_url, "published_at": _iso(_utc(_text(news.get("source_published_at"), news.get("source_published_at_utc"))))},
            "official_evidence": official,
            "macroview_status": "AVAILABLE" if macro else ("NOT_CONFIGURED" if paths.macroview is None else sources["macroview"]["status"]),
            "expectation_status": _text(expectation.get("expectation_state"), expectation.get("linkage_state")) if expectation else None,
            "geography": None,
            "geography_status": "UNKNOWN",
        })
    items.sort(key=_feed_order_key, reverse=True)
    source_health, last_update = _health_rows(health_rows, current, stale_after_seconds)
    observed_values = [_utc(row.get("observed_time")) for row in raw_news_rows]
    observed_values = [value for value in observed_values if value is not None]
    latest_observed = _iso(max(observed_values)) if observed_values else None
    canonical_events = build_canonical_events(items)
    official_projection = build_official_evidence_projection(official_rows, items, canonical_events["events"])
    official_projection["events"] = build_event_timelines(items, official_projection["official_evidence"], official_projection["events"])
    geography_metadata = None
    geography_metadata_status = "NOT_CONFIGURED"
    if paths.geography is not None:
        try:
            records = _read_rows(paths.geography)
            if (len(records) != 1 or not isinstance(records[0], dict)
                    or records[0].get("schema") != "EVENT_GEOGRAPHY_METADATA_V1"
                    or records[0].get("presentation_only") is not True
                    or not isinstance(records[0].get("events"), dict)):
                raise EvidenceReadError("GEOGRAPHY_METADATA_INVALID")
            geography_metadata = records[0]
            geography_metadata_status = "AVAILABLE"
        except EvidenceReadError:
            geography_metadata_status = "UNAVAILABLE"
    geography_projection = build_event_geographies(official_projection["events"], geography_metadata)
    from tools.stage1b_historical_campaign.radar_market_expectations import parse_markets, ExpectationError
    expectation_rows = []
    for row in poly_rows[:20]:
        try:
            expectation_rows.extend(parse_markets(row, row.get("observed_at") or row.get("retrieved_at")))
        except ExpectationError:
            continue
    expectation_projection = project_market_records(geography_projection["events"], expectation_rows, paths.expectation_links)
    from tools.stage1b_historical_campaign.radar_context_intelligence import enrich_events
    expectation_projection['events'] = enrich_events(expectation_projection['events'], items)
    status = "AVAILABLE" if items else "EMPTY"
    view = {
        "contract_version": CONTRACT_VERSION, "read_only": True, "status": status,
        "reason": None if items else "NO_NEWS_DISCOVERY_RECORDS",
        "items": items, "item_count": len(items), "news_item_count": len(items), **canonical_events,
        **official_projection, **geography_projection, **expectation_projection,
        "geography_metadata_status": geography_metadata_status,
        "latest_observed_data_at": latest_observed,
        "last_successful_update": last_update,
        "health_status": _overall_health(source_health, news_rows),
        "source_health": source_health, "sources": sources,
    }
    from tools.stage1b_historical_campaign.radar_market_reality import add_projection
    return add_projection(view, paths.market_reality, as_of=_iso(current))


def build_event_geographies(events: list[dict[str, Any]], metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """V1 accepts explicit curator-supplied presentation points only.

    Current News/RSS and Official contracts contain no authoritative coordinates.
    Never use a headline, publisher, instrument or country keyword to locate an event.
    Validation checks the declared metadata's shape, not geographical factual truth;
    CURATED_PRESENTATION is always disclosed and cannot affect verification.
    """
    configured = (metadata.get("events", {}) if isinstance(metadata, dict)
                  and metadata.get("schema") == "EVENT_GEOGRAPHY_METADATA_V1"
                  and metadata.get("presentation_only") is True else {})
    if not isinstance(configured, dict):
        configured = {}
    enriched = []
    for event in events:
        points = {}
        rows = configured.get(event["event_id"], [])
        if not isinstance(rows, list) or len(rows) > 16:
            rows = []
        for row in rows:
            if not isinstance(row, dict) or row.get("evidence_type") != "CURATED_PRESENTATION":
                continue
            place, reference = _text(row.get("place_name")), _text(row.get("evidence_reference"))
            country = row.get("country_code")
            latitude, longitude = row.get("latitude"), row.get("longitude")
            if (not place or len(place) > 200 or not reference or len(reference) > 1000
                    or not _valid_url(reference)
                    or (country is not None and (not isinstance(country, str) or not re.fullmatch(r"[A-Z]{2}", country)))
                    or type(latitude) not in (int, float) or type(longitude) not in (int, float)
                    or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
                    or not math.isfinite(latitude) or not math.isfinite(longitude)):
                continue
            point = {"place_name": place, "country_code": country,
                "latitude": float(latitude) if latitude else 0.0,
                "longitude": float(longitude) if longitude else 0.0,
                "evidence_type": "CURATED_PRESENTATION", "evidence_reference": reference}
            encoded = json.dumps(["EVENT_GEOGRAPHY_V1", event["event_id"], point],
                                 sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            identity = "event-geography-v1-" + hashlib.sha256(encoded).hexdigest()
            points[identity] = {"geography_id": identity, **point}
        enriched.append({**event, "geography_status": "KNOWN" if points else "UNKNOWN",
                         "geography": [points[key] for key in sorted(points)] if points else None})
    mapped = sum(event["geography_status"] == "KNOWN" for event in enriched)
    return {"events": enriched, "geography_contract": "EVENT_GEOGRAPHY_V1",
            "mapped_event_count": mapped, "unmapped_event_count": len(enriched) - mapped}


def build_event_timelines(items: list[dict[str, Any]], evidence: list[dict[str, Any]],
                          events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Presentation-only chronology from explicit V0 membership, never new links.

    Reported time requires REPORTED_TIME. Proxy dates are not publication.
    Missing times stay null and sort last. IDs depend on event/type/source identity,
    not timestamps or ordering. Current status is a summary, not a dated entry.
    """
    articles: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        reference = _text(item.get("article_reference"))
        if reference:
            articles.setdefault(reference, []).append(item)
    official: dict[str, list[dict[str, Any]]] = {}
    for record in evidence:
        identity = _text(record.get("official_evidence_id"))
        if identity:
            official.setdefault(identity, []).append(record)

    def timestamp(record: Mapping[str, Any], fields: list[tuple[str, str]]) -> tuple[str | None, str]:
        for field, role in fields:
            value = record.get(field)
            if _utc(value) is not None:
                return value, role
        return None, "UNKNOWN"

    def entry_id(event_id: str, kind: str, identity: str) -> str:
        encoded = json.dumps(["EVENT_TIMELINE_V1", event_id, kind, identity], ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8")
        return "event-timeline-v1-" + hashlib.sha256(encoded).hexdigest()

    enriched = []
    for event in events:
        entries = []
        event_id = event["event_id"]
        for reference in sorted(set(event.get("article_references") or [])):
            copies = articles.get(reference, [])
            if not copies:
                continue
            # Same conflict rule as Canonical V0. Ambiguous copies cannot add a story.
            signatures = {(i.get("title"), i.get("reported_at"), i.get("reported_time_kind"),
                           (i.get("news_source") or {}).get("name")) for i in copies}
            if len(signatures) != 1:
                continue
            item = dict(min(copies, key=lambda i: json.dumps(i, sort_keys=True, ensure_ascii=False)))
            observations = [_utc(i.get("observed_at")) for i in copies]
            observations = [value for value in observations if value is not None]
            if observations:
                item["observed_at"] = _iso(min(observations))
            fields = [("reported_at", "REPORTED_AT")] if item.get("reported_time_kind") == "REPORTED_TIME" else []
            moment, role = timestamp(item, fields + [("observed_at", "OBSERVED_AT"), ("discovered_at", "OBSERVED_AT")])
            source = item.get("news_source") or {}
            entries.append({"timeline_entry_id": entry_id(event_id, "NEWS_DISCOVERED", reference),
                "entry_type": "NEWS_DISCOVERED", "timestamp": moment, "timestamp_role": role,
                "title": item.get("title"), "source_name": source.get("name"),
                "source_url": source.get("url"), "article_reference": reference,
                "observed_at": item.get("observed_at"), "status": "UNVERIFIED_NEWS"})
        for identity in sorted(set(event.get("official_evidence_ids") or [])):
            copies = official.get(identity, [])
            # An identity with conflicting copies must never select a convenient record.
            unique = {json.dumps(record, sort_keys=True, ensure_ascii=False) for record in copies}
            if len(unique) != 1:
                continue
            record = copies[0]
            if (record.get("canonical_event_id") != event_id
                    or record.get("evidence_status") != "OFFICIAL_CONFIRMED"
                    or not _text(record.get("fact_proposition"))):
                continue
            moment, role = timestamp(record, [("published_at", "EVIDENCE_PUBLISHED_AT"),
                ("first_seen_at", "EVIDENCE_FIRST_SEEN_AT"), ("retrieved_at", "EVIDENCE_RETRIEVED_AT")])
            entries.append({"timeline_entry_id": entry_id(event_id, "OFFICIAL_EVIDENCE", identity),
                "entry_type": "OFFICIAL_EVIDENCE", "timestamp": moment, "timestamp_role": role,
                "title": record.get("fact_proposition"), "source_name": record.get("authority_name"),
                "source_url": record.get("document_url"), "official_evidence_id": identity,
                "published_at": record.get("published_at"), "status": "OFFICIAL_CONFIRMED"})
        maximum = datetime.max.replace(tzinfo=timezone.utc)
        priority = {"NEWS_DISCOVERED": 0, "OFFICIAL_EVIDENCE": 1}
        entries.sort(key=lambda entry: (entry["timestamp"] is None, _utc(entry["timestamp"]) or maximum,
                                        priority[entry["entry_type"]], entry["timeline_entry_id"]))
        news_count = sum(entry["entry_type"] == "NEWS_DISCOVERED" for entry in entries)
        official_count = sum(entry["entry_type"] == "OFFICIAL_EVIDENCE" for entry in entries)
        enriched.append({**event, "timeline_contract": "EVENT_TIMELINE_V1", "timeline": entries,
            "timeline_count": len(entries), "status_summary": {
                "verification_status": event.get("verification_status"),
                "news_article_count": news_count, "official_evidence_count": official_count}})
    return enriched


def _overall_health(rows: list[dict[str, Any]], news_rows: list[dict[str, Any]]) -> str:
    required: set[str] = set()
    for row in news_rows:
        name = _text(row.get("source_name"), row.get("source_publisher"), row.get("source_provider"))
        if not name:
            return "UNKNOWN"
        required.add(name.casefold())
    if not required:
        return "UNKNOWN"
    by_source = {(_text(row.get("source")) or "").casefold(): row.get("status") for row in rows}
    if not required.issubset(by_source):
        return "UNKNOWN"
    states = {by_source[name] for name in required}
    if "STALE" in states:
        return "STALE"
    return "FRESH" if states == {"FRESH"} else "UNKNOWN"


def project_market_records(events, records, links_path=None):
    """Exact curated links only; optional-input failure cannot suppress News."""
    from tools.stage1b_historical_campaign.radar_market_expectations import project_expectations
    mapping = None
    unavailable = False
    if links_path is not None:
        try:
            rows = _read_rows(links_path)
            if len(rows) != 1 or rows[0].get("schema") != "EXACT_MARKET_LINKS_V1":
                raise EvidenceReadError("INVALID_EXPECTATION_LINKS")
            mapping = rows[0].get("event_to_market")
            if not isinstance(mapping, dict):
                raise EvidenceReadError("INVALID_EXPECTATION_LINKS")
        except EvidenceReadError:
            unavailable = True
    result = project_expectations(events, records, mapping)
    if unavailable:
        result["expectation_link_status"] = "UNAVAILABLE"
    return result
