# Order 97 / PEVIDENCE - clause evidence and remaining prerequisites

Order 97 expands the category-level negative audit into a source-block and
operative-requirement inventory. It records both assertions and reproducible
failures. It does not close CAUDIT-01 or certify Core Rules gameplay.

## Scope and authority

The reviewed implementation baseline is `8007555e`, after Orders 95 and 96.
The selected source body reproduces every row and block fingerprint in the
September 24 Order 84 inventory. The same public asset was retrieved for the
September 28 review. Its unversioned live body is not assigned changelog v946
as an App-data version. The 12 observed changelog versions are retained
separately, with an individual disposition for all 85 changes and six notes.

The complete ten-clause Order 94 Heroic Intervention observation replaces the
truncated Game Datamissions row. Both observations remain intact and separately
identified. All other selected rows retain their original source identities.
Source blocks include literal text, table cells and structured callouts; table
rendering metadata, examples and cross-references receive explicit dispositions.
Repeated locators and the untitled 24.37.01 row retain distinct row identities.

The historical Orders 84 and 95 negative audits remain unchanged. The September
10 review dispositions, C12-04 official-App Engaging-only resolution and C18-07
passenger engagement convention remain required PFINAL inputs. Order 87 random
Movement grouping and Order 92 random melee commitment are still qualified
owner conventions, not newly certified source semantics.

## Evidence model

`data/source_audits/order97/selected-sources.json` retains 345 selected rule/FAQ
rows, including all 59 FAQs. The category JSON files split operative requirements
from explicitly classified nonoperative blocks. Every requirement identifies its
source blocks, engine owner, exact assertion text and scope of proof, or an
explicit gap with an owned prerequisite. Negative observations do not masquerade
as passing gameplay regressions.

`runtime-reconciliation.json` compares every one of the 112 rule rows in the 52
retained runtime packages with the selected source. It preserves exact text,
transcription hashes, package hashes, metadata hashes, declared consumers and
separate load/execution statuses. Narrow excerpts cannot certify clauses they
omit. Superseded text remains recorded. Stale consumer IDs retain both their old
identity and an explicitly reviewed current owner until the source repair lands.

The offline validator checks source-block coverage, duplicate and missing IDs,
exact test assertions, the enclosing test AST, complete test modules, conftest and shared fixture dependencies,
runtime build identity, literal source text, and scheduled prerequisites. Its
reviewed identity must be deliberately updated after evidence changes; merely
renaming a test or rewriting a helper does not preserve its receipt. The generated
[clause report](ORDER_97_EVIDENCE_REPORT.md) is a navigable index; the JSON retains
exact assertion text. Assertion-bound means a concrete proof was reviewed, with
its stated qualifications. It does not imply universal semantic compliance.

New real-domain regressions close previously indirect evidence, including:

- accepted ground/Fly movement followed by a Heavy attack through LocalGameSession;
- two complete rounds of phase/turn ordering, source-loaded timing effects,
  invalid submissions, JSON restore, both viewers and deterministic replay;
- numeric and geometric boundaries, physical model ownership, keyword subjects,
  movement, targeting, attack completion and ability lifetimes;
- mixed normal and deferred mortal damage with actual nonempty applications.

Diagnostic probe modules under `tests/order97_gap_probes_*.py` reproduce the
negative observations committed beside the inventory. They are ordinary runnable
modules, not expected-failure tests or passing support claims. Their assertions
validate fixture preconditions. Repairs must replace those negative observations
with source-correct consumer regressions in the owning roadmap PR.

## Maintaining the reviewed inventory

After reviewing a changed clause or consumer, update its exact assertion and
qualification in the category JSON, reconcile affected runtime source rows, and
update the owning prerequisite. Refresh hashes only for reviewed evidence files.
The identity is `fingerprint(Inventory.model_validate(assemble_inventory()).model_dump())`
from the two Order 97 tool modules. Replace `REVIEW_SHA256` with that reviewed
value, generate the report with `uv run python -m tools.core_rules_order97_inventory`,
and run its `--check` form. Updating a hash does not establish semantic equivalence.
Do not modify the retained Orders 84 and 95 observations to describe later code.

## Architecture and delivery

This change adds offline audit data, tools, documentation and real-domain tests.
It changes no engine source, rule loader, supported content, decision shape,
viewer visibility policy or packaged runtime identity. The existing
[adapter decision contract](ADAPTER_DECISION_CONTRACT.md) covers every exercised
submission. No contract revision or generated runtime package change is required.
Historical source audits are preserved as evidence of their reviewed commits.

Scope was reviewed by invariant: discovered runtime defects are scheduled before
PFINAL, grouped by the shared owner that must repair them. This PR does not make
local gameplay fixes while claiming a completed global audit. New evidence tests
exercise the authoritative engine path and do not replace decision controllers.

There is no hot-path or algorithm change. Full-game performance remains deferred
under Order 32; these tests and diagnostic observations do not establish that
performance targets pass.

## Reproduction and final verification

```bash
uv run python -m tools.core_rules_order97_inventory --check
uv run python -m tests.order97_gap_probes_01_08
uv run python -m tests.order97_gap_probes_04_06
uv run python -m tests.order97_gap_probes_09_17
uv run python -m tests.order97_gap_probes_18_25
uv run python -m tests.order97_gap_probes_timing
uv run python -m tests.order97_gap_probes_keywords
```

Final delivery also requires the repository's complete behavioral coverage gate,
code-quality suite, both type checkers, lint/format/import checks, regenerated
eight-shard inventory, base-ref contract compatibility, runtime identity,
installed-wheel smoke, TypeScript contract client and live conformance checks.
The PR records their actual results and the independent review requested by the
owner. PFINAL remains a fresh audit after all newly scheduled prerequisites merge.
