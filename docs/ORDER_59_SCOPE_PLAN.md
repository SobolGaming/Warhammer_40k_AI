# Order 59 / P18A — empty Dedicated Transports die at formation reveal

## Invariant and source

At the end of Declare Battle Formations, every Dedicated Transport model without
an embarked unit is destroyed and removed. That destruction does not trigger
rules that trigger when a model is destroyed. An empty Dedicated Transport must
not remain as a delayed battle-round-1 unavailable/setup consequence.

The complete 18.01 operative text was retrieved from the 40k.app Transports
page. The separate `gw-11e-core-empty-dedicated-transport` source package
records the complete wording, reviewed obligations, immutable observation and
package hashes, typed destruction policy, execution consumers, and the
historical official Core Rules source hash. The maintained-mirror source policy
and registry authorize this Core-Rules-only observation. No second-provider
agreement is asserted.

## Ownership and proof

`engine.empty_dedicated_transport_destruction` owns the source-authorized
mutation. It destroys unplaced models through
`destroy_unplaced_model_without_reactions` and removes them through
`GameState.replace_battlefield_state`. `SetupFlow.advance` remains the
setup-step owner: after splits, mandatory Aircraft reserves, battle-formation
hooks, and reserve declarations are complete, it applies empty-Dedicated-Transport
destruction before completing Declare Battle Formations and emitting
`battle_formations_revealed`. Empty-manifest setup consequences stay
owner-secret until that reveal. The public `empty_dedicated_transports_destroyed`
event carries the 18.01 source rule ID and `destroyed_model_rules_triggered: false`.
Setup completion requires those models to be destroyed and removed. No new
player-facing decision, named handler, or alternative mutation path is
introduced.

## Audit and scope

The bug-class search found one delayed empty-Dedicated-Transport owner: the
muster-time `DedicatedTransportSetupConsequence` whose kind encoded
first-battle-round destruction without applying it. That record now names
no-trigger destruction. The live mutation scans every Dedicated Transport
without embarked cargo at the formation boundary, including empty manifests.
Cargo-filled Dedicated Transports are unchanged. Strategic-reserve deadline
destruction and coherency cleanup remain separate no-trigger families.

## Validation and contract

Regressions cover immediate no-trigger destruction at Declare Battle Formations,
preservation of embarked Dedicated Transports, owner rejection outside that
setup step, adapter viewer-scoped event streams, GameState restore, and
`GameLifecycle` restore through local session forks, persistence reload, and
server command snapshots. Unrelated setup wound changes remain rejected.
This PR adds no option family, proposal kind, or visibility change.
See [performance and final gates](performance/order59/README.md).

Reproduce the source with
`uv run python tools/build_core_empty_dedicated_transport_source.py --check`.
