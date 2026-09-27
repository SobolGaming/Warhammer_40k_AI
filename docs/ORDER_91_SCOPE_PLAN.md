# Order 91 / P04C — shooting selection without attacks

Violated invariant: unit/type selection is independent of the existence of a legal
weapon/target declaration. A selected unit with no model attacks has not shot;
the selected shooting type still completes and applies its restrictions.

## Sources and scope

This implements C04-04 from the retained Order 84 audit: Core 04.01.01, 04.03.04,
10.02 and 10.04, plus FAQ `9bfa47ed-be8d-4e11-80de-f3832d507ca1`.
The September 24 evidence, provider observation identities and official historical
provenance remain in `data/source_audits/order84/audit.json` and the linked
[observation notes](ORDER_84_AUDIT_NOTES.md). The existing source packages
`core_actions_2026_09`, `core_indirect_shooting_2026_09` and core Stratagems retain
the four ordinary shooting types and Snap Shooting restrictions. No source package
is replaced or newly claimed as current official App evidence.

The same-class search covered ordinary eligibility, random Range selection,
selected-unit hooks/grants, observer eligibility, out-of-phase and retained shooting,
Firing Deck, attack participation, hidden status and Action restriction restoration.
Explicit attack-capability queries used by target-specific reactions still require
a legal declaration. Normal, Assault, Close-quarters and Indirect type eligibility
uses unit conditions and living/retained models’ effect-aware equipped weapons;
spent One Shot weapons cannot produce
attacks but still meet the type's weapon-possession condition.

## Owning path

The engine enumerates the existing finite unit and type decisions. Selected-unit
hooks and random Range evaluation run at their existing boundary. The declaration
owner evaluates the selected type's weapon/target candidates. When no legal candidate
exists, one shared `shooting_without_attacks` owner completes that selection without
creating a proposal or an attack sequence. Ordinary selection remains consumed,
while the phase continues to the next unit or its existing completion option.

The terminal records the accepted unit/type identities, actual turn and phase,
canonical rules unit, optional out-of-phase host and Firing Deck cargo snapshot.
It applies the existing phase-end Action restriction and turn-end cargo restriction.
It does not create shot-unit membership, ranged/model participation, One Shot use,
hidden-status loss, after-shot triggers, target reactions or attack dice. Retained
models finish the existing once-only cleanup and resume their parent host.

Restore binds terminals to accepted decisions, the historical phase clock and
out-of-phase hosts. Host starts require an already accepted source selection, and
terminal games preserve the lifecycle producer’s paired-null phase/turn boundary.
Validation rejects missing/duplicate or mismatched terminals, authenticates
restriction inventories, and rejects ordinary selection state claiming an attack
or a skipped unit. Historical Action checkpoints reconstruct the same restrictions.
Cargo drift at the pending type decision rejects before queue pop or mutation.

## Adapter and validation

The existing finite decision envelopes and nonempty attack proposal contract remain
in force. The type request adds a cargo snapshot and the terminal adds a public,
JSON-safe event; Contract 40's opaque payload schemas cover these additions.
[The adapter contract](ADAPTER_DECISION_CONTRACT.md#order-91-shooting-without-attacks)
documents their semantics. Runtime identity remains exact; no compatibility shim
or alternate UI/headless/network mutation path is introduced.

Regressions cover unarmed/out-of-range ordinary and attached units, all four types,
spent One Shot weapons, source-loaded selected-unit grants, retained cleanup,
Firing Deck cargo drift, invalid restore, both viewers, persistence and exact replay.
The static audit forbids target-candidate gates on selection and attack participation
mutation in the empty-completion owner. Performance and final gates are recorded
in [the delivery evidence](performance/order91/README.md).
