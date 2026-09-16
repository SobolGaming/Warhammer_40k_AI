# Order 52 performance evidence

Seven serial samples on the same provisional Apple M5 Pro host, macOS 26.6.2,
Python 3.14.5, 18 allocated CPUs and 64 GiB RAM. No competing tests, coverage or
profiling ran during timing. Each sample validates two five-model paths on an
open battlefield with ten total models. Fixture setup is measured separately.

| Runtime | Mean seconds | Maximum seconds | Accepted paths |
| --- | ---: | ---: | --- |
| Base 4135da5e | 0.005057 | 0.005985 | full and incomplete |
| Order 52 | 0.006281 | 0.008952 | full only |

`matched-base.json` and `matched-head.json` retain every sample, identical
workload/driver/helper/lock hashes, hardware and exact engine build identity.
The base is a clean `git archive` of 4135da5e; only the measurement driver and
fixture helper were supplied. The explicit `--runtime-layout` option selects
the resolver's old or extracted module. It does not change the workload.
`base.json` preserves the original preimplementation diagnostic measurement.

The predeclared 0.5-second maximum and mean ratio 2 plus 0.02 seconds are unchanged
and checked with path-result counts and the corrected acceptance result by the
Order 52 code-quality test. They are component regression checks, not the deferred
full-game targets. No arbitrary-terrain optimization or complete-game timing
certification is claimed; broader efficiency work remains deferred under Order 32.

The full code-quality gate also exercises the existing Order 35 Rapid Ingress
work budget. It detected 12 attached-unit lookups against a limit of 8 because
lock checks reconstructed unit identity even when the phase contained no Surge.
The exact no-Surge check now returns before those unnecessary lookups. The
before/after profiled reports retain all work counts; the repaired path uses 8
lookups and preserves every existing budget. A phase containing a Surge still
resolves canonical unit/model identity before deciding whether that unit is locked.

Run the same committed driver and fixture against each matching runtime:

```sh
PYTHONPATH=src:. uv run --no-sync python scripts/measure_surge.py --runtime-layout base --revision 4135da5ea81ea998880c334fb743681787c9cfe7 --output base.json
PYTHONPATH=src:. uv run --no-sync python scripts/measure_surge.py --runtime-layout head --revision codex/order-52-surge-movement --output head.json
```
