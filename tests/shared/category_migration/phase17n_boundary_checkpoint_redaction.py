from __future__ import annotations

from dataclasses import replace

import pytest

from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.projection import public_decision_request_view
from warhammer40k_core.adapters.redaction import (
    public_decision_request_payload,
    public_event_record_payload,
    public_victory_point_transaction_payload,
    redacted_lifecycle_status,
)
from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DamageKind,
    FeelNoPainSource,
    MortalWoundApplicationProgress,
    build_feel_no_pain_request,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import (
    EventRecord,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseKind,
    model_destruction_cause_id,
)
from warhammer40k_core.engine.model_logical_death import (
    MODEL_LOGICAL_DEATH_RECORDED_EVENT,
    DamageApplicationLogicalDeathTransition,
    ModelLogicalDeathRecord,
    model_logical_death_boundary_id,
)
from warhammer40k_core.engine.mortal_wound_application_authority import (
    MORTAL_WOUND_APPLICATION_STARTED_EVENT,
)
from warhammer40k_core.engine.mortal_wound_logical_death import MortalWoundLogicalDeathCauseBinding
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE,
)
from warhammer40k_core.engine.mortal_wound_target_lineage import (
    FROZEN_RULES_UNIT_COMPONENTS_POLICY,
    MortalWoundTargetLineage,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, LifecycleStatus
from warhammer40k_core.engine.primary_mission_action_decline_integrity import (
    MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
)
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardState,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.geometry.pose import Pose


def _tactical_score_request() -> DecisionRequest:
    context = _tactical_score_context()
    options = (
        DecisionOption(
            option_id="score:beacon",
            label="Score beacon",
            payload={**context, "score": True},
        ),
        DecisionOption(
            option_id="retain:beacon",
            label="Retain beacon",
            payload={**context, "score": False},
        ),
    )
    return DecisionRequest(
        request_id="phase17n-tactical-score-request",
        decision_type="score_tactical_secondary_mission",
        actor_id="player-a",
        payload={
            **context,
            "legal_option_ids": [option.option_id for option in options],
        },
        options=options,
    )


def _tactical_score_context() -> dict[str, JsonValue]:
    return {
        "achievement_id": "phase17n-tactical-achievement",
        "game_id": "phase17n-tactical-score-redaction",
        "player_id": "player-a",
        "active_player_id": "player-a",
        "secondary_mission_id": "beacon",
        "mode": "tactical",
        "battle_round": 2,
        "phase": "fight",
        "card_battle_round": 2,
        "victory_points": 5,
        "scoring_rule_id": "beacon-rule",
        "scoring_rule_condition": "beacon-condition",
        "scoring_rule_source_id": "beacon-source",
        "scoring_timing": "turn_end",
        "source_id": "beacon",
        "evidence": {
            "scoring_commit_checkpoint_id": "primary-mission-boundary:secret",
            "scoring_commit_checkpoint_hash": "a" * 64,
            "secondary_scoring_state_evidence_id": "secondary-evidence:secret",
            "secondary_scoring_state_evidence_hash": "b" * 64,
            "evidence_by_rule": {"beacon": {"selected_unit_instance_ids": ["secret-owner-unit"]}},
        },
    }


def _assert_internal_secondary_authority_absent(payload: object) -> None:
    encoded = canonical_json(validate_json_value(payload))
    for key in (
        "scoring_commit_checkpoint_id",
        "scoring_commit_checkpoint_hash",
        "secondary_scoring_state_evidence_id",
        "secondary_scoring_state_evidence_hash",
    ):
        assert f'"{key}"' not in encoded


def _assert_owner_score_context_preserved(payload: JsonValue) -> None:
    assert isinstance(payload, dict)
    assert payload["achievement_id"] == "phase17n-tactical-achievement"
    assert payload["secondary_mission_id"] == "beacon"
    evidence = payload["evidence"]
    assert isinstance(evidence, dict)
    assert evidence["evidence_by_rule"] == {
        "beacon": {"selected_unit_instance_ids": ["secret-owner-unit"]}
    }


def _pending_fnp_request_with_logical_death_authority() -> tuple[DecisionRequest, str, str]:
    game_id = "phase17n-private-fnp-game"
    application_id = "phase17n-private-fnp-application"
    physical_unit_id = "army-a:unit-a"
    destroyed_model_id = f"{physical_unit_id}:model-a"
    next_model_id = f"{physical_unit_id}:model-b"
    damage = DamageApplication(
        target_unit_instance_id=physical_unit_id,
        model_instance_id=destroyed_model_id,
        damage_kind=DamageKind.MORTAL,
        requested_damage=1,
        wounds_lost=1,
        excess_damage_lost=0,
        starting_wounds_remaining=1,
        final_wounds_remaining=0,
        destroyed=True,
    )
    cause_id = model_destruction_cause_id(
        game_id=game_id,
        cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
        producer_id=application_id,
        model_instance_id=destroyed_model_id,
    )
    boundary_id = model_logical_death_boundary_id(
        game_id=game_id,
        cause_id=cause_id,
        model_instance_id=destroyed_model_id,
    )
    logical_death = ModelLogicalDeathRecord(
        boundary_id=boundary_id,
        game_id=game_id,
        cause_id=cause_id,
        cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
        producer_id=application_id,
        model_instance_id=destroyed_model_id,
        physical_unit_instance_id=physical_unit_id,
        rules_unit_instance_id=physical_unit_id,
        destroyed_model_placement=ModelPlacement(
            army_id="army-a",
            player_id="player-a",
            unit_instance_id=physical_unit_id,
            model_instance_id=destroyed_model_id,
            pose=Pose.at(x=12.0, y=8.0),
        ),
        placement_retained=True,
        transition=DamageApplicationLogicalDeathTransition(damage_application=damage.to_payload()),
    )
    logical_death_event = EventRecord(
        event_id="event-000001",
        event_type=MODEL_LOGICAL_DEATH_RECORDED_EVENT,
        payload=validate_json_value(logical_death.to_payload()),
    )
    progress = MortalWoundApplicationProgress(
        application_id=application_id,
        source_rule_id="phase17n-private-fnp-source",
        source_context={"source_result_id": "phase17n-private-fnp-source-result"},
        target_unit_instance_id=physical_unit_id,
        defender_player_id="player-a",
        mortal_wounds=2,
        remaining_mortal_wounds=1,
        spill_over=True,
        destruction_evidence=None,
        logical_death_events=(logical_death_event,),
        logical_death_cause_binding=MortalWoundLogicalDeathCauseBinding.fixed(
            cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
            producer_id=application_id,
        ),
        applications=(damage,),
        target_lineage=MortalWoundTargetLineage(
            policy=FROZEN_RULES_UNIT_COMPONENTS_POLICY,
            canonical_target_unit_instance_id=physical_unit_id,
            owner_player_id="player-a",
            component_unit_instance_ids=(physical_unit_id,),
            character_component_unit_instance_ids=(),
        ),
    )
    return (
        build_feel_no_pain_request(
            request_id="phase17n-private-fnp-request",
            defender_player_id="player-a",
            lost_wound_context=validate_json_value(
                progress.to_feel_no_pain_context(
                    model_instance_id=next_model_id,
                    allocation_occurrence={
                        "private_selected_model_id": next_model_id,
                        "private_fnp_source_id": "phase17n-private-fnp-source-a",
                    },
                )
            ),
            sources=(
                FeelNoPainSource(
                    source_id="phase17n-private-fnp-source-a",
                    threshold=5,
                ),
                FeelNoPainSource(
                    source_id="phase17n-private-fnp-source-b",
                    threshold=6,
                ),
            ),
            decline_allowed=False,
        ),
        cause_id,
        boundary_id,
    )


def _assert_internal_model_destruction_authority_absent(
    payload: object,
    *,
    cause_id: str,
    boundary_id: str,
) -> None:
    encoded = canonical_json(validate_json_value(payload))
    for key in (
        "allocation_occurrence",
        "logical_death_cause_binding",
        "logical_death_event",
        "logical_death_events",
        "model_destruction_cause_authorities",
        "model_destruction_cause_id",
        "parent_model_destruction_cause_id",
    ):
        assert f'"{key}"' not in encoded
    assert MODEL_LOGICAL_DEATH_RECORDED_EVENT not in encoded
    assert cause_id not in encoded
    assert boundary_id not in encoded


def _administrator_viewer() -> ViewerContext:
    return ViewerContext(
        principal_id="phase17n-administrator",
        role=PrincipalRole.ADMINISTRATOR,
        viewer_player_id=None,
        policy=ROLE_POLICY_BY_ROLE[PrincipalRole.ADMINISTRATOR],
    )


__all__: list[str] = []
__all__ += ["DamageApplication", "DamageApplicationLogicalDeathTransition", "DamageKind"]
__all__ += ["DecisionOption", "DecisionRecord", "DecisionRequest", "DecisionResult"]
__all__ += ["FROZEN_RULES_UNIT_COMPONENTS_POLICY", "EventRecord", "FeelNoPainSource"]
__all__ += ["GameLifecycleError", "GameLifecycleStage", "JsonValue", "LifecycleStatus"]
__all__ += ["MISSION_ACTION_OPPORTUNITY_DECLINED_EVENT", "MODEL_LOGICAL_DEATH_RECORDED_EVENT"]
__all__ += ["MORTAL_WOUND_APPLICATION_STARTED_EVENT", "MORTAL_WOUND_MODEL_ALLOCATED_EVENT_TYPE"]
__all__ += ["ModelDestructionCauseKind", "ModelLogicalDeathRecord", "ModelPlacement"]
__all__ += ["MortalWoundApplicationProgress", "MortalWoundLogicalDeathCauseBinding"]
__all__ += ["PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT", "MortalWoundTargetLineage"]
__all__ += ["PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT", "Pose", "PrimaryMissionBoundaryCheckpoint"]
__all__ += ["ROLE_POLICY_BY_ROLE", "PrincipalRole", "SecondaryMissionCardState"]
__all__ += ["VictoryPointSourceKind", "VictoryPointTransaction", "ViewerContext"]
__all__ += ["_administrator_viewer", "_assert_internal_model_destruction_authority_absent"]
__all__ += ["_assert_internal_secondary_authority_absent"]
__all__ += ["_assert_owner_score_context_preserved"]
__all__ += ["_pending_fnp_request_with_logical_death_authority", "_tactical_score_context"]
__all__ += ["_tactical_score_request", "build_feel_no_pain_request", "canonical_json"]
__all__ += ["canonical_payload_sha256", "model_destruction_cause_id"]
__all__ += ["model_logical_death_boundary_id", "public_decision_request_payload"]
__all__ += ["public_decision_request_view", "public_event_record_payload"]
__all__ += ["public_victory_point_transaction_payload", "pytest", "redacted_lifecycle_status"]
__all__ += ["replace", "validate_json_value"]
