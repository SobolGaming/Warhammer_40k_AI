# Unrestricted Action workload: cold visibility accounting

Order 93's final gate exposed a pre-existing measurement mismatch: the unchanged
Order 34 unrestricted live slice computes 12 visibility pairs against its former
seven-pair limit. The same isolated test fails on the untouched Order 93 base.
This is not presented as a passed historical budget.

Order 91 (`ad096b7f`) made shooting-unit selection independent of target legality.
Previously, fixture setup queried the first shooting model against five enemy
models, warming those five pairs before profiling began. It also queried the
engaged observer's two models against six enemy models, work no longer required
for selecting that unit. The live declaration still checks both firing models
against five enemy models and the engager: twelve pairs in total.

Fresh-process measurements with explicit cache resets demonstrate the change:

| Source | Setup pairs | Live pairs | Cold total |
| --- | ---: | ---: | ---: |
| Pre-Order 91, `cacde87c` | 19 | 7 | 26 |
| Order 93 base, `d7bcb10b` | 2 | 12 | 14 |
| Order 93 repaired head, `6ba430dc…` runtime | 2 | 12 | 14 |

Both cached-resolver body entries and uncached solver calls have these counts.
They are primitive calls from one function definition, not recursive counts or
same-name aggregation. The setup's two remaining pairs belong to fixture
construction. The driver and shooting fixture bytes, accepted declaration,
actual dice payloads, final model wounds, six decisions, 32 effects and final
Fight phase match across all three revisions. Exact identities, hashes and
model-pair inventories are in [the retained proof](visibility-boundary-evidence.json).
Instrumented wall times are excluded from this evidence.

The current calibration explicitly changes only the unrestricted geometry
measurement boundary. Its cold ceiling is **26**, derived from the historical
19 setup calls plus the original seven live calls. The old seven-call values
remain recorded as historical slice limits. All nongeometry limits still apply
to the original live interval; attached-selection and retained limits are
unchanged. This is a documented metric migration, not a claim that all budgets
were unchanged.

The driver clears the complete target-candidate cache and the visibility context
fingerprint, context result, physical-obstacle and geometry result caches before
setup. It profiles setup and live execution separately, retains both counts and
checks their sum. There is no warmup, cache insertion, geometry shortcut, seed
change or altered declaration. The quality regression repeats the unrestricted
case and interleaves attached selection to check cache-order independence.

Run the check with:

```sh
uv run pytest tests/code_quality/test_order34_action_restrictions.py -q --no-cov
```

The separate [Action work report](action-work-counts.json) also records the
permission-source probe repair. Its phase-expiry guard suppresses no-op mutation
method entries; it does **not** reduce expiration predicate scans. The measured
paths each add one short-circuit predicate check, explicitly retained in that
report, while the source probe reduces rules-unit and effect-applicability work.
