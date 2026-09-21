# Order 70 / P24J — model-complete Fights First

Status: implemented and locally validated; PR publication pending.
Finding: C24-10. Dependencies P02D, P05B and P24A are merged. Evidence gate:
APP-DRIFT. Base: `6ee55f30` (Order 69). This closes only the Fights First finding,
not category 24 or final Core Rules certification.

## Invariant and source

A rules unit is Fights First only while every rules-present model has the
ability. Intrinsic component abilities cover their physical models. An explicit
unit grant covers the rules unit. Retained Fight On Death models continue to
participate until cleanup; an empty unit never satisfies the predicate.

Previously `FightsFirstRegistry.from_state` promoted every component effect to
the attached identity. Fight order then used that phase-start snapshot even
after membership, presence or grants changed. Conditional Leader checks also
used living-only component keywords/presence in two places.

Controlling source: Core 24.13 Fights First and the unit-effect clause of 01.02
Units and Models, observed through the search index of the non-affiliated
[40k.app Core Abilities page](https://www.40k.app/rules/24-core-abilities) and
[Core Concepts page](https://www.40k.app/rules/01-core-concepts) on
`2026-09-21T12:06:54Z`. Direct requests returned 403. No direct page capture,
App-data version, official-App observation or co-version comparison is claimed.
The 24.13 operative predicate is retained verbatim; its additional cross-reference
to the 12.04 Fight step is recorded in the audit. The 01.02 artifact is the
complete operative unit-effect sentence, not a transcription of unrelated clauses.
The maintained-mirror policy already authorizes these observations; no source
exception was encountered.

Package `gw-11e-core-fights-first`, version
`maintained-app-mirrors-observed-2026-09-21`, has stable source IDs
`gw-11e-core-fights-first:fights-first` and
`gw-11e-core-fights-first:unit-grants`. The committed source artifact and
`data/source_audits/maintained_app_mirrors/fights_first_2026_09_21.audit.json`
retain each transcription SHA-256 and immutable observation fingerprint. The
typed eager loader pins artifact SHA-256
`501db53231ec964f4c60af8dca80b726bca7902ba3618023e7a04919d712593d`;
the authority registry independently pins both observations. Historical official
GW Core Rules provenance remains
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.
Load status (`loaded`) and execution status (`executable_engine_runtime`) remain
separate fields.

| Source clause | Transcription SHA-256 | Observation fingerprint |
| --- | --- | --- |
| fights-first:40k-app | `35e5bd3db977c70e49dc2ae64913ce55fbd487a8df0333e85636d5e8ff4fb227` | `240c270d94c77235f822eb461c614e840742dc95c8a1bad957fe2eb9312e70b9` |
| unit-grants:40k-app | `1d29a08b455a18c186b76bdb992d8a0afa24c95c68df2d3d2af7e0cce9a7fbac` | `26acf54fda3dad1d1a2cc87ad2a81de36527374ad62197aeb1933482678cbf32` |

## Ownership and scope

Catalog descriptors/canonical model keywords -> shared native source inventory
and materialization -> persisting effects with explicit intrinsic model IDs ->
current RulesUnitView with retained presence and authenticated split lineage ->
shared model-coverage query -> live fight eligibility -> ordinary activation and
Counteroffensive validation -> existing engine mutation, events, adapters and replay.

`fights_first_native.py` owns intrinsic source identities and model footprints.
Materialization and restored-effect validation use the same inventory. Restore
rejects changed source, target, identity or model scope, including removal of the
scope field from a known native occurrence. Historical split origins preserve
the original source inventory; the live query intersects its footprint with
each successor's actual models.

`fights_first_model_inventory` combines partial native and model grants before
the all-model test. Core duplicate-source enumeration consumes those partial
footprints instead of pretending a partial grant belongs to other components.
Conditional Leader grants retain their descriptor-authorized unit scope and
recheck current leading conditions. The not-leading model grant now records its
explicit source model. Its start-of-Fight condition remains a snapshot, with its
existing phase lifetime. Charge and selected whole-unit grants retain unit scope.

The frozen Fight-start registry remains historical evidence, including Charge
eligibility and forced-Fight reconstruction. Live ordering uses a fresh registry
for each eligibility query; casualties, cleanup, revival, split membership and
grant expiry therefore need no invalidation callbacks or cache. Historical
builders continue to use event-time evidence. No named handler, hook family,
architecture exception, new faction content or excluded content is introduced.

The first quality run exposed unnecessary membership/effect-target work when no
Fights First grant exists. After validating native source integrity, the registry
now returns an explicit empty inventory for that case before constructing unit
views. A shared structural payload predicate covers both the empty-inventory test
and per-model query. All three existing Order 34 live work guards pass with their
unchanged budgets. This correction changes no rules answer; it requires fresh
runtime identity, component measurements and final aggregate validation.

The same-bug-class search covered every Fights First producer and consumer,
native descriptor/keyword materialization, conditional leading/not-leading
providers, selectable catalog modes, Charge, duplicate abilities, split aliases,
fight order, Counteroffensive and historical reconstruction. The related Stealth
all-model owner already handles its own coverage. Broader ability migrations and
Orders 71–73 remain outside scope.

## Decisions, restoration and proof

The existing finite Fight and Stratagem contracts cover all player choices.
There is no new public decision type, option shape, submission or viewer field.
Pending activation revalidation rejects a lost grant before queue pop and without
state mutation. Both viewer projections retain their existing visibility.
Intrinsic model IDs are existing operator/replay persisting-effect data. The
new engine build identity rejects old persistence; source scope is never inferred
from an old native effect missing its model footprint. No compatibility shim is
provided. See the Order 70 entry in `ADAPTER_DECISION_CONTRACT.md`.

Regression coverage includes both directions of mixed native attachment, all
native components, per-model keyword ownership, whole-unit/Charge and model-only
grants, live casualty/retained-cleanup transitions, restoration of a non-ability
model, conditional Leader retention and loss, Counteroffensive bands, stale
submission, source-scope corruption, split footprints, both viewer projections,
facade submissions, fork and exact replay. The first regression failed for both
single-native-component cases before implementation. Behavioral changes use
existing test files; eight-shard membership is unchanged.

## Generated artifacts and validation

Reproduce the reviewed source with
`uv run python tools/build_core_fights_first_source.py --check`.
Regenerate runtime identity before external-contract examples. The active CI
workflow also requires exact-base contract compatibility, installed-wheel smoke,
TypeScript generated-client checks/unit tests/live conformance, lint/type/import
checks, shard inventory and both final Python suites.

Scope and architecture audit: production changes are limited to native ownership,
live coverage/ordering, duplicate-source footprints, conditional grant presence
and source records. New modules are below the size limit. Existing oversized
modules only delegate or remove the replaced responsibility. No new behavioral
test file or speculative runtime registry is added.

Matched query and inherited component evidence is recorded in
[performance/order70](performance/order70/README.md). Complete-game performance,
the 60-second mean/300-second maximum targets and deferred Order 32 budgets are
not certified. Final local results and diagnostic history are retained in
[validation.json](performance/order70/validation.json).

## Validation results

8,662 behavioral tests passed with 85.1418% coverage; all 567 code-quality tests passed without coverage. Ruff check/format, mypy (3,174 files), Pyright, 11 import contracts, eight-shard inventory, source/catalog generators, exact-base contract compatibility, installed-wheel smoke, generated TypeScript client/typecheck, five client tests, 342 live conformance assertions and all-files pre-commit passed. All retained component/work budgets pass unchanged. `npm ci` was unavailable locally; package-script equivalents ran through Node with the installed dependencies.

Both final suites use 32 automatically allocated xdist work-stealing workers,
following Order 69's recorded host-scheduling assessment. No production code
changed after the final behavioral run began. The first behavioral run passed;
the first quality run found two work-budget failures. The empty-inventory
correction, fresh runtime/component evidence and passing full reruns are recorded
separately in the validation JSON. Ten pre-existing SQLite ResourceWarnings were
reported during the final behavioral suite.

PR URL and merge commit: publication pending; merge remains owner-controlled.
