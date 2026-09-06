# F00 faction source governance review

Generated offline by `uv run python tools/build_faction_source_governance.py`.

Policy: `faction-source-policy:maintained-direct-app-data-mirror:2026-09-05`. Selected App-data: **946**, locale `en`.
Retained artifact SHA-256: `b24acc551927200dfc5562b509ce5138dddf7841dd2b5eb394ff4e2528f010b5`.
Canonical source-catalog SHA-256: `81ab4a71ea5e22f4fae34a657c49e5abcbfce37977bb1a32ed72917d4532eb91`.

These three complete observations exercise faction, detachment and datasheet package governance. They are a bounded source selection, not the F01 corpus reconciliation. Page source IDs are stable provenance identities, not runtime rule or catalog IDs. Each page still needs clause-level identity and consumer review before execution.

| Source page | Kind | Observation fingerprint | Load | Execution |
| --- | --- | --- | --- | --- |
| [Adepta Sororitas army rules](https://www.40k.app/factions/adepta-sororitas/army-rules) | faction | `b6b959e996a5616b29e9595889a0501b7d3d49891a194a170eb05e5d8f063091` | loaded | not certified |
| [Sanctified Orators](https://www.40k.app/factions/adepta-sororitas/detachments/sanctified-orators) | detachment | `f69f04398ac2b49ffd999e74e6003ddc3b5d4229dda0c0bcbeddf087363c9fa6` | loaded | not certified |
| [Exorcist](https://www.40k.app/factions/adepta-sororitas/units/exorcist) | datasheet | `549cee4dfb3ad4bba0ffa8d4be6c65c4fce8610a6766ea5f6b90fd8a1fc8beda` | loaded | not certified |

## Source and geometry limits

40k.app is a non-affiliated maintained mirror. The current observation is project authority, never official-primary evidence. The retained July Games Workshop PDF keeps its independent URL and hash as historical primary evidence; no current corroboration or unchanged-clause claim is inferred from that relationship.

The Exorcist page supplies Hull, but no dimensions or height. Its geometry obligation blocks fieldability pending accepted, variant-specific ModelGeometryCatalogRecord evidence. Source loading cannot accept a default base, zero height, or an invented measurement. F06 owns those measurements.

The captured text preserves each complete main element. Operative text begins at the reviewed heading and includes the remainder, including points, choices, restrictions, profiles, subrules, examples and damaged sections where present. Page navigation may remain in that retained document; it is not gameplay semantics. Normalization reuses the shared non-Core objective terminology boundary.

The source invariant is enforced at observation parsing, the reviewed byte pin, the authority registry, RuleEvidenceRecord, and RuleSourcePackage. Source IDs are globally unique across documents. Package version/date derive from the audit; the registry authenticates the full canonical catalog hash. Recomputed hashes alone cannot authorize new text, owners, URLs, source identities or catalog metadata. Conflicts, ambiguous identity, mixed versions/locales and excluded classifications fail closed. No site is fetched by the loader.

Candidate validation checks structural completeness: schema, declared review status, capture/suffix relationship and hashes. Human review establishes actual provider-page completeness, authenticated by the immutable byte pin. A mutually truncated capture and suffix can pass structural validation after rehashing, but cannot pass the reviewed pin. Official artifact paths must be normalized relative POSIX paths, and the shared checksum reader requires resolved containment beneath the artifact root, including symlink targets.

## Remaining work

F01 owns all remaining admitted URLs, provider/catalog crosswalks, historical deltas and the Warbuggies identity hold. F02-F09 own gameplay and roster certification. Acts of Faith's turn-start change is retained here; its consumer is unchanged.
