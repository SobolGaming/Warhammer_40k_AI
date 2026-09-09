# Order 33 completed shooting slice
Seven uninstrumented samples per case on the same provisional Apple M5 Pro
host and locked environment; separate one-sample cProfile work-count runs.
Every sample requires exactly one attack-sequence completion and one hit step.
The driver runs real Movement choices and restores the session during setup,
which is reported separately from the measured Shooting slice.

| Case | Base mean s | Head mean s | Head max s | Mean change | Base / head LOS calls |
|---|---:|---:|---:|---:|---:|
| visible-self-observer | 0.0967 | 0.1075 | 0.1096 | +11.1% | 44 / 50 |
| unseen-no-observer | 0.3385 | 0.3867 | 0.4384 | +14.2% | 283 / 318 |
| unseen-friendly-observer | 0.2580 | 0.3049 | 0.3344 | +18.2% | 291 / 326 |

All 42 timed base/head slices completed. Head generates the now-legal ordinary
weapon options, and wrapper calls increase by 6 for visible and 35 for unseen
cases. This is consistent with the extra profile eligibility work. Instrumented
exact visibility-pair calculations remain 20 / 20 / 0 on both revisions; the
existing shared geometry cache avoids additional exact solves. The observer
query and attack-modifier builder each execute twice per accepted declaration
(validation and application). No new cache, solver or approximation is introduced.

Initial budgets are in budgets.json: head mean <0.45 s, maximum <0.55 s and
mean/base ratio <1.25 on this provisional host. Observed within-case variation
and the added legal-profile work informed these limits. CI enforces stable work
ceilings, including at most 25 distinct model-pair solves (five by five),
and two observer/build queries per declaration; it does not impose host-specific
timing thresholds on shared runners. The absolute call limits leave bounded
headroom over measured head counts.

An illustrative 100 activations at the slowest measured mean consume about
39 seconds for this one-attack slice alone. This is an estimate, not observed
calls in a complete game: real multi-weapon attack counts, other phases and
setup still need measurement against the standing <60 s mean and <=300 s
observed maximum objectives. Full-game certification is outstanding.

Reproduce from the repository root:

    uv run python -m scripts.measure_indirect_shooting --samples 7 --output timing.json
    uv run python -m scripts.measure_indirect_shooting --samples 1 --work-counts --output work.json
    uv run pytest tests/code_quality/test_order33_indirect_shooting.py --no-cov -q

Reports retain commit, runtime diff, manifest, script/helper/lock hashes. The head
timing was measured before its commit; its runtime manifest hash identifies the
tested production tree. Earlier incomplete-driver observations remain under
provisional-driver/ and are not delivery evidence. Order 32's exception is not
extended. Correctness and independent review remain separate requirements.
