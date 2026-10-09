"""Bind accepted overrides to their original roll and recorded resource effect.

Historical authority uses the accepted prefix, never later balances or expired
source availability. A choice may be saved before its owning step completes.
"""

from __future__ import annotations

# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceRollState
from warhammer40k_core.engine.attack_sequence_model import (
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice_result_overrides import (
    DICE_RESULT_OVERRIDE_DECISION_TYPE,
    _context_fingerprint_without_stored,
    _request_payload,
)
from warhammer40k_core.engine.dice_roll_history import latest_roll_state
from warhammer40k_core.engine.event_log import EventLog, EventRecord, JsonValue, canonical_json
from warhammer40k_core.engine.gathered_dice_occurrence import unresolved_dice_occurrence
from warhammer40k_core.engine.lifecycle_state_queries import active_attack_sequence_for_state
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_dice_result_override_history(
    *, state: GameState, decisions: DecisionController
) -> None:
    events = decisions.event_log.records
    for record in decisions.records:
        request, result = record.request, record.result
        if request.decision_type != DICE_RESULT_OVERRIDE_DECISION_TYPE:
            continue
        payload = _request_payload(request)
        if payload["context_fingerprint"] != _context_fingerprint_without_stored(payload):
            raise GameLifecycleError("Recorded override context fingerprint drift.")
        issued = _one(events, "decision_requested", "request_id", request.request_id)
        accepted = _one(events, "decision_recorded", "record_id", record.record_id)
        if (
            canonical_json(events[issued].payload) != canonical_json(request.to_payload())
            or (canonical_json(events[accepted].payload) != canonical_json(record.to_payload()))
            or issued >= accepted
        ):
            raise GameLifecycleError("Recorded override request/acceptance drift.")
        prefix = DecisionController(
            event_log=EventLog.from_payload([event.to_payload() for event in events[:issued]])
        )
        original = latest_roll_state(decisions=prefix, roll_id=payload["roll_id"])
        if original != DiceRollState.from_payload(payload["roll_state"]):
            raise GameLifecycleError("Recorded override physical roll prefix drift.")
        spec = original.original_result.spec
        if payload["roll_type"] == "hit":
            expected_spec = attack_sequence_hit_roll_spec(
                weapon_profile_id=payload["weapon_profile_id"],
                attack_context_id=payload["attack_context_id"],
                attacker_player_id=cast(str, request.actor_id),
                reroll_forbidden_rule_ids=spec.reroll_forbidden_rule_ids,
            )
        elif payload["roll_type"] == "wound":
            expected_spec = attack_sequence_wound_roll_spec(
                weapon_profile_id=payload["weapon_profile_id"],
                attack_context_id=payload["attack_context_id"],
                attacker_player_id=cast(str, request.actor_id),
            )
        else:
            raise GameLifecycleError("Recorded override has an invalid step.")
        if spec != expected_spec or payload["roll_spec_type"] != spec.roll_type:
            raise GameLifecycleError("Recorded override owning physical spec drift.")
        common: dict[str, JsonValue] = {
            "request_id": request.request_id,
            "result_id": result.result_id,
            "roll_id": payload["roll_id"],
            "attack_context_id": payload["attack_context_id"],
            "source_rule_id": payload["source_rule_id"],
        }
        if result.selected_option_id == "decline":
            effect = _one(events, "dice_result_override_declined", "request_id", request.request_id)
            expected = original
            expected_payload = common
        elif result.selected_option_id == "use":
            effect = _one(events, "dice_result_overridden", "request_id", request.request_id)
            expected = original.with_result_override(
                decision_id=result.result_id,
                request_id=request.request_id,
                source_rule_id=payload["source_rule_id"],
                replacement_value=payload["replacement_value"],
            )
            assert expected.result_override is not None
            expected_payload = {
                **common,
                "roll_type": payload["roll_type"],
                "attacker_model_instance_id": payload["attacker_model_instance_id"],
                "source_component_unit_instance_id": payload["source_component_unit_instance_id"],
                "critical_trigger_markers": cast(JsonValue, payload["critical_trigger_markers"]),
                "override_record": cast(JsonValue, expected.result_override.to_payload()),
                "updated_roll_state": cast(JsonValue, expected.to_payload()),
            }
            spend = _one(events, "unit_resource_spent", "decision_request_id", request.request_id)
            raw = events[spend].payload
            if not isinstance(raw, dict) or not accepted < spend < effect:
                raise GameLifecycleError("Recorded override resource effect order drift.")
            fields = {
                "player_id": request.actor_id,
                "unit_instance_id": payload["source_component_unit_instance_id"],
                "resource_kind": payload["resource_kind"],
                "transaction_kind": "spend",
                "requested_amount": payload["resource_cost"],
                "applied_amount": payload["resource_cost"],
                "source_rule_id": payload["source_rule_id"],
                "status": "applied",
                "decision_result_id": result.result_id,
            }
            if any(
                canonical_json(raw.get(key)) != canonical_json(value)
                for key, value in fields.items()
            ):
                raise GameLifecycleError("Recorded override resource association drift.")
            transactions = [
                transaction.to_payload()
                for ledger in state.unit_resource_ledgers
                for transaction in ledger.transactions
                if transaction.decision_request_id == request.request_id
            ]
            if len(transactions) != 1 or canonical_json(transactions[0]) != canonical_json(
                raw.get("transaction")
            ):
                raise GameLifecycleError("Recorded override resource ledger association drift.")
        else:
            raise GameLifecycleError("Recorded override finite choice is invalid.")
        if effect <= accepted or canonical_json(events[effect].payload) != canonical_json(
            expected_payload
        ):
            raise GameLifecycleError("Recorded override effect association drift.")
        steps = [
            (index, event.payload)
            for index, event in enumerate(events)
            if event.event_type == "attack_sequence_step"
            and isinstance(event.payload, dict)
            and event.payload.get("sequence_id") == payload["sequence_id"]
            and event.payload.get("attack_context_id") == payload["attack_context_id"]
            and event.payload.get("step") == payload["roll_type"]
        ]
        if len(steps) == 1:
            index, step = steps[0]
            raw_step = step.get("payload")
            if (
                index <= effect
                or not isinstance(raw_step, dict)
                or (
                    canonical_json(raw_step.get("roll_state"))
                    != canonical_json(expected.to_payload())
                )
                or type(step.get("attack_index")) is not int
                or step.get("attack_index") != payload["attack_index"]
            ):
                raise GameLifecycleError("Recorded override completed owning step drift.")
        elif not steps:
            host = active_attack_sequence_for_state(state)
            if host is None or host.sequence_id != payload["sequence_id"]:
                raise GameLifecycleError("Unfinished override has no active owner.")
            current = unresolved_dice_occurrence(sequence=host, events=events)
            if (
                current.sequence.attack_context_id() != payload["attack_context_id"]
                or current.step != payload["roll_type"]
            ):
                raise GameLifecycleError("Unfinished override occurrence drift.")
        else:
            raise GameLifecycleError("Recorded override has duplicate owning steps.")


def _one(events: tuple[EventRecord, ...], kind: str, key: str, value: str) -> int:
    matching = [
        index
        for index, event in enumerate(events)
        if event.event_type == kind
        and isinstance(event.payload, dict)
        and event.payload.get(key) == value
    ]
    if len(matching) != 1:
        raise GameLifecycleError(f"Override history requires one {kind} event.")
    return matching[0]
