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
Visible pending decisions receive only the engine-authored descriptor produced
for their authorized request. Hidden event records are
omitted from that viewer's event page entirely. Public `sequence_number` values
are contiguous within each viewer scope, and pagination scans hidden records
while advancing only an opaque protected authoritative offset. A projection
does not expose the authoritative event count, and hidden records do not create
placeholder entries, sequence gaps, extra pages, or `has_more` changes. Secret
secondary information and similar source-backed state remain hidden until the
engine records their reveal.

Errors must not echo an opponent's submitted body or hidden current request.
Status payloads may include request/actor details only when the corresponding
request is visible to that viewer. Catalog projections contain static public
display data and no live hidden state.

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

`examples/projections/hidden_secondary_redaction_view.json` and the generated
event/status examples are conformance fixtures. Adding a visibility-sensitive
payload requires valid owner and opponent examples plus a regression proving
that counts and metadata do not leak.
