# Order 40 component performance

This is a provisional local component assessment, not complete-game certification.
The standing mean-under-60s / observed-maximum-under-300s full-game targets and
Order 32 deferral are unchanged.

The same script, interpreter, lock and fixtures measure base `506dad94` and head.
Four cases use three canonical models and no terrain: no grant, direct Cover,
an obscuring source, and a source outside the line of sight. Each of seven samples
prepares a fresh real lifecycle and measures ten attack-modifier queries. Setup
is measured separately. JSON retains all samples, environment, hashes, summaries,
completion and throughput. The base lacks the new geometry consequence and is
only a cost comparison. No policy search, coverage or profiling is included.

The numeric budget was set before head measurement: mean <= 1.5 times base plus
10 ms, maximum sample-average query <= 20 ms. This allows the added exact causal
query while bounding an estimated 1,000-query workload to 20 seconds within the
60-second objective. That call count is an estimate; no full-game extrapolation
is certified. Maximum/P95 concern sample averages, not a universal per-call bound.
No scenarios, failures or prior thresholds were discarded or weakened.

Reproduce using `PYTHONPATH=.:src uv run python scripts/measure_smokescreen_cover.py
--output docs/performance/order40/head.json`. Export the base into an isolated
checkout and copy the identical measurement script and its named fixture helper;
use the same Python runtime with that checkout first on PYTHONPATH. Run without
competing workers, after regenerating runtime identity. The required static gate
checks retained comparability, completion and numeric thresholds. Existing bounded
visibility caches retain their independent correctness/cache regressions.

## Recorded result

On the Apple M5 Pro / Python 3.14.5 host, all four cases completed all seven
samples and passed the unchanged budget. Head mean query times are 0.073 ms
(plain), 0.207 ms (direct), 1.908 ms (obscured) and 0.444 ms (clear). The largest
sample-average query is 2.120 ms. Base means are 0.152, 0.054, 0.048 and 0.048 ms,
respectively. These include cold samples; no warm-up samples are discarded.
Base and head retain identical script, fixture, lock, interpreter and environment
identities, and separate engine manifests. Gameplay-slice and full-game timings
were not measured by this assessment.
