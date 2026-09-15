from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.generic_modifier_helpers import generic_effect
from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

SOURCE = "army-alpha:source"
OLD = "army-beta:old"
NEW = "army-beta:new"
_OLD_ORIGIN = Pose.at(25, 20)


def request_from(status: LifecycleStatus) -> DecisionRequest:
    assert status.decision_request is not None, status
    return status.decision_request


def charge_session(*, old_origin: Pose = _OLD_ORIGIN) -> LocalGameSession:
    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("source", "next"),
        game_id="order46-replacement",
        battle_round=2,
        enemy_unit_ids=("old", "new"),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(20, 20), model_count=5),
        enemy_origins={"old": old_origin, "new": Pose.at(10, 26)},
    )
    state = lifecycle.state
    assert state is not None
    add_modifier(state, effect_id="initial-roll-bonus", kind="modify_dice_roll", delta=10)
    return LocalGameSession(lifecycle=lifecycle)


def add_modifier(state: GameState, *, effect_id: str, kind: str, delta: float) -> None:
    parameters: dict[str, JsonValue] = {"delta": delta}
    if kind == "modify_dice_roll":
        parameters = {"delta": int(delta), "roll_type": "charge"}
    effect = generic_effect(
        effect_id=effect_id,
        owner_player_id="player-a",
        target_unit_instance_ids=(SOURCE,),
        target_kind="this_unit",
        effect_kind=kind,
        parameters=parameters,
    )
    state.record_persisting_effect(
        replace(
            effect,
            started_phase=BattlePhase.CHARGE,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round, phase=BattlePhase.CHARGE, player_id="player-a"
            ),
        )
    )


def select_source(session: LocalGameSession) -> DecisionRequest:
    request = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        session.submit_option(
            request_id=request.request_id, option_id=SOURCE, result_id="order46-select-source"
        )
    )
    return decline_charge_command_reroll(session, request)


def decline_charge_command_reroll(
    session: LocalGameSession, request: DecisionRequest
) -> DecisionRequest:
    """Drive the optional reroll before testing a Charge's targets or movement."""
    if request.decision_type != "use_stratagem":
        return request
    assert isinstance(request.payload, dict)
    context = request.payload["stratagem_context"]
    assert isinstance(context, dict)
    trigger = context["trigger_payload"]
    assert isinstance(trigger, dict)
    assert isinstance(trigger["charge_action_id"], str)
    return request_from(
        session.submit_option(
            request_id=request.request_id,
            option_id="decline_stratagem_window",
            result_id=f"decline-charge-reroll:{request.request_id}",
        )
    )


def select_targets(
    session: LocalGameSession,
    request: DecisionRequest,
    targets: tuple[str, ...],
    *,
    result_id: str = "order46-targets",
) -> DecisionRequest:
    request = decline_charge_command_reroll(session, request)
    option = next(
        o
        for o in request.options
        if isinstance(o.payload, dict) and o.payload.get("target_ids") == list(targets)
    )
    return request_from(
        session.submit_option(
            request_id=request.request_id, option_id=option.option_id, result_id=result_id
        )
    )


def move_payload(
    session: LocalGameSession,
    request: DecisionRequest,
    *,
    target: str = NEW,
    dx: float = 0,
    dy: float = 4,
) -> JsonValue:
    state = session.lifecycle.state
    assert state is not None
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(SOURCE)
    return cast(
        JsonValue,
        ChargeMoveProposal(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.CHARGE_MOVE,
            unit_instance_id=SOURCE,
            movement_phase_action="charge_move",
            movement_mode=MovementMode.CHARGE,
            charge_target_unit_instance_ids=(target,),
            witness=PathWitness.for_paths(
                tuple(
                    (
                        m.model_instance_id,
                        (
                            m.pose,
                            Pose.at(m.pose.position.x + dx / 2, m.pose.position.y + dy / 2),
                            Pose.at(m.pose.position.x + dx, m.pose.position.y + dy),
                        ),
                    )
                    for m in placement.model_placements
                )
            ),
        ).to_payload(),
    )
