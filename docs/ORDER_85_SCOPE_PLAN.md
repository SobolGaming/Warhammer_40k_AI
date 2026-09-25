# Order 85 / P01H: witnessed deemed base contact

Implementation and final artifacts have independent approval. Required local
validation passed before publication; evidence is recorded below.

## Source and invariant

Core 01.04.04 grants symmetric deemed base contact after a qualifying move toward
an enemy whose overhang prevents physical base contact. The distance available
must suffice for a legal contact move without that enemy's overhang; the models
must remain as close as possible and some part of either must remain within one
inch of some part of the other. Authority expires at the actual turn boundary.

The complete expanded rule was inspected on September 24, 2026 (America/New_York)
at the maintained [Game Datamissions Core Rules mirror](https://game-datamissions.com/11th/rules/core-rules#rule-01.04.04).
It exposes no App-data version and is not an official GW capture. The versioned
`core_base_contact_2026_09` source package preserves this provenance, observation,
text and hash under the maintained-mirror source policy. Reproduce its package
and audit with `uv run python tools/build_core_base_contact_source.py --check`.
The Order 84 audit remains an immutable record of the earlier implementation gap.

## Approved prerequisite and architecture

The owner approved the physical-geometry prerequisite on September 24, 2026.
The catalog already distinguished a physical footprint from a support base, but
runtime construction retained only the rules footprint. A contact flag could not
establish physical impossibility using that representation.

Runtime models now preserve explicit, provenance-linked body prisms separately
from their rules base. Shared collision predicates cover moving bases against
physical enemy bodies in transit and full bodies at endpoints, including
placement, disembarkation, return and reserves. Fall Back's projected crossing
inventory includes overhangs. Terrain endpoints and impossibility certificates
share the same explicit ground/support-plane domain; floating endpoints cannot
supply a legal alternative. This represents catalogued prisms, not an inferred
or universally certified mesh for every commercial miniature.

`geometry/base_contact.py` proves the counterfactual using the actual witnessed
movement budget, terrain, collision, whole-rules-unit coherency and owning move's
endpoint restrictions. Continuous position/orientation certificates establish
negative results over a relaxed domain; a positive relaxation is only a candidate
and still requires a validated path. Search exhaustion remains typed unresolved.
Fight and Surge target restrictions include closer selected targets, continuing
per-model engagement, unit engagement obligations, forbidden targets and
conditional mandatory endpoints. Only the enemy overhang is removed in the
counterfactual; other obstacles remain.

The engine derives contact authority from accepted movement events and per-model
movement history. It binds source ID, physical pair, geometry, witnessed path,
move permissions, budget, source targets, battle round and actual turn owner.
Restore authenticates these against accepted physical history and decisions and
rejects correlated alterations, omissions, duplicates and unknown nested fields.
Continuing contact refreshes current physical dependencies; loss of proximity or
closest placement suspends it. Absence from the battlefield suspends authority;
return of the same physical identity is still subject to every condition and
turn expiry. No adapter makes a separate contact choice or mutates authority.

## Consumer and contract audit

The shared Fight base-contact predicate consumes symmetric deemed contact for
pile-in/consolidation movement locks. Charge and reactive movement produce the
same witnessed authority. Ordinary geometric base contact remains immediate.
Numeric distance, Engagement Range, attack target eligibility, coherency and
objective measurement retain their existing base/hull semantics: 01.04.04 grants
contact status, not a replacement measured range. Physical collision uses the
separate body description.

Contract 39 records body geometry and movement proof authority; required history
arrays cannot be omitted. Shared adapter redaction removes full feasibility
queries and counterfactual paths from both players' event views. Operator saves
and exact replay preserve the complete evidence. See the
[adapter contract](ADAPTER_DECISION_CONTRACT.md) and
[38-to-39 migration](../contracts/migrations/38-to-39.md).

## Evidence and independent review

The matched base is `19a5b863e8bd3b15541facb73fd4c0f78a835ce1`. The real Charge
facade fixture uses a solid radius-four-inch target on a 120 mm support base, a
40 mm mover, and a twelve-inch engine-issued budget. Base rejects physical body
contact (base gap 1.637795 inches) but accepts penetration to a 0.5-inch base gap;
head reverses those results. The matched diagnostic is reproducible with
`scripts/measure_order85.py`; retained input hashes, timings and results live in
[performance evidence](performance/order85/README.md). These are component/slice
diagnostics, not full-game certification.

Direct and facade regressions cover source/budget/proximity conditions, physical
penetration and retry, fresh and Charge-derived Fight contact, attached units,
Consolidation target constraints, Surge permissions, opponent-turn ownership,
turn expiry, physical absence, symmetry, unchanged numeric range, viewer
redaction, forged restore evidence and exact replay.

The first independent subagent review did not approve publication. It found
forged Fight permissions/Surge restore policy drift, a floating-endpoint proof
domain mismatch, five duplicated placement collision predicates plus Fall Back
crossing, and a Consolidation counterfactual that abandoned the closest selected
enemy. All four received shared fixes and regression coverage. The second independent
review approved the implementation after 14 targeted tests. Final artifact review
also approved source, contract and performance evidence. The final geometry-import
ownership correction received independent approval without new findings.

## Final local validation

The final runtime `04db14ae5849986ba82f63ebaea65aa5f34c46b0e5ee347a9c7e38abb9a6d4db` passed:

- Complete behavioral suite: **9,284 passed**, **85.21% coverage**, with the required Node path and xdist work stealing. Ten existing SQLite ResourceWarnings were reported, not suppressed.
- Complete code-quality suite afterward without coverage: **676 passed**.
- Ruff check and formatting, mypy, Pyright, all import contracts and pre-commit.
- Eight shard manifests regenerated from the successful full JUnit profile; the exact fail-closed inventory check passed.
- Engine identity, source package generation, external contract generation against the verified PR base, and installed-wheel smoke.
- Generated TypeScript client/type checks, unit tests and HTTP conformance scenarios.

[Machine-readable validation](performance/order85/validation.json) retains exact commands,
exit codes, durations and log hashes, plus superseded failed checks and their fixes.
After aggregate validation, a test-only compound assertion was split for Ruff;
the affected regression passed again, with no production change.
All runtime-pinned diagnostics were refreshed serially against the final build;
inherited baselines and budgets are unchanged. These local checks do not claim
remote CI success or full-game performance certification.
