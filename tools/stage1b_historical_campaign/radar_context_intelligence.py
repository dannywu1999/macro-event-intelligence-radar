"""Deterministic presentation context. Never establishes factual event location.

Curated reference definitions are not active provider integrations. Coordinates
are approximate navigation anchors, not measured event coordinates. Replay must
use persisted event context; it must not call this module to enrich old history.
"""
from copy import deepcopy
import hashlib
import json
import re

CONTRACT = "EVENT_CONTEXT_V1"

def region(name, zh, kind, lat, lon, aliases):
    return dict(display_name=name, display_name_zh=zh, region_type=kind,
                centroid_lat=lat, centroid_lon=lon, aliases=aliases,
                coordinate_role="CONTEXT_ANCHOR")

REGIONS = {
    "united-states": region("United States", "美國", "COUNTRY", 39, -98, ["United States", "U.S.", "USA", "US", "America"]),
    "china": region("China", "中國", "COUNTRY", 35, 104, ["China", "Chinese", "中國"]),
    "taiwan": region("Taiwan", "臺灣", "COUNTRY_CONTEXT", 23.7, 121, ["Taiwan", "Taiwanese", "臺灣", "台灣"]),
    "japan": region("Japan", "日本", "COUNTRY", 36, 138, ["Japan", "Japanese", "日本"]),
    "united-kingdom": region("United Kingdom", "英國", "COUNTRY", 54, -2, ["United Kingdom", "UK", "英國"]),
    "euro-area": region("Euro Area", "歐元區", "JURISDICTION", 49, 10, ["euro area", "eurozone", "Eurosystem", "歐元區"]),
    "european-union": region("European Union", "歐盟", "JURISDICTION", 50, 12, ["European Union", "EU", "歐盟"]),
    "europe": region("Europe", "歐洲", "CONTINENT", 52, 15, ["Europe", "European", "歐洲"]),
    "middle-east": region("Middle East", "中東", "MACRO_REGION", 29, 44, ["Middle East", "中東"]),
    "iran": region("Iran", "伊朗", "COUNTRY", 32, 54, ["Iran", "Iranian", "伊朗"]),
    "red-sea": region("Red Sea", "紅海", "SEA", 20, 38, ["Red Sea", "紅海"]),
    "persian-gulf": region("Persian Gulf", "波斯灣", "SEA", 26, 52, ["Persian Gulf", "波斯灣"]),
    "taiwan-strait": region("Taiwan Strait", "臺灣海峽", "SEA", 24, 119, ["Taiwan Strait", "臺灣海峽", "台灣海峽"]),
    "south-china-sea": region("South China Sea", "南海", "SEA", 12, 114, ["South China Sea", "南海"]),
    "global": region("Global", "全球", "GLOBAL", None, None, ["global", "worldwide", "world", "全球"]),
}

INSTITUTIONS = {
    "ecb": dict(institution_id="ecb", short_name="ECB", official_name="European Central Bank",
        official_name_zh="歐洲中央銀行", institution_type="Central Bank", institution_type_zh="中央銀行",
        headquarters="Frankfurt, Germany", headquarters_zh="德國法蘭克福", jurisdiction="Euro Area",
        jurisdiction_zh="歐元區", jurisdiction_region_id="euro-area", relevant_currency="EUR / Euro",
        relevant_domain="Monetary policy", context_lat=50.11, context_lon=8.68,
        coordinate_role="INSTITUTION_HQ_ANCHOR", reference_url="https://www.ecb.europa.eu/ecb/html/index.en.html",
        metadata_role="CURATED_PRESENTATION_REFERENCE", active_integration_claim=False,
        aliases=["ECB", "European Central Bank", "Eurosystem", "歐洲中央銀行"]),
    "eia": dict(institution_id="eia", short_name="EIA", official_name="U.S. Energy Information Administration",
        official_name_zh="美國能源資訊署", institution_type="Government Energy Statistics Agency",
        institution_type_zh="政府能源統計機構", headquarters="Washington, DC, United States",
        headquarters_zh="美國華盛頓特區", jurisdiction="United States", jurisdiction_zh="美國",
        jurisdiction_region_id="united-states", relevant_currency=None, relevant_domain="Energy",
        context_lat=38.90, context_lon=-77.04, coordinate_role="INSTITUTION_HQ_ANCHOR",
        reference_url="https://www.eia.gov/about/", metadata_role="CURATED_PRESENTATION_REFERENCE",
        active_integration_claim=False, aliases=["EIA", "Energy Information Administration", "美國能源資訊署"]),
}
REGISTRY_FINGERPRINT = hashlib.sha256(json.dumps([REGIONS, INSTITUTIONS], sort_keys=True,
    ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

# Short English acronyms must be uppercase: 'us' is not a country mention.
def matches(text, alias):
    flags = 0 if alias in {"US", "UK", "EU", "USA"} else re.I
    if alias == "America" and re.search(r"(?:South|North|Latin|Central) America", text, re.I):
        return []
    pattern = r"(?<![\w])" + re.escape(alias) + r"(?![\w])"
    return [(m.start(), m.end(), m.group()) for m in re.finditer(pattern, text, flags)]


def mentions(text):
    candidates = []
    for identity, data in REGIONS.items():
        for alias in data["aliases"]:
            candidates.extend((start, end, identity, matched) for start, end, matched in matches(text, alias))
    # Longest phrase wins within overlapping spans (South China Sea != China).
    result = []; occupied = []
    for start, end, identity, matched in sorted(candidates, key=lambda r: (-(r[1]-r[0]), r[0], r[2])):
        if any(start < b and end > a for a, b in occupied):
            continue
        occupied.append((start, end)); result.append((identity, matched))
    return result


def unknown_context():
    return dict(status="UNKNOWN", region_type=None, region_id=None, display_name=None,
        display_name_zh=None, centroid_lat=None, centroid_lon=None, coordinate_role="CONTEXT_ANCHOR",
        method="UNKNOWN", confidence=None, reason="No supported geographic or institution mention.",
        reason_zh="沒有足以支持判斷的地名或機構資訊。", supporting_mentions=[], candidates=[])


def infer_context(event, articles):
    headline = event.get("event_title") or ""
    texts = [t[:8000] for t in list(dict.fromkeys([headline] + [a.get("title") or "" for a in articles]))[:32]]
    bodies = [t[:8000] for t in list(dict.fromkeys(a.get("summary") or a.get("body_text") or "" for a in articles))[:32]]
    headline_scores = {}; body_scores = {}; institution_scores = {}; evidence = []
    def record_text(text, role, scores):
        # Aliases and repetition within one text are one canonical region's
        # support, not additional independent evidence. Keep a matched phrase
        # for provenance; longest overlapping phrase selection still applies.
        seen = set()
        for identity, mention in mentions(text):
            if identity in seen:
                continue
            seen.add(identity)
            scores[identity] = scores.get(identity, 0) + 1
            evidence.append(dict(region_id=identity, mention=mention, evidence_role=role))
    for text in texts:
        record_text(text, "HEADLINE", headline_scores)
    for text in bodies:
        record_text(text, "BODY", body_scores)
    institutions = []
    source_names = event.get("source_names") or []
    for identity, reference in INSTITUTIONS.items():
        found = any(matches(text, alias) for text in texts+bodies for alias in reference["aliases"])
        source_found = any(matches(name, alias) for name in source_names for alias in reference["aliases"])
        if not (found or source_found): continue
        institution = deepcopy(reference); institution.pop("aliases")
        institution["recognition_method"] = "INSTITUTION_MENTION" if found else "SOURCE_INSTITUTION_REFERENCE"
        institutions.append(institution)
        jurisdiction = reference["jurisdiction_region_id"]
        institution_scores[jurisdiction] = institution_scores.get(jurisdiction, 0) + 1
        evidence.append(dict(region_id=jurisdiction, mention=reference["short_name"],
                             evidence_role=institution["recognition_method"]))
    # Compare support only inside the strongest available evidence tier.
    # Body repetition and institution metadata cannot change a headline tie,
    # erase explicit Europe/Global, or upgrade an institution into event location.
    scores = headline_scores or body_scores or institution_scores
    explicit_support = bool(headline_scores or body_scores)
    context = unknown_context()
    if scores:
        highest = max(scores.values()); winners = sorted(k for k,v in scores.items() if v==highest)
        specificity={'SEA':0,'COUNTRY':1,'COUNTRY_CONTEXT':1,'JURISDICTION':2,'MACRO_REGION':3,'CONTINENT':4,'GLOBAL':5}
        if explicit_support:
            # More specific equally supported text retains the existing sea /
            # broad-region behavior. An institution cannot participate in this.
            rank=min(specificity[REGIONS[k]['region_type']] for k in winners)
            winners=[k for k in winners if specificity[REGIONS[k]['region_type']]==rank]
        if len(winners)>1:
            context.update(status="MULTI_REGION", method="MULTI_REGION", confidence="LOW",
                reason="Equally supported regions; no single location is asserted.",
                reason_zh="多個區域具有相同支持程度，不宣稱單一事件位置。", candidates=winners,
                supporting_mentions=evidence)
        else:
            identity = winners[0]; data = REGIONS[identity]
            context.update({k:deepcopy(v) for k,v in data.items() if k!="aliases"})
            headline_support = identity in headline_scores
            context.update(status="INFERRED", region_id=identity,
                method="EXPLICIT_CONTEXT_MENTION" if explicit_support else "INSTITUTION_JURISDICTION",
                confidence="HIGH" if headline_support else "MEDIUM" if explicit_support or any(i['recognition_method']=='INSTITUTION_MENTION' for i in institutions) else "LOW",
                reason="Explicit text supports this broad context; not an event location." if explicit_support else "Recognized institution jurisdiction; not an event location.",
                reason_zh="文字支持此廣域脈絡，並非事件發生位置。" if explicit_support else "依辨識出的機構管轄範圍推定，並非事件發生位置。",
                supporting_mentions=evidence, candidates=[])
    explanation = dict(method="HEADLINE_CONTEXT_SUMMARY", explanation_en=None, explanation_zh=None,
        supporting_references=list(event.get("article_references") or []), authority_role="PRESENTATION_ONLY")
    ids = {i['institution_id'] for i in institutions}
    if 'ecb' in ids and re.search(r"monetary policy",headline,re.I) and re.search(r"guidelines",headline,re.I) and re.search(r"amend|review",headline,re.I):
        explanation.update(method="CURATED_ECB_IMPLEMENTATION_GUIDELINES",
            explanation_en="This headline concerns operational guidelines for implementing Eurosystem monetary policy. The headline itself is not an interest-rate decision.",
            explanation_zh="這則標題涉及歐元體系實施貨幣政策的操作指引；標題本身不是升息或降息決議。")
    elif institutions:
        institution=institutions[0]
        explanation.update(explanation_en="Discovery from or about "+institution['official_name']+", a "+institution['institution_type']+" serving "+institution['jurisdiction']+". Read the original headline and evidence for the specific claim.",
            explanation_zh="這是來自或涉及"+institution['official_name_zh']+"的新聞 discovery；該機構是"+institution['institution_type_zh']+"，主要範圍為"+institution['jurisdiction_zh']+"。具體命題請以原文及證據為準。")
    return context, institutions, explanation


def enrich_events(events, items):
    by_ref={item.get('article_reference'):item for item in items}
    result=[]
    for original in events:
        event=deepcopy(original)
        articles=[by_ref[ref] for ref in event.get('article_references',[]) if ref in by_ref]
        context,institutions,explanation=infer_context(event,articles)
        # Existing CURATED_PRESENTATION coordinates do not establish event location.
        strict=[deepcopy(p) for p in (event.get('geography') or []) if p.get('evidence_type') in {'STRUCTURED_SOURCE','EXPLICIT_SOURCE'} and p.get('evidence_reference')]
        event.update(context_contract=CONTRACT, context_registry_fingerprint=REGISTRY_FINGERPRINT,
            context_geography=context, institution_context=institutions, headline_explanation=explanation,
            event_geography=dict(status='KNOWN' if strict else 'UNKNOWN', geography=strict or None))
        result.append(event)
    return result
