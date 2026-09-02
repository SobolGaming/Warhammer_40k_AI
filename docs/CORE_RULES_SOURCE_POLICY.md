# Core Rules Source Authority Policy

## Decision

- Policy ID:
  `core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02`
- Decision date: 2026-09-02
- Decision owner: repository owner
- Scope: Warhammer 40,000 11th Edition Core Rules categories 01–25 only
- Maintained direct App-data mirror providers:
  [40k.app](https://www.40k.app/) and
  [Game Datamissions](https://game-datamissions.com/11th/rules/changelog)

The repository owner identifies both named providers as maintained direct
mirrors of Games Workshop Warhammer 40,000 App data for this scope. A complete,
hash-pinned observation from either provider may therefore carry
`project_authoritative_app_mirror` authority. A matching observation from the
other provider is useful corroboration, but it is not required when no
co-versioned observation exists.

This is a project authority decision. It does not claim that either provider is
owned by, affiliated with, or endorsed by Games Workshop. Every mirror record
must preserve the provider's identity and non-affiliation marker and must never
use `official_primary`. That authority remains reserved for retained evidence
that actually came from Games Workshop.

This policy supersedes
`core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26` for
new observations. Existing immutable 40k.app observations retain that earlier
policy ID as historical provenance; the superseded policy cannot authorize a
new provider or a new source observation.

## Required evidence tuple

Every project-authoritative maintained-mirror source row must retain all of the
following:

1. The exact provider name: `40k.app` or `Game Datamissions`.
2. The provider's canonical HTTPS URL for the observation.
3. The App-data version or an ISO-8601 observation timestamp with UTC offset.
4. The exact reviewed operative transcription and its lowercase SHA-256.
5. An immutable source-observation SHA-256 fingerprint covering provenance and
   transcription metadata while excluding implementation status.
6. The linked offline audit ID, audit row ID, and audit-row source-observation
   fingerprint.
7. The non-affiliation marker and the current policy ID.

Missing or malformed tuple data fails source-package loading. Provider names
and URLs are allowlisted together: 40k.app records use canonical
`https://www.40k.app/rules...` URLs, while Game Datamissions records use
`https://game-datamissions.com/11th/rules/changelog`.

## Comparison and conflict rules

1. Stable project rule IDs remain authoritative identity. Provider numbering
   is metadata and cannot replace a stable source ID.
2. Project-authoritative observations for the same stable rule ID and App-data
   version form a co-versioned comparison group.
3. When more than one named provider is present in that group, every
   transcription SHA-256 must match. A mismatch fails closed before a source
   package can load or certify semantics.
4. A co-versioned mismatch requires comparison with the official App. Neither
   provider wins by preference, recency, record order, or fallback.
5. When only one provider exposes the required App-data version, its complete
   evidence tuple may control. Do not invent a comparison result for the absent
   provider.
6. Current maintained App wording supersedes an older Games Workshop PDF or
   stale repository transcription for the affected rule and version. Preserve
   the older artifact and record the drift; do not merge the texts.

## Operational rules

1. The live provider sites are never queried by the game engine. Reviewed,
   normalized, hash-pinned source artifacts are the only loader boundary.
2. Preserve official PDF artifacts and hashes as historical primary evidence.
3. Keep source observation identity separate from implementation status and PR
   planning so implementation-only edits do not change the observation
   fingerprint.
4. Owner or project-review transcriptions and maintained-mirror observations
   remain separate evidence records even when their text matches. A repository
   review transcription remains `unverified_transcription_only` on its own.
5. If App headings or cross-references are internally inconsistent, bind by
   stable source ID, rule title, and complete operative statement and record
   the anomaly.
6. A row absent from, or conflicting with, all applicable authoritative
   maintained-mirror evidence is not certified merely because an older
   repository transcription exists.
7. Load support and semantic execution status remain separate and truthful.
8. The checked-in
   [maintained-mirror review](CORE_RULES_MAINTAINED_MIRROR_REVIEW.md) and its
   audit artifact record both approved providers without treating either as a
   Games Workshop source.

## User disambiguation exception

Routine rule work does not require a second mirror or official-App capture
while this policy remains in force. Stop and ask the repository owner to check
the actual official App only when one of these occurs:

- the owner observes wording in the official App that differs from a maintained
  mirror;
- the needed mirror text is omitted, truncated, or genuinely ambiguous;
- co-versioned 40k.app and Game Datamissions observations disagree;
- the App corpus contains internally incompatible statements that stable title
  plus complete operative text cannot resolve;
- applicability depends on an App build, locale, or tournament cutoff that has
  not been selected; or
- a later source-policy decision withdraws or narrows this authority.

The disambiguation record must identify the category/rule, provider, URL, App
version/build if available, platform, locale, observation timestamp, exact
conflicting statement, affected finding IDs, chosen interpretation, and
supersession scope. Retained capture bytes and hashes are preferred when mirror
equivalence itself is disputed. Until the exception is resolved, mark the row
as conflicting and block semantic certification.

This policy does not authorize faction, faction-detachment, or faction-datasheet
review and does not expand any scope prohibited by `AGENTS.md`.
