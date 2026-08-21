# Session semantics

The Phase 18E-18L reference server exposes a formal authenticated session,
optimistic-concurrency command, reconnect, and durable recovery protocol around
the Phase 18C `AdapterGameSession` facade.
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
parameterized route accept the same 19 proposal kinds plus the two Cult Ambush
alternatives and return-on-death payload.

## State and ordering

- The server owns the authoritative session and invokes only the shared
  `AdapterGameSession` facade for engine interaction.
- `session_revision` begins at `0` and increases once for each command committed
  to authoritative history: start, state-changing advance, close, an accepted
  decision, or a recorded rule-invalid retry attempt. A Phase 18F command must
  present the current expected revision before mutation.
- `projection_state_hash` is the SHA-256 of the canonical complete role-scoped
  projection object excluding only the hash field itself. Pending decisions,
  proposals, interaction descriptors, typed nested interaction requests, public
  ledgers, display maps, and every other viewer-visible field are therefore
  checkpointed; hidden source state is absent before hashing. An event cursor
  is an opaque HMAC-derived identifier bound to the session, principal,
  visibility role/player/delay scope, authorization epoch, protected
  authoritative event-log offset, viewer sequence, session revision, and
  projection hash. The wire token resolves to protected server-side state; it
  does not encode readable state. Clients never construct or inspect offsets.
- A client begins with the cursor from metadata or a full projection, applies
  events by deterministic `sequence_number`, and advances to `next_cursor`.
  `has_more` requires another page from that cursor.
- The default page size is 100 and the maximum is 500. `retention_limit` is the
  authoritative-event window and defaults to 4096 records;
  `revision_retention_limit` is the session-wide revision-snapshot window and
  defaults to 128 revisions. A cursor remains valid only while both its
  protected offset and its revision are retained. Delayed viewers use the same
  session-wide snapshot floor, applied to their delayed target projection.
  Pagination scans the authoritative log, omits hidden records, and exposes
  only contiguous viewer-scoped sequence numbers. The protected offset still
  advances across hidden records, but no raw count, sequence gap, placeholder
  record, extra page, or `has_more` value reveals how many were skipped.
- Malformed, expired, ahead, wrong-session, wrong-principal/role, revision-
  divergent, or projection-hash-divergent cursors return a successful typed
  delta with `resync_required: true`, no events, and a stable `resync_reason`.
  The client then replaces all derived state from `GET /projection` and resumes
  from that projection's cursor.
- The server generates a cryptographically random cursor key and retains the
  protected token-to-state map as authority-private state. Each token carries a
  server-verifiable authentication tag, so a
  tampered or foreign token is malformed while an authentic token whose state
  was evicted is expired. Issuance evicts states below the session-wide revision
  floor and below the issuing viewer scope's event floor; an authorization-
  scope change evicts that principal's former scope. A terminal or closed
  transition compacts each principal/scope to its newest pre-terminal checkpoint
  before issuing final checkpoints. That preserves terminal-boundary resume
  while discarding historical cursor states; final cursors remain valid as long
  as the completed session remains addressable. The Phase 18L atomic checkpoint
  includes the exact cursor key and retained token registry. Recovery accepts
  that state only when its authenticated token payloads, session identities,
  revision floors, principal bindings, and authorization epoch verify exactly;
  otherwise it fails closed without exposing the session.
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

The command journal proves Phase 18F ordering and retry semantics; Phase 18G
adds protected opaque cursor, retention, pagination, delayed-snapshot, and
reconnect resynchronization semantics over retained revision snapshots. Phase
18L persists those structures as one atomic authority checkpoint. An accepted
command's complete envelope and authorization context, committed revision,
cached public status/response, staged adapter state, revision snapshots,
revision commitment, and cursor registry become durable before the response is
published or the in-memory authority pointer is replaced. A failure before
replacement leaves the previous checkpoint authoritative; a restart after
replacement returns the cached byte-equivalent outcome for an exact retry.
Because a store error may be reported after durable replacement, the server
arms fail-stop state immediately before invoking the commit boundary and clears
it only after the store returns success. Typed storage failures and normalized
custom-store `OSError`/`RuntimeError` failures therefore leave the authority
latched. A fresh process must load and verify the store before serving again, so
stale in-memory state cannot overwrite an ambiguous successful commit.

## Persistence, recovery, and authority

`session-persistence-v2-phase18l` is a closed operator-only artifact. It is not
an HTTP request or response and is never a client mutation surface. Its root
binds the server, engine build, external-contract, and persistence-schema
versions to the authorization bindings, protected cursor codec, retention
policy, complete authoritative sessions, and the game-to-session index. A
canonical SHA-256 covers every state member preceding that hash. Bearer
credentials are deliberately absent; a deployer re-injects its credential
registry and recovery verifies the principal/role/player bindings and
authorization epoch against the checkpoint.

`engine_version` remains the semantic package version. `engine_build_id` is
separate and has the form
`warhammer40k-core-v2:runtime-tree-sha256-v1:<sha256>`. A generated manifest
hashes the exact packaged Python, JSON, `py.typed`, and packaged contract-schema
resource inventory. Runtime startup recomputes and compares that complete
inventory; an absent manifest or any resource drift is untrusted and fails
closed. Recovery then requires the checkpoint's verified build ID exactly, so
two builds with the same package version but different runtime content cannot
share durable state.

Each persisted session retains normalized `GameConfig` input, exact ruleset,
overlay, catalog, source-package, and source hashes, RNG state, lifecycle
status, terminal flags, accepted decision and event history, monotonic revision,
idempotency journal, retained revision snapshots, and adapter-owned recovery
checkpoint. The checkpoint carries the current lifecycle, initial replay input,
latest replay artifact, and deterministic decision/event/projection/RNG/package
commitments. Operational timestamps are restored but never determine
simulation order. A successful read advances the session-level
`last_activity_at` value without rewriting a retained revision snapshot; the
timestamp inside each snapshot remains the immutable activity boundary at
which that revision was captured. Recovery therefore requires the current
session timestamp to be at least as recent as the latest retained snapshot.

The session also retains a contiguous, unpruned commitment for every revision
from zero through the current head. Each domain-separated commitment names a
typed protocol-command or legacy/non-command origin and commits to the previous
revision, exact decision-record and event-record prefixes, RNG history/draw/state,
the adapter checkpoint, the viewer-independent authoritative session state,
and explicit `started`/`closed` lifecycle flags. The flags bind creation, start,
and final close transitions even after their full revision snapshots are
pruned. Protocol-command revisions additionally bind the
complete command envelope and fingerprint, journal entry and cached response,
and authenticated before/after cursor states. Recovery recomputes these values
from the current authoritative histories and every still-retained snapshot,
requires a one-to-one command-revision/journal relationship, and checks finite
or parameterized envelopes against the `DecisionRecord` they produced. Snapshot
retention may discard old full checkpoints, but it never discards their revision
commitments or durable idempotency linkage.

Recovery validates the closed artifact and root hash before registering any
session. It loads the latest verified adapter checkpoint, replays any accepted
decision tail carried by the replay artifact through the adapter-owned session
recovery path and therefore through `GameLifecycle.submit_decision(...)`, then
compares the complete decision records, authoritative events and sequence, RNG
state, replay artifact, projection hashes, package identities, session revision,
revision history head, and authenticated historical cursor commitments. Where
a full snapshot remains retained, cached journal projections and cursor
positions are recomputed against that exact snapshot and saved authorization
context. The command journal is restored and cross-validated as an idempotency
cache; recovery does not reapply its command envelopes. A
schema, package, build, checkpoint, or deterministic-content mismatch produces
a typed corruption or drift diagnostic and leaves the session unavailable;
there is no partial reconstruction or permissive fallback.

Initialization is an explicit operator action. Constructing a server with a
persistence store always means recovery and requires one complete durable root;
neither a missing database nor a database with a missing singleton row is
interpreted as first boot. A new authority starts without a store and invokes
`initialize_persistence(...)`, which exclusively reserves a new database path
and transactionally installs its schema and initial empty-server root before
attaching it. If initialization is interrupted after the path is reserved, the
existing path is not silently retried or recovered as empty; operator repair or
replacement is required.

The SQLite reference store uses schema version
`server-persistence-store-v2` and `PRAGMA user_version = 2`. `initialize`,
`load`, and `commit` use a write transaction; load and commit open only an
existing database. While holding `BEGIN IMMEDIATE`, the store checks WAL mode,
the exact STRICT singleton table SQL and extended column metadata, and the
absence of extra schema objects, indexes, foreign keys, views, and triggers.
Commit verifies the existing row, performs the UPSERT, requires exactly one
affected singleton row, and selects and compares the exact new version, JSON,
and content hash before transaction commit. A deleted root, missing singleton
constraint, non-STRICT table, suppressed or rewritten write, or concurrent
schema mutation fails closed.

One process or actor owns mutation for a session and serializes its commands.
Reads may use immutable viewer-scoped projections, but no second writer may
advance the same session. Failover transfers ownership only after the complete
checkpoint, decision tail, revision chain, and command journal verify. The store
uses one atomic transaction for the authority artifact and indexes sessions by
validated identities.

This integrity design detects accidental corruption, incomplete writes,
internally inconsistent revisions, and code/build drift. Its content hashes and
revision commitments are not keyed attestations. An actor able to rewrite the
entire database can recompute a coherent root and chain, and replacement by an
older valid database is not detectable from that database alone. Resistance to
a malicious storage writer or rollback therefore requires a trusted external
monotonic, signed, or append-only anchor; Phase 18L does not claim that threat
model.

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
