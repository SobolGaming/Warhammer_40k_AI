# Core Section05 corpus

274 cases:272 pass and2 enabled source-correct failures.79 obligations have passing assertions,2 map to SF05-001, and1 maps to the SF05-002 future-fix semantic finding. No skips/xfails. Corpus completeness is distinct from engine compliance.

All15 rule rows and locally owned FAQs09,20,29,37,47,48,49 are authenticated against the retained current capture, accounting for82 obligations. All source fingerprints match; no05 rows are unadopted. The body is unversioned, and changelog981 is context rather than a version. `coverage.json` preserves full blocks, original qualifications, successor bindings, cross-section links and actual assertion/expected-exception bodies. Three metadata checks do not count as behavioral coverage.

| Clause group | Obligations | Status |
| --- | ---: | --- |
| 05.00 Attack Sequence | 8 | 8 asserted |
| 05.01 Hit Rolls | 5 | 5 asserted |
| 05.01.01 Critical Hits and Critical Wounds | 3 | 3 asserted |
| 05.02 Wound Rolls | 9 | 9 asserted |
| 05.02.01 Multiple Toughness Characteristics | 2 | 2 asserted |
| 05.03 Save Rolls | 8 | 8 asserted |
| 05.03.01 Saving Throw | 1 | 1 asserted |
| 05.03.02 Attacks Modified during Hit and Wound rolls | 3 | 3 asserted |
| 05.04 Inflict Damage | 11 | 11 asserted |
| 05.04.01 Current Allocation Group | 2 | 2 asserted |
| 05.04.02 Modifying Damage | 0 | Cross-reference to02.02.01 |
| 05.04.03 Suffers Damage | 1 | 1 asserted |
| 05.04.04 Destroyed | 7 | 7 asserted |
| 05.04.05 Fight On Death | 5 | 4 asserted, 1 visible_semantic_failure |
| 05.04.06 Measuring To A Destroyed Model Or Unit | 3 | 3 asserted |
| FAQ 09 FAQ 09 | 1 | 1 asserted |
| FAQ 20 FAQ 20 | 2 | 1 asserted, 1 visible_semantic_failure |
| FAQ 29 FAQ 29 | 2 | 2 asserted |
| FAQ 37 FAQ 37 | 1 | 1 asserted |
| FAQ 47 FAQ 47 | 2 | 2 asserted |
| FAQ 48 FAQ 48 | 1 | 1 asserted |
| FAQ 49 FAQ 49 | 5 | 4 asserted, 1 visible_semantic_failure |

SF05-001: Epic Challenge rejects an authenticated retained native Lord Exultant with `epic_challenge_model_not_alive_and_placed`, contrary to05.04.05 block3 and FAQ49 block2. Alive control accepts, spends1CP and grants Precision. This is a valid rejection, not a crash. The explicit proposal boundary does not prove natural phase window discovery or close D12 qualifications.

SF05-002 is now an enabled future-fix semantic finding. On 2026-10-17 at 12:06 UTC, the user approved the FAQ-specific sequence: finish Fight on Death or reach its expiry, remove the retained model, then resolve Deadly Demise. This supersedes the earlier user-approved before-removal interpretation for this interaction only. Retained FAQ20 is `faq:ab92e97b-be2b-4125-9ded-fcfa6abe092e`, not newly verified official App authority. The end-of-phase alternative need not have enemy casualties, making the retained models the stronger referent. Conflicting Core05.04.05 wording and the prior verdict remain provenance in `future-fixes.json`. See [the approved specification](../../../docs/SECTION05_DEADLY_DEMISE_DECISION.md).

Four immutable native definitions are reused through the selected-army loader; each case has fresh mutable state and physical geometry. Constructed absent boundary values are labeled in `prerequisites.json`. No full-game creation, mission authority, mustering execution, earlier phases or replay. One isolation test and the catalog digest guard prevent shared-state contamination.

Stable serial Windows measurement: selected-definition preparation 1.737413s; warm test calls 2.168037s, including 1.991212s behavioral-only; pytest 6.04s; subprocess 11.822278s. Imports/plugins/full failure reporting account for unprofiled residual time. No filesystem-cache flush, Linux run or controlled speedup comparison is claimed. Short traceback is recommended for routine development.

Use `.venv/Scripts/python.exe -m pytest tests/rules/section05 --no-cov --selected-army-source-index=<existing-index> -q --tb=short`. Expected exit1 comes only from the two named findings.22-file scoped Ruff/format/Mypy/Pyright and35 direct dependency controls pass. Runtime identity is unchanged.18 new test files receive supplemental measured shard entries, preserving all1180 historical durations. Final exact12-shard and preservation receipts live in `C:/Users/nostr/Documents/Codex/2026-10-16/task-12`.

No runtime changes or crash repairs. Previous Sections01–04, loader integration and narrow Action repair remain untouched. SF01-001/SF03-001/SF04-002 remain deferred. Fresh Section06 follows;00 remains deferred. Broader Linux integration and independent legacy equivalence are still required before predecessor tests are retired.

Decision addendum (2026-10-17): the existing removal-before-Deadly-Demise test and all executable assertions are unchanged; no suite was rerun. Historical Windows/Linux outcomes remain 1,075 total, 1,064 passed and 11 failed, now classified into six future-fix semantic groups. Section05 remains 274 cases, 272 passed and two failures. Coverage metadata now records 79 asserted obligations and three visible semantic-failure obligations; two map to SF05-001 and one to SF05-002. `validation.json` and older run reports retain their historical verdicts. The combined Deadly Demise interaction still lacks focused coverage proving use of the Core05.04.06 position before destruction (not merely the last position before removal), and protection of enemy casualties with their own independent retention. These requirements are queued for the future fix and are not claimed as covered.
