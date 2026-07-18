# Session semantics

The Phase 18E reference server exposes a formal session protocol around the
Phase 18C `AdapterGameSession` facade. `session_id` identifies the server-owned
transport session and is distinct from the authoritative engine `game_id`.
Session metadata records ruleset, catalog, source-package, contract, engine,
and build identities; participant-to-player assignments; spectator/observer
roles; operational timestamps; lifecycle state; terminal reason; monotonic
session revision; viewer event cursor; and viewer projection hash.

A client creates a session with `SessionCreatePayload`, then explicitly starts
it. Creation initializes the engine-owned game behind the facade while leaving
the transport session in `created`; `StartSession` performs the first bounded
drain and moves it to `active` or `terminal`. `CloseSession` makes the session
closed and rejects later mutations with a typed error. Participant assignments
are validated as metadata, but Phase 18H still owns authenticated principal
binding. A caller-supplied `viewer_player_id` is not authentication.

## State and ordering

- The server owns the authoritative session and invokes only the shared
  `AdapterGameSession` facade for engine interaction.
- `session_revision` begins at `0` and increases once for each accepted start,
  advance, decision, or close command. Phase 18F owns expected-revision checks,
  idempotency keys, and concurrent command serialization guarantees.
- `projection_state_hash` identifies a viewer projection state; event cursors
  are monotonically increasing indexes into the viewer-scoped event stream. A
  metadata response without a viewer does not expose a projection hash.
- A client starts at cursor `0`, applies events in response order, and advances
  to `next_cursor`. It must retrieve a fresh projection after cursor loss or
  state-hash drift.
- Only the current pending request may be answered. `request_id`, `actor_id`,
  `result_id`, option ID, proposal request context, and schema version are
  validated before engine mutation.
- Retrying the same request after it was consumed is stale/conflicting; clients
  must fetch the current projection rather than guessing a replacement ID.

After an accepted finite or parameterized submission, the server performs a
bounded deterministic drain until the next adapter-visible decision, terminal
state, typed invalid/unsupported result, or transition-budget safety boundary.
The command response contains the resulting metadata, viewer projection
checkpoint, and half-open event range. Clients do not issue guessed advance
calls between a decision and its next visible boundary. Explicit
`AdvanceSession` remains available for start/recovery/conformance and documented
idle boundaries; it never authorizes the transport to apply an option payload.

Phase 18G still owns durable event cursor tokens, retention windows, reconnect
resynchronization, and persistence/recovery semantics.

## Lifecycle outcomes

`status_kind` is one of `advanced`, `waiting_for_decision`, `terminal`,
`invalid`, or `unsupported`. Parameterized rule-invalid attempts may return a
422 lifecycle status when the underlying adapter contract allows a recorded
rejection and retry. Transport/precondition failures use the typed error
envelope. Clients must distinguish stale/conflict, malformed/invalid,
unsupported, forbidden, corruption, and terminal examples rather than mapping
all failures to a generic retry.

The required formal operations are `CreateSession`, `GetSessionMetadata`,
`StartSession`, `GetProjection`, `GetCatalog`, `GetEvents`,
`SubmitFiniteDecision`, `SubmitParameterizedDecision`, `AdvanceSession`,
`ExportReplay`, and `CloseSession`.
