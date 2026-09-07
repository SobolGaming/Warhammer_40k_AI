# Order 28 / P24I scope review

Status: the owner approved the scope below on 2026-09-07. Implementation and all required local validation are complete. Published in [PR #433](https://github.com/SobolGaming/Warhammer_40k_AI/pull/433); not merged.

Finding: `C24-09`. Reviewed base: `67c60842ef87d3df646ec762f4e328eeff46ee0b`,
matching `origin/main` after fetch on 2026-09-07. Orders 26 and 27 are merged
through PR #432. No open PR was returned by the repository PR inventory.

## Invariant and source

Every applicable modifier to a Psychic attack's BS/WS or hit roll must retain
its individual source identity until the controlling player has chosen which
modifiers to ignore. Only retained modifiers may then be combined and bounded.
Equal or cancelling numerical outcomes do not identify the same selection.

The operative maintained-mirror statements were observed through indexed
[24.29 Psychic](https://www.40k.app/rules/24-core-abilities) and
[02.02.02 Ignore Modifiers](https://www.40k.app/rules/02-datasheets).
The former permits selection among BS/WS and hit-roll modifiers for each
Psychic attack; the latter expressly allows retaining only some modifiers,
including when positive and negative modifiers cancel.

Direct retrieval returned HTTP 403. No App version, direct official capture,
or co-versioned mirror comparison is asserted. Before semantic changes, retain
the exact operative transcriptions in the versioned source package and audit,
with provider, URL, observation time, transcription SHA-256, immutable observation
fingerprint and source-authority registry pins. No source ambiguity was observed.

## Authoritative path before implementation

1. Catalog profiles and source-linked runtime bindings enter
   `RuntimeModifierRegistry.modified_weapon_profile`. Registered providers
   transform the profile sequentially, followed by generic RuleIR effects.
2. `rule_ir_modified_weapon_profile` applies BS/WS changes through
   `_modified_characteristic_value`. That helper bounds each change and uses
   `CharacteristicValue.from_raw` on the result. Individual operations and the
   original skill are lost. Existing Adeptus Mechanicus, Astra Militarum and
   T'au skill helpers also clamp and replace raw values.
3. Shooting target validation adds source rule IDs but sums hit adjustments
   into `ShootingTargetCandidate.hit_roll_modifier`. Declaration validation
   adds Heavy to the same scalar before constructing attack pools.
4. `attack_sequence_hit_wound._hit_skill_modifier` combines Cover and Plunging
   Fire. `_hit_roll_modifier` combines the attack-pool scalar, persisting
   effects and `RuntimeModifierRegistry.hit_roll_modifier`. The registry and
   generic dice-effect consumer return totals rather than individual effects.
5. `attack_sequence_psychic_modifiers` creates the finite choice from those
   two totals. A zero/zero total suppresses the request. Other requests group
   choices by beneficial/detrimental buckets and deduplicate equal outcomes.
6. Both Shooting and Fight consume this shared attack sequence through the
   lifecycle decision controller. The current selection record carries totals,
   not individual modifier identities. Hit resolution compares totals again.
   Source changes preserving the totals cannot be detected by that comparison.
7. Decision records, attack pools and weapon profiles flow into lifecycle/session
   checkpoints, event projections, persistence and exact replay. The complete
   fix consequently changes serialized runtime evidence and generated identity.

## Pre-fix reproductions

Executed on the reviewed base with `uv run --no-sync python -`, using real
domain objects from `tests.phase13b_shooting_declaration_helpers` and production
consumers. No integration stub or test-module import was used.

| Scenario | Required result | Observed result |
| --- | --- | --- |
| Psychic pool with Cover and Plunging Fire rule IDs | Choice remains available for the two modifiers | `_psychic_attack_modifier_ignore_request` returns `None` |
| BS 2, generic RuleIR deltas -1 then +1, retaining both | BS 2 after combination and one final bound | BS 3; raw/base/final all overwritten to 3; modifier IDs empty |
| BS 2, the same deltas +1 then -1, retaining both | Same result and individual evidence | BS 2; raw/base/final all overwritten to 2; modifier IDs empty |

The command completed successfully as a diagnostic: these are observed failures
of the required invariant, not passing behavioral regressions. The existing
Psychic tests in `tests/unit/test_phase13b_shooting_declarations.py` exercise net
modifiers and do not establish arbitrary individual selection. Existing ordered
modifier regressions were also inspected in
`tests/integration/test_core_modifier_boundaries.py` and
`tests/unit/test_attributes_modifiers.py`.

## Required scope decision

AGENTS.md states: "If the required solution is materially broader than the
apparent request, pause before broadening it."

The apparent selection repair reaches an additional upstream defect: weapon-skill
producers discard operations and clamp them before the attack exists. A local
choice-menu repair cannot recover a discarded modifier, its value before the
cap, or its source. Repairing this requires changing the weapon-skill producer
contract, its serialized provenance, and affected existing faction-provider
implementations. The Core remediation roadmap otherwise excludes faction work.

Approved decision: include that necessary upstream provenance/arithmetic repair
and migration of existing BS/WS producers in the single Order 28 PR. Keep the
work limited to the individual Psychic-modifier invariant and its common
consumers. Do not add faction content or certify faction rules as part of it.

## Approved implementation

1. Add failing regressions for the reproductions above, plus opposing effects
   within the same hit bucket and equal-valued distinct source effects.
2. Preserve typed individual skill operations and source identities at their
   producers. Combine retained operations through the existing shared arithmetic
   owner and apply final skill bounds once. Migrate existing skill producers
   without adding named handlers or content branches to generic code.
3. Preserve declaration, persisting-effect, registered-binding and generic hit
   contributions before aggregation. Audit duplicate ability occurrences
   separately from independent modifiers; retain the P24C2 ownership boundary.
4. Define source-bound Psychic choices through the existing adapter contract.
   Support arbitrary subsets without collapsing equal outcomes. Prefer a
   deterministic sequence of finite individual choices, with explicit whole-set
   shortcuts, to exponential enumeration or an artificial modifier-count cap.
   Confirm the final shape in `docs/ADAPTER_DECISION_CONTRACT.md` before coding it.
5. Revalidate complete modifier snapshots and active attack context before queue
   pop. Reject malformed, foreign, duplicated, stale and drifted selections
   without rolling dice or mutating state. Reuse the same owner in Shooting,
   Fight and supported out-of-phase attack hosts.
6. Authenticate source lineage, selected identities and effective arithmetic on
   pending/completed restore and replay. Exercise facade submissions and both
   viewer projections/event streams through the shared adapter redaction owner.
7. Add feasible static guards against pre-choice aggregation and provenance loss.
   Update evidence, load/execution status, roadmap, contract, schemas/examples,
   engine identity and TypeScript client wherever affected.
8. Audit architecture, module sizes and diff scope before aggregate validation.
   Extract responsibilities before extending frozen oversized modules.
9. Run focused regressions, then every AGENTS.md final gate. Regenerate the
   eight-shard inventory from the successful complete JUnit profile if adding
   behavioral test files. Inspect active CI and generator documentation; run
   base-ref compatibility, generated-client checks, conformance and wheel smoke.
10. Commit, push and create the new PR in the configured repository. Record its
    URL and validation results; leave merging to the owner.

Explicit exclusions: the P22B Psychic ability-use ledger, duplicate weapon/core
ability instance selection owned by P24C2, unrelated characteristic families,
new faction rules, new generic hook families without a current source consumer,
new named handlers, movement semantics and whole-engine certification.

Validation status: 6,609 behavioral tests passed with 85.07% coverage; 390
code-quality tests passed. All required lint, format, type, import, pre-commit,
eight-shard, source/artifact, base-ref compatibility, generated-client and
installed-wheel checks passed. Live client conformance passed 342 assertions.
The complete validation record and publication status are in the Order 28
section of `CORE_RULES_REMEDIATION_ROADMAP.md`.

PR #433 review follow-up: the owner requested independent source authentication
for completed modifier history. The original head passed CI, but the coordinated
source/hash/actor forgeries were reproduced in standalone restoration. The correction
retains one pre-declaration lifecycle origin and reconstructs its decision tail with
the existing engine replay owner. This includes original declaration and effect inputs
without adding content-specific historical handlers. The contract and the roadmap's
completed-history correction section record the authority boundary, scope, restore
cost and revised validation. Publishing this correction updates PR #433.


Revised validation passed: 6,631 behavioral tests with 85.07% coverage, 390
code-quality tests, 67 focused Order 28 regressions, all lint/type/import/pre-commit
checks, the exact refreshed eight-shard inventory check, source and contract
regeneration/base-ref compatibility, installed-wheel smoke, five TypeScript client
unit tests and 342 live conformance assertions. The roadmap records runtime identity
and the distinction from the previously reviewed CI-successful head.
