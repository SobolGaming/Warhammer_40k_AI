# Aeldari current source correction review

Two current-source corrections are bound to complete 2 November 2026 browser
observations from **40k.app**, the project-authoritative non-affiliated mirror.
This is not Games Workshop publication or full Aeldari gameplay certification.

The retained [F00 v2 audit](../data/source_audits/aeldari_current_2026_11/source.audit.json)
contains the complete army-rules page (all six manoeuvres expanded) and complete
Corsair Voidscarred page. Its packaged copy has an immutable SHA-256 pin. The
authority registry authenticates each exact page identity, owner, timestamp,
fingerprint and the full canonical source catalog including normalization mode.
The [original captures](../data/source_audits/aeldari_current_2026_11/browser-captures.json)
also retain the complete version feed: global 995, released 16 October. This is
an observation snapshot, not a modification date for either corrected clause.

The [exact field review](../data/source_audits/aeldari_current_2026_11/review.json)
records old/new text, field hashes and whole-row preimages. The current overlay
updates `Datasheets/000002532/loadout` and `Abilities/000009894:AE/description`.
It adds the existing close combat weapon to Shade Runner, Soul Weaver and Way
Seeker defaults. Sudden Strike changes from selected-to-fight/end-of-phase to
charge-completion/end-of-turn. Its six-inch effect, other five manoeuvres, base
2/4/6 token amounts, eligibility, phase quotas and round-end loss are preserved.
The existing generic loadout parser already expresses all five model roles.
The same-numbered historical Drukhari ability row is not an Aeldari-owned page
and is unchanged. Three mandatory default weapon entries are restored. No new optional upgrade,
unit, model, geometry or support admission is added.

Source consumption is shared: `aeldari_current_2026_11.source_package()` passes
the ordinary F00 evidence and registry boundary; its two-operation overlay runs
after the historical Aeldari overlays in `load_ability_support_sources`.
The selected-source index hashes the new overlay, packaged audit and registry.
The native catalog and ability support generator consume those composed sources.
Runtime source rule `phase17f:phase17e:aeldari:army-rule` and all existing hook IDs
remain stable; current Sudden Strike links to `faction-app:aeldari:army-rules`.
Faction coverage/execution descriptors carry identities and historical PDF
ancestry, not a second Battle Focus transcription. The only packaged current
transcription copies are generated native datasheets, regenerated from this path.

The July Aeldari PDF is retained and hash-verified as independent historical
primary evidence, explicitly **not current corroboration**. Old snapshots,
overlays, F00 v1 audit/pin and previous captures remain immutable. Older semantic
coverage snapshots retain their own historical scope rather than being relabeled
as current full-page evidence. The full-page F00 package records source loading
separately from semantic execution and does not certify the complete page.

The required source-boundary repair exposes the existing structured-lines
normalizer only through an explicit `RuleSourceText` mode. Flat legacy behavior
and emitted payloads stay unchanged. This keeps AP `0` / damage `D3`, and numeric
cell `2` / dice cell `D6`, separate. The mode round-trips and is part of the source
catalog hash; unknown modes and explicit invalid `0D3` remain rejected. No source
capture is shortened or rewritten and no token-validation bypass is used.

Offline verification: `tools/generate_aeldari_current_source.py --check`, existing
F00 governance checks, and focused source overlay/normalization regressions.
Native construction, melee availability, charge/fight, persistence/replay and
resource/lifetime tests belong to the coordinated runtime correction. Full local
and hosted gates and exact-head independent reviews remain delivery requirements.
