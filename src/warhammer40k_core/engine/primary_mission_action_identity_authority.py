from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_historical_rules_unit_identity(
    *,
    state: GameState,
    player_id: str,
    rules_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
    unit_identity_ids: tuple[str, ...],
) -> None:
    components = tuple(sorted(component_unit_instance_ids))
    if len(components) == 1 and rules_unit_instance_id == components[0]:
        valid = True
    else:
        valid = any(
            record.player_id == player_id
            and record.attached_unit_instance_id == rules_unit_instance_id
            and tuple(sorted(record.component_unit_instance_ids)) == components
            for record in state.starting_attached_unit_records
        )
    if not valid or unit_identity_ids != tuple(sorted({rules_unit_instance_id, *components})):
        raise GameLifecycleError("Primary Mission Action historical rules-unit inventory drifted.")


def allowed_rules_unit_ids_for_component(
    *,
    state: GameState,
    player_id: str,
    component_unit_instance_id: str,
) -> frozenset[str]:
    return frozenset(
        {
            component_unit_instance_id,
            *(
                record.attached_unit_instance_id
                for record in state.starting_attached_unit_records
                if record.player_id == player_id
                and component_unit_instance_id in record.component_unit_instance_ids
            ),
        }
    )


__all__ = (
    "allowed_rules_unit_ids_for_component",
    "validate_historical_rules_unit_identity",
)
