# Core Section04 corpus

2026-10-17 correction checkpoint: R4 now checks intermediate weapon/model/unit completion using the real executor and participation query. SF04-003 exposes delayed model participation in shooting and fighting; both new failures remain enabled. Native source identity is preserved; selected-pool and melee extra-attack contracts are explicit. Earlier counts/timings below are historical receipts; the current combined receipt is in `C:/Users/nostr/Documents/Codex/2026-10-16/task-15/corrections/FINAL-REPORT.txt`. No predecessor retirement or Linux qualification is claimed.

112 cases:111 pass and one enabled source-correct failure for SF04-002. Corpus completeness is distinct from engine compliance. No skips or xfails;108 behavioral cases,3 map checks and1 isolation check.

All18 rule rows and locally owned FAQs02,03,21,30,55,56 are authenticated against the retained current source, accounting for63 adopted obligations. The Core body is unversioned; changelog981 is not its version. No Section04 source rows are unadopted. `coverage.json` retains every source block, prior qualification, successor binding, and links to concrete assertion/expected-exception bodies. Metadata checks are not semantic coverage.

| Clause group | Obligations | Status |
| --- | ---: | --- |
| 04.00 Making Attacks | 3 | Passing semantic assertions |
| 04.01 Select Weapons | 4 | Passing semantic assertions |
| 04.01.01 Models Without Ranged/Melee Weapons | 2 | Passing semantic assertions |
| 04.01.02 Sidearms | 1 | Passing semantic assertions |
| 04.01.03 Multiple Weapon Profiles | 3 | Passing semantic assertions |
| 04.01.04 Attack Characteristics and Abilities | 3 | Passing semantic assertions |
| 04.01.05 Selected to Attack | 3 | Passing semantic assertions |
| 04.02 Select Targets | 7 | Passing semantic assertions |
| 04.02.01 Selecting Targets | 3 | Passing semantic assertions |
| 04.02.02 Against An Attack | 2 | Passing semantic assertions |
| 04.02.03 Single Target | 1 | Passing semantic assertions |
| 04.03 Resolve Attacks | 8 | Passing semantic assertions |
| 04.03.01 Identical Attacks | 2 | Passing semantic assertions |
| 04.03.02 Splitting Melee Attacks | 3 | Passing semantic assertions |
| 04.03.03 Target No Longer Eligible Or Viable | 1 | Passing semantic assertions |
| 04.03.04 Shot | 4 | SF04-002 unit-shot and SF04-003 model-completion failures; other assertions pass |
| 04.03.05 Fought | 4 | SF04-003 model-completion failure; other assertions pass |
| 04.03.06 Finished Making Its Attacks | 1 | Passing semantic assertions |
| FAQ 02 FAQ 02 | 2 | Passing semantic assertions |
| FAQ 03 FAQ 03 | 1 | Passing semantic assertions |
| FAQ 21 FAQ 21 | 1 | Passing semantic assertions |
| FAQ 30 FAQ 30 | 1 | Passing semantic assertions |
| FAQ 55 FAQ 55 | 1 | Passing semantic assertions |
| FAQ 56 FAQ 56 | 2 | Passing semantic assertions |

`future-fixes.json` records SF04-002: the eligibility consumer reports a unit as shot immediately after declaration, before any attack resolves. A real Lord Exultant two-weapon facade regression remains failing. Completion events are not claimed to fire early. No runtime code was changed. The provisional cross-bearer grouping suspicion was disproved on the native resolver and withdrawn; native physical grouping passes. Prior SF01-001 and SF03-001 remain untouched.

Use `.venv/Scripts/python.exe -m pytest tests/rules/section04 --no-cov --selected-army-source-index=<existing-index> -q`. Current expected exit1 contains three cases in test_completion_boundaries.py: one SF04-002 unit-shot failure and two SF04-003 model-completion failures (shooting and fighting), representing two distinct finding groups.

Fixtures reuse six immutable native selected-loader definitions and create fresh mutable state. Native Noise Marines supply two physical Blastmasters with different profiles. `prerequisites.json` labels Core contracts, including absent keywords/characteristics, zero-equipment melee, against-trigger qualifiers, and post-declaration geometry. No full-game construction, mustering execution, charging, unrelated missions, or replay reconstruction. The actual cached mission authority is an unavoidable facade Action dependency; its preparation is measured separately.

Serial Windows observation: native definition preparation 2.029410s, mission preparation 4.241638s, warm test calls 6.821166s (semantic-only 6.594383s), pytest 14.04s. Fresh process; filesystem caches not flushed. These are not Linux CI or speedup evidence.

Scoped Ruff/format/Mypy/Pyright pass for17 Python files.12 direct dependency controls pass; runtime identity remains current.14 new test files receive a labeled supplemental Windows shard profile including failed-case time; historical durations are preserved. Exact12-shard verification and preservation receipts live in `C:/Users/nostr/Documents/Codex/2026-10-16/task-11`.

Cross-section FAQ links remain in coverage.json:06/07/15 to06;09/20/37/48/49 to05;23 to02;44 to13. FAQ52's adopted and already-tested Not On Battlefield portion belongs to01.02.04; the transport/Firing Deck consumer remains18 per predecessor handoff. No duplicate FAQ execution is claimed here. A future independent clause/equivalence review and broader Linux integration are still required before older tests are retired.
