"""Canonical engine-created revival request for facade and projection regressions."""

from __future__ import annotations

from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture
from tests.phase15c_fight_order_helpers import fight_lifecycle
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    UnitPlacement,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked
from warhammer40k_core.engine.healing_geometry import (
    healing_phase_start_enemy_engagement_model_ids,
    healing_phase_start_model_ids,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import Pose


def revival_projection_session() -> tuple[LocalGameSession, dict[str, JsonValue]]:
    x, y = 8.5, 15.0
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("recipient",),
        enemy_unit_ids=("enemy",),
        origins={},
        poses_by_unit_key={
            "recipient": tuple(Pose.at(10, 10 + 1.5 * i) for i in range(5)),
            "enemy": tuple(Pose.at(13 + 1.5 * i, 10) for i in range(5)),
        },
        game_id="order81-revival-projection",
        battle_phase=BattlePhase.COMMAND,
        record_deployment=True,
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    model_id = units["recipient"].own_models[-1].model_instance_id
    removed = state.battlefield_state.model_placement_by_id(model_id)
    # Fixture preparation before the replay root; the only player submission is via the facade.
    destroy_rule_model_for_fixture(
        state=state,
        decisions=lifecycle.decision_controller,
        model_id=model_id,
        destroying_player_id="player-b",
        source_unit_id=units["enemy"].unit_instance_id,
        source_model_id=units["enemy"].own_models[0].model_instance_id,
    )
    unit = rules_unit_view_by_id(state=state, unit_instance_id=units["recipient"].unit_instance_id)
    allowed = healing_phase_start_enemy_engagement_model_ids(state=state, rules_unit=unit)
    effect = HealingEffect(
        effect_id="order81-revival",
        target_unit_instance_id=unit.unit_instance_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=healing_phase_start_model_ids(state=state, rules_unit=unit),
        phase_start_enemy_engagement_model_ids=allowed,
        source_context={"revive_model_full_health": True, "revive_destroyed_models_only": True},
    )
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    placement = removed.with_pose(Pose.at(x, y))
    session = LocalGameSession(lifecycle)
    payload: dict[str, JsonValue] = {
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
    return session, payload
