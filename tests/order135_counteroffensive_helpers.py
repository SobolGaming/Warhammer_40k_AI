"""Pregame-declared combat scenes driven only by public decisions and real dice.

M12 and A1/WS6/S1/D1 are bounded synthetic catalog choices, not provider or
whole-faction certification. No started state, history or RNG is replaced.
"""

from dataclasses import replace
from typing import cast

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.phase11c_command_phase_helpers import phase11c_config, unit_selection
from tests.psychic_modifier_helpers import submit_fixture_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.deployment import DeploymentPlacementRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.stratagems import StratagemTargetProposal, stratagem_decline_payload
from warhammer40k_core.engine.stratagems_model import StratagemTargetProposalPayload
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def other_player(player: str) -> str:
    assert player in {"player-a", "player-b"}
    return "player-b" if player == "player-a" else "player-a"


def army_id(player: str) -> str:
    assert player in {"player-a", "player-b"}
    return "army-alpha" if player == "player-a" else "army-beta"


def native_combat_session(*, first_player: str) -> LocalGameSession:
    units = tuple(
        unit_selection(
            unit_selection_id=name,
            datasheet_id="core-character-leader",
            model_profile_id="core-character-leader",
            model_count=1,
        )
        for name in ("one", "two")
    )
    config = phase11c_config(
        game_id=f"order135-counteroffensive-native:{first_player}",
        player_a_units=units,
        player_b_units=units,
    )
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(
                datasheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            CharacteristicValue.from_raw(Characteristic.MOVEMENT, 12)
                            if value.characteristic is Characteristic.MOVEMENT
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in datasheet.model_profiles
                ),
            )
            if datasheet.datasheet_id == "core-character-leader"
            else datasheet
            for datasheet in config.army_catalog.datasheets
        ),
        wargear=tuple(
            replace(
                wargear,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(1),
                        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 6),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 1),
                        damage_profile=DamageProfile.fixed(1),
                    )
                    for profile in wargear.weapon_profiles
                ),
            )
            if wargear.wargear_id == "core-leader-blade"
            else wargear
            for wargear in config.army_catalog.wargear
        ),
    )
    assert config.mission_setup is not None
    mission = replace(config.mission_setup, terrain_features=())
    session = LocalGameSession()
    session.start(
        replace(
            config,
            turn_order=(first_player, other_player(first_player)),
            army_catalog=catalog,
            mission_setup=mission,
            ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
                mission, rules_overlay_ids=()
            ),
        )
    )
    return session


def proposal_from_native_request(request: DecisionRequest) -> StratagemTargetProposal:
    assert request.decision_type == "submit_stratagem_target_proposal"
    payload = cast(dict[str, JsonValue], request.payload)
    return StratagemTargetProposal.from_payload(
        cast(StratagemTargetProposalPayload, payload["proposal_request"])
    )


def actual_fought_events(session: LocalGameSession) -> tuple[EventRecord, ...]:
    return tuple(
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "unit_has_fought"
    )


def submit_native_combat_choice(
    session: LocalGameSession, request: DecisionRequest, *, first_player: str
) -> None:
    state = session.lifecycle.state
    assert state is not None
    kind = request.decision_type
    result_id = f"{request.request_id}:order135-native-choice"
    if kind == "submit_stratagem_target_proposal":
        status = session.submit_parameterized_payload(
            request_id=request.request_id, result_id=result_id, payload=stratagem_decline_payload()
        )
    elif kind == "submit_deployment_placement":
        deployment = DeploymentPlacementRequest.from_decision_request_payload(request.payload)
        unit_id = deployment.unit_instance_id
        y = 24 if unit_id.endswith(":one") else 28
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=result_id,
            payload=deployment_placement_payload_for_request(
                session.lifecycle,
                request=request,
                pose_factory=lambda _i, owner, _model: Pose.at(8 if owner == "player-a" else 52, y),
            ),
        )
    elif kind == "select_movement_action":
        option = "normal_move" if state.battle_round <= 2 else "remain_stationary"
        assert any(o.option_id == option for o in request.options)
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option
        )
    elif kind == "submit_movement_proposal":
        move = MovementProposalRequest.from_decision_request_payload(request.payload)
        if move.proposal_kind in {ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE}:
            # Decline optional displacement through its actual proposal contract.
            submit_fixture_request(session, request)
            return
        assert move.proposal_kind in {ProposalKind.NORMAL_MOVE, ProposalKind.CHARGE_MOVE}
        assert move.context is not None
        assert state.battlefield_state is not None
        assert state.active_player_id is not None
        before = state.battlefield_state.unit_placement_by_id(move.unit_instance_id)
        model = before.model_placements[0]
        distance_from_home = 20.0 if state.battle_round == 1 else 32.0
        x = distance_from_home if state.active_player_id == "player-a" else 60 - distance_from_home
        models = {
            m.model_id: m
            for m in battlefield_scenario_for_state(state=state).placed_geometry_models()
        }
        own = models[model.model_instance_id]
        if state.battle_round == 2 and state.active_player_id == other_player(first_player):
            target = f"{army_id(first_player)}:{move.unit_instance_id.split(':')[-1]}"
            enemy = state.battlefield_state.unit_placement_by_id(target).model_placements[0]
            other = models[enemy.model_instance_id]
            separation = own.base.radius_at_angle(0, own.pose.facing) + other.base.radius_at_angle(
                0, other.pose.facing
            )
            approach = (
                separation
                + session.lifecycle.config.ruleset_descriptor.engagement_policy.horizontal_inches
                + 0.25
            )
            x = enemy.pose.position.x + (
                approach if state.active_player_id == "player-b" else -approach
            )
        submission: dict[str, JsonValue] = {
            "proposal_request_id": move.request_id,
            "proposal_kind": move.proposal_kind.value,
            "unit_instance_id": move.unit_instance_id,
            "movement_phase_action": move.movement_phase_action,
            "movement_mode": move.context["movement_mode"],
        }
        if move.proposal_kind is ProposalKind.CHARGE_MOVE:
            target = f"{army_id(first_player)}:{move.unit_instance_id.split(':')[-1]}"
            enemy = state.battlefield_state.unit_placement_by_id(target).model_placements[0]
            other = models[enemy.model_instance_id]
            separation = (
                own.base.radius_at_angle(0, own.pose.facing)
                + other.base.radius_at_angle(0, other.pose.facing)
                + 1e-7
            )
            maximum = move.context["maximum_distance_inches"]
            assert isinstance(maximum, (int, float))
            contact = enemy.pose.position.x + (
                separation if state.active_player_id == "player-b" else -separation
            )
            x = (
                max(contact, model.pose.position.x - maximum)
                if state.active_player_id == "player-b"
                else min(contact, model.pose.position.x + maximum)
            )
            assert abs(x - model.pose.position.x) <= maximum
            submission["charge_target_unit_instance_ids"] = [target]
        submission["witness"] = validate_json_value(
            PathWitness.for_paths(
                ((model.model_instance_id, (model.pose, Pose.at(x, model.pose.position.y))),)
            ).to_payload()
        )
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=result_id,
            payload=validate_json_value(submission),
        )
    elif kind == "select_charging_unit":
        candidates = [
            o
            for o in request.options
            if o.option_id.startswith(army_id(other_player(first_player)) + ":")
        ]
        option = (
            candidates[0].option_id
            if state.battle_round == 2
            and state.active_player_id == other_player(first_player)
            and candidates
            else next(
                o.option_id
                for o in request.options
                if o.option_id.startswith(("end_", "complete_", "decline", "skip"))
            )
        )
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option
        )
    elif kind == "select_charge_targets":
        payload = cast(dict[str, JsonValue], request.payload)
        target = f"{army_id(first_player)}:{cast(str, payload['unit_instance_id']).split(':')[-1]}"
        option = next(
            o.option_id
            for o in request.options
            if isinstance(o.payload, dict) and o.payload.get("target_ids") == [target]
        )
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option
        )
    elif kind == "submit_melee_declaration":
        submit_fixture_request(session, request)
        return
    else:
        assert kind in {
            "select_secondary_missions",
            "select_deployment_unit",
            "select_movement_unit",
            "select_shooting_unit",
            "select_fight_activation",
            "use_stratagem",
            "select_damage_allocation_model",
            "select_feel_no_pain",
            "select_modifier_ignores",
            "select_psychic_attack_modifier_ignores",
        }, kind
        if kind == "select_secondary_missions":
            option = "fixed:assassination:bring_it_down"
        elif kind in {"select_movement_unit", "select_fight_activation"}:
            option = request.options[0].option_id
        else:
            option = next(
                (
                    o.option_id
                    for o in request.options
                    if o.option_id.startswith(("complete_", "end_", "decline", "skip"))
                ),
                request.options[0].option_id,
            )
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option
        )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
