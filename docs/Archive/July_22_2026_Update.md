# July 22, 2026 Faction Pack Update Plan

## Purpose

This document records the first-page review of every Faction Pack PDF in
`data/raw/faction_packs/` whose filename starts with `eng_22-07_`. It identifies
which `What's New?` entries affect current CORE V2 source coverage or executable
runtime support and orders the required follow-up work into reviewable pull
requests.

This is a planning artifact only. It does not change source-package identities,
generated catalogs, support claims, or runtime behavior.

## Review rules

- The review covers physical PDF page 1 of all 27 matching files.
- A generic `Changes to Rules Updates` or `New entries in Rules Updates` notice
  is informational here. Those changes were handled by the preceding rules-update
  work and do not create another task in this plan.
- Forge World, Imperial Armour, Legends, Warhammer Legends, Boarding Actions,
  Crusade, and Kill Team content remains outside CORE V2 scope under `AGENTS.md`.
  A first-page item in one of those categories is recorded as excluded, not queued
  for ingestion.
- A source-only or blocked row still needs its source text, provenance, and
  support status updated so later work cannot implement obsolete wording. It does
  not become executable merely because its source row is refreshed.
- Runtime work is required only where the project currently executes at least
  part of the changed rule. New runtime support for previously blocked content is
  not part of this update program.
- Raw extracted PDF text and rendered page images are review intermediates and
  must not be committed. The existing redistribution-policy tests continue to
  govern committed official-source artifacts.

## Result

- 27 of 27 matching PDFs were reviewed.
- 14 packs contain at least one in-scope named change that requires a source,
  catalog, support-report, or runtime update.
- 13 packs contain only an already-handled Rules Updates notice, or that notice
  plus an out-of-scope Imperial Armour change.
- Three factions have changes to currently executable runtime behavior:
  Chaos Daemons, Emperor's Children, and Thousand Sons.
- Two detachments are new to the combined Faction Packs and are not in the
  current Phase 17 source package: Orks `Equatorial Hordes` and Space Marines
  `Vengeful Hosts`.
- The July PDFs are currently pending source evidence in
  `data/source_manifests/gw_11e_pending_faction_packs_2026_07.yaml`. Generated
  faction support documents and the Phase 17E/17F packages remain pinned to the
  June source package and must remain pinned through PR 7, so a controlled source
  cutover is required after the affected rows have been migrated.
- Deathwatch has no July 22 successor PDF. Its June package remains current
  source evidence throughout this progression and after the July cutover; the
  final current-source set is 27 July packages plus the June Deathwatch package.

## Packs with in-scope changes

The support classifications below are based on the committed generated faction
documents, Phase 17E/17F source packages, and focused runtime tests on `main`.
`Source/load only` means no changed semantic is currently executable.

| Faction pack | First-page finding | Current project impact | Required disposition |
| --- | --- | --- | --- |
| [Adepta Sororitas](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_adepta_sororitas-kbko8lsd8p-ptxieipyp8.pdf) | `Hagiomnifex` is restricted to an Adepta Sororitas Character that is not Penitent. | Source/load only. Sanctified Orators is scaffolded with no semantic detachment support, and this July Enhancement wording is not executable. | Refresh the exact Enhancement row and its eligibility metadata; keep execution blocked. |
| [Adeptus Mechanicus](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_adeptus_mechanicus-d1ubc1apog-mpt3r8xzy4.pdf) | Thulia Ghuld gains `MOBILE` and loses `Cybernetic Augmentation`. | Source review only. Thulia Ghuld is classified as a complete-PDF datasheet, but the generated support report says there are no catalog datasheets for the faction. | Update the datasheet review/overlay and keyword/ability source rows without adding a runtime support claim. |
| [Blood Angels](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_blood_angels-l1ttsuicte-4xq8nrzqy1.pdf) | `Ordained Sacrifice` now has a once-per-battle, per-army 2+ single-model return with three wounds. | Source/load only. Angelic Inheritors and this Enhancement have no executable semantic support. | Refresh the exact Enhancement text and unsupported diagnostics; do not implement revival as part of this update. |
| [Chaos Daemons](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_chaos_daemons-lycqqrymwe-qogh4b5yly.pdf) | Changes affect `Daemonic Manifestation`, `The Realm of Chaos`, `Foetid Resurgence`, `Thieves of Pain`, `Infernal Puppeteer`, Kairos Fateweaver, Screamers, and Fluxmaster. | Mixed. `Daemonic Manifestation`, `The Realm of Chaos`, Kairos's Stratagem-cost modifier, and part of Fluxmaster's current ability are executable. The three named Plague Legion/Legion of Excess/Scintillating Legion rules are source-only. Screamers is partially supported and its `FRAME` keyword is catalog data. | Split source-only row refreshes from two focused Chaos Daemons runtime PRs; details are below. |
| [Chaos Space Marines](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_chaos_space_marines-att4ehoaum-8mmiunajyf.pdf) | `Empyric Wellspring`, `Sorrowscent Vulture`, and the Defiler's `Daemonforge` ability change. | Source/load only. Cabal of Chaos and Nightmare Hunt are scaffolded, `Sorrowscent Vulture` is explicitly source-only, and the generated report has no Chaos Space Marines catalog datasheets. | Refresh the detachment-rule, Enhancement, and Defiler source/review rows; preserve blocked execution. |
| [Emperor's Children](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_emperor_s_children-srspmclqtm-i8ey7hgk2s.pdf) | The `Host` tag is removed from Frenzied Host; `Exalted Patron` is reduced to the Lord Exultant restriction and +1" Move. | Mixed. Frenzied Host is source-only. Court of the Phoenician and all four Enhancements are executable; the current `Exalted Patron` RuleIR also grants attachment to Flawless Blades, which the July text removes. | Refresh Frenzied Host metadata as source-only, then update the executable `Exalted Patron` RuleIR and remove the stale attachment grant. |
| [Grey Knights](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_grey_knights-dlzvusufhy-uialb3pko4.pdf) | `Echojump` now prevents Personal Teleporters and grants a D6+1" surge move after an Interceptor Squad shoots. | Source/load only. Immaterial Interdiction has no semantic detachment hook. The Thunderhawk `FRAME` removal is Imperial Armour and excluded. | Refresh the detachment-rule row and keep the movement semantics explicitly blocked. |
| [Imperial Knights](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_imperia_knights-0at8boavnz-vxe5grd7zi.pdf) | `Mysterious Guardian` now moves an unengaged unit to Strategic Reserves, grants temporary Deep Strike, and requires an ingress move in the next Movement phase. | Source/load only. The Enhancement is explicitly source-only with no runtime consumers. | Refresh the exact Enhancement row and keep execution blocked. |
| [Necrons](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_necrons-k3e43twijn-hgmq2u3w1j.pdf) | `Murdermind` grants `DESTROYER CULT` and +3" Move; `Reletavistic Tether` changes Transdimensional Displacement spacing and charge eligibility. | Source/load only. Both Enhancement rows are explicitly source-only. | Refresh both exact rows and their movement/keyword diagnostics; do not expand runtime scope. |
| [Orks](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_orks-ggcht2iwrd-x41aivbtcv.pdf) | Adds `Equatorial Hordes`; Wazdakka Gutsmek's `Shokk Attack Engine` moves the unit to Strategic Reserves and permits an ingress move next Movement phase. | Source/load only. Equatorial Hordes is absent from the Phase 17 detachment package. Wazdakka is a complete-PDF source-review row, but the generated report has no Orks catalog datasheets. | Add complete source/load coverage for the detachment and refresh Wazdakka's datasheet row without claiming execution. |
| [Space Marines](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_space_marines-631fzvmfjm-2qfrbosgdj.pdf) | Adds `Vengeful Hosts`; updates `Evasive Manoeuvres`, `Fusillade`, and `Temporal Corridor`. | Source/load only for all four in-scope items. Vengeful Hosts is absent from the Phase 17 detachment package; the existing Stratagem and Enhancement rows have no runtime consumers. The Thunderhawk keyword change is Imperial Armour and excluded. | Add complete source/load coverage for Vengeful Hosts and refresh the three exact subrule rows while keeping them blocked. |
| [Thousand Sons](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_thousand_sons-h1ysumgym3-kyfwf7cjpt.pdf) | The Defiler loses Feel No Pain 6+ and `Destroyer of Futures` becomes a Counteroffensive cost/use exception; `Eruption of Vitality` and `Kaleidoscopic Tempest` also change. | Mixed. The Defiler's Feel No Pain and current `Destroyer of Futures` minimum-hit-threshold RuleIR are engine-consumed. The Enhancement and Stratagem are source-only. | Refresh the two source-only rows separately, then replace the executable Defiler descriptors and behavior in a focused runtime PR. |
| [Astra Militarum](data/raw/faction_packs/eng_22-07_warhammer_40000_faction_pack_astra_militarum-y4301esy7a-bsy7fkb1gw.pdf) | `On My Signal` and Commissar Yarrick's `Counterstrategist` change 9" to 8"; Tempestus Aquilons and Ratlings are removed. | Source/load only. Armoured Infantry has no semantic hook, and the generated report has no Astra Militarum catalog datasheets, but all three datasheets are currently represented in the complete-PDF source review. | Refresh the rule and datasheet rows and remove Aquilons/Ratlings from the current matched-play Faction Pack inventory while retaining historical provenance. Ciaphas Cain is Legends and excluded. |
| [Tyranids](data/raw/faction_packs/eng_22-07_warhammer_40000_faction_pack_tyranids-rz5ydhbpyi-a1yqdtcqcm.pdf) | The Red Terror loses `Serpentine Fiend` and gains `MOBILE`. | Source review only. The Red Terror is a complete-PDF datasheet row, but the generated report says there are no Tyranids catalog datasheets. | Update its ability/keyword source rows and source review without adding a runtime support claim. |

### Chaos Daemons runtime details

The Chaos Daemons pack has the broadest executable impact:

- `Daemonic Manifestation`: the existing army-rule hook already applies the +1
  Battle-shock modifier and heals one wounded non-Battleline model. It currently
  emits an unsupported result when a Battleline unit has destroyed models. The
  July text requires returning up to D3 destroyed non-Character models, so that
  unsupported branch must become a deterministic revival/placement decision
  through the existing engine decision path.
- `The Realm of Chaos`: the current supported Stratagem sends units to Strategic
  Reserves with a required Deep Strike arrival. The July text instead requires
  an ingress move in the next Movement phase, including in the first turn. The
  existing generic ingress-move and placement-proposal machinery should be reused.
- `Foetid Resurgence`, `Thieves of Pain`, and `Infernal Puppeteer`: their rows
  have no runtime consumers. Update their source text and continue reporting them
  as blocked.
- Kairos Fateweaver's `One Head Looks Back`: the Stratagem-cost modifier is
  currently engine-consumed. Its source-backed range, once-per-turn limit, target,
  and +1 CP behavior must be regenerated and retested.
- Screamers: remove `FRAME` from the current keyword data. No new runtime handler
  is warranted.
- Fluxmaster: remove the stale supported led-unit Hit modifier and replace it
  with self-only Stealth and a melee Hit penalty against the unit. Preserve the
  separate explicit unsupported diagnostic for `Altered Reality`.

### Thousand Sons runtime details

- Remove the Defiler's Feel No Pain descriptor and both lost-wound runtime
  consumers tied to that descriptor.
- Delete the current `minimum_unmodified_hit_success` interpretation of
  `Destroyer of Futures`.
- Model the July ability through source-backed Counteroffensive eligibility and
  cost/restriction semantics: once per phase per unit, -1 CP for that use, and
  that use neither blocked by nor blocking Counteroffensive uses on other units.
- Reuse the existing Counteroffensive decision and mutation path. If option
  payloads or adapter-visible eligibility change, update
  `docs/ADAPTER_DECISION_CONTRACT.md` and its tests in the same PR.
- `Eruption of Vitality` and `Kaleidoscopic Tempest` remain source-only. In
  particular, the new -3 detection-range effect must remain explicitly blocked
  until a real executable consumer can use a typed generic semantic; the current
  detection-range effect path only proves positive bonuses.

## Packs with no in-scope semantic change

These packs still participate in the eventual July source-provenance cutover,
but their first pages create no additional code or runtime task.

| Faction pack | First-page disposition |
| --- | --- |
| [Adeptus Custodes](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_adeptus_custodes-9ddgakd3ms-3azheaqd6y.pdf) | Ignore the Rules Updates notice. Ares Gunship and Orion Assault Dropship changes are Imperial Armour and excluded. |
| [Aeldari](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_aeldari-qe1ykopo7h-blfkukhecc.pdf) | Rules Updates notice only; no new task. |
| [Black Templars](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_black_templars-inz7wljsdy-badlygdtjm.pdf) | Rules Updates notice only; no new task. |
| [Chaos Knights](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_chaos_knights-mdwarnukhh-irpnxydqyr.pdf) | Rules Updates notice only; no new task. |
| [Dark Angels](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_dark_angels-vml9eoamc5-muz1tp9qlk.pdf) | Rules Updates notice only; no new task. |
| [Death Guard](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_death_guard-333phejcfc-tvefnstlub.pdf) | Rules Updates notice only; no new task. |
| [Drukhari](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_drukhari-8cbmbcz0ai-0bz2psrjty.pdf) | Rules Updates notice only; no new task. |
| [Genestealer Cults](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_genestealer_cults-vmkwgeydbr-sh7picbeqo.pdf) | Rules Updates notice only; no new task. |
| [Imperial Agents](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_imperia_agents-fttx9vrxuj-jug1nycmjn.pdf) | Rules Updates notice only; no new task. |
| [Leagues of Votann](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_leagues-of-votann-kpfosalfyb-sbqk309w4w.pdf) | Rules Updates notice only; no new task. |
| [Space Wolves](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_space_wolves-vkg7nwp9ez-ldpwen5t8a.pdf) | Rules Updates notice only; no new task. |
| [T'au Empire](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_tau_empire-hdrq4u64wm-xopcvjvqfu.pdf) | Ignore the Rules Updates notice. Tiger Shark changes are Imperial Armour and excluded. |
| [World Eaters](data/raw/faction_packs/eng_22-07_warhammer_40,000_faction_pack_world_eaters-5g8k1b5jg0-3ttsio6riy.pdf) | Rules Updates notice only; no new task. |

## Pull request progression

The order below prevents the active source manifest and generated support reports
from claiming July semantics before the corresponding runtime consumers are
correct.

### Staging and activation invariant

PRs 1-7 must not edit July wording into the active
`faction_detachments_2026_27.py` or `faction_subrules_2026_27.py` packages, change
their June package identities or `SOURCE_DATE = "2026-06-11"`, advance the
active Phase 17E/17F mappings, or regenerate `docs/factions/*.md` from July data.
Those artifacts and their source-row IDs and hashes continue to describe the
active June source boundary until PR 8.

Instead, PR 1 establishes a separate staged July successor package or overlay.
It must have its own July 22, 2026 identity, versioned data artifacts, canonical
hashes, and explicit predecessor links to the active June package and source-row
IDs. PRs 2-7 populate that staged package and may add runtime descriptors or
consumers that are reachable only through an explicitly selected staged provider
or candidate registry. Focused tests must construct that staged bundle
explicitly; the default current-source mapping and default runtime registry must
continue to load June behavior until PR 8 atomically activates the completed
successor.

Deathwatch is not part of the successor overlay because no July Deathwatch pack
exists. Its `gw-11e-deathwatch-faction-pack-2026-06` identity, hash, and binary
path remain in the current-source mapping rather than becoming predecessor-only
provenance.

### PR 1 — July delta ledger and source-cutover guard

Create a versioned, structured delta ledger for all 27 packs, linked to the
pending-manifest package IDs and hashes. Record every first-page item above as
one of:

- `rules_updates_already_applied`;
- `in_scope_source_only`;
- `in_scope_runtime_affected`;
- `excluded_imperial_armour`; or
- `excluded_legends`.

Add a fail-closed audit proving that every pending July pack has exactly one
review row and that every named runtime-affected row maps to an existing stable
source rule, descriptor, or datasheet ID. Create the staged July successor
package/overlay with its own identity, date, hashes, and row-level predecessor
links, but do not promote it to the active semantic source. Add a guard proving
that staged July package or row IDs cannot appear in the default current-source,
Phase 17E/17F, runtime-registry, or generated-current-document mappings before
PR 8. Retain the active June package unchanged while runtime-backed successor
rows are prepared.

### PR 2 — Staged load-only faction, detachment, Enhancement, and Stratagem rows

Populate the staged July successor boundary for changed rows that are not
currently executable:

- Hagiomnifex;
- Ordained Sacrifice;
- Foetid Resurgence, Thieves of Pain, and Infernal Puppeteer;
- Empyric Wellspring and Sorrowscent Vulture;
- the Frenzied Host tag removal;
- Echojump;
- Mysterious Guardian;
- Murdermind and Reletavistic Tether;
- Equatorial Hordes;
- Vengeful Hosts, Evasive Manoeuvres, Fusillade, and Temporal Corridor;
- Eruption of Vitality and Kaleidoscopic Tempest; and
- On My Signal.

Add separate July detachment and subrule data artifacts, staged Phase 17E
coverage rows, staged Phase 17F execution rows, staged runtime scaffolds, and
their own hashes and predecessor links. Do not modify
`faction_detachments_2026_27.py`, `faction_subrules_2026_27.py`, the active Phase
17E/17F packages, their June identities or hashes, or the generated current
faction documents. Any generated review output in this PR must be explicitly
marked as a staged preview and must not be consumed by current-support reporting.

Previously blocked rows must remain blocked unless that same PR supplies
source-backed generic semantics and a real runtime consumer. Do not add named
handlers for these source-only changes.

### PR 3 — Staged load-only datasheet and keyword inventory

Populate staged July datasheet source reviews and overlays for:

- Thulia Ghuld;
- the Chaos Space Marines Defiler;
- Wazdakka Gutsmek;
- Commissar Yarrick;
- removal of Tempestus Aquilons and Ratlings from the current matched-play
  Faction Pack inventory; and
- The Red Terror.

Preserve historical source rows where required for provenance, but do not expose
removed units as current Faction Pack content. Do not ingest Ciaphas Cain or any
Imperial Armour/Legends change. Generate a staged datasheet review manifest and
support-document preview without modifying the active June review manifest or
current support documents, and without upgrading any `Unknown`, `Catalog-only`,
or blocked runtime status.

### PR 4 — Staged Chaos Daemons Daemonic Manifestation

Add the July Chaos Daemons army-rule successor row and implement its Battleline
return branch through typed healing/revival state and deterministic placement
decisions in the staged runtime provider. The active June source mapping and
default runtime registry remain unchanged. Cover:

- the existing +1 Battle-shock modifier;
- a successful non-Battleline roll healing one model by D3;
- a successful Battleline roll returning up to D3 destroyed non-Character
  models;
- no eligible destroyed models;
- multiple legal placement choices;
- stale, malformed, and invalid placement submissions;
- attached-unit and model-group behavior;
- replay/event payload round trips; and
- viewer-scoped decision/event projections.

Update the adapter decision contract in the same PR because the formerly
unsupported branch becomes a player-facing placement choice when the staged
provider is activated. Exercise that choice through an explicitly constructed
staged adapter session until PR 8 makes the provider current.

### PR 5 — Staged Chaos Daemons Realm of Chaos and changed datasheets

Migrate the remaining executable Chaos Daemons deltas into the staged July
provider:

- change `The Realm of Chaos` from required Deep Strike arrival to the existing
  generic ingress-move flow in the next Movement phase, including turn one;
- update Kairos Fateweaver's once-per-turn, 12" Stratagem-cost modifier;
- replace Fluxmaster's stale supported modifier with Stealth and the melee Hit
  penalty while retaining the separate unsupported `Altered Reality` diagnostic;
  and
- remove `FRAME` from Screamers.

Use stable source IDs and generic semantic services. Confirm whether the
existing ingress and Stratagem-cost decision contracts already cover the
resulting payloads; update `docs/ADAPTER_DECISION_CONTRACT.md` if any
adapter-visible option, proposal context, or event shape changes. Prove that the
default June provider still exposes the prior June behavior and that the July
behavior is reachable only when the staged provider is selected explicitly.

### PR 6 — Staged Emperor's Children Exalted Patron

Generate the staged Court of the Phoenician static RuleIR successor for
`Exalted Patron`. Retain the Lord Exultant eligibility gate and +1" Move
modifier, remove the Flawless Blades attachment grant, refresh the staged
hashes/execution records, and add mustering and lifecycle regression coverage
proving the removed permission is not available through the staged provider.
Keep the Frenzied Host rule itself source-only, and prove that the default June
provider remains unchanged until PR 8.

### PR 7 — Staged Thousand Sons Defiler

Atomically add the staged July Defiler source overlay, descriptors, runtime
consumers, and tests:

- remove Feel No Pain 6+;
- remove the old `Destroyer of Futures` minimum-hit-threshold RuleIR;
- add the Counteroffensive -1 CP behavior;
- allow the ability's once-per-phase, per-unit use without blocking uses on
  other eligible units;
- reject repeated use for the same Defiler in the same phase;
- preserve the normal Counteroffensive decision, CP transaction, event, and
  replay paths; and
- update the adapter contract if option availability or payloads change.

Search for the same stale Defiler ability rows across all god-aligned Defiler
overlays so the fix is source-ID-scoped and does not alter Death Guard, World
Eaters, Emperor's Children, or Chaos Space Marines behavior accidentally. Prove
that the active June Thousand Sons provider also remains unchanged until PR 8.

### PR 8 — July source promotion and closeout

After PRs 1-7 are merged and the source-cutover guard passes:

- atomically switch the 27 replaced factions' current-source and default runtime
  mappings from their June packages to the completed staged July successor;
- establish the exact 28-faction current-source set as all 27 July 22 packages
  plus `gw-11e-deathwatch-faction-pack-2026-06`;
- add a fail-closed exact-set assertion that rejects a missing or additional
  current faction, a duplicate faction mapping, any non-July replacement for the
  27 promoted factions, or any Deathwatch mapping other than its June package;
- require the current Deathwatch row to retain the June source identity
  `gw-11e-deathwatch-faction-pack-2026-06`, SHA-256
  `698b7063a71e3f10301aab1498effcb88ad2be41f3f491e24737c2abc9f988ce`,
  and binary path
  `data/raw/faction_packs/eng_08-06_warhammer40000_faction_pack_deathwatch-z0ebavrfze-muhcibnets.pdf`
  until Games Workshop publishes a successor; it remains current source and must
  not be classified as historical-only predecessor evidence;
- retain the replaced June PDFs/package identities as versioned predecessor
  provenance after their July successors become current;
- regenerate source-package hashes, catalogs, coverage/execution records,
  ability-support artifacts, and every `docs/factions/*.md` file;
- prove that the active Phase 17E/17F packages, default runtime registry, and
  generated current-support documents switch together with no partially promoted
  state;
- prove that no executable rule still points at superseded June wording;
- prove that the 13 no-action packs changed provenance only;
- prove that Imperial Armour and Legends rows were not introduced; and
- remove the pending designation only when the generated current-support state
  is internally consistent.

## Required checks

Every implementation PR in this progression must run the repository-required
commands from `AGENTS.md`:

```text
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pyright
uv run pytest -n auto --dist=worksteal tests/
uv run --no-sync python scripts/build_test_shards.py --check --shard-count 4
uv run lint-imports
uv run pre-commit run --all-files
```

In addition, each PR should run the focused source, generated-artifact, faction,
adapter, replay, and runtime tests for the rows it changes before running the
full suite. Any behavioral test-file addition, deletion, move, or rename must
regenerate the committed four-shard inventory before the PR is published.
