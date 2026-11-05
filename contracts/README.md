# CORE V2 external contract

The current language-neutral bundle is Contract **45.0.0**. Start with
`openapi.yaml`, the canonical schemas and schema-validated examples. The
[adapter decision contract](../docs/ADAPTER_DECISION_CONTRACT.md) defines current
choice, projection, visibility and replay semantics. The
[compatibility policy](compatibility-policy.md) preserves released baselines and
all deployment-retention obligations.

## Integrating a client

- Generate models from the current OpenAPI and Draft 2020-12 schemas. Respect each
  payload family's explicit `schema_version`; bundle and family versions are separate.
- Use engine-authored pending decisions, option IDs, proposal schemas and spatial
  context. Submit choices through the shared session command path.
- Refresh viewer-scoped projections and pending requests after reconnect/resync.
  Hidden information, diagnostics and events remain principal- and viewer-scoped.
- Preserve physical model/weapon identities and canonical rules-unit membership.
  Do not infer missing history when loading saves or replays from older runtimes.
- The reference server supports one contract major per deployment, without
  content negotiation. Retain old deployments for the support windows in the
  compatibility policy.

Contract 45's `error-envelope-v2-diagnostics` includes optional typed diagnostic
codes/nullable fields for an authenticated current-request owner's uncommitted
rejection. Other viewers retain generic denial. Uncommitted rejection preserves
state, revision and pending request for retry; recorded-invalid HTTP 422 advances
the revision and provides a fresh request. See the
[session semantics](session-semantics.md) and [adapter contract](../docs/ADAPTER_DECISION_CONTRACT.md).

Completed migration narratives remain in Git history and their original PRs;
current integrations use the maintained references above. This does not change
any compatibility baseline, support window, payload version or runtime behavior.

## Layout

- `openapi.yaml`: OpenAPI 3.1 description of the reference HTTP transport.
- `schemas/`: canonical Draft 2020-12 payload schemas.
- `examples/`: schema-validated projections, decisions, events, errors,
  lifecycle statuses, support profiles, replay artifacts, and an operator-only
  persistence artifact.
- `compatibility/`: committed public-shape baseline used by the breaking-change
  audit.
- `conformance-scenarios/`: transport-neutral client behavior requirements.
- `manifest.json`: deterministic file hashes, schema/example bindings, and
  decision/proposal coverage.

## Verification

Run:

```bash
uv run --no-sync python scripts/build_engine_build_identity.py --check
uv run --no-sync python scripts/build_external_contract.py --check
```

The first check fails when the generated runtime-resource inventory or any
packaged Python/JSON/schema content drifts. The contract check fails if schemas
are invalid, examples drift, OpenAPI references a
non-canonical definition, registered decision metadata or proposal coverage
drifts, a bundle hash changes without regeneration, or a breaking public-shape
change is made without the required contract-version change. Pull-request CI
also passes the base commit with `--base-ref`. The audit compares the proposed
schemas and OpenAPI operations with both that exact base contract and the oldest
supported-major baseline, then separately proves released baselines are
immutable.

The packaging gate builds and installs the wheel into an isolated environment,
runs outside the repository, enumerates all packaged schemas, and validates
representative session-create, session-command, engine-create, finite, and
parameterized requests:

```bash
uv run --no-sync python scripts/smoke_installed_contract_wheel.py
```

To refresh deterministic fixtures and the manifest after an intentional
compatible change:

```bash
uv run python scripts/build_engine_build_identity.py
uv run python scripts/build_external_contract.py
```

The build-identity generator runs first because session/support-profile examples
publish its verified immutable runtime-tree ID.

The manifest also hashes every Markdown file under `contracts/`, including this
README and the maintained semantic policies. Regenerate the contract bundle after the final
documentation edit, then run the exact-base check before pushing. Documentation
changes outside the packaged runtime do not require a new engine build identity.

`--write-baseline --base-ref <sha>` writes the first baseline of an explicitly
reviewed compatibility major. It may refresh that baseline until it appears on
the base commit, then refuses to overwrite it or add another baseline within
the same major. See
[compatibility-policy.md](compatibility-policy.md).
