# Current rules semantics and support limits

The engine consumes versioned structured source packages. This guide records
interpretations that adapters and maintainers need; it does not replace the
[source policy](CORE_RULES_SOURCE_POLICY.md), retained source evidence, or
[decision contract](ADAPTER_DECISION_CONTRACT.md). No whole-game compliance or
performance certification follows from merged fixes or passing component tests.

## Consolidation and disembark

Only Engaging Consolidation grants forced enemy Fight selection. Ongoing
Consolidation preserves each model's prior enemy-unit engagements. Objective
Consolidation ends unengaged and in range of the selected objective. The
owner-confirmed official App v946 (2026-09-21) interpretation supersedes only the
older v931 Ongoing forced-selection clause. It was an owner-supplied transcription,
not an agent-observed capture; no missing device, locale or capture metadata is
inferred. The typed resolution and original observations remain in
`src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/core_fight_2026_09/`.
The resolution timestamp records the repository decision, not when the owner
observed the App. Historical v931 Ongoing evidence stays `not_certified` with no
current runtime consumers; no co-version equivalence is inferred.

Shock Disembark uses ordinary coherent, unengaged setup and prohibits charging
through turn end. It creates no Shock-generated enemy Fight queue. The source
exception was resolved by the repository owner on 2026-09-19 for the older rules;
that engaged-setup interpretation is superseded by the current retained 18.07
observation. It must not be reapplied to current games or used to rewrite old
replays. Atomic proposal validation, retry and engine-owned continuation still
apply. Other disembark types retain their separate source permissions.

Embark requires every living model of the rules unit to be within an inclusive
actual three inches of a Transport model in full 3D, using support bases or complete
recorded FRAME parts. Ordinary embark uses its actual movement action;
source-authorized no-movement embark uses its explicit source occasion. Tactical/Emergency placement respects complete unit
geometry and engine-owned feasibility. Movement witnesses must identify the
canonical physical model inventory before mutation; an invalid inventory leaves
the pending decision available for a corrected retry.

Mixed random Movement uses an owner-approved provisional interpretation: fixed
values stay fixed, models sharing one expression share one roll, and different
expressions roll independently without reusing component dice. These are maximum
allowances; coherency still applies. This is not additional official or mirror
wording. Equal unresolved BS/WS/Strength/AP expressions may gather, while each
physical occurrence retains its own evaluation; no early roll or guessed scalar
is introduced by grouping.

Objective control requires player control, any present rules-unit member in range,
and any present rules-unit member with positive OC. The positive-OC member need
not itself be in range; only in-range members contribute to the score. Terrain
Objectives use rules-area membership without an arbitrary marker height cap.
For body-measured markers, one physical point must satisfy both axis limits.
That same-point rule is a human convention, not invented official wording;
scalar closest distance and the membership witness remain separate.

## Attacks and player choices

Selecting a unit, selecting weapons, selecting targets and making attacks are
separate facts. Empty ranged declarations and selected weapons with null targets
retain their explicit selection consequences. A physical ranged weapon cannot
fire multiple alternate profiles in one declaration. One Shot is a physical-copy
budget shared across its profiles and retained when a model returns.

The provisional random-melee convention is
`core-rules-owner-convention:order92:random-melee-pretarget:2026-09-27`.
Commit physical weapons/profiles, generate each random A once, then choose targets
and exact per-target splits. Every selected target receives at least one attack;
the split conserves that weapon's total. Retries preserve committed choices and
rolls. Cleave additions cannot be distributed across split targets. This is an
owner-approved engine convention resolving conflicting source timing, not an
official FAQ; Shooting timing is unchanged.

Original Hit, Wound and Save rolls are gathered at their respective steps before
reroll choices. Optional intrinsic and source-granted rerolls use recorded player
decisions. Raw physical dice, assigned values and modifier operations retain
separate identities. Effective Save values such as 7 and 8 remain valid; a D6
face bound must not cap the Save characteristic. Attached rules-unit identity
governs targeting, ability lifetime, CHARACTER selection and casualty choices,
while physical model ownership remains explicit.

## Source and faction boundaries

Current catalog descriptions must agree with their selected source; old global
paragraphs are not authority for current Stealth, Infiltrators, Scouts, Lone
Operative, Fights First or Deadly Demise. Current numeric/profile corrections and
keyword overlays require exact source identities and preimages. They do not admit
additional units, geometry, factions or rule branches by implication.

Ordinary Daemons do not receive unconditional SHADOW LEGION merely because a
detachment can grant it during mustering. The supported Aeldari corrections retain
source-owned loadouts, conditional saves and captured charge-completion timing.
Acts of Faith's automatic gain uses both players' turn starts; Triumph retains its
separate round selection. Blessings and Icon consumers use canonical attached
rules units and structured phase ownership. The current MFM package is separately
versioned v1.6; current points do not certify complete current faction semantics.

The reviewed after-prior-movement reposition seam requires a separately issued
source permission and the prior move in the same actual opponent Movement phase.
Prior movement is not a universal prerequisite for other source reposition rules. Shadow
of Anarch's move and reserves branches cannot combine. Its user transcription is
not fetched faction authority, and named activation/CP/eligibility remain load-only.
Starfang's Deep Strike source package is loaded but `not_certified`; Wave Serpent
real-hull geometry and Daemons detachment/facade admission are not certified by
their source corrections. Global App data version 995 is not a per-unit observation
date or build. Maintained-mirror evidence retains its
`project_authoritative_app_mirror` qualification.

## Persistence, evidence and remaining work

Ordinary save/load and replay require their producing runtime and source identity.
Missing history, physical-copy IDs, target context or geometry is never inferred
from a newer build. The explicitly authorized retained-checkpoint reconstruction
tool is a separate operator operation described in
[its guide](A32_HISTORICAL_CHECKPOINT_RECONSTRUCTION.md); it is not a load fallback.

Source admission, load support, semantic execution, fieldability, playability and
replay verification are separate claims. The [Core requirements inventory](CORE_RULES_REMEDIATION_ROADMAP.md)
and [faction roadmap](FACTION_RULES_REMEDIATION_ROADMAP.md) retain their acceptance
gates. `CAUDIT-01` and `PFINAL` remain open until fresh clause/FAQ evidence maps
the selected source to engine owners and facade regressions. Deferred integrity
hardening and unproved complete-game performance remain separate work under the
[review policy](SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md).
