# Physical-history save/load prerequisite

User approved this separate prerequisite PR on 10 October 2026 at 15:22 UTC,
followed by finishing D06. Exact base is
`7debdbd4182c1ee2703a367f2966dbdac685f18e` (tree
`e964044f5fde51ea7e843e7d39a9a12c82e8e74f`). D06's isolated uncommitted
distance predicate and evidence remain separate.

## Reproduced defect and invariant

Canonical Core transport/character and predeclared analytical terrain, public
setup/deployment, real player-b round-one Tactical Disembark/carrier Advance,
and round-two pending passenger Normal Move produce valid state that fails
JSON restore during historical Command Battle-shock candidate reconstruction.
No state, controller, dice or history injection is required. Unchanged baseline
and transferred D06 produced identical payload bytes (SHA-256
`2208b190df5659f2c634f8e1343a7659124f079658b72c6f3ee4727ebef40b0b`).
The missing authority is the passenger's earlier embarked state before a later
physical mutation, despite retained engine-recorded scoring checkpoints.

Historical physical presence, pose and wounds must come from authenticated
pre-mutation authority and ordered transitions, with complete physical model
inventory, ownership and terminal-state consistency. Current state cannot
invent a missing earlier mutated state. This save/load failure blocks the
required second-player persistence/fork/replay/continuation path.

## Shared implementation boundary

`primary_mission_boundary_physical_authority` now accepts existing authenticated
preceding scoring-commit checkpoints in its shared ordered reconstruction.
Its two private callers receive their authoritative `GameState`. Existing
mission-boundary reconstruction, row comparison, transition-decision checks,
missing-anchor rejection, forward-anchor stop-before-mutation and final-state
binding remain intact. Existing scoring checkpoint authentication is extracted
without changing its body into `primary_scoring_physical_anchor` to respect the
1,500-line owner budget. Occurrence, retained lifecycle/evidence/OC record,
checkpoint and OC hashes, player/game/round/phase/battlefield and inventory
checks remain required.

All shared physical-history consumers retain the same public entry point.
The static consumer inventory is impact analysis, not evidence of additional
defects. No new gameplay rule, fabricated history, fallback, compatibility
shim, broader integrity hardening or D06 distance change is included.
Emergency Disembark, MONSTER floors, Heavy, alternate profiles, Epic Challenge,
grouped attacks, Save-reroll and other approved repairs remain separate.
FRAME native applicability remains unproven.

## Bounded acceptance and retained source

- Demonstrate the original normal-path baseline failure and corrected first/
  second-player ground/elevation progression through public decisions.
- Pending and completed movement must survive engine-generated JSON restore,
  independent forks, all principal role views/events, source-bound exact replay,
  atomic malformed move rejection, legal retry and continuation into shooting.
- Preserve legal scoring, authenticated movement/destruction/return-on-death,
  historical position and attached ownership/inventory controls, plus existing
  missing-checkpoint, forged-pose and coordinated-erasure assertions. The latter
  remain preserved regressions, not authorization for new manual-history hardening.
- Preserve original test bodies/assertions, source archives and all budgets.
  `data/source_audits/physical-history-restore/provenance.json` pins original
  owner and existing Command regression source. The new regressions live with
  existing off-battlefield Command history tests; no original body is replaced.
  The existing fail-closed historical resolver binds this one original Order97
  file pin to its exact archived bytes; the reviewed inventory and original
  assertions remain unchanged while current regressions execute current source.
  Required current-inventory regeneration changes only this test file's byte
  count and two file hashes; source observations, audit findings and assertion
  bodies remain unchanged. The prior inventory and exact three-field comparison
  are preserved in the review evidence.
- Runtime identity changes in the existing versioned server/recovery contract.
  Preserve its exact runtime and source-binding guards without a migration shim.
  The local-session boundary retains its existing rules/source identity checks;
  verify the untouched original local save directly and report actual behavior,
  alongside current-source session round trips, without rewriting archived saves.
- The explicit preceding-anchor branch is a correctness repair using existing
  checkpoint/transition algorithms and serializers. Exact-base assessment and
  quiet serial current-runtime smoke are required; deliberate performance work
  or a demonstrated serious regression would require matched comparisons.
  Operation mapping and classification require independent exact-source review.

## Delivery and evidence limits

No focused run, prior host, failed or partial cohort is a final gate. Preserve
all immutable failed receipts. Complete source/type/import/contract/client/wheel,
pin/inventory, quiet performance/smoke and whole quality prerequisites; then all
16 original polygon cases in isolated serial branch-coverage processes. Parent
explicit RELEASE precedes the remaining 32-worker behavioral coverage gate and
reviewer probes. Complete passing current-cohort timings supply twelve shards;
run whole quality after profile metadata. Parent arranges fresh independent
coding/rules reviews and same-reviewer exact-final metadata renewal. Canonical
full-source/acceptance/policy/HEAD/TREE/BASE/Git-blob/archive identities bind final
checks. Both clean final reviews, required gates and parent readiness precede
draft publication; native CI/protected human merge and fetched main verification
follow. D06 resumes on verified new main as a separate PR. No nested agents or
predecessor/main CI watcher. Requested Sol6.1 High/fast remains the user direction;
unavailable runtime/model/speed attestation is not claimed.

## Required scoped policy

Apply `docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`. Prioritize the complete
playable behavior in this order. Block on incorrect rules, normal legal-play
failures, engine-generated valid-state save/load/replay failures, and explicitly
required trust-boundary failures. For each blocker provide the reproduced entry
path, impact, normal reachability and violated acceptance requirement. Queue
coordinated hand-edited-history hardening separately when no necessary supported
input boundary or normal path is demonstrated. Keep scope within this order;
expansion requires an explicit decision. Preserve positive controls, regression
tests, source truthfulness and every required local/remote exact-head gate.
