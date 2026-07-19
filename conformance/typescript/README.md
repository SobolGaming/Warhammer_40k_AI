# Phase 18M-A TypeScript conformance client

This package is the first executable backend-conformance slice for the CORE V2
2.0 HTTP/OpenAPI contract. The client is generated and compiled from
`contracts/openapi.yaml`, validates wire payloads against the canonical Draft
2020-12 JSON Schemas, and communicates with the reference server only through
HTTP.

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
  an unavailable-route classification, and the canonical
  `rule_path_unsupported` error shape;
- viewer-scoped event pagination with contiguous sequence numbers and forced
  full-projection resynchronization;
- active/terminal replay policy and terminal command handling;
- byte-equivalent replay artifacts and matching SHA-256 hashes from two
  independent HTTP executions.

The runner uses the public `contracts/examples/sessions/session-create.json`
fixture and constructs deployment poses from the server-published proposal and
coordinate values. It does not apply rules or mutate option payloads locally.

## Commands

Node.js 24 and a synchronized project environment are required.

```bash
npm ci
npm run generate
npm run check
npm test
```

Run against two clean external implementations with:

```bash
npm run conformance -- \
  --base-url http://127.0.0.1:8000 \
  --comparison-base-url http://127.0.0.1:8001
```

External credentials may replace the reference development credentials by
setting all four variables:

- `CORE_V2_CONFORMANCE_ADMIN_TOKEN`
- `CORE_V2_CONFORMANCE_PLAYER_A_TOKEN`
- `CORE_V2_CONFORMANCE_PLAYER_B_TOKEN`
- `CORE_V2_CONFORMANCE_REPLAY_TOKEN`

`npm run check:generated` regenerates the OpenAPI types in a temporary
directory and fails on drift. The generation adapter removes canonical `$id`
values and maps their absolute local references to sibling schema files only in
that temporary copy. It selects the normative 2.0 session operations and omits
the deprecated legacy routes plus unused component aliases so the generated
module stays within the repository size budget; it does not alter or maintain
another contract source.
