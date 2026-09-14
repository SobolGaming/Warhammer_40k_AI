# Order 48 — Crushing Impact Charge continuation

Status: implementation and required local validation complete; publication in progress.
Finding `C15-09` / `P15I`.
Base: `10a3b19d09a9fdb0aa1bd393e8bc141487368d05`; dependencies P15D, P11A,
P06B and P05A are merged.

## Invariant and source

After a friendly MONSTER/VEHICLE rules unit completes a Charge move during its
owner's Charge phase, Crushing Impact must be available through the shared
decision path. The owner selects an engaged enemy rules unit and a living,
placed model in the charging rules unit engaged with that enemy. Roll D6 equal
to that model's Toughness; each 1 causes a self mortal wound and each 5+ an enemy
mortal wound, capped independently at six per unit. Allocation, Feel No Pain,
destruction and any triggered rules must finish before ordinary Charge resumes.

The existing complete 15.05 transcription is preserved in
`core_stratagems_2026_08/artifacts/package.json` under stable source ID
`gw-11e-core-stratagems:core:crushing-impact`. Provider: maintained 40k.app mirror,
URL `https://www.40k.app/rules/15-stratagems`, observation
`2026-08-26T11:15:23-04:00`, transcription SHA-256
`63fe27d984e7863a906d1ff7edeaef678fa69cdc1c6a7040869409749353e060`,
source-observation fingerprint
`329f378b3cb1f78f28f7f32047e01e2b78295d155c30df9fde775bf0cab3afa4`.
The retained observation and historical official GW provenance remain unchanged;
no fresh live-provider observation is claimed.

## Ownership and smallest complete scope

The original handler already rolls Toughness-based dice and routes both damage
packets through shared mortal-wound services. However, the source catalog marks
its targets non-enumerable, Charge completion does not discover its opportunity,
model membership checks one physical component, and only enemy wounds are capped.

The intended path is source JSON → typed Core catalog → completed-move trigger
and shared timing batch → finite Stratagem option → validation and CP/use record
→ shared damage allocation/Feel No Pain/destruction → timing-batch completion
→ Charge continuation. The same catalog-driven candidate builder serves immediate
and deferred move completion. Deferred discovery must consume the complete
configured Stratagem catalog, including Core entries, as the phase owners do.

The existing `core:crushing-impact` orchestrator retains its identity and budget.
It coordinates this source's two damage packets and suspended choices; generic
services continue to own CP, dice, allocation, wounds and destruction. No new
named handler or speculative hook family is required. Orders 49–51 retain their
separately scheduled Charge reroll, Heroic Intervention and Aircraft work.

The bug-class search covers both duplicated wound-count calculations, current
and historical attached identities, target enumeration/validation, immediate and
deferred move discovery, mortal-wound routing, source support claims, public
projection/event redaction and replay authority. The adapter contract must record
the finite model/enemy selections and completed-move source context.

## Acceptance and validation

The pre-fix real-facade regression reproduces a completed ordinary Charge going
directly to `select_charging_unit`, without a Crushing Impact choice. Tests cover
MONSTER and VEHICLE, attached source models, both capped damage packets, decline,
stale and malformed submissions, allocation and Feel No Pain, destruction,
continuation, restoration and exact replay. Final results and the scope/diff
audit are recorded below.

The unchanged versioned Charge slice is measured on base before runtime edits;
its seven samples and predeclared limits are in `performance/order48`. This is
component/slice evidence, not complete-game certification. Full-game objectives
and deferred solver budgets are unchanged.

Generated artifacts: source semantic support metadata and package/loader hashes,
runtime build identity, external contract bundle and examples, support artifacts
where affected, and the eight-shard test inventory from the final JUnit profile.

PR URL and merge commit: pending publication; no merge is authorized by this task.

## Approved shared destruction repair

The real-facade Deadly Demise regression showed that the pre-existing Core
Stratagem mortal-wound route removed casualties without invoking destruction
reactions. The owner explicitly approved including the shared destruction fix
in Order 48. Crushing Impact and Explosives now use one retained-packet service;
the existing rule-destruction service owns Deadly Demise, collateral damage,
removal and subsequent triggers. The existing mortal-wound continuation hook
registry gains a typed completed-application callback. Its Core providers remain
behind source-linked bindings; generic lifecycle code does not branch on content.

The packet stores its frozen result and target lineage in private events, binds
logical deaths to the original application, and resumes its registered completion
only after casualty routing. Both physical history and restore authority include
this packet boundary. A secondary regression exposed event-at-a-time and
checkpoint-slice physical scans losing the earlier Deadly Demise application
root; the scans now carry the complete event history. The existing transition
scan was extracted to the decision-authority module before extending its
near-limit caller. No model damage, explosion or removal logic is duplicated.

The initial Deadly Demise regression failed with no explosion event and untouched
collateral units. Passing regressions now cover collateral damage, suspended
restoration, exact replay, tampered or missing receipts and the shared Explosives
consumer. The initial performance artifact is retained alongside the final
matched timings after the expanded runtime stabilized.

## Scope and architecture audit before aggregate gates

The final runtime change is the catalog-driven Charge occurrence, a typed finite
selection, shared independent caps, selected-model characteristic modifiers,
canonical rules-unit ownership/geometry, and the owner-approved retained damage
packet service. Explosives is the second concrete consumer of that service.
Physical-history changes preserve complete source evidence through one-event
inventory scans and checkpoint slices. Three completion bindings reuse the
existing Core orchestrators and mortal-wound registry; no new named handler,
architecture dependency edge, decision type, speculative hook registry, or
faction/display-name gate was added. New modules remain below 1,500 lines; the
physical-history caller was reduced before extension.

Focused validation: 164 Crushing Impact/Explosives/source tests passed; 7 nested
destruction and altered-history regressions passed; the final focused Core
Stratagem/static/performance/redaction run passed 223 tests. Mypy and Pyright
passed. Runtime/source artifacts and the external contract were regenerated;
the isolated installed-wheel smoke passed. The remote main base is unchanged.
Matched Charge means are 0.021779 s base and 0.021814 s head. The 21 new-capability
samples completed with a 1.386167 s maximum, within all predeclared budgets.
See [performance evidence](performance/order48/README.md).

## Final validation

The final runtime identity is
`warhammer40k-core-v2:runtime-tree-sha256-v1:155186145754959fc00dbdb3bec0aa0fe4e144a2a39ae32caaa833ba04ccb6c0`.

| Required gate | Result |
| --- | --- |
| `uv run ruff check .` | Passed |
| `uv run ruff format --check .` | Passed |
| `uv run mypy src tests` | Passed, 3,016 source files |
| `uv run pyright` | Passed, no errors or warnings |
| Complete behavioral suite, xdist work stealing, coverage | 7,940 passed; 85.11% coverage; 587.87 s |
| `uv run pytest tests/code_quality -q -n auto --dist=worksteal --no-cov` | 475 passed; 123.73 s |
| `uv run --no-sync python scripts/build_test_shards.py --check --shard-count 8` | Passed after regeneration from the complete final JUnit profile |
| `uv run lint-imports` | Passed |
| `uv run pre-commit run --all-files` | Passed |

The behavioral command was
`PATH="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:${PATH}" uv run pytest tests --ignore=tests/code_quality -n auto --dist=worksteal --cov=warhammer40k_core --cov-report=term-missing --cov-fail-under=85`,
with `--junitxml=/private/tmp/order48-behavior.xml` added for the shard profile.
It emitted ten existing SQLite resource warnings. No production code changed
after this run. The first code-quality run reported one obsolete direct-call
assertion: Stratagem geometry now delegates to the existing shared physical
geometry owner. The audit was updated to require that delegation; the separate
shared-owner audit continues to enforce retained battlefield presence.

Additional CI-equivalent checks passed: source artifact and runtime identity
verification; external contract generation check against base
`10a3b19d09a9fdb0aa1bd393e8bc141487368d05`; isolated installed-wheel smoke
(27 schemas and 2,796 engine resources); TypeScript generated-client check;
five TypeScript unit tests; and 342 conformance assertions. Public schema version
19.0.0 is unchanged because its existing finite options and private engine
payloads cover this change. All versioned performance budgets passed within the
measured scope above; full-game certification remains outstanding.
