# Core Section02 testing milestone

2026-10-17 correction checkpoint: R2 now exercises witnessed fixed-pose movement through normal/advance/fixed consumers and actual reserve setup. Constructed absent-M qualification and Order115 successor references remain. Earlier counts/timings below are historical receipts; the current combined receipt is in `C:/Users/nostr/Documents/Codex/2026-10-16/task-15/corrections/FINAL-REPORT.txt`. No predecessor retirement or Linux qualification is claimed.

The bounded Section02 corpus is complete: **100 adopted operative obligations
(97 rules + 3 local FAQ), all mapped to assertions; zero unimplemented**.
The complete family passes **239 cases**, comprising 235 rule cases, one mutable
state isolation case, and three coverage-map integrity checks. Eight obligations
use explicitly constructed Core rule-contract inputs; the other obligations use
real datasheets or typed Core examples/algebra at their named production owners.
This does not certify all native datasheet integrations or full-game behavior.

`coverage.json` maps each clause, source block/hash, production owner, assertion,
predecessor and adopted successor. Context/nonoperative blocks remain separate.
No predecessor was copied wholesale, retired, deleted, or counted as a new pass.

## Source authority and hierarchy

The adopted full Core capture is `data/source_audits/order135/retained-current-sources.json`
(2026-10-01T12:04:31.127429Z), with its current bindings. All 22 relevant retained
row fingerprints (19 rules and 3 FAQ) match the complete October15 body observation
recorded in the map. That body is unversioned; changelog v981 is not a body version.
No new source adoption occurred. Bindings include Orders 115, 123, 124, 125 and 133.
The seven subsections and twelve sub-subsections are all represented below. Zero
operative obligations means context/metadata rather than an omitted requirement.

| Section | Adopted operative obligations | Contract inputs among these |
| --- | ---: | ---: |
| 02.01 Datasheet Name | 0 | 0 |
| 02.01.01 Datasheet Name and Keywords | 1 | 0 |
| 02.02 Profiles | 7 | 3 |
| 02.02.01 Modifiers | 43 | 0 |
| 02.02.02 Ignore Modifiers | 2 | 1 |
| 02.02.03 Random Characteristics | 8 | 3 |
| 02.02.04 Healing Or Regaining Lost Wounds | 7 | 0 |
| 02.02.05 Full Wounds Remaining | 1 | 0 |
| 02.02.06 Characteristic Modifiers & Modified Characteristics | 0 | 0 |
| 02.03 Abilities | 0 | 0 |
| 02.03.01 Rules With Multiple Conditions And Effects | 1 | 0 |
| 02.04 Weapons | 8 | 0 |
| 02.04.01 Weapons With No Strength | 1 | 1 |
| 02.05 Keywords | 1 | 0 |
| 02.05.01 Using Keywords & Mixed Keywords in Units | 12 | 0 |
| 02.06 Unit Composition And Other Rules | 2 | 0 |
| 02.06.01 Bearer | 1 | 0 |
| 02.06.02 Unit's Equipment | 1 | 0 |
| 02.07 Wargear options | 1 | 0 |

The three adopted clarifications remain beside the sections they clarify:

- `faq:66be2ad9-24af-4edf-890a-c0e55004bf76`: owning section **02.02.01**, Core FAQ +1A input modifies each of real Ranger rifle/pistol profiles, generates source A+1 each, leaves melee unchanged and consumes no random dice.
- `faq:6575ee89-b92a-456d-8e59-4ee513df8f4e`: owning section **02.05.01**, EMPEROR'S CHILDREN matches actual faction; CHILDREN fails.
- `faq:60232b79-7a10-44a0-ac68-e27312c7ba60`: owning section **02.05.01**, Dead leader stops contributing CHARACTER; explicitly retained presence preserves contribution until removal.

Cross-section clarifications have one owner and a link in `coverage.json`: attached
ability scope in 19, optional stratagem base cost in 15, and retained Fight-on-Death
presence in 05. Their future owning rewrite locations and predecessor references
are explicit; no duplicate lifecycle execution was added. The three unadopted
v981 Firing Deck clarification IDs remain one distinct obligation V981-Q03 owned
by 18; they are not silently adopted or included in the 100-obligation pass count.

## Fixture and boundary design

One immutable indexed catalog build supplies six actual supported datasheets:
Infractors **000004080**, Dire Avengers **000000593**, Maulerfiend **000000968**,
Rangers **000000592**, Lord Exultant **000004078**, Chaos Spawn **000004090**.
Native profiles, equipment, keywords, abilities and geometry stay intact. Each case
instantiates and deep-copies its small unit graph. Isolation asserts that mutating
one ability payload leaves peers/subsequent instances unchanged; session teardown
verifies the prepared package digest unchanged.

The explicitly labelled constructed files test absent M/OC/S, random model M/T,
other random weapon S and an unqualified modifier-ignore permission. They use
production consumers and Core-contract identities, never claim those stats or that
grant belong to a real datasheet, and do not change the retained catalog. Raw source
candidate/provider limitations remain in `prerequisites.json` as native integration
limitations, not unimplemented Core semantics. No new provider or geometry support
was added. No incorrect engine outcome or execution crash was confirmed;
`future-fixes.json` retains the user's future-fix and narrow crash-repair policy.

Tests use direct production owners, avoiding mission mustering/deployment/charge
lifecycles. The nested Core example alone needs one authentic objective setup to
exercise both predicates; it is explicitly labelled cross-section integration.
Healing/revival asserts health and reserve transitions, not physical placement of
a revived model. The bounded Maulerfiend attack case proves random damage occurs
after allocation and continues to completion, without a save/fork/all-view matrix.

## Run and bounded Windows evidence

```powershell
uv run --no-sync pytest tests/rules/section02 -q --no-cov --selected-army-source-index=<index-directory>
```

The existing provider's full-source path remains available if the option is omitted.
A supplied missing/stale/corrupt index is rejected; the tests never rebuild it.
Explicit regeneration remains:

```powershell
uv run --no-sync python -m tools.ability_support_sources <source-json-dir> <new-index-dir>
```

Fresh-process measurement on Windows, without flushing filesystem caches:

- Prepared six real definitions once: **1.779s**.
- Prepared the immutable nested-example objective setup once: **1.345s**.
- First nested-case call, including further cold source validation: **4.121s**.
- Other 238 call bodies after their fixture setup: **0.999s** total.
- All 239 call bodies: **5.120s**; pytest reports **8.78s**;
  measured pytest invocation including startup/import/collection: **13.455s**.
- Reused task7 source index; no index build or architecture tuning performed.

These figures separate setup and first-use cost. They are one bounded receipt,
not a cold-cache benchmark, full-suite speedup, or Linux CI performance claim.
Per-family setup includes whichever session fixture that family first triggers.

| Test family | Cases | Call seconds | Setup seconds |
| --- | ---: | ---: | ---: |
| `test_02_01_identity.py` | 5 | 0.0108 | 1.7866 |
| `test_02_02_01_modifiers.py` | 104 | 0.0574 | 0.0305 |
| `test_02_02_01_weapon_scope.py` | 3 | 0.0046 | 0.0006 |
| `test_02_02_02_ignore_modifiers.py` | 10 | 0.0110 | 0.0027 |
| `test_02_02_02_native_permission.py` | 4 | 0.0852 | 0.0010 |
| `test_02_02_03_attack_generation.py` | 2 | 0.0464 | 0.0005 |
| `test_02_02_03_damage_timing.py` | 1 | 0.1801 | 0.0002 |
| `test_02_02_03_random_characteristics.py` | 3 | 0.0008 | 0.0008 |
| `test_02_02_04_healing.py` | 7 | 0.0221 | 0.0018 |
| `test_02_02_04_revival.py` | 4 | 0.0197 | 0.0008 |
| `test_02_02_constructed_contracts.py` | 7 | 0.0457 | 0.0013 |
| `test_02_02_profiles.py` | 12 | 0.0214 | 0.0031 |
| `test_02_03_01_nested.py` | 4 | 4.2318 | 1.3469 |
| `test_02_04_01_constructed_contract.py` | 1 | 0.0002 | 0.0002 |
| `test_02_04_live_consumers.py` | 17 | 0.1043 | 0.0054 |
| `test_02_04_weapons.py` | 9 | 0.0141 | 0.0025 |
| `test_02_05_keyword_consumers.py` | 20 | 0.0851 | 0.0056 |
| `test_02_05_keywords.py` | 12 | 0.0210 | 0.0028 |
| `test_02_06_equipment.py` | 11 | 0.0144 | 0.0025 |
| `test_coverage_map.py` | 3 | 0.1440 | 0.0003 |

Durable receipts are linked by `validation.json`. Direct dependency controls passed
104 cases in the earlier unchanged-production run. Scoped Ruff, mypy and Pyright
checks cover this new family and its support modules. All 20 test files are included
once in the generated 12-shard inventory, with other historical timings preserved.

## Remaining gates and next work

Full integration/Linux CI and independent coverage/equivalence review remain pending.
Predecessor retirement requires that review; none was removed here. The loader's
10 previously documented out-of-scope Pyright diagnostics are unchanged; scoped
Section02 checks do not establish repository-wide type cleanliness. The exact
staged tree and ten loader integration files are preserved, verified in the final
manifest. No production edits, staging, commits, pushes or remote CI occurred.

Stop this milestone here. The smallest next task is a fresh Section01 inventory and
efficient test rewrite, following the approved **02 → 01 → 03 → 04 → 05 → 06** sequence;
Section00 remains deferred.
