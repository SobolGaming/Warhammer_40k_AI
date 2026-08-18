from __future__ import annotations

from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PrimaryScoringSpatialEvidence,
    objective_control_record_hash,
)


def validate_primary_scoring_spatial_rows_context(
    rows: tuple[PrimaryScoringSpatialEvidence, ...],
    *,
    mission_setup: MissionSetup,
    turn_order: tuple[str, ...],
    record: ObjectiveControlRecord,
    end_of_battle: bool,
) -> None:
    """Require the frozen spatial rows needed by every scoring player policy."""
    from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup

    policies = mission_scoring_policies_from_setup(mission_setup)
    scoring_player_ids = turn_order if end_of_battle else (record.active_player_id,)
    expected_conditions_by_player = {
        player_id: required_conditions
        for player_id in scoring_player_ids
        for required_conditions in (
            policies.policy_for_player(player_id).required_primary_spatial_conditions(
                record=record,
                end_of_battle=end_of_battle,
            ),
        )
        if required_conditions
    }
    if tuple(row.player_id for row in rows) != tuple(sorted(expected_conditions_by_player)):
        raise GameLifecycleError("Primary scoring state spatial evidence player coverage drifted.")
    record_hash = objective_control_record_hash(record)
    for row in rows:
        if row.requested_condition_ids != expected_conditions_by_player[row.player_id]:
            raise GameLifecycleError("Primary scoring state spatial evidence conditions drifted.")
        if (
            row.game_id != record.game_id
            or row.battlefield_id != record.battlefield_id
            or row.battle_round != record.battle_round
            or row.active_player_id != record.active_player_id
            or row.phase != record.phase
            or row.timing is not record.timing
            or row.objective_control_record_id != record.record_id
            or row.objective_control_record_hash != record_hash
        ):
            raise GameLifecycleError(
                "Primary scoring state spatial evidence drifted from its boundary."
            )


__all__ = ("validate_primary_scoring_spatial_rows_context",)
