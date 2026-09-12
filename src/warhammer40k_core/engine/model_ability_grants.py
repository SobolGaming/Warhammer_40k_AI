"""Source-linked model ability grants consumed by the owning Core ability query."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class ModelAbilityGrantContext:
    state: GameState
    target: RulesUnitView

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState or type(self.target) is not RulesUnitView:
            raise GameLifecycleError("Model ability grants require state and a rules unit.")


@dataclass(frozen=True, slots=True)
class ModelAbilityGrantBinding:
    modifier_id: str
    source_id: str
    ability_id: str
    handler: Callable[[ModelAbilityGrantContext], tuple[str, ...]]

    def __post_init__(self) -> None:
        for value in (self.modifier_id, self.source_id, self.ability_id):
            if type(value) is not str or not value or value != value.strip():
                raise GameLifecycleError("Model ability grant identities must be nonempty IDs.")
        if not callable(self.handler):
            raise GameLifecycleError("Model ability grant handler must be callable.")

    def model_ids(self, context: ModelAbilityGrantContext) -> tuple[str, ...]:
        ids = self.handler(context)
        if type(ids) is not tuple or any(type(item) is not str for item in ids):
            raise GameLifecycleError("Model ability grant must return a tuple of model IDs.")
        if len(ids) != len(set(ids)) or not set(ids).issubset(
            {
                model.model_instance_id
                for model in context.target.own_models
                if model.is_alive or model.model_instance_id in context.target.retained_model_ids
            }
        ):
            raise GameLifecycleError("Model ability grant returned duplicate or foreign models.")
        return tuple(sorted(ids))
