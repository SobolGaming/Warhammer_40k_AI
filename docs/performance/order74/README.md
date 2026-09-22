# P03C mandatory endpoint proof evidence

The versioned workload is one five-model Charge facade submission with a
3.75-inch movement budget and a feature-owned wall. Three independent samples
clear the shared reachability cache before submission. Fixture construction and
finite target selection are outside the timing boundary. The base is
`54284173293238ea417a1eb1cb0351843a442998`; head records the verified runtime ID.
Both use identical fixture/script/lock hashes and the same provisional macOS
host with one measurement process and no competing test/build jobs.
R74-001 refreshed this pair on an Apple M5 Pro with 64 GiB memory and Python
3.14.5 because the shared fixture gained the attached-unit regression variant.
The timed workload remains the original five-model ordinary Charge; neither
the runtime nor its budget changed. The original Windows measurements remain
available at reviewed commit `9135086a9a081d4a495ea51c35f10df457f696c2`.

The base rejects every sample with the reproduced endpoint-proof gap; the head
accepts every sample and completes the ordinary mutation/advance path. The API
boundary is matched, but accepted and rejected outcomes perform different work.
These timings establish neither a speedup nor a comparable completed-base cost.
The declared head budget is 12 seconds per submission, with every sample legal.
Full games remain unmeasured and the 60/300-second targets are not certified.

Reproduce using the current fixture with each runtime source tree:

```powershell
uv run --no-sync python scripts/measure_order74.py --runtime-src <base-checkout>/src --revision 54284173293238ea417a1eb1cb0351843a442998 --output docs/performance/order74/base.json
uv run --no-sync python scripts/measure_order74.py --runtime-src src --revision <verified-runtime-id> --output docs/performance/order74/head.json
```

The baseline checkout must include its own `pyproject.toml` and canonical
`contracts/schemas`, so its runtime identity can be authenticated. The initial
source-only archive correctly failed that check before measurements; the complete
baseline export was used for the qualified run.

`preflight.json` retains the actual facade rejection and geometric counterexample.
`base.json` and `head.json` retain individual timings and outcomes. Inherited
current-runtime evidence for Orders 64–66, 69–72 and the R73-001 component/facade
pair is also refreshed against unchanged baselines, workloads and budgets.
Their old README tables remain historical; the JSON files identify this runtime.

Final correctness, coverage, package, client and evidence-gate results are recorded
in `validation.json` for the original review and `r74-001-validation.json` for
the attached-unit follow-up. Historical report hashes in the original validation
record refer to the reviewed commit above. PFINAL remains gated on merge and a
fresh complete audit, including representative full-game/headless measurement;
the focused 12-second threshold cannot substitute for the 60/300-second targets.
