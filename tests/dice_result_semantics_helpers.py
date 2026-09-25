"""Canonical lifecycle roots for Core dice-result authority regressions."""

from __future__ import annotations

from copy import deepcopy

from tests.phase15c_fight_order_helpers import fight_lifecycle
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec, DiceRollState
from warhammer40k_core.core.dice_extremum import DiceExtremum
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.dice_extremum import request_dice_extremum
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_dice_results_2026_09 import (
    HIGHEST_LOWEST_SOURCE_ID,
)


def extremum_session(
    *,
    extremum: DiceExtremum,
    secret: bool = False,
) -> tuple[LocalGameSession, DiceRollState, DecisionRequest]:
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=("alpha",),
        enemy_unit_ids=("enemy",),
        origins={"alpha": Pose.at(10, 10), "enemy": Pose.at(40, 30)},
        game_id="order84-dice",
        record_deployment=True,
    )
    state = lifecycle.state
    assert state is not None
    decisions = lifecycle.decision_controller
    open_phase(lifecycle)
    start = len(decisions.event_log.records)
    roll = DiceRollManager(state.game_id, event_log=decisions.event_log).roll_fixed(
        DiceRollSpec(
            DiceExpression(3, 6),
            reason="Core highest/lowest physical-die reference",
            roll_type="core_dice_reference",
            actor_id="player-a" if secret else "player-b",
        ),
        (5, 5, 2) if extremum is DiceExtremum.HIGHEST else (2, 2, 5),
    )
    if secret:
        decisions.event_log.mark_secret_suffix(
            start_index=start,
            player_id="player-a",
            visibility_source="dice_extremum",
        )
    request = request_dice_extremum(
        state=state,
        decisions=decisions,
        roll_state=roll,
        extremum=extremum,
        referring_source_rule_id=HIGHEST_LOWEST_SOURCE_ID,
        reference_id="order84:reference",
    )
    assert isinstance(request, DecisionRequest)
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    session._initial_replay_lifecycle_payload = deepcopy(lifecycle.to_payload())  # pyright: ignore[reportPrivateUsage]
    return session, roll, request


def open_phase(lifecycle: GameLifecycle) -> None:
    from warhammer40k_core.engine.phase_start_sequencing import phase_start_context
    from warhammer40k_core.engine.timing_window_events import record_timing_window_boundary

    assert lifecycle.state is not None
    record_timing_window_boundary(
        decisions=lifecycle.decision_controller,
        window=phase_start_context(lifecycle.state).timing_window,
        completed=False,
    )


def assert_active_player_history(
    lifecycle: GameLifecycle, *, expected_player: str | None = None
) -> None:
    from warhammer40k_core.engine.active_player_boundary_history import (
        active_player_authority_before_event,
    )

    state = lifecycle.state
    assert state is not None
    decisions = lifecycle.decision_controller
    historical = active_player_authority_before_event(
        state=state, decisions=decisions, event_index=len(decisions.event_log.records)
    )
    assert historical.effective_player_id == state.effective_active_player_id(), (
        historical,
        state.active_player_scopes,
    )
    if expected_player is not None:
        assert historical.effective_player_id == expected_player
    assert historical.scopes == state.active_player_scopes
    assert historical.turn_player_id == state.active_player_id
    assert historical.battle_round == state.battle_round
    assert state.current_battle_phase is not None
    assert historical.phase == state.current_battle_phase.value


def forged_future_shooting_scope_payload() -> dict[str, object]:
    """Adversarial checkpoint: the tie's own future choice pretends to authorize shooting."""
    import json
    from typing import cast

    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.phases.shooting_model import OutOfPhaseShootingState

    session, _roll, request = extremum_session(extremum=DiceExtremum.HIGHEST)
    state = session.lifecycle.state
    assert state is not None
    phase = state.current_battle_phase
    assert phase is not None
    session.submit_option(
        request_id=request.request_id,
        option_id=request.options[1].option_id,
        result_id="review-choice",
    )
    raw = cast(dict[str, JsonValue], json.loads(json.dumps(session.lifecycle.to_payload())))

    def tamper(value: JsonValue) -> None:
        if isinstance(value, dict):
            if value.get("visibility_source") == "dice_extremum":
                value["player_id"] = "player-b"
                if "scope_request_ids" in value:
                    value["scope_request_ids"] = [request.request_id]
            if value.get("request_id") == request.request_id and "actor_id" in value:
                value["actor_id"] = "player-b"
            for child in value.values():
                tamper(child)
        elif isinstance(value, list):
            for child in value:
                tamper(child)

    tamper(raw["decisions"])
    events = cast(dict[str, JsonValue], raw["decisions"])["event_log"]
    assert isinstance(events, list)
    opening = OutOfPhaseShootingState(
        battle_round=1,
        player_id="player-b",
        parent_phase=phase,
        source_rule_id="unrelated-source",
        source_decision_request_id=request.request_id,
        source_decision_result_id="review-choice",
        source_context={},
        selected_unit_instance_id="unrelated-unit",
    )
    insertions: tuple[tuple[str, str, JsonValue], ...] = (
        (
            "dice_extremum_referenced",
            "out_of_phase_shooting_started",
            cast(JsonValue, opening.to_payload()),
        ),
        ("dice_extremum_selected", "out_of_phase_shooting_completed", {}),
    )
    for kind, event_type, payload in insertions:
        index = next(
            i
            for i, event in enumerate(events)
            if isinstance(event, dict) and event["event_type"] == kind
        )
        events.insert(
            index + int(kind == "dice_extremum_selected"),
            {
                "event_id": "temporary",
                "event_type": event_type,
                "payload": payload,
            },
        )
    for index, event in enumerate(events):
        assert isinstance(event, dict)
        event["event_id"] = f"event-{index + 1:06d}"
    return cast(dict[str, object], raw)


def forged_shooting_source_lifecycle(*, reuse: bool) -> GameLifecycle:
    from tests.charge_reroll_helpers import heroic_session
    from tests.fire_overwatch_helpers import (
        ENEMIES,
        choose_enemy,
        choose_shooter,
        finish_overwatch,
        overwatch_session,
        pending_overwatch,
    )
    from tests.heroic_intervention_helpers import add_heroic_modifier, use_heroic
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.phases.shooting_model import OutOfPhaseShootingState

    if reuse:
        session = overwatch_session(attacks=2)
        open_phase(session.lifecycle)
        status = choose_shooter(session, pending_overwatch(session))
        request = status.decision_request
        assert request is not None
        finish_overwatch(session, choose_enemy(session, request, ENEMIES[0]))
        payload = next(
            event.payload
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "out_of_phase_shooting_started"
        )
    else:
        session, unit_id = heroic_session(natural=False)
        open_phase(session.lifecycle)
        add_heroic_modifier(session, unit_id, delta=20)
        request = use_heroic(session, unit_id)
        targets = session.submit_option(
            request_id=request.request_id, option_id=unit_id, result_id="order84-declare"
        ).decision_request
        assert targets is not None
        assert targets.decision_type == "select_charge_targets"
        session.submit_option(
            request_id=targets.request_id,
            option_id="decline_charge_targets",
            result_id="order84-decline",
        )
        state = session.lifecycle.state
        assert state is not None
        use = state.stratagem_use_records[0]
        opening = OutOfPhaseShootingState(
            battle_round=use.battle_round,
            player_id=use.player_id,
            parent_phase=use.phase,
            source_rule_id=use.source_id,
            source_decision_request_id=use.request_id,
            source_decision_result_id=use.result_id,
            source_context=validate_json_value({"stratagem_use": use.to_payload()}),
            selected_unit_instance_id=use.targeted_unit_instance_ids[0],
        ).to_payload()
        payload = validate_json_value(opening)
    session.lifecycle.decision_controller.event_log.append("out_of_phase_shooting_started", payload)
    return session.lifecycle
