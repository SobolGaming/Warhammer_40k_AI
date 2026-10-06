# Order134: conditional oversized deployment restrictions

Selected scope: P03L/C03-12, `03.02.02-obligation-02` and
`03.02.02-obligation-03` only. The selected source is Core
`rule:03:03.02.02:1`, *Setting Up Large Models*, Game Datamissions SHA256
`910af631243255d6f41c6eb1c64fabad2de8e7999528fbcf837883fcce10d169`.
All ten literal blocks and hashes remain in the Order134 source audit. Blocks2-4
conditionally prohibit Normal, Advance, Fall Back and Charge moves and ranged
attacks in the turn an oversized deployment occurs. The Strategic Reserves
paragraph's AIRCRAFT exemption belongs to that separate clause.

The user revised acceptance on 2026-10-06: **"yes, implement and test the conditional
restriction now"**, after being offered conditional infrastructure with playable
in-turn certification left open pending a granting rule and consumer. The original
acceptance and exact question/answer are retained in the source audit.

Acceptance: implement and test the conditional restrictions now; retain pregame
no-first-turn-lock, no deployment AIRCRAFT exemption, shared consumers, valid
state persistence, isolated forks and exact replay from conditional checkpoints.
Leave in-turn gameplay certification **OPEN** until an authenticated granting
rule and admitted consumer establish the condition in legal play. The current
deployment owner remains SETUP-only and its existing BATTLE rejection is unchanged.

`large_model_deployment_restrictions.py` owns a strict typed persistent-effect
payload: source ID, deterministic setup occasion, qualifying model identities,
affected rules-unit identity and the actual active turn. Its record helper takes
an already-qualified condition and verifies identity before mutation; it neither
places a model nor grants permission nor proves geometry. A future deployment
owner must authenticate its granting rule and validate oversized geometry first.
No admitted in-turn owner calls the helper today. It records no pregame effect.

The shared `large_model_activity_reason` reads these effects through established
rules-unit lineage before its unchanged Strategic Reserves branch. Expiration uses
the actual active player, including when that player is the opponent of the unit
owner. Normal, Advance, Fall Back, Charge and ranged consumers share the result;
stationary, Surge, pile-in, consolidate and melee are outside this selected lock.
No player-facing decision, payload family or visibility schema changes: existing
finite choices, persistent effects, facade projections, save/load and checkpoint
replay already carry this state. Contract44.3.20 publishes the changed runtime
identity with unchanged external shapes.

Tests explicitly construct qualifying contexts, exercise attached components and
actual turn expiry, and run native facade rejection/legal retry, valid JSON
restore, forks, player/role views, events, exact checkpoint replay and continuation.
These tests certify infrastructure only. They are not deployment admission or
end-to-end source-backed in-turn gameplay certification. Original tests/assertions,
source observations, archives and ceilings remain intact; the original changed
restriction owner is preserved byte-for-byte in the Order134 historical mapping.

The review policy blocks incorrect rules, ordinary legal-play failures,
engine-generated valid-state persistence/replay failures and explicit trust
boundaries. Reproduce entry, impact, normal reachability and violated acceptance.
Coordinated hand-edited-history hardening stays separate unless required by one
of those supported boundaries. No full-game or universal-history claim is made.

Delivery requires cheap static/types/archive checks, complete source/types,
contracts/wheel/client/inventory/pins, quiet current smoke, complete source quality,
then HOLD for the sixteen unchanged polygon cases alone with branch coverage.
Explicit RELEASE permits the remaining complete cohort in 32 workers and bounded
reviewer probes. Only a complete passing current cohort supplies final timings.
Both independent exact-final reviews, authenticated draft/ready native CI artifacts
and protected squash remain mandatory. Order135 receives this open prerequisite
in an immutable handoff; its implementation and automatic main-CI monitoring stop.
