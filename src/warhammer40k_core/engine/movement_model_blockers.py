"""Physical Monster/Vehicle blockers shared by witnessed movement consumers."""

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.phase import GameLifecycleError

_validate_identifier = IdentifierValidator(GameLifecycleError)


def vehicle_monster_model_ids_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    friendly: bool,
    moving_model_instance_id: str | None = None,
) -> tuple[str, ...]:
    """Classify present physical models, never their unit's union of keywords."""
    requested_player_id = _validate_identifier("player_id", player_id)
    if type(friendly) is not bool:
        raise GameLifecycleError("friendly must be a bool.")
    moving_model_id = (
        None
        if moving_model_instance_id is None
        else _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    )
    model_ids: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if (placed_army.player_id == requested_player_id) is not friendly:
            continue
        for unit_placement in placed_army.unit_placements:
            for placement in unit_placement.model_placements:
                if placement.model_instance_id == moving_model_id:
                    continue
                if not scenario.model_is_present_at_placement(placement):
                    continue
                model = scenario.model_instance_for_placement(placement)
                if "MONSTER" in model.keywords or "VEHICLE" in model.keywords:
                    model_ids.append(model.model_instance_id)
    return tuple(sorted(model_ids))
