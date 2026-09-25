# Order 86 / P01I: shared table-quarter dividers

## Invariant and source

Core 01.04.05 defines four equal rectangles outside two one-millimetre-wide
lines through the battlefield centre. Every rules-present scoring model's
base or rules hull must fit in the same rectangle for a whole-unit quarter
witness. An edge 0.01 inches from a centre line is inside the half-millimetre
divider and cannot establish occupancy.

The complete expanded clause was reviewed on the maintained
[Game Datamissions Core page](https://game-datamissions.com/11th/rules/core-rules#rule-01.04.05)
on September 25, 2026 at 15:36:30 UTC. It corroborates the September 24 Order 84
observation; no wording change or source conflict was found. The live page
exposes no App-data version. This is a non-affiliated maintained mirror,
not an official-App capture. The source package, transcription hash, observation
fingerprint and authority-registry entry pin that precise observation; the
retained official PDF hash remains historical provenance. Reproduce both JSON
artifacts with `uv run python tools/build_core_table_quarters_source.py --check`.
The historical Order 84 negative audit remains unchanged.

## Ownership and scope

The bug-class search found two duplicated quarter constructions, in primary
spatial evidence and secondary occupancy. Both now call `engine/table_quarters.py`,
which binds the reviewed divider width to `geometry/table_quarters.py` and
preserves these missions' independent six-inch centre exclusion. The geometry
query knows only typed models, board dimensions and divider width. It evaluates
analytic extrema of circles, rotated ellipses and rectangular hulls, avoiding
polygonal under-approximation at the narrow borders. Quarter rectangles include
their boundaries; any positive overlap with the divider is excluded. The
battlefield's outer boundary remains inclusive. Empty groups do not qualify.

Existing primary/secondary owners retain complete canonical rules-unit membership,
attached-component identity, physical presence and mission eligibility. They pass
the entire group to the shared query; adapters neither select a quarter nor
mutate scoring state. Primary scoring-commit restore reconstructs spatial
witnesses through the same producer. Secondary restore rebuilds occupancy from
its authenticated boundary state. Rehashed occupancy/witness claims cannot
replace the physical evidence. Order 79's separate objective-control-first
boundary remains intact.

There is no new player decision, submission, event field, witness schema or
viewer-visible payload. The existing Phase 11D adapter contract covers the
change; its Order 86 note records the corrected semantics. Runtime identity
and generated contract examples are refreshed to prevent old runtime saves
from being treated as current authority. No compatibility shim is added.

## Validation and review

The pre-fix regression run reproduced eight incorrect border acceptances.
Focused coverage includes both divider axes and sides, exact tangency, overlap,
clearance, empty and multi-quarter groups, rotated base/hull geometry, board
edges, centre exclusion, attached Leader membership, source corruption,
primary/secondary scoring through the facade, both viewers, persistence and
exact replay. Forged and rehashed primary and secondary quarter evidence is
checked against the physical reconstruction owners.

Matched base/head five-model witness diagnostics and the fixed component budget
are retained in [performance evidence](performance/order86/README.md). These are
component costs only. Complete-game performance and PFINAL remain uncertified.

Final validation passed all 9,339 behavioral cases with 85.20% branch-inclusive
coverage and all 682 code-quality cases. The first behavioral run exposed an
outdated source-package inventory count; the assertion now includes the new
package. The final pytest process passed every case but could not reopen its
SQLite coverage database for reporting. The saved database passed its integrity
check, and standalone coverage text and JSON reports from that same data passed
the unchanged 85% threshold. The raw nonzero process result and recovery are
explicit in [validation.json](performance/order86/validation.json).

Ruff, formatting, Mypy, Pyright, all 11 import contracts, pre-commit, source and
runtime artifact checks, exact-base contract compatibility, installed-wheel
smoke, generated TypeScript client checks, five TypeScript unit tests, and the
342-assertion conformance scenario passed. The eight-shard inventory was
regenerated from the complete successful behavioral JUnit profile and passes
the required fail-closed check. npm is absent on this host; equivalent installed
Node entry points executed the TypeScript commands.

Independent implementation review found no engine issue. Artifact review found
two measurements initially written into historical Order 82 paths. Those files
were restored exactly, and the correct current workloads were rerun into the
active Order 83 paths. The full quality gate also caught missing static package
inventory/classification entries and stale Order 73–75 report identities; those
inventories are updated and the workloads remeasured without competing test
workers. Historical baselines and budgets remain unchanged.

Final independent review approved publication with no remaining findings. The
reviewer verified all successful JUnit cases, the quality results and retained
log hashes, same-database coverage recovery, all 23 refreshed inherited reports,
source provenance, generated contracts and shard inventory.
