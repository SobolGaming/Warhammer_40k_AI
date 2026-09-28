# Order 94 / P15J — complete Heroic Intervention evidence

Base: `94f7e18cf369461063dcd78eaa19199c72fb1374` (Order 93 / PR #515).
Finding: C15-10. Scope: Core 15.11 source governance only.

## Invariant and evidence

A selected source observation must retain the complete operative wording and
its actual identity. Missing provider text cannot silently become a rule change,
and an unversioned live page cannot inherit a changelog's App version.

The [review inventory](../data/source_audits/order94/audit.json) retains the
complete September 28 40k.app 15.11 DOM section, a deterministic transcription,
provider, canonical URL, observation time, policy, non-affiliation, stable rule ID,
capture hash, transcription hash and observation fingerprint. Both App-data
version and App build are explicitly unknown. The retained fragment includes
both mode labels, the extra cost nested with Into the Fray, and every sentence.
The browser accessibility view additionally confirms the base cost's CSS-rendered
CP label. The capture method records that limitation and the added final newline.

The immutable September 24 GDM observation is a separate comparison input.
Retrieving its exact pinned public asset reproduced the original raw SHA-256
and all eight Heroic blocks; those blocks are now retained locally so their
fingerprints can be checked offline. They lack both mode names, the extra CP
cost, and the starts of two Into the Fray sentences. They are never filled in
using another provider's text. This is not a claim about the current GDM UI.

The complete official Core PDF was hash-verified and page 57 was rendered and
visually inspected. All ten operative comparisons match the selected mirror,
including the +1CP badge's placement with Into the Fray. The existing
[Order 50 source review](ORDER_50_SCOPE_PLAN.md) is retained and hash-bound too.
The [generated reconciliation](ORDER_94_SOURCE_REVIEW.md) records each clause,
historical omission and the boundaries of the comparison.

The source policy permits complete observations from either maintained provider.
This review resolves the selection's completeness with a complete 40k.app
observation and independent existing official evidence. It establishes neither
co-versioned agreement nor co-versioned disagreement. It does not grant an
exception to the existing official-App disambiguation or conflict policy.

## Ownership and scope audit

The source-to-engine trace uses the existing stable ID
`gw-11e-core-stratagems:core:heroic-intervention`. The catalog owns base cost,
eligibility and the two structured modes; Stratagem selection owns additional
cost; `heroic_intervention_rolls` supplies restrictions to the shared Charge
owner. Existing facade regressions cover mode commitment, costs, modified-roll
limits, completed-charge targets, range, witnessed completion, viewers, restore
and exact replay. The inventory links individual requirements to those owners
and existing regressions as trace evidence, not independent PFINAL certificates.

The same-class audit inspected the historical category-15 blocks, the original
Order 84 findings and source-policy version handling. This change closes the
identified 15.11 evidence gap; a fresh full-corpus completeness comparison remains
PFINAL's work. It preserves the negative Order 84 audit byte-for-byte.

This is an offline review artifact, not a runtime source package. It neither
adds nor claims registered `project_authoritative_app_mirror` loader evidence.
No engine package, source-authority registry, generated runtime identity, content
support status or gameplay consumer changes. Existing runtime source identity
and official provenance remain intact. There is no hot-path or algorithm change
requiring new performance measurements; no full-game target is certified.

The existing [adapter contract](ADAPTER_DECISION_CONTRACT.md) applies unchanged:
there is no new choice, option family, proposal, payload or viewer behavior.
No behavioral file is added, moved or removed, so the shard inventory is unchanged.

## Offline validation

The typed loader rejects unknown/missing fields and pins the whole reviewed
inventory independently of its self-reported hashes. It authenticates capture,
transcription, source tuple, historical GDM blocks, official PDF and Order 50
review, and checks that the linked owners and regressions exist. New observations
require separate reviewed identities; refreshing this audit into a different
source selection is intentionally unsupported.

```sh
uv run python -m tools.core_rules_order94_audit --check
uv run python -m tools.core_rules_order84_audit --check
uv run python -m tools.core_rules_40k_app_audit --check
uv run pytest tests/code_quality/test_order94_source_review.py --no-cov
```

Source-integrity regressions were added before the loader. They cover every
observation tuple field, each of ten clause omissions, truncation, invalid
selection/version/certification claims, changed hashes/history/owner references,
malformed shapes and a changed retained capture.

## Final validation and independent review

The complete behavioral suite passed **9,756 tests with 85.20% coverage**, then
the complete code-quality suite passed **741 tests** without coverage. Both
used 18 xdist workers with work stealing and the required Node PATH. There were
no failed, errored or skipped tests in either JUnit report. The redirected
behavioral console log is empty; the successful process exit, complete JUnit
profile and coverage JSON retain the result. No second no-coverage behavioral
run was used as a final gate.

Ruff, formatting, mypy, Pyright, all 11 import contracts, the exact eight-shard
check and all-files pre-commit passed. The affected source-audit generators,
historical full-capture reproduction, exact-base external contract, generated
TypeScript/type checks, five client tests, 342 HTTP conformance assertions and
installed-wheel smoke passed. This host has no npm executable; the package
scripts ran directly with bundled Node and existing dependencies. No `npm ci`
execution is claimed.

Runtime identity is unchanged:
`warhammer40k-core-v2:runtime-tree-sha256-v1:699ca0e11f45466d9a7d0c16706fde3562d231d7856d7d70bbe2ef6b4a994e75`.
Commands, results, timing and evidence hashes are retained in the
[validation record](../data/source_audits/order94/validation.json). Initial
type-check and client-command corrections are recorded there separately from
the successful final gates. Audit-only corrections made during the behavioral
run did not change runtime, behavioral-test or contract inputs; the subsequent
full quality suite tested the corrected audit.

Independent review found one P2 issue: implementation statuses were included
in the source-observation fingerprint. They are now excluded from that identity
and still covered by the immutable whole-review pin. Regressions prove status
independence and rejection of a self-rehashed truncated observation. The reviewer
independently verified the correction and all 36 focused quality tests, then
approved the source/code changes with no remaining findings. Final publication
review independently verified all 20 gate-log hashes, aggregate JUnit/coverage
evidence and unchanged runtime inputs, and returned **APPROVE for publication**
with no remaining actionable findings before the first push.

PFINAL / CAUDIT-01 remains open after this source-only closure.
