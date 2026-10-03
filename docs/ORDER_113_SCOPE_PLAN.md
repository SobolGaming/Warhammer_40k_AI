# Order113 / P24M / C24-13 â€” Blast X and Cleave X

The violated invariant is source-defined attack-count authority: Blast X must add
X dice per complete five models in the selected target rules unit, rather than
always one. The owner's bounded extension includes the equivalent parameterized
Cleave consumer with its distinct one-target-per-physical-weapon condition.
Prior112's Extra Attacks and deferred-allocation scope remain unchanged.

## Source obligations and truthfulness

The authority is the pinned original Order97 selection in
`data/source_audits/order97/selected-sources.json`, not a new official observation.
`rule:24:24.05:1` has source SHA-256
`0769f92c46c103e89c71fec090feaadc1dacb07e70c4d3c935b03c0bd2c71cb6`.
Block1 defines bare Blast as one additional die per five models present in the
Select Targets step; block2 substitutes X for Blast X; block3 gives A3, Blast2,
12 models => seven dice. Block hashes are respectively
`61214fbb343e699625f5145f1745e3c09519a804ee3d265a3d52078d0438aaa6`,
`ffd5e93f1dd55f008ed3a7893d83d6707b1f1c7b13fd799ab9c530fde9f16e70`, and
`b86450e5848426479e3f35843496649303d4e524180851aaa82a8dc7968a280e`.

`rule:24:24.06:1` has source SHA-256
`d030ed1f70e3e30f848b22c8a38f552906392d88838d8eeca88385d67c0f0bcc`.
Block1 requires Cleave X, one selected target for all attacks of that weapon,
and X dice per complete five models present at Select Targets. Its hash is
`dbca1b5f9130938d9deb8e6ff9931006d425cec3ccaa294cae44f02458e50038`.
Block2's A3, Cleave1, 16-model single target => six dice has hash
`d308825a5a98b8550601053622a521bb4bcb4b7e93e6d933f98cd00bb7fd2fe7`.
The original source captures, audit inventory/assertions and retained histories
are immutable. Current support does not rewrite the historical Order97 gap.

## Owning abstractions and complete consumer trace

- Boundary: `rules.weapon_keyword_values` parses valued catalog tokens once;
  `wahapedia_bridge` keeps normalization/provenance ownership. Existing plain
  Blast remains a supported source-defined form.
- Identity: `core.weapon_profiles.AbilityDescriptor.blast` adds positive integral
  X with deterministic descriptor identity, optional canonical target conditions,
  typed payload validation and attack timing. `weapon_ability_sources` places
  plain and valued occurrences in the same Blast family. The existing source
  occurrence selection authority chooses exactly one; instances never stack.
- Generic grants: `engine.weapon_ability_grants` owns descriptor construction
  for catalog and RuleIR. Frozen catalog/bridge modules delegate extracted
  responsibilities before extension. Explicit malformed Blast values are
  unsupported or rejected, never converted to plain Blast.
- Shooting: `_apply_phase13d_weapon_modifiers` consumes the selected profile
  through `blast_attack_bonus_for_profile`, using `RulesUnitView.alive_models()`
  and canonical target keywords when constructing accepted physical attack pools.
  Ordinary Shooting and out-of-phase/reaction declarations use this same owner.
- Fight: existing `melee_attack_counts` validates single-target totals and split
  conservation; `fight_weapon_selection` creates physical pools through
  `_cleave_attack_bonus_for_target`. Cleave retains its single-target restriction;
  split random budgets do not receive or distribute Cleave dice.
- Shared calculation: `weapon_abilities._attack_bonus_per_five` provides the
  positive-X integer arithmetic for both consumers. Counts and final attacks are
  frozen in accepted pools before resolution, casualties and target replacement.
- Persistence/replay: existing accepted events, physical source contexts,
  `melee_pool_authority`, random commitments and immutable pool payloads retain
  counts without rerolling. Existing LocalGameSession/DecisionController paths
  own submission, invalid retry and engine mutation. Adapter projections consume
  existing viewer-scoped requests/events. Exact runtime identity is regenerated.

## Acceptance matrix

| Requirement | Direct acceptance control |
| --- | --- |
| Bare Blast and Blast X differ by X; floor complete groups of five | Pure count boundaries, canonical descriptor and conditioned source ingestion |
| Source identity, value and occurrence selection survive payload round-trip | Native plain plus valued grant; Cleave1 plus Cleave2; exactly one occurrence, no stacking |
| Missing Cleave X and malformed explicit Blast X fail closed | Existing Cleave descriptor checks plus new positive integral Blast tests and generic grant shape tests |
| Fixed/random Blast uses selected attached rules-unit count | Shared ordinary/reaction facade declarations; four bodyguards plus attached members cross the five-model threshold |
| Fixed/random melee Cleave counts attached target models | Existing Fight consumer and canonical four-bodyguard/one-Leader facade controls |
| Cleave dice require all physical weapon attacks to select one target | Existing fixed Fight and random split tests; invalid overspend preserves committed roll |
| Valid engine-created boundaries restore, fork and replay | Pending declaration and accepted pool round-trips, isolated fork, both viewer reads, exact replay |
| Later casualties/replacement preserve original attack commitments | Existing replacement, retained attack and lethal continuation suites plus immutable accepted-pool controls |
| Public contract remains authoritative | Existing finite ability-source choices and parameterized attack proposals; contract note explains unchanged envelopes |

## Bug-class search and scope audit

Searched all runtime/tests for Blast, Cleave, attack bonuses, structured grant
construction, source-family grouping, identical-attack signatures, melee split
validation and commitment authentication. The only fixed-one Blast arithmetic
consumer was shared Shooting declaration validation; no reaction-specific copy
exists. Blast lacked AbilityKind/descriptor ingestion and both generic grant
builders discarded its value. Selected-target pair support rejected valued Blast.
Cleave already had typed X, target-gated source choice and fixed/random consumers;
its differing restrictions are preserved and directly exercised. Identical attack
signatures now accept the new Blast descriptor while still requiring its keyword.
No named handler, new decision family, fallback, cache, geometry solver, history
migration or unsupported-content support is added. Coordinated hand-edited-history
hardening remains separately queued absent a required boundary/normal reproduction.

## Focused validation and remaining gates

Focused red/green receipts and timestamps live in sibling `order113-state`.
The initial copied-console-launcher attempt used Order112's interpreter; the
failed receipt is preserved. The verified exact-base red run uses archived base
runtime source and schemas under a separate evidence directory. All current tests
use the corrected Order113 interpreter. Final focused results are recorded below
when implementation freezes. The exact-base negative run failed 23 cases because
the base lacked the Blast descriptor/value API; mixed-source Cleave controls
also import that new shared API, so those failures are not claimed as proof of
a previously absent Cleave implementation.

The active `.github/workflows/ci.yml`, README generator instructions,
contracts README and TypeScript conformance instructions were inspected.
Runtime identity and external examples/manifests must be regenerated and checked
against the exact PR base; original source/history pins must remain unchanged.
No behavioral test file is added/moved/deleted; the exact twelve-shard check is
required before committing. The parent owns full covered behavioral validation,
aggregate quality/type/lint/contracts, quiet serial performance smoke, two clean
exact-head reviews and hosted CI/publication. None is claimed here before it runs.

Performance is a bounded source/rule branch change, with no deliberate performance
work or demonstrated severe regression. Prepare an exact-base diff-bound
assessment; parent runs the required quiet current-runtime smoke before final
quality. Historical timing evidence remains immutable; complete-game performance
and Core Rules certification remain outstanding.

Carry forward the roadmap maintenance requirement: each completed order must
replace its own How it is currently done cell with its actual shared behavior,
without rewriting unrelated rows.

## Freeze evidence and limits

Evidence receipts remain outside the repository in `order113-state`, with command,
time, input hashes, exit code and logs. Final implementation checks are the
`focused-freeze-attacks` receipt, `focused-freeze-positive-counts`,
`focused-lint-freeze`, `focused-type-freeze`, `focused-pyright-freeze`,
`generated-support-freeze`, `identity-check`, `contract-check`, `wheel-smoke`,
TypeScript check/unit/conformance, `order97-inventory-final`, `pins-precheck` and
`shards-precommit`. The review packet records their actual outcomes and any pending
gates; a list here is not a passing-check claim. The earlier positive commitment
subset passed 12 cases; the grant/ingestion/count subset passed 61 cases.

The Windows checkout converted immutable `.txt` and some contract/pinned files
to CRLF. Restore-to-LF receipts show the recorded SHA-256 matched the original
committed bytes before any audit claim; original pins were never rewritten. Four
new authenticated historical mappings retain base bytes for original Order97
inputs extended by this order (Overwatch fixture/tests, random-melee fixture,
ability helpers). Existing histories and selected literal source artifacts remain
unchanged. The runtime manifest, existing Contract44.2 examples/manifests and
generated TypeScript client are refreshed for the current runtime identity.

The scope/architecture audit found one shared ranged count consumer and existing
Cleave fixed/random owners. Extracted boundary parsing and generic grant
construction reduce frozen modules; new modules are small and stay within current
import contracts. No new behavioral file changes the shard inventory. The exact-
base performance assessment records every changed owner and an ordinary bounded
rule branch, with no deliberate performance work or serious measured regression.
The parent must still run the quiet serial smoke, covered full behavior at >=85%,
all aggregate quality/type/lint/contract gates, exact-head independent reviews and
complete hosted CI. Full-game performance certification remains outstanding.

Requested configuration is the owner's current `gpt-6.1-sol`, `high`, FAST
(`service_tier=fast`, `features.fast_mode=true`). The parent preserved an accepted
explicit CLI probe. The implementation has no independent resolved-model or speed
multiplier attestation and makes no speed/quality advantage claim. That direction
supersedes historical model preferences in the handoff/review policy.

Final focused execution passed: 45 Order113 cases (`focused-freeze-attacks`),
61 complete helper/grant/normalization controls (`focused-freeze-positive-counts`),
9 generated-support checks, focused Ruff/format, Mypy and Pyright, runtime identity,
Contract44.2 regeneration against the exact base, installed-wheel smoke, TypeScript
type/unit/conformance, Order97 inventory and source/history pins. The exact shard
check passed before commit. These are implementation-focused checks, not the
parent's aggregate/coverage/performance/review/hosted-CI gates. All failed attempts
and superseded receipts remain outside the repository. This final prose/assessment
update changes governance inputs only; runtime/source/tests/contract stay frozen.
