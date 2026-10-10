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

def project(view, *, now=None):
    f = (view.get("news_freshness") if now is None else None) or freshness(view, now=now)
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
        cards[ref] = dict(article_reference=ref, canonical_event_id=(event or {}).get('event_id'),
            macro_relevant=relevant, topic=topics[0][0] if topics else 'UNKNOWN',
            matched_terms=[m.group() for t in topics for m in re.finditer(t[1], title, re.I)],
            relevance_en=topics[0][2] if topics else None, relevance_zh=topics[0][3] if topics else None,
            context_en=explanation.get('explanation_en'), context_zh=explanation.get('explanation_zh'),
            interpretation_role='PRESENTATION_ONLY_POTENTIAL_MECHANISM',
            official_evidence_ids=evidence, official_evidence_count=len(evidence),
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
