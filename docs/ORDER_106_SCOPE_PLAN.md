# Order 106 / P12C: closest Pile In target and attainable engagement

This order implements C12-05 and selected `12.03-closest-target` and
`12.03-attainable-engagement`. Each model that moves approaches the selected
Pile In target closest to it at the start and must engage that target when a
legal move can do so. An unmoved model has no new movement obligation.

## Source authority

The controlling complete source remains `rule:12:12.03:1` in
`data/source_audits/order97/selected-sources.json`, source SHA-256
`14e888de341e5254a658971a791a2e4671c575e3acd15a34cb9deba87b572d02`.
Block 12 supplies both selected obligations. Blocks 8-9 supply target selection;
blocks 11, 14, 16-17 and 19 retain base contact restrictions, ordinary witnessed
movement, final unit engagement, each model's continuing engagement and the
three-inch move limit. Shared Moving (03) supplies coherency.
The Order 97 inventory and gap observations remain historical evidence.

## Owner and consumer path

`consolidation_model_constraints.py:consolidation_model_violation` shares the
existing per-model Consolidation constraints and authenticated movement
reachability query with Pile In. `fight_pile_in_validation.py` owns the extracted
ordinary endpoint validation; `fight_rules_unit_movement.py` serves attached
source units. Existing inexpensive endpoint checks retain their diagnostic
priority before the mandatory-endpoint query. Closest selected target identity is
computed from each model's initial pose, including all physical models in an
attached enemy rules unit. Equal closest targets retain the existing shared
choice among ties. The endpoint must approach an initially closest target; a
newly nearer selected target cannot substitute for it.

For a moved model that does not engage its closest selected target, the shared
reachability query uses the actual Pile In budget, movement permissions, physical
bodies, terrain, battlefield bounds, the other proposed final positions,
coherency and continuing engagements. Only an authenticated legal full path
establishes attainability. Proven unattainability permits a closer nonengaging
move; an unresolved query returns a typed invalid result. Existing full proposal
witness validation and engine-owned mutation remain in force.

Ordinary and attached Pile In submissions use the same model constraints through
the existing Fight movement owners. Local, network and headless adapters retain
the same parameterized proposal, recorded rejection/retry, persistence and replay
path. Contract 44.1 already covers these payloads and typed diagnostics; no new
choice, field, handler or contract version is introduced.

## Validation and limits

`tests/unit/test_order106_pile_in.py` covers legal facade proposals for ordinary
and attached units, target switching, attainable engagement, legal controls,
stationary and closed-loop witnesses, tied targets, and switching physical
components inside one attached target unit. It verifies the intended committed
poses, both viewer projections/event deltas, pending and completed restoration,
rejected-proposal retry, and exact replay. A far trailing model has a proven
movement-budget exemption; a real coherence-constrained unresolved query is
rejected without mutation.

The corrected exact-base run at `3a3d4cdf1342715d3de49e986d741f7466a7b915`
(`base-red-corrected.xml`) reproduces four failures: both selected obligations
through ordinary and attached facade paths. Four legal controls restore and
replay successfully on that base. All 3,017 runtime source files matched the
base Git bytes before implementation. Initial overlapping-fixture attempts are
retained as failed setup evidence, not legal reproductions.

Three existing `test_phase15c_fight_order.py` restore/retention fixtures previously
proposed short moves for unengaged trailing models. The shared query reports
unresolved reachability in two cases and a reachable engaged endpoint in the
third. Parallel enemy ranks now make each moved living model engage directly,
preserving every original retention, authority,
physical-versus-living coherency, and checkpoint assertion. No RNG seed or
historical assertion pin changes. The existing authenticated historical archive
retains the original pinned test bytes.

Exact base reproductions and final receipts are kept in the sibling `order106-state` evidence directory. Required complete covered behavior
at 85%, quality/type/lint/contract gates, hosted CI and both clean exact-head
reviews remain separate delivery requirements.

This bounded rule repair reuses the existing reachability algorithm and cache.
The exact-base assessment and serial live smoke apply; no deliberate performance
change or full-game certification is claimed. Order 107 must start in a fresh
session after this order merges. Its implementation PR must update its own
**How it is currently done** roadmap cell with concrete prior and resulting
behavior, as required for every subsequent order.
