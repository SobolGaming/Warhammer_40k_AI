# Rules-engine performance policy

Policy ID: `rules-engine-performance-v2`, owner direction received 2026-09-08.

## Order 32 owner-directed deferral

Later in the same task on 2026-09-08, the owner explicitly chose to use the
correct continuous/planar formula and defer efficiency work until a complete
head-to-head headless game can be measured. This supersedes Order 32's proposed
component timing thresholds, comparative timing certification, and performance
CI gate as publication/merge-readiness prerequisites. It does not change their
measured results into passes or establish full-game performance certification.
The 60-second mean / 300-second observed maximum full-game objectives remain
recorded for that future assessment. No training system or new game driver is
authorized by this deferral.

Keep the baseline, difficult scenarios, timeouts, and reproducible diagnostic
command. Correctness, complete validation, shared engine authority, deterministic
records, bounded caches and stale-result rejection remain required now. The
general policy below remains the standing guidance for subsequent assessment;
apply this explicit deferral to Order 32.

The owner subsequently approved narrowly scoped exact-solver repairs needed to
complete ordinary gameplay tests and CI. This permits mathematically justified
termination proofs for the observed stalls; it does not resume broader efficiency
work or allow timeouts to become invented visibility answers.

Performance is part of delivery correctness. The supported full-game workload
must achieve an arithmetic mean **below 60 seconds**, with **no measured game
above 300 seconds** on declared reference hardware. Retain incomplete games,
timeouts, and threshold violations as failures. A finite sample cannot prove a
universal worst-case bound. Semantic correctness and deterministic replay remain
separate mandatory gates; interactive and headless execution share authority.

Assess changes to hot paths, algorithms, data structures, caches, and gameplay
orchestration. Extend the existing benchmark/profiling infrastructure; choose
optimizations from measured evidence. Current rules-engine profiling and
optimization are authorized independently of later AI/training work.

Before changing an implementation, version the benchmark workload and measure
the base. Repeat identical base/head measurements on the same machine and
dependency lock. Record CPU model/allocation, memory, OS, interpreter and library
versions, roster/model counts, terrain shapes/complexity, seeds, decision policy,
concurrency, setup/preparation/query timing boundaries, and script/config hashes.
Until production hardware is selected, label the available host provisional.
Run timing samples without coverage, profiler/debug instrumentation, or competing
test workers. Profile work counts and memory separately. Report sample count,
mean, median, percentiles, maximum, completion rate and declared throughput.

Commit numeric component/slice budgets and regression thresholds, with the
measurement variability and workload rationale that selected them. Tie component
budgets to observed calls per phase/game and the 60-second objective; label
extrapolations as estimates. An incorrect base is a cost comparison, never a
correctness oracle. Do not silently change thresholds or discard hard scenarios.

Every affected PR needs a fast meaningful CI gate based on stable work metrics
and/or calibrated timing comparisons, plus a reproducible fuller command and
machine-readable results. Include the fast gate in an appropriate required
aggregate. Missing or skipped evidence is incomplete. A PR with an unmet required
budget is not ready for merge. Independent review assesses performance as well
as semantics; report correctness, performance and CI status separately.

Caches must be bounded and cover all geometry, presence, keyword, terrain and
rules-policy inputs. Demonstrate cached/uncached agreement, invalidation after
movement, casualty, retained-presence cleanup and restoration, and isolation
across independent games. Timing/profiling values stay outside deterministic
authoritative state and replay records. Timeouts and unresolved calculations
must not invent rules answers or bypass validation.

Inspect supported headless capability before claiming full-game certification.
Reuse a legal existing driver or recorded workload. Measure per-game initialization
through normal completion, including legal-action generation, policy decisions,
engine execution and normal replay/log output; report worker startup separately.
Separate policy/search and engine costs without removing either from end-to-end
totals. If complete games are not supported, deliver component/slice gates and
record full-game certification and its missing prerequisites as outstanding.

Order 32 preimplementation evidence and remaining acceptance obligations are in
`ORDER_32_VISIBILITY_REVIEW.md` and `order32/`. A diagnostic baseline or prototype
is not a passing delivery gate.
