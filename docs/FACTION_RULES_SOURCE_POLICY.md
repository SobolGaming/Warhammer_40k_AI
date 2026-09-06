# Faction Rules Source Authority Policy — F00

Policy ID: `faction-source-policy:maintained-direct-app-data-mirror:2026-09-05`.
Decision: extend the maintained-App evidence contract to in-scope Warhammer
40,000 11th Edition faction, detachment and datasheet source packages, as
requested in Order F00. This is a separate authority scope,
`warhammer_40000_11th_factions`; the Core Rules policies and immutable historical
observations retain their existing scope and identity.

## Selected version and provider

The initial selection is **App-data 946**, English, observed on **5 September
2026**. The retained update-feed statement identifies the 2 September release.
These current-page observations belong to that complete App-data snapshot;
946 is not a claim that each selected rule last changed in that release. There
is no selected tournament cutoff or official App binary build, and this source
package makes no tournament certification claim. Later versions require a new
retained observation and reviewed pin, not relabeling these bytes.

For this scope, the approved provider is **40k.app**, at canonical HTTPS
`https://www.40k.app/factions/<faction>/army-rules`,
`.../detachments/<detachment>` and `.../units/<datasheet>` URLs.
The exact observed owner, page kind and complete URL must agree. Navigation
indexes, update snippets, search results, redirects, version-query parameters
and other providers cannot authorize operative faction text through this policy.
An update-feed statement can identify the selected snapshot only.

40k.app is a non-affiliated maintained mirror, not a Games Workshop website.
Its authority is `project_authoritative_app_mirror`, never `official_primary`.
Game Datamissions retains its approved Core Rules scope; adding a faction
provider requires observed canonical faction pages, a policy update and
registered complete evidence. 39k PRO remains secondary lookup evidence under
AGENTS.md and cannot authorize a package or replace official provenance.

## Retention and completeness contract

The authoritative input is reviewed JSON, with a typed fail-fast loader. Each
selected page must retain:

1. Stable project source-document ID, owning faction source ID, content kind,
   exact provider and URL, English locale, App-data version and timezone-aware
   observation timestamp. Page IDs are provenance identities, not catalog or
   clause execution IDs. F01 must explicitly map those identities; same-name,
   related-army and inherited views never transfer ownership or execution.
2. Complete rendered `main.innerText` in `captured_text` and its UTF-8 SHA-256,
   an explicit unique starting heading, and the complete suffix from that
   heading in `operative_text`, with a separate transcription SHA-256. Retain
   points/DP, force disposition, profiles, all options, restrictions, subrules,
   examples and damaged sections present on the selected page. Preserve source
   anomalies without silently correcting the text. Section absence is not a
   gameplay default. Linked Core Abilities remain separately sourced dependencies.
3. A source-observation fingerprint over **all** observation fields except the
   fingerprint itself, using sorted compact JSON with ASCII escaping and UTF-8.
   Status and consumer claims are stored separately in `RuleEvidenceRecord`.
   Implementation changes cannot rewrite the source observation.
4. Explicit `matched_play` classification, resolved exact identity and a scope
   review. A completeness label is a review assertion authenticated by the
   immutable byte pin; hashing a shortened page cannot establish completeness.
5. Independent official historical source IDs, provider, original URL, source
   date, retained PDF path and SHA-256. Historical primary evidence is not
   current corroboration. Preserve it when maintained App wording supersedes it;
   record clause-level drift in F01 without combining versions or texts.
6. Explicit geometry obligations for each observed datasheet model role,
   including whether a base was actually observed and missing height evidence.

The initial three complete pages are Acts of Faith, Sanctified Orators (including
Hagiomnifex and all five selectable subrules), and Exorcist (including both cost
rows, every weapon, options and damaged section). The
[retained audit](../data/source_audits/maintained_app_mirrors/factions_2026_09_05.audit.json)
and [generated review](FACTION_SOURCE_GOVERNANCE_REVIEW.md) identify their hashes.
The timestamp records completion of this observation review batch. Original
5 September inventory fingerprints remain historical observations and are not
reused as the fingerprints of these new retained captures.

## Validation and scope exclusions

`validate_faction_source_audit_bytes` checks structural completeness: schema,
declared review status, capture/suffix relationship and hashes. It does not prove
provider-page completeness or grant authority. A mutually truncated capture and
operative suffix can pass those structural checks after rehashing. Human review
establishes provider-page completeness; `load_faction_source_audit_bytes`
authenticates that reviewed selection through the exact immutable artifact SHA-256.

The packaged authority registry binds the policy to an exact audit row, provider,
URL, fingerprint and version/timestamp. Package version and catalog source date
are derived from the audit's App-data version and latest UTC observation date,
including the version-feed observation. The registry also authenticates a SHA-256
of the full canonical `SourceCatalog.to_payload()` (sorted compact JSON, ASCII
escaping, UTF-8). This covers package and catalog versions, source date, document
IDs/titles, document-to-source relationships, text and normalization, and ruleset
bundles. Registry schema v2 requires this hash for faction packages; existing
Core Rules registrations explicitly retain their inventory-only policy with a
null catalog hash.

`SourceCatalog` requires globally unique source IDs across all documents.
`RuleEvidenceRecord` additionally authenticates source ID, title and transcription
against the retained observation. `RuleSourcePackage` requires exact source/evidence
inventories and the non-Core normalization scope. Recomputing hashes or supplying
a Core Rules audit cannot authorize a new row or drifted catalog metadata.

Missing, duplicate, unknown or cross-owner rows, unsupported schemas/fields,
mixed versions/locales, malformed provenance, structural incompleteness and
mismatched hashes fail closed during candidate validation. Any changed capture,
including a structurally valid truncation, fails the reviewed byte pin.
Co-versioned observations of one source ID must agree in
complete operative transcription. Duplicate agreement does not create a second
identity. Do not resolve disagreement by provider preference, recency, row order,
or fallback. Absent comparison evidence is not an agreement claim.

Forge World, Crusade, Boarding Action/Boarding Actions, Kill Team as a separate
game, Legends and Warhammer Legends remain excluded. The schema rejects their
classifications and the immutable authority registry admits only reviewed IDs.
Do not reclassify excluded content as matched play to bypass that boundary.
Current ordinary 40,000 Deathwatch datasheets named Kill Team are not excluded
by their display name. The Warbuggies exact-identity hold remains unresolved
under F-SCOPE-01; it has no source-package or catalog admission in F00. F01 owns
its source review. No excluded or held content is scaffolded as supported.

Unresolved identity, truncated/ambiguous operative wording, incompatible clauses
or actual co-versioned provider disagreement require official-App disambiguation
before admission. Record the exact statements, affected IDs, URLs, version/build
when available, locale, platform, timestamp, chosen interpretation and
supersession scope. Until resolved, retain the finding outside the admitted
package and block source and semantic certification. A stale search-index
rendering is not a co-versioned complete observation.

## Geometry authority

An explicit maintained-App base statement can establish that source field. An
official product/base specification or model profile can independently establish
the dimensions it actually supplies. Neither establishes a model height or hull
shape it does not specify. A Hull label requires measured hull geometry; it
does not mean zero dimensions or a circular default.

F06 must use the existing `ModelGeometrySourceEvidence` and
`ModelGeometryCatalogRecord` owners, including model-profile and variant identity,
measurement kind, source and canonical units/dimensions, coordinate frame,
origin, document/URL and accepted review status. Manual or crowd-sourced
measurements require explicit review for that exact sculpt/configuration; they
are not official evidence. Footprint/support base, height and any z-offset must
have the required accepted evidence. New provider authority does not promote
existing unreviewed geometry. Missing base, height, hull or variant evidence
blocks fieldability, independently of source loading and semantic execution.
The F00 page-observation schema cannot certify geometry or supply numeric
defaults; an Exorcist Hull obligation demonstrates that boundary.

## Build and verification

Run `uv run python tools/build_faction_source_governance.py --check` offline.
The builder verifies the retained official PDF bytes, the entire audit-derived
source-package authorization and audit registry rows, the packaged observation
copy, generated review and real shared source-package construction. Official URL
and artifact paths must be normalized relative POSIX paths without dot segments,
backslashes, colons, percent escapes or control characters. Before reading, the
shared `SourceFileChecksum.from_path` resolves the candidate and artifact root and
requires containment beneath `data/raw/faction_packs`, including symlink targets.
The builder never fetches a provider. To update reviewed
evidence, add a new versioned audit, review the complete selection and scope,
update the authority registry and loader pins in the same PR, then generate the
packaged JSON and report without `--check`. Runtime loaders use only packaged
data and never require local PDF caches or live access.

Regressions are in `tests/unit/test_faction_source_governance.py`; source/static
audits are in `tests/code_quality/test_faction_source_governance.py`. Existing
Core Rules authority, legacy inventory and package-scope regressions remain
required. Runtime JSON/code changes also require the engine build manifest and
external contract examples to be regenerated and checked against the PR base.

F00 closes source governance for these package kinds. It does not reconcile the
remaining 40-view inventory (F01), implement faction semantics (F02–F07), or
certify rosters, replay or faction coverage (F08–F09). No player-facing decision,
proposal, visibility rule or adapter payload shape changes, so the existing
adapter decision contract covers this PR without revision.
