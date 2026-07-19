# Session semantics

The Phase 18E-18H reference server exposes a formal authenticated session,
optimistic-concurrency command, and reconnect protocol around the Phase 18C
`AdapterGameSession` facade.
`session_id` identifies the server-owned transport session and is distinct from
the authoritative engine `game_id`.
Session metadata records ruleset, catalog, source-package, contract, engine,
and build identities; the authenticated visibility role; operational
timestamps; lifecycle state; a role-scoped terminal reason; monotonic session
revision; signed viewer event cursor; and viewer projection hash.

A client authenticates with an opaque bearer credential. An administrator may
create a session with `SessionCreatePayload`; the server validates that every
configured game player has a server-owned player-principal binding. Creation
initializes the engine-owned game behind the facade while leaving the transport
session in `created`. The administrator starts and closes it through typed
commands. A player principal may submit a decision only when its bound
`player_id` owns the pending engine request. Coaches, delayed spectators, and
replay viewers cannot mutate. Client-supplied participant assignments are
schema-invalid, and no header, query, or body actor/viewer value establishes
authority.

Every normative mutation uses `POST /sessions/{session_id}/commands` with a
`SessionCommandEnvelope`. The envelope carries `command_id`, `session_id`,
`expected_session_revision`, the pending `request_id` and client `result_id`
where applicable, and one typed lifecycle, finite-option, or parameterized
submission. It never accepts a viewer or actor identity. The formal Phase 18E
start, finite, parameterized, advance, and close routes are not part of contract
2.0. Deprecated authenticated `/games` development routes remain separate from
the Phase 18F command contract and must not be used by new clients.
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
- `projection_state_hash` identifies one role-scoped projection. An event cursor
  is an opaque HMAC-derived identifier bound to the session, principal,
  visibility role/player/delay scope, authorization epoch, protected
  authoritative event-log offset, viewer sequence, session revision, and
  projection hash. The wire token resolves to protected server-side state; it
  does not encode readable state. Clients never construct or inspect offsets.
- A client begins with the cursor from metadata or a full projection, applies
  events by deterministic `sequence_number`, and advances to `next_cursor`.
  `has_more` requires another page from that cursor.
- The default page size is 100, the maximum is 500, and the reference retention
  window is 4096 authoritative records. Pagination scans the authoritative log,
  omits hidden records, and exposes only contiguous viewer-scoped sequence
  numbers. The protected offset still advances across hidden records, but no
  raw count, sequence gap, placeholder record, extra page, or `has_more` value
  reveals how many were skipped.
- Malformed, expired, ahead, wrong-session, wrong-principal/role, revision-
  divergent, or projection-hash-divergent cursors return a successful typed
  delta with `resync_required: true`, no events, and a stable `resync_reason`.
  The client then replaces all derived state from `GET /projection` and resumes
  from that projection's cursor.
- The reference in-memory server generates a cryptographically random cursor
  key per server instance and retains the protected token-to-state map in
  memory. If session state is restored without that key and protected map,
  outstanding cursors are classified as malformed and use the same typed full-
  projection resynchronization path. Phase 18L owns durable protected state/key
  storage when sessions and cursors must survive process recovery.
- Only the current pending request may be answered. `request_id`, `actor_id`,
  `result_id`, option ID, proposal request context, and schema version are
  validated before engine mutation.
- Retrying a consumed request with a new command ID is stale/conflicting;
  clients must fetch the current projection rather than guessing a replacement
  ID. Retrying the same command ID, canonical envelope, and exact current
  authorization context returns its cached original public outcome. That
  context includes principal, role, player binding, visibility/cursor scope,
  delay/omniscience policy, route permissions, and registry authorization epoch.

Command processing is serialized by the server authority. A command is parsed
and validated, authorized for its submission kind, checked for an existing
journal outcome under the exact current authorization context, compared with
the current revision and pending request, and then applied to an isolated
session fork. Only a committed
result replaces the authoritative session together with its journal entry,
revision, projection checkpoint, and event cursor. Malformed commands,
revision/request conflicts, unauthorized actors, illegal unrecorded proposals,
terminal/closed sessions, and failures before that replacement leave
authoritative state unchanged. Two commands racing on one revision can
therefore commit at most one result.

A repeated `command_id` is idempotent only when its complete authorization
context and canonical envelope fingerprint match the journaled command and the
current context still permits that operation. Reuse under another principal,
role, player binding, policy, cursor scope, or authorization epoch returns the
shared authorization denial without revealing the journaled command. Only an
exact authorized context may receive `command_id_conflict` for a different
envelope or the cached status and response body for an exact retry.

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
Phase 18G adds protected opaque cursor, retention, pagination, delayed-snapshot, and
reconnect resynchronization semantics over retained in-memory revision
snapshots. Phase 18L still owns durable journal/state persistence, durable
cursor-key management, compaction storage, and crash recovery.

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
`ExportReplay`. Start, finite/parameterized submission, explicit advance, and
close are typed `ExecuteSessionCommand` variants rather than separate authority
surfaces.

Raw replay artifacts remain available to omniscient administrators during an
active session. A non-live replay viewer may export the raw artifact only after
the session is terminal or closed, so the role cannot become an active-game
omniscient feed.
