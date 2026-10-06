"""The same setup-turn lock for ordinary and reactive activity consumers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleStage
from warhammer40k_core.engine.rules_units import rules_unit_identity_history_contains
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_large_model_setup_2026_09 as large_model_source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.movement_proposals import PlacementProposalPayload


def large_model_activity_reason(
    state: GameState, unit_instance_id: str, activity: str
) -> str | None:
    if (
        state.stage is not GameLifecycleStage.BATTLE
        or activity not in large_model_source.SETUP_POLICY.restricted_activities
    ):
        return None
    for reserve in state.reserve_states:
        if (
            reserve.large_model_exception_used
            and reserve.post_arrival_restrictions
            and reserve.restriction_battle_round == state.battle_round
            and rules_unit_identity_history_contains(
                state=state,
                identity_ids=(reserve.unit_instance_id,),
                unit_instance_id=unit_instance_id,
            )
        ):
            return "large_model_setup_turn_restriction"
    return None


def validate_arrival_restriction_evidence(
    *, state: GameState, submitted: PlacementProposalPayload, payload: dict[str, JsonValue]
) -> None:
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.reserves import LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS

    exception_ids = {row.model_instance_id for row in submitted.large_model_exceptions}
    models = {
        model.model_instance_id: model
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    submitted_model_ids = {
        row.model_instance_id for row in submitted.resolved_rules_unit_placement().model_placements
    }
    if not exception_ids.issubset(models) or not exception_ids.issubset(submitted_model_ids):
        raise GameLifecycleError("Oversized setup restriction lost model identity.")
    restricted = any(
        large_model_source.SETUP_POLICY.reserve_exempt_keyword not in models[mid].keywords
        for mid in exception_ids
    )
    expected = (
        sorted(row.value for row in LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS)
        if restricted
        else []
    )
    if (
        payload.get("large_model_exception_used") != bool(exception_ids)
        or payload.get("post_arrival_restrictions") != expected
    ):
        raise GameLifecycleError("Oversized setup restriction evidence drifted.")
