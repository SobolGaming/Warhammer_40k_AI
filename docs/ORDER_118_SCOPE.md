# Order 118: attack-scoped attached ability sources

Base: ae452b60dd37b2ee262eb5e830ecf6405cf80516 (merged PR558).
Acceptance: retained Order97 rule:19:19.04:1 block4 keeps an ability from a
destroyed conferring attached model until the attacking unit finishes all attacks.
Cover Bodyguard, Leader, Support and equipped bearer through shared consumption,
then expiration, engine-generated save/restore, fork and replay. Preserve ordinary
non-attack source expiration, revival and special retained-destruction behavior.

The owning seam is shared ability presence. Attack damage and attack-classified
mortal application register semantic source IDs using existing persisting effects.
The attack executor expires them after deferred attack mortal wounds and before
destruction reactions. Catalog equipment queries accept that authenticated source
set without reintroducing an independent living-only check. Geometry continues to
use battlefield IDs; model-only action consumers continue to require living models.
Model-anchored auras keep the attached unit's own ability without looking up a
removed bearer's placement or granting range to another unit. The regression uses
the catalog's structured Stealth grant, not a claim of raw-text provider support.

The added source-lifetime responsibility is extracted into a small module. Frozen
large damage/catalog owners only route the boundary to extracted helpers. No new
player choices, faction providers, speculative history hardening, or test-file
reorganization. Existing persisting-effect serialization and private audit-event
projection remain authoritative. The patch contract publishes the new build.
The original Order97-pinned unit-ability test file is retained byte-for-byte from
the base through the established historical-input mapping. Added regressions are
current evidence; the retained original assertions and source audits stay intact.
Shooting fixtures use a clear battlefield and unobstructed firing corridors so
source lifetime validation does not depend on an unrelated model-occlusion solve.

Performance: bounded ordinary-rule semantics; default quiet serial current-runtime
smoke under the owner-authorized review policy, exact-base Git-blob input and
Python3.14 owner-AST bindings. No deliberate performance change or full-game claim.

Apply docs/SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md. Block incorrect rules, normal
legal-play failures, engine-generated valid-state restore/replay failures and
explicitly required supported-input boundaries; reproduce entry, impact,
reachability and acceptance violation. Queue coordinated hand-edited-history
hardening separately. Preserve all required local/hosted gates and two distinct
exact-head clean reviews before protected merge.
