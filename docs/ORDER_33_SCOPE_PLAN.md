# Order 33 / P10 / C10-01 and C10-02

Base: `8ef8cb83622eb30066fbd113aa94bd87e2ec4fe3` (current origin/main,
PR #436 including R32-001). Work is isolated on `codex/order-33-indirect-shooting`.

## Acceptance matrix established before implementation

The complete 10.07 text was observed in the browser at
`https://www.40k.app/rules/10-shooting-phase` on 2026-09-09. The provider
exposed no App version, so the immutable observation uses its UTC timestamp.
The maintained-mirror policy authorizes this single-provider observation;
no co-version agreement with Game Datamissions is claimed. Historical official
Core Rules evidence and earlier observations remain unchanged.

| Source clause / invariant | Runtime owner and consumers | Required regression |
|---|---|---|
| 10.02 chooses one shooting mode for the unit; 10.07 requires unengaged, no Advance, at least one INDIRECT FIRE weapon | Shooting eligibility, available weapons, selected-mode candidate filter, declaration validation | Mode eligibility; ordinary weapons remain available in mixed declarations but require visible eligible targets |
| 10.07 permits unseen targets for INDIRECT FIRE weapons | Shared shooting target authority | Normal versus Indirect for the same profile; unseen ordinary attacks rejected without mutation |
| Every INDIRECT FIRE attack in Indirect mode grants Cover and prohibits hit rerolls regardless of visibility | Declaration attack-pool construction; shared Cover, dice specifications and reroll services | Visible/unseen outcomes; real generic and Command Re-roll mechanisms; ordinary weapon isolation |
| Unmodified 1–5 fails; 1–3 fails if the firing unit remained stationary this turn and target is visible to a friendly unit | Existing stationary query, shared friendly LOS, attack hit resolver | Raw 1,3,4,5,6 with positive/negative modifiers and Cover's BS penalty |
| No Indirect-specific hit modifier exists in the operative text | Shared candidate and declaration modifier contributions | Remove both obsolete -1 contributions; preserve Heavy and independently applicable effects |
| Friendly observer means a friendly unit with current visibility; no special keyword, observer range, separate-unit, or observer-stationary requirement is stated | Current placed component visibility; retained presence and model keyword authority | Firing unit may observe; other friendly observer; attached and retained-only components; removal/cleanup invalidation |
| Visibility is evaluated when attacks are declared by the shared engine path, with resulting attack facts retained in accepted pools | Proposal validation, current-state cache identity, attack state, persistence/replay, viewer projections | Stale geometry rejection; restoration and exact replay; both viewer projections |

The 09.04 stationary definition and existing P09A movement history remain the
shared authority. No observer range is invented. Hidden/detection and terrain
continue through the existing continuous visibility query. Orders 34+ (including
Action timing, Stealth replacement and critical-hit/Snap semantics) remain out
of scope. The complete 10.07 source is retained, but its Action-after-shooting
clause is not certified by this Order.

## Live-path audit

The base already adds Cover, no-hit-reroll and stationary-friendly-visible IDs
in `_apply_phase13d_weapon_modifiers` for all Indirect-mode INDIRECT FIRE
attacks. The hit resolver and dice reroll restrictions consume those IDs.
The obsolete -1 is duplicated in `shooting_targets` and
`attack_hit_modifiers`. Ordinary weapons are separately removed by both
available-weapon helpers, the selected-mode filter and declaration validation.
Those are instances of the requested defect, including the Firing Deck path.
The existing friendly visibility query enumerates physical placements and uses
retained-aware LOS; R32-001's unit ability consumer remains unchanged.

## Execution and evidence

Task-owned command runner: `/private/tmp/order33-evidence/run.py`; each command
has a unique log and JSON record with PID, start, deadline, elapsed time and
terminal outcome. Success, exit 7 and an intentionally infinite command were
verified before expensive work. Initial sandbox failures on `ps` and git fetch
were retained; the approved execution channel resolved those restrictions.

The owner explicitly authorized early **draft** publication for this Order once
focused regressions pass. This changes publication timing only; final gates and
independent review remain required. No permanent policy exception is added.

Performance uses an isolated shooting slice on base/head with the same locked
environment, separate timing and work-count runs. Full games remain unmeasured:
mean <60 seconds and observed maximum <=300 seconds are outstanding objectives.


## Stationary audit and scope decision

Observed complete 09.04 at 40k.app on 2026-09-09T12:16:21.670Z: Remain
Stationary moves no models. The old shooting predicate conflated this choice
with Heavy's separate three-inch allowance and read temporary Movement state,
which is cleared at the phase boundary. Indirect now checks existing durable
normal-move history, together with the shared Advance, Fall Back and setup
exclusions. Its regression submits a real half-inch Normal Move with PathWitness,
crosses into Shooting and restores the session. Heavy retains its existing
separate distance allowance. Its temporary-distance lifetime is an adjacent
Heavy-history issue, recorded for follow-up rather than changed in this Order.

The scope audit found no new decision types, payload fields, named handlers,
architecture edges, geometry solver changes, faction branches or runtime text
parsing. The existing shared shooting path handles visible ordinary profiles
and unseen Indirect profiles. The adapter contract documents this corrected
eligibility within the existing schemas. Behavioral file names are unchanged.
