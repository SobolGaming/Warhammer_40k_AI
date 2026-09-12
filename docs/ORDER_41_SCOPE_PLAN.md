# Order 41 — Explosives source-model selection

P15B / C15-02, based on main `5180254a` (Order 40).

## Invariant and authority

During the owner's Shooting phase, Explosives targets a friendly, unengaged
EXPLOSIVES/GRENADES rules unit that is eligible to shoot and has not Advanced
this turn. Its owner selects one living, placed model with either keyword and
one unengaged enemy rules unit within 8 inches of and visible to that model.
Six D6 cause one mortal wound per 4+. The chosen model, physical component,
canonical rules-unit identities and source identity remain authoritative through
validation, CP, destruction, allocation, Feel No Pain, restore and replay.

The complete 15.06 transcription, 1 CP price, hashes and official historical
provenance were already reviewed in P15D and committed in
`core_stratagems_2026_08/artifacts/package.json`. This change preserves every
source observation, stable source ID and provider audit. It updates only the
separate Explosives semantic-execution status to `executable_engine_runtime`
and regenerates the package/evidence hashes. The other P15D rules retain their
recorded partial status. No fresh provider observation is claimed.

## Owning path and scope audit

Source JSON/typed loader → Core Stratagem catalog → existing `during_phase`
Shooting opportunity → finite `use_stratagem` unit/model/enemy option → shared
decision prevalidation → CP/use record → existing mortal-wound service →
defender allocation/Feel No Pain continuation → Shooting resume.

`ExplosivesSelection` closes the model/enemy payload shape. Enumeration and
submission share the same eligibility and geometry query. Source and target use
first-class attached rules units; the selected model retains its physical owner.
Range uses the selected model's base/hull and the target group's living models;
visibility uses the existing exact, terrain/Hidden-aware line-of-sight authority.
A nearby model cannot supply another model's range or sight. Explosives is not a
weapon attack, so a fabricated weapon profile no longer decides its targeting.

The bug-class search covered catalog timing, target policy, finite enumeration,
handler eligibility, geometry, affected-versus-targeted identity derivation,
mortal-wound destruction evidence, continuation events and source-support status.
It found duplicated GRENADES-only and unconditional Fall Back checks. Both
keywords now use the canonical model tokens. State-only Action/Fall Back
restrictions are shared with ordinary Shooting, preserving explicit Fall Back
shoot permission; Advance remains an independent absolute restriction here.

No new named handler, generic lifecycle content branch, hook registry or cache is
introduced. The existing approved `core:explosives` orchestration identity and
budget remain unchanged: it hosts the source's six-dice resolution and suspended
defender-choice continuation, delegating CP, damage, destruction and choice
mutation to their existing generic services. This PR does not extend that
orchestrator into an independent damage or shooting implementation.

The old five parameterized/start-phase tests are migrated into the dedicated
finite/facade regression suite. Their intended mortality, attached-target,
enemy-not-targeted and invalid-submission invariants remain covered. The test
file inventory is regenerated from the final complete successful JUnit profile.

## Adapter and acceptance evidence

Contract 15.2 adds a finite effect-selection variant within the existing envelope.
The public IDs and source-model event field use the existing shared Stratagem
redaction path; no private state or alternate adapter mutation is introduced.
Earlier start-phase trigger-target proposals are not accepted as the new rule.

`tests/unit/test_explosives.py` covers both keywords, each source model, mixed
model keyword ownership, model-specific range and obstructed visibility, unit
and model removal, Advance with/without shooting permission, Fall Back permission,
Action and already-shot locks, CP/phase drift, malformed/foreign choices, optional
decline, later-phase re-offer after another unit shoots, attached source/target,
defender allocation and Feel No Pain, exact persistence, replay and public views.
The static gate audits source-model geometry ownership, shared shooting
restrictions and comparable bounded component measurements.

## Validation

The focused regression run passes 239 tests; the additional stale-model,
full-source removal and separately engaged-target cases pass all 13 selected
revalidation cases. Ruff check/format, mypy (2,961 files), Pyright and all 11
import-boundary contracts pass. The reviewed source and engine identity checks
pass. Runtime fingerprint:
`b52e534f9183becafa47a1854cee1fd1cb8d194718a978980ec943d09367260a`.

The support-artifact generator completed. External contract regeneration and
compatibility against base `5180254af6cd6c0c76cce9f7930d6991b74d458e` pass.
The installed wheel validates 27 schemas and six request families outside the
checkout. TypeScript generated-client and type checks, all five unit tests, and
the live HTTP scenario pass (342 assertions, exact replay, contract 15.2.0).
The host has Node but no npm executable, so `npm ci` could not be run locally;
the installed Node entrypoints executed the package scripts and CI will perform
the clean npm installation. The initial wheel attempt encountered a local TLS
trust-store error; using system certificates completed the unchanged smoke.

The retained component comparison passes its unchanged budgets: 4.655/4.366 ms
mean for GRENADES/EXPLOSIVES, 1.792 ms out of range, 4.877 ms maximum sample
average. This is not complete-game certification.

The first aggregate reached 85.06% coverage, with 7,458 passes and one server-smoke
assertion still pinning contract 15.1. The only stale version assertion was updated
to 15.2 and its focused regression passed. No runtime change was required. The
complete behavioral coverage gate was repeated: all 7,459 tests pass with 85.06%
coverage in 526.61 seconds (18 xdist workers, work stealing). The eight committed
shards were regenerated from that successful JUnit profile, and the exact
fail-closed shard check passes. No production code changed after these gates.
All 437 code-quality tests pass in 109.99 seconds with 18 xdist workers and no
coverage rerun. Pre-commit passes without modifying any files.
