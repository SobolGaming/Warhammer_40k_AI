# Order 100 / P17B — based FRAME measurement

C17-02 left based FRAME models measured from the support base. A larger body
could sit inside whole-distance, Engagement Range, or a terrain area while the
base stayed outside. The retained Order 97 probes observed that split on an
8-inch circular body mounted on a 120 mm support base.

## Source and scope

The selected Order 97 transcriptions already contain the operative sentences.
This change does not recapture or regenerate that source. Load and execution
status stay as recorded. The historical probe JSON remains the discovery record.

| Clause | Requirement |
|---|---|
| 01.04.01-obligation-06 | A FRAME model is wholly within only when every part of the model is within. |
| 17.02-measurement | Relationships to a FRAME model measure from the closest point on the model, including when it has a base. |
| faq-603e9b2f-cc24-498c-ac2e-08ad3068f257-elevated-membership | A model inside a terrain boundary remains inside that area when elevated. |
| faq-603e9b2f-cc24-498c-ac2e-08ad3068f257-frame-membership | Overhanging FRAME body parts place the model inside that terrain area. |

Ordinary models, including non-FRAME models that carry a physical body for
contact, still measure rules distance from the support base. Baseless FRAME
models already use the body as their rules footprint.

## Authority trace

`geometry_model_for_placement` sets `measures_every_part` when the model carries
the canonical `FRAME` keyword. `Model.rules_distance_subjects` then returns the
support base and each recorded body prism. Range, Engagement Range, objective
control, terrain-area membership, and disembark whole-distance placement read
those subjects. Wholly-within distance requires every point of a FRAME target,
including a FRAME model whose only prism is its main body, proved continuously
against the union of source parts. An ordinary target keeps support-base
containment even when the source is FRAME. The horizontal-only path is unchanged.
Movement lower bounds orbit offset parts around the parent anchor. Endpoint
exclusion and goal regions use the same parts, so a support-base proof cannot
certify that a legal body endpoint is impossible. Ordinary models still use
support-base rules distance. Transit collision still uses the moving base.
Replay derives the flag from the keyword again, so the session payload shape is
unchanged.

## Evidence and retained gates

`tests/unit/test_order100_frame_measurement.py` covers wholly within, Engagement
Range, movement containment, terrain membership at ground and elevation,
objective control, disembark whole-distance, both viewers, restore, and exact
replay. The same geometry without `FRAME` keeps support-base results. No Core
Rules or complete-game performance certificate is claimed. PFINAL remains open.

The Order 97 inventory now binds these clauses to the assertions above. Its
probe files and gap JSON stay the historical support-base observations. The
reviewed inventory fingerprint was recomputed after those evidence and runtime
manifest changes.

Runtime identity changed, so the existing runtime-bound head reports were
remeasured on this host with the same workloads, baselines, and budgets.
Historical baseline samples were not relabeled. The Order 85 contact baseline
keeps its timings; its recorded hash for `tests/order85_overhang_helpers.py`
now matches the optional enemy-keyword argument added for this order. The
baseline workload does not pass that argument. Commands, durations, and hashes
are in [the refresh record](performance/order100/inherited-refresh.json).
