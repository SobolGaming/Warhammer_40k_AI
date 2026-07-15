from __future__ import annotations

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.reserves import ReserveState, ReserveStatus
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    canonical_rules_unit_view_from_armies,
    rules_unit_view_from_armies,
)


def validate_reserve_state_rules_unit(
    *,
    armies: tuple[ArmyDefinition, ...],
    reserve_state: ReserveState,
) -> RulesUnitView:
    return canonical_rules_unit_view_from_armies(
        armies=armies,
        unit_instance_id=reserve_state.unit_instance_id,
        owner_player_id=reserve_state.player_id,
    )


def reserve_state_for_rules_unit(
    *,
    armies: tuple[ArmyDefinition, ...],
    reserve_states: tuple[ReserveState, ...],
    unit_instance_id: str,
) -> ReserveState | None:
    rules_unit_id = rules_unit_view_from_armies(
        armies=armies,
        unit_instance_id=unit_instance_id,
    ).unit_instance_id
    return next(
        (
            reserve_state
            for reserve_state in reserve_states
            if reserve_state.unit_instance_id == rules_unit_id
        ),
        None,
    )


def unarrived_reserve_model_ids(
    *,
    armies: tuple[ArmyDefinition, ...],
    reserve_states: tuple[ReserveState, ...],
) -> tuple[str, ...]:
    model_ids: list[str] = []
    for reserve_state in reserve_states:
        if reserve_state.status is not ReserveStatus.IN_RESERVES:
            continue
        reserve_view = validate_reserve_state_rules_unit(
            armies=armies,
            reserve_state=reserve_state,
        )
        model_ids.extend(model.model_instance_id for model in reserve_view.own_models)
        for embarked_unit_id in reserve_state.embarked_unit_instance_ids:
            embarked_view = rules_unit_view_from_armies(
                armies=armies,
                unit_instance_id=embarked_unit_id,
            )
            model_ids.extend(model.model_instance_id for model in embarked_view.own_models)
    return tuple(sorted(model_ids))
