# Trigger Opportunity Windows

CORE V2 handles optional triggered abilities, Stratagems, rerolls, and similar
opportunistic rules through one deterministic engine path:

1. The engine reaches a supported timing point.
2. Rule handlers enumerate the legal actions for the eligible player or players.
3. Those actions are exposed as an `OpportunityWindow` and a normal
   `DecisionRequest`.
4. Adapters return a normal `DecisionResult`.
5. The lifecycle validates and mutates through the existing engine-owned path.

This keeps CLI, UI, headless AI, network clients, replay, and tests synchronized.
Adapters may differ in presentation and policy, but not in legality, mutation,
or replay records.

## Engine Contract

`src/warhammer40k_core/engine/opportunity_windows.py` provides the shared
envelope types:

- `OpportunityWindow`: the timing-window wrapper with stable state hash,
  sequence number, revision, anchor events, eligible players, priority order,
  legal actions, default pass action, and close condition.
- `OpportunityLegalAction`: one engine-enumerated legal action. It can represent
  a Stratagem, ability, reroll, reaction, side action, or pass. Its payload is
  JSON-safe and can describe batched targets such as a whole attack sequence or
  one roll inside a roll group.
- `TriggerBatchingMode`: the action's batching semantics. Fast rolling remains
  an optimization only; if a rule requires atomic timing, the host must split the
  roll group or use `none`.
- `WindowPass` and `WindowPassLedger`: deterministic pass-loop suppression keyed
  by window ID, player, revision, and legal-action fingerprint.
- `InterfaceIntent`: a UI/CLI/network captured intent that can become a
  `DecisionResult` only when the current pending request matches the intended
  window, timing, state hash, source, action, and targets.

Opportunity windows do not mutate state by themselves. They produce request
payloads and option payloads that later flow through `GameLifecycle.submit_decision(...)`.
Lifecycle validation is keyed to the request payload's
`submission_family: "opportunity_window"` envelope, not to a specific
`decision_type`, so reaction, ability, Stratagem, reroll, and side-action hosts
share the same stale-state, sequence, window, fingerprint, drift, wrong-player,
and malformed-submission checks.

## Adapter Behavior

Human adapters should render "available now" controls instead of repeatedly
asking modal yes/no questions. A GUI can show a reaction tray or enabled
Stratagem button. A CLI can show the current opportunity count and list actions
on demand. A headless AI receives the same legal actions as structured data.

Adapters may capture proactive human input as an `InterfaceIntent`, for example
"use Smoke on Unit 17 until the end of this Shooting step." That capture is not
authoritative. The intent is rejected if it is stale, expired, wrong-context, or
not currently legal. If it does match the active pending request, it materializes
as an ordinary `DecisionResult`.

Policy-driven auto-pass and auto-use behavior belongs in the adapter or agent
layer. The engine still opens the same windows and records the same decisions.
Prompt suppression means the agent submitted pass; it must never mean the
opportunity did not exist.

## Priority and Replay

When both players can act, the opportunity window carries the deterministic
priority order. Hosts resolve players in that order, recompute legal actions
after state changes, and close the window only when the rules-defined close
condition is satisfied.

Replay should consume recorded `DecisionResult` payloads. It should verify that
the same opportunity request, state hash, option ID, and legal-action
fingerprint are reproduced. It should not ask a UI or AI to choose again.

## Command Re-roll Hosts

Command Re-roll remains answered as an ordinary finite `use_stratagem`
submission, but attack-resolution hosts wrap that request in an
`OpportunityWindow` envelope. Shooting and Fight surface the window immediately
after eligible Hit, Wound, real Save, and random Damage rolls. The request
payload carries `submission_family: "opportunity_window"`, the window payload,
the window ID, the boundary state hash, the boundary sequence number, anchor
event IDs, and the legal-action fingerprint. Each use or decline option carries
a matching nested `opportunity_submission` payload.

`GameLifecycle.submit_decision(...)` validates the opportunity envelope before
queue pop, CP spend, reroll mutation, or decline recording. A stale state hash,
stale sequence number, wrong window ID, changed legal-action fingerprint, wrong
player, unavailable action, or malformed opportunity payload returns typed
invalid diagnostics and leaves the pending request unresolved. The host records
the original dice state, opens the optional Stratagem window, and then resumes
from the event-log state after decline or accepted reroll.

For wound rolls with native weapon rerolls such as Twin-linked, the attack
sequence opens Command Re-roll at the failed wound timing first. If the player
declines Command Re-roll, the native reroll permission resolves next and the
same original wound roll does not immediately reopen a duplicate Command
Re-roll prompt.

Adapters must not apply a reroll locally or infer eligibility from displayed
roll text. They submit the engine-emitted `use_stratagem` option or the decline
option, and any nested `select_dice_reroll` option when a multi-die eligible roll
requires component selection.
