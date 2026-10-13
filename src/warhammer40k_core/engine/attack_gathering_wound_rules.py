"""Source-owned Wound rule templates, queried without characteristic dice."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class WoundGatheringPredicate(StrEnum):
    ALWAYS = "always"
    STRENGTH_GREATER_THAN_TOUGHNESS = "strength_greater_than_toughness"
    STRENGTH_NOT_GREATER_THAN_TOUGHNESS = "strength_not_greater_than_toughness"


@dataclass(frozen=True, slots=True)
class WoundGatheringContext:
    state: GameState
    source_phase: BattlePhase
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    weapon_profile: WeaponProfile

    def __post_init__(self) -> None:
        # Reuse real identity/profile validation; no numeric context is invented.
        from warhammer40k_core.engine.runtime_modifiers import HitRollModifierContext

        validated = HitRollModifierContext(
            state=self.state,
            source_phase=self.source_phase,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attacker_model_instance_id=self.attacker_model_instance_id,
            target_unit_instance_id=self.target_unit_instance_id,
            weapon_profile=self.weapon_profile,
        )
        for field in (
            "source_phase",
            "attacking_unit_instance_id",
            "attacker_model_instance_id",
            "target_unit_instance_id",
        ):
            object.__setattr__(self, field, getattr(validated, field))


type WoundGatheringHandler = Callable[[WoundGatheringContext], int]


def validate_wound_gathering_handler(
    handler: WoundGatheringHandler | None, predicate: WoundGatheringPredicate
) -> None:
    if handler is not None and not callable(handler):
        raise GameLifecycleError("Wound gathering handler must be callable.")
    if type(predicate) is not WoundGatheringPredicate:
        raise GameLifecycleError("Wound gathering predicate must be source-owned and typed.")
