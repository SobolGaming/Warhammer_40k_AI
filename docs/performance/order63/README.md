# Order 63 component measurements

The matched workload selects an unloaded reserve Transport, submits its ordinary
Ingress placement, and restores the serialized lifecycle. Both base `25ec75b6`
and head accept this case. Seven serial samples use the same current fixture,
script, dependency lock and provisional host. Preparation is recorded separately.
No dice, profiling, coverage or competing test workers are included in measurement.

The versioned matched component gate retains the previous Transport assessment's
limits: twice the base mean plus 20 ms, and twice the base maximum plus 50 ms.
These broad diagnostic regression limits accommodate host variability. A separate
head-only sample measures loaded ingress, Rapid Disembark and authenticated
restore; the incorrect base rejects loaded ingress, so no equivalent successful
base timing exists. It remains an unpaired component diagnostic.

Reproduce with `scripts/measure_order63.py --output <path> --revision <identity>
--runtime-src <checkout>/src`. Add `--loaded` for the new accepted cargo path.
Machine-readable reports retain all samples, host details and input hashes.

The provisional host is Windows 11, Python 3.14.5, AMD Ryzen Threadripper 3970X
(32 cores / 64 logical processors), with 137,327,259,648 bytes of physical memory.

| Workload | Mean seconds | Maximum seconds |
| --- | ---: | ---: |
| Base unloaded ingress + restore | 1.014 | 1.077 |
| Head unloaded ingress + restore | 1.044 | 1.149 |
| Head loaded ingress + Rapid Disembark + restore | 4.067 | 4.155 |

The matched mean increased by 3.0%; the maximum increased by 6.6%. Both pass the
recorded limits (mean 2.048 seconds; maximum 2.205 seconds). All seven samples
completed for each revision.
The loaded path also completed all seven samples; it is diagnostic only, with no
successful base equivalent against which to enforce the matched regression gate.

Gameplay slices and complete head-to-head games remain unmeasured. These component
results do not certify the 60-second mean / 300-second maximum full-game targets
or the deferred Order 32 budgets. Final validation is recorded in `validation.json`.

Final validation passed 8,430 behavioral tests at 85.11% coverage, all 535
code-quality tests, all required lint/type/import/pre-commit checks, the exact
eight-shard inventory check, reproducible source/build/contract generation,
installed-wheel smoke, five TypeScript client tests and 342 conformance assertions.
No production code changed after the successful coverage run.
