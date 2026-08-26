# Core Rules Source Authority Policy

## Decision

- Policy ID:
  `core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26`
- Decision date: 2026-08-26
- Decision owner: repository owner
- Scope: Warhammer 40,000 11th Edition Core Rules categories 01–25 only

The repository owner attests that the Core Rules corpus hosted by 40k.app is a
verbatim representation of the maintained Games Workshop Warhammer 40,000 App.
For this project, a pinned 40k.app observation is therefore an authoritative App
mirror. When that maintained App wording differs from an older Games Workshop
PDF, the App wording supersedes the PDF for the affected rule and version.

This is a project authority decision. It does not claim that 40k.app is owned,
affiliated with, or endorsed by Games Workshop. Evidence records must continue
to identify 40k.app as the hosting provider and retain its non-affiliation
marker. They use `project_authoritative_app_mirror`, never
`official_primary`, unless the retained artifact actually came from Games
Workshop.

## Operational rules

1. Pin the 40k.app URL, observation timestamp, transcription hash, and retained
   source-observation fingerprint used by a source row. Keep that immutable
   fingerprint separate from the full review-row hash so implementation status
   and PR-plan edits do not change source identity.
2. Preserve official PDF artifacts and hashes as historical primary evidence.
3. Where the App mirror and PDF differ, record the drift and use the App mirror
   wording; do not merge the two texts.
4. Keep provider numbering separate from stable project IDs. If App headings or
   cross-references are internally inconsistent, bind behavior by rule title and
   complete operative statement and record the numbering anomaly.
5. The live website is never queried by the game engine. Reviewed, normalized,
   hash-pinned source artifacts are the data boundary consumed by loaders.
6. Owner transcriptions and mirror observations remain separate evidence
   records even when their text matches.
7. A row absent from, or conflicting with, the authoritative App mirror is not
   certified merely because an older repository transcription exists.
8. Load support and semantic execution status remain separate and truthful.

## User disambiguation exception

Routine rule work does not require a second official-App capture while this
policy remains in force. Stop and ask the repository owner to check the actual
official App only when one of these occurs:

- the owner observes wording in the official App that differs from 40k.app;
- 40k.app omits, truncates, or ambiguously renders the operative statement;
- the App corpus contains internally incompatible headings, examples, or
  cross-references and rule title plus operative text do not resolve behavior;
- applicability depends on an App build, locale, or tournament cutoff that has
  not been selected; or
- a later source-policy decision withdraws or narrows this attestation.

The disambiguation record must identify the category/rule, App version/build if
available, platform, locale, observation date, exact conflicting statement,
affected finding IDs, chosen interpretation, and supersession scope. A
retained screenshot/recording and hashes are preferred when the App/40k.app
equivalence itself is disputed. Until the exception is resolved, mark the row
as conflicting and block semantic certification.

This policy does not authorize faction, faction-detachment, or faction-datasheet
review and does not expand any scope prohibited by `AGENTS.md`.
