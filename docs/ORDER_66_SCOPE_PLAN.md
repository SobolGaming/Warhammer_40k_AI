# Order 66 / P23: Aircraft

Finding: C23-01. Base: `48b691133ee89fa9ff7495c9157f1cad9aad8131`
(Order 65, PR #485). The prerequisite orders are merged.

## Invariant and source

Core 23.01-23.04 gives Aircraft an ingress-only lifecycle. All Aircraft start
in Strategic Reserves and every battlefield Aircraft returns at its opponent's
turn end. The previous ordinary-move/edge-exit route and Hover keyword removal
violated that invariant. Canonical rules units own restrictions; individual
model keywords own transit and the restriction on melee attacks against Aircraft.

The complete four operative statements are retained from the 40k.app search
index observed on 2026-09-20 at 14:34:15 UTC. Direct retrieval returned HTTP 403.
No App build or cross-mirror agreement is claimed. The reviewed JSON package,
transcription hashes, observation fingerprint and source-authority registration
use the approved maintained-mirror policy. This does not claim official GW
hosting; historical official artifacts retain their original provenance.
`uv run python tools/build_core_aircraft_source.py --check` reproduces the data.
The existing Order 51 and Core ability sources continue to own FLYING and Hover.

## Authoritative path and bug-class search

Formation setup -> canonical rules-unit reserve declaration -> existing ingress
finite choice/placement validation -> battlefield presence -> mandatory END_TURN
sequencing -> core engine reserve/departure mutation -> source event and Primary
mutation receipts -> viewer projections, persistence and replay authentication.

The boundary binding is composed in the shared Core registry for ordinary and
faction-loaded sessions. It uses the existing mandatory sequencing participant;
there is no new named content handler, generic hook family or client mutation.
It returns all Aircraft owned by the opponent, preserves embarked cargo, removes
all physical components and records one occurrence per canonical Aircraft. The
existing during-battle reserve deadline policy applies; no invented next-round
arrival requirement is added. Restore binds the exact source event, owner/turn,
components/models, reserve state and selected timing participant to its receipt.

The same bug-class search covered ordinary, reactive, charge, fight, Scout,
mutation and history paths. Shared movement locks reject non-ingress activity;
low-level movement owners also fail closed. All movement path owners pass
individual AIRCRAFT model identities for transit, keeping endpoint collision and
engagement constraints. Non-FLY pile-in/consolidation/Surge target and closest
selection share one keyword predicate. Normal/Advance remain legal when engaged
solely with Aircraft. Charge eligibility uses unit FLY; melee eligibility uses
attacker-unit and individual attacking-model FLY as required. This is independent
of the per-move Take to the Skies choice. Existing terrain and Towering Plunging
Fire exclusions are certified by additional consumer assertions.

Legacy Hover state, its serialization and all movement plumbing are removed.
Hover retains AIRCRAFT; the existing flight-distance exemption remains. The old
20-inch override and edge-exit implementation and obsolete tests are retired.
Existing retained-destruction transit tests continue to cover ordinary movers;
a former Aircraft-moving fixture is replaced by an explicit ingress-only test.

## Architecture and contract audit

Before aggregate gates, the diff was reviewed against the category-23 invariant.
The broad file count primarily removes the shared Hover parameter/state from
callers. Fight path validation, Scout path validation and mandatory Aircraft
formation declarations were extracted before extension. Oversized module caps
shrink; no architecture boundary, fallback, engine stub or faction branch is
introduced. Physical removal continues through the established Primary departure
and reserve mutation receipt owners; static provenance inventories move to the
new mandatory turn-end owner.

Contract 32 documents the retired fields and movement semantics, source-linked
public departure event, private restore receipts and unchanged submission
families. See [31-to-32](../contracts/migrations/31-to-32.md) and the Order 66
section of [the adapter contract](ADAPTER_DECISION_CONTRACT.md). Released
baselines are retained. The engine manifest, schemas/examples, new-major baseline
and TypeScript client are generated from the final runtime.

## Proof and validation

Regressions in `test_phase10r_aircraft.py` cover ordinary-action exclusion,
retained Hover identity, opponent versus own turn, all-aircraft return, exact
lifecycle/persistence restore and both viewer projections/event deltas, forged
source rejection, return followed by ingress, cargo preservation, unit versus
individual model FLY targeting, all movement modes' transit/endpoint distinction,
and direct ordinary/charge/fight mutation guards. Reactive movement, existing
Hover flight behavior, secret initial reserves and both Plunging Fire consumers
are covered in their existing test modules. No behavioral test file was added,
deleted or renamed; the eight-shard inventory check remains required.

The component assessment and final gate outcomes are recorded in
[performance/order66/README.md](performance/order66/README.md). Full-game
performance and final cross-category certification remain separate obligations.

The final caller audit distinguished individual-model transit from engagement
with an AIRCRAFT rules unit. A regression with only the non-AIRCRAFT model in
engagement first reproduced the eligibility error; classification now reads the
canonical enemy rules unit while transit retains individual model IDs. An unused
unit-wide transit-ID accessor was retired. The earlier aggregate attempt was
cancelled when this issue was found; final coverage, identities and performance
evidence are rerun for the corrected runtime rather than reused.

The first completed coverage run reached 85.12% with 8,496 passes and two
obsolete expectations outside the Aircraft test module: an ordinary Aircraft
rotation move and an edge-exit reserve lifecycle. The former now requires an
invalid move while retaining its distance/rotation evidence assertions. The
latter retains its provider, origin, transition, removal and source tamper checks
using the canonical facade-driven mandatory turn-end fixture. Return/ingress
cycles remain covered by the Aircraft facade regression. Both migrated tests
passed before repeating the complete coverage gate; production and measured
runtime identity did not change.

The first full quality run found two stale static inventory entries and the
existing Order 35 Rapid Ingress work budget detected four redundant canonical
view lookups in movement candidate enumeration. The lock owner now accepts the
canonical view already built by enumeration, retaining the scenario's destroyed
model presence. The ID-based entry point still resolves its own authoritative
view. All 73 focused Aircraft, geometry/source inventory and Rapid Ingress work
checks passed with the existing budgets unchanged. This narrow production repair
requires fresh head timing, generated identities/contracts and aggregate gates;
the earlier passing behavioral result is retained as diagnostic evidence only.

Final validation on runtime `57d311ec` passed all 8,498 behavioral tests with
85.13% coverage and all 551 code-quality tests using 64-worker work stealing.
Ruff, both type checkers, all 11 import contracts, pre-commit, shard inventory,
source/identity generators, exact-base contract compatibility, installed wheel,
TypeScript checks and all 342 conformance assertions passed. The committed
`performance/order66/validation.json` records exact counts, report hashes and
qualified performance limitations.
