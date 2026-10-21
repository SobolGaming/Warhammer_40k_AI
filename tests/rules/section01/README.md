# Core Section01 focused corpus

2026-10-17 correction checkpoint: R3 now executes whole-roll and component reroll permissions through the actual decision/result consumer and injected physical outcomes; repeat rerolls remain prohibited. Earlier counts/timings below are historical receipts; the current combined receipt is in `C:/Users/nostr/Documents/Codex/2026-10-16/task-15/corrections/FINAL-REPORT.txt`. No predecessor retirement or Linux qualification is claimed.

The adopted bounded corpus is implemented: **143 obligations accounted for (140 rule,
3 FAQ)** across seven subsections and thirty sub-subsections. **142 obligations have
local production-owner assertions**: 139 map to passing paths and three to the same
visible Stealth regression. The remaining Firing Deck FAQ obligation has one external
Section18 owner and is linked only. It is not claimed as a new Section01 pass.

Final run: **230 passed, 4 failed, 0 skipped/xfail**, 234 cases in 30 test files.
The four failures are deliberately visible source-expected assertions, registered as
**SF01-001** in `future-fixes.json`. Corpus implementation does not mean engine-green
or full compliance. Three inventory checks assert map integrity, not rule behavior.
One state-isolation case and one small serialization case are separately identifiable.

`coverage.json` gives every adopted clause, source block/fingerprint, actual production
entry point, asserting node, predecessor reference and ownership status. Old broad
tests were used as references; none was copied wholesale, deleted or retired.

## Source authority and complete hierarchy

The adopted full capture and bindings remain
`data/source_audits/order135/retained-current-sources.json` and `current-bindings.json`
(observed 2026-10-01T12:04:31.127429Z). All 37 adopted rule rows and FAQ52 match the
hash-verified complete October15 capture recorded in the map. The body is unversioned;
changelog 981 is not a body version. Orders 122 duration defaults and 131 objective
approach bindings remain explicit. No authority migration or source adoption occurred.

| Section | Adopted obligations |
| --- | ---: |
| 01.01 Armies | 2 |
| 01.01.01 You | 1 |
| 01.02 Units and Models | 7 |
| 01.02.01 Starting Strength and Half-Strength | 8 |
| 01.02.02 Persisting Rules Effects | 6 |
| 01.02.03 Revived and Adding Models to a Unit | 12 |
| 01.02.04 Not On The Battlefield | 12 |
| 01.02.05 Other Model / Unit | 2 |
| 01.02.06 Splitting Units | 5 |
| 01.02.07 Describing Units | 3 |
| 01.02.08 A (Unit/Model/Object) | 1 |
| 01.02.09 Tokens | 2 |
| 01.02.10 Adding a new unit to your army | 1 |
| 01.02.11 All Types of Model | 2 |
| 01.03 Active Player and Opposing Player | 6 |
| 01.03.01 Player's Rules | 9 |
| 01.03.02 Rules Sequencing | 5 |
| 01.04 Measuring Distances | 3 |
| 01.04.01 Within / Wholly Within | 6 |
| 01.04.02 Closest Or Nearest Model/Unit | 2 |
| 01.04.03 As Close As Possible | 7 |
| 01.04.04 Base Contact or Base to Base Contact | 5 |
| 01.04.05 Table Quarters | 1 |
| 01.05 Dice | 6 |
| 01.05.01 Automatically Successful/Passes/Hits/Wounds | 2 |
| 01.05.02 Re-rolls | 4 |
| 01.05.03 Modifying Dice Rolls | 0 |
| 01.05.04 Ignoring Roll Modifiers | 0 |
| 01.05.05 Roll Off | 2 |
| 01.05.06 Doubles Or Triples | 2 |
| 01.05.07 Highest or Lowest Dice Result | 2 |
| 01.05.08 Treated As, Set To (Dice Roll) | 2 |
| 01.06 Leadership Rolls | 3 |
| 01.06.01 Leadership Test | 1 |
| 01.07 Battle-shock Rolls | 7 |
| 01.07.01 Battlefield Morale | 0 |
| 01.07.02 Battle-shock Test | 1 |

Zero-obligation rows are retained context, not missing tests. Modifier/ignore-modifier
cross-references link to Section02. FAQ52 (`7ac6c358-0263-49ff-aee7-28b8fd4b5b8b`, no
explicit version; row hash `736b6d704a27951f968fbcc84f7b0eca6840b08a451d353390367442244b1766`)
is colocated with **01.02.04**. Its first two obligations execute there; its third
Firing Deck ownership obligation is linked to Section18 and its retained predecessor.

Two newer retained source rows remain explicit **unadopted gaps**:
01.02.12 replacement alignment/closest legal position, and 01.04.06 zero-thickness,
normally straight lines. They are not included in the adopted obligation count.

## Minimal states, real definitions and explicit contracts

One immutable prepared catalog supplies six supported native definitions: Infractors
000004080, Lord Exultant 000004078, Chaos Spawn 000004090, Dire Avengers 000000593,
Maulerfiend 000000968 and Wave Serpent 000000599. Native stats/equipment/abilities and
geometry are retained. Fresh unit graphs deep-copy mutable payloads. The isolation
test mutates one graph and proves peers and later instances unchanged; session teardown
checks the immutable catalog digest. No objective preparation is needed in this family.

`prerequisites.json` lists constructed Core contracts explicitly. They include parsed
lifetime/target/grant examples, typed presence and Action permissions, attached and
cargo boundaries over native bodies, player-owned rule categories, timing batches,
pure circle/FRAME/overhang geometry, dice values and an automatic-hit weapon contract.
Those are not native faction legality or datasheet-grant certifications. The Rhino
definition still lacks a representative-height prerequisite; supported Wave Serpent
geometry is reused without adding provider or faction geometry support.

Tests call actual parsers, evaluators and finite decision owners. Return decisions,
capacity overflow, starting strength, sequencing, range/path predicates, dice rerolls,
Battle-shock and Action interruption run on small valid states. Geometry is checked
with real path/terrain validators. The automatic-hit case reaches the wound step and
proves no hit die was rolled. Save/replay concerns are kept in a small JSON roundtrip
integration case, rather than repeated full-game setup. No mission/mustering/charge
traversal is used merely to reach unrelated clauses.

One supported native Action path crashed during permission scanning. The narrow repair
in `engine/mission_action_battle_shock.py` skips unrelated RuleIR abilities before
validating an actual Action permission's source identity. Positive permission and
drift rejection controls pass. This is recorded as **CF01-001**. No wrong-rule-outcome
repair was made; the Stealth normalization defect remains for a future fix PR.

## Bounded Windows validation

```powershell
.venv/Scripts/python.exe -m pytest tests/rules/section01 -q --no-cov --selected-army-source-index=<existing-index>
```

Reused the explicit task7 index and existing provider. Missing/stale/corrupt supplied
indexes are rejected, not rebuilt. No loader tuning or index regeneration occurred.
This command exits1 while SF01-001 remains open.

Final fresh-process receipt: definition preparation **2.731s** once;
all call bodies **1.398s**, including **0.112s** for
map checks; other semantic/isolation/integration bodies **1.287s**.
Pytest reports **5.35s**; process startup/import/collection included wall time is
**11.984s**. Filesystem caches were not flushed. Dependency/type
checks ran concurrently, so these are bounded receipts, not comparative benchmarks.
Earlier complete run before the extra advancement assertion: 229 pass/4 fail in 4.06s,
retained separately. No Linux performance claim is made.

| Test file | Passed | Failed | Calls (s) | Setup (s) |
| --- | ---: | ---: | ---: | ---: |
| `test_01_02_attached.py` | 9 | 0 | 0.0686 | 2.7409 |
| `test_01_02_attached_return.py` | 2 | 0 | 0.0267 | 0.0006 |
| `test_01_02_aura.py` | 4 | 0 | 0.0561 | 0.0013 |
| `test_01_02_cargo_return.py` | 2 | 0 | 0.0282 | 0.0005 |
| `test_01_02_effects.py` | 12 | 0 | 0.1055 | 0.0045 |
| `test_01_02_group.py` | 3 | 0 | 0.0128 | 0.0005 |
| `test_01_02_presence.py` | 22 | 0 | 0.1543 | 0.0066 |
| `test_01_02_revival.py` | 6 | 0 | 0.0436 | 0.0014 |
| `test_01_02_revival_geometry.py` | 5 | 0 | 0.0028 | 0.0008 |
| `test_01_02_split.py` | 7 | 0 | 0.0337 | 0.0014 |
| `test_01_02_strength.py` | 15 | 0 | 0.0343 | 0.0023 |
| `test_01_02_tokens.py` | 1 | 0 | 0.0071 | 0.0001 |
| `test_01_02_unrestricted.py` | 4 | 4 | 0.0406 | 0.0018 |
| `test_01_03_batches.py` | 4 | 0 | 0.0038 | 0.0003 |
| `test_01_03_ownership.py` | 4 | 0 | 0.0309 | 0.0007 |
| `test_01_03_stratagem_ownership.py` | 2 | 0 | 0.0089 | 0.0003 |
| `test_01_03_timing.py` | 11 | 0 | 0.0431 | 0.0020 |
| `test_01_04_contact_lifetime.py` | 3 | 0 | 0.2034 | 0.0007 |
| `test_01_04_contact_movement.py` | 3 | 0 | 0.0251 | 0.0008 |
| `test_01_04_measurement.py` | 17 | 0 | 0.0040 | 0.0035 |
| `test_01_04_movement.py` | 13 | 0 | 0.2052 | 0.0038 |
| `test_01_04_units.py` | 5 | 0 | 0.0420 | 0.0012 |
| `test_01_05_choice.py` | 4 | 0 | 0.0233 | 0.0010 |
| `test_01_05_dice.py` | 32 | 0 | 0.0115 | 0.0062 |
| `test_01_05_results.py` | 26 | 0 | 0.0192 | 0.0056 |
| `test_01_06_07_morale.py` | 5 | 0 | 0.0233 | 0.0008 |
| `test_01_06_leadership.py` | 2 | 0 | 0.0088 | 0.0003 |
| `test_01_07_actions.py` | 3 | 0 | 0.0131 | 0.0005 |
| `test_coverage_map.py` | 3 | 0 | 0.1117 | 0.0003 |
| `test_integration_roundtrip.py` | 1 | 0 | 0.0065 | 0.0001 |

The 24 direct dependency controls pass. Scoped Ruff, format, mypy and Pyright pass for
the 33 new Python files and one repaired production module. The 30 test files occur once
in the 12-shard inventory; prior file timings are unchanged. The supplemental timing
profile explicitly includes four failing cases and does not claim a successful suite.
`validation.json` links durable commands, XML, per-phase timings and preservation proof.

## Preservation and handoff

Incoming HEAD, exact staged tree, all loader/Section02 work and all predecessors are
preserved. Only the narrow crash module and generated shard records change among
pre-existing files. New Section01 files stay unstaged. No reset, staging, commit,
push, remote CI or full-repository test suite occurred.

Broader integration/Linux CI and independent clause/assertion/equivalence review remain
pending; predecessors must remain until that review. Stop here and hand off to a fresh
Section03 task, then 04/05/06. Section00 remains deferred. Carry forward the same minimal
fixture, visible semantic-regression, narrow crash-repair, preservation and FAQ-owner
rules. See the task9 `section03-handoff.txt` and `section01-complete-report.txt`.
