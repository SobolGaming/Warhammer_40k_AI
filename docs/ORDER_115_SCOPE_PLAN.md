# Order 115 / P02K: absent Movement

The selected Order 97 obligation `02.02-obligation-01` says a model whose
Movement is `-` may be set up on the battlefield but otherwise cannot be moved.
The exact retained text is block 2 of `rule:02:02.02:1` in
`data/source_audits/order97/selected-sources.json`; its complete retained capture
and provenance remain in the immutable Order 97 inventory. This is an
implementation repair, with no new live-source or version claim. Advance's
separate distance remains the existing source-backed `09.06` authority.

The violated invariant was the loss of absent-M identity when Movement became a
numeric distance: Advance and fixed-distance reactions could move a dash model.
The same omission permitted free rotations and return paths, so an endpoint-only
check or a zero distance cap alone would be incomplete.

`model_movement_path_context` owns the per-model permission and fixes the pose of
source-dash and replacement-dash models throughout the full path. Numeric zero
retains its numeric meaning and can use an Advance roll or explicit move distance.
The existing ordinary budget owner also keeps dash-M at zero before adding any
Advance or movement bonus. Attached components use their own model descriptors.

Ordinary Normal/Advance/Fall Back, reactive/Surge, Scout, Charge and Fight paths
all consume the same permission. The pure geometry context carries the fixed-pose
constraint through path validation and serialized reachability queries. Mandatory
endpoint proofs recognize a fixed pose as their complete feasible set. Live and
historical Charge/Fight/reactive context reconstruction use the same owner.
Starting-pose, distance, terrain, collision, coherency and engagement checks remain
active. Explicit deployment, reserve ingress, disembark and other setup placement
retain their separate source permissions.

No new decision family, proposal kind or viewer policy is introduced. Existing
movement proposals return the typed `model_pose_fixed` diagnostic on attempted
displacement and retain their retry path. Zero-displacement paths retain the
model's pose and can preserve a mixed unit's complete witnessed movement.
Existing runtime identity binds saves, forks and replay to this release.

Apply `docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`. Prioritize the complete
playable behavior in this order. Block on incorrect rules, normal legal-play
failures, engine-generated valid-state save/load/replay failures, and explicitly
required trust-boundary failures. For each blocker provide the reproduced entry
path, impact, normal reachability and violated acceptance requirement. Queue
coordinated hand-edited-history hardening separately when no necessary supported
input boundary or normal path is demonstrated. Keep scope within this order;
expansion requires an explicit decision. Preserve positive controls, regression
tests, source truthfulness and every required local/remote exact-head gate.

The serial current-runtime smoke is the performance assessment for this bounded
rule repair. Historical receipts and their Git pins remain unchanged; this order
does not claim complete-game performance or Core certification. Order 116 is
unstarted. Maintain the roadmap's implementation prose for each subsequent order.

The inherited performance selectors classify every geometry owner as search.
The owner's quiet-smoke direction is recorded only for this exact-base repair in
`docs/performance/policy-v3/order115-rule-semantics.json`. Exact file and AST-owner
hashes authenticate the fixed-pose constraint and its singleton reachability
consequence. Mandatory operation mappings and all live/historical gates remain;
any changed owner bytes invalidate that scoped selection. Review must assess
this classification independently. No numerical budget exception is introduced.
