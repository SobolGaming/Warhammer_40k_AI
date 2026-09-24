# Order 84 audit evidence and limits

The requested Order 84 audit evaluated runtime `557803404b549023b2d0271b52a2c8d19f5b994b`
(merged Order 83 / PR #503). Work continued through every category and FAQ after
the first defect. The result is a **negative audit**, not a PFINAL certification:
11 follow-ups occupy Orders 84–94 and PFINAL moves to Order 95. The compact
roadmap format comes from documentation PR #504, whose runtime tree is unchanged.
This PR publishes the audit and backlog; it does not silently broaden into 11
gameplay implementations. Each follows the one-at-a-time remediation process.

The [generated report](ORDER_84_AUDIT_REPORT.md) contains all findings and category
dispositions. The [JSON inventory](../data/source_audits/order84/audit.json) preserves
every observed rule/FAQ, exact rendered-block fingerprint, category owner and
regression-family link, prior obligation, reviewed Core package hash and support
status. **All clause-certification fields remain open.** This is deliberate:
family regression files and merged orders cannot establish a source-exact,
individual-clause facade certificate. That remaining evidence work belongs to
CAUDIT-01; it is not automatically another gameplay defect for every row.

## Source review

Selected candidate: the public [GDM Core page](https://game-datamissions.com/11th/rules/core-rules),
observed September 24. Its HTML identifies the public page asset retained by URL
and SHA-256 in the audit. The extractor parses literal data without executing
downloaded JavaScript. Every subsection and accordion was read, including all 59
FAQ entries, supplemental Stratagem bodies, the Universal Updates section, tables
and callouts. The resulting 345 rows contain 1,424 rendered blocks. These blocks
include examples, labels and formatting metadata; they are not a semantic rule count.

Numbering is not a unique identity: both 09.07.01 entries survive with title and
occurrence, and untitled 24.37.01 survives. No row is deduplicated by section number.
The observed page exposes no App-data version. The changelog's v946 selection does
not identify the live body as v946. Provider formatting markers remain part of
exact fingerprints; no runtime parsing or source registry was changed.

The browser confirmed GDM 15.11 omits the Heroic Intervention mode labels, extra
CP cost and part of the charge instruction. The complete modes are visible on
[40k.app 15.11](https://www.40k.app/rules/15-stratagems#15.11), consistent with the
existing [Order 50 source record](ORDER_50_SCOPE_PLAN.md). This is a source
completeness defect, not evidence that the engine lost Heroic Intervention or
that two declared identical App versions disagree. The candidate cannot certify
the corpus. No official-App access or co-versioned full-corpus comparison is claimed.

This artifact retains metadata and block fingerprints, not a redistributed copy
of the provider's complete text. Registered exact transcriptions remain in the
existing Core source packages; the audit records their current hashes and separate
load/execution statuses without upgrading partial or superseded rows. Source
equivalence between the candidate and those transcriptions remains a required
closure step. Historical observations and the owner resolutions for C12-04 and
C18-07 are preserved.

Reproduce inventory validation, generated reports and source extraction:

```sh
uv run --no-sync python -m tools.core_rules_order84_audit --check
uv run --no-sync python -m tools.core_rules_40k_app_audit --check
# Optional: supply the exact public page asset identified in audit.json.
uv run --no-sync python -m tools.core_rules_order84_audit --check --verify-capture /path/to/page.js
```

The fixed capture identity fails closed on drift. A future observation gets a new
audit identity; it must not overwrite this negative result to claim certification.

## Counterexamples and consumer trace

Run `uv run --no-sync python -m tools.core_rules_order84_probes` from the repository
root. [Retained results](../data/source_audits/order84/probe-results.json) contain
eight probes across seven finding families, plus a positive Shooting control. Diagnostics use real
canonical domain objects and named shared fixture builders, with no engine stubs
or decision-controller replacement. They report observations rather than assert
that known defects are correct gameplay.

| Probe | Expected Core behavior | Observed at the audited commit | Evidence scope |
|---|---|---|---|
| Dice set to 7 | Preserve the source-assigned result | D6-only record rejects it; 6 is accepted | Typed dice boundary, not a source-trigger replay |
| Source-dash Strength | Resolve the interaction as Strength 1 | Profile is accepted; wound-table consumer rejects its zero sentinel | Actual profile and shared wound helper; full attack regression still required |
| No viable Shooting attack | Allow eligible unit/type selection, then resolve no attacks | The phase advances without offering the unit; nearby-target control offers it | `LocalGameSession` progression and both viewer projections |
| 1 mm quarter divider | Exclude a base overlapping the divider | Secondary occupancy counts a base whose edge is 0.01 inches from centre | Real geometry; primary has the same duplicated bounds; no full scoring replay claimed |
| Full-health embarked revival | Return a two-wound model with two wounds | Returns one wound despite the full-health flag | Shared healing owner and recorded finite decision; cargo fixture is explicit state, not a replayed embark journey |
| Multiple wounded ordinary unit | Offer an eligible wounded model choice | Rejects because the unit is not attached | Real domain state; synthetic wounded precondition, not a damage-producer certificate |
| Ordinary healing with a destroyed Character | Exclude that model from ordinary unit-healing revival | Emits a revival placement request for it | Canonical infantry fixture with explicit Character keyword assignment, engine destruction and authenticated phase opening; no faction claim |
| Random melee splitting | Support source-correct random attack allocation | Returns `random_melee_split_unsupported` | Real catalog/proposal/shared validator; source timing must be resolved before implementation |

The Strength probe mirrors `attack_sequence_hit_wound` passing `.strength.final`
to `wound_roll_target_number`; it does not claim that the pure helper alone accepts
source descriptors. Ordinary Shooting filters both unit and type options using
legal declarations. Fight's explicit no-weapon/no-target completion and retained
Shooting's no-weapon completion are same-class controls, not additional failures.

Healing candidates, wound application and revival placement were traced through
`healing`, `healing_source_context`, `healing_geometry` and `healing_revival`.
The Character exclusion and multiple-wounded restriction share the ordinary
healing owner. Embarked health is independently hard-coded to one in both mutation
and `HealingStep` validation. Non-cargo reserve revival, default chooser authority,
overhang contact, intrinsic random profiles and general ignore-modifier permissions
are explicitly **consumer-trace/capability findings**. They need legal producer-to-
facade proofs in their follow-ups; they are not reported as successful full replay
counterexamples. An unsupported semantic path is still a certification blocker.

The same-class sweep included primary/secondary quarter consumers, physical
base-contact predicates, dice descriptors/records, catalog characteristic schemas,
all healing branches, ordinary/Fight/retained attack hosts and generic/Psychic
modifier selection. It also checked explicit unsupported results and current Core
package execution statuses. Existing per-weapon-instance One Shot support,
Torrent incompatibility validation, active-player-aware Psychic phase identity and
no-attack Fight completion were found; these are not falsely listed as missing.

The following links identify the inspected owners at the audited runtime. They
are trace anchors, not claims of complete source-clause regression coverage.

| Finding | Inspected owners |
|---|---|
| C01-07 | [Dice override record](../src/warhammer40k_core/core/dice_result_override.py), [override descriptors](../src/warhammer40k_core/engine/dice_result_override_descriptors.py) |
| C01-08 | [Fight contact geometry](../src/warhammer40k_core/engine/fight_geometry.py) |
| C01-09 | [Primary quarter evidence](../src/warhammer40k_core/engine/primary_scoring_spatial_evidence.py), [secondary occupancy](../src/warhammer40k_core/engine/secondary_scoring_occupancy.py) |
| C02-06 | [Catalog model profiles](../src/warhammer40k_core/core/datasheet.py), [characteristic values](../src/warhammer40k_core/core/attributes.py) |
| C02-07 | [Attack hit/wound consumer](../src/warhammer40k_core/engine/attack_sequence_hit_wound.py) |
| C02-08 | [Healing selection/mutation](../src/warhammer40k_core/engine/healing.py), [source context](../src/warhammer40k_core/engine/healing_source_context.py) |
| C01-10 | [Embarked healing and step validation](../src/warhammer40k_core/engine/healing.py), [battlefield revival](../src/warhammer40k_core/engine/healing_revival.py) |
| C04-04 | [Shooting unit/type eligibility](../src/warhammer40k_core/engine/phases/shooting_eligibility.py) |
| C04-05 | [Melee allocation validator](../src/warhammer40k_core/engine/fight_resolution.py) |
| C02-09 | [Modifier-ignore descriptors](../src/warhammer40k_core/engine/catalog_modifier_ignore.py), [shared decisions](../src/warhammer40k_core/engine/modifier_ignore.py) |
| C15-10 | [Source policy](CORE_RULES_SOURCE_POLICY.md), [retained Heroic source review](ORDER_50_SCOPE_PLAN.md) |

## Prior work and full-game assessment

The inventory includes all 18 distinct v931 obligations, v946 Rapid Disembark,
the September 10 dispositions, and explicit links for Heavy/flight distance,
Normal Move occurrence, objective control before cleanup, Action interruption,
revival anchors, shared parameterized projection and viewer redaction. Existing
regression families run again in the full suite. The historical Ongoing erratum
does not override the owner's v946 Engaging-only resolution.

No existing complete legal game driver or complete recorded workload was found
in the adapters, scripts or versioned performance evidence. `adapters/headless.py`
requires a supplied finite ranker and parameterized proposal generator; a single
decision adapter is not a complete game. All available measurement scripts report
component/slice evidence. Full-game samples are zero, mean/maximum unknown, and
both standing targets remain uncertified. Required workload, driver/replay,
hardware and result prerequisites are listed in the JSON. No AI or speculative
driver was added, and no timeout was converted into a rules answer.

## Scope and validation

PR review identified two closure-integrity defects: historical evidence could be
deleted or changed without failing validation, and the parser discarded PFINAL's
aggregate prerequisites. Complete fingerprints now pin the 48 retained Core
packages, 20 September 10 dispositions, six cross-category reviews and 19 prior
obligations, including nested identities, hashes and support statuses. These pins
authenticate the historical observation at `55780340`; they do not compare it to
future runtime package contents or silently refresh the audit.

PFINAL now declares all prior roadmap rows, including `P15J` and `S-MIRRORS`.
The parser expands that declaration into ordered prerequisite IDs, and the
prerequisite-order regression includes PFINAL. Omission, empty-list, duplicate,
metadata/status mutation and narrowed-prerequisite regressions fail closed; an
inserted source-governance row automatically becomes a PFINAL prerequisite.
The committed audit JSON and its historical findings remain unchanged.

Only audit tooling/data, code-quality regressions and documentation change. No
runtime source package, engine identity, decision type, payload schema, handler,
architecture boundary or gameplay path changes. The existing adapter contract
applies unchanged. Follow-up gameplay PRs must update it where their choices or
payloads change. No behavioral test file was added, moved or deleted, so the
eight-shard inventory remains unchanged and is checked before publication.

Local validation on the merged PR #504 baseline (`a050b8ab`) passed, including
fresh behavioral and code-quality runs after the integrity fixes:

- Complete behavioral suite, once with coverage and the required Node `PATH`:
  **9,196 passed; 85.22% coverage**. It emitted 10 SQLite `ResourceWarning`s
  from unchanged persistence-tampering tests; there were no failures.
- Complete code-quality suite, once afterward without coverage:
  **669 passed**. Both suites used `-n auto --dist=worksteal` (18 workers).
- Ruff check/format, mypy (3,220 source files), Pyright, all 11 import contracts,
  pre-commit, and the exact eight-shard manifest check passed.
- Engine build identity, external contract generation with `--base-ref origin/main`,
  and the installed-wheel smoke passed. Runtime identity remains
  `7c461fe83f419b78d2311b60ed93608835145a36e2b37be43f928b8e5718e807`.
- TypeScript generated models/typecheck, **5 unit tests** and **342 HTTP
  conformance assertions** passed, including deterministic replay comparison.
- Both audit report generators passed `--check`; the observed JS asset reproduced
  the pinned inventory; all eight probe results reproduced the retained JSON
  byte-for-byte. Local report/roadmap links resolve.
- The 58 focused audit/roadmap checks pass, including 36 added integrity cases.
  All 48 retained package paths, artifact hashes and package hashes were also
  checked directly against the audited Git commit, without changing the JSON.

The installed-wheel and TypeScript results are retained from initial PR
validation. The integrity fixes change none of their runtime or contract inputs;
the engine-identity and base-ref contract checks passed again.

The host has bundled Node but no `npm` executable. The initial `npm run check`
could not start. The same package scripts then passed through these direct
commands in `conformance/typescript`, using the bundled Node `PATH`:

```sh
node scripts/check-generated.mjs
node node_modules/typescript/bin/tsc --noEmit
node node_modules/tsx/dist/cli.mjs --test src/**/*.test.ts
node node_modules/tsx/dist/cli.mjs src/main.ts
```

These are correctness gates, not complete-game performance measurements. No
runtime hot path changed; no new performance budget is asserted.
