# R73-001 contact-plane correction

Matched base/head runs reuse the unchanged Order 60 component and Order 73
facade workloads, helpers, dependency lock, provisional host and budgets.
The base is the reviewed PR commit `516f75c31626aa883ed3e488eba5807148bc6faa`
(runtime `bc075ee4`), measured serially before this production correction.
The head identifies the corrected runtime. Both workloads completed all base
samples; the original Order 73 unsupported base remains in the parent directory.

These retained workloads assess regression cost. The eight focused objective
regressions separately prove the corrected marker semantics; the benchmark
fixtures are unchanged and are not a new marker-specific performance claim.
All qualified measurements run without coverage or competing test/build jobs.
No budget is raised. Whole-game targets and PFINAL remain uncertified.

| Workload | Base mean / maximum | Corrected mean / maximum | Complete samples per revision |
| --- | --- | --- | --- |
| Five-model component | 0.011922 / 0.062500 seconds | 0.012026 / 0.061946 seconds | 7/7 |
| Actual facade submissions | 1.248366 / 2.123744 seconds | 1.243493 / 2.152611 seconds | 12/12 |

The nine focused performance evidence guards pass, including the seven inherited
current-runtime reports and both original/corrected Order 73 report pairs.

Current results: [validation.json](validation.json).
