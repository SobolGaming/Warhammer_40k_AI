# Order114 / P18J / C18-11: source-owned embark without movement

## Source and scope

The immutable Order97 selection contains FAQ
`faq:c2df3e97-f21e-4fc9-943e-37072c08c10e`, answer block2, hash
`3331d006616a0da2fffb9f7111862c71f5498f9385943973130d3dafc08d7a36`.
It confirms embark after disembark for an embarkation that makes no Normal,
Advance or Fall Back move. This is the existing reviewed source observation;
Order114 makes no fresh official-source observation. Original captures, clauses,
gap observations and historical test facts remain unchanged.

The violated invariant was truthful source and decision context: `EmbarkSelection`
required one of those three moves, and the finite producer and restore binding
required its accepted movement completion. Supplying an invented move was the
only representable workaround.

This order repairs the Core permission and decision seam. The FAQ does not define
the named ability's timing, range or faction loading. Those remain the source
provider's responsibility and outside this Core audit. A provider issues an
explicit typed permission for its real source occasion; runtime code never
identifies the ability by display name or source-text parsing. The canonical
fixtures supply that permission explicitly rather than claiming named faction
gameplay support.

## Shared implementation and authority

`transport_embark_context.NoMovementEmbarkContext` records source rule, permission
effect, occasion, rules unit, actual turn owner, round and phase. The extracted
`transport_embark_types.EmbarkSelection` accepts `NOT_MOVED` only with that context.
Ordinary selection still requires its actual Normal, Advance or Fall Back action;
Remain Stationary and Ingress are not substituted.

`transport_source_embark` consumes a current typed persisting permission. Permission
to embark without movement and permission to embark after disembark are distinct.
The source context, owner and overrides must match the permitting effect. The
Movement action-selection consumer can offer that current permission before an
ordinary action; source providers can use the same Core finite-request producer
at the declared occasion. This does not infer or install the named ability's timing.

The existing `select_embark_transport` options, `FiniteOptionSubmission`, engine
dispatch and recorded decision remain authoritative. The source request records
`source_context` instead of `movement_context`. Its current permission, exact
offered options and physical context are revalidated before queue pop. Decline
consumes the occasion and preserves ordinary action selection. Acceptance uses
the shared rules-unit geometry, distance, living-component capacity, friendly
Transport, setup-turn and persisting-restriction validation.

Ordinary and source embark share `transport_embark_mutation`: battlefield removal,
every living attached component's cargo membership, Primary departure evidence,
and `unit_embarked`. Cargo and post-disembark state retain their existing owners.
No synthetic move, witness, Advance/Fall Back state or movement-completion event
is introduced. `transport_source_embark_history` binds the no-movement request,
accepted selection and event; the existing cargo-location history binds its
physical removal and exact carrier membership. Existing witnessed-move bindings
continue to handle ordinary embark.

The ordered failed-setup selection history also consumes accepted source
`unit_embarked` events to close an actually selected Movement unit with zero
distance. This preserves the next passenger's rule-invalid placement retry and
engine-created save/load/replay continuation without manufacturing a move event.

The bug-class search covered the selection constructor, both shared finite option
and acceptance consumers, setup-turn prevalidation, movement-completion history,
cargo-location history, restore and adapter dispatch. Off-battlefield friendly
carriers are skipped through the existing explicit presence query when enumerating
options. Named source loading and manually coordinated history hardening remain
outside this order.

## Evidence and delivery

The existing `tests/unit/test_order61_embark.py` contains the focused regressions;
`tests/order114_embark_helpers.py` supplies canonical objects and legal disembark
proposals. Controls cover ordinary movement requirements, no-movement context
round-trip, actual disembark followed by embark or decline, the distinct
post-disembark permission, stale permission/capacity/distance before queue pop,
and attached-unit removal/cargo authority. Valid engine-created checkpoints,
both viewer projections/event deltas, isolated forks and exact replay are covered.

The original Order97 test and fixture bytes are retained from exact base
`6653b86daf7d1bc51e1d0158691fe640bb3a2a4d` in a bounded hash-checked historical
mapping. They are historical assertions, not new Order114 gameplay evidence.
New implementation evidence lives in the tests and this scope record.
The ordinary embark fixture now seeds nearby poses before Command snapshots;
it no longer changes physical location after those historical snapshots. The
continuation regression checks that its initial checkpoint restores before any
source embark or rejected placement is submitted.

Apply `SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`: block on incorrect rules, normal
legal-play failures, valid engine-created save/load/replay failures and necessary
supported-input boundaries. Queue unrelated coordinated hand-edited-history
hardening separately. Every complete local covered/quality/type/lint/generated/
contract/client/package gate, serial current-runtime smoke, both distinct exact-head
reviews, full required CI and protected merge remains mandatory. The repair is an
ordinary rule/permission branch change, not a performance optimization or full-game
performance certification. Refresh the successful complete JUnit profile only
after the runtime/tests freeze; metadata-only successors require renewed exact-head
bindings and narrow reviews, without a duplicate full behavioral run.

Every subsequent implementation must update its roadmap **How it is currently
done** cell with the actual implementation before the final input freeze and
carry this requirement into the handoff. Stop before Order115 for a fresh session.
