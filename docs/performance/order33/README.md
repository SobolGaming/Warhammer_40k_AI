# Order 33 completed shooting slice
Seven uninstrumented samples per case on the same provisional Apple M5 Pro
host and locked environment; separate one-sample cProfile work-count runs.
Every sample requires exactly one attack-sequence completion and one hit step.
The driver runs real Movement choices and restores the session during setup,
which is reported separately from the measured Shooting slice.

| Case | Base mean s | Head mean s | Head max s | Mean change | Base / head LOS calls |
|---|---:|---:|---:|---:|---:|
| visible-self-observer | 0.0944 | 0.1079 | 0.1140 | +14.3% | 44 / 50 |
| unseen-no-observer | 0.3375 | 0.3805 | 0.4289 | +12.7% | 283 / 318 |
| unseen-friendly-observer | 0.2573 | 0.2994 | 0.3292 | +16.3% | 291 / 326 |

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
38 seconds for this one-attack slice alone. This is an estimate, not observed
calls in a complete game: real multi-weapon attack counts, other phases and
setup still need measurement against the standing <60 s mean and <=300 s
observed maximum objectives. Full-game certification is outstanding.

Reproduce from the repository root:

    uv run python -m scripts.measure_indirect_shooting --samples 7 --output timing.json
    uv run python -m scripts.measure_indirect_shooting --samples 1 --work-counts --output work.json
    uv run pytest tests/code_quality/test_order33_indirect_shooting.py --no-cov -q

Reports retain commit, runtime diff, manifest, script/helper/lock hashes. Final head timing identifies commit
5fa1db619def01ae1c67678320512b5747061cf9 and its runtime manifest hash. Earlier incomplete-driver observations remain under
provisional-driver/ and are not delivery evidence. Order 32's exception is not
extended. Correctness and independent review remain separate requirements.

The timed interval starts with an already-pending unit-selection request.
Initial option generation, real Movement choices and persistence restoration
are included in setup. The fixture hash pins this configuration and policy.
Prototype and initial completed-run reports remain available in Git history;
the final reports use the typed profiler API and matching base/head driver hashes.
