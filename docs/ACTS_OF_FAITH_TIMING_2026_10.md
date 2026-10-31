# Acts of Faith automatic-gain timing

This bounded maintenance corrects the existing supported Sororitas army consumer.
It does not add a faction, datasheet, detachment or layout, or certify a fieldable
Sororitas roster. The violated invariant is that the automatic Miracle-die gain
must run at the start of both players' turns, once per turn, rather than once per
battle round.

## Selected source

The current [Acts of Faith page](https://www.40k.app/factions/adepta-sororitas/army-rules)
was freshly read in the ordinary in-app browser on 31 October 2026. Its selected
timing clause is: "At the start of each turn." Army-faction eligibility and the
separate destroyed-unit gain remain separate obligations. The user's maintained
App-mirror preference controls over conflicting PDFs; 40k.app is not a GW-owned
site. Existing F00 retained observations independently record turn-start timing.

The [update index](https://www.40k.app/factions/updates) lists global v995
(16 October, Genestealer Cults only) and Sororitas' latest listed faction delta
as v981 (14 October, 11 units/11 changes). The current faction updates page reports
no changes between its selected versions. This index context does not date the
individual timing clause. No raw HTML/JSON response hash or complete-faction
source certificate is claimed. The
[bounded observation](../data/source_audits/supported_rules_2026_10/acts-of-faith-timing.json)
hashes the selected transcription and its locator; it is not a complete operative
source package or a relabelled historical observation. Web retrieval returned 403;
the ordinary browser read succeeded without a login or access bypass.

## Owning path and preservation

The existing army owner is
`engine/faction_content/warhammer_40000_11th/adepta_sororitas/army_rule.py`.
The correction uses the shared engine turn-start timing authority and its normal
runtime contribution loading. Automatic gains retain source-linked deterministic
events and resource records. Per-turn identity includes the active player and
battle round so the opposing turn earns its own die and repeated processing does
not earn another.

The same module also owns Triumph's Relics of the Matriarchs selection. That
separate battle-round hook stays at battle-round start. The separate destruction
occurrence source and duplicate accounting,
Miracle-die D6 generation, per-unit per-phase use, allowed substitutions and
eligibility retain their existing scope. The existing adapter decision contract
applies; no new player-facing decision family or payload shape is intended.

Native admitted regressions must cover both players' turns, the initial battle
boundary, later round transitions, repeated processing, preservation controls,
restoration and exact replay. Analytical canonical fixtures establish those
consumer invariants and do not certify an official complete roster.

## Qualification boundary

The ten admitted native runtime controls pass, including both-turn and
last-model-death restore/replay. The targeted registry, preservation and isolated
scratch controls pass 118 active cases with 30 existing historical deferrals. Full
local/hosted qualification and final-head reviews remain pending at this
documentation checkpoint. Required gates retain full-package branch
coverage 64%, the 260 exact deferrals, 720-second behavioral shards, 570-second
quality supervisors and 180-second serial performance cap. Detailed comparisons,
if selected by the exact-base operation assessment, require their own fresh
measurements and complete evidence; historical passes are not current passes.
Both independent final-head reviews and normal protected hosted CI must pass
before merge. No GitHub approval review or protection bypass is authorized.

The wider audit remains incomplete: 48 native profiles' wider comparison and 86
later clauses remain unverified. The five existing Defiler comparisons are a
separate next task. No full-game performance or global rules-currency claim follows.

## Last-model destruction eligibility

Paired native-owner probes on clean base `2490faab` and the timing-only candidate
reproduced a second defect. After a canonical analytical Sororitas unit loses its
last model, `UnitInstance.faction_keywords` is empty because that view enumerates
living models. The destruction provider consequently rejected the destroyed unit
and granted no Miracle die, despite its physical model retaining the canonical
`ADEPTA SORORITAS` keyword. The paired before/after state digests matched.

The separately approved destruction-only correction reads the physical models'
retained canonical keyword assignments in one shared predicate used by both
candidate discovery and application. It does not change the ordinary live-unit
predicate or spending eligibility. Native death controls retain the real
destruction owner; no direct resource grant replaces the death path. Noneligible
casualties, repeated occurrences, last-model death, later turn gains and
restore/replay require explicit regression evidence.

This remains existing consumer maintenance. Canonical analytical fixtures
demonstrate the corrected ownership path, rather than an official complete
Sororitas roster or full-game qualification. Full local and hosted gates remain
pending until their actual final-head results are recorded.
