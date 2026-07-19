# Client conformance scenarios

A conforming client demonstrates the following scenarios against the canonical
schemas and the ordinary `AdapterGameSession` path.

1. Create a formal session with the current request schema version and retain
   its distinct `session_id`, engine `game_id`, and revision `0`.
2. Authenticate as the administrator, start it through
   `ExecuteSessionCommand`, then retry that exact command as the same principal
   and exact role/player/policy/authorization-epoch context on a new connection
   and require the same HTTP status and byte-equivalent public response. Change
   each part of that context in turn and require the shared 403 response rather
   than the cached data.
3. Race two valid commands carrying one expected revision and require at most
   one commit. Verify stale revision/request, wrong principal, malformed
   envelope, illegal proposal, terminal session, and pre-commit failure all
   preserve the authoritative revision, replay, event cursor, and projection
   hash.
4. Retrieve and cache the source-hashed rules catalog; retrieve a player-scoped
   game projection and verify its projection schema/hash.
5. Render every decision family marked `live_scenario` in
   `examples/decisions/family-coverage.json` and submit only one of the emitted
   option IDs with a unique deterministic/replay-safe `result_id`. Treat
   `envelope_only` rows as inventory, not conformance evidence.
6. Render every generated proposal-kind fixture, preserve its request/source
   context, and submit the corresponding typed proposal without applying it
   locally.
7. Consume events from the opaque cursor issued with a role-scoped projection,
   preserve `sequence_number` order, follow `next_cursor` while `has_more`, and
   replace client state from a full projection when `resync_required` is true.
   Treat `retention_limit` as the event-record window and
   `revision_retention_limit` as the revision-snapshot window; a cursor is valid
   only inside both.
   Treat sequence numbers as viewer-scoped, and reject projections/deltas that
   expose authoritative event counts, readable cursor state, hidden placeholders,
   or sequence gaps caused by hidden records.
8. Display hidden-decision and hidden-secondary fixtures without revealing
   hidden type, source, option-count, or payload metadata.
9. Distinguish waiting, advanced, invalid, unsupported, and terminal lifecycle
   statuses.
10. Distinguish malformed, stale/conflict, forbidden, corruption, unsupported,
   and terminal error fixtures; do not blindly retry schema or corruption
   failures.
11. Enforce the player, coach, delayed-spectator, administrator, and replay-
    viewer route policies; deny raw active-session replay to a replay viewer,
    permit that role only after terminal/close, and treat exported replay
    payloads as immutable audit artifacts.
12. Reject a response that fails its declared schema, contains an unknown major
    version, or contradicts the coordinate/session/redaction semantics.

The generated coverage directories are:

- `examples/decisions/family-coverage.json` for every registered, nested, or
  redaction-only external decision token and its honest coverage status;
- `examples/decisions/families/` for real session-derived decision scenarios;
- `examples/decisions/parameterized/` for every supported proposal kind;
- `examples/projections/`, `examples/events/`, `examples/statuses/`, and
  `examples/errors/` for read, lifecycle, and failure behavior.

The repository contract check validates that the inventory and proposal sets
remain complete as new registered decision metadata or proposal kinds are
added. A decision row advances from `envelope_only` to `live_scenario` only when
its committed example is captured through the ordinary adapter session path.

## Phase 18M-A executable certification

`conformance/typescript/` implements the first executable scenario through the
published OpenAPI/JSON Schema/HTTP boundary. It authenticates an administrator,
both players, and a replay viewer with opaque bearer credentials; creates and
starts the public session fixture; compares player/opponent projections; submits
emitted finite options and a deployment proposal; verifies revisions,
idempotency, events, and resynchronization; closes the session; and compares
immutable replay exports from two independent reference-server executions.

Exact command retries against one backend require byte-equivalent cached
responses. Cross-backend replay comparison instead parses and schema-validates
both artifacts, recursively orders object member names by Unicode code point,
preserves array order, emits compact JSON with non-ASCII strings escaped as
lower-case `\\u` code units, and compares the SHA-256 of that canonical form.
It separately compares complete semantic content, source identity, decision
records, event records, projection checkpoints, and published source/checkpoint
hashes. Wire property order and insignificant whitespace are not conformance
requirements.

This slice certifies the Phase 18E-18H generic protocol and one setup/deployment
decision path. It does not promote `envelope_only` inventory rows to
`live_scenario`, claim the Phase 20A full-game gate, or claim persistence,
concurrent-race, every-decision-family, complete golden-corpus, coach,
delayed-spectator, or live rejected `rule_path_unsupported` coverage. Those
backend-executable cases remain Phase 18M-B+ work.
