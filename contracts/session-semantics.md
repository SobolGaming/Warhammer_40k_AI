# Session semantics

The Phase 18E-18F reference server exposes a formal session and optimistic-
concurrency command protocol around the Phase 18C `AdapterGameSession` facade.
`session_id` identifies the server-owned transport session and is distinct from
the authoritative engine `game_id`.
Session metadata records ruleset, catalog, source-package, contract, engine,
and build identities; participant-to-player assignments; spectator/observer
roles; operational timestamps; lifecycle state; terminal reason; monotonic
session revision; viewer event cursor; and viewer projection hash.

A client creates a session with `SessionCreatePayload`, then explicitly starts
it. Creation initializes the engine-owned game behind the facade while leaving
the transport session in `created`; `StartSession` performs the first bounded
drain and moves it to `active` or `terminal`. `CloseSession` makes the session
closed and rejects later mutations with a typed error. Participant assignments
are validated as metadata. The development HTTP transport supplies participant
context in `X-Participant-ID`, outside the command envelope. Decision commands
map that participant to the pending engine actor. Lifecycle commands use the
participant assigned to the first configured player as the development
lifecycle coordinator; other player, spectator, and observer participants may
not start, explicitly advance, or close the session. This is routing context
rather than authentication: Phase 18H still owns authenticated operator and
principal binding, and a caller-supplied `viewer_player_id` is not authentication.

Every normative mutation uses `POST /sessions/{session_id}/commands` with a
`SessionCommandEnvelope`. The envelope carries `command_id`, `session_id`,
`expected_session_revision`, the pending `request_id` and client `result_id`
where applicable, and one typed lifecycle, finite-option, or parameterized
submission. It never accepts a viewer or actor identity. The older Phase 18E
start, finite, parameterized, advance, and close routes remain deprecated
compatibility operations through at least 2026-10-16 and one released minor
line, whichever is later; they are not the Phase 18F concurrency contract.
The parameterized command payload references the canonical proposal union, so
OpenAPI, generated clients, installed runtime validation, and the standalone
parameterized route accept the same 19 proposal kinds.

## State and ordering

- The server owns the authoritative session and invokes only the shared
  `AdapterGameSession` facade for engine interaction.
- `session_revision` begins at `0` and increases once for each command committed
  to authoritative history: start, state-changing advance, close, an accepted
  decision, or a recorded rule-invalid retry attempt. A Phase 18F command must
  present the current expected revision before mutation.
- `projection_state_hash` identifies a viewer projection state; event cursors
  are monotonically increasing indexes into the viewer-scoped event stream. A
  metadata response without a viewer does not expose a projection hash.
- A client starts at cursor `0`, applies events in response order, and advances
  to `next_cursor`. It must retrieve a fresh projection after cursor loss or
  state-hash drift.
- Only the current pending request may be answered. `request_id`, `actor_id`,
  `result_id`, option ID, proposal request context, and schema version are
  validated before engine mutation.
- Retrying a consumed request with a new command ID is stale/conflicting;
  clients must fetch the current projection rather than guessing a replacement
  ID. Retrying the same command ID, participant context, and canonical envelope
  returns its cached original public outcome.

Command processing is serialized by the server authority. A command is parsed
and validated, checked for an existing journal outcome, compared with the
current revision and pending request, authorized against the participant
assignment, and then applied to an isolated session fork. Only a committed
result replaces the authoritative session together with its journal entry,
revision, projection checkpoint, and event cursor. Malformed commands,
revision/request conflicts, unauthorized actors, illegal unrecorded proposals,
terminal/closed sessions, and failures before that replacement leave
authoritative state unchanged. Two commands racing on one revision can
therefore commit at most one result.

A repeated `command_id` is idempotent only when both its participant context
and canonical envelope fingerprint match the journaled command. Reuse with a
different envelope returns `command_id_conflict`; reuse by another participant
returns `actor_not_authorized` without revealing the journaled command. The
cached status and response body are returned unchanged, including after a new
HTTP connection.

`SessionCommandResult.committed` reports whether a command entered authoritative
history, while `accepted` reports whether its proposed gameplay action was
rule-valid/applied. A recorded invalid attempt therefore returns
`committed: true`, `accepted: false`, advances the revision, includes its event
range, and exposes the fresh retry request through the viewer projection. An
invalid result rejected by an engine pre-validator before decision recording
returns `committed: false`, `accepted: false` and leaves the revision unchanged.
The schema and runtime both require `accepted: true` to imply `committed: true`.
A recorded valid action whose deterministic post-application advancement reaches
the typed `transition_budget_exhausted` safety boundary remains accepted; its
lifecycle status is `unsupported`, but it returns `committed: true`,
`accepted: true`. Other directly returned recorded `unsupported` outcomes are
not accepted unless their typed status proves that application completed.
Rejected `invalid` outcomes use `proposal_invalid`; rejected `unsupported`
outcomes use `rule_path_unsupported`, whether the latter was recorded or
rejected before recording.

After an accepted finite or parameterized submission, the server performs a
bounded deterministic drain until the next adapter-visible decision, terminal
state, typed invalid/unsupported result, or transition-budget safety boundary.
The command response contains the resulting metadata, viewer projection
checkpoint, and half-open event range. Clients do not issue guessed advance
calls between a decision and its next visible boundary. Explicit
`AdvanceSession` remains available for start/recovery/conformance and documented
idle boundaries; it never authorizes the transport to apply an option payload.
An advance at an existing `waiting_for_decision` boundary returns
`advance_not_required` without forking the facade, changing state, advancing the
revision, or reserving the command ID.

The in-memory command journal proves Phase 18F ordering and retry semantics;
Phase 18L owns durable journal/state persistence and crash recovery. Phase 18G
still owns durable event cursor tokens, retention windows, and reconnect
resynchronization semantics.

## Lifecycle outcomes

`status_kind` is one of `advanced`, `waiting_for_decision`, `terminal`,
`invalid`, or `unsupported`. Parameterized rule-invalid attempts may return a
422 lifecycle status when the underlying adapter contract allows a recorded
rejection and retry. Transport/precondition failures use the typed error
envelope. Clients must distinguish stale/conflict, malformed/invalid,
unsupported, forbidden, corruption, and terminal examples rather than mapping
all failures to a generic retry.

The required formal operations are `CreateSession`, `GetSessionMetadata`,
`ExecuteSessionCommand`, `GetProjection`, `GetCatalog`, `GetEvents`, and
`ExportReplay`. `StartSession`, `SubmitFiniteDecision`,
`SubmitParameterizedDecision`, `AdvanceSession`, and `CloseSession` remain
documented deprecated Phase 18E compatibility operations during the support
window above.
