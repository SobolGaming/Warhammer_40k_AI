"""Real facade movement fixtures across both players' turns in one round."""

from __future__ import annotations

from tests.phase15c_fight_order_helpers import fight_lifecycle
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementEligibleUnit,
    TriggeredMovementHandler,
    TriggeredMovementKind,
)
from warhammer40k_core.engine.triggered_movement_physical_authority import (
    triggered_movement_placement,
)
from warhammer40k_core.engine.triggered_movement_selection import (
    triggered_movement_unit_selection_request,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def request_from(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def move_witness(session: LocalGameSession, unit_id: str, dx: float = 0.25) -> PathWitness:
    state = session.lifecycle.state
    assert state is not None
    placement = triggered_movement_placement(
        scenario=battlefield_scenario_for_state(state=state), unit_instance_id=unit_id
    )
    return PathWitness.for_paths(
        tuple(
            (
                model.model_instance_id,
                (
                    model.pose,
                    Pose.at(
                        model.pose.position.x + dx,
                        model.pose.position.y,
                        model.pose.position.z,
                        facing_degrees=model.pose.facing.degrees,
                    ),
                ),
            )
            for model in placement.model_placements
        )
    )


def reaction_session(
    *,
    attached: bool = False,
    parameterized: bool = False,
    enqueue_reaction: bool = True,
    catalog: ArmyCatalog | None = None,
) -> tuple[LocalGameSession, str]:
    lifecycle, _ = fight_lifecycle(
        catalog=catalog,
        alpha_unit_ids=("source",),
        enemy_unit_ids=("reactor", "leader") if attached else ("reactor",),
        origins={
            "source": Pose.at(10, 20),
            "reactor": Pose.at(30, 20),
            "leader": Pose.at(30, 21.5),
        },
        enemy_unit_specs={"leader": ("core-character-leader", "core-character-leader", 1)}
        if attached
        else None,
        enemy_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="reactor"
            ),
        )
        if attached
        else (),
        game_id=f"order80-occurrence-{attached}-{parameterized}",
        battle_phase=BattlePhase.MOVEMENT,
        record_deployment=True,
    )
    state = lifecycle.state
    assert state is not None
    unit_id = rules_unit_view_by_id(
        state=state, unit_instance_id="army-beta:reactor"
    ).unit_instance_id
    if enqueue_reaction:
        lifecycle.decision_controller.request_decision(
            reaction_request(LocalGameSession(lifecycle), unit_id, parameterized=parameterized)
        )
    return LocalGameSession(lifecycle), unit_id


def reaction_request(
    session: LocalGameSession, unit_id: str, *, parameterized: bool
) -> DecisionRequest:
    state = session.lifecycle.state
    assert state is not None
    assert state.current_battle_phase is not None
    descriptor = TriggeredMovementDescriptor(
        movement_kind=TriggeredMovementKind.TRIGGERED,
        source_rule_id="test:order80:reactive-normal",
        trigger_timing=ReactionWindow(
            phase=state.current_battle_phase,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step="order80-normal-move-audit",
            source_event_id=None,
        ),
        max_distance_inches=1.0,
    )
    if parameterized:
        request = triggered_movement_unit_selection_request(
            state=state,
            player_id=rules_unit_view_by_id(state=state, unit_instance_id=unit_id).owner_player_id,
            descriptor=descriptor,
            eligible_units=(
                TriggeredMovementEligibleUnit(
                    unit_instance_id=unit_id,
                    hook_id="test:order80:reaction",
                    source_id=descriptor.source_rule_id,
                ),
            ),
        )
    else:
        request = TriggeredMovementHandler(
            ruleset_descriptor=state.runtime_ruleset_descriptor()
        ).request_from_state(
            state=state,
            unit_instance_id=unit_id,
            descriptor=descriptor,
            candidate_witnesses=(move_witness(session, unit_id),),
        )
    return request


def submit_path(
    session: LocalGameSession, request: DecisionRequest, *, result_id: str, dx: float = 0.25
) -> LifecycleStatus:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert proposal.movement_phase_action is not None
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action=proposal.movement_phase_action,
                witness=move_witness(session, proposal.unit_instance_id, dx),
                movement_mode="normal"
                if proposal.proposal_kind is ProposalKind.NORMAL_MOVE
                else None,
            ).to_payload()
        ),
    )


def accept_reaction(session: LocalGameSession, *, parameterized: bool) -> LifecycleStatus:
    request = request_from(session.advance_until_decision_or_terminal())
    option = next(o for o in request.options if o.option_id != "decline_triggered_movement")
    status = session.submit_option(
        request_id=request.request_id,
        option_id=option.option_id,
        result_id="order80-reactive-selection",
    )
    if parameterized:
        status = submit_path(session, request_from(status), result_id="order80-reactive-path")
    return status


def next_player_action(
    session: LocalGameSession, status: LifecycleStatus, unit_id: str
) -> DecisionRequest:
    state = session.lifecycle.state
    assert state is not None
    for index in range(20):
        request = request_from(status)
        if (
            state.active_player_id == "player-b"
            and request.decision_type == "select_movement_action"
        ):
            assert state.battle_round == 1
            assert state.current_battle_phase is BattlePhase.MOVEMENT
            return request
        choices = [
            o
            for o in request.options
            if o.option_id
            in {
                "remain_stationary",
                "complete_shooting_phase",
                "complete_charge_phase",
                "complete_fight_phase",
            }
        ]
        if not choices:
            choices = [o for o in request.options if o.option_id in {"army-alpha:source", unit_id}]
        assert len(choices) == 1, request.decision_type
        status = session.submit_option(
            request_id=request.request_id,
            option_id=choices[0].option_id,
            result_id=f"order80-boundary-{index}",
        )
    raise AssertionError("Did not reach Player B's Movement action.")
