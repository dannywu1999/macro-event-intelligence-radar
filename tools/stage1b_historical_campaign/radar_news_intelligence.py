"""Read-only News presentation. Reuses source relevance, context and canonical proof.

No article translation, importance score, world-event clustering or truth promotion.
Publication is the sole brief clock. A new topic development is never topic-deduped.
"""
from itertools import combinations
import re
from urllib.parse import urlsplit
from tools.stage1b_historical_campaign.broad_news_ingestion import macro_relevant_title
from tools.stage1b_historical_campaign.global_event_radar_read_adapter import canonical_merge_evidence
from tools.stage1b_historical_campaign.radar_news_freshness import project as freshness

# Terminology hints only: not article translations, impact estimates or recommendations.
TOPICS = (
 ('TRADE_POLICY', r"\b(tariffs?|sanctions?|reciprocal trade|export controls?|trade agreements?|trade deal|embargo)\b", 'Trade restrictions can affect costs and supply chains; the magnitude and direction remain unverified.', '貿易限制可能影響成本與供應鏈；幅度及方向仍待查證。'),
 ('ENERGY', r"\b(oil|crude|energy|refiner\w*|pipelines?|natural gas)\b", 'Energy supply and infrastructure can affect input costs; this headline does not prove a price impact.', '能源供給與基礎設施可能影響投入成本；標題本身不證明價格影響。'),
 ('MONETARY_POLICY', r"\b(central bank|federal reserve|fomc|interest rates?|monetary policy|rate cuts?|rate hikes?)\b", 'Policy and financing conditions may be relevant; confirm the actual decision in the original document.', '政策與融資條件可能相關；實際決議須核對原始文件。'),
 ('ECONOMIC_DATA', r"\b(inflation|unemployment|employment|payroll|gdp|recession|food security)\b", 'Economic activity and household costs may warrant investigation; data definitions and results need verification.', '經濟活動與民生成本值得查核；數據定義及結果仍須驗證。'),
 ('TECH_SUPPLY_CHAIN', r"\b(semiconductors?|chips?|military affiliate|alibaba|nvidia)\b", 'Technology supply chains and regulatory exposure may be relevant; effects on specific firms are not established.', '科技供應鏈與監管曝險可能相關；個別企業所受影響尚未確立。'),
 ('GEOPOLITICS', r"\b(war|ceasefire|invasion|airstrikes?|missiles?|military|blockade|coup)\b", 'Conflict can affect logistics and risk perceptions; verify what occurred and its scope.', '衝突可能影響物流與風險認知；發生事實與範圍仍須查證。'),
 ('POLICY_AND_SYSTEMIC_RISK', r"\b(elections?|government|budget|debt|financial crisis|bank failures?|capital controls|liquidity)\b", 'Policy or financial conditions may change; this is a topic hint, not a demonstrated market effect.', '政策或金融條件可能改變；這是主題提示，並非已證實的市場效果。'),
 ('DISASTER', r"\b(earthquake|hurricane|flooding|famine|disaster)\b", 'Disruptions may affect infrastructure or supply; locations and economic effects require evidence.', '災害可能影響基礎設施與供給；地點及經濟效果仍須證據。'),
)

def provenance(article):
    source = article.get('news_source') or {}
    try:
        url = urlsplit(source.get('url') or '')
        return bool(article.get('title') and source.get('name') and url.scheme in {'http', 'https'} and url.hostname and not url.username and not url.password)
    except ValueError:
        return False

def project(view, *, now=None, research_library=None):
    f = (view.get("news_freshness") if now is None else None) or freshness(view, now=now)
    if research_library is None:
        from tools.stage1b_historical_campaign.radar_market_reaction import load_research_library
        research_library = load_research_library()
    articles = {a['article_reference']: a for a in view.get('items', []) if a.get('article_reference')}
    events = view.get('events', [])
    memberships = {ref: [e for e in events if ref in e.get('article_references', [])] for ref in articles}
    cards, related = {}, []
    for ref, article in articles.items():
        matches = memberships[ref]
        event = matches[0] if len(matches) == 1 else None
        title = article.get('title') or ''
        topics = [t for t in TOPICS if re.search(t[1], title, re.I)]
        institutions = {str(i.get('institution_id') or '').upper() for i in (event or {}).get('institution_context', [])}
        # Reuse existing curated institution context; it is not factual authority.
        if not topics and 'ECB' in institutions: topics = [TOPICS[2]]
        if not topics and 'EIA' in institutions: topics = [TOPICS[1]]
        relevant = bool(macro_relevant_title(title) or institutions.intersection({'EIA', 'ECB'}))
        evidence = [e['official_evidence_id'] for e in view.get('official_evidence', [])
                    if event and e.get('official_evidence_id') in event.get('official_evidence_ids', [])
                    and e.get('canonical_event_id') == event.get('event_id')
                    and e.get('evidence_status') == 'OFFICIAL_CONFIRMED'
                    and isinstance(e.get('fact_proposition'), str) and e['fact_proposition'].strip()]
        explanation = (event or {}).get('headline_explanation') or {}
        linked_official = [e for e in view.get('official_evidence', [])
            if event and e.get('official_evidence_id') in event.get('official_evidence_ids', [])
            and e.get('canonical_event_id') == event.get('event_id')
            and e.get('evidence_status') == 'OFFICIAL_CONFIRMED'
            and isinstance(e.get('fact_proposition'), str) and e['fact_proposition'].strip()]
        # Historical ECB cases are offered only for an explicit monetary-policy
        # title plus an ECB identity. Topic similarity alone never merges events.
        policy_action = is_ecb_decision(article, institutions)
        research_cases = (research_library or {}).get('cases', [])
        analogue_ids = ([c.get('research_case_id') for c in research_cases
                         if c.get('status') == 'AVAILABLE' and c.get('receipt')]
                        if event and policy_action else [])
        source_name = (article.get('news_source') or {}).get('name')
        provider_name = (f.get('attribution', {}).get(ref) or {}).get('source') or source_name
        source_state = (view.get('discovery_sources') or {}).get(provider_name, {})
        if not source_state:
            source_state = (view.get('sources') or {}).get(source_name, {})
        if any(e.get('link_status') == 'CONFLICTING_EVIDENCE_COPIES' for e in linked_official):
            verification_status = 'CONFLICTING_EVIDENCE'
        elif linked_official:
            verification_status = 'OFFICIAL_PARTIAL'
        else:
            verification_status = 'SOURCE_REPORTED_ONLY' if provenance(article) else 'NOT_VERIFIED'
        cards[ref] = dict(article_reference=ref, canonical_event_id=(event or {}).get('event_id'),
            macro_relevant=relevant, topic=topics[0][0] if topics else 'UNKNOWN',
            matched_terms=[m.group() for t in topics for m in re.finditer(t[1], title, re.I)],
            relevance_en=topics[0][2] if topics else None, relevance_zh=topics[0][3] if topics else None,
            context_en=explanation.get('explanation_en'), context_zh=explanation.get('explanation_zh'),
            interpretation_role='PRESENTATION_ONLY_POTENTIAL_MECHANISM',
            official_evidence_ids=evidence, official_evidence_count=len(evidence),
            event_triage=dict(contract='NEWS_EVENT_RESEARCH_BRIDGE_V1',
                event_identity_status='CANONICAL_EVENT' if event else 'NO_UNAMBIGUOUS_CANONICAL_EVENT',
                canonical_event_id=(event or {}).get('event_id'), original_headline=title,
                publisher=source_name, source_url=(article.get('news_source') or {}).get('url'),
                publication_time=f['published_at'].get(ref),
                publication_time_precision=article.get('publication_precision') or 'UNKNOWN',
                publication_time_basis=article.get('reported_time_kind') or 'UNKNOWN',
                first_observed_at=(article.get('observed_at') or article.get('discovered_at')) if article.get('observation_time_basis') == 'FIRST_RECORDED_SOURCE_OBSERVATION' else None,
                clocks=research_clocks(article, source_state),
                prospective_evidence=article.get('prospective_evidence') or dict(status='NOT_RECORDED', recorded_at=None, replay_available=False),
                current_market_observation_status='MARKET_OBSERVATION_NOT_AVAILABLE',
                preview_authority='NON_AUTHORITATIVE_PREVIEW',
                latest_provider_check_at=source_state.get('last_attempt_at') or source_state.get('last_success_at'),
                latest_provider_status=source_state.get('status') or 'UNKNOWN',
                verification_status=verification_status,
                official_scope='PARTIAL_ARTICLE_COVERAGE;EACH_FACT_PROPOSITION_SCOPED' if linked_official else 'NO_PROPOSITION_LINKED',
                official_propositions=[dict(official_evidence_id=e.get('official_evidence_id'),
                    authority_name=e.get('authority_name'), fact_proposition=e.get('fact_proposition'),
                    document_url=e.get('document_url'), document_title=e.get('document_title'),
                    published_at=e.get('published_at'), first_seen_at=e.get('first_seen_at'),
                    retrieved_at=e.get('retrieved_at'), match_rationale='DIRECT_CANONICAL_EVENT_AND_EVIDENCE_ID_LINK')
                    for e in linked_official],
                research_relation='SAME_POLICY_TOPIC' if analogue_ids else 'NO_VALID_HISTORICAL_ANALOGUE',
                research_case_ids=analogue_ids,
                market_observation_status='HISTORICAL_ECB_DAILY_REFERENCE_AVAILABLE' if analogue_ids else 'MARKET_OBSERVATION_NOT_AVAILABLE',
                market_observation_case_ids=analogue_ids,
                causality_status='NOT_ESTABLISHED', point_in_time_status='REQUIRES_GENUINE_RECORDED_HISTORY'),
            novelty_status='NOT_ESTABLISHED', published_at=f['published_at'].get(ref),
            recency=f['article_recency'].get(ref), provenance_valid=provenance(article))
    # Reconstruct the SAME conservative adapter primitive. Country/topic matches never merge.
    proven_groups = set()
    for event in events:
        refs = event.get('article_references', [])
        members = [articles[r] for r in refs if r in articles]
        if len(refs) > 1 and len(set(refs)) == len(refs) == len(members) and all(len(memberships[r]) == 1 for r in refs) and all(canonical_merge_evidence(a,b)['merge'] for a,b in combinations(members,2)):
            proven_groups.add(event['event_id'])
            related.append(dict(canonical_event_id=event['event_id'], article_references=sorted(refs, key=lambda r:(f['published_at'].get(r) or '',r)), rule='EXPLICIT_RATE_DECISION_SAME_DAY_6H_V0'))
    eligible = [c for c in cards.values() if c['macro_relevant'] and c['provenance_valid'] and c['recency'] in {'LAST_24H','LAST_48H'}]
    eligible.sort(key=lambda c:(c['published_at'], bool(c['official_evidence_count']), c['article_reference']), reverse=True)
    brief, seen = [], set()
    for card in eligible:
        key = card['canonical_event_id'] if card['canonical_event_id'] in proven_groups else card['article_reference']
        if key in seen: continue
        seen.add(key)
        if len(brief) < 5: brief.append(card['article_reference'])
    return dict(contract='NEWS_INTELLIGENCE_V1', as_of=f['as_of'], window_hours=48,
        selection_rule='KNOWN_PUBLICATION_LAST_48H_MACRO_TOPIC_PROVENANCE_THEN_NEWEST;OFFICIAL_EVIDENCE_BREAKS_TIME_TIES;PROVEN_CANONICAL_GROUPS_ONLY',
        cards=cards, brief_article_references=brief, eligible_article_count=len(eligible),
        eligible_development_count=len(seen), related_coverage=related,
        macro_relevant_last_24h=sum(c['macro_relevant'] and c['provenance_valid'] and c['recency']=='LAST_24H' for c in cards.values()),
        unknown_analysis_count=sum(c['relevance_en'] is None for c in cards.values()))


# V4.6 extends the existing News projection and opt-in ledger. No workers or
# storage are created by importing this module or rendering a research card.
def is_ecb_decision(article, institutions=()):
    """Explicit reported action, never a meeting, forecast or implementation review."""
    title = article.get('title') or ''
    url = (article.get('news_source') or {}).get('url') or ''
    actor = 'ECB' in institutions or bool(re.search(r'\b(?:ECB|European Central Bank)\b', title, re.I))
    if re.search(r'\b(?:meeting|minutes|accounts|interview|speech|outlook|forecast|expect\w*|preview|guidelines?|implementation|diagnostic|review|scheduled|will|may|could|should)\b', title, re.I):
        return False
    if re.search(r'/press/(?:key|inter|accounts|govcdec)/', url):
        return False
    action = re.search(r'\b(?:cuts?|lowers?|reduces?|raises?|hikes?|holds?|keeps?|maintains?|announces?)\b.{0,48}\b(?:rates?|rate decision)\b', title, re.I)
    explicit_document = title.strip().casefold() == 'monetary policy decisions' and urlsplit(url).hostname == 'www.ecb.europa.eu' and '/press/pr/' in url
    return bool(actor and action or explicit_document)


def metadata_content(article):
    """Only title/source/time metadata; excludes summaries and full article bodies."""
    from copy import deepcopy
    return {key: deepcopy(article.get(key)) for key in (
        'article_reference', 'title', 'news_source', 'reported_at',
        'reported_time_kind', 'observed_at', 'discovered_at', 'verification_status')}


def metadata_hash(article):
    from .radar_intelligence_store import canonical, sha
    return sha(canonical(metadata_content(article)))


def research_clocks(article, source_state):
    """Independent clocks. Upstream observation is never local ledger registration."""
    from .radar_news_freshness import timestamp
    published = article.get('reported_at') if article.get('reported_time_kind') in {'REPORTED_TIME', 'SOURCE_REPORTED_TIME'} else None
    observed = article.get('observed_at') or article.get('discovered_at')
    publication_dt, observation_dt = timestamp(published), timestamp(observed)
    # Only an explicit first-observation contract can establish detection latency.
    verified_first = article.get('observation_time_basis') == 'FIRST_RECORDED_SOURCE_OBSERVATION'
    latency = (observation_dt - publication_dt).total_seconds() if verified_first and publication_dt and observation_dt and observation_dt >= publication_dt else None
    detection = article.get('detection_evidence')
    if detection is not None:
        latency = detection.get('source_to_observation_delay_seconds')
        verified_first = bool(detection.get('first_observed_proven'))
    capture = article.get('prospective_evidence') or {}
    return dict(source_published_at=published, upstream_observed_at=observed,
                first_observed_at=observed if verified_first else None,
                first_observed_basis=article.get('observation_time_basis') or 'UPSTREAM_OBSERVATION;FIRST_OBSERVATION_NOT_PROVEN',
                recorded_at=capture.get('recorded_at'), retrieval_time=capture.get('retrieval_time'),
                last_provider_check_at=source_state.get('last_attempt_at'),
                last_successful_provider_check_at=source_state.get('last_success_at'),
                displayed_at=None, displayed_at_basis='BROWSER_RENDER_CLOCK',
                discovery_latency_seconds=latency,
                discovery_latency_status='MEASURED' if latency is not None else 'UNKNOWN')


def capture_snapshot(snapshot_bytes, retrieval_receipt, selected_refs, pilot_root):
    """Explicit one-shot local capture into a NEW isolated store; no freeze/write API.

    Source clocks stay inside the payload. Ledger registration uses the actual
    local wall clock. A receipt binds the supplied public snapshot bytes; it is
    an acquisition record, not an independent truth certification.
    """
    import json
    from pathlib import Path
    from copy import deepcopy
    from .radar_intelligence_store import IntelligenceStore, StoreError, canonical, sha, now, time_value
    from .global_event_radar_read_adapter import build_canonical_events
    from .radar_reality_replay import replay_event_as_of
    from .radar_macroview_freeze import preview_macroview
    if len(snapshot_bytes) > 2 * 1024 * 1024:
        raise StoreError('PILOT_SNAPSHOT_TOO_LARGE')
    if not isinstance(selected_refs, list) or not 1 <= len(selected_refs) <= 8 or len(set(selected_refs)) != len(selected_refs):
        raise StoreError('PILOT_SELECTION_REQUIRED')
    if retrieval_receipt.get('http_status') != 200 or retrieval_receipt.get('sha256') != __import__('hashlib').sha256(snapshot_bytes).hexdigest():
        raise StoreError('PILOT_RETRIEVAL_HASH_MISMATCH')
    retrieval_time = time_value(retrieval_receipt.get('retrieved_at'))[0]
    recorded_at = now()
    if time_value(retrieval_time)[1] > time_value(recorded_at)[1]:
        raise StoreError('PILOT_FUTURE_RETRIEVAL')
    view = json.loads(snapshot_bytes)
    selected = [a for a in view.get('items', []) if a.get('article_reference') in selected_refs]
    if len(selected) != len(selected_refs) or not all(provenance(a) for a in selected):
        raise StoreError('PILOT_GENUINE_PROVENANCE_REQUIRED')
    # Reuse the existing deterministic article-set identity, and require the
    # supplied projection to agree. Do not manufacture real-world event identity.
    derived = build_canonical_events(view.get('items', []))
    by_ref = {}
    for event in derived['events']:
        for ref in event['article_references']:
            by_ref[ref] = event['event_id']
    events = [deepcopy(e) for e in view.get('events', []) if set(e.get('article_references', [])).intersection(selected_refs)]
    for event in events:
        if any(by_ref.get(ref) != event.get('event_id') for ref in event['article_references']):
            raise StoreError('PILOT_CANONICAL_IDENTITY_MISMATCH')
        if not set(event['article_references']).issubset(selected_refs):
            raise StoreError('PILOT_COMPLETE_EVENT_MEMBERS_REQUIRED')
    event_ids = {e['event_id'] for e in events}
    if any(ref not in by_ref for ref in selected_refs) or set(by_ref[r] for r in selected_refs) != event_ids:
        raise StoreError('PILOT_CANONICAL_MEMBERSHIP_REQUIRED')
    root = Path(pilot_root).expanduser().resolve()
    package = Path(__file__).resolve().parents[2]
    if root.is_relative_to(package) or root.exists():
        raise StoreError('PILOT_NEW_EXTERNAL_DIRECTORY_REQUIRED')
    records, receipts = [], []
    triage = project(view, research_library={'cases': []})['cards']
    for original in selected:
        article = metadata_content(original)
        ref = article['article_reference']
        event_id = by_ref[ref]
        bridge = triage[ref]['event_triage']
        receipt = dict(contract='PROSPECTIVE_NEWS_RECEIPT_V1', scope='ISOLATED_LOCAL_PILOT',
                       canonical_event_id=event_id, identity_basis='CANONICAL_EVENT_V0_ARTICLE_SET;NOT_VERIFIED_REAL_WORLD_IDENTITY',
                       source_id=(view.get('news_freshness', {}).get('attribution', {}).get(ref) or {}).get('source') or article['news_source']['name'],
                       publisher=article['news_source']['name'], source_url=article['news_source']['url'],
                       source_publication_time=article['reported_at'], publication_precision=original.get('publication_precision') or 'UNKNOWN',
                       publication_time_basis=article['reported_time_kind'] or 'UNKNOWN',
                       upstream_observed_at=article['observed_at'] or article['discovered_at'],
                       first_observed_at=(article['observed_at'] or article['discovered_at']) if original.get('observation_time_basis') == 'FIRST_RECORDED_SOURCE_OBSERVATION' else None,
                       first_observed_basis=original.get('observation_time_basis') or 'UPSTREAM_OBSERVATION;FIRST_OBSERVATION_NOT_PROVEN',
                       recorded_at=recorded_at, retrieval_time=retrieval_time, retrieval_receipt=deepcopy(retrieval_receipt),
                       content_hash=metadata_hash(original), hash_scope='TITLE_SOURCE_TIME_METADATA_ONLY',
                       fact_status=bridge['verification_status'], official_propositions=deepcopy(bridge['official_propositions']),
                       evidence_version='metadata-sha256-'+metadata_hash(original), authoritative_frozen_macroview=False)
        receipt['receipt_id'] = 'prospective-news-v1-'+sha(canonical(receipt))
        receipts.append(receipt)
        records.append(dict(observation_kind='NEWS_ARTICLE', entity_id=ref, canonical_event_id=event_id,
                            source_timestamp=article['reported_at'], payload=article,
                            provenance={'time_basis': 'SYSTEM_RECORDED_TIME', 'research_receipt': receipt}))
    for event in events:
        records.append(dict(observation_kind='CANONICAL_EVENT_STATE', entity_id=event['event_id'], canonical_event_id=event['event_id'],
                            payload=event, provenance={'time_basis': 'SYSTEM_RECORDED_TIME', 'capture_scope': 'ISOLATED_LOCAL_PILOT'}))
    facts = [deepcopy(f) for f in view.get('official_evidence', []) if f.get('canonical_event_id') in event_ids
             and f.get('evidence_status') == 'OFFICIAL_CONFIRMED' and f.get('authority_role') == 'FACT_AUTHORITY'
             and any(f.get('official_evidence_id') in e.get('official_evidence_ids', []) for e in events if e['event_id'] == f.get('canonical_event_id'))
             and f.get('link_status') not in {'CONFLICTING_EVIDENCE_COPIES', 'UNLINKED'}]
    for fact in facts:
        records.append(dict(observation_kind='OFFICIAL_EVIDENCE',entity_id=fact['official_evidence_id'],canonical_event_id=fact['canonical_event_id'],source_timestamp=fact.get('published_at'),payload=fact,provenance={'time_basis':'SYSTEM_RECORDED_TIME','capture_scope':'ISOLATED_LOCAL_PILOT'}))
    # Validate every prospective record BEFORE creating any local capture files.
    from .radar_intelligence_store import validate_payload_time
    for row in records:
        validate_payload_time(row['observation_kind'], row['payload'], time_value(recorded_at)[1])
    root.mkdir(parents=True, exist_ok=False)
    store = IntelligenceStore(root/'evidence.sqlite3', create=True)
    inserted = store.append(records, observed_at=recorded_at)
    previews = []
    for event in events:
        replay = replay_event_as_of(store,event['event_id'],recorded_at,internal=True)
        if replay.get('_projection'):
            preview = preview_macroview(replay['_projection'],event['event_id'])
            previews.append(dict(recorded_at=recorded_at,canonical_event_id=event['event_id'],preview=preview))
    for receipt in receipts:
        with (root/(receipt['receipt_id']+'.json')).open('xb') as handle:
            handle.write((canonical(receipt)+'\n').encode('utf8'))
    result = dict(contract='PROSPECTIVE_CAPTURE_RESULT_V1', scope='ISOLATED_LOCAL_PILOT', recorded_at=recorded_at,
                  article_record_count=len(receipts), ledger_observation_count=len(inserted),
                  receipt_ids=[r['receipt_id'] for r in receipts], event_ids=sorted(event_ids),
                  preview_only=True, persisted_frozen_macroviews=0, previews=previews)
    with (root/'CAPTURE_RESULT.json').open('xb') as handle:
        handle.write((canonical(result)+'\n').encode('utf8'))
    return result


def attach_recording_status(view, store=None, *, as_of=None):
    """Read-only join. A current headline must match its captured metadata version."""
    from .radar_intelligence_store import now
    from copy import deepcopy
    result = deepcopy(view)
    as_of = as_of or now()
    latest = {}
    if store is not None:
        for event in result.get('events', []):
            for row in store.read_as_of(event['event_id'],as_of):
                if row['observation_kind'] == 'NEWS_ARTICLE':
                    key = row['entity_id']
                    if key not in latest or row['observed_us'] > latest[key]['observed_us']:
                        latest[key] = row
    for article in result.get('items', []):
        row = latest.get(article.get('article_reference'))
        state = dict(status='NOT_RECORDED', recorded_at=None, replay_available=False, authority='NON_AUTHORITATIVE_PREVIEW')
        if row:
            receipt = (row.get('provenance') or {}).get('research_receipt') or {}
            content_hash = receipt.get('content_hash') or metadata_hash(row['payload'])
            same = metadata_hash(article) == content_hash
            state.update(status=('RECORDED_LOCAL_PILOT' if receipt else 'RECORDED_EVIDENCE_LEDGER') if same else 'CAPTURED_EARLIER_VERSION',
                         recorded_at=row['observed_at'], retrieval_time=receipt.get('retrieval_time'),
                         receipt_id=receipt.get('receipt_id') or row['observation_id'], content_hash=content_hash,
                         evidence_version=receipt.get('evidence_version') or 'metadata-sha256-'+content_hash, replay_available=True,
                         scope='ISOLATED_LOCAL_PILOT' if receipt else 'EXISTING_INTELLIGENCE_LEDGER')
        article['prospective_evidence'] = state
    result['prospective_evidence_contract'] = 'PROSPECTIVE_NEWS_RECEIPT_V1'
    return result


def capture_main(argv=None):
    import argparse,json
    from pathlib import Path
    parser=argparse.ArgumentParser(description='One-shot isolated prospective metadata capture; no provider requests, workers or authoritative freeze.')
    parser.add_argument('--capture-snapshot',required=True)
    parser.add_argument('--retrieval-receipt',required=True)
    parser.add_argument('--pilot-root',required=True)
    parser.add_argument('--article',action='append',required=True)
    args=parser.parse_args(argv)
    result=capture_snapshot(Path(args.capture_snapshot).read_bytes(),json.loads(Path(args.retrieval_receipt).read_bytes()),args.article,args.pilot_root)
    print(json.dumps({k:result[k] for k in ['scope','recorded_at','article_record_count','ledger_observation_count','preview_only','persisted_frozen_macroviews']},ensure_ascii=True))


if __name__ == '__main__':
    capture_main()
