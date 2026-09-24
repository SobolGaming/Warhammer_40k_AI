# Order 82 / P01E — revived-model engagement

Status: implemented and locally validated in [PR #502](https://github.com/SobolGaming/Warhammer_40k_AI/pull/502); merge pending. Finding C01-05.
Dependency: Order 81 / C03-05 merged as PR #501, main
`c0d172f2f209f75144da1625b0f5b6f0721b9c34`. The owner's September 24 request
approves this implementation. PFINAL remains Order 83 and requires a fresh
complete audit after this prerequisite merges.

## Invariant and controlling source

A returned model may engage another model of an enemy rules unit already engaged
with the receiving rules unit. Only coherency refers to models present at the
start of the phase. The previous HealingEffect snapshot and validator instead
restricted individual enemy models, and some producers omitted the snapshot,
which rejected every engaged placement.

The complete expanded Core 01.02.03, “Revived and Adding Models to a Unit”, was
read through the ordinary browser at
<https://www.40k.app/rules/01-core-concepts#01.02.03>. The retained observation
was finalized at 2026-09-24T13:16:10+00:00 (09:16:10 America/New_York).
The provider exposes no App-data version; none is inferred. The complete text,
transcription SHA-256, source-observation fingerprint, non-affiliation statement,
separate load/semantic status and historical official-PDF provenance are pinned
in `core_revival_2026_09/artifacts/package.json` and
`data/source_audits/maintained_app_mirrors/revival_2026_09_24.audit.json`.
Stable source ID: `gw-11e-core-revival:revival`. The immutable source-authority
registry explicitly authorizes this observation and package. Reproduce with
`uv run python tools/build_core_revival_source.py --check`.

This source record supports the changed engagement clause. It is not a new
certification of every enclosing revival, wargear, capacity or Starting Strength
requirement. No contradictory or ambiguous source statement was encountered.

## Ownership and same-class audit

`HealingEffect` retains amount, granting source/context, selection actor,
phase-start coherency anchors and step history. It no longer accepts or emits
`phase_start_enemy_engagement_model_ids`. Legacy payloads fail with an explicit
domain error. No mapping from old model IDs to current unit IDs is attempted.

`healing_revival` validates the current player proposal before queue pop, calls
`revival_engagement_evidence` on the unmodified battlefield, and only then
applies the hypothetical wounds/placement through the existing engine owner.
The shared physical geometry inventory supplies canonical attached groups and
all rules-present models, including Fight On Death retention. One predicate
compares the enemy units engaged before return with those engaged by the returned
model; the model cannot establish its own permission. Each later revival uses
its own pre-return state. Phase-start coherency and all source restrictions remain
in their existing validators.

| Producer/consumer | Disposition |
|---|---|
| Necrons Reanimation, generic command restoration, generic Stratagem Healing | Remove the duplicated snapshot capture; their shared placement service owns engagement. |
| Chaos Daemons Battleline manifestation | Previously omitted the snapshot; receives the same correct engagement check without content-specific wiring. Its strict event reader consumes the shared typed engagement evidence; pending/completed progress use one shared event reader. |
| Catalog Battle-shock healing, destroyed-enemy wound recovery, non-Battleline manifestation | Wound-only constraints remain with their source owners; no new revival permissions or faction support are added. |
| Selection and placement dispatch, command continuations | Same lifecycle submission, finite options and typed proposals; no alternative mutation route. |
| Destruction/restoration and physical transition history | Existing exact decision/event/placement authentication remains; accepted battlefield revivals additionally require source-bound unit engagement evidence. |
| Restore | `revival_engagement_history` recomputes the predicate using authenticated pre-return physical rows and canonical rules-unit membership. It checks exact source/package and unit sets, retained presence, removed-model state and one-to-one decision/mutation closure. |
| UI/network/headless/replay/viewers | Existing shared facade and redaction owner. Both viewers see public engagement evidence; protected nested source context remains redacted. |

The same-class search covered every HealingEffect construction, snapshot reference,
healing request reader and restoration consumer. Separate return-on-death and
model-materialization placement families retain their own source-defined rules;
this PR does not broaden them, implement new content or add named handlers.
The retained `scripts/probe_order81_revival.py` intentionally reproduces the old
defects against its documented base `45561d864c3634ce1d0e00d2b6599091ef43ed58`;
its old API calls remain historical evidence. Current-runtime diagnostics use
the Order 82 facade regressions and `scripts/measure_order82.py`.
Current attached membership and source-authorized pre-battle split identities
remain owned by `rules_units`; revival does not dissolve or reconstruct them.

## Regression and architecture evidence

The first regression failed on the base with the reported `(12, 12)` placement.
The fixed facade cases cover ordinary and attached recipients/enemies, engagement
with a different model/component, retained enemy presence, a removed engagement
anchor, a genuinely new enemy unit, unchanged state after rejection and a legal
retry. Both viewer projections, JSON-safe events, checkpoint recovery and exact
replay are asserted. Corrupted before/returned sets, missing evidence, source hash
drift and legacy model-scoped effects fail restore. Existing Healing and adapter
regressions retain wound limits, phase-start coherency, stale/malformed proposals,
source restrictions, actor ownership and recursive redaction coverage.

Two small runtime modules own the shared revival predicate and its historical
authentication. The old per-model engagement loops and all producer snapshots
are removed. Existing shared physical predicates and engine decision/mutation
boundaries are reused; no architecture boundary, fallback, cache, speculative
hook, name-based behavior gate or named handler is added. Scope and diff are
reviewed before aggregate gates.

## Contract, generated artifacts and validation

Contract 36 records the changed mutation semantics and removal of the obsolete
HealingEffect property. Replay advances to v30, operator persistence to v28 and
server wrappers to v36. Existing proposal families and viewer policy keep their
shapes. See `contracts/migrations/35-to-36.md` and the Order 82 adapter contract.
Released compatibility baselines remain immutable; the new baseline, runtime
manifest, external examples and TypeScript client are regenerated together.
The new behavioral file is added to the eight-shard inventory using the complete
final JUnit profile.

Matched base/head measurements and the numeric slice budget are retained in
`docs/performance/order82/`. The base is the unchanged archived runtime with the
same current fixture and benchmark; its rejecting result is a cost comparison,
not a correctness oracle. Inherited performance evidence is refreshed as required
by existing gates. Removing the obsolete field also changes the Order 81 shared
fixture: its original baseline runtime `45561d864c3634ce1d0e00d2b6599091ef43ed58`
and current runtime are remeasured with the same updated fixture into Order 82's
`projection-base.json` and `projection-head.json`. The original Order 81 reports
and projection budget remain unchanged. No complete game is measured or certified; the full-game
60-second mean/300-second maximum targets remain outstanding.

Final validation: 9,177 behavioral tests passed with 85.22% coverage; 615 code-quality tests passed. All required local gates passed.
Commands, hashes, counts and limitations are recorded in
`docs/performance/order82/validation.json`. PR URL: [#502](https://github.com/SobolGaming/Warhammer_40k_AI/pull/502).
Merge commit: pending owner review and merge.
