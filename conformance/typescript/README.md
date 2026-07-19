# Phase 18M-A TypeScript conformance client

This package is the first executable backend-conformance slice for the CORE V2
2.0 HTTP/OpenAPI contract. Its transport methods derive request bodies,
path/query parameters, and status-specific responses directly from the
generated `paths` operations in `contracts/openapi.yaml`. It validates wire
payloads against the canonical Draft 2020-12 JSON Schemas and communicates with
the reference server only through HTTP.

The client source does not import Python, `warhammer40k_core.engine`,
`warhammer40k_core.adapters.local_session`, `GameLifecycle`, or
`DecisionController`. The Python process launched by the default test command is
the server under test; process launch and shutdown are outside the client/server
contract exchange.

## Certified scenario

`npm test` launches two clean reference-server processes and runs the same
public setup scenario against each. It asserts:

- administrator authentication, session creation, start, and close;
- player projection/catalog reads and owner/opponent hidden-decision redaction;
- accepted finite-option and deployment-placement proposal round-trips;
- byte-equivalent command retries, stale revision/request rejection, and actor
  authorization;
- malformed request rejection, a live typed unsupported transition boundary,
  and an unavailable-route classification;
- viewer-scoped event pagination with contiguous sequence numbers and forced
  full-projection resynchronization;
- active/terminal replay policy and terminal command handling;
- schema-valid, semantically equivalent replay artifacts with matching canonical
  SHA-256 hashes, source identities, decision/event records, checkpoints, and
  published replay hashes across two independent HTTP executions.

Raw byte equality is required only for an exact idempotent retry against the
same backend. Cross-backend replay comparison parses and schema-validates each
artifact before canonicalization, so JSON property order and insignificant
whitespace are not conformance requirements.

The runner uses the public `contracts/examples/sessions/session-create.json`
fixture, sources player-to-army identity from its muster requests, and constructs
deployment poses from server-published proposal/coordinate values with a neutral
zero-degree facing. It does not derive identity from identifier spelling, apply
rules, or mutate option payloads locally.

Phase 18M-A does not certify a live rejected `rule_path_unsupported` command
response because the public setup scenario has no deterministic route to one.
That backend-executable error case, coach policy, and delayed-spectator policy
remain Phase 18M-B+ work.

## Commands

Node.js 24 and a synchronized project environment are required.

```bash
npm ci
npm run generate
npm run check
npm run test:unit
npm test
```

Run against two clean external implementations with:

```bash
npm run conformance -- \
  --base-url http://127.0.0.1:8000 \
  --comparison-base-url http://127.0.0.1:8001
```

External credentials for the four Phase 18M-A certified principals may replace
the reference development credentials by setting all four variables:

- `CORE_V2_CONFORMANCE_ADMIN_TOKEN`
- `CORE_V2_CONFORMANCE_PLAYER_A_TOKEN`
- `CORE_V2_CONFORMANCE_PLAYER_B_TOKEN`
- `CORE_V2_CONFORMANCE_REPLAY_TOKEN`

`npm run check:generated` regenerates the OpenAPI types in a temporary
directory and fails on drift. The generation adapter removes canonical `$id`
values, maps their absolute local references to sibling schema files, and
extracts `$defs` into temporary referenced schemas so definition containers are
not misgenerated as required wire properties. These transformations exist only
in that temporary copy. The adapter selects the normative 2.0 session
operations and omits deprecated legacy routes plus unused component aliases so
the generated module stays within the repository size budget; it does not alter
or maintain another contract source.
