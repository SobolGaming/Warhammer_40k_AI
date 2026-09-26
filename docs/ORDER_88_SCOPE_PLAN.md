# Order 88 / P02G — weapons with no Strength

Violated invariant: a legal source-dash Strength must resolve as one whenever a
rule interacts with Strength, while its immutable dash descriptor remains
unmodifiable. A real Shooting facade regression reproduced the original failure
in `WoundRollModifierContext` before production changes.

## Source authority

Core 02.04.01 is the controlling clause. The Game Datamissions page asset
`https://game-datamissions.com/_next/static/chunks/app/11th/rules/core-rules/page-ec6350d45d9ddeb5.js`
was retrieved on September 26 and verified against the retained Order 84 SHA-256
`6f4d27c5670489e9b6310bb8f43e837d8abaf2d5f7a8c8938f56690190edad0e`.
The source row `rule:02:02.04.01:1` retains fingerprint
`e266bdad60564967e9ac444d60ee6fe4045c54b892f44cf9ef359ed0f5e38834`
and its text block retains
`13a157af75b900b0b90c29f80a20e4424c8728680cd82138e5f3111194049a45`.
Only formatting control characters around the S abbreviation were removed from
the reviewed transcription. The exact observation timestamp and transcription
hash are recorded in the existing Core modifiers source artifact and audit.

The registered source ID is `gw-11e-core-modifiers:weapons-with-no-strength`.
The existing typed, hash-pinned loader and authority registry authenticate this
additional row; prior observation tuples and the official historical PDF hash
remain unchanged. Game Datamissions is a project-authoritative maintained App-data
mirror under the repository policy, not an official GW source. No App build,
co-version agreement, or new official corroboration is inferred. The historical
negative Order 84 audit remains unchanged. Reproduce the artifacts offline with
`uv run python tools/build_core_modifiers_source.py --check`.

## Ownership and scope audit

Source/catalog loading already preserves Strength as a typed characteristic.
`WeaponProfile.strength_for_interaction()` owns its interpretation: numeric and
evaluated random Strength retain their values; source and replacement dash yield
one without changing any profile field. Unresolved random values, numeric zero,
and unsupported special values remain explicit errors. No missing descriptor is
silently manufactured.

The bug-class search found exactly three direct Strength reads in engine consumers:
the wound table input, `WoundRollModifierContext` for generic and registered
Strength/Toughness comparisons, and Twin-linked wound reroll reconstruction.
All now use the same query. Shooting, Fight and reaction attacks share these
owners. Generic, catalog and faction comparisons consume that context rather
than reading a profile sentinel. Attack grouping/identity still compares the
structured descriptor. Existing modifier APIs still reject source-dash mutation.

No new decision, option, proposal, event shape, visibility rule, hook family or
named handler is needed. Contract 40 already represents the immutable dash
descriptor and positive integer WoundRoll interaction value. The engine identity
and generated external examples must be refreshed; no contract version bump or
compatibility shim is appropriate. The adapter contract documents this existing
shape explicitly.

## Acceptance

The focused regressions cover dash/numeric/random queries, positive wound-table
inputs against T1/T2/T10, immutable serialized descriptors, modifier rejection,
ordinary Shooting and Fight, a conditional generic S>T wound modifier with a
numeric positive control, Twin-linked, JSON persistence, both viewer projections
and event streams, and exact replay. A static AST audit rejects direct
`.strength.raw/base/final` engine reads and protects all three consumer calls.

Matched performance evidence and final validation results are recorded in
[the performance record](performance/order88/README.md). Core Rules certification
and complete-game performance remain separate, outstanding gates.

## Adjacent observation

Combining Command Re-roll with Twin-linked can reach the existing attempt to
reroll an already-rerolled wound die after a failed Command Re-roll. The unchanged
Twin-linked owner does not test prior reroll history before requesting another
reroll. This is a separate reroll-eligibility invariant, not a Strength
interpretation defect; no reroll eligibility code is changed here. The independent
review confirmed this scope separation. Order 88 separately tests Twin-linked
with absent Strength and paused Command Re-roll/restore with Twin-linked disabled.
This observation remains a follow-up and is not claimed resolved by Order 88.
