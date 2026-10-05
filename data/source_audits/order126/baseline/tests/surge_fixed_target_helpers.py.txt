"""Canonical Surge fixtures with fixed noncircular target footprints."""

from __future__ import annotations

from dataclasses import replace
from math import cos, radians, sin
from typing import cast

from tests.phase15a_charge_declaration_helpers import (
    charge_config,
    mustered_armies,
    unit_placement_at,
)
from tests.setup_completion_helpers import (
    ensure_army_mustered_events_for_fixture,
    record_completed_command_occurrences_for_fixture,
    record_current_battlefield_placements_for_fixture,
)
from tests.surge_helpers import SOURCE, TARGET, surge_descriptor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.triggered_movement import TriggeredMovementEligibleUnit
from warhammer40k_core.engine.triggered_movement_selection import (
    triggered_movement_unit_selection_request,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def fixed_target_surge_session(
    *, attached: bool = False, oval: bool = False, facing: float = 0
) -> LocalGameSession:
    config = charge_config(
        game_id="order75-surge-rectangular-target",
        alpha_unit_ids=("source", "leader") if attached else ("source",),
        alpha_attached_unit_ids=("source", "leader") if attached else None,
        enemy_unit_ids=("enemy",),
    )
    # Canonical typed vehicle fixture with a rectangular footprint. This is
    # test geometry, not a claim about a faction datasheet's physical dimensions.
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(
                datasheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        base_size=(
                            BaseSizeDefinition.oval(length_mm=203.2, width_mm=50.8)
                            if oval
                            else BaseSizeDefinition.rectangular(length_mm=203.2, width_mm=50.8)
                        ),
                    )
                    for profile in datasheet.model_profiles
                ),
            )
            if datasheet.datasheet_id == "core-vehicle-monster"
            else datasheet
            for datasheet in config.army_catalog.datasheets
        ),
    )
    enemy_request = replace(
        config.army_muster_requests[1],
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="enemy",
                datasheet_id="core-vehicle-monster",
                model_profile_selections=(
                    ModelProfileSelection(model_profile_id="core-vehicle-monster", model_count=1),
                ),
            ),
        ),
    )
    config = replace(
        config,
        army_catalog=catalog,
        army_muster_requests=(config.army_muster_requests[0], enemy_request),
    )
    armies = mustered_armies(config)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="order75-surge-open-battlefield",
        armies=armies,
        battlefield_width_inches=100,
        battlefield_depth_inches=100,
    )
    battlefield = scenario.battlefield_state

    def positioned(x: float, y: float) -> Pose:
        angle = radians(facing)
        return Pose.at(
            30 + x * cos(angle) - y * sin(angle),
            30 + x * sin(angle) + y * cos(angle),
            facing_degrees=facing,
        )

    for army in armies:
        for unit in army.units:
            if army.player_id == "player-b":
                poses: tuple[Pose, ...] = (positioned(0, 0),)
            elif unit.unit_instance_id.endswith(":leader"):
                poses = (positioned(0 if oval else -2.8, -11.6),)
            else:
                poses = tuple(
                    positioned(
                        0 if oval else -2.8 + 1.4 * index, -10 - 1.4 * index if oval else -10
                    )
                    for index in range(5)
                )
            battlefield = battlefield.with_unit_placement(
                unit_placement_at(unit, army_id=army.army_id, player_id=army.player_id, poses=poses)
            )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.battle_round = 1
    state.active_player_id = "player-a"
    decisions = GameLifecycle().decision_controller
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_completed_command_occurrences_for_fixture(state, decisions=decisions, config=config)
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": {"frames": []},
            },
        )
    )
    return LocalGameSession(lifecycle)


def fixed_target_surge_request(session: LocalGameSession) -> DecisionRequest:
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    lifecycle = session.lifecycle
    state = lifecycle.state
    assert state is not None
    descriptor = surge_descriptor(lifecycle=lifecycle)
    source = rules_unit_view_by_id(state=state, unit_instance_id=SOURCE).unit_instance_id
    selection = triggered_movement_unit_selection_request(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        descriptor=descriptor,
        eligible_units=(
            TriggeredMovementEligibleUnit(source, "test:hook", descriptor.source_rule_id),
        ),
    )
    lifecycle.decision_controller.request_decision(selection)
    session.advance_until_decision_or_terminal()
    status = session.submit_option(
        request_id=selection.request_id,
        option_id=f"surge:{source}:target:{TARGET}",
        result_id="select-fixed-target-surge",
    )
    assert status.decision_request is not None
    return status.decision_request


def fixed_target_surge_payload(
    session: LocalGameSession, request: DecisionRequest, *, distance: float = 3
) -> JsonValue:
    from warhammer40k_core.engine.triggered_movement_physical_authority import (
        triggered_movement_placement,
    )

    state = session.lifecycle.state
    assert state is not None
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    placement = triggered_movement_placement(
        scenario=battlefield_scenario_for_state(state=state),
        unit_instance_id=proposal.unit_instance_id,
    )

    def shifted(pose: Pose, amount: float) -> Pose:
        angle = radians(pose.facing.degrees)
        return Pose.at(
            pose.position.x - amount * sin(angle),
            pose.position.y + amount * cos(angle),
            facing_degrees=pose.facing.degrees,
        )

    witness = PathWitness.for_paths(
        tuple(
            (
                model.model_instance_id,
                (model.pose, shifted(model.pose, distance / 2), shifted(model.pose, distance)),
            )
            for model in placement.model_placements
        )
    )
    return validate_json_value(
        MovementProposalPayload(
            proposal_request_id=request.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=proposal.unit_instance_id,
            movement_phase_action="surge_move",
            witness=witness,
        ).to_payload()
    )
