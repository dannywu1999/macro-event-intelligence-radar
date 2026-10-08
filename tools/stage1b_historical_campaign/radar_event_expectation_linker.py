"""Pure, conservative proposition links; no provider, clock, or trading access.

V0 recognizes explicit central-bank rate meetings only. A title similarity,
publication date, provider closing date, or shared country is never enough.
Unsupported propositions remain NO_MATCH; missing scope remains unlinked.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
import re
import unicodedata

CONTRACT = 'EVENT_EXPECTATION_LINK_V0'
METHOD = 'DETERMINISTIC_RATE_MEETING_V0'
ALIASES = {
    'ECB': ('ecb', 'european central bank'),
    'FED': ('fed', 'federal reserve', 'fomc'),
    'BOE': ('boe', 'bank of england'),
    'BOJ': ('boj', 'bank of japan'),
}
REGIONS = {'ECB': 'EURO_AREA', 'FED': 'US', 'BOE': 'UK', 'BOJ': 'JAPAN'}
REGION_ALIASES = {'EURO_AREA': r'euro area|eurozone', 'US': r'us|u\.s\.|united states',
                  'UK': r'uk|united kingdom|britain', 'JAPAN': r'japan'}
MONTHS = {m: i for i, m in enumerate(('january', 'february', 'march', 'april',
    'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'), 1)}
MONTH_NAMES = '|'.join(sorted({m for m in MONTHS} | {m[:3] for m in MONTHS}, key=len, reverse=True))


def normalize(value):
    if not isinstance(value, str):
        return ''
    value = unicodedata.normalize('NFKC', value).casefold()
    return re.sub(r'\s+', ' ', re.sub(r'[^\w%.\-]+', ' ', value)).strip()[:6000]


def instant(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (ValueError, OverflowError):
        return None


def date_scopes(value):
    """Only explicit text dates; never infer a year from observation time."""
    scopes = set()
    try:
        for y, m, d in re.findall(r'\b(20\d{2})-(\d{2})-(\d{2})\b', value):
            scopes.add(date(int(y), int(m), int(d)).isoformat())
        pattern = rf'\b({MONTH_NAMES})\.?\s+(?:(\d{{1,2}})\s+)?(20\d{{2}})\b'
        for match in re.finditer(pattern, value):
            # In "15 October 2026", October 2026 is not a second month scope.
            if re.search(r'\b\d{1,2}\s+$', value[:match.start()]):
                continue
            month, day, year = match.groups()
            number = next(n for m, n in MONTHS.items() if m.startswith(month))
            scopes.add(date(int(year), number, int(day)).isoformat() if day else f'{year}-{number:02}')
        for day, month, year in re.findall(rf'\b(\d{{1,2}})\s+({MONTH_NAMES})\.?\s+(20\d{{2}})\b', value):
            number = next(n for m, n in MONTHS.items() if m.startswith(month))
            scopes.add(date(int(year), number, int(day)).isoformat())
    except ValueError:
        return ['INVALID_DATE']
    return sorted(scopes)


def proposition(value):
    text = normalize(value)
    actors = sorted(actor for actor, aliases in ALIASES.items()
                    if any(re.search(r'\b' + re.escape(alias) + r'\b', text) for alias in aliases))
    rate = bool(re.search(r'\b(?:interest\s+rates?|rates?|monetary policy)\b', text))
    actions = []
    if rate:
        for action, terms in [('CUT', r'cut|cuts|cutting|reduce|reduces|reduced|reduction|lower|lowers|lowered'),
                              ('RAISE', r'raise|raises|raised|hike|hikes|increase|increases'),
                              ('HOLD', r'hold|holds|held|unchanged|maintain|maintains')]:
            if re.search(r'\b(?:' + terms + r')\s+(?:(?:interest|policy)\s+)?rates?\b', text):
                actions.append(action)
        if re.search(r'\brates?\s+(?:will\s+)?(?:remain|be|stay)\s+unchanged\b', text):
            actions.append('HOLD')
        actions = sorted(set(actions))
    generic = bool(re.search(r'\b(?:(?:interest|policy)\s+)?rate\s+(?:decision|meeting)\b|\bmonetary policy\s+(?:decision|meeting)\b', text)) and not actions
    thresholds = sorted(set(re.findall(r'\b\d+(?:\.\d+)?\s*(?:bps|basis points?|%)', text)))
    thresholds = [re.sub(r'\s*(?:bps|basis points?)$', 'bps', t) for t in thresholds]
    jurisdictions = sorted(region for region, alias in REGION_ALIASES.items()
        if re.search(r'\brates?\s+(?:in|for)\s+(?:the\s+)?(?:'+alias+r')(?:\s|$)', text))
    return dict(actors=actors, region=REGIONS.get(actors[0]) if len(actors) == 1 else None,
                object='POLICY_RATE' if rate else None, actions=actions,
                generic_decision=generic, date_scope=date_scopes(text), thresholds=thresholds,
                rate_jurisdictions=jurisdictions,
                negated=bool(re.search(r'\b(?:not|never|won t|no cut|no hike|without)\b', text)),
                deadline=bool(re.search(r'\b(?:before|by|until|after|since)\b', re.sub(
                    r'\bby\s+\d+(?:\.\d+)?\s*(?:bps|basis points?|%)', '', text))),
                prospective=bool(re.search(r'\b(?:will|would|may|could|expected|upcoming|scheduled|to cut|to raise|to hold)\b', text)),
                retrospective=bool(re.search(r'\b(?:cuts|raised|reduced|lowered|held|has cut|have cut|did cut)\b', text)),
                commentary=bool(re.search(r'\b(?:interview|speech|hearing|commentary|survey|forecast|supervision)\b', text)))


def compare(event, market):
    """Return a categorical audit record, never a confidence probability."""
    ep = proposition(event.get('event_title'))
    mp = proposition(market.get('question'))
    status, reason = 'INSUFFICIENT_EVIDENCE', 'EXPLICIT_ACTOR_ACTION_DATE_REQUIRED'
    if ep['object'] != 'POLICY_RATE' or mp['object'] != 'POLICY_RATE':
        status, reason = 'NO_MATCH', 'UNSUPPORTED_OR_DIFFERENT_PROPOSITION'
    elif ep['actors'] and mp['actors'] and set(ep['actors']).isdisjoint(mp['actors']):
        status, reason = 'NO_MATCH', 'DIFFERENT_INSTITUTION'
    elif any(p['rate_jurisdictions'] and p['rate_jurisdictions'] != [p['region']] for p in (ep, mp)):
        status, reason = 'NO_MATCH', 'DIFFERENT_POLICY_JURISDICTION'
    elif len(ep['actors']) > 1 or len(mp['actors']) > 1:
        status, reason = 'AMBIGUOUS', 'MULTIPLE_INSTITUTIONS'
    elif (len(ep['date_scope']) > 1 or len(mp['date_scope']) > 1
          or len(ep['actions']) > 1 or len(mp['actions']) > 1
          or len(ep['thresholds']) > 1 or len(mp['thresholds']) > 1):
        status, reason = 'AMBIGUOUS', 'MULTIPLE_PROPOSITION_SCOPES'
    elif ep['date_scope'] and mp['date_scope'] and ep['date_scope'] != mp['date_scope']:
        status, reason = 'NO_MATCH', 'DIFFERENT_DATE_SCOPE'
    elif (ep['negated'] or mp['negated'] or ep['deadline'] or mp['deadline']
          or re.search(r'\b(?:if|unless)\b', normalize(event.get('event_title')) + ' ' + normalize(market.get('question')))):
        status, reason = 'INSUFFICIENT_EVIDENCE', 'NEGATION_DEADLINE_OR_CONDITION_NOT_SUPPORTED'
    elif ep['thresholds'] and mp['thresholds'] and ep['thresholds'] != mp['thresholds']:
        status, reason = 'NO_MATCH', 'DIFFERENT_NUMERIC_THRESHOLD'
    elif any('%' in threshold for p in (ep, mp) for threshold in p['thresholds']):
        status, reason = 'INSUFFICIENT_EVIDENCE', 'PERCENT_LEVEL_VERSUS_CHANGE_NOT_SUPPORTED'
    elif ep['actions'] and mp['actions'] and ep['actions'] != mp['actions']:
        status, reason = 'NO_MATCH', 'DIFFERENT_POLICY_ACTION'
    elif event.get('event_occurred_at') is not None or (ep['retrospective'] and not ep['prospective']):
        status, reason = 'NO_MATCH', 'COMPLETED_EVENT_NOT_ACTIVE_EXPECTATION'
    elif ep['commentary']:
        status, reason = 'NO_MATCH', 'COMMENTARY_NOT_A_MEETING_PROPOSITION'
    elif (market.get('proposition_metadata') or {}).get('closed') is True or (market.get('proposition_metadata') or {}).get('active') is False:
        status, reason = 'NO_MATCH', 'PROVIDER_MARKET_NOT_ACTIVE'
    elif (market.get('proposition_metadata') or {}).get('incomplete') is True:
        status, reason = 'INSUFFICIENT_EVIDENCE', 'TRUNCATED_PROVIDER_PROPOSITION'
    else:
        observed, detected, closes = (instant(market.get('observed_at')),
            instant(event.get('first_detected_at')), instant(market.get('market_close_time')))
        if observed is None or detected is None or closes is None:
            reason = 'VALID_OBSERVATION_AND_MARKET_CLOSE_REQUIRED'
        elif observed >= closes or detected >= closes:
            status, reason = 'NO_MATCH', 'EXPECTATION_WINDOW_ALREADY_CLOSED'
        elif (ep['actors'] == mp['actors'] and len(ep['actors']) == 1
              and ep['date_scope'] == mp['date_scope'] and len(ep['date_scope']) == 1
              and len(ep['date_scope'][0]) == 10 and len(mp['actions']) == 1
              and (ep['generic_decision'] or (ep['actions'] == mp['actions'] and ep['prospective']))
              and (ep['generic_decision'] or ep['thresholds'] == mp['thresholds'])
              and market.get('authority_role') == 'EXPECTATION_SENSOR'
              and market.get('provider') == 'Polymarket'):
            # A text meeting scope must still lie in the remaining active window.
            scope = ep['date_scope'][0]
            start = date.fromisoformat(scope + '-01' if len(scope) == 7 else scope)
            end = date(start.year + (start.month == 12), start.month % 12 + 1, 1) if len(scope) == 7 else start
            if (end < max(observed.date(), detected.date())
                    or (len(scope) == 7 and end <= max(observed.date(), detected.date()))
                    or start > closes.date()):
                status, reason = 'NO_MATCH', 'TEXT_SCOPE_OUTSIDE_ACTIVE_WINDOW'
            else:
                status, reason = 'LINKED', 'SAME_INSTITUTION_POLICY_RATE_AND_EXPLICIT_MEETING_SCOPE'
    if status == 'LINKED':
        metadata = market.get('proposition_metadata') or {}
        # Secondary resolution text may refuse a match; it never fills missing
        # primary terms. Complex/mixed resolution scopes require human review.
        for key in ('description', 'resolution_criteria'):
            secondary = proposition(metadata.get(key))
            if (len(secondary['actors']) > 1 or len(secondary['date_scope']) > 1
                    or len(secondary['actions']) > 1 or secondary['negated']):
                status, reason = 'AMBIGUOUS', 'COMPLEX_RESOLUTION_TEXT'
            elif ((secondary['actors'] and secondary['actors'] != mp['actors'])
                  or (secondary['actions'] and secondary['actions'] != mp['actions'])
                  or (secondary['date_scope'] and secondary['date_scope'] != mp['date_scope'])
                  or (secondary['thresholds'] and secondary['thresholds'] != mp['thresholds'])):
                status, reason = 'NO_MATCH', 'RESOLUTION_TEXT_CONTRADICTS_QUESTION'
    record = dict(contract_version=CONTRACT, canonical_event_id=event.get('event_id'),
        expectation_market_id=market.get('market_id'), expectation_id=market.get('expectation_id'),
        link_status=status, link_method=METHOD, confidence_class='HIGH' if status == 'LINKED' else None,
        event_terms=ep, market_terms=mp, matched_terms=[ep['actors'][0], 'POLICY_RATE', *ep['date_scope']] if status == 'LINKED' else [],
        reason=reason, observed_at=None, market_observed_at=market.get('observed_at'),
        time_basis='SYSTEM_RECORDED_TIME_ON_INGEST', authority_role='EXPECTATION_SENSOR')
    return identify(record)


def identify(record):
    record = {k: v for k, v in record.items() if k != 'link_id'}
    record['link_id'] = 'event-expectation-link-v0-' + hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return record


def link_events(events, markets):
    """Multiple markets per event; an indistinguishable event target is refused."""
    pairs = [compare(e, m) for e in sorted(events[:100], key=lambda r: r['event_id'])
             for m in sorted(markets[:20], key=lambda r: r['market_id'])]
    targets = Counter(p['expectation_market_id'] for p in pairs if p['link_status'] == 'LINKED')
    event_ids = Counter(e['event_id'] for e in events[:100])
    for i, pair in enumerate(pairs):
        if pair['link_status'] == 'LINKED' and (targets[pair['expectation_market_id']] > 1 or event_ids[pair['canonical_event_id']] > 1):
            pairs[i] = identify({**pair, 'link_status': 'AMBIGUOUS', 'confidence_class': None,
                                 'matched_terms': [], 'reason': 'MULTIPLE_CANONICAL_EVENT_TARGETS'})
    return pairs
