# Order 36 performance assessment

For the initial Order 36 publication (`57957112`), all final uninstrumented
samples and separate work profiles completed. The
unchanged Order 34 and Order 35 budgets pass. Initial retained identity-query and
Rapid Ingress timing failures are preserved under `initial/`.

The measured repairs avoid repeated identity work for an empty Battle-shock
registry, repeated reserve enumeration, duplicate configuration validation,
unneeded charge-reroll registry loading and repeated replay-payload validation
while checking discovery purity. Discovery still checks every provider against
an independent snapshot of all state, pending choices, records and events;
nested mutation and event mutation regressions fail before the next provider runs.

| Workload | Base mean s | Head mean s | Head max s | Mean change |
|---|---:|---:|---:|---:|
| action | 0.10889 | 0.11289 | 0.12623 | +3.67% |
| unrestricted | 0.06261 | 0.06006 | 0.09279 | -4.07% |
| attached_selection | 0.00354 | 0.00353 | 0.00377 | -0.16% |
| retained | 0.19403 | 0.21760 | 0.25697 | +12.15% |

Rapid Ingress uses Order 35's existing 1.5× base mean plus 1 ms allowance and
per-case maxima, with independently enforced work counts.

| Rapid Ingress case | Base mean s | Head mean s | Head max s | Mean change |
|---|---:|---:|---:|---:|
| legal | 0.010732 | 0.016626 | 0.017027 | +54.92% |
| first_round | 0.000029 | 0.000032 | 0.000033 | +12.15% |
| aircraft | 0.000082 | 0.000094 | 0.000101 | +14.72% |
| mixed | 0.061432 | 0.074589 | 0.100668 | +21.42% |
| placement | 0.116161 | 0.162614 | 0.189029 | +39.99% |

Base: `05ca3d8506a695d2a1e0b36ccb5b828dfb7f505a`. The final report binds
engine manifest SHA256 `390231096e85983215cb4c0ba841706c59bbe79dd049f6670c3df594463838a0`.
Hardware: Apple M5 Pro, 68719476736 bytes RAM, macOS-26.6.2-arm64-arm-64bit-Mach-O,
Python 3.14.5. Measurements ran serially without competing task-owned
test workers, coverage or profiling. Setup is recorded separately. Profiling
ran in separate processes. This local host is provisional.

The existing benchmark drivers and lock are identical across revisions. Each
runtime uses its canonical fixtures because the P01D-specific sequencing types
are unavailable on main. `input-manifest.json` preserves both sets of hashes.
The Rapid Ingress raw reports likewise preserve both fixture hash inventories.
This is a cost comparison of the same declared workloads; it is not a claim of
byte-identical setup or correctness equivalence with the old rules order.
`benchmark-spec.json` defines the measurements; `budget-validation.json` records
the unchanged limits' outcomes. `rapid-ingress-validation.json` records the
additional Order 35 comparison. These are bounded cost measurements, not a claim
that every workload became faster.

Reproduce in isolated base/head checkouts using the same Python environment:

```bash
PYTHONPATH=.:src /path/to/python -m scripts.measure_action_restrictions \
  --samples 7 --output /path/to/reports/action-timing.json
PYTHONPATH=.:src /path/to/python -m scripts.measure_action_restrictions \
  --samples 7 --live-case retained --output /path/to/reports/retained-timing.json
```

Repeat the live command for `unrestricted` and `attached_selection`. Run each
case separately with `--samples 1 --work-counts` for work evidence. Compare with
`docs/performance/order34/budgets.json`; do not run concurrent timing workers.

For Rapid Ingress, run `scripts/measure_rapid_ingress.py --samples 7 --output`
with a report path, and a separate `--samples 1 --work-counts` run, in each checkout.
The original identical-fixture Order 35 comparison remains unchanged; Order 36
records fixture migration differences explicitly and uses the same numeric budgets.

Full attached-declaration diagnostics remain incomplete as recorded in Order 34;
attached selection does not replace that diagnostic. Complete-game performance
is uncertified. No timeout became a rules answer, no budget was raised, and no
Order 32 deferral was extended to Order 34's required gates.

## R36-001 restoration correction

`r36-001-restoration.json` compares the changed restoration validator with
`57957112` on identical real retained-shooting state and decision/event history.
Seven alternating base/head batches of 100 calls measured mean costs of 6.216 µs
and 8.473 µs per call, respectively (+2.257 µs). Construction is excluded and
recorded separately; both versions completed every call. The report embeds the
exact measurement script, source/lock hashes and provisional host metadata.
This measures only the validator, not complete checkpoint restoration or games.
The base is a cost comparison, not an ordering-correctness oracle. The earlier
Order 34/35 reports above remain evidence for their recorded runtime identity.

The additional work is a decision/event scan for each live attack scope (at most
one Fight and one out-of-phase shooting continuation), followed by sorting the
small active stack. It adds no per-action mutation, geometry query or cache.
The ordered-stack regressions and static audit run in the existing CI gates.

To repeat this diagnostic from the repository root with the locked environment:

```bash
uv run --no-sync python - <<'PY'
import json
from pathlib import Path
report = json.loads(Path("docs/performance/order36/r36-001-restoration.json").read_text())
Path("/tmp/r36-001-measure.py").write_text(report["measurement_script"])
PY
PYTHONPATH=.:src uv run --no-sync python /tmp/r36-001-measure.py
```

Run without coverage, profiling or competing test workers. The command rewrites
only its diagnostic report; it does not replace the versioned gameplay budgets.
