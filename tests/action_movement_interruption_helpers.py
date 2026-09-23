"""Real facade fixtures for completed-move Action interruption and its cost workload."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal, cast

from tests.phase11c_command_phase_helpers import (
    default_unit_selection,
    unit_selection,
    with_model_offsets,
)
from tests.phase17n_primary_mission_helpers import phase17n_event_setup, phase17n_state_with_setup
from tests.phase17n_step5g_pairing_certification_helpers import pairing_certification_config
from tests.setup_completion_helpers import (
    ensure_army_mustered_events_for_fixture,
    record_completed_command_occurrences_for_fixture,
    record_current_battlefield_placements_for_fixture,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.charge_movement_source import ChargePlacement
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import SecondaryMissionChoice, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.mission_decisions import request_mission_action_start
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.primary_scoring_pairing_certification import (
    event_companion_pairing_lifecycle_certification_rows,
)
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import SecondaryMissionCardState
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementHandler,
    TriggeredMovementKind,
)
from warhammer40k_core.engine.triggered_movement_physical_authority import (
    triggered_movement_placement,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

MovementCase = Literal["translation", "return", "zero", "rotation", "rotation_return"]


def action_movement_session(
    *,
    attached: bool = False,
    mission_action_id: str = "maintain-control",
    pause_after_move: bool = False,
) -> tuple[LocalGameSession, str]:
    units = (
        (
            default_unit_selection("intercessor-unit-3"),
            unit_selection(
                unit_selection_id="leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        )
        if attached
        else None
    )
    if mission_action_id == "cleanse-objective" or pause_after_move:
        units = (
            *(units or (default_unit_selection("intercessor-unit-3"),)),
            default_unit_selection("spare"),
        )
    attachments = (
        (
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="intercessor-unit-3"
            ),
        )
        if attached
        else ()
    )
    setup = phase17n_event_setup(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-b",
        phase=BattlePhase.SHOOTING,
        battle_round=1,
        player_b_units=units,
        player_b_attachment_declarations=attachments,
    )
    assert state.battlefield_state is not None
    unit = next(a for a in state.army_definitions if a.player_id == "player-b").units[0]
    target = next(
        m for m in setup.objective_markers if m.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    placement = with_model_offsets(
        placement,
        target,
        offsets=((0.0, 0.0), (1.5, 0.0), (3.0, 0.0), (0.75, 1.5), (2.25, 1.5)),
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(placement)
    if attached:
        leader = state.battlefield_state.unit_placement_by_id("army-beta:leader")
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            with_model_offsets(leader, target, offsets=((3.75, 1.5),))
        )
    if mission_action_id == "cleanse-objective" or pause_after_move:
        spare = state.battlefield_state.unit_placement_by_id("army-beta:spare")
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            replace(
                spare,
                model_placements=tuple(
                    replace(model, pose=Pose.at(6 + 1.5 * index, 10))
                    for index, model in enumerate(spare.model_placements)
                ),
            )
        )
    if mission_action_id == "cleanse-objective":
        state.secondary_mission_choices = [
            choice
            if choice.player_id != "player-b"
            else SecondaryMissionChoice(
                player_id="player-b",
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "cleanse"),
            )
            for choice in state.secondary_mission_choices
        ]
        state.secondary_mission_card_states = [
            card for card in state.secondary_mission_card_states if card.player_id != "player-b"
        ] + [
            SecondaryMissionCardState.active_fixed(player_id="player-b", secondary_mission_id=mid)
            for mid in ("assassination", "cleanse")
        ]
    decisions = DecisionController()
    row = next(
        row
        for row in event_companion_pairing_lifecycle_certification_rows()
        if row.layout_id == "purge-the-foe-vs-priority-assets-layout-1"
    )
    config = pairing_certification_config(
        row=row, setup_game_id=state.game_id, player_b_units=units
    )
    config = replace(
        config,
        army_muster_requests=tuple(
            replace(req, attachment_declarations=attachments)
            if req.player_id == "player-b"
            else req
            for req in config.army_muster_requests
        ),
    )
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
    assert lifecycle.state is not None
    state = lifecycle.state
    decisions = lifecycle.decision_controller
    session = LocalGameSession(lifecycle)
    status = request_mission_action_start(
        state=state,
        decisions=decisions,
        player_id="player-b",
        mission_action_id=mission_action_id,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    request = status.decision_request
    assert request is not None
    option = next(o for o in request.options if o.option_id.startswith("start:"))
    status = session.submit_option(
        request_id=request.request_id,
        option_id=option.option_id,
        result_id="order77-start-action",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.mission_action_states[-1].status.value == "started"
    assert lifecycle.pending_decision_request() is None
    return session, state.mission_action_states[-1].unit_instance_id


def action_move_witness(placement: ChargePlacement, case: MovementCase) -> PathWitness:
    paths: list[tuple[str, tuple[Pose, ...]]] = []
    for model in placement.model_placements:
        start = model.pose
        step = Pose.at(
            start.position.x + (0.125 if case in {"translation", "return"} else 0.0),
            start.position.y,
            start.position.z,
            facing_degrees=start.facing.degrees
            + (22.5 if case == "rotation" else 45.0 if case == "rotation_return" else 0.0),
        )
        end = (
            Pose.at(
                start.position.x + 0.25,
                start.position.y,
                start.position.z,
                facing_degrees=start.facing.degrees,
            )
            if case == "translation"
            else Pose.at(
                start.position.x,
                start.position.y,
                start.position.z,
                facing_degrees=start.facing.degrees + 45.0,
            )
            if case == "rotation"
            else start
        )
        paths.append((model.model_instance_id, (start, step, end)))
    return PathWitness.for_paths(tuple(paths))


def request_action_move(
    session: LocalGameSession, unit_id: str, case: MovementCase
) -> DecisionRequest:
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = triggered_movement_placement(
        scenario=battlefield_scenario_for_state(state=state), unit_instance_id=unit_id
    )
    handler = TriggeredMovementHandler(ruleset_descriptor=state.runtime_ruleset_descriptor())
    request = handler.request_from_state(
        state=state,
        unit_instance_id=unit_id,
        descriptor=TriggeredMovementDescriptor(
            movement_kind=TriggeredMovementKind.TRIGGERED,
            source_rule_id="test:mission-action:forced-move",
            trigger_timing=ReactionWindow(
                phase=BattlePhase.SHOOTING,
                window_kind=ReactionWindowKind.RULE_TRIGGER,
                source_step="mission-action-interruption",
                source_event_id=None,
            ),
            max_distance_inches=1.0,
        ),
        candidate_witnesses=(action_move_witness(placement, case),),
    )
    session.lifecycle.decision_controller.request_decision(request)
    session._initial_replay_lifecycle_payload = session.lifecycle.to_payload()  # pyright: ignore[reportPrivateUsage]
    return request
