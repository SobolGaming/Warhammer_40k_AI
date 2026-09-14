# R47-001 Charge restore diagnostic

The seven-sample workload restores a completed attached Charge with a source-backed
FLY leader, a nonzero vertical gap and a proven unreachable preferred endpoint.
It compares reviewed commit `cd46c143` with the fixed runtime identity in `head.json`.
The isolated base receives only the identical benchmark and two named fixture helpers;
its production code is unchanged. All checkpoint, script, fixture, lock and machine
hashes match. Each process performs one declared warmup restore before timing seven
restores. Setup and output equality assertions are outside the timed boundary.

| Restore measurement | Base | Head |
| --- | ---: | ---: |
| Mean | 0.090434 s | 0.090258 s |
| Maximum | 0.091107 s | 0.091206 s |
| Completed samples | 7/7 | 7/7 |

Both revisions restore this pre-casualty checkpoint identically. The regression
separately demonstrates that base rejects the later retained flying-leader casualty
while head accepts it; base is not a correctness oracle for that scenario. The
bodyguard-casualty control remains valid. This is an uninstrumented restore-only
diagnostic on provisional Apple M5 Pro hardware with concurrency one. It does not
certify a complete game, gameplay-slice throughput, worst-case solver work or the
component budgets deferred by Order 32. Existing Charge slice reports and their
versioned limits remain unchanged; no budget is raised or newly claimed here.

Reproduce on both revisions with the identical final helper and script files:

```bash
PYTHONPATH=src:. uv run --no-sync python scripts/measure_charge_endpoint_restore.py \
  --output docs/performance/r47-001/head.json
```
