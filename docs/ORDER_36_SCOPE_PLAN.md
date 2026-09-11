# Order 36 / P01D / C01-04 — scope and validation

Status: implemented and locally validated; ready for PR review. All required
local gates pass, and no demonstrated P01D blocker remains open.

The owner approved the complete sequencing migration on 2026-09-10 and requested
scope closure on 2026-09-11. The approved change is cross-cutting: fixing only the
permutation helper would leave live phase, attack, movement and mission callers
resolving rules in provider order. This is a substantial engine migration, not
primarily mechanical file moves. No additional content semantics, general rules
audit or performance optimization is part of the wrap-up.

## Scope closure

The retained changes implement one invariant: source-backed rules at the same
timing resolve in their owner's mandatory/optional tier, with each selected rule
finishing before the next and new triggers waiting for the original batch.
Temporary active-player authority, historical source ownership, replay and viewer
redaction must describe that same execution.

The late mission correction was necessary: the old end-of-turn chain completed
all Actions, then all Primary scoring, then Secondary scoring in fixed order.
The real facade regression reproduced the missing owner choice. Primary and Fixed
Secondary now compete as mandatory owned rules; optional Consecration and Tactical
choices use their owner's optional tier. Sensor Sweep's internal choice finishes
its selected Action. The scoring evidence records the owner's chosen commit time.

Demonstrated migration regressions are distinguished from fixture maintenance:

- Existing Horror/materialization corruption tests stopped rejecting altered
  casualty provenance after deferred destruction was introduced. Shared historical
  ownership and exact producer validation restore those rejection assertions.
- Existing retained-casualty tests exposed premature unit-destruction completion
  while the last casualty's reaction remained pending. Completion now follows
  the shared casualty owner.
- Several old fixtures manufactured move/destruction events directly. They now
  invoke the actual event producer and preserve the original behavioral assertion.
- A retained-casualty ordering submission exposed different Core provider
  registries in execution and validation. Both now use one shared composition
  for retained cleanup, return-on-death and sticky-objective candidates.
- Out-of-phase post-roll choices now use the selected attacker's temporary
  active-player authority, matching the rest of attack resolution.
- Mission certification fixtures begin at the Fight end step, leaving the
  lifecycle to resolve its end rules; they no longer mark the phase fully complete.
- The retained-workload gate found repeated identity queries during mission
  candidate discovery with an empty Battle-shock registry. The occupancy owner
  now handles that exact empty case directly; a regression checks live registry
  changes, and the original failed measurement is retained.

Unconfirmed adjacent concerns do not expand implementation. In particular,
load-only post-shoot movement Stratagem profiles have not been promoted to
executable content to manufacture an acceptance scenario.

## Authority and invariant

The complete 01.03, expanded 01.03.01 and expanded 01.03.02 were read in the
browser on 2026-09-10, approximately 16:07 UTC, at
<https://www.40k.app/rules/01-core-concepts>. Ordinary browser verification
completed; the HTTP reader returned 403. No App version was exposed. The provider
identifies itself as unaffiliated with Games Workshop. No conflicting official
App or co-versioned maintained-mirror observation was encountered.

The controlling requirements are:

- The first-turn player is active between turns, including round boundaries.
- Selecting a unit to move changes active-player authority until that move
  ends. Selecting it to shoot or fight changes authority until its attacks resolve.
- Rule ownership comes from the player's army, detachment, Stratagem,
  Enhancement or datasheet. Mission rules used by a player belong to that player;
  automatic unowned mission rules precede player rules unless a specific source
  supplies a different sequence.
- Resolve active mandatory, active optional, opposing mandatory, opposing
  optional rules. Each owner chooses the order inside that owner's tier.
- Newly triggered rules wait until all rules in the original timing batch
  finish. Completing one rule is distinct from completing that batch.

Implementation must retain exact operative source transcriptions in the existing
offline generated-JSON/source-authority system, with stable source IDs, hashes,
observation fingerprints, separate load/execution status and preserved historical
official evidence. The registered package is
`gw-11e-core-sequencing`, version
`maintained-app-mirrors-observed-2026-09-10`. Its offline generator is
`tools/build_core_sequencing_source.py`; the typed loader pins the generated JSON.
Load support and semantic execution remain separately recorded.

## Owning abstractions and consumer audit

| Consumer family | Shared owner and retained responsibility |
|---|---|
| Finite sequencing and Command Battle-shock | `sequencing`, `timing_batch_state`, `timing_batch_runtime` and `timing_rule_candidates` own tiers, immutable populations, owner choices and completion. P08A retains its required-test materialization and source history. |
| Temporary active player | `active_player`, `active_player_scopes` and scope history distinguish selected movement/attacks from turn identity. Fight, reactive movement and out-of-phase attacks push/close typed authority. |
| Phase/round/turn boundaries | `boundary_rule_flow`, boundary authority and phase-specific candidate providers discover before activation. Native army and generic runtime providers join the same owner. Explicit 07.02/07.03 ordering remains source-linked. |
| Movement and setup completion | `move_completion_triggers`, completion candidates and source-linked hook registries capture the population at the actual source event. Movement grants and opposing reactions retain their own validators and mutation services. |
| Attack completion and Hazardous | The shared attack-completion owner admits catalog and native source rules together; Hazardous rolls and retained casualty continuations finish their selected operation. No RNG is consumed during discovery. |
| Battle-shock outcomes and destruction | Shared trigger/history services distinguish source occurrence from later resolution, preserve historical physical ownership and wait for retained reactions. Materialization authenticates original casualty evidence after model-group changes. |
| Marker removal | Cult Ambush and Surveil record trigger-time candidates and validate the actual mutation boundary; deferred observation is not mistaken for removal time. |
| Mission rules | `mission_turn_end_sequencing` owns per-Action, per-owner scoring and optional mission candidates. Primary v2 evidence and lifecycle rows bind scoring owner and exact commit history; the aggregate engine API shares the same scoring service. |
| Redeploy and Scout | Redeploy uses ordinary source-backed ownership without an implicit roll-off. P24G's explicit alternating Scout cursor remains separate. |
| Adapters and persistence | Existing finite/parameterized submissions use `GameLifecycle.submit_decision`. Shared `adapters/redaction` hides private batch/trigger metadata. Contract 15, replay v9 and persistence v7 reject missing historical authority. |

The module extractions retain the repository's dependency direction and frozen
module budgets. Content-specific providers remain behind source-linked registries;
generic lifecycle orchestration does not branch on rule names or factions.

## Acceptance evidence

- `test_order36_sequencing.py` directly covers all four populated tiers, owner
  choices, source-explicit unowned mission priority, no round roll-off, immutable
  and deferred batches, invalid selection and source/owner/tier drift, hidden
  candidates, checkpoint restoration and exact replay.
- The same file covers Primary/Fixed and Primary/Action in either order, active
  Tactical choice before opposing Primary scoring, Consecration subjects in
  either order and Sensor Sweep's internal continuation. These use real mission
  state and facade submissions; scoring event order and frozen evidence are checked.
- `test_phase10s_triggered_movement.py` covers temporary movement authority,
  nested out-of-phase shooting, invalid paths and restoration. The source-loaded
  Spirit Mark regression in `test_phase17g_aeldari_army_rule.py` exercises three
  real facade moves, use/decline, fork and replay.
- Existing Emperor's Children post-shoot tests exercise source-loaded mixed
  Battle-shock/mortal-wound completion and changed target populations. Phase 14B
  covers opposing end-movement reaction order. Retained attack, Hazardous and
  Horror suites cover child continuations and historical source evidence.
- Prebattle and Fight tests preserve Scout alternation, redeploy validation and
  selected Fight authority. Static sequencing audits cover shared historical
  ownership, blocked roots, marker mutation boundaries and materialization checks.

The source's post-shoot move/shoot-back example is covered compositionally by
four-tier/deferred-batch tests plus real movement and post-attack consumers.
There is no claim that one end-to-end test executes that entire example with a
newly playable post-shoot movement Stratagem. Load-only content remains load-only.

## Initial implementation validation record

The focused migration failure list is clear, including retained-casualty owner
choices, out-of-phase post-roll authority, deferred destruction, Fall Back,
mission scoring, generated movement reactions, setup UI and replay. Ruff, mypy,
Pyright and all 11 import-boundary contracts pass. Source and engine identity,
generated contract and client checks, 342 live conformance assertions, five
TypeScript unit tests and the installed-wheel smoke pass on the initial published runtime (`57957112`).

The previous complete behavioral run found two fixture errors (a missing typed
movement ruleset and incomplete materialization transition evidence) and coverage
of 84.894%, below the unchanged 85% gate. Both fixture errors are corrected.
Additional direct P01D tests cover persisted batch transitions, trigger source and
parent authority, active-player history, accepted move endpoints, Cult Ambush
capture/continuation and Imperial Knights candidate activation. The final complete behavioral run passed all 7,202 tests at 85.01% coverage,
followed by 427 code-quality tests without coverage. Both used 18 xdist workers
and work stealing. The CI-required serial macOS semantic audit also passed all
19 tests. The successful JUnit profile regenerated all eight shards; the exact
fail-closed inventory check and pre-commit passed. No production code changed
after the successful aggregate run started.

That initial runtime passes unchanged Order 34 and Order 35 component timing and work
budgets. Initial failed measurements remain in the evidence. No complete-game
certification is claimed.

The original base was `c85ad6f3cd77a724f45517e9d17434ec4bd4e123`. Requested main
refreshes incorporated documentation PRs #443–#450. The latest fetch and merge
on 2026-09-11 included `f9f33e47`. These Track G surveys do not authorize new P01D
content work.
Branch: `codex/order-36-rules-sequencing`.

## Review correction R36-001

Review of `57957112` identified a violated P01D invariant: the persisted
active-player stack must preserve authoritative nesting order. Comparing attack
scopes as sets accepted an inverted Fight/shoot-on-death stack and changed the
effective player before later completion failed. The owning restoration validator
now merges accepted attack-selection event positions with live movement-start
positions and compares the complete ordered stack. Missing or ambiguous attack
selection authority fails closed. A search of the other active-player scope
validators found no other unordered authority comparison.

The real Unending Fidelity facade test rejects checkpoints with only the scope
list reversed, for attached and unattached retained shooting, while unchanged
checkpoints still restore and complete. Component tests cover movement before
attack and attack before movement; a static audit prohibits unordered scope
comparisons. Three existing executor fixtures now record their accepted attack
selections before their declarations and resolutions. This correction changes one production module and
adds no rules content, decision family, payload field or architecture boundary.
Generated engine/contract identity artifacts were refreshed. The adapter contract
clarifies the existing restoration requirement.

The focused timing-authority/static suite passed 130 tests. Retained-shooting,
adapter-phase and reactive-movement checks passed 132 tests before detecting the
incomplete executor fixture; its corrected focused check then passed. The first
complete coverage run passed 7,201 tests and failed three cases in two additional
fixtures with the same omitted-selection defect (84.98% coverage). Those fixture
cases and the earlier integration fixture now pass together (four cases), and
the history component tests also reject missing selections and missing/duplicate
selection events. The bounded restoration cost comparison is recorded in
`performance/order36/README.md`. No production change followed the focused fix.

The latest main fetch confirms `9fe32591` (documentation PR #451) is already
included in the branch.

Final behavioral validation passed all 7,204 tests at 85.01% coverage, using
18 xdist workers with work stealing. No production code changed during or after
that successful run. Existing behavioral files were extended; no test file was
added, removed or renamed, and the exact eight-shard inventory check passes.

The final code-quality suite passed 428 tests without coverage using 18 xdist
workers and work stealing. The separate CI-required serial macOS semantic audit
passed all 19 tests. Ruff check/format, mypy (2,941 files), Pyright, all 11 import
contracts, pre-commit, source/build identity, external-contract compatibility
against `9fe32591`, generated TypeScript checks, five TypeScript unit tests,
342 live conformance assertions and the installed-wheel smoke all pass. The wheel
contains the verified 2,747 runtime resources, 27 schemas and six validated request
families. No required local gate remains failing.
