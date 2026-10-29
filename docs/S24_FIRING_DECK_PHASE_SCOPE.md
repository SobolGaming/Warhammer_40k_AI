# S24: Firing Deck phase authority

The invariant is that borrowed Firing Deck weapons exist only in the carrier's
own ordinary Shooting phase. A public shooting request must offer lawful weapon
choices, and a direct invalid cargo declaration must return typed invalid before
queue pop or gameplay mutation, leaving the carrier's own legal attack available.

The original October 14 full-start probe was reproduced against accepted D11
source f38a60cc4c8fde32ad367c394297cfb0cf1b3188b49ea7bb4b2a485f8aae7df7.
Actual Core Overwatch advertised two cargo weapons and submitting one raised
`Firing Deck validation requires shooting_phase_state`. This establishes an
illegal public offer and escaping prevalidation exception, not a completed illegal
shot or a permanently lost session.

Authority is the retained adopted Core capture
`data/source_audits/v963_shock/captures/core-page.js`, SHA256
8b7e7a4004f8a55b17305013f181bf25933dff763e6737af407da254c5656026.
24.14 explicitly says "In your Shooting phase"; 07.02.01 prohibits using other
phase-locked rules through an out-of-phase action. FAQ
7ac6c358-0263-49ff-aee7-28b8fd4b5b8b retains carrier ownership of the borrowed
weapons. The original capture's stale Overwatch explanatory example does not
override the retained operative Stratagem source. The source observation is a
project-adopted mirror, not a newly fetched or co-version certified official source.

The shared `shooting_firing_deck` owner now checks current phase, controlling
player and absence of an out-of-phase shooting context. Inventory, public cargo
snapshot and direct selection validation use the same predicate. A forbidden
selection returns `firing_deck_out_of_phase` before ordinary Shooting state is
required. The carrier's own inventory and Overwatch selection stay available.
No schema, option family, adapter contract shape or persistence format changes;
the existing parameterized declaration contract and typed invalid retry apply.
The descriptor's numeric Firing Deck value may remain metadata in a reaction;
it grants no cargo choices or ordinary shot-history authority.

Bug-class tracing included ordinary/unit/rules-unit weapon inventories, public
request producers, both declaration consumers, cargo restriction effects and
pending restore. Existing explicit One Shot exclusion, physical copy/profile
identity, model selection and capacity validation remain unchanged. No named
handler, catalog provider, faction implementation or exception fallback is added.

Section24 `test_facade.py` adds native-source selected-sheet regressions for
ordinary end-Movement Core Overwatch discovery, public weapon lists and both
viewers, schema-valid cargo and selection-only invalid proposals, complete
lifecycle/queue atomicity, pending authoritative state round-trip, legal carrier
attack completion, own-phase Firing Deck success, over-capacity rejection,
physical borrowed identities, One Shot exclusion and the owner/phase/reaction
boundaries. `tests/support/s24_firing_deck.py` builds fresh mutable states from
the existing session-scoped immutable selected catalog, whose hash is checked.
No existing test or unique assertion is removed. The behavioral file inventory
is unchanged, so no twelve-shard redistribution is needed.

Admission is deliberately bounded. The ordinary Trukk/Boyz provider probe failed
because retained representative model heights are unavailable. The regression
uses admitted Wave Serpent, Infractor and Lord definitions through the ordinary
selected source loader, with explicit constructed Firing Deck 2, cargo/capacity,
resource and custom battlefield checkpoints. These are Core consumer premises,
not the Wave Serpent's printed ability or strict mixed-faction roster admission.
A separate adaptation of the original constructed Core full-start scenario
verifies pending session restore/fork and completed carrier Overwatch with exact
replay. This avoids attributing invented roster/setup authority to the native
boundary kernel. Initial harness/mission/roster checkpoint failures are retained
in the author evidence and not called engine regressions.

S24 is delivered for fresh independent review. The accepted eleven dependency
failures are preserved and authenticated separately. Full behavioral coverage at
85%, aggregate quality, hosted CI under ten minutes, full-game performance and
publication gates remain open. A32 is outside this repair.
