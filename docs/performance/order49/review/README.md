# PR 469 review performance

Workload `order49-review-cost-and-replay-v1` compares reviewed commit `61543817`
with the fixes on the same provisional Apple M5 Pro / macOS 26.6.2 host, Python
3.14.5, 18 CPUs and 64 GiB RAM. Seven serial samples use identical script,
fixture and lockfile hashes, without coverage or competing test workers.

| Timed workload | Base mean | Head mean | Base maximum | Head maximum |
| --- | ---: | ---: | ---: | ---: |
| Catalog fixture through discounted Hit window | 0.561541 s | 0.563170 s | 2.204268 s | 2.217712 s |
| Replay with checkpoint at 84 and tail to 92 events | 0.361563 s | 0.369954 s | 0.362440 s | 0.378059 s |

The attack timing includes cold catalog construction in the first sample;
medians are 0.287722 s and 0.287468 s. The initial provisional two-second absolute
attack ceiling fails on both base and head cold samples. `budgets-initial.json`
retains that failed calibration. The current three-second setup-inclusive
ceiling allows the observed cold preparation with margin. The relative
2x + 50 ms mean guard, two-second replay ceiling, work-count limits and standing
full-game targets are unchanged. This calibration is not a claimed pass of the
initial limit.

Both versions produce 22 events / five decisions at the Hit window and 92 events /
four decisions in replay. Base displays the wrong reroll cost and reports replay
as `drifted`; head displays the discounted cost and reports `reproduced` in every
sample. Base is a cost comparison, not a correctness oracle. The required static
quality gate checks matching inputs, final budgets and successful head replay.

```bash
PYTHONPATH=src:. uv run --no-sync python scripts/measure_order49_review.py --samples 7 --output docs/performance/order49/review/head.json
```

Copy the final script and `tests/command_reroll_cost_helpers.py` into an isolated
checkout of `61543817`, and run it with the same Python environment for base.
Raw samples and runtime diff hashes are retained in `base.json` and `head.json`.
The behavioral suite separately covers all four discounted attack roll kinds,
restore, multiple checkpoints, corrupt projections and subsequent decisions.
No full-game certification is claimed.
