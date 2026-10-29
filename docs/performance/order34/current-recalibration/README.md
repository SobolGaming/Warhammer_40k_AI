# Current unrestricted lookup calibration (2026-10-21)

This is an owner-approved budget recalibration at accepted cumulative commit
`923e24c9d6cea9668bec488e79b717173851c91b`. It changes only unrestricted
`rules_unit_view_by_id`: **240 -> 270**. All other cases, metrics, cold geometry
ceilings, provisional timing values, coverage minimum85 and qualification
600-second cap/500-second warning remain unchanged.

The canonical `scripts/measure_action_restriction_live.py::live_sample` workload
is unchanged: four units, ten physical models,32 effects, six live decisions,
Shooting through Charge completion into Fight. Setup is excluded from lookup
counts and live timing. The separate pre-existing cold geometry metric still
includes setup. Current instrumented lookup count is246; cold geometry is2 setup
plus12 live =14, below the unchanged26 ceiling. Live selection/solver multiplicity
does not expand: three shooting eligibility calls, zero charging eligibility calls
reported in this completion path (limit2),27 LOS calls (limit72), zero `decide_full`.

The rounded ceiling270 leaves24 calls/9.76% headroom. The original public PR438
measurement was219 with ceiling240 (21/9.59%); no foundational formula is claimed.
Public provenance is commit `9699f8f8aaebc1a452b11eafda9fe14f1cddd6b9`, merged as
`51952e49c2b360f1dacffc03d53916324a1e9253`. Original reports,219 measurement and240
records remain untouched. This new calibration supersedes only the current
unrestricted lookup ceiling.

`lookup-callers.json` accounts for all246 calls in the live profiler interval.
The largest caller is `_matching_generic_attack_effects` (78), which authenticates
the physical attacker/target rules-unit and model ownership for typed effect
queries. Other repeated callers include enemy placed-unit enumeration12, charge
target restriction12, movement locks11, action shooting restriction11 and physical
weapon inventory10. These are bounded correctness queries in the six-decision
path. Nine calls come from `_firing_deck_phase_available`, whose explicit current
Shooting-phase and controlling-player check prevents borrowing cargo weapons in
reaction shooting. This is legitimate additional correctness work in current
source; it does **not** prove that this guard caused exactly six calls or explain
every call of the historical219-to246 delta. No obvious accidental explosion was
found. This limited attribution is not a full historical performance investigation.

`measurements.json` retains seven fresh serial uninstrumented samples and one
separate profiled count sample on Linux WSL2, Python3.14.5, AMD Threadripper3970X.
No competing test workers were present. Mean live time is0.2620928063 seconds;
maximum0.2940313740. The instrumented0.7425692660 seconds is not timing evidence.
The uninstrumented values exceed old provisional0.2/0.25 values on different
reference hardware; timing remains explicitly unenforced and unchanged. Neither
the lookup breach nor this cross-host observation establishes a wall-time
regression. No historical-to-current timing ratio or full-game claim is made.

The legacy reporting CLI completes its workload but fails on Linux at its
macOS-only `sysctl` metadata query. An external Linux metadata harness imports
and calls the canonical workload unchanged; neither driver nor runtime is edited.

The existing budget test remains byte-for-byte unchanged as a function. A new
quality regression feeds that exact test an otherwise real workload result with
only the lookup count changed:270 passes and271 raises the metric-specific
assertion. The original240 ceiling fails246; attached and retained cases pass
before the change. Full-quality receipts and candidate/runtime/input preservation
hashes are delivered separately in the qualification packet.

Gameplay evidence may be reused only under exact byte/import preservation of
runtime source, selected source artifacts, fixtures, lock and behavioral test
inventory. This candidate adds no runtime, source, import selection, gameplay or
behavioral-test change. Existing gameplay evidence keeps its original scope and
limitations; no new coverage or complete behavioral run is claimed. Independent
review of this separate cumulative candidate remains pending.

The historical inventory also pins the original budget JSON itself. The only
historical-reader change routes that exact path through the existing
`historical_input_bytes` resolver at unchanged revision
`7f45d87d3094c76beb1be58e0cabb721dec21053`. Its unchanged inventory SHA and budget
SHA `5178d85cec2077035e405a95ba59fa7f68d377bbcdd51a2cb1fef3a475ac06cc`
still authenticate original240. Every other report continues checking its live
pinned bytes. The current270 report is rejected as historical; corrupted old
budget bytes and an unrelated report's live corruption are both rejected.
No historical inventory, revision, measurement, source input or general proof
activation changes. This single-path historical boundary is necessary to let an
approved current budget coexist with immutable historical claims.

Concurrency audit: B2 pytest ran20:10:27.953–20:12:15.994UTC, after the
measurement outer interval20:08:03.129–20:08:51.871UTC and before the first full
quality launch20:15:11.639UTC. Its interruption receipt is retained separately.
A0.2008-second B2 static-binding step ended around20:08:08UTC and overlaps the
outer measurement harness interval. Per-sample wall-clock timestamps were not
logged, so these timings carry possible brief static contention and make no
exclusive-host claim. Counts remain deterministic; no timing regression ratio or
automatic timing rerun is justified by this overlap.
