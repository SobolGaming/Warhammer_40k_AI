# Order120 / P22C / C22-03: Psychic ability damage

## Source and bounded scope

The immutable Order97 selection `rule:22:22.03:1`, block1, classifies every
wound caused by an explicitly Psychic ability as inflicted by a Psychic attack.
The retained official July22 Chaos Daemons faction pack, version1.1, supplies
a real example on PDF page48: The Blue Scribes' Xirat'p's Sorcerous Barrages
(Psychic), which causes mortal wounds at the end of the Movement phase.
Its exact operative text, PDF hash, approved manifest URL and Core selection
are retained in [the source audit](../data/source_audits/order120/source.audit.json).
The matched-play cover and contents establish that page48 is in the Index;
Legends begins at page132. An initial Legends candidate was rejected.

This is conditional Core permission evidence, not F00 faction admission.
No source observation or authority registry is extended. Named Blue Scribes
range, timing, dice, target discovery and activation remain deferred/load-only.
The additional-attack fixture is an independent provider-authorized Core outcome:
the official example does not grant additional successful-wound mortals.
The older Cabal probe's unqualified named Psychic title remains unresolved;
this order does not certify its named failure or enable that faction scaffold.

## Shared implementation

`AbilityDamageSource` binds the stable source rule ID, normalized text hash and
structured damage classification. Its data-boundary constructor reads only an
explicit Psychic title tag from already normalized `RuleSourceText`; a Psychic
word elsewhere does not confer classification. Runtime consumers inspect the
descriptor, never names or rule text. Providers retain activation authority.

The existing phase/turn/bearer-bound additional-mortal permission can carry this
descriptor. Deferred outcomes snapshot it alongside originating attack and
weapon provenance. The shared mortal allocation and Feel No Pain owners carry
the same context through preview, allocation, pending choice and restoration.
Psychic ability classification is additive to Psychic weapon classification:
the existing same-attack rule for additional mortals remains intact.

Nonattack direct ability damage uses the same typed context. The direct owner
now forwards both source context and destruction evidence into preflight and
allocation instead of dropping them. Optional or competing protection still
requires lifecycle routing and rejects before mutation. Malformed supplied
classification rejects eagerly even when there are no prevention sources.
Existing recipient priority, attached physical groups, dice, spill/no-spill,
permission expiry and source lifetimes retain their current owners.

## Acceptance and validation

Canonical Shooting/Fight facade regressions complete ordinary damage and deferred
ability mortals, accept/decline Psychic-only protection, reject invalid options
before queue mutation, persist pending choices, fork independently, inspect both
viewer projections/event streams, and reproduce exact replay. Controls cover
ordinary ability damage and an ordinary grant on a Psychic weapon. Genuine
nonattack ABILITY direct outcomes cover mandatory prevention and optional-choice
rejection. Existing Order116-118 tests retain native Psychic weapons, attached
ownership, lethal continuation and lifetime/expiry controls.

Source pins, original Order97 evidence and historical reports remain unchanged.
No behavioral test files are reorganized. Final delivery requires the complete
covered inventory (16 serial polygon cases plus all remaining parallel cases
with appended branch coverage at least85%), full quality after quiet current
runtime smoke, types, lint, imports, shards, generated contracts, package and
TypeScript checks, two distinct exact-head CLEAN reviews, hosted CI and protected
merge. Counts and exact identities are recorded after execution. This is an
ordinary rule branch, with no deliberate performance change or full-game claim.
