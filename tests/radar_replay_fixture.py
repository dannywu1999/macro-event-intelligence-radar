"""Explicit synthetic history and curated mappings; never production data."""
import copy,json,tempfile
from pathlib import Path
from tools.stage1b_historical_campaign import global_event_radar_read_adapter as radar
from tools.stage1b_historical_campaign.radar_market_expectations import parse_markets,project_expectations
ROOT=Path(__file__).resolve().parents[1]
def at(hm):return '2026-10-07T'+hm+':00Z'
def projection(stage='09:00'):
 fixture=json.loads((ROOT/'tests/fixtures/reality_replay_v0.json').read_text('utf-8'));assert fixture['synthetic'] is True
 rows=fixture['articles']
 if stage>='10:15':rows[0]['headline_or_text']='Synthetic EIA later update'
 with tempfile.TemporaryDirectory() as t:
  p=Path(t)/'news.json';p.write_text(json.dumps(rows),'utf-8');v=radar.build_radar_view(radar.EvidencePaths(news=p))
 by_url={e['article_references'][0]:e['event_id'] for e in v['events']};eid=by_url['https://example.test/eia']
 if stage>='09:30':
  facts=[]
  for name,slug in [('U.S. Energy Information Administration','eia'),('European Central Bank','ecb')]:
   facts.append(dict(official_confirmation='OFFICIAL_CONFIRMED',authority_role='FACT_AUTHORITY',authority_name=name,official_source='https://example.test/'+slug+'/official',official_document_reference='SYNTHETIC-'+slug,official_fact_proposition='Synthetic fixture proposition only.',official_published_at=None,official_project_first_seen_at=at('09:30'),official_retrieved_at=at('09:30'),canonical_event_id=by_url['https://example.test/'+slug]))
  v.update(radar.build_official_evidence_projection(facts,v['items'],v['events']))
 if stage>='09:10':
  observed=at('10:00') if stage>='10:00' else at('09:10');prices=['0.70','0.30'] if stage>='10:00' else ['0.55','0.45']
  raw=[dict(id='synthetic-market-'+slug,question='Synthetic fixture question '+slug,outcomes=['Yes','No'],outcomePrices=prices,endDate=at('08:30')) for slug in ['eia','market']]
  v.update(project_expectations(v['events'],parse_markets(raw,observed),{by_url['https://example.test/'+slug]:'synthetic-market-'+slug for slug in ['eia','market']}))
 return v,eid
