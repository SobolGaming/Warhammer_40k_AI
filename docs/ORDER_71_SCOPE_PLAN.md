# Order 71 / P17 — engaged shooting penalties

Finding: C17-01. Base: `ec32e01f` (merged Order 70, PR #490).
Scope: Core 10.06 and 17.03 targeting, model ownership, source-preserving
modifiers and shared attack consumers. Category certification remains Order 73.

## Invariant and source evidence

A CLOSE-QUARTERS attack is exempt from either engagement penalty only when its
attacking rules unit is engaged with that specific target. Core 10.06 applies
to the attacking MONSTER/VEHICLE **model** in an engaged rules unit. Core 17.03
applies to an engaged target MONSTER/VEHICLE **rules unit**. Both causes contribute
independently before other modifiers and the final +/-1 hit-roll cap. PISTOL
uses the existing shared CLOSE-QUARTERS equivalence.

10.06 reuses the complete authenticated 40k.app observation retained by Order 34
in `core_actions_2026_09`, observed `2026-09-09T14:50:00+00:00`. Its stable source
ID remains `gw-11e-core-actions:close-quarters-shooting`; its transcription hash
remains `c44508145d53b35217bab6049826848d84569409feb52ab41e3644aa94f6dc78`.
The original observation and partial-execution record remain immutable; this PR
supplies the additional targeting/modifier consumer proof, not a new observation
or certification of all Action clauses.

17.03 was observed through the search index of the non-affiliated
[40k.app Monsters and Vehicles page](https://www.40k.app/rules/17-monsters-and-vehicles)
on `2026-09-21T18:41:25Z`. Direct requests returned HTTP 403. No direct capture,
App-data version, official-App observation or co-version comparison is claimed.
The two complete operative paragraphs are retained in the versioned JSON package
`gw-11e-core-engaged-shooting` and linked maintained-mirror audit. Their stable ID
is `gw-11e-core-engaged-shooting:engaged-monster-vehicle-target`.

| Evidence | SHA-256 |
| --- | --- |
| 17.03 transcription | `12806475dcbcab62cd737334b032c0f214dff4fd11720161cdbaeb4405eee26e` |
| Mirror observation | `fe8800c2b4aaa318418101e797fd98bce387f07dc15d995e992f287e1aecba4a` |
| Audit observation | `71dded5a559844c3f96399ef560988c8d422954d65a9c4a5c668d7daabd09d5e` |
| Source artifact bytes | `0dfed05d9cf2d7b842f66b9e7375a636e6b45ed73a09f8831521dc43e38692ab` |

The eager typed loader pins artifact bytes and validates source identity,
transcription hashes and separate load/execution status. The authority registry
pins the new audit tuple and allowed package IDs. Historical official Core Rules
PDF hash remains `f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.

## Authoritative path and same-bug-class audit

Canonical catalog model keywords and weapon profiles -> physical rules-unit
engagement -> per-model candidate/weapon inventory -> shared declaration
validation -> independent source-linked RollModifiers -> AttackSequence,
Psychic selection and final hit cap -> engine events, scoped adapter projections,
restore and replay.

`shooting_engagement.py` owns the common exception and the two independent
penalty sources. `shooting_targets.py` supplies current canonical engagement
and the actual observer model's keywords. It no longer promotes a component's
union of keywords into firing-model authority. Attached target keywords retain
rules-unit scope. No local keyword normalization remains in that candidate owner.

The old OR expression both collapsed two penalties into one and exempted every
CLOSE-QUARTERS profile. The targeting audit also found that an engaged
MONSTER/VEHICLE model was incorrectly forbidden from firing a CLOSE-QUARTERS
weapon at another target, and that a third-party engaged target changed an
unengaged shooter's mode to Close-quarters. Both contradicted the same retained
10.06/17.03 clauses and are corrected here. Non-MONSTER/non-VEHICLE models in
an engaged rules unit still require CLOSE-QUARTERS weapons and an engaged target.
BLAST's engaged-target prohibition remains enforced before pool construction.

The weapon-inventory audit found two component/rules-unit keyword checks with
the same model-scope problem. Both now filter each physical weapon owner.
Borrowed Firing Deck weapons retain the Transport model as attacking owner.
Declaration modifiers replace the legacy `big_guns_never_tire` identifier with
the two authenticated source IDs. Psychic options can keep or ignore either
source independently; grouped signatures preserve both sources.

The audit covered candidate caches, ordinary and out-of-phase declaration
validation, Snap/Overwatch, retained Shoot On Death, Firing Deck, grouped pools,
Psychic choices and the common hit resolver. There is no adapter-side rule,
new player decision, named handler, hook registry or architecture exception.
Fortification-specific semantics and unrelated keyword consumers are not
redefined by this change.

## Regression and contract evidence

Tests cover the two causes separately and together, CLOSE-QUARTERS/PISTOL
exemption only against the engaged target, third-party shooting, attached model
permission versus target-unit keyword scope, BLAST rejection, changing target
keywords after casualty, cache revalidation, and JSON candidate round trips.
Facade tests cover malformed and wrong-mode pre-pop rejection, ordinary attacks,
reactions, Overwatch's unmodified-six rule, Transport ownership of borrowed
weapons, Shoot On Death, +0/+1/+2/+3 offsets, the final hit cap, selective Psychic
source ignores, exact restoration, both viewer projections and replay.

The existing finite/proposal envelope and modifier-source fields cover the
change. No schema version bump is required. The adapter contract documents the
changed source values and candidate mode semantics. Old persisted/replay states
remain bound to their original runtime build; no source-ID compatibility shim
is added. External examples are regenerated for the new runtime identity.

Behavioral regressions extend existing test files, so shard membership is
unchanged. The exact eight-shard check remains a publishing gate. Static audits
reject the legacy runtime token, local keyword normalization and loss of either
source contribution, and verify source reproducibility.

## Scope audit and final validation

Production behavior changes are confined to the common shooting candidate,
model-owned weapon inventory and declaration modifier mapping, with one small
shared policy module. Source artifacts and loaders stay at the data boundary.
No unrelated phase behavior, faction content or excluded content is added.

Reproduce source data with `uv run python tools/build_core_engaged_shooting_source.py --check`.
The active CI workflow requires runtime/contract generation, exact-base contract
compatibility, installed-wheel smoke, TypeScript generation/type/unit/conformance,
lint/type/import checks, shard inventory and the two final Python suites.

Matched component evidence and the unchanged inherited guards are recorded in
[performance/order71](performance/order71/README.md). Complete-game performance,
the 60-second mean/300-second maximum targets and deferred Order 32 budgets are
not certified. Final validation results are recorded there before publication.

The first published head (`cee6f5bb`) passed 8,712 behavioral tests with 85.1428%
coverage and all 570 code-quality tests. Its results are retained as historical
evidence in the validation record; the review corrections below require fresh
runtime identity, measurements and full validation before publication.

## Review corrections: model scope and execution-consumer proof

P2 identified the last live physical-unit MONSTER/VEHICLE union check in shooting:
`_validate_model_pistol_exclusivity`. Model-specific permission must come from the
declaring source model. The shared validator now resolves the source model ID
(including borrowed-weapon source identity) and reads that model's canonical
keywords through the existing `is_monster_or_vehicle` predicate.

Eight facade cases use one physical unit with two catalog-authenticated model
profiles: ordinary infantry and a MONSTER or VEHICLE model. They cover both
CLOSE-QUARTERS and PISTOL, both declaration orders, rejection before queue pop
without state mutation, legal mixed weapons on the exceptional model alongside
the infantry model's separate declaration, persistence, both viewers and replay.
Before the fix, the first case reproduced acceptance of the infantry model's
illegal mixed declaration. The existing homogeneous and Firing Deck cases remain
part of the focused consumer run.

The bug-class audit finds no remaining call to the physical-unit union helper
in shooting modules. The rules-unit helper in shooting-mode eligibility remains
deliberately unit-scoped and consumes model-validated candidate types. Movement
and terrain predicates are separate unit rules, outside this shooting invariant.
A static audit prevents reintroducing the physical-unit helper into shooting
and pins the declaring-model authority of the exclusivity guard.

P3 is addressed by the separately versioned, hash-pinned
[runtime consumer proof](../data/source_audits/order71-runtime-consumer-proof-v1.json).
It links each of these operative clause families to concrete runtime symbols and
regression functions:

| Source clause | Runtime owners |
| --- | --- |
| 10.06 model weapon and target permission | `_locked_in_combat_validation`, `_target_engagement_validation`, `_validate_model_pistol_exclusivity`, both model-owned weapon inventories |
| 10.06 attacking-model penalty and target-specific exemption | `engaged_shooting_penalty_sources`, `declaration_hit_modifiers` |
| 10.06 BLAST against the attacker's engaged target | `_blast_engaged_target_validation` |
| 17.03 engaged target-unit selection | `_target_engagement_validation` |
| 17.03 BLAST target exclusion | `_blast_engaged_target_validation` |
| 17.03 target-unit penalty and target-specific exemption | `engaged_shooting_penalty_sources`, `declaration_hit_modifiers` |

The typed code-quality loader validates the proof hash, both complete source
artifact hashes, transcription and mirror-observation hashes, exact clause
inventory, owner/regression symbols, and the shared candidate's consumer calls.
Both source packages and their authenticated observations remain byte-for-byte
unchanged. This supplements their original execution metadata; it does not
upgrade the preserved partial 10.06 record or certify unrelated Action clauses,
all Making Attacks semantics, or an entire category. A later proof revision must
use a new versioned record rather than rewriting these observation identities.

The review changes one existing runtime validator and adds no decision envelope,
schema, mutation path, handler or registry. The existing mixed-declaration
diagnostic and adapter contract apply unchanged. Refreshed performance and final
validation are recorded in [Order 71 validation](performance/order71/validation.json).

Review validation passed 8,720 behavioral tests with 85.1425% coverage and all 572 code-quality tests without coverage. Lint, both type checkers, import boundaries, shard inventory, generated artifacts, exact-base contract compatibility, installed-wheel smoke, five TypeScript tests, 342 live conformance assertions and all-files pre-commit passed. All six refreshed component evidence sets pass their unchanged guards. `npm ci` was unavailable; direct Node package-script equivalents passed with installed dependencies. No production code changed after the behavioral run began.
