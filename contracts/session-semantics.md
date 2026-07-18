# Session semantics

The Phase 18D contract describes the in-process/reference Phase 18C session
facade through the Phase 18E development HTTP adapter. `game_id` identifies the
authoritative engine session in this baseline. Distinct hosted `session_id`,
participant assignment, authentication, close/start operations, and resumable
transport ownership remain Phase 18E-18H work and are not implied here.

A client creates a game with `CreateSessionPayload`. Another client joins the
same development session by receiving that `game_id` out of band and reading
viewer-scoped projection/events with its assigned `viewer_player_id`; this is
not authorization. Production clients must not treat the development server's
player ID query parameter as authentication.

## State and ordering

- The engine owns authoritative state and serializes each server operation.
- `projection_state_hash` identifies a viewer projection state; event cursors
  are monotonically increasing indexes into the viewer-scoped event stream.
- A client starts at cursor `0`, applies events in response order, and advances
  to `next_cursor`. It must retrieve a fresh projection after cursor loss or
  state-hash drift.
- Only the current pending request may be answered. `request_id`, `actor_id`,
  `result_id`, option ID, proposal request context, and schema version are
  validated before engine mutation.
- Retrying the same request after it was consumed is stale/conflicting; clients
  must fetch the current projection rather than guessing a replacement ID.

`advance` performs the reference server's bounded lifecycle advancement. A
submission still uses the shared decision path and returns a lifecycle status;
it does not authorize the adapter to apply any option payload itself.

## Lifecycle outcomes

`status_kind` is one of `advanced`, `waiting_for_decision`, `terminal`,
`invalid`, or `unsupported`. Parameterized rule-invalid attempts may return a
422 lifecycle status when the underlying adapter contract allows a recorded
rejection and retry. Transport/precondition failures use the typed error
envelope. Clients must distinguish stale/conflict, malformed/invalid,
unsupported, forbidden, corruption, and terminal examples rather than mapping
all failures to a generic retry.
