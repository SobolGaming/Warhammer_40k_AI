"""Bind model-profile evaluation occurrences to their owning engine rule boundaries."""

from __future__ import annotations

import re
from typing import cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.random_attack_authority import validate_generated_profile_attack


def validate_profile_scope(
    *,
    state: GameState,
    scope: str,
    unit_id: str,
    player_id: str,
    characteristic: Characteristic,
    body: dict[str, JsonValue],
    events: tuple[EventRecord, ...],
    prior_events: tuple[EventRecord, ...],
    requests: tuple[DecisionRequest, ...],
) -> None:
    if characteristic is Characteristic.MOVEMENT:
        return  # The movement authority additionally checks the accepted selection.
    battle_round, turn_player, phase = body["battle_round"], body["turn_player_id"], body["phase"]
    if type(battle_round) is not int or battle_round < 0:
        raise GameLifecycleError("Random profile evaluation round is invalid.")
    if phase is not None and (
        type(phase) is not str or phase not in {item.value for item in BattlePhase}
    ):
        raise GameLifecycleError("Random profile evaluation phase is invalid.")
    if phase is not None and (type(turn_player) is not str or turn_player not in state.player_ids):
        raise GameLifecycleError("Random profile evaluation turn owner is invalid.")
    if characteristic is Characteristic.WOUNDS and scope.startswith("muster-wounds:"):
        if phase is not None or not any(
            scope == f"muster-wounds:{army.army_id}"
            and army.player_id == player_id
            and unit_id in {unit.unit_instance_id for unit in army.units}
            for army in state.army_definitions
        ):
            raise GameLifecycleError("Random Wounds muster occurrence is invalid.")
        return
    if characteristic is Characteristic.WOUNDS and scope.startswith("materialization-wounds:"):
        matching = [
            request
            for request in requests
            if request.decision_type == "submit_catalog_model_materialization_placement"
            and isinstance(request.payload, dict)
            and scope == f"materialization-wounds:{request.payload.get('roll_event_id')}"
            and request.payload.get("source_unit_instance_id") == unit_id
            and request.actor_id == player_id
        ]
        if not matching or not any(
            event.event_type == "catalog_model_materialization_roll_resolved"
            and scope == f"materialization-wounds:{event.event_id}"
            and isinstance(event.payload, dict)
            and event.payload.get("successful") is True
            and event.payload.get("source_unit_instance_id") == unit_id
            for event in prior_events
        ):
            raise GameLifecycleError("Random Wounds lacks its materialization occurrence.")
        return
    if characteristic is Characteristic.TOUGHNESS and scope.startswith("stratagem-use:"):
        entries = body.get("entries")
        for event in prior_events:
            use = event.payload
            if event.event_type != "stratagem_used" or not isinstance(use, dict):
                continue
            binding, selection = use.get("target_binding"), use.get("effect_selection")
            if (
                scope == f"stratagem-use:{use.get('use_id')}:toughness"
                and use.get("player_id") == player_id
                and isinstance(binding, dict)
                and binding.get("target_unit_instance_id") == unit_id
                and isinstance(selection, dict)
                and isinstance(entries, list)
                and len(entries) == 1
                and isinstance(entries[0], dict)
                and entries[0].get("model_instance_id") == selection.get("model_instance_id")
            ):
                return
        raise GameLifecycleError("Random Toughness lacks its selected Stratagem use.")
    if characteristic in {
        Characteristic.TOUGHNESS,
        Characteristic.WOUNDS,
        Characteristic.SAVE,
        Characteristic.INVULNERABLE_SAVE,
    }:
        match = re.fullmatch(
            r"(.+):pool-([0-9]+):(?:attack-([0-9]+)(?::generated-hit-([0-9]+))?|save-profiles(?::.+)?)",
            scope,
        )
        if match is None or int(match[2]) < 1 or (match[3] is not None and int(match[3]) < 1):
            raise GameLifecycleError("Random defensive profile attack occurrence is invalid.")
        if (characteristic is Characteristic.TOUGHNESS) != (match[3] is not None):
            raise GameLifecycleError("Random defensive profile timing drifted.")
        if match[3] is not None:
            validate_generated_profile_attack(
                sequence_id=match[1],
                pool_index=int(match[2]) - 1,
                attack_index=int(match[3]) - 1,
                generated_hit_number=None if match[4] is None else int(match[4]),
                events=prior_events,
            )
        for event in reversed(prior_events):
            payload = event.payload
            if not isinstance(payload, dict) or event.event_type not in {
                "shooting_declaration_accepted",
                "out_of_phase_shooting_declaration_accepted",
                "melee_declaration_accepted",
                "target_replacement_resolved",
            }:
                continue
            sequence = (
                payload.get("attack_sequence_id")
                if event.event_type != "shooting_declaration_accepted"
                else f"attack-sequence:{payload.get('result_id')}"
            )
            if event.event_type == "target_replacement_resolved":
                context = payload.get("context")
                sequence = context.get("action_id") if isinstance(context, dict) else None
            if sequence != match[1]:
                continue
            pools = payload.get("attack_pools")
            if isinstance(pools, list):
                index = int(match[2]) - 1
                if index >= len(pools) or not isinstance(pools[index], dict):
                    break
                pool = cast(dict[str, JsonValue], pools[index])
                if pool.get("target_unit_instance_id") != unit_id:
                    break
                attacks = pool.get("attacks")
                if match[3] is not None and (type(attacks) is not int or int(match[3]) > attacks):
                    break
                return
        raise GameLifecycleError("Random defensive profile lacks its declared attack target.")
    if characteristic is Characteristic.LEADERSHIP:
        for event in events:
            payload = event.payload
            if not isinstance(payload, dict):
                continue
            if (
                payload.get("unit_instance_id") == unit_id
                and payload.get("player_id") == player_id
                and scope
                == ":".join(
                    (
                        "leadership-test",
                        str(payload.get("attack_sequence_completed_event_id")),
                        str(payload.get("effect_id")),
                    )
                )
                and "leadership_target" in payload
                and any(
                    prior.event_id == payload.get("attack_sequence_completed_event_id")
                    and prior.event_type == "attack_sequence_completed"
                    for prior in prior_events
                )
            ):
                return
            for row in _objects(payload):
                if (
                    row.get("request_id") == scope
                    and row.get("unit_instance_id") == unit_id
                    and row.get("player_id") == player_id
                    and "leadership_target" in row
                ):
                    return
            if (
                payload.get("target_unit_instance_id") == unit_id
                and payload.get("target_player_id") == player_id
                and scope
                == (
                    f"{payload.get('movement_action_result_id')}:"
                    f"{payload.get('timing_participant_id')}"
                )
                and "leadership_target" in payload
            ):
                return
            if (
                payload.get("test_kind") == "leadership"
                and payload.get("source_unit_instance_id") == unit_id
                and payload.get("player_id") == player_id
                and scope
                == (
                    f"{payload.get('runtime_event_id')}:{payload.get('source_rule_id')}:"
                    f"{payload.get('source_model_instance_id')}"
                )
            ):
                return
        raise GameLifecycleError("Random Leadership lacks its test occurrence.")
    if characteristic is Characteristic.OBJECTIVE_CONTROL:
        if phase is None or battle_round < 1:
            raise GameLifecycleError("Random OC requires a battle boundary.")
        if scope.startswith("objective-control-placement:"):
            from warhammer40k_core.engine.move_completion_triggers import (
                MOVE_COMPLETION_EVENT_TYPES,
            )

            if any(
                scope == f"objective-control-placement:{event.event_id}"
                and event.event_type
                in MOVE_COMPLETION_EVENT_TYPES
                | {
                    "catalog_models_materialized",
                    "healing_step_resolved",
                    "return_on_death_set_back_up_completed",
                }
                for event in prior_events
            ):
                return
            raise GameLifecycleError("Random OC lacks its physical placement occurrence.")
        if scope in {
            f"objective-control:round-{battle_round:02d}:{turn_player}:{phase}:{timing.value}"
            for timing in ObjectiveControlTiming
        } and any(
            record.record_id == scope
            for record in (
                *state.objective_control_records,
                *(
                    row.source_objective_control_record
                    for row in state.primary_objective_turn_start_states
                ),
            )
        ):
            return
        if scope == (
            f"objective-proximity:{state.game_id}:round-{battle_round:02d}:"
            f"turn:{turn_player}:phase:{phase}:start"
        ) and any(
            event.event_type == "objective_marker_phase_start_proximity_snapshot"
            and isinstance(event.payload, dict)
            and event.payload.get("snapshot_id") == scope
            for event in events
        ):
            return
        if scope.startswith("mission-action-options:decision-request-"):
            suffix = scope.removeprefix("mission-action-options:decision-request-")
            request_id = f"decision-request-{suffix}"
            if any(
                request.request_id == request_id
                and request.decision_type == "start_mission_action"
                and isinstance(request.payload, dict)
                and request.payload.get("phase") == phase
                and request.payload.get("battle_round") == battle_round
                for request in requests
            ) or any(
                event.event_type == "mission_action_profile_options_unavailable"
                and isinstance(event.payload, dict)
                and event.payload.get("request_id") == request_id
                and event.payload.get("phase") == phase
                and event.payload.get("battle_round") == battle_round
                for event in events
            ):
                return
        raise GameLifecycleError("Random OC occurrence is not an engine evaluation boundary.")
    raise GameLifecycleError("Unsupported model-profile evaluation characteristic.")


def _objects(value: JsonValue) -> tuple[dict[str, JsonValue], ...]:
    if isinstance(value, dict):
        return (value, *(row for child in value.values() for row in _objects(child)))
    if isinstance(value, list):
        return tuple(row for child in value for row in _objects(child))
    return ()
