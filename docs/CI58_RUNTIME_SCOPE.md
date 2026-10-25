# CI58 manifest reconstruction scope

This local, unpublished follow-up starts from the independently reviewed CI57 commit
9fe876d26c79c20613916b661640cd662ea08db7. It reduces repeated execution-record scans
inside generated runtime-manifest construction. It adds no rules, faction support,
public API, schema, source observation, or cross-call cache.

## Ownership and invariants

tools/generate_faction_content_scaffold.py owns the generated manifest. Each call
to generated_runtime_content_rows groups the current module's execution-record
tuple by owner, exact rule key and execution ID. Read-only mappings contain tuples
of the original frozen records and remain local to that invocation. The existing
execution tuple and source-package identity initialize at module import; rebuilding
this index is not physical-source authentication.

Owner keys retain a nullable detachment ID. Rule keys retain faction, nullable
detachment, nullable rule ID and coverage-kind value. Execution IDs preserve record
multiplicity; source IDs remain sorted sets. Executable rule selection retains
only generic-IR and named-handler statuses, while source selection includes blocked
records. Semantic status retains its original requested-ID set membership and
matched-record-count comparison against the raw requested tuple length. Empty,
unknown and duplicate cases keep their existing behavior. Pilot matching remains
a substring search.

The original family order, input row order, eligibility filters and typed row
constructors remain. Faction, detachment, enhancement and stratagem source calls
retain their order and count. Phase17E/F fresh observations, expected-record
reconstruction, package validation, per-payload JSON validation, source/dependency
integrity, lifecycle, cancellation and causal restore/replay checks are unchanged.
An exception publishes no partial manifest or retained index.

## Validation and measurement boundary

The existing Phase17G test owner retains all previous cases and assertions. Five
additional cases compare full inventory scans, reordered and duplicated records,
all semantic statuses, unknown IDs, changed source/status under identical keys,
read-only ownership, successive tuple replacement and source failure/recovery.

A separate native capture compares all ordered manifest fields and complete
Phase17E/F public payload bytes. Real permission, characteristic and own-model
tests retain their native checkpoint/restore/replay assertions. Measurements use
fresh processes with the same pinned environment, inputs, four-worker setting and
strict pytest defaults; source proof reads occur before each workload. They do not
establish OS-cold conditions. Three before/after runs and a serial checkpoint pair
report whole invocation and separate preproof, CLI and postproof durations. All
attempts, including failures, remain evidence. The whole worker has the unchanged
500-second warning and 600-second deadline, including proof and journal work;
cancelled or incomplete evidence cannot pass.

The saved CI56 profile is attribution evidence, not an unprofiled baseline.
Its 7.111 seconds in manifest construction out of 73.347 seconds is an upper bound
for eliminating that entire component in that profiled case, not a predicted
speedup. A local material-gain description requires at least five percent lower
median whole time with separated repeat ranges and corroborating CLI/node
direction; this reporting criterion is not a new CI gate or statistical proof.
Host load, run order and preproof variation remain limitations. Measurements and
their results are retained separately so this source description does not relabel
earlier runs or change after candidate freeze.

These local checks do not certify the full quality or behavior suites, coverage,
the official performance protocol, under-ten-minute CI, readiness or publication.
The CI57 known transport fixture failure remains queued outside this scope.
CI57's Fight-on-Death reachability limitation remains: an engine-generated snapshot
from an admitted synthetic fixture does not prove ordinary pregame/catalog reachability.
