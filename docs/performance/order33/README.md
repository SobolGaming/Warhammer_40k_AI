# Order 33 completed shooting slice
Seven uninstrumented samples per case on the same provisional Apple M5 Pro
host and locked environment; separate one-sample cProfile work-count runs.
Every sample requires exactly one attack-sequence completion and one hit step.
The driver runs real Movement choices and restores the session during setup,
which is reported separately from the measured Shooting slice.

| Case | Base mean s | Head mean s | Head max s | Mean change | Base / head LOS calls |
|---|---:|---:|---:|---:|---:|
| visible-self-observer | 0.1031 | 0.1099 | 0.1145 | +6.6% | 44 / 50 |
| unseen-no-observer | 0.3478 | 0.3904 | 0.4480 | +12.2% | 283 / 318 |
| unseen-friendly-observer | 0.2624 | 0.3040 | 0.3282 | +15.9% | 291 / 326 |

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
ceilings, including at most 25 additional model-pair solves in the timed interval,
and two observer/build queries per declaration; it does not impose host-specific
timing thresholds on shared runners. The exact-solve allowance is the observed 20 plus five solves of headroom;
it is not a universal geometric bound. The wrapper-call limits also leave
bounded headroom over measured counts.

An illustrative 100 activations at the slowest measured mean consume about
39 seconds for this one-attack slice alone. This is an estimate, not observed
calls in a complete game: real multi-weapon attack counts, other phases and
setup still need measurement against the standing <60 s mean and <=300 s
observed maximum objectives. Full-game certification is outstanding.

Reproduce from the repository root:

    uv run python -m scripts.measure_indirect_shooting --samples 7 --output timing.json
    uv run python -m scripts.measure_indirect_shooting --samples 1 --work-counts --output work.json
    uv run pytest tests/code_quality/test_order33_indirect_shooting.py --no-cov -q

Reports retain commit, runtime diff, manifest, script/helper/lock hashes. Final head timing identifies commit
9a1d9cfd5f3e9c05e8c621b0c50e01011ff12a75 and its runtime manifest hash. Earlier incomplete-driver observations remain under
provisional-driver/ and are not delivery evidence. Order 32's exception is not
extended. Correctness and independent review remain separate requirements.

The timed interval starts with an already-pending unit-selection request.
Initial option generation, real Movement choices and persistence restoration
are included in setup. The fixture hash pins this configuration and policy.
Prototype and initial completed-run reports remain available in Git history;
the final reports use the typed profiler API and matching base/head driver hashes.

The R33-001 engagement repair was remeasured on both revisions with matching
driver/helper hashes. Budgets are unchanged; earlier reviewed measurements are
preserved in Git history. The repair adds no engagement or visibility query.
