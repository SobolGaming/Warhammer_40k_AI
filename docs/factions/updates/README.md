# Faction update pipeline (Track U)

[Faction roadmap](../../FACTION_RULES_REMEDIATION_ROADMAP.md) · [S2 identity model](../identity/S2_IDENTITY_MODEL.md) · [Track T taxonomy](../taxonomy/README.md) · [Observation register](../../FACTION_AUDIT_SOURCES.md)

Pre-gate update-pipeline design lives here as planning evidence. It does not
admit content, change catalogs, implement the S4 diff tool, classify live
pages, or emit task packets. FM0 implements U1–U8 from retained pages and
reconciles them with these documents.

| ID | Document | Status |
| --- | --- | --- |
| U2, U3, U4 | [Classification system](U_CLASSIFICATION_SYSTEM.md) | FM-pre design delivered: diff grain, impact classes, layer demotion. S4 tool, classifier, invalidation, and packets remain FM0 |
| U1, U5, U6, U8 | Capture, tombstones, rewrite procedure, runbook | Not this folder yet |
| U7, U7a | Retention and replay compatibility | Not this folder yet |

Machine-readable catalog (planning evidence, not a runtime artifact or
content-set record): [`u_classification_system.json`](u_classification_system.json).
