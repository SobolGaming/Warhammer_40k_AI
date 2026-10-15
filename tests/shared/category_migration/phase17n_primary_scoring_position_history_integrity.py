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
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
    resolve_primary_scoring_boundary_lifecycle,
)
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
        scoring_player_id=scoring_record.active_player_id,
        state=state,
        record=scoring_record,
        scoring_commit_checkpoint=None,
        runtime_modifier_registry=None,
    )
    evidence = build_primary_scoring_state_evidence(
        scoring_player_id=scoring_record.active_player_id,
        state=state,
        record=scoring_record,
        end_of_battle=False,
        scoring_commit_checkpoint=scoring_commit_checkpoint,
    )
    emit_primary_scoring_commit_checkpoint(
        event_log=decisions.event_log,
        scoring_player_id=evidence.scoring_player_id,
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
    resolve_primary_scoring_boundary_lifecycle(
        scoring_player_id=scoring_record.active_player_id,
        state=state,
        record=scoring_record,
        scoring_boundary_kind=evidence.scoring_boundary_kind,
        scoring_commit_checkpoint_id=evidence.scoring_commit_checkpoint_id,
        scoring_commit_checkpoint_hash=evidence.scoring_commit_checkpoint_hash,
        evidence_id=evidence.evidence_id,
    )

    payload = GameLifecycle(state=state, decision_controller=decisions).to_payload()
    assert GameLifecycle.from_payload(deepcopy(payload)).to_payload() == payload
    return payload


__all__: list[str] = []
__all__ += ["BattlePhase", "DecisionController", "GameLifecycle", "GameLifecycleError"]
__all__ += ["GameLifecyclePayload", "Literal", "ObjectiveControlContext"]
__all__ += ["ObjectiveControlTiming", "ObjectiveMarkerRole", "Pose"]
__all__ += ["append_authenticated_normal_move", "bound_primary_scoring_commit_checkpoint"]
__all__ += ["build_current_primary_rules_unit_memberships"]
__all__ += ["build_primary_scoring_state_evidence", "canonical_payload_sha256", "deepcopy"]
__all__ += ["emit_primary_scoring_commit_checkpoint", "mission_scoring_policies_from_setup"]
__all__ += ["phase17n_event_setup", "phase17n_state_with_setup", "pytest"]
__all__ += ["record_primary_scoring_state_evidence", "resolve_objective_control"]
__all__ += ["resolve_primary_scoring_boundary_lifecycle", "scoring_position_lifecycle_payload"]
__all__ += ["with_model_offsets"]
