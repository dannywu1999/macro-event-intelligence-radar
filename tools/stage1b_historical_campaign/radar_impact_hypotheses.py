"""Impact hypotheses V0: typed, read-only, conditional presentation, never prediction.

The source headline is the reported input, not a newly verified action. Institution
context alone cannot select a mechanism. No data acquisition or market measurement.
"""
from __future__ import annotations
import re
from typing import Literal, TypedDict
from tools.stage1b_historical_campaign.radar_news_intelligence import provenance
from tools.stage1b_historical_campaign.global_event_radar_read_adapter import canonical_merge_evidence

class Text(TypedDict):
    en: str
    zh: str
class MarketExposure(TypedDict):
    market_id: str
    label: Text
    rationale: Text
    observation_instruments: list[str]
    evidence_status: Literal['HYPOTHESIS']
    direction: None
class Mechanism(TypedDict):
    mechanism_id: str
    label: Text
    explanation: Text
    trigger_terms: list[str]
    conditions: list[Text]
    counter_scenario: Text
    next_observation: list[Text]
    exposed_markets: list[MarketExposure]
    evidence_status: Literal['HYPOTHESIS']
class Impact(TypedDict):
    status: Literal['CONDITIONAL_HYPOTHESIS_AVAILABLE','IMPACT_NOT_ESTABLISHED']
    article_reference: str
    canonical_event_id: str | None
    source_fact: dict
    article_kind: dict
    official_propositions: list[dict]
    mechanisms: list[Mechanism]
    market_reaction: dict
    novelty_status: Literal['NOT_ESTABLISHED']
    interpretation_role: Literal['CONDITIONAL_INTERPRETATION_ONLY']

def text(en,zh):
    return Text(en=en,zh=zh)
def market(identifier,label,rationale,instruments):
    return MarketExposure(market_id=identifier,label=label,rationale=rationale,
        observation_instruments=list(instruments),evidence_status='HYPOTHESIS',direction=None)
def mechanism(identifier,label,explanation,terms,conditions,counter,next_checks,markets):
    return Mechanism(mechanism_id=identifier,label=label,explanation=explanation,
        trigger_terms=terms,conditions=conditions,counter_scenario=counter,
        next_observation=next_checks,exposed_markets=markets,evidence_status='HYPOTHESIS')
def matched(pattern,title):
    return [m.group() for m in re.finditer(pattern,title,re.I)]

def classify_article(article):
    title=article.get('title') or ''
    if canonical_merge_evidence(article,article)['merge']:
        kind='REPORTED_RATE_DECISION'
    elif matched(r"\b(analysis|opinion|commentary|outlook|forecast|interview|linking|review|threaten\w*|could|may|expect\w*)\b|^(?:How|Why|What)\b",title):
        kind='ANALYSIS_OR_CONTEXT'
    else:kind='ARTICLE_TYPE_UNKNOWN'
    return dict(status=kind,basis='HEADLINE_CUES_ONLY;NOT_A_VERIFIED_NEW_EVENT',breaking_event_established=False)

def hypotheses(article,event):
    title=article.get('title') or '';result=[]
    institutions={str(i.get('institution_id') or '').upper() for i in (event or {}).get('institution_context',[])}
    terms=matched(r"\b(interest rates?|monetary policy|rate cuts?|rate hikes?)\b",title)
    if not terms and canonical_merge_evidence(article,article)['merge']:terms=matched(r'\brates\b',title)
    fed=bool(matched(r"\b(Fed(?!\s+up\b)|Federal Reserve|FOMC)\b",title));ecb='ECB' in institutions or bool(matched(r"\b(ECB|European Central Bank)\b",title))
    if terms and (fed or ecb):
        # Jurisdiction-specific; ECB does not automatically become a US-rate/DXY call.
        label=text('US Treasury yields','美國公債殖利率') if fed else text('Euro-area funding / yield curves','歐元區融資條件／殖利率曲線')
        instrument=['US Treasury yields'] if fed else ['Euro-area yield curves']
        result.append(mechanism('MONETARY_POLICY',text('Policy expectations → financing conditions','政策預期 → 融資條件'),
            text('If the report changes expectations of the relevant central bank policy path, funding and discount-rate assumptions could change. Guidelines or commentary alone do not establish a rate decision.','若報導改變相關央行政策路徑的預期，融資與折現條件可能改變。操作指引或評論本身不等於利率決議。'),terms,
            [text('Identify an actual decision versus operational guidance or commentary.','先辨別實際決議、操作指引或評論。'),text('The information must differ materially from what was already expected.','資訊必須相對既有預期有實質差異。')],
            text('An unchanged expected policy path, offsetting data or guidance limited to operations could leave the hypothesis unsupported.','政策路徑未變、其他數據抵銷或僅屬操作指引，都可能使假說不成立。'),
            [text('Check the dated central-bank decision and stated scope.','查核具日期的央行決議與適用範圍。'),text('Obtain timestamped relevant yield curves before/after the release, with competing news identified; none are acquired here.','取得發布前後具時間戳的相關殖利率曲線，辨識其他同時新聞；本功能未取得這些資料。')],
            [market('US_RATES' if fed else 'EURO_AREA_RATES',label,text('Policy-path expectations enter funding and yield-curve pricing; maturity-specific responses remain unknown.','政策路徑預期可能進入融資與殖利率曲線定價；各期限反應仍未知。'),instrument)]))
    terms=matched(r"\b(tariffs?|sanctions?|export controls?|reciprocal trade|trade agreements?|trade deal|embargo)\b",title)
    if terms:
        result.append(mechanism('TRADE_POLICY',text('Trade rules → operating costs / market access','貿易規則 → 營運成本／市場准入'),
            text('If enforceable trade rules change an identified firm or sector’s costs or access, its earnings assumptions may need review. The headline alone does not establish implementation or affected holdings.','若可執行的貿易規則改變已辨識企業或產業的成本／准入，獲利假設可能須重查。標題本身未證明已實施或受影響持股。'),terms,
            [text('Verify the policy text, effective date, jurisdiction and covered products/services.','查核政策文本、生效日、管轄區及涵蓋產品／服務。'),text('Identify actual exposure and whether costs can be passed on; do not assign SPY/QQQ from a generic topic.','辨識實際曝險及成本能否轉嫁；不由泛泛主題自動指定 SPY／QQQ。')],
            text('Exemptions, delayed implementation, substitution or already-priced rules may prevent the proposed channel.','豁免、延後實施、替代來源或既已反映的規則可能阻斷此傳導。'),
            [text('Obtain official implementation details and affected-firm disclosures.','取得官方實施細節與受影響企業揭露。'),text('Identify the relevant sector basket and timestamped observations before evaluating a market response.','先辨識相關產業組合及具時間戳觀測，再評估市場反應。')],
            [market('TRADE_EXPOSED_EQUITIES',text('Trade-exposed equities · constituents unknown','貿易曝險股票 · 成分尚待辨識'),text('Costs and market access can affect earnings of actually exposed firms; broad index exposure is not established.','成本及准入可能影響確有曝險企業的獲利；大盤指數曝險尚未確立。'),[])]))
    terms=matched(r"\b(crude(?: oil)?|petroleum|WTI|Brent|oil pipelines?|oil supply|oil production|oil prices)\b",title)
    non_energy=matched(r"\b(olive|cooking|vegetable|palm|essential) oil\b",title)
    if terms and not non_energy:
        result.append(mechanism('OIL_SUPPLY',text('Oil supply / transport → physical balance','原油供給／運輸 → 實體供需'),
            text('A material change in crude production, transport or availability could change the physical balance relevant to oil benchmarks. An infrastructure essay is not evidence that a disruption has occurred.','原油產量、運輸或可得性若有實質變化，可能改變原油基準的實體供需。基礎設施分析文章不證明已發生中斷。'),terms,
            [text('Verify actual crude volumes, affected route, duration and whether the source describes a scenario or observation.','查核實際原油量、路線、持續時間，並辨別情境或已觀測事實。'),text('Establish linkage to the relevant benchmark region and account for inventories and demand.','確立與相關基準區域的連結，並考慮庫存及需求。')],
            text('Spare capacity, inventories, rerouting or weaker demand could offset or reverse the hypothesized effect.','備用產能、庫存、改道或較弱需求可能抵銷或反轉假設效果。'),
            [text('Seek dated physical-flow, inventory and operational evidence.','尋找具日期的實體流量、庫存及營運證據。'),text('Obtain timestamped WTI/Brent observations and a defined comparison window; do not infer returns from this headline.','取得具時間戳的 WTI／Brent 觀測及明確比較窗口；不由標題推算報酬。')],
            [market('OIL_BENCHMARKS',text('Oil benchmarks · WTI / Brent','原油基準 · WTI／Brent'),text('Physical crude availability can enter benchmark pricing, conditional on regional linkage; neither direction nor magnitude is established.','實體原油可得性可能影響基準定價，但須有區域連結；方向與幅度均未確立。'),['WTI','Brent'])]))
    shock=matched(r"\b(war|conflict|blockade|attack\w*|airstrikes?)\b",title);route=matched(r"\b(shipping|supply|trade|transport|strait|Hormuz|pipelines?)\b",title)
    if shock and route:
        result.append(mechanism('GEOPOLITICAL_SUPPLY',text('Conflict → route availability / logistics cost','衝突 → 路線可用性／物流成本'),
            text('If an evidenced conflict materially disrupts the named supply or transport channel, exposed businesses could face delays or costs. A shared country or conflict word is insufficient.','若有證據的衝突實質中斷所述供應／運輸管道，曝險企業可能面臨延遲或成本。僅同國家或衝突字詞不足。'),shock+route,
            [text('Verify the disruption, route and affected businesses; the article may be commentary.','查核中斷、路線及受影響企業；文章也可能只是評論。')],
            text('De-escalation, alternative routes or no actual interruption could invalidate the scenario.','降溫、替代路線或根本未中斷，都可能使情境不成立。'),
            [text('Seek dated route/operational evidence and identify exposed firms before acquiring comparable market observations.','先尋找具日期的路線／營運證據及曝險企業，再取得可比較市場觀測。')],
            [market('LOGISTICS_EXPOSED_EQUITIES',text('Route-exposed businesses · holdings unknown','路線曝險企業 · 持股尚待辨識'),text('Transport delays or added operating costs could affect actual route-dependent earnings; no Gold/DXY reflex is assumed.','運輸延遲或營運成本可能影響確有路線依賴的獲利；不自動推論黃金／DXY 反應。'),[])]))
    return result[:2]

def project(view):
    by_article={};events=view.get('events',[])
    for article in view.get('items',[]):
        ref=article.get('article_reference')
        if not isinstance(ref,str) or not ref:continue
        matches=[e for e in events if ref in e.get('article_references',[])];event=matches[0] if len(matches)==1 else None
        valid=provenance(article) and event is not None
        mechanisms=hypotheses(article,event) if valid else []
        facts=[dict(official_evidence_id=e['official_evidence_id'],fact_proposition=e['fact_proposition'],
            authority_name=e.get('authority_name'),document_url=e.get('document_url'),published_at=e.get('published_at'),
            evidence_status='OFFICIAL_CONFIRMED',scope='SPECIFIC_PROPOSITION_ONLY')
            for e in view.get('official_evidence',[]) if event and e.get('official_evidence_id') in event.get('official_evidence_ids',[])
            and e.get('canonical_event_id')==event.get('event_id') and e.get('evidence_status')=='OFFICIAL_CONFIRMED'
            and isinstance(e.get('fact_proposition'),str) and e['fact_proposition'].strip()]
        by_article[ref]=Impact(status='CONDITIONAL_HYPOTHESIS_AVAILABLE' if mechanisms else 'IMPACT_NOT_ESTABLISHED',
            article_reference=ref,canonical_event_id=event.get('event_id') if event else None,
            source_fact=dict(headline=article.get('title'),source=article.get('news_source'),reported_at=article.get('reported_at'),
                reported_time_kind=article.get('reported_time_kind'),observed_at=article.get('observed_at'),
                evidence_status='REPORTED_HEADLINE_NOT_INDEPENDENTLY_VERIFIED',scope='SOURCE_ATTRIBUTED_HEADLINE_ONLY'),
            article_kind=classify_article(article),official_propositions=facts,mechanisms=mechanisms,
            market_reaction=dict(status='NOT_MEASURED',observations=None,attributed_return=None),
            novelty_status='NOT_ESTABLISHED',interpretation_role='CONDITIONAL_INTERPRETATION_ONLY')
    return dict(contract='IMPACT_HYPOTHESES_V0',by_article=by_article,
        hypothesis_article_count=sum(bool(i['mechanisms']) for i in by_article.values()),
        unknown_article_count=sum(not i['mechanisms'] for i in by_article.values()))
