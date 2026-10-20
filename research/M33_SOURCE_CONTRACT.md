# M3.3 public-safe context contract — PARTIAL

This research branch prepares an exact-item public metadata gate. It does **not** recover timely independent macro news, activate capture, or deploy anything.

## Rights-first decisions

| Candidate | Rights classification | Actual result | Decision |
|---|---|---|---|
| VOA Economy | ITEM_LEVEL_RIGHTS_REQUIRED | Officially advertised RSS works; 20 records, newest March 2025; nine explicit Reuters/AP/AFP bylines | No public integration. A staff name is not proof of exclusive original ownership; stale even if cleared |
| Global Voices | PUBLIC_COMMERCIAL_ELIGIBLE for original licensed text, item exceptions still apply | 15 records; zero selected meaningful macro news | No forced integration or item publication |
| 360info | PUBLIC_COMMERCIAL_ELIGIBLE only after exact-item proof | 10 records; two five-day-old energy-policy analyses positively checked | Analysis context only; no new policy/supply-news count |
| Federal Reserve Board | PUBLIC_COMMERCIAL_ELIGIBLE original government text, no insignia or third-party content | 15 monetary-policy feed records; one previously known seven-day publication reviewed | OFFICIAL_ORIGIN_DISCOVERY fallback, not independent news |
| BEA | PUBLIC_COMMERCIAL_ELIGIBLE original government information, subject to exceptions | 48 feed items, 47 safe references; newest October 6 | Public-source fallback candidate, not added as a third integrated source |
| ECB | UNKNOWN current reviewed terms response | Old disclaimer URL returned 301; redirect refused | Not fetched or integrated as a feed in M3.3 |

Additional documentation-only check: GroundUp's newer freelancer guidance says most articles switched to a permission-based republication licence in April 2026. Older generic CC assertions are insufficient. No feed request or integration was made. This negative result did not change the predeclared six-source experiment pool.

Publisher references: [VOA terms](https://www.voanews.com/p/5338.html), [VOA directory](https://www.voanews.com/rssfeeds), [GV](https://globalvoices.org/about/), [360info](https://360info.org/how-to-use-our-content/), [Fed](https://www.federalreserve.gov/disclaimer.htm), [BEA](https://www.bea.gov/help/faq/147), [GroundUp current guidance](https://groundup.org.za/freelancing/).

These are publisher-specific documented permissions, not a general legal guarantee. The source page hashes and actual HTTPS receipt identities are recorded locally. A SHA verifies preserved bytes, not a cryptographic publisher licence signature.

## Exact-item gate

Only `360info` and `fed_monetary` can enter this public research path. No CNA content is parsed or used as a trigger or projection input; prior private files are only hashed in read-only preservation checks. VOA wire/staff records, unreviewed items, full bodies, excerpts, images, local paths, receipts and runtime logs are excluded from public outputs.

Every published item must match an immutable reviewed metadata fingerprint and original URL. The review pins policy and item-body SHA256 values to their actual source receipts. Missing, changed or mismatched evidence fails closed.

For the two 360info items, the gate verifies:

- Exact original h1 headline and publication timestamp against the feed.
- Body **Authors** region matches feed attribution, including the named scholar. CMS/SEO authors are deliberately ignored.
- Original article body explicitly says it was originally published under Creative Commons by 360info, with the CC BY 4.0 URL.
- Positive source-policy licence statement, not merely a copyright footer.
- No selected third-party wire attribution/restriction in the relevant original-text region.
- Public headline, author/affiliation, publisher, original URL, licence and terms links, hash proof and changes indication travel together, including in the handoff.

The reviewed scope is **title/byline/time/link only**. No third-party image, excerpt or full article is copied. CC BY 4.0 permits adapting licensed original text with attribution and changes disclosure; this candidate performs **no translation**. Other articles are not automatically approved because the publisher generally uses CC.

The Fed item is a Board-hosted original release corroborated against its original document and the positive government-public-domain statement. The supported proposition concerns publishing discount-rate meeting minutes. It does not verify a new FOMC decision, federal-funds target, future forecast, or the content of an unfetched PDF.

## Access and time

The publishers offer RSS for subscription, but no precise polling quota or unrestricted periodic-access permission was expressly established. The current two manually initiated bounded observations are research access. **Production periodic capture remains unauthorized**. No scheduler, background writer, source registration, new service or trading component is changed.

Transport/locks/reservations are reused from M3/M3.1. A separately versioned M3.3 plan pins the two selected sources. All qualification, quality and item requests share <=100 direct GET / <=20 MB accounting. Denial, redirects, rate limits and unknown write/read acknowledgments are never bypassed or retried automatically. Same spent cycle IDs do not issue new HTTP.

Publication, request start, response-body completion/retrieval, receipt completion and first observation in M3.3 are separate. The public gate cannot use rights/item evidence obtained after its as-of. URL identity remains unchanged; an unreviewed revision cannot inherit approval. Different article references are not forcibly merged into one world event.

Both 360info analyses were already present in the M3.2 source response; the Fed release was already present in M3. `NEW_TO_EXPERIMENT` means new to M3.3 only. No improved prospective recall, global first-seen or breaking-news detection is claimed. The old M3/M3.1/M3.2 plans, receipts and repositories remain unchanged.
