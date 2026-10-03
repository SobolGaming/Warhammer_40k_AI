# Order 109 / P14B: controlling units

This order implements C14-04 and Core 14.02's controlling-unit definition.
Player control, unit range, and a unit containing a positive-OC model are separate
conditions. An OC0 unit cannot borrow a different friendly unit's positive OC.
A mixed unit can control when its in-range model has OC0 and its positive-OC
member is outside objective range. Only in-range models contribute to the
player's control total.

## Source resolution

The approved maintained App mirror observation is retained in
`data/source_audits/order97/selected-sources.json`, row `rule:14:14.02:1`:
source SHA-256 `fb293871a67b148d02932262508d7e6ae93d0d92a8e8573a14b2fa96021976dc`;
block 5 SHA-256 `4c3d540e50f1fd2bd65a964a51ec9eb055a0f4ad8949b016137aa03da1d06801`.
It states that a unit within range of a player-controlled objective must contain
one or more models with OC1+. It does not require that positive model itself to
be in range. Core 01.04.01 establishes unit range through any constituent model.

The source-parent resolved this distinction on 3 October 2026 after independently
verifying the current English asset at
`https://gdmissions.app/_next/static/chunks/app/11th/rules/core-rules/page-40b1308bf97ccf3b.js`,
SHA-256 `8b7e7a4004f8a55b17305013f181bf25933dff763e6737af407da254c5656026`.
The 2 October v972 change record does not change Core/FAQ wording. The retained
Order 97 inventory's stricter in-range-positive paraphrase is historical evidence,
not runtime authority. Its bytes, assertions and pins remain unchanged. This
resolution supersedes that paraphrase and the old Order109 roadmap requirement.

Core 14.02.01 still determines player control before other end-boundary rules;
secured objectives retain their player-control semantics. No separate unit
"contest" status is introduced.

## Owners and consumers

`engine/unit_objective_control.py` owns the shared three-condition query. The live
path uses canonical rules-unit components, physical presence, Battle-shock and
the existing OC modifier resolver. Attached bodyguard and Leader members share
unit control. Accepted retained models follow existing rules-presence semantics;
removed models cannot supply OC. Objective scores and contributor inventories
are unchanged.

Generic Stratagem objective-selection enumeration and validation use this query.
They first require player control and unit range before resolving the unit's OC,
so an out-of-range unit's legitimately unprepared random OC does not prevent
empty enumeration or typed selection rejection.
Their existing range helper remains available for rules requiring only a unit
within range of an objective its player controls. In particular, Corsair Coterie's
Cloak and Shadow target text says "within range of an objective marker you control";
it does not demand unit control and continues to allow OC0 units.

Primary mission action completion uses the same predicate against the existing
objective-record authority checkpoint. That immutable checkpoint already contains
all model OC values, component/group identities and physical presence, including
members outside objective range. It supplies the same answer during completion
and restore validation; later live state does not rewrite the boundary. No new
decision, payload field, schema or external contract version is needed.

Random OC and optional modifier preparation includes present models of an
in-range rules unit, so positive OC outside range can be evaluated through the
existing recorded decision machinery. This does not add those models to player
scores or objective range evidence.

The bug-class search distinguished unit-control conditions from range conditions.
`catalog_sticky_objective_runtime` consumes the source-linked RuleIR relationship
`source_unit_within_controlled_objective` and scope
`controlled_objective_within_source_unit_range`; its restore counterpart in
`objective_control_record_authority` validates that same range condition. Both
remain unchanged. Faction range predicates and mission-action start range
enumeration also remain range predicates. This order does not alter their source
definitions or broaden faction support.

## Validation and limits

The base `be9bda2bf56ffde3147727fb9dc869c4163ddabc` reproduction uses a config-backed
canonical lifecycle, five OC0 infantry and a separate OC1 friendly unit. The
shared Stratagem query incorrectly selects the objective for the OC0 unit after
successful JSON persistence restoration. The external Order109 state directory
retains that original script and result.

Focused regressions cover all-OC0 exclusion, positive controls, mixed attached
units, controller/range/tie/secured cases, modifiers, Battle-shock, frozen mission
completion evidence, rules-present retained versus removed positive members,
facade boundaries, both viewers, valid persistence and exact replay. The actual
Maintain Control mission action starts through the facade with OC0 bodies touching
a linked terrain objective and its attached positive-OC Leader outside the entire
footprint. Both action-first and scoring-first boundary sequences survive pending
and completed JSON restoration and exact replay. These fixtures establish a valid
battle state before the exercised decisions; they do not claim a complete game
from army deployment. Full gates and independent exact-head reviews remain delivery requirements;
the focused evidence does not certify all Core Rules or complete-game performance.

The performance assessment binds this ordinary rule correction to the exact PR
base and changed owners. It adds bounded unit-member checks and required OC
preparation; no performance improvement is claimed. The owner's sequential
policy requires serial current-runtime smoke and all live semantic/work/cache
checks, while preserving historical measurements.

After Order109 merges, stop and hand off Order110 in a fresh session. Every
subsequent order must update its own roadmap **How it is currently done** cell
to the actual implementation, preserving unrelated rows and historical bytes.
