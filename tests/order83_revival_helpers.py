"""Two independent Core revival grants after a real phase boundary."""

from __future__ import annotations

from copy import deepcopy

from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture
from tests.phase15c_fight_order_helpers import fight_lifecycle
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked
from warhammer40k_core.engine.healing_geometry import healing_phase_start_model_ids
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import Pose


def revival_proposal(
    request: DecisionRequest, removed: ModelPlacement, pose: Pose
) -> dict[str, JsonValue]:
    placement = removed.with_pose(pose)
    return {
        "proposal_request_id": request.request_id,
        "proposal_kind": "healing_revival_placement",
        "unit_instance_id": placement.unit_instance_id,
        "placement_kind": BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD.value,
        "attempted_placement": validate_json_value(
            UnitPlacement(
                army_id=placement.army_id,
                player_id=placement.player_id,
                unit_instance_id=placement.unit_instance_id,
                model_placements=(placement,),
            ).to_payload()
        ),
    }


def request_revival(
    lifecycle: GameLifecycle, removed: ModelPlacement, index: int
) -> DecisionRequest:
    state = lifecycle.state
    assert state is not None
    effect = HealingEffect(
        effect_id=f"order83-heal-{index}",
        target_unit_instance_id=removed.unit_instance_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=healing_phase_start_model_ids(
            state=state,
            decisions=lifecycle.decision_controller,
            rules_unit=rules_unit_view_by_id(
                state=state, unit_instance_id=removed.unit_instance_id
            ),
        ),
        source_context={
            "revive_model_full_health": True,
            "revive_destroyed_models_only": True,
            "eligible_revival_model_ids": [removed.model_instance_id],
        },
    )
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    return request


def sequential_revival_session() -> tuple[LocalGameSession, ModelPlacement]:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("recipient",),
        enemy_unit_ids=("enemy",),
        origins={},
        poses_by_unit_key={
            "recipient": tuple(Pose.at(10, 10 + 1.5 * i) for i in range(5)),
            "enemy": tuple(Pose.at(40, 30 + 1.5 * i) for i in range(5)),
        },
        game_id="order83-revival-anchors",
        battle_phase=BattlePhase.FIGHT,
        record_deployment=True,
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    removed = tuple(
        state.battlefield_state.model_placement_by_id(model.model_instance_id)
        for model in units["recipient"].own_models[-2:]
    )
    for placement in removed:
        destroy_rule_model_for_fixture(
            state=state,
            decisions=lifecycle.decision_controller,
            model_id=placement.model_instance_id,
            destroying_player_id="player-b",
            source_unit_id=units["enemy"].unit_instance_id,
            source_model_id=units["enemy"].own_models[0].model_instance_id,
        )
    LocalGameSession(lifecycle).advance_until_decision_or_terminal()
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    request = request_revival(lifecycle, removed[0], 1)
    first = LocalGameSession(lifecycle)
    movement = first.advance_until_decision_or_terminal().decision_request
    assert movement is not None
    status = first.submit_option(
        request_id=movement.request_id,
        option_id=units["enemy"].unit_instance_id,
        result_id="order83-select-movement-unit",
    )
    assert status.decision_request == request
    status = first.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order83-first-revival",
        payload=revival_proposal(request, removed[0], Pose.at(10, 16)),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    request = request_revival(lifecycle, removed[1], 2)
    second = LocalGameSession(lifecycle)
    second.advance_until_decision_or_terminal()
    second._initial_replay_lifecycle_payload = deepcopy(lifecycle.to_payload())  # pyright: ignore[reportPrivateUsage]
    action = lifecycle.decision_controller.queue.peek_next()
    option = next(option for option in action.options if "stationary" in option.option_id)
    status = second.submit_option(
        request_id=action.request_id,
        option_id=option.option_id,
        result_id="order83-enemy-stationary",
    )
    assert status.decision_request == request
    return second, removed[1]
