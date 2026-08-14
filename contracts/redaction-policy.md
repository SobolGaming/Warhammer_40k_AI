# Viewer redaction policy

Every request is authenticated before route dispatch, then every viewer-bearing
read or command response is scoped to the server-bound principal role before it
crosses the adapter boundary. The shared adapter redaction module is
authoritative for projections, pending decisions, events, lifecycle status,
session metadata checkpoints, command results, and hidden transport metadata.
Transport code must not maintain a second hidden-type list.

Hidden information includes payload values and all information derivable from
metadata: option labels and counts, decision types, source IDs, event details,
status messages, support rows, record counts, and identifiers. A field is not
safe merely because it is outside the main game projection.

When a pending decision belongs to another player and is hidden, the projection
receives the canonical hidden decision type, a stable redacted request ID, an
empty option list, a redacted payload, and no actor ID. Hidden pending decisions
are also assigned `interaction: null`; renderer kind, required inputs, selected
entities, constraints, schema references, and display hints are hidden metadata.
Their projection also carries an empty `nested_interaction_requests` array.
When the parent request is visible, that array contains only typed nested
requests derived from the same engine payload and visibility decision; transport
code does not rescan arbitrary proposal JSON or apply a second redaction rule.
Visible pending decisions receive only the engine-authored descriptor produced
for their authorized request. Hidden event records are
omitted from that viewer's event page entirely. Public `sequence_number` values
are contiguous within each viewer scope, and pagination scans hidden records
while advancing only an opaque protected authoritative offset. A projection
does not expose the authoritative event count, and hidden records do not create
placeholder entries, sequence gaps, extra pages, or `has_more` changes. Secret
secondary information and similar source-backed state remain hidden until the
engine records their reveal.

Both entries in `primary_mission_assignments` are public mission data. Viewer
projection and redaction preserve the complete directed pair; neither player's
Primary Mission or Force Disposition binding is removed from a player view.

Errors must not echo an opponent's submitted body or hidden current request.
Status payloads may include request/actor details only when the corresponding
request is visible to that viewer. Catalog projections contain static public
display data and no live hidden state.

Phase 17N turn-start position snapshots preserve their public
game/round/source metadata. Army-list unit and model identities, including an
unplaced Strategic Reserve, are public to both players; Declare Battle
Formations secrecy applies to the declaration choices and their unrevealed
state, not to roster/datacard identity. Turn-start snapshots do not exist until
the battle has begun, after that declaration window has closed, so both players
receive every complete historical rules-unit row. The redactor still validates
typed snapshots before publishing every row without viewer filtering; it never
manufactures or removes a partial Attached Unit row.

When the configured setup sequence includes `declare_battle_formations`, its
simultaneous declarations remain unresolved from game creation through
completion of that step. During that interval, every player-owned reserve or
faction-rule setup request, its recorded result, and every event created by
applying it are visible only to that player and an omniscient administrator.
Pre-materialized embarked-unit manifests and Dedicated Transport setup
consequences use the same boundary, including when they are materialized during
`muster_armies`. A setup sequence with no `declare_battle_formations` step has no
battle-formation secrecy window. Both the structured
`battlefield_view` and the sibling raw `battlefield_state` suppress an
opponent's reserve/cargo state and any premature model pose; live opponent
modifier traces and mutable unit-resource totals likewise stay at their public
roster baseline. Roster/datacard IDs remain public. Completing the step emits
one deterministic public
`battle_formations_revealed` event containing the final reserve, transport,
setup-consequence, and faction-rule state. Attached-unit declarations are made
during Muster Armies and their frozen starting records are public in the
`army_mustered` event; they are not battle-formation secrets. Subsequent projections
publish those formation facts normally.

Authoritative `model_destroyed` events carry event-time source and destroyed
rules-unit objective-proximity witnesses. Both witnesses describe public
battlefield facts after Declare Battle Formations has been revealed, so player
and administrator event streams receive the same evidence. The shared event
projection validates both typed witness payloads before publishing them. This
does not relax the separate redaction of still-unrevealed Declare Battle
Formations choices and formation state.

The derived `primary_turn_start_evidence_recorded`,
`primary_battlefield_departure_recorded`, and
`primary_unit_destruction_recorded` records are likewise public game history.
Their complete canonical payload is identical for both players and an
administrator; the redactor must not suppress, truncate, or owner-scope those
evidence rows.

The nested Phase 17O capability manifest is projected by this same redaction
module. A non-omniscient viewer receives only owned roster, unit, rule,
geometry, and unsupported-effect rows. Capability counts and mode results are
rebuilt from visible rows. Selection hashes and manifest IDs cover the viewer's
complete canonical muster request plus a digest of the complete public mission
setup, never an opponent's selection. Certification blocker details are rebuilt
from visible rows, but the authoritative Phase 20A and Phase 20D booleans are
preserved so redaction cannot strengthen a certification claim. When a hidden
authoritative blocker would otherwise disappear, the projection emits only a
generic redacted-blocker reason code. The common
mission/catalog/ruleset/contract identities and neutral interaction inventory
contain no selected opponent content.

Session metadata is always principal scoped. Viewer-scoped command checkpoints
and event ranges use only that role's redacted projection and stream; they must
not become a hash, count, cursor, or next-actor oracle for hidden opponent state.
Missing and invalid credentials return the same `authentication_required` 401
body. All authenticated authorization denials return the same `access_denied`
403 body. Neither shape includes request IDs, actor identity, option/target
counts, source IDs, support status, terminal details, or caught exception text.

Role policy is explicit:

| Role | Live visibility | Delay | Mutation | Cursor scope | Replay |
|---|---|---:|---|---|---|
| player | bound player's view | 0 | own pending decisions | principal + player | denied |
| coach | paired player's view | 0 | denied | principal + player | denied |
| delayed spectator | public-only view | 1 revision | denied | principal + delay | denied |
| administrator | omniscient view | 0 | lifecycle only; no actor impersonation | principal + administrator | allowed |
| replay viewer | no live view | n/a | denied | none | terminal/closed only |

A role, player binding, policy, or registry authorization-epoch change changes
cursor scope and invalidates previously issued cursors. Delayed spectators read a retained historical revision snapshot;
they do not receive current hidden state with fields merely omitted.

`examples/projections/hidden_secondary_redaction_view.json`,
`examples/support-profile.json`, both
`examples/support-profile-player-*-redacted.json` files, and the generated
event/status examples are conformance fixtures. Adding a visibility-sensitive
payload requires valid owner and opponent examples plus a regression proving
that counts and metadata do not leak.
