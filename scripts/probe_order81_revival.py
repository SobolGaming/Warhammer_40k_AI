"""Reproduce Order 81 preflight findings on main 45561d864c3634ce1d0e00d2b6599091ef43ed58.

Run: PYTHONPATH=.:src uv run --no-sync python scripts/probe_order81_revival.py
This diagnostic expects known defects, not repaired semantics or a complete game.
Canonical fixture permissions are explicit inputs, not faction certification.
"""

from __future__ import annotations

import json

from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture
from tests.phase15c_fight_order_helpers import fight_lifecycle

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_request import PARAMETERIZED_DECISION_OPTION_ID
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked
from warhammer40k_core.engine.healing_geometry import (
    healing_phase_start_enemy_engagement_model_ids,
    healing_phase_start_model_ids,
)
from warhammer40k_core.engine.healing_revival import _validated_healing_revival_submission
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import Pose


def probe(case: str, x: float, y: float) -> dict[str, object]:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("recipient",),
        enemy_unit_ids=("enemy",),
        origins={},
        poses_by_unit_key={
            "recipient": tuple(Pose.at(10, 10 + 1.5 * i) for i in range(5)),
            "enemy": tuple(Pose.at(13 + 1.5 * i, 10) for i in range(5)),
        },
        game_id=f"order81-revival-{case}",
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
    scenario = battlefield_scenario_for_state(state=state)
    proposed_model = geometry_model_for_placement(
        model=units["recipient"].own_models[-1], placement=placement
    )
    enemy_placements = state.battlefield_state.unit_placement_by_id(
        units["enemy"].unit_instance_id
    ).model_placements
    engaged_after = tuple(
        p.model_instance_id
        for p in enemy_placements
        if proposed_model.is_within_engagement_range(
            geometry_model_for_placement(
                model=scenario.model_instance_for_placement(p), placement=p
            ),
            horizontal_inches=2,
            vertical_inches=5,
        )
    )
    session = LocalGameSession(lifecycle)
    assert session.advance_until_decision_or_terminal().decision_request == request
    before = lifecycle.to_payload()
    payload = {
        "proposal_request_id": request.request_id,
        "proposal_kind": "healing_revival_placement",
        "unit_instance_id": placement.unit_instance_id,
        "placement_kind": BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD.value,
        "attempted_placement": UnitPlacement(
            army_id=placement.army_id,
            player_id=placement.player_id,
            unit_instance_id=placement.unit_instance_id,
            model_placements=(placement,),
        ).to_payload(),
    }
    pending_views = projection_results(session)
    assert all(row["status"] == "projection_error" for row in pending_views.values())
    # Read-only engine validation isolates the diagnostic hidden by the facade's status.
    diagnostic: dict[str, object]
    try:
        _validated_healing_revival_submission(
            state=state,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            request=request,
            result=DecisionResult(
                request_id=request.request_id,
                result_id="order81-validator-diagnostic",
                decision_type=request.decision_type,
                actor_id=request.actor_id,
                selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
                payload=payload,
            ),
        )
    except GameLifecycleError as exc:
        diagnostic = {"status": "rejected", "error_type": type(exc).__name__, "message": str(exc)}
    else:
        diagnostic = {"status": "accepted"}
    assert before == lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order81-revive-placement",
        payload=payload,
    )
    if case == "new_model_same_enemy_unit":
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert diagnostic["message"] == "Revived model engages a new enemy model."
        assert set(engaged_after) - set(allowed)
        assert before == lifecycle.to_payload()
    else:
        assert status.status_kind is not LifecycleStatusKind.INVALID
        assert diagnostic["status"] == "accepted"
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint
    views = projection_results(session)
    assert views == projection_results(restored)
    result = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order81-revival")).run()
    assert result.status is ReplayRunStatus.REPRODUCED
    return {
        "case": case,
        "allowed_enemy_model_ids": allowed,
        "engaged_enemy_model_ids_after": engaged_after,
        "enemy_unit_id": units["enemy"].unit_instance_id,
        "placement": [x, y],
        "expected_legal": True,
        "status": status.status_kind.value,
        "status_payload": status.payload,
        "lifecycle_unchanged": before == lifecycle.to_payload(),
        "checkpoint_exact": True,
        "validator_diagnostic": diagnostic,
        "pending_viewer_results": pending_views,
        "final_viewer_results": views,
        "replay": result.status.value,
    }


def projection_results(session: LocalGameSession) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    for viewer in ("player-a", "player-b"):
        try:
            view = session.view(viewer_player_id=viewer)
        except GameLifecycleError as exc:
            results[viewer] = {
                "status": "projection_error",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        else:
            results[viewer] = {
                "status": "projected",
                "projection_state_hash": view["projection_state_hash"],
            }
    for row in results.values():
        if row["status"] == "projection_error":
            assert row["message"] == (
                "Parameterized DecisionRequest payload missing proposal_request."
            )
    return results


if __name__ == "__main__":
    print(
        json.dumps(
            {
                "cases": [
                    probe("new_model_same_enemy_unit", 12, 12),
                    probe("old_enemy_model_only", 11.5, 12.5),
                    probe("unengaged", 8.5, 15),
                ]
            },
            indent=2,
        )
    )
