# Order 39 — model-complete Stealth and Benefit of Cover

Status: implementation and required local validation complete; awaiting PR review and merge.
Finding: C24-01 / P24A. Dependency P10 is merged. Base: main
`304d828f71e137d7cfc4f7ee9c5788b288322854` (Order 38).

## Invariant and source

Every present model in the target rules unit must have Stealth before the unit
receives Benefit of Cover against a ranged attack. Native component abilities,
model keyword assignments and current grants contribute their actual model
footprints. Living and retained Fight On Death models both count. Stealth does
not subtract from Hit rolls; Cover remains the existing single Ballistic Skill
modifier, suppressed by Ignores Cover and applicable Cover denial.

The previous implementation accepted any attached component's native ability
and subtracted one from Hit. Catalog Aura, passive self, selected-target and
Darkness consumers duplicated that old consequence. Some generated descriptions
also retained the older wording.

The complete operative statement is Core 24.33 on
[40k.app](https://www.40k.app/rules/24-core-abilities), observed in the search
index at `2026-09-12T02:06:45Z`: every model must have the ability, and the unit
receives the benefit of cover against each ranged attack targeting it. The
exact transcription is retained in the source artifact. Direct retrieval
returned HTTP 403; no direct page capture, App-data version, co-version mirror
comparison or official-GW-host observation is claimed. The provider is
non-affiliated and is admitted under the repository's existing maintained
App-data mirror policy `core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02`.

Source package: `gw-11e-core-stealth`, version
`maintained-app-mirrors-observed-2026-09-12`, rule ID
`gw-11e-core-stealth:stealth`. Transcription SHA-256:
`f10c66ca0215b0893d5385bd13b4064640f23182cdaef342715a87e68c8d4f85`.
Observation fingerprint:
`f0e3ecd64cf432c5c7768b6c0ed4eb2f4e9624ac2e6a74176a6e42afdab9aef1`.
Reviewed artifact bytes:
`50d05f2f15af7a173b74cbd2e4c601a9ee00f4260bccdb4248aed584c9f9eadb`.
The authority registry pins the actual source catalog hash
`5f0bc9b93f64d7b3a39bed442c3fc54b81350e419f5d14d459b07134fd1cfe55`.
The audit retains historical GW Core Rules provenance/hash
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.
Load and semantic-execution status are separate fields. A typed eager loader
rejects byte, schema, identity, transcription and execution-evidence drift.

## Owning path and complete scope

Source package and catalog descriptors -> native per-model abilities / generic
RuleIR grants / source-linked model grant providers -> canonical RulesUnitView
with attached and retained authority -> shared `rules_unit_stealth_sources`
query -> existing attack Cover modifier and allocation metadata -> source-bound
Psychic choice -> engine validation/mutation -> records, viewer projections,
persistence and exact replay.

`ModelAbilityGrantBinding` is a typed generic provider of model IDs. The current
catalog Aura/self rules and Harbingers Darkness are real source-backed consumers
in this change. Bindings are loaded through RuntimeContentContribution/Bundle,
validated for exact types, duplicate IDs and foreign model returns, and included
in bundle identity and support inventories. Content-specific providers stay
outside generic lifecycle code. No named handler or faction branch is added.
The existing bespoke Harbingers resource/selection orchestrator remains in place;
its reusable Stealth consequence now uses the generic grant service.

Persisted grants use the existing target lineage owner. A single effect can cover
multiple attached components; model-only effects remain model-only. Conditional
leader grants recheck current leader/bodyguard presence, including retained
models, through the shared conditional-grant owner. The native query is rebuilt
from current model authority; no cache or second mutation path is introduced.
Native ability recognition uses stable descriptor IDs or canonical model keyword
tokens, never display names or freshly normalized rule text.

The source-aware Cover modifier preserves one effect when terrain, Indirect Fire
and multiple Stealth sources overlap. It operates for ranged attacks in every
phase. Save metadata observes the same ranged-only rule; 11e Cover does not add
an armor save bonus. Its existing opaque modifier ID commits source identities
and footprints, rejecting a source replacement at the same numeric total before
consuming a pending Psychic choice. The existing adapter contract already covers
this skill modifier and its public visibility; no schema, decision type or option
family changes are required. The contract documentation records the semantics.

## Bug-class and architecture audit

Searches covered native descriptors/keyword queries, target declaration evidence,
Hit modifier reconstruction, attack snapshots, save metadata, persisted selected
targets, conditional leaders, Aura/self providers, Darkness, source registries,
current catalog JSON, support inventories, tests and documentation. Obsolete
Stealth Hit consumers were removed. Smokescreen's own independent modifier is
Order 40 and remains outside this finding; unrelated melee defensive modifiers
remain owned by their existing RuleIR services.

Only the supported Chaos Daemons roster and Court of Slaughter/An'vanth catalogs
contained obsolete native Stealth descriptions. Their generators apply the
reviewed Core overlay and record its artifact hash and source ID. Historical
input snapshots and official PDF hashes remain intact. The Be'lakor reconciliation
gameplay hash changes because the generated current catalog includes that Core
overlay; it does not assert a change to the official PDF. Court output also emits
the current serializer's empty model-keyword assignment collection. No excluded
content is added or exposed. Generated support reports follow the new consumers.
The faction coverage/execution inventory and its four documented governance
checksums also track the Darkness binding ID; named-handler counts and budgets
are unchanged.

Before aggregate gates, the diff was narrowed to this ability invariant and its
required source/runtime/generated paths. Registry identity validation was
extracted from `runtime_modifiers.py`; contribution combination was extracted
from the near-cap faction bundle before adding the grant family. Both preserve
strict validation and existing call surfaces. New modules are under 1,500 lines;
existing module caps and import directions are preserved. No behavioral test
file was added, removed or moved; the eight-shard inventory is unchanged.

## Acceptance and delivery checks

Regressions cover mixed native model footprints, all eight combinations of three
attached components, one/multiple component targets, whole-unit and model-only
grants, grant removal, malformed model context, casualty/retained presence,
conditional-leader retention, native/catalog Aura self inclusion and distance,
source destruction, selected-target grants and Darkness. Attack tests cover
Ignores Cover, denial, Indirect Fire non-stacking, ranged attacks in other phases,
melee exclusion and save metadata. Facade tests cover native and granted Stealth,
JSON-safe source commitments, both viewer projections, persistence, exact replay
and same-total source drift rejection. Static audits reject the old Hit consumer
path, check source rows and retain the bounded query evidence.

Regenerate/verify with:

```sh
uv run python tools/build_core_stealth_source.py --check
uv run python tools/generate_chaos_daemons_roster_catalog.py --check
uv run python tools/generate_court_of_slaughter_anvanth_catalog.py --check
uv run python tools/generate_ability_support_matrix.py
uv run python scripts/build_engine_build_identity.py --check
uv run python scripts/build_external_contract.py --check --base-ref 304d828f71e137d7cfc4f7ee9c5788b288322854
```

The support generator has no `--check` flag; its committed outputs are verified
by `tests/code_quality/test_generated_ability_support_artifacts.py`.
The runtime identity and external contract must be regenerated without `--check`
after intentional runtime changes. The active CI workflow also requires the
installed wheel smoke, generated TypeScript client, typecheck/unit tests and the
live HTTP conformance scenario, plus all AGENTS.md validation gates.

Performance evidence and its limits are in [order39/README.md](performance/order39/README.md).
The first aggregate run found three stale assertions (Darkness binding type,
Fluxmaster's old ranged modifier and the source-package count); all were
corrected and pass focused verification. The first coverage report hit a SQLite
database-open error after collecting data. Final revalidation uses the same
required command with `COVERAGE_FILE=/private/tmp/order39-final.coverage` to
isolate the database. This preserves coverage configuration, thresholds and
xdist work stealing. No serial or non-coverage behavioral rerun substitutes for
the final gate.

Final behavioral validation passes all 7,402 tests with 85.04% coverage
(85% required), using 18 xdist work-stealing workers and the required Node PATH.
Ten ResourceWarnings came from the existing SQLite persistence tests. The
complete code-quality suite passes all 433 tests without coverage, using
18 xdist work-stealing workers.

Ruff check/format, mypy (2,950 files), Pyright, all 11 import contracts, the exact
eight-shard check and all-files pre-commit checks pass. Source/catalog generators
and the final runtime identity verify; external-contract compatibility passes
against unchanged main `304d828f`. The installed-wheel smoke validates 27 schemas
and six request families. TypeScript generated-client verification, typecheck,
all five unit tests and the live HTTP scenario pass (342 assertions, exact replay).
Node runs the package script entrypoints directly because npm is absent on this
host; `npm ci` cannot be run locally. CI performs its clean dependency installation.

All four versioned component performance cases pass, with final query means
0.051–0.173 ms and a maximum sample average of 0.175 ms. These results do not
certify complete-game performance. Final runtime fingerprint:
`eb908777d82d4cd0512ad368b8a6a6820993ea39d6419ed61c09016264e3617a`.

PR URL will be recorded after publication; remote CI is not claimed as passed locally.
