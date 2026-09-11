# Order 37 — final Stratagem CP cost authority

P02E / C02-05. Base: `35f492b2` (Order 36 merged).

Invariant: collect applicable, source-linked operations, apply replacement,
multiplication, addition, division, subtraction and final rounding, then bound
the cost to `[0, unmodified cost + 1]`. A committed modifier remains recorded
even when the final bound makes its numeric effect redundant.

The owner is `StratagemCostModifierRegistry`, with exact ordered arithmetic in
`core.modifiers`. Catalog RuleIR and the existing generic/faction providers
must return operations rather than intermediate prices. Explicit source
non-cumulative increases retain their restriction independently of the final
cost ceiling. There is no new hook family or named handler.

Source/consumer trace: reviewed 02.02.01 plus source-linked RuleIR/provider
bindings → registry → `_selected_command_point_cost_result` → option and target
affordability, submission validation, increased-cost failure, CP transaction,
`StratagemUseRecord`, events, checkpoint and replay. Heroic Intervention's
selected additional section is included in the unmodified cost for that use
by the existing 15.01 owner. Adapter schemas and decision kinds are unchanged;
the contract documents final-cost and source-commitment semantics.

Bug-class audit found per-handler zero clamps in the registry, Master of the
Pageant and Soul-hungry Slaughterers; catalog non-cumulative logic also inspected
an intermediate price. All these producers must be migrated together. The first
regressions on the base fail for base 1 +3 (4 rather than 2) and base 1 -5 +3
(3 rather than 0), with the ordinary cumulative control passing.

Scope excludes other Stratagem timing, target and reaction findings. Validation
includes mixed operations, identity permutation, zero costs, source commitments,
real catalog/facade consumers, restore/replay, malformed/stale decisions and a
static producer audit, followed by all repository publication gates. Performance
uses the existing Rapid Ingress workload/budgets and a linear provider-call gate;
complete-game performance remains uncertified.

During consumer-fixture development, an independent existing target-discovery
limitation was observed: Fire Overwatch enumeration without its ruleset/catalog
context yields no candidates when unbound affordability cannot short-circuit
(e.g. zero available CP with a target-specific discount). That is a missing
shooting-context issue, not a CP arithmetic/ceiling instance, and is retained as
follow-up for the Fire Overwatch owner (P15H). Order 37 tests zero-priced Overwatch
with one available CP and preserves Order 35's zero-available-CP discounted
Rapid Ingress regression. Neither the parser's unrelated range-free opponent
relationship nor Overwatch's target-discovery contract is changed here.

## Source evidence

The new source row is `gw-11e-core-modifiers:stratagem-cost-limits`, added to the
existing typed, hash-pinned Core modifiers JSON package and source-authority
registry. Provider: 40k.app, canonical URL
`https://www.40k.app/rules/02-datasheets`, observed at
`2026-09-11T19:52:51Z` through its search-index text; direct retrieval returned
403. No App version or second-provider comparison is asserted. Provider
non-affiliation and the maintained-mirror authority policy remain explicit.
Earlier observations and the historical official GW Core Rules hash
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`
are preserved. The offline builder verifies both package and audit bytes.

## Acceptance and scope audit

- Exact replacement/multiplication/addition/division/subtraction order, final
  rounding, signed additions, zero and +1 bounds, changed source-ID order,
  malformed/symbolic/conflicting operations and selected Heroic section costs.
- Registry absence versus applicable operations, source-preserving terminal
  limits, non-cumulative increases, and one evaluation of each registered source.
- Real catalog-loaded Overwatch: five accepted opponent sources, bounded spend,
  unaffordable-use completion without spend, large reduction to zero, automatic
  increase affordability, pending/final restoration and exact `ReplayRunner`
  reproduction, both viewer projections/events, stale and invented option rejection.
- Existing zero-available-CP discounted Rapid Ingress, finite Archraider cost
  choices, generic Warptide/Master of the Pageant and catalog consumers remain
  covered by their original regressions.

The pre-aggregate diff audit confines production changes to the arithmetic owner,
registry, existing producers and their internal type interfaces, plus source and
build identity artifacts. No new gameplay rule, named handler, generic hook,
architecture boundary, decision family or public payload field is introduced.
The existing contract covers the decisions; its documentation now specifies
final prices and retained commitments. No behavioral test file was added, moved
or deleted, so the eight-shard file inventory is unchanged.

Initial complete affected-module run: `401 passed` (154.62 s, serial focused
iteration, no coverage). The final suite below includes subsequent stale-option,
invalid-operation and selected-section regressions. Final cost component timing
passes its versioned budget. Base/head means and
all seven completed samples per case are recorded in
[the performance evidence](performance/order37/README.md).

## Final validation

Validated the final production tree with runtime identity
`warhammer40k-core-v2:runtime-tree-sha256-v1:c01108ad5a914002c545c2c8dcaf322157474befb4cae8ee351b91184ba1d236`.

| Gate | Result |
|---|---|
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed; 3,048 files formatted |
| `uv run mypy src tests` | Passed; 2,942 source files |
| `uv run pyright` | Passed; zero errors or warnings |
| Complete behavioral suite, coverage, `-n auto --dist=worksteal` | 7,232 passed in 489.32 s; 85.02% coverage against the 85% gate |
| Complete code-quality suite, `-n auto --dist=worksteal --no-cov` | 430 passed in 99.87 s |
| Eight-shard fail-closed inventory check | Passed |
| `uv run lint-imports` | Passed; all 11 contracts kept |
| `uv run pre-commit run --all-files` | Passed |
| Source-package and engine-identity generators, `--check` | Passed |
| External contract generator, `--check --base-ref origin/main` | Passed |
| Generated TypeScript client, type check and unit tests | Passed; five unit tests |
| Live TypeScript conformance | Passed; 342 assertions, contract 15.0.0 |
| Installed-wheel contract smoke | Passed; 2,747 runtime resources, 27 schemas, six request families |
| Versioned cost and unchanged Rapid Ingress component timing | Passed; full-game certification remains outstanding |

The behavioral command included the required bundled Node `PATH` prefix and
ran once with coverage. It reported ten SQLite `ResourceWarning`s without test
failures. This host has Node but no `npm` executable, so `npm ci` could not run.
The package's exact generated-client, TypeScript, unit-test and conformance
entry points ran directly with Node and the existing installed dependencies.
