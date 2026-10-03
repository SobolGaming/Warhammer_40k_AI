# Order 110 / P16C: Actions and Battle-shock

This order implements C16-04. Becoming Battle-shocked immediately interrupts a
started Action unless the unit has an explicit rule allowing it to start Actions
while Battle-shocked. Clearing Battle-shock later cannot revive the Action.
Permission does not remove other eligibility conditions, the Action's shooting
and charge restrictions, movement interruption, or mission completion conditions.

## Source and scope

The maintained App mirror observation is pinned in
`data/source_audits/order97/selected-sources.json`:

- `faq:bbe268a2-b1fd-43ab-8b24-fd4363730c3f`, source SHA-256
  `1912cbae65dddd8e8799e7e7a82a5ec5984533152aae9239745831f9dfed89ae`:
  becoming Battle-shocked stops an Action already started.
- `faq:4c654d00-318d-4665-9e46-26cfab179a29`, source SHA-256
  `fef99387330cc3df5d34f0f94c59f49ddd403bffc2bb46936e4b80d8214f46bb`:
  an explicit shocked-start rule also permits continuation after later shock.
- Core 16.01, source SHA-256
  `9ace4fc09f4a890c9ed17ace0ba98e9863db6dff5f73eb55e767db04805c573d`,
  retains its independent eligibility, restrictions and completion conditions.

The two FAQ answer blocks both have SHA-256
`184fda5c980b9d9cb375f42a528817c6235fbd4f79775a8018fae5afcbdf2a63`.
The original Order97 inventory, paraphrases, assertions and historical evidence
remain unchanged. This order does not claim complete Core Rules certification.

## Shared owners

`battle_shock_state.apply_direct_battle_shock_state` owns newly applied status
for failed tests and direct Super-heavy Walker completion results. It immediately
delegates Action interruption to `primary_mission_action_interruptions` before
Battle-shock outcome hooks run. Ordinary and attached rules units use the same
lineage query. A repeated application to an already shocked unit does not create
a new transition. Domain state-only calls also interrupt immediately; eventful
engine producers pass their real DecisionController and record source evidence.

The shared interruption owner emits `mission_action_battle_shock_applied` and the
existing `mission_action_interrupted` terminal event, carrying the source result,
affected identities and FAQ source ID. Movement and Battle-shock share the
terminal event writer. The new core interruption reason is `unit_battle_shocked`;
it applies independently of a mission's additional interruption conditions.

The existing catalog RuleIR `GRANT_ABILITY` surface represents an explicit
`can_perform_actions_while_battle_shocked` permission. The supported consumer is
an unconditional, permanent `THIS_UNIT` datasheet grant. It requires a present
source component and consumes structured source identity, never display text.
Other clause shapes do not acquire this consumer. The test catalog instantiates
the FAQ's conditional premise; it is not a claim that any faction datasheet has
that rule. No new named handler, generic hook registry or faction support is added.

Start enumeration, accepted starts and immediate completion use the shared
permission query. Historical start validation supplies its authenticated present
model inventory. Later completion uses terminal Action state: a stopped Action
cannot complete even after its status clears, while a permitted continuing
Action still has to satisfy its actual source effect conditions. The permission
does not supply positive OC or objective control.

## Delivery and limits

The regression first reproduced an attached Cleanse Action remaining STARTED
after failed Battle-shock. Focused tests cover ordinary and attached identities,
primary and secondary Actions, explicit permission, unchanged activity locks,
movement interruption and persistence/replay through the common facade.
The external Order110 evidence directory retains actual attempts and receipts;
required aggregate gates and two exact-head reviews remain merge requirements.

The exact-base performance assessment selects the required serial current-runtime
smoke under the owner's sequential policy. This is an ordinary rule correction;
no deliberate performance change or full-game performance certification is claimed.
Historical measurements remain unchanged.

After Order110 merges, stop. Order111 starts in a fresh session. Every subsequent
order must update its own roadmap **How it is currently done** cell to the actual
implementation, preserving unrelated rows and historical evidence.
