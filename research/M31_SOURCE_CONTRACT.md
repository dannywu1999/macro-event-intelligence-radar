# M3.1 economic discovery contract v1

Research only. Independent M3.1 plan/receipts; M3 six-source plan is unchanged.

## Two selected source families, three bounded endpoints

|Family|Original publisher/authority|Endpoint|What is actually observed|
|---|---|---|---|
|BLS API v1|U.S. Bureau of Labor Statistics|https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0|CPI-U, all items, U.S. city average, NSA, index 1982-84=100|
|BLS API v1|U.S. Bureau of Labor Statistics|https://api.bls.gov/publicAPI/v1/timeseries/data/CES0000000001|Total nonfarm payroll employment level, SA, thousands of persons|
|BEA current releases|U.S. Bureau of Economic Analysis|https://www.bea.gov/news/current-releases|Only monthly Personal Income and Outlays announcement metadata; includes PCE, not CPI|

### Rights and access documentation

- [BLS API signatures](https://www.bls.gov/developers/api_signature.htm): public v1 GET single-series interface; no credentials supplied.
- [BLS API FAQ](https://www.bls.gov/developers/api_faqs.htm): unregistered access up to 25 queries/day. The experiment caps its own BLS requests at 25 UTC-day reservations; other users on a shared egress IP are unobservable.
- [BLS data API](https://www.bls.gov/bls/api_features.htm): values/footnotes, not release metadata; documented lag warning. Do not claim current publication-time SLA from an old feature description.
- [BLS copyright](https://www.bls.gov/bls/linksite.htm): government data, attribution; third-party exceptions preserved.
- [CPI series semantics](https://www.bls.gov/cpi/factsheets/cpi-series-ids.htm).
- [BLS publication, footnote 9](https://www.bls.gov/opub/mlr/2023/article/job-openings-reach-record-highs-in-2022-as-the-labor-market-recovery-continues.htm): identifies CES0000000001 as all employees, thousands, total nonfarm, seasonally adjusted. A level is not monthly payroll growth.
- [BEA reuse policy](https://www.bea.gov/help/faq/145): unless otherwise noted public domain; attribute BEA.
- [BEA developers](https://www.bea.gov/resources/for-developers): designated RSS and programmatic interfaces. The actual current-release HTML also links the tested RSS.

Only metadata and small public statistical values enter the research projection. Local raw official responses are reproducibility evidence, not a public full-text news feed. No account, paid API or registration is created.

## Time and identity semantics

- BLS year/month identifies the **reference period**, never publication time. Publication and release latency remain null/UNKNOWN. Annual-average M13 is separate from a month.
- BLS `-` remains source-unavailable/null with original raw value and footnote; never zero. Preliminary footnotes remain attached.
- Series/period source keys identify statistical observations, **not canonical news events**. No BLS time-series record is promoted into a release announcement or official proposition packet.
- BEA uses the existing article URL identity helper. HTML `time@datetime` is source-reported publication time, not measured first public availability. Date-only, missing, invalid and future times stay explicitly qualified.
- First observed is only the first M3.1 retrieval of that record. HTTP ACK recording and later metadata parsing clocks are separate. Neither is global first-seen or retrospective PIT history.
- Probe responses are acquired before final source selection. Their later derived parses preserve original ACK clocks and bytes. The selection probes are round 1 for repeatability; the frozen-plan subsequent round is not an out-of-sample coverage benchmark.
- BEA's current list replaces older releases; it is not an archive. Its RSS was incomplete for the tested current PCE release. Retain the miss rather than treating HTTP 200 as completeness.

## Operational boundary

Default CLI is offline. Explicit network opt-in, sequential GET, 2 MiB/response, 80 reserved requests/20 MB experiment budget, no redirects/retries. Unknown ACK or denial pauses that family. Existing M3 transport, OS lock, canonical JSON, timestamps and hashing are reused without editing M3.

The 30-minute interval is for this short experiment only. Two BLS GETs every 30 minutes would exceed the unregistered daily limit over 24 hours; **this is not an approved continuous schedule**. No scheduler or production registration is installed.

Discovery remains distinct from proposition verification. No production Writer, owner/claim, D1, Frozen, H2, Broker, Paper or Live operation is involved.
