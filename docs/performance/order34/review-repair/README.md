# R34-003 final repaired-runtime performance evidence

Base: `e56c1a4caf2a6915548222caed0872627f8dbf43`.
Measured runtime/test commit: `5b6752ff07bc5b86e91054a7822ee7ea7dadf7cb`.
Source tree: `7342088900a27801964819690229b8471b59bbc7`.
Engine build: `warhammer40k-core-v2:runtime-tree-sha256-v1:ab699c69e39310e5c158976bdf3169b5ca282c8e3a65163681b59a201e20196e`.
Engine manifest SHA256: `35277d8c1634d8924bc8b722b54d7b94b512e67f07b8ba766c1156ca1c992200`.
Later fixture and evidence commits preserve this measured runtime. The raw reports
retain the exact 5b6752ff workload inputs used on both revisions.
`later-fixture-audit.json` confirms that subsequent changes to the shared primary
mission helper affect only two turn-end functions not called by these drivers;
the measured entry point and its setup are unchanged.

All **98 uninstrumented samples** (seven per base/head case) completed, and all
versioned timing and CI work budgets passed. No original component or difficult
Indirect case was dropped; no existing limit was increased. The eight profiling
samples are separate work-count evidence and are not timing measurements.
The adjacent `benchmark-spec.json` records the complete final workload inventory.
`benchmark-input-manifest.json` pins 15 identical driver, recursive
fixture and lock inputs installed in both checkouts. Raw reports retain all
samples, setup time, mean, median, p95, maximum, throughput and runtime hashes.
The incorrect base is a cost comparison, not a correctness oracle.

| Case | Base mean s | Head mean s | Head maximum s | Mean change |
|---|---:|---:|---:|---:|
| action | 0.12494 | 0.12001 | 0.12098 | -3.95% |
| unrestricted | 0.07519 | 0.07277 | 0.07853 | -3.23% |
| attached_selection | 0.00687 | 0.00422 | 0.00470 | -38.58% |
| retained | 0.21131 | 0.21272 | 0.24628 | +0.67% |
| visible-self-observer | 0.12519 | 0.12768 | 0.13670 | +1.99% |
| unseen-no-observer | 0.42738 | 0.43541 | 0.49083 | +1.88% |
| unseen-friendly-observer | 0.33446 | 0.34639 | 0.38802 | +3.57% |

Timing ran serially on the same provisional Apple M5 Pro / 64 GiB / macOS 26.6.2
host, Python 3.14.5 and frozen `uv.lock`, without coverage, profiling or competing
task-owned test workers. Instrumented samples ran separately. The bounded
`r34-followup-runtime-performance` runner completed in **267.439 s**, exit zero.
The unseen/no-observer mean is 0.43541 s against its unchanged 0.45 s ceiling;
finite local results do not guarantee performance on other hosts.
Historical 9699f8f8 reports remain under `../review-9699/`.

## Workload coverage and calibration

The original Action component still accepts one real mission Action, queries
three eligibility paths 100 times each and visits four explicit expiry boundaries.
The additional `scripts/measure_action_restriction_live.py` driver uses the same
canonical fixture files and deterministic decision policy on both revisions:

- `unrestricted`: a real legal shooter and friendly observer, 32 generic live
  effects, finite shooting-unit selection and submission preflight, Normal
  declaration, completed attacks, actual shooting completion and charge choices.
- `attached_selection`: the same legal selection with an attached opposing
  rules unit and 32 effects. It ends at the real shooting-type request, before
  target-declaration construction. It is one decision and its own workload ID.
- `retained`: a real pending Shoot On Death choice, 32 effects, accepted retention,
  that model's out-of-phase declaration and completed attack, cleanup/parent
  continuation, then actual phase/charge completion choices (five decisions).

The CI test checks exact case inventory, effect count, decision count, charge
reachability, submission-preflight count and all named work ceilings in
[`../budgets.json`](../budgets.json). Limits have roughly 4–14% headroom for the
measured view/effect work; geometry-solver and boundary multiplicities cannot
grow. Initial calibration measured 41 view / 1,504 effect / 57 line-of-sight calls
for attached selection. It exposed all-unit enumeration duplicated by preflight.
Restricting the existing legality function to the selected unit in preflight and
application gives 25 / 1,056 / nine calls; base uses 23 / 832 / 30. The extra
current-effect checks are explicit, while unrelated target work is removed.
Phase completion still validates its full skipped-unit inventory. No cache,
geometry approximation or history scan in hot eligibility was added.

New provisional time ceilings are 0.20/0.25 s mean/max for unrestricted,
0.05/0.075 s for attached selection and 0.45/0.55 s for retained; each keeps the
1.25 head/base mean-ratio limit. They bound short local slices, not total game
calls. CI enforces stable work counts instead of host-specific wall times.
Calibration and raw final counts are retained for independent review.

## Incomplete diagnostic and full-game evidence

The additional `attached` full target-declaration diagnostic exceeded a 150 s
head deadline during calibration (`r34-live-calibration-03`). Fresh bounded 30 s
probes on the final base and head both stopped in
`Z3_solver_check_assumptions` through the exact continuous-visibility formula
while constructing the Normal declaration. Their JSON outcomes and stack logs
are retained here; none is reported as a completed sample or a rules answer.
The separate attached-selection workload does not replace this diagnostic.
No existing difficult Indirect case was removed. This task does not change the
visibility solver or extend the Order 32 performance deferral to these budgets.

Complete-game mean below 60 s and no measured game above 300 s remain
**uncertified**. No full-game or training framework was built.

## Reproduction

Run on the pinned measured revisions with the identical 5b6752ff driver/helper
inputs listed in the manifest. Later candidates retain the same production tree.
The base
checkout is `/private/tmp/order34-base`; its production source stayed unchanged.
Use the repository virtual environment with `PYTHONPATH=.:src` in that checkout.

```sh
uv run python -m scripts.measure_action_restrictions --samples 7 --output action-timing.json
uv run python -m scripts.measure_action_restrictions --samples 1 --work-counts --output action-work.json
uv run python -m scripts.measure_action_restrictions --live-case unrestricted --samples 7 --output unrestricted-timing.json
uv run python -m scripts.measure_action_restrictions --live-case attached_selection --samples 7 --output attached-selection-timing.json
uv run python -m scripts.measure_action_restrictions --live-case retained --samples 7 --output retained-timing.json
uv run python -m scripts.measure_indirect_shooting --samples 7 --output shooting-timing.json
uv run pytest tests/code_quality/test_order34_action_restrictions.py tests/code_quality/test_order33_indirect_shooting.py -q --no-cov
```

For each live case, use `--samples 1 --work-counts` for profiling separately.
The non-terminating diagnostic remains selectable with `--live-case attached`;
use the retained bounded runner command and a process deadline when reproducing.

## Recompute the comparison

Run this from the repository root after producing the reports above. It enforces
the unchanged absolute and relative time limits, sample inventory, work budgets,
matching input hashes and clean measured runtime trees.

```python
import json
from pathlib import Path
p=Path('docs/performance/order34/review-repair')
a=json.loads(Path('docs/performance/order34/budgets.json').read_text())
s=json.loads(Path('docs/performance/order33/budgets.json').read_text())
checks={}
heads=set()
bases=set()
def compare(name,b,h,budget):
    values={'base_mean':b['mean_seconds'],'head_mean':h['mean_seconds'],'head_maximum':h['maximum_seconds'],'ratio':h['mean_seconds']/b['mean_seconds'],'sample_counts':[len(b['samples']),len(h['samples'])]}
    values['passed']=values['head_mean']<=budget['mean'] and values['head_maximum']<=budget['maximum'] and values['ratio']<=budget['head_to_base_mean_ratio'] and values['sample_counts']==[7,7]
    checks[name]=values
for case in ('action','unrestricted','attached_selection','retained'):
    b=json.loads((p/f'base-{case}-timing.json').read_text())
    h=json.loads((p/f'head-{case}-timing.json').read_text())
    assert b['hashes']==h['hashes']
    assert b['runtime_diff_sha256']==h['runtime_diff_sha256']=='e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'
    heads.add(h['commit']); bases.add(b['commit'])
    compare(case,b,h,(a if case=='action' else a['live_cases'][case])['provisional_timing_limits_seconds'])
b=json.loads((p/'base-shooting-timing.json').read_text());h=json.loads((p/'head-shooting-timing.json').read_text())
assert b['hashes']==h['hashes']
heads.add(h['commit']); bases.add(b['commit'])
assert set(b['results'])==set(h['results'])==set(s['work_limits'])
for name, row in h['results'].items():
    compare(name,b['results'][name],row,s['provisional_timing_limits_seconds'])
work={}
for case in ('action','unrestricted','attached_selection','retained'):
    budget=(a if case=='action' else a['live_cases'][case])['work_limits']
    b=json.loads((p/f'base-{case}-work.json').read_text());h=json.loads((p/f'head-{case}-work.json').read_text())
    assert b['hashes']==h['hashes']
    assert h['commit'] in heads and b['commit'] in bases
    counts=h['samples'][0]['work_counts']
    work[case]={'base':b['samples'][0]['work_counts'],'head':counts,'passed':all(counts.get(metric,0)<=maximum for metric,maximum in budget.items())}
assert len(heads)==len(bases)==1
result={'base_sha':bases.pop(),'head_sha':heads.pop(),'comparability_hashes_match':True,'timing_checks':checks,'work_checks':work,'all_required_budgets_passed':all(v['passed'] for v in checks.values()) and all(v['passed'] for v in work.values()),'full_attached_declaration_diagnostic':'incomplete: exact visibility solver exceeds deadline on both base and head; retained separately','full_game_certified':False}
(p/'budget-validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
assert result['all_required_budgets_passed']
```
