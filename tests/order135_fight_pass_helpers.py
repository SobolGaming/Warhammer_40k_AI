"""Native pass scene using predeclared analytical Core profiles and real dice.

Canonical 40mm models use M18/W50 leaders and a cloned W1 analytical target, with
A12/WS2/S12/D1 melee. This finite synthetic scene is not faction certification.
All setup, movement, charges, casualties and Fight choices use public decisions;
no started state, RNG, history, or replay anchor is replaced.
"""

from dataclasses import replace

from tests.deployment_submission_helpers import deployment_placement_payload_for_request
from tests.order135_counteroffensive_helpers import (
    army_id,
    other_player,
    submit_native_combat_choice,
)
from tests.phase11c_command_phase_helpers import phase11c_config, unit_selection
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.deployment import DeploymentPlacementRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def native_pass_session(*, passer: str, nearby: bool) -> LocalGameSession:
    first = other_player(passer)
    armies = {
        player: tuple(
            unit_selection(
                unit_selection_id=name,
                datasheet_id="order135-pass-victim"
                if player == first and name == "one"
                else "order135-pass-first"
                if player == passer and name == "three" and not nearby
                else "core-character-leader",
                model_profile_id="order135-pass-victim"
                if player == first and name == "one"
                else "core-character-leader",
                model_count=1,
            )
            for name in (("one", "three") if player == first else ("one", "two", "three"))
        )
        for player in ("player-a", "player-b")
    }
    config = phase11c_config(
        game_id=f"order135-pass-eligibility:{passer}:{nearby}",
        player_a_units=armies["player-a"],
        player_b_units=armies["player-b"],
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
                            else CharacteristicValue.from_raw(
                                Characteristic.WOUNDS,
                                50,
                            )
                            if value.characteristic is Characteristic.WOUNDS
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
                        attack_profile=AttackProfile.fixed(12),
                        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 2),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 12),
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
    leader = catalog.datasheet_by_id("core-character-leader")
    victim = replace(
        leader,
        datasheet_id="order135-pass-victim",
        name="Order135 analytical one-wound target",
        model_profiles=tuple(
            replace(
                profile,
                model_profile_id="order135-pass-victim",
                characteristics=tuple(
                    CharacteristicValue.from_raw(Characteristic.WOUNDS, 1)
                    if value.characteristic is Characteristic.WOUNDS
                    else value
                    for value in profile.characteristics
                ),
                source_ids=("order135-pass:analytical-target",),
            )
            for profile in leader.model_profiles
        ),
        composition=tuple(
            replace(part, model_profile_id="order135-pass-victim") for part in leader.composition
        ),
        wargear_options=tuple(
            replace(option, model_profile_id="order135-pass-victim")
            for option in leader.wargear_options
        ),
        attachment_eligibilities=(),
        source_ids=("order135-pass:analytical-target",),
    )
    first_unit = replace(
        leader,
        datasheet_id="order135-pass-first",
        name="Order135 analytical Fights First leader",
        abilities=(
            *leader.abilities,
            DatasheetAbilityDescriptor(
                ability_id="core-fights-first",
                name="Fights First",
                source_id="order135-pass:analytical-fights-first",
                support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
                source_kind=CatalogAbilitySourceKind.CORE,
                effect_description="CORE Fights First descriptor.",
                timing_tags=("fight_phase", "fights_first"),
            ),
        ),
    )
    catalog = replace(catalog, datasheets=(*catalog.datasheets, victim, first_unit))
    assert config.mission_setup is not None
    mission = replace(config.mission_setup, terrain_features=())
    session = LocalGameSession()
    session.start(
        replace(
            config,
            turn_order=(first, passer),
            army_catalog=catalog,
            mission_setup=mission,
            ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
                mission, rules_overlay_ids=()
            ),
        )
    )
    return session


def submit_pass_scene_choice(
    session: LocalGameSession, request: DecisionRequest, *, passer: str, nearby: bool
) -> None:
    from typing import cast

    first = other_player(passer)
    state = session.lifecycle.state
    assert state is not None
    kind = request.decision_type
    result_id = f"{request.request_id}:order135-pass-native"
    options = [option.option_id for option in request.options]
    reroll: str | None = None
    if kind == "use_stratagem" and state.current_battle_phase is BattlePhase.CHARGE:
        assert isinstance(request.payload, dict)
        context = cast(dict[str, JsonValue], request.payload["stratagem_context"])
        trigger = cast(dict[str, JsonValue], context["trigger_payload"])
        unit_id = trigger["affected_unit_instance_id"]
        roll = cast(dict[str, JsonValue], trigger["dice_roll_state"])
        total = roll["current_total"]
        assert isinstance(total, int)
        candidate = f"use-stratagem:command-reroll:target:{unit_id}"
        # These two public setup paths stop 2.25 inches from the shared target.
        # Use only a genuinely offered reroll when that fixed approach is too short.
        if (
            unit_id in (f"{army_id(passer)}:one", f"{army_id(passer)}:two")
            and total < 2.25
            and candidate in options
        ):
            reroll = candidate
    if reroll is not None:
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=reroll
        )
    elif kind == "resolve_sequencing_order":
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=options[0]
        )
    elif kind == "submit_deployment_placement":
        deployment = DeploymentPlacementRequest.from_decision_request_payload(request.payload)
        y: float = {"one": 12, "two": 16, "three": 34}[deployment.unit_instance_id.split(":")[-1]]
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
        option = (
            "normal_move"
            if state.battle_round <= 2 and "normal_move" in options
            else "remain_stationary"
        )
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option
        )
    elif kind == "select_charging_unit":
        wanted = (
            [f"{army_id(passer)}:one", f"{army_id(passer)}:two"]
            if state.active_player_id == passer
            else [f"{army_id(first)}:three"]
        )
        candidates = (
            [option for option in wanted if option in options] if state.battle_round == 2 else []
        )
        option = (
            candidates[0]
            if candidates
            else next(o for o in options if o.startswith(("end_", "complete_")))
        )
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option
        )
    elif kind == "select_charge_targets":
        charge_target_id = (
            f"{army_id(first)}:one"
            if state.active_player_id == passer
            else f"{army_id(passer)}:three"
        )
        option = next(
            o.option_id
            for o in request.options
            if isinstance(o.payload, dict) and o.payload.get("target_ids") == [charge_target_id]
        )
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option
        )
    elif kind == "submit_movement_proposal":
        move = MovementProposalRequest.from_decision_request_payload(request.payload)
        if move.proposal_kind in {ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE}:
            submit_native_combat_choice(session, request, first_player=first)
            return
        assert move.proposal_kind in {ProposalKind.NORMAL_MOVE, ProposalKind.CHARGE_MOVE}
        assert move.context is not None
        assert state.battlefield_state is not None
        assert state.active_player_id is not None
        own = state.battlefield_state.unit_placement_by_id(move.unit_instance_id).model_placements[
            0
        ]
        x = 20.0 if state.active_player_id == "player-a" else 40.0
        y = own.pose.position.y
        target_id = (
            f"{army_id(first)}:one"
            if state.active_player_id == passer
            else f"{army_id(passer)}:three"
        )
        approach = state.battle_round == 2 and (
            state.active_player_id == passer or move.unit_instance_id.endswith(":three")
        )
        if state.battle_round == 2 and not approach:
            x = 32.0 if state.active_player_id == "player-a" else 28.0
        if approach:
            target = state.battlefield_state.unit_placement_by_id(target_id).model_placements[0]
            models = {
                m.model_id: m
                for m in battlefield_scenario_for_state(state=state).placed_geometry_models()
            }
            own_model, target_model = (
                models[own.model_instance_id],
                models[target.model_instance_id],
            )
            radii = own_model.base.radius_at_angle(
                0, own_model.pose.facing
            ) + target_model.base.radius_at_angle(0, target_model.pose.facing)
            vertical = state.active_player_id == passer and move.unit_instance_id.endswith(":two")
            direction = 1 if vertical or state.active_player_id == "player-b" else -1
            target_axis = target.pose.position.y if vertical else target.pose.position.x
            axis = target_axis + direction * (radii + 2.25)
            if move.proposal_kind is ProposalKind.CHARGE_MOVE:
                maximum = move.context["maximum_distance_inches"]
                assert isinstance(maximum, (int, float))
                start = own.pose.position.y if vertical else own.pose.position.x
                contact = target_axis + direction * (radii + 1e-7)
                axis = (
                    max(contact, start - maximum)
                    if direction == 1
                    else min(contact, start + maximum)
                )
            x, y = (target.pose.position.x, axis) if vertical else (axis, target.pose.position.y)
        payload: dict[str, JsonValue] = {
            "proposal_request_id": move.request_id,
            "proposal_kind": move.proposal_kind.value,
            "unit_instance_id": move.unit_instance_id,
            "movement_phase_action": move.movement_phase_action,
            "movement_mode": move.context["movement_mode"],
            "witness": validate_json_value(
                PathWitness.for_paths(
                    ((own.model_instance_id, (own.pose, Pose.at(x, y))),)
                ).to_payload()
            ),
        }
        if move.proposal_kind is ProposalKind.CHARGE_MOVE:
            payload["charge_target_unit_instance_ids"] = [target_id]
        status = session.submit_parameterized_payload(
            request_id=request.request_id, result_id=result_id, payload=payload
        )
    elif (
        kind == "select_fight_activation"
        and not nearby
        and state.battle_round == 2
        and state.active_player_id == passer
        and (close_option := f"fight:normal:{army_id(passer)}:three") in options
    ):
        # The positive pass scene first consumes the nearby friendly Fights First
        # unit through real melee. The nearby enemy remains eligible for Remaining.
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=close_option
        )
    else:
        submit_native_combat_choice(session, request, first_player=first)
        return
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
