# Current MFM reconciliation — 30 October 2026

The current official [Munitorum Field Manual](https://mfm.warhammer-community.com/en/)
was checked as v1.6 for the same 28 permitted faction groups. The official
[download index](https://www.warhammer-community.com/en-gb/downloads/warhammer-40000/)
labels the update 14 October 2026. The two Titan Legions groups and policy-excluded
sections remain outside scope. This is a points and army-construction source update,
not certification of all current faction rules or new playable datasheets.

For faction rules, the user's subsequent direction gives
[40k.app mirrored App-data updates](https://www.40k.app/factions/updates)
precedence over PDFs when they disagree. The [supported-rule follow-up](SUPPORTED_FACTION_RULE_RECONCILIATION_2026_10.md)
records versioned browser confirmations of all five selected PR599 clauses,
World Eaters' selected army-rule table and the Vyper/Vypers label discrepancy.
The original PDF-only receipts below remain unchanged historical evidence.
This faction-rule precedence clarification does not invalidate this separate
official interactive MFM points and army-construction reconciliation.

## Source and behavior

`mfm_2026_10` preserves current unit brackets, wargear prices, detachment points and
all legal force dispositions, enhancement prices, and modeled unit leader/support permissions.
The default lazy lookup in `engine/army_points.py` selects this package. Explicit
historical package injection still selects that historical source; the June and July
packages and July review retain their bytes and meaning.

The shared HTML boundary now resolves streamed structural chunks at their original
template slots. Late Ultramarines cards no longer inherit White Scars ownership.
The v3 package retains every current legal disposition in a typed tuple, while
legacy v2 payloads retain their singular field and original hashes.
Direct enhancement list rows and their adjacent allowance rows are normalized at
import, with legacy wrapped rows retained. An enhancement section without price rows
fails closed. Anathema Psykana is a reviewed current Custodes section, not a new faction.

The current review records 719 changed matching unit-cost records, 45 wargear rows,
110 unit leader permissions, 48 unit support permissions, 72 detachment cost/disposition
records and 37 enhancement prices. Source additions/removals include renames and
section moves: 70/140 unit records, 96/108 detachments, and 256/478 enhancements.
These numbers compare structured source records; they do not claim all differences
are newly changed official rules, nor that new records are executable content.

No source-backed alias or July fallback is invented for removed/renamed datasheets.
The existing exact-ID/name resolver rejects an unresolvable catalog selection. The
review explicitly lists all unmatched source identities for subsequent catalog review;
this maintenance does not certify those identities as usable with older catalogs.

Murdermind remains `semantic_execution_status=blocked`, with no runtime consumers.
Its 15-point price and typed v3 SUPPORT metadata are captured. Its grant to Lokhust Heavy Destroyers,
Ophydian Destroyers, Skorpekh Destroyers and Lokhust Destroyers is explicitly recorded
in the current review as blocked execution, not omitted source data. It is not converted into a
LEADER grant or claimed as implemented. New source rows do not add catalogs/providers.

## Reproduction and evidence

`data/source_audits/mfm_2026_10/*.html.gz` retains all 29 ordinary HTTP responses
(index and 28 faction pages) with deterministic compression. The source manifest
records their decoded SHA-256 hashes, exact URLs, source version/date, checked date,
and the empty inaccessible-source list. No special access headers or access-control
workarounds were used. The current package carries a canonical payload checksum.

```sh
uv run --no-sync python tools/import_mfm_points.py --source-directory data/source_audits/mfm_2026_10 --capture-manifest data/source_manifests/mfm_2026_10_sources.json
uv run --no-sync python tools/build_mfm_update_review.py --current --check
uv run --no-sync python tools/build_mfm_update_review.py --check
uv run --no-sync pytest tests/rules/section25/test_mfm.py -q --no-cov
```

The existing selected section25 file tests every captured page against committed
source data plus independent explicit before/after values through pricing, catalog
construction and real physical mustering. It covers repeated-unit brackets, wargear,
enhancement totals, detachment cost/disposition, and leader/support grants with
historical negative controls. It also checks streamed ownership, excluded/unknown
sections, direct and legacy enhancement markup and historical package identity.
Only its current admitted byte pin changes; native test membership, the coverage
metric, 64% floor and all 260 deferred quality identities remain unchanged.

The limited supporting faction-PDF checks are retained in
`data/source_audits/mfm_2026_10/bounded-rule-checks.json`. They identify checked current
PDF versions/hashes and selected unchanged executable clauses. They do not reconcile
whole faction books. The later linked audit confirms selected World Eaters and
the five earlier clauses against the preferred mirror; unreviewed faction sources
remain open.
No core-layout, mission or broader faction-rule implementation changes are included.

This maintenance has no allocated numbered Core remediation Order. Its completion
record is the separate MFM maintenance entry in the Core roadmap, and does not close
any existing numbered order. Final aggregate, performance, independent review and
hosted-check outcomes are reported separately; this document makes no pass claim.
