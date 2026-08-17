from __future__ import annotations

from copy import deepcopy
from typing import Literal

import pytest
from tests.phase11c_command_phase_helpers import with_model_offsets
from tests.phase17n_primary_mission_helpers import (
    append_authenticated_normal_move,
    phase17n_event_setup,
    phase17n_state_with_setup,
)

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
    bound_primary_scoring_commit_checkpoint,
    emit_primary_scoring_commit_checkpoint,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    build_primary_scoring_state_evidence,
    record_primary_scoring_state_evidence,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    build_current_primary_rules_unit_memberships,
)
from warhammer40k_core.geometry.pose import Pose


@pytest.fixture(scope="module")
def scoring_position_lifecycle_payload() -> GameLifecyclePayload:
    mission_setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-take-and-hold-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="take-and-hold",
    )
    state = phase17n_state_with_setup(
        setup=mission_setup,
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        battle_round=2,
    )
    decisions = DecisionController()
    battlefield = state.battlefield_state
    assert battlefield is not None
    scoring_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    scoring_marker = next(
        marker
        for marker in mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    scoring_placement = battlefield.unit_placement_by_id(scoring_unit.unit_instance_id)
    state.battlefield_state = battlefield.with_unit_placement(
        with_model_offsets(
            scoring_placement,
            scoring_marker,
            offsets=((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (0.0, 1.0), (1.0, 1.0)),
        )
    )
    scoring_record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        )
    )
    state.record_objective_control_record(scoring_record)
    decisions.event_log.append(
        "end_boundary_objective_control_determined",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "record_ids": [scoring_record.record_id],
            "source_rule_id": (
                "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
            ),
        },
    )
    scoring_commit_checkpoint = bound_primary_scoring_commit_checkpoint(
        state=state,
        record=scoring_record,
        scoring_commit_checkpoint=None,
        runtime_modifier_registry=None,
    )
    evidence = build_primary_scoring_state_evidence(
        state=state,
        record=scoring_record,
        end_of_battle=False,
        scoring_commit_checkpoint=scoring_commit_checkpoint,
    )
    emit_primary_scoring_commit_checkpoint(
        event_log=decisions.event_log,
        objective_control_record_id=scoring_record.record_id,
        scoring_boundary_kind=evidence.scoring_boundary_kind.value,
        checkpoint=scoring_commit_checkpoint,
    )
    awards = mission_scoring_policies_from_setup(
        mission_setup
    ).primary_awards_from_objective_control(
        record=scoring_record,
        authoritative_state=state,
        end_of_battle=False,
    )
    assert awards
    record_primary_scoring_state_evidence(state=state, evidence=evidence)
    for award in awards:
        state.award_victory_points(award)

    payload = GameLifecycle(state=state, decision_controller=decisions).to_payload()
    assert GameLifecycle.from_payload(deepcopy(payload)).to_payload() == payload
    return payload


@pytest.mark.parametrize(
    "cleared_field",
    ["evaluated_models", "terrain_areas", "objective_witnesses"],
)
def test_restore_rejects_rehashed_incomplete_primary_position_witness(
    scoring_position_lifecycle_payload: GameLifecyclePayload,
    cleared_field: Literal["evaluated_models", "terrain_areas", "objective_witnesses"],
) -> None:
    payload = deepcopy(scoring_position_lifecycle_payload)
    evidence = payload["state"]["primary_scoring_state_evidence_records"][0]
    did_clear = False
    for witness in evidence["current_rules_unit_position_witnesses"]:
        for component in witness["rules_unit_membership"]["component_memberships"]:
            if cleared_field == "evaluated_models" and component["evaluated_model_instance_ids"]:
                component["evaluated_model_instance_ids"] = []
                component["objective_marker_witnesses"] = []
                did_clear = True
                break
            if cleared_field == "terrain_areas" and component["logical_terrain_area_ids"]:
                component["logical_terrain_area_ids"] = []
                did_clear = True
                break
            if cleared_field == "objective_witnesses" and component["objective_marker_witnesses"]:
                component["objective_marker_witnesses"] = []
                did_clear = True
                break
        if did_clear:
            break
    assert did_clear
    old_evidence_id = evidence["evidence_id"]
    content = {
        key: value for key, value in evidence.items() if key not in {"evidence_id", "evidence_hash"}
    }
    digest = canonical_payload_sha256(content)
    evidence["evidence_id"] = f"primary-scoring-state-evidence:{digest}"
    evidence["evidence_hash"] = digest
    for ledger in payload["state"]["victory_point_ledgers"]:
        for transaction in ledger["transactions"]:
            metadata = transaction["metadata"]
            if not isinstance(metadata, dict):
                continue
            if metadata.get("primary_scoring_state_evidence_id") != old_evidence_id:
                continue
            metadata["primary_scoring_state_evidence_id"] = evidence["evidence_id"]
            metadata["primary_scoring_state_evidence_hash"] = digest

    with pytest.raises(
        GameLifecycleError,
        match="position witness drifted from authoritative boundary history",
    ):
        GameLifecycle.from_payload(payload)


def test_restore_uses_historical_boundary_positions_before_later_authenticated_move(
    scoring_position_lifecycle_payload: GameLifecyclePayload,
) -> None:
    lifecycle = GameLifecycle.from_payload(deepcopy(scoring_position_lifecycle_payload))
    state = lifecycle.state
    assert state is not None
    state.battle_round = 3
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    moved_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    append_authenticated_normal_move(
        state=state,
        decisions=lifecycle.decision_controller,
        unit_instance_id=moved_unit.unit_instance_id,
        suffix="after-primary-scoring-boundary",
        pose_transform=lambda pose: Pose.at(
            pose.position.x,
            pose.position.y + 6.0,
            pose.position.z,
            facing_degrees=pose.facing.degrees,
        ),
    )
    historical = state.primary_scoring_state_evidence_records[0].position_witness_for_rules_unit(
        moved_unit.unit_instance_id
    )
    current = next(
        membership
        for membership in build_current_primary_rules_unit_memberships(state=state)
        if membership.rules_unit_instance_id == moved_unit.unit_instance_id
    )
    assert current != historical.rules_unit_membership

    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    assert restored.state.primary_scoring_state_evidence_records == (
        state.primary_scoring_state_evidence_records
    )
