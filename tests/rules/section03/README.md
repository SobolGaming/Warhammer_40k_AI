# SF03-001 repair checkpoint

The native turn-end boundary now requests the controlling player's casualty
choice before each removal and rechecks complete rules-unit coherency. The two
original source-correct regressions and all original downstream assertions remain
enabled. New native finite-choice, rejection, attached-unit, geometry/model-count
and valid casualty-checkpoint persistence/replay controls are in `test_cleanup.py`.
See [bounded source and implementation scope](../../../docs/SF03_001_COHERENCY_CHOICE_SCOPE.md).
The same independent review remains pending; the earlier receipts below are history.

# Core Section03 corpus

2026-10-17 correction checkpoint: R1 downstream cleanup tests now consume explicitly authenticated post-choice contracts; they no longer bless automatic casualty selection. Native D13 remains open. Sequential removals and either player turn are covered. R5 FAQ52 obligations01-02 belong to 01.02.04; obligation03 remains Section18 linked-only. Earlier counts/timings below are historical receipts; the current combined receipt is in `C:/Users/nostr/Documents/Codex/2026-10-16/task-15/corrections/FINAL-REPORT.txt`. No predecessor retirement or Linux qualification is claimed.

116 cases: 114 pass and two enabled source-correct failures for SF03-001. Corpus completion is not engine compliance. No skips or xfails.

The complete adopted hierarchy contains 13 rule rows and four locally owned FAQs (04, 05, 26, 28), with 62 obligations. All fingerprints match the retained current Core capture. The Core body is unversioned; changelog 981 is not its version. No Section03 source rows are unadopted. `coverage.json` retains every original qualification and current successor binding, all source blocks and explicit source-to-assertion links. Metadata checks do not count as semantic coverage.

| Clause group | Adopted obligations | Status |
| --- | ---: | --- |
| 03.01 Moving Units | 21 | Passing semantic assertions |
| 03.01.01 Different Move Characteristics | 1 | Passing semantic assertions |
| 03.01.02 Moving Over Or Through Models | 2 | Passing semantic assertions |
| 03.01.03 Random Movement | 0 | Context/cross-reference accounted |
| 03.01.04 When Moving Up To | 1 | Passing semantic assertions |
| 03.02 Set Up | 4 | Passing semantic assertions |
| 03.02.01 If You Cannot Set Up a Unit | 2 | Passing semantic assertions |
| 03.02.02 Setting Up Large Models | 13 | Passing semantic assertions |
| 03.02.03 Redeployments | 3 | Passing semantic assertions |
| 03.03 Coherency | 6 | 1 visible semantic failure; other assertions pass |
| 03.03.01 What Is Coherency | 1 | Passing semantic assertions |
| 03.04 Engagement | 4 | Passing semantic assertions |
| 03.04.01 What Is Engagement | 0 | Context/cross-reference accounted |
| FAQ 04 FAQ 04 | 1 | Passing semantic assertions |
| FAQ 05 FAQ 05 | 1 | Passing semantic assertions |
| FAQ 26 FAQ 26 | 1 | Passing semantic assertions |
| FAQ 28 FAQ 28 | 1 | Passing semantic assertions |

`future-fixes.json` describes SF03-001 with expected/actual behavior, production entry path and failing node IDs. The owner should choose coherency casualties; the engine currently destroys one automatically. No rule behavior was repaired. Existing Section01 Stealth failures remain untouched.

`prerequisites.json` distinguishes native selected-loader definitions from labeled Core contracts. Immutable definitions are reused once; units and mutable states are fresh per case. Mission authority is cached only for boundaries requiring it. No full-game startup, mustering, prior phases or replay reconstruction is used.

Windows observation: native definition preparation 2.097027s, mission authority preparation 3.993744s, all warm test bodies 3.419149s, semantic bodies 3.324270s, pytest total13.83s. Fresh process, filesystem caches not flushed; quality checks concurrent. This is not Linux CI evidence or a speedup benchmark. Detailed per-case timings and JUnit: `C:/Users/nostr/Documents/Codex/2026-10-16/task-10`.

Run: `.venv/Scripts/python.exe -m pytest tests/rules/section03 --no-cov --selected-army-source-index=<existing-index> -q`. Expected current exit1: only the two SF03-001 cases fail. Scoped Ruff/format/Mypy/Pyright pass. The bounded direct dependency set passes17 cases. Historical shard durations are retained; the new Windows supplemental profile includes failed cases honestly.

Cross-section FAQ ownership:14 remains18;39 remains17;49 remains05;52 obligations01-02 belong to01.02.04 and obligation03 remains18 linked-only. Random Movement03.01.03 links to Section02.02.03. Future sections must preserve these owners and source qualifications. Independent clause/equivalence review and broader Linux integration remain gates before predecessor retirement.
