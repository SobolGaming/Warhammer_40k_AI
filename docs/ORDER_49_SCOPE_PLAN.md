# Order 49 — Charge rerolls (P15E, C11-02, C15-05)

## Verified rule and scope

Verified 2026-09-14 against the retained official GW Core Rules PDF and July
Universal Rules Updates, and the maintained current App mirror:

- Core Rules 15.01 (p54): each player cannot target the same unit with more than
  one Stratagem in a phase, except where expressly permitted.
- 15.02 Command Re-roll (p56): the target is the unit/model that made the roll.
  A Charge roll is eligible, and the complete roll must be rerolled.
- 15.11 Heroic Intervention (p57): the targeted unit resolves a Charge. The rule
  contains no blanket ban on its natural Charge reroll abilities. Their own
  conditions and the general prohibition on rerolling a die twice still apply.
- 01.05.02 Re-rolls (expanded App rule, observed through the maintained mirror):
  a combined result such as 2D6 requires rerolling every die, before modifiers.
- The retained official July update and Tacoma FAQ provide no exception that
  permits Command Re-roll after Heroic Intervention on the same unit that phase.

Official sources:
[Core Rules](https://assets.warhammer-community.com/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf),
[Universal Rules Updates](https://assets.warhammer-community.com/eng_22-07_warhammer40000_universal_rules_updates-coltxp7ngi-3kvdfxwyon.pdf).
Their committed files under `docs/source_rules/` have SHA-256 hashes
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833` and
`a16ede8a54d693c91e24253e8731f12d298b68fd29f4ee457dd7ba4c69c0c053` respectively.

Secondary maintained App mirror observations:
[15 Stratagems](https://www.40k.app/rules/15-stratagems), including expanded
15.01.02 Affected By A Stratagem, and
[01 Core Concepts](https://www.40k.app/rules/01-core-concepts), expanded 01.05.02.
This provider is not GW. The official PDF independently supports the targeting,
Heroic Intervention Charge and full Command Re-roll conclusions. The official
August update announcement lists points, maps and detachment changes; the public
downloads page did not expose an additional readable Core FAQ during this check.
No unseen FAQ is asserted to have been reviewed.

The precise restriction concerns **targeting** a unit; incidental effects on an
enemy do not automatically consume a Stratagem target slot. The roadmap's old
suggestion to offer Command Re-roll after Heroic Intervention is corrected here.
Order 50 retains its separate modifier, cap, eligibility and full ordinary-Charge
pipeline work. This change closes the reroll invariant without claiming Order 50.

## Authoritative path and implementation

1. Correct the existing reviewed Command Re-roll source descriptor from targetless
   dice to the rolling unit/model, preserving stable source/handler IDs. The
   catalog's normal import hash incorporates the correction. No new faction
   handler, generated Python content, registry family or out-of-scope content.
2. Enumerate and validate its canonical friendly rules-unit binding through the
   shared Stratagem owner. CP costs, Battle-shock, same-unit targeting and repeat
   Stratagem limits now apply to every eligible roll class, including Charges.
3. Extract the existing attack-host Command Re-roll opportunity and dice-history
   continuation into small shared modules. Ordinary Charge emits a source-linked
   `charge_roll_started` event and pauses before resolving distance/targets.
   Natural rerolls are offered first; declining retains Command Re-roll eligibility.
   An accepted reroll replaces both dice and closes further reroll opportunities.
4. Extract the existing Heroic Intervention roll continuation. Its loaded ability
   index supplies the same natural Charge reroll permission as ordinary Charge.
   Source use, CP history, reaction wrapper, original dice and pending choices
   remain authenticated across submission and restore; the existing witnessed
   movement request follows. No extra Stratagem is invoked for this ability.
5. Resume through `GameLifecycle.submit_decision` for local/headless/network and
   replay. The existing result and movement-budget owner applies modifiers only
   after rerolls. Contract 20 versions the target binding and saved history.
6. Removing illegal second-Stratagem windows also exposes reaction completion
   with no pending choice. Replay and persistence verification share deterministic
   continuation bounded by an exact prefix of the recorded event tail. They
   neither stop before recorded phase progress nor advance beyond a saved
   checkpoint. The existing replay request validator is extracted alongside this
   owner, reducing the large replay module. Overwatch tests cover both boundaries.

The bug-class search covered ordinary and reactive Charges, attack rerolls,
shared Stratagem target/affected-unit tracking, natural reroll permissions,
restoration, reaction continuation and the obsolete synthetic forbidden marker.
Existing real-dice retained-reaction fixtures use updated fixed seeds so their
intended casualties still occur after the decision history changes. Existing
movement tests explicitly decline the new optional Charge reroll.
The old test that allowed Command Re-roll after prior unit targeting was reversed.
The original large Charge and attack modules lost their extracted responsibilities;
no local duplicate reroll engine or adapter-specific mutation path was added.

## Validation and delivery

`tests/unit/test_charge_rerolls.py` covers finite accept/decline, both-die selection,
natural-before-Command ordering, no second reroll, real Heroic Intervention use,
canonical attached actors, Battle-shock, deterministic restore/replay, JSON-safe
viewer projections and invalid context rejection before queue consumption.
The existing Charge declarations and Core Stratagem suites remain regression gates.
`tests/code_quality/test_order49_charge_rerolls.py` checks shared ownership, the
source target policy and the matched workload's declared performance budgets.

[Performance evidence](performance/order49/README.md) reports the existing matched
Charge slice separately from new-capability and complete-game evidence. Full-game
performance is not certified. Final validation uses the required coverage suite,
code-quality suite, lint/type/import/pre-commit gates, eight-shard inventory,
base-ref external contract checks, TypeScript conformance and installed-wheel smoke.

Final local validation passed on 2026-09-14:

- 7,999 behavioral tests with 85.11% coverage; 482 code-quality tests.
- Ruff check/format, mypy, Pyright, import-linter and all-files pre-commit.
- All eight shards regenerated from the successful JUnit run; exact inventory
  check passed before commit/publication.
- External contract checked against base `8e569cd024ffbedab035febdc262dfc410041b48`,
  installed-wheel smoke, generated TypeScript check, five TypeScript unit tests
  and 342 conformance assertions.

Final runtime fingerprint:
`cecf2e8b079f5dbee5f4de26cb179914965e035925f09580c79e980693baadab`.
