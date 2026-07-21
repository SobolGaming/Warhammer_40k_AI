# Phase 17K Wahapedia bridge test decomposition

This note records the equivalence audit for removing
`tests/unit/test_phase17k_wahapedia_bridge.py`. The split preserves the original
behavioral case names and parameter IDs while assigning each invariant to the
layer that owns it.

## Original test to owner map

All original `test_phase17k_*` function names are unchanged. The owner for each
original test is determined by the invariant family below; the counts are
unique test functions, before parameter expansion.

| New owner | Original functions | Invariant family |
| --- | ---: | --- |
| `tests/unit/rules/test_wahapedia_bridge_catalog.py` | 18 | Canonical catalog construction, geometry, wargear, attachment, and unit-resource data |
| `tests/unit/rules/test_wahapedia_bridge_normalization.py` | 11 | Source normalization, descriptors, source IDs, damaged profiles, and RuleIR spans |
| `tests/unit/rules/test_wahapedia_bridge_diagnostics.py` | 6 | Fail-fast bridge diagnostics and unsupported source paths |
| `tests/unit/engine/test_catalog_rule_ir_classification.py` | 7 | RuleIR consumer classification, hook inventories, coverage classification, and strict validators |
| `tests/unit/engine/test_catalog_weapon_ability_runtime_helpers.py` | 2 | Private weapon-choice payload and keyword-grant helper validation |
| `tests/unit/engine/test_catalog_post_shoot_runtime_validation.py` | 1 | Private post-shoot payload and status validation |
| `tests/integration/test_catalog_rule_ir_runtime.py` | 9 | Catalog RuleIR activation through real army, state, decision, and runtime consumers |
| `tests/integration/test_catalog_wargear_runtime.py` | 3 | Wargear RuleIR behavior through battle-shock, charge, and damage consumers |
| `tests/integration/test_catalog_weapon_ability_runtime.py` | 4 | Named weapon choices through the decision and runtime modifier path |
| `tests/integration/test_catalog_post_shoot_runtime.py` | 6 | Attack-sequence events through post-shoot consumers |
| `tests/integration/test_catalog_movement_runtime.py` | 8 | Movement eligibility, rerolls, reserves, and scoped records |
| `tests/integration/test_catalog_movement_completion_runtime.py` | 2 | Charge/movement completion mortal-wound consumers |

The former global snapshot test had several independent owners and therefore
does not map one-to-one:

| Former invariant | New owner |
| --- | --- |
| Exact committed JSON and global Markdown content | `tests/code_quality/test_generated_ability_support_artifacts.py` |
| Exact committed faction Markdown set, order, and content | `tests/code_quality/test_generated_faction_docs.py` |
| Ability, category, datasheet, mustering, faction, and detachment inventory completeness | `tests/unit/reporting/test_support_evidence_inventories.py` |
| Cross-faction army-rule runtime consumer aggregation | `tests/unit/reporting/test_runtime_consumer_evidence.py` |
| Runtime manifest semantic-status aggregation | `tests/unit/reporting/test_runtime_semantic_coverage.py` |
| Renderer headings, ordering, escaping, and empty cells | `tests/unit/reporting/test_support_renderers.py` |
| Chaos Daemons faction-specific report evidence | `tests/unit/reporting/test_chaos_daemons_support_report.py` |
| Aeldari faction-specific evidence | Existing Aeldari reporting tests, including `tests/unit/test_faction_pack_datasheet_review.py` |

## Collected-node audit

The original file collected 91 cases: 90 behavioral cases plus the global
snapshot test. After removing the snapshot test, the normalized original and
decomposed node IDs compare exactly:

```text
original behavioral cases:   90
decomposed behavioral cases: 90
comm -3 result:              empty
```

The comparison strips only the file path, retaining each function name and
full pytest parameter ID. In other words, all original parameterized cases are
present, not merely all original Python function names.

Coverage was also captured once from the original 91-case file and once from
the behavioral replacement set, excluding code-quality freshness tests, against
the same production tree. Both runs
covered 41.18882643538189% of the full `warhammer40k_core` package. Comparing
every production-file percentage produced no positive or negative deltas; in
particular, no production module lost coverage in the decomposition.

The replacement reporting suites add focused cases beyond those 90. Artifact
freshness is intentionally classified as code quality; reporting semantics are
ordinary unit tests; live multi-subsystem consumers are integration tests.
None of the original or replacement tests uses an explicit pytest marker, so
marker selection is unchanged. Suite ownership is expressed by directory,
consistent with the rest of this repository.

## Shared fixture boundaries

The shared helpers are split by dependency direction:

- `wahapedia_source_fixtures.py` caches only the immutable tuple of parsed
  source artifacts; every bridge, catalog, army, unit, state, attack sequence,
  and event object is constructed fresh.
- `wahapedia_bridge_fixtures.py` owns bridge-artifact construction.
- `catalog_package_fixtures.py` owns canonical packages, armies, and units.
- `catalog_runtime_fixtures.py` owns fresh battlefield/state construction and
  event emission.
- `catalog_rule_ir_fixtures.py` owns RuleIR and coverage-value constructors.

No support module contains tests or assertions, and every new Python file is
below the 1,500-line module limit.
