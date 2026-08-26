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

The current scope is exactly the 25 core-rules categories. Factions, faction detachments, and
faction datasheet content is explicitly excluded.
