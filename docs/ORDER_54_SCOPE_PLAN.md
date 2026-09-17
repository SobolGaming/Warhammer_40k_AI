# Order 54 — oversized setup

## Invariant and source

A base that cannot physically fit wholly within its deployment zone may be set
up touching its player's battlefield edge. In a turn in which an oversized model
uses the setup exception, its rules unit cannot make Normal, Advance, Fall Back
or Charge moves, or ranged attacks. The Strategic Reserves paragraph expressly
exempts AIRCRAFT models. That exemption does not waive deployment geometry.
Pregame deployment occurs outside player turns and creates no first-turn lock.

Authority is the reviewed [03 Moving source](https://www.40k.app/rules/03-moving),
under the repository's maintained App-data mirror policy. The dated audit,
short transcription, paraphrased obligations, historical official artifact hash,
execution consumers and package hashes are committed. This is secondary mirror
evidence, not a claim of a newly retrieved official GW document. Regenerate with
`uv run python tools/build_core_large_model_setup_source.py --check`.

## Ownership and complete path

1. Mission setup retains source layout attacker/defender edges. Custom layouts
   must supply both edges to use the exception; absent edge authority produces
   an explicit unsupported diagnostic. Restore checks source layout identity.
2. Shared analytic geometry proves whether any translation and rotation fits.
   It handles circular, oval and rectangular bases, polygon unions and polygon
   or circular cutouts. Each region retains its own cutouts. Convex regions use
   exact support constraints; other shapes use quantified real arithmetic.
   Coordinates are rationalized from their decimal representation. Redundant
   regions are removed only after an exact quantifier-free proof that they have
   no point outside the union of the remaining regions. The shared membership
   predicate retains each region's cutouts and recognizes equivalent polygon
   decompositions, including coverage split across multiple regions. This avoids
   a pinned-solver rejection of redundant nonlinear branches at tangency. A failed
   sample, obstructing model or terrain feature never proves oversized status.
   Unresolved solver results raise an explicit domain error, never permission.
3. Deployment and prebattle placement retain collision, coherency, terrain,
   enemy-distance, battlefield and objective checks. Oversized bases additionally
   need analytic contact with their player's edge. Reserve fit proof considers
   rotation and the full battlefield extent, replacing the proposed-orientation
   bounding-box shortcut.
4. Reserve arrival owns the existing persisted restriction record. Every
   ordinary/reactive movement consumer, shared shooting eligibility and shared
   Charge eligibility reads one rules-unit-aware activity check. Pre-pop
   validation rejects stale ordinary/reactive choices without consuming them.
   Existing end-turn cleanup expires the record even for an opponent-turn arrival.
   AIRCRAFT exemption is derived per exceptional model from canonical keywords;
   one non-exempt exceptional model restricts the complete attached rules unit.
5. Restored arrival events authenticate the exception declaration and resulting
   restriction list against model/source authority. Existing reserve-history
   validation binds live restrictions to arrival evidence and turn cleanup.
   Decisions, events, viewers and replay use the existing shared engine pipeline.

## Scope and bug-class audit

The audit found the same missing deployment exception in prebattle geometry,
an orientation-dependent reserve fit test, unconditional AIRCRAFT restrictions,
and recorded restrictions with no movement/shooting/charge consumers. These are
instances of the requested invariant. Frozen deployment, prebattle and reserve
modules were reduced by extracting their existing validation/resolution functions
before extending them. No new decision family or named handler is introduced.

Review finding P2 in `6ae47595` exposed an incomplete absorption test: syntactically
different polygon decompositions bypassed it and falsely authorized deployment.
The repair stays in shared `geometry/setup_fit.py`; the consumer search confirms
deployment, prebattle and reserve fit queries already route through it. Regression
tests cover both region orders, coverage by one or several regions, exact-fit and
too-large bases, retained cutouts, and the canonical 200 mm deployment rejection
with and without the redundant region. The existing adapter contract covers the
unchanged proposal and invalid-result shapes; only runtime identity changes.

Order 55's transport/disembark exception and Order 66's wider Aircraft overhaul
remain separate roadmap work. This change adds no transport exception, flight
mode, faction handler, source-name gate or alternate adapter mutation path.

Contract 25 versions required mission edge identity and corrected setup semantics;
see [migration](../contracts/migrations/24-to-25.md). Old artifacts require their
original runtime; missing authority is not inferred.

## Verification

Focused regressions cover impossible versus inconvenient placement, own-edge
contact, ordinary geometry rejection, every rotation, cutouts and region unions,
AIRCRAFT/non-AIRCRAFT duration, all prohibited activities, retained permitted
activities, reactive rejection, forged restriction evidence and facade-driven
restore/replay. Static checks bind geometry/activity consumers and source pins.

Matched component performance evidence and its limits are in
[performance/order54](performance/order54/README.md). Passing final aggregate,
generated-contract, client and package results are recorded there.

Source corner edges (`north_west_corner`, `north_east_corner`,
`south_west_corner`, `south_east_corner`) designate their two adjoining
cardinal edges. Contact with either designated edge satisfies the source corner
edge; contact with an opposing edge does not. Source layout identity is retained.
