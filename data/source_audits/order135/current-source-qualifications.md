# Order135 retained current-source and consumer refinement

Same sole independent gpt-6.1-sol / High coding reviewer. Static text inspection and source hashing only. No subagents, tests, imports, runtime probes, benchmarks or repository changes. No reproduced blocker, CLEAN or certification claim. HEAD/base remains `70b0c0b43774f81d67753b0e3f830b38f1b178ff`, tree `9bfe078571d851065730f716ca990d87e7a11621`; Git status was empty at inspection. Earlier three static reports remain immutable.

## Authenticated current source observations

`retained-current-source-01.json` authenticates as SHA256 `a473e270f76d9556c25e68477abf040bc8a7f1a6c21c1fd9d9a0fa960edd627f`. It retains the complete current Core capture (26 categories including00, 64 FAQs, stratagems, tables and callouts) and 13 changelog versions. Its authority is the accepted GDM mirror observed `2026-10-01T12:04:31.127429+00:00`; this does not independently certify an official App v963 body export. Raw Shock captures and their literal extractions are separately retained. The selected old packet and canonical archives must remain unchanged.

Comparing its 350 row IDs/fingerprints against the 345 selected source observations in `static-current-inventory-01.json` finds four changed rows and five additions, with no further row fingerprint changes:

| Row | Old SHA256 | Current SHA256 |
| --- | --- | --- |
| rule:15:15.09:1 | `7f0d6aae4999b69197d7e2d7d2007fad2a78a9c23e9a069c304e5e18756c5ae8` | `7b8751d5410514a1e93385df76d0f02f15ca36797e8ade90b0ee5ddd168ff92a` |
| rule:15:15.11:1 | `df759b591cf0a01391ac884dd29c436a8030346e655da7dae56e1210da9ae2a0` | `e407ce0a8f58f5ceeb5eb88a9553346f97ac3801ec1d6fc3880e1c2a513c629c` |
| rule:16:16.01:1 | `9ace4fc09f4a890c9ed17ace0ba98e9863db6dff5f73eb55e767db04805c573d` | `19b3cd2eaa9f36060d8eff197121cfc0989562ece20f01ec1c31970796d76241` |
| rule:18:18.07:1 | `e025777aff6de7c7295be2f0c857794148f2fdbdafc28f5f1df304655e7a2c41` | `1747a6ed39b7eeb9a7e5d45284cddea38c3148e9bbeeab30fadd00fc475dbd93` |

| Added complete FAQ | Fingerprint | Required current disposition |
| --- | --- | --- |
| db020803-7564-45c9-a6d4-e4cdf463da32 | `8352b49b9fbfaceb630ac21dc45eac4d9fdf112bd15de3e50ec2f0fbd30ca36e` | A unit can control more than one objective. |
| 8c51d370-70b2-46c7-abaa-228b55c830c3 | `cda9f83e49d0006eef29aeb0e17f388472db9fa391be2ea4a96e6ce4850e80a6` | The same model's OC contributes to each objective within range. |
| f1507145-5606-474c-ba71-f5c92f2d6faf | `f1569a6a16420f52ff3a4cc89c61762db7467cba6bdc320c8a4e3fa8ceec239f` | Effects remain active at the stated end boundary, including +1 OC through turn end; absent next turn. Already separately selected in the Shock duration FAQ. |
| 9638115f-b94b-4d05-ba62-df9fba2805ac | `1c43f713b930f8f51c7d429991f40174c22eb30bbf4bd56773993b4a8e319cd8` | Outgoing LOS uses only in-bounds parts; incoming LOS can use any part. |
| 3da822cb-4a7c-44d2-8a9d-b867b4c4aed8 | `cbf7e42f41f0d4cce05a0f084c6982e8899da06ac0a71c7339ad6845ef0acc47` | Unit/model-in-unit targets apply to the attached unit; a single-model target remains single-model. |

15.09 and18.07 require current Snap/Shock supersession mappings already specified in report01. 16.01 changed source formatting/callout placement rather than an identified change to the21 gameplay blocks; retain the separate callout observation. The newer15.11 mirror still has visibly incomplete Heroic mode transcription in its stratagem data (fragments without their full mode labels). Preserve the accepted Order94 full user transcription and explicit mirror discrepancy. Newer capture time alone does not downgrade the selected complete authority.

Objective overlap is a definition with an existing independent-per-objective owner. A narrow explicit overlapping-objectives semantic assertion, together with the existing Order109 real boundary/mission consumer family, is sufficient inventory architecture; there is no requirement to duplicate a whole facade scenario merely to acquire a facade-role label. Attached unit/model scope likewise needs explicit clause bindings to actual scope owners and the existing Order118/unit-ability facade consumers. Existing behavior should be reconciled before inferring missing implementation.

The current v963 changelog contains all10 Chinese-only translation rows and three GDM preset deployment substitutions. Record English-unchanged localization dispositions explicitly. Record each Layout A/B/C old/new deployment comparison separately and distinguish selected external GDM preset metadata from separately sourced Event Companion runtime layouts. These source dispositions are not assumed Core gameplay defects.

## Visibility refinement: body geometry is omitted, and outgoing bounds are absent

This corrects the shorthand 'whole-model prism' in earlier reports. `src/warhammer40k_core/engine/battlefield_state.py::geometry_model_at_pose` (line1269) retains the support base and separate `body_parts`. `engine/shooting_selection_range.py::geometry_models_for_unit_placement` and `::attacker_geometry_models` return those actual geometry models. `engine/shooting_targets.py` supplies them to `core/visibility.py::TerrainVisibilityContext`.

However, `geometry/visibility_shapes.py::model_visibility_prism` uses only `model.base`, `model.pose` and `model.volume.height`. It does not consume `body_parts`. `core/visibility.py` constructs this single support-base extrusion for observer/target resolution (lines460-461), source-group obscuring (396-397), broad vertical bounds (485-488), and other-model obstacles (684). Thus baseline LOS omits declared physical body parts both as endpoints and blockers. `geometry/physical_model.py::physical_prisms` already provides support-base plus all body prisms for other physical owners.

Separately, the actual `TerrainVisibilityContext`/payload has no battlefield bounds or clipped-observer geometry. The baseline cannot express the outgoing-only battlefield-edge restriction. Model payload context fingerprints retain body geometry, so omission of body parts from the separate shooting model-blocker revision string is not, by itself, a reproduced cache-authentication failure. Do not enlarge this finding into speculative cache hardening.

Concrete policy-relevant concern: a normally admitted physical model can be visible by a body part while its support-base extrusion is hidden, so baseline target availability can be wrong. Correct any-part LOS and new outgoing edge clipping together for those admitted body parts. A support-base-only test cannot prove the edge FAQ because it can reject outgoing body-only visibility for the wrong reason.

### Native legal entry candidate, still unexecuted

`tests/integration/test_order128_setup_overhang.py::test_catalog_strategic_reserve_whole_body_fit_and_impossible_exception[edge-band-impossible]` and `tests/order128_helpers.py::reserve_session` are the actual native entry family. The helper starts a loaded `LocalGameSession`, declares reserve formations and advances normal decisions to battle round2 ingress. The existing parameterized submission accepts an8-inch circular physical body with a120mm support base at `(5, 2.5)` on a60x44 battlefield, for the no-enemy case. Body geometry is configured before session start as an explicitly synthetic, source-linked analytical-cylinder measurement, not presented as an official faction miniature measurement.

At that pose the support base is wholly on the battlefield while the physical body reaches y=-1.5. Whole-body fit is impossible under a qualifying6-inch reserve edge band because the120mm base permits a center no farther than approximately3.638 from the edge, whereas the8-inch body needs4. `engine/reserve_setup_geometry.py::append_reserve_body_violations` admits the impossible-fit exception through `model_fits_regions`; it still rejects avoidable overhang, enemy-distance violations and invalid support-base placement. This is normal configured native placement rather than a post-hoc fabricated battlefield pose.

After explicit RELEASE, prove the decisive geometry through real shooting target/declaration consumers: incoming visibility to an exposed physical part, outgoing rejection when all clear rays originate outside the battlefield, a positive outgoing in-bounds-body control, and wholly-in-bounds controls. Use terrain declared in setup, continue the actual phase/turn lifecycle, and respect arrival-turn activity restrictions; do not fabricate a faction granting ability or replace live state. Verify parameterized pending/completed checkpoints, atomic invalid submission, viewer roles, restore/fork and exact replay. For each claimed blocker record exact head/tree, full normal reachability and any unproven steps. At this static checkpoint the decisive shooting geometry and outcome remain unproven.

## Generic expiry concern narrowed by actual late consumers

`engine/turn_end_boundary.py::prepare_turn_end_boundary` expires generic TURN_END persisting effects after recording turn control but before `engine/battle_round_flow.py` offers mission turn-end rules (lines352 then380). Shock's separate expiry occurs only after END_TURN completion (line395). These two owners must not be conflated.

Actual late mission consumers narrow the possible impact: `mission_turn_end_sequencing.py` supplies the retained TURN_END `ObjectiveControlRecord`; `primary_mission_action_resolution.py::resolve_primary_mission_action_at_turn_end` captures completion with that record. `primary_mission_action_lifecycle_policy.py::evaluate_primary_mission_action_completion_evidence` evaluates objective-related effects using frozen boundary unit-control authority. Surveil is unconditional at completion, and Vanguard's completion predicate uses actor/enemy terrain presence, not the fresh OC values also included in its terrain evidence inventory. Therefore the inspected normal late consumers do not demonstrate the +1OC example failing due to generic early expiry.

Keep a precise lifetime sequencing qualification until a real admitted late consumer is shown to use the expiring effect live. Do not classify mere early inventory removal as a reproduced legal-play blocker; do not invent a future generic effect provider. Existing direct duration/consumer assertions plus actual boundary pause/restore/replay families remain necessary to map the FAQ. Phase-end effects correctly finish before the separate turn-end boundary, and specialized Shock proof is limited to Shock.

## Review boundary

The all-category1078-requirement static inventory,14 historical assertion dispositions and34 absent-old-link mappings remain as recorded in `coding-review-current-dispositions-02.md`. They are not1078 runtime passes. September10, all older operative updates, v931/v946, C12-04/C18-07, Heavy accepted movement history, Normal Move occurrence, control-first and Action interruption retain their earlier concrete evidence/qualifications. Original tests, assertions, source archives, pins and authority conventions remain preserved.

Apply the clarified user Core scope: missing faction in-turn deployment granting ability alone is not a Core blocker; Order134 conditional restrictions can use their conditional checkpoint and existing real consumer/persistence/replay evidence. Do not rewrite historical Order134 qualifications. Final certification still requires a stable canonical current packet, prerequisite completion, explicit polygon RELEASE and same-reviewer exact-head review. No runtime gate was bypassed here.
