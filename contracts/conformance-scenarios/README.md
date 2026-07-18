# Client conformance scenarios

A conforming client demonstrates the following scenarios against the canonical
schemas and the ordinary `AdapterGameSession` path.

1. Create a session with the current request schema version and retain the
   returned `game_id`.
2. Retrieve and cache the source-hashed rules catalog; retrieve a player-scoped
   game projection and verify its projection schema/hash.
3. Render every generated finite decision-family fixture and submit only one of
   the emitted option IDs with a unique deterministic/replay-safe `result_id`.
4. Render every generated proposal-kind fixture, preserve its request/source
   context, and submit the corresponding typed proposal without applying it
   locally.
5. Consume events from cursor `0`, preserve order, advance to `next_cursor`, and
   resynchronize from a projection if cursor/state context is lost.
6. Display hidden-decision and hidden-secondary fixtures without revealing
   hidden type, source, option-count, or payload metadata.
7. Distinguish waiting, advanced, invalid, unsupported, and terminal lifecycle
   statuses.
8. Distinguish malformed, stale/conflict, forbidden, corruption, unsupported,
   and terminal error fixtures; do not blindly retry schema or corruption
   failures.
9. Export support and replay payloads, verify their schema versions and source
   identities, and treat them as immutable audit artifacts.
10. Reject a response that fails its declared schema, contains an unknown major
    version, or contradicts the coordinate/session/redaction semantics.

The generated coverage directories are:

- `examples/decisions/families/` for every registered engine decision type;
- `examples/decisions/parameterized/` for every supported proposal kind;
- `examples/projections/`, `examples/events/`, `examples/statuses/`, and
  `examples/errors/` for read, lifecycle, and failure behavior.

The repository contract check validates that these sets remain complete as new
decision constants or proposal kinds are added.
