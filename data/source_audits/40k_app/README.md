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

The current scope is exactly the 25 core-rules categories. Factions, faction detachments, and
faction datasheet content is explicitly excluded.
