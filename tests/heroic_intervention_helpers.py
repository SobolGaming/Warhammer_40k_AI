from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.charge_distance_helpers import request_from
from tests.charge_reroll_helpers import heroic_session
from tests.generic_modifier_helpers import generic_effect
from tests.phase15a_charge_test_support import _heroic_proposal_from_request
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.charge_declaration import ChargeRollResult, ChargeRollResultPayload
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.stratagems import StratagemTargetBinding, StratagemTargetKind


def add_heroic_modifier(
    session: LocalGameSession, unit_id: str, *, delta: float, movement: bool = False
) -> None:
    state = session.lifecycle.state
    assert state is not None
    effect = generic_effect(
        effect_id="order50-distance" if movement else "order50-roll",
        owner_player_id="player-a",
        target_unit_instance_ids=(unit_id,),
        target_kind="this_unit",
        effect_kind="modify_move_distance" if movement else "modify_dice_roll",
        parameters={"delta": delta} if movement else {"delta": int(delta), "roll_type": "charge"},
    )
    state.record_persisting_effect(
        replace(
            effect,
            started_phase=BattlePhase.CHARGE,
            expiration=EffectExpiration.end_turn(battle_round=1, player_id="player-b"),
        )
    )


def use_heroic(
    session: LocalGameSession, unit_id: str, *, mode: str = "into_the_fray"
) -> DecisionRequest:
    request = request_from(session.advance_until_decision_or_terminal())
    proposal = _heroic_proposal_from_request(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id=unit_id,
        ),
        effect_selection={"mode": mode},
    )
    return request_from(
        session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order50-use",
            payload=validate_json_value({"proposal": proposal.to_payload()}),
        )
    )


def start_heroic(
    *, natural: bool = False, delta: int = 0, movement_delta: float = 0
) -> tuple[LocalGameSession, str, DecisionRequest]:
    session, unit_id = heroic_session(natural=natural)
    if delta:
        add_heroic_modifier(session, unit_id, delta=delta)
    if movement_delta:
        add_heroic_modifier(session, unit_id, delta=movement_delta, movement=True)
    declaration = use_heroic(session, unit_id)
    assert declaration.decision_type == "select_charging_unit"
    return session, unit_id, declaration


def latest_heroic_roll(session: LocalGameSession) -> ChargeRollResult:
    events = [
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "charge_roll_resolved"
    ]
    payload = cast(dict[str, JsonValue], events[-1].payload)
    return ChargeRollResult.from_payload(cast(ChargeRollResultPayload, payload["roll_result"]))


def drive_heroic_charge_choices(
    session: LocalGameSession, status: LifecycleStatus, *, unit_id: str, result_prefix: str
) -> LifecycleStatus:
    """Submit the real declaration/target choices before movement-specific regressions."""
    request = status.decision_request
    if request is not None and request.decision_type == "select_charging_unit":
        status = session.submit_option(
            request_id=request.request_id, option_id=unit_id, result_id=f"{result_prefix}:declare"
        )
        request = status.decision_request
    if request is not None and request.decision_type == "select_charge_targets":
        option = next(
            option for option in request.options if option.option_id != "decline_charge_targets"
        )
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option.option_id,
            result_id=f"{result_prefix}:targets",
        )
    return status
