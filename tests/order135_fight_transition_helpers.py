"""Public two-turn Fight scene; predeclared M18/A1/WS6/S1/D1 Core catalog.

This is a bounded analytical control, not faction/provider certification. No
started state, decision history, replay anchor, or RNG state is replaced.
"""

from dataclasses import replace
from typing import cast

from tests.order135_counteroffensive_helpers import (
    army_id,
    other_player,
    submit_native_combat_choice,
)
from tests.phase11c_command_phase_helpers import phase11c_config, unit_selection
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def transition_session(*, first_player: str) -> LocalGameSession:
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
        game_id=f"order135-fight-transition:{first_player}",
        player_a_units=units,
        player_b_units=units,
    )
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            CharacteristicValue.from_raw(Characteristic.MOVEMENT, 18)
                            if value.characteristic is Characteristic.MOVEMENT
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            if sheet.datasheet_id == "core-character-leader"
            else sheet
            for sheet in config.army_catalog.datasheets
        ),
        wargear=tuple(
            replace(
                gear,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(1),
                        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 6),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 1),
                        damage_profile=DamageProfile.fixed(1),
                    )
                    for profile in gear.weapon_profiles
                ),
            )
            if gear.wargear_id == "core-leader-blade"
            else gear
            for gear in config.army_catalog.wargear
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


def submit_transition_choice(
    session: LocalGameSession, request: DecisionRequest, *, first_player: str
) -> None:
    state = session.lifecycle.state
    assert state is not None
    kind = request.decision_type
    option_ids = [option.option_id for option in request.options]
    result_id = f"{request.request_id}:order135-transition"
    if kind == "select_movement_action":
        option = (
            "normal_move"
            if "normal_move" in option_ids and state.battle_round <= 2
            else "remain_stationary"
        )
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option
        )
    elif kind == "select_charging_unit":
        suffix = "two" if state.active_player_id == first_player else "one"
        assert state.active_player_id is not None
        desired = f"{army_id(state.active_player_id)}:{suffix}"
        option = (
            desired
            if state.battle_round == 2 and desired in option_ids
            else next(
                option
                for option in option_ids
                if option.startswith(("end_", "complete_", "decline", "skip"))
            )
        )
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option
        )
    elif kind == "select_charge_targets":
        assert state.active_player_id is not None
        payload = cast(dict[str, JsonValue], request.payload)
        suffix = cast(str, payload["unit_instance_id"]).split(":")[-1]
        target = f"{army_id(other_player(state.active_player_id))}:{suffix}"
        option = next(
            option.option_id
            for option in request.options
            if isinstance(option.payload, dict) and option.payload.get("target_ids") == [target]
        )
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option
        )
    elif kind == "submit_movement_proposal":
        move = MovementProposalRequest.from_decision_request_payload(request.payload)
        if move.proposal_kind in {ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE}:
            submit_native_combat_choice(session, request, first_player=first_player)
            return
        assert move.proposal_kind in {ProposalKind.NORMAL_MOVE, ProposalKind.CHARGE_MOVE}
        assert state.battlefield_state is not None
        assert state.active_player_id is not None
        assert move.context is not None
        model = state.battlefield_state.unit_placement_by_id(
            move.unit_instance_id
        ).model_placements[0]
        models = {
            model.model_id: model
            for model in battlefield_scenario_for_state(state=state).placed_geometry_models()
        }
        own = models[model.model_instance_id]
        x = 20.0 if state.active_player_id == "player-a" else 40.0
        target = (
            f"{army_id(other_player(state.active_player_id))}:"
            f"{move.unit_instance_id.split(':')[-1]}"
        )
        enemy = state.battlefield_state.unit_placement_by_id(target).model_placements[0]
        other = models[enemy.model_instance_id]
        separation = own.base.radius_at_angle(0, own.pose.facing) + other.base.radius_at_angle(
            0, other.pose.facing
        )
        direction = 1 if state.active_player_id == "player-b" else -1
        if state.battle_round == 2:
            x = enemy.pose.position.x + direction * (separation + 2.25)
        submission: dict[str, JsonValue] = {
            "proposal_request_id": move.request_id,
            "proposal_kind": move.proposal_kind.value,
            "unit_instance_id": move.unit_instance_id,
            "movement_phase_action": move.movement_phase_action,
            "movement_mode": move.context["movement_mode"],
        }
        if move.proposal_kind is ProposalKind.CHARGE_MOVE:
            maximum = move.context["maximum_distance_inches"]
            assert isinstance(maximum, (int, float))
            contact = enemy.pose.position.x + direction * (separation + 1e-7)
            x = (
                max(contact, model.pose.position.x - maximum)
                if direction == 1
                else min(contact, model.pose.position.x + maximum)
            )
            submission["charge_target_unit_instance_ids"] = [target]
        submission["witness"] = validate_json_value(
            PathWitness.for_paths(
                ((model.model_instance_id, (model.pose, Pose.at(x, model.pose.position.y))),)
            ).to_payload()
        )
        status = session.submit_parameterized_payload(
            request_id=request.request_id, result_id=result_id, payload=submission
        )
    else:
        submit_native_combat_choice(session, request, first_player=first_player)
        return
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
