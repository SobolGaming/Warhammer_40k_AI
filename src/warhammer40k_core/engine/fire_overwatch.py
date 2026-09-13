"""Fire Overwatch target scope, independent of enemy movement history."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.shooting_eligibility import shooting_unit_can_select_to_shoot
from warhammer40k_core.engine.physical_engagement import current_rules_unit_is_physically_engaged
from warhammer40k_core.engine.retained_model_presence import model_is_present_on_battlefield
from warhammer40k_core.engine.rules_unit_effects import rules_unit_persisting_effects
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.unit_rule_effects import fire_overwatch_forbidden_by_effects

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def fire_overwatch_target_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    """Return present enemy rules units permitted by source-owned Overwatch effects.

    Weapon, visibility, range and runtime target restrictions remain the shared
    shooting candidate authority's responsibility.
    """
    return tuple(
        sorted(
            unit.unit_instance_id
            for unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
            if unit.owner_player_id != player_id
            and any(
                model_is_present_on_battlefield(
                    state=state, model_instance_id=model.model_instance_id
                )
                for component in unit.components
                for model in component.unit.own_models
            )
            and not fire_overwatch_forbidden_by_effects(
                tuple(
                    effect
                    for _, effect in rules_unit_persisting_effects(state, unit.unit_instance_id)
                ),
                owner_player_id=unit.owner_player_id,
            )
        )
    )


def fire_overwatch_shooter_ineligibility_reason(
    *, state: GameState, player_id: str, unit_instance_id: str, army_catalog: ArmyCatalog
) -> str | None:
    """Shared shooter checks that do not resolve any unselected shot's visibility."""
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    return _shooter_ineligibility_reason(
        state=state, player_id=player_id, unit=unit, army_catalog=army_catalog
    )


def _shooter_ineligibility_reason(
    *, state: GameState, player_id: str, unit: RulesUnitView, army_catalog: ArmyCatalog
) -> str | None:
    """Consume the current authoritative view, including discovery's enumerated view."""
    if unit.owner_player_id != player_id:
        raise GameLifecycleError("Fire Overwatch shooter owner drift.")
    if state.battlefield_state is None:
        return "fire_overwatch_requires_battlefield"
    if not any(
        model_is_present_on_battlefield(state=state, model_instance_id=model.model_instance_id)
        for model in unit.alive_models()
    ):
        return "fire_overwatch_unit_ineligible_to_shoot"
    if "TITANIC" in unit.keywords:
        return "fire_overwatch_unit_titanic"
    if current_rules_unit_is_physically_engaged(
        state=state, unit_instance_id=unit.unit_instance_id
    ):
        return "fire_overwatch_unit_engaged"
    if not shooting_unit_can_select_to_shoot(
        state=state, unit=unit.components[0].unit, army_catalog=army_catalog, player_id=player_id
    ):
        return "fire_overwatch_unit_ineligible_to_shoot"
    return None


def fire_overwatch_has_potential_shooter(
    *, state: GameState, player_id: str, army_catalog: ArmyCatalog
) -> bool:
    """Exclude impossible windows without deciding visibility for an unchosen shot."""
    if not fire_overwatch_target_unit_ids(state=state, player_id=player_id):
        return False
    return any(
        _shooter_ineligibility_reason(
            state=state,
            player_id=player_id,
            unit=unit,
            army_catalog=army_catalog,
        )
        is None
        for unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if unit.owner_player_id == player_id
    )
