# 39k PRO observation artifacts

These artifacts retain secondary-reference observations used by generated support reports. They
are review evidence, not runtime catalog input, and official GW artifacts remain authoritative.

Each audit pins the observed provider asset URL and SHA-256, the exact source snapshot artifacts,
source/provider datasheet name pairs, and one row per source assignment. Assignment rows retain the
provider relationship record, definition record, display identity, qualifiers, comparison status,
and discrepancy reason. Datasheet and assignment `evidence_sha256` values are SHA-256 digests of
the canonical JSON provider-observation fields validated by
`tools/emperors_children_39k_pro_audit.py`.

CI does not contact the provider. The typed loader instead fails closed on source snapshot drift,
missing or duplicate observations, URL/name swaps, category or qualifier drift, invalid provider
record identities, and conclusions that disagree with the retained row-level evidence.
