# Order 46 Charge performance evidence

This is a matched component/gameplay-slice assessment on provisional local
reference hardware, not a complete-game certification. Both revisions use the
same final benchmark script, canonical fixture, dependency lock, seed, roster,
15 models, zero terrain, two-segment paths and concurrency one. The base is
`63b4030a382787783f6364c0badbf70fd79aa15c`; the head JSON records the working-tree runtime build ID.
The fixture changes are shared by both measurements and do not modify base
production code. Host CPU, memory, platform, interpreter, script/fixture/lock
hashes and all seven samples are retained in the JSON files.

| Measurement | Base | Head |
| --- | ---: | ---: |
| Mean Charge slice | 0.027935 s | 0.029542 s |
| Maximum measured slice | 0.030012 s | 0.033635 s |
| Decisions | 2 | 3 |
| Events | 48 | 51 |

The measured boundary starts with charging-unit selection and ends after an
accepted Charge path and the next decision. Initial roster/lifecycle preparation
is measured separately. Head adds the required finite target commitment; both
runs finish the same physical move. The predeclared limits in `budgets.json`
are unchanged: mean no greater than twice base plus 0.05 seconds, maximum no
greater than 0.5 seconds, at most three decisions and 75 events. All samples
complete and these slice limits pass.

Reproduce in each checkout after copying the identical benchmark script and
`tests/phase15a_charge_declaration_helpers.py` to the base:

```bash
PYTHONPATH=src:. uv run --no-sync python scripts/measure_charge_distance.py \
  --samples 7 --output docs/performance/order46/head.json
```

This small slice does not measure many-target option growth, complex-terrain
endpoint solving, or complete head-to-head games. Those limits are explicit;
no timeout or unresolved calculation is converted into a rules answer.
The standing full-game mean below 60 seconds and observed maximum below
300 seconds remain unmeasured here. Order 32's deferred certification is not
claimed by these results.
