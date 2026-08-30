# 40k.app core-rules observation artifacts

These artifacts retain observations from a non-affiliated hosting provider. Under repository-owner
policy `core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26`, the Core Rules
corpus is treated as a verbatim authoritative mirror of the maintained Warhammer 40,000 App.
Maintained App wording supersedes older PDF wording where they differ. This authority decision does
not relabel the provider as Games Workshop or claim endorsement; see
`docs/CORE_RULES_SOURCE_POLICY.md`.

The live website is not runtime input. Reviewed, normalized, hash-pinned source artifacts are the
loader boundary.

The audit contains category URLs, section identities, short paraphrased source findings,
implementation-review dispositions, planned remediation PR IDs, status fields, immutable
source-observation SHA-256 fingerprints, and full review-row SHA-256 fingerprints. The itemized
implementation findings live in
`docs/CORE_RULES_REMEDIATION_ROADMAP.md`. The audit intentionally contains no scraped HTML, page
bundles, screenshots, or copied page bodies. The source-observation hash excludes implementation
status and remediation planning; the full row hash detects any checked-in review-row change.
Neither authenticates the external website.

CI remains offline. Validate the artifact and generated report with:

```text
uv run --no-sync python tools/core_rules_40k_app_audit.py --check
```

Refresh source-observation and full review-row hashes after a reviewed audit edit, then regenerate
the report with:

```text
uv run python tools/core_rules_40k_app_audit.py --update-evidence-hashes
uv run python tools/core_rules_40k_app_audit.py
```

P15D's exact reviewed 15.05-15.09 source rows and the Fight 12.01 numbering anomaly live in the
packaged `core_stratagems_2026_08/artifacts/package.json` loader boundary. After an intentional
reviewed edit, refresh only its derived transcription, observation, and package hashes with:

```text
uv run python tools/build_core_stratagem_app_source.py
uv run python tools/build_core_stratagem_app_source.py --check
```

The loader's reviewed byte, package, per-row transcription/observation, and numbering-anomaly
transcription/observation pins must be updated in the same change. The builder is offline and never
queries the live provider.

P08A and P08B's ordered Command-phase source rows live in the packaged
`core_command_phase_2026_08/artifacts/package.json` loader boundary. Its retained 2026-08-26
search-index observation at `https://www.40k.app/rules` is authoritative `RuleEvidence` for the
exact normalized five-heading sequence from Start of Command Phase through End of Command Phase.
The artifact pins the actual URL and timestamp, every normalized heading and transcription hash,
the ordered sequence text and hash, and a source-observation fingerprint whose canonical input
includes that URL, timestamp, scope, text, and order. The older category-08 audit record remains
category-locator metadata only; its fingerprint does not certify an exact heading or operative
statement, and the audit retains no category-page body. Complete 08.01 through 08.03 operative text
is separately transcribed from the retained official Core Rules PDF. The 08.03 source row remains
`partial_engine_runtime` only because P01 retains the off-battlefield embarked and Strategic
Reserve extension; P08B's on-battlefield scope is executable. After an intentional reviewed edit,
refresh only the derived transcription, observation, and package hashes with:

```text
uv run python tools/build_core_command_phase_source.py
uv run python tools/build_core_command_phase_source.py --check
```

The loader's reviewed byte, package, search-index sequence observation, per-heading transcription,
official-PDF text transcription, source identity, ordered-row, support-status, and runtime-consumer
pins must be updated together. The builder is offline and never queries the live provider.

P09A's exact 09.02 Move Units sequence lives in
`core_movement_phase_2026_08/artifacts/package.json`. The artifact pins the reviewed URL,
observation timestamp, complete Select Unit location set, complete move-type list, transcription
hash, evidence observation hashes, execution status, and runtime consumers. The older category-09
audit row remains locator metadata and does not authenticate this exact excerpt. After an
intentional reviewed edit, refresh its derived hashes offline with:

```text
uv run python tools/build_core_movement_phase_source.py
uv run python tools/build_core_movement_phase_source.py --check
```

The typed loader's reviewed artifact-byte pin must be updated in the same change.

The current scope is exactly the 25 core-rules categories. Factions, faction detachments, and
faction datasheet content is explicitly excluded.
