from __future__ import annotations

from warhammer40k_core.engine.charge_required_targets import (
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
)

CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS = "charge_move_proposal_required"
CHARGE_MOVE_COMPLETED_STATUS = "charge_move_completed"
CHARGE_MOVE_PROPOSAL_CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        "source_selected_option_id",
        "movement_mode",
        "maximum_distance_inches",
        "reachable_target_unit_instance_ids",
        "reachable_target_distances_inches",
        CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
        "charge_roll",
    }
)
CHARGE_MOVE_MODEL_MOVEMENT_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "model_instance_id",
        "movement_mode",
        "maximum_distance_inches",
        "start_pose",
        "end_pose",
        "movement_distance_witness",
        "path_validation_result",
        "terrain_path_legality_result",
    }
)
CHARGE_MOVE_ENDPOINT_WITNESS_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "selected_target_unit_instance_ids",
        "target_distances_before_inches",
        "target_distances_after_inches",
        "engaged_target_unit_instance_ids",
        "preferred_distance_target_unit_instance_ids",
        "non_target_engaged_unit_instance_ids",
    }
)
CHARGE_MOVE_FLY_POLICY_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {"has_fly", "uses_aircraft_rules", "can_declare_charge"}
)
CHARGE_MOVE_COMPLETED_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "unit_instance_id",
        "request_id",
        "result_id",
        "proposal_request_id",
        "phase_body_status",
        "proposal_validation",
        "transition_batch",
        "movement_mode",
        "maximum_distance_inches",
        "selected_target_unit_instance_ids",
        "model_movements",
        "path_validation_results",
        "terrain_path_legality_results",
        "coherency_result",
        "endpoint_witness",
        "fly_charge_policy",
    }
)
CHARGE_MOVE_COMPLETED_OPTIONAL_PAYLOAD_KEYS: frozenset[str] = frozenset({"persisting_effect"})

__all__ = (
    "CHARGE_MOVE_COMPLETED_OPTIONAL_PAYLOAD_KEYS",
    "CHARGE_MOVE_COMPLETED_PAYLOAD_KEYS",
    "CHARGE_MOVE_COMPLETED_STATUS",
    "CHARGE_MOVE_ENDPOINT_WITNESS_PAYLOAD_KEYS",
    "CHARGE_MOVE_FLY_POLICY_PAYLOAD_KEYS",
    "CHARGE_MOVE_MODEL_MOVEMENT_PAYLOAD_KEYS",
    "CHARGE_MOVE_PROPOSAL_CONTEXT_KEYS",
    "CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS",
)
