# External-contract proposal source reuse comparison

This new performance family measures the unchanged existing pytest workload
`tests/code_quality/test_phase18m_conformance_boundary.py::test_external_contract_write_mode_removes_orphan_generated_fixture`.
Its module is both the executable workload driver (invoked through pytest) and the
retained workload reference. That reference is source, not a historical timing
report. There is no fabricated historical baseline measurement for this family.

The registered case is `orphan-write-independent-check`, with three actual-PR-base
and three candidate samples on the same declared four-logical-CPU Linux host,
Python 3.14.5 and identical dependency lock. Run one pytest process at a time with
`-n 0 --no-cov`, fresh output roots, no profiler and no inherited instrumentation.
Predeclare order base/head, head/base, base/head. Each sample is the complete
original pytest process envelope, including collection and setup. Retain its
separate setup/call/teardown observations through pytest built-in
`--durations=0 --durations-min=0` output on both arms; the opt-in timing plugin
stays disabled. Both original child processes and the
checker's nested independent regeneration must remain fresh; no assertion,
negative control, serialization or replay validation is removed.

Register `current-change-relative-v1` without modifying its policy thresholds:
candidate mean <=1.25 times baseline mean +0.05 seconds, and candidate maximum
<=1.5 times baseline maximum +0.10 seconds. Those are regression gates, not proof
of useful improvement. Report all paired deltas, cold/warm scanner work and memory
separately; no full-pipeline speed claim follows from passing this family.

A companion standard-library-only source experiment uses three base/head batch
pairs, each process independently measuring a cold lookup, a six-read sequence
and a three-read sequence, with a fresh index for each scenario. Timed samples
exclude parser instrumentation; separate real-parser counts prove reuse.
Fresh source inventory and byte equality remain mandatory. OS page-cache state
is uncontrolled and must not be described as cold merely because a process is
fresh. The scanner's exact token oracle remains independent.

The proposed later controller has a 55-minute maximum and enclosing job a
60-minute maximum. Six complete original pytest invocations each have a
420-second allocation; six source batches each have a 60-second allocation.
Cleanup fits inside each cap. Mandatory exact command/source/owned-process
preflights, unique outputs, retained failures and stop-on-integrity/failure
semantics precede measurement. This specification does not launch a campaign or
authorize a workflow. The exact controller/workflow and frozen candidate require
independent review before execution.

Current detailed comparison output is pending. The diff-bound assessment selects
the family and reserves a new evidence path, but the complete policy command must
fail until real matched evidence and the required current-runtime smoke exist.
Do not create synthetic passing samples, weaken policy or overwrite historical
records to make that gate pass.

The concrete controller and label-gated workflow are now drafted for independent
review. The controller only emits raw samples, exact commands, input bindings,
resource reports, generated-tree comparisons and completion/failure receipts.
It does not manufacture or automatically approve a policy report. After an
approved successful run, a separately reviewable ingestion step must construct
the strict comparison report from those original receipts, and the unchanged
regression gates and required current smoke still apply.

`tool-input-roles-v1` is supported only for this exact family/workload. The actual
base and head bytes bind two treatment files, individually named control-plane
files, the identical external harness, and all other selected inputs as equal
common files. The source corpus and full copied contracts tree include ignored
files visible to the actual workload. A report's measured head SHA is only an
untrusted Git locator: it must be an ancestor of the current checkout and its
selected Git blobs must equal independently read current bytes. This permits an
evidence-only descendant commit without accepting stale implementation bytes.
No historical applicability substitution is allowed for this family.
