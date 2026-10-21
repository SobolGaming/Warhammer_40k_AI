# Bounded World Eaters gameplay outcomes

Apply `docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`. Prioritize the complete
playable behavior in this order. Block on incorrect rules, normal legal-play
failures, engine-generated valid-state save/load/replay failures, and explicitly
required trust-boundary failures. For each blocker provide the reproduced entry
path, impact, normal reachability and violated acceptance requirement. Queue
coordinated hand-edited-history hardening separately when no necessary supported
input boundary or normal path is demonstrated. Keep scope within this order;
expansion requires an explicit decision. Preserve positive controls, regression
tests, source truthfulness and every required local/remote exact-head gate.

## Reproduced invariant and narrow fix

Accepted source a7672883622fd69dcd7e3384179b987820aeccea6833467ae2ad23a1b4e4e3c3
registered Rage-fuelled Invigoration only at Fight activation. The initial Pile In
step precedes that activation. A real loaded World Eaters consumer request after
the blessing selection therefore still allowed three inches, rather than six.
This blocks an otherwise legal witnessed initial Pile In. The fixture uses a
canonical synthetic roster and legacy non-strict mustering; complete official
faction fieldability is not inferred.

The existing army-rule selection owner now records the existing generic Fight
movement-distance effect when Rage-fuelled Invigoration is chosen. It targets all
eligible units and expires with the round blessing. The shared movement owner
still enforces the matching step, PathWitness, target eligibility and geometry.
The original activation hook remains; its overlapping permission cannot stack
distance because the shared consumer takes the maximum. No new handler, generic
hook, decision shape, adapter contract or runtime support claim is introduced.

The same-class search found Aeldari Sudden Strike and catalog-sourced activation
movement options. Those are separately selected activation/resource rules rather
than a preselected round blessing. Their source timing needs its own scoped audit;
no additional normal-play defect was reproduced or silently repaired here.

## Consumer proof and limits

The new faction army-rule tests cover witnessed initial Pile In, witnessed
Consolidate, matching-step Overrun distance and round expiry; real critical
Sustained/Lethal choices, wounds, damage and completed Fight; Infantry-conditioned
Devastating Wounds damage and a non-Infantry control; Total Carnage miss, ranged,
already-fought, decline, retained Fight and single removal after restore.
Consolidate retains the Core three-inch enemy eligibility range: the longer legal
witness follows a detour to an eligible target. It does not invent broader target
eligibility. Native fixed-dice tests complement facade-driven sequences.

Icon belongs to the separate unit/wargear test file. A real facade killing attack
earns one point, repeated reads do not duplicate it, and the next round's native
Blessings request rolls nine dice and spends that point exactly once.

The accepted nineteen World Eaters cases, ninety-nine original assertions, ten
prior selected admissions and all accepted helper bytes are preserved. Eight
detachment families remain unchanged load-only scaffolds, with separate rule,
Enhancement and Stratagem owners. No detachment gameplay was added. The user
reported App v995 as translation-only; no data refresh was performed.

Battlefield-layout work in this batch is read-only. The external author packet
contains assertion, selection-overlap and cost audits and a precise follow-on
recommendation. No layout tests or unrelated setup/API tests were admitted.

Fresh complete successful JUnit profiling, 85% coverage and complete local/hosted
CI/build qualification remain separate unmet gates. Supplemental affected-file
weights and a bounded selected aggregate cannot certify them. No CI gates were
modified, no full-suite run was launched, and no publication is authorized.
