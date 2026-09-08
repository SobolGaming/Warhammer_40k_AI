from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    ModelRemovalRecord,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus

_validate_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class RuleModelDestructionResult:
    model_destroyed_event_id: str | None
    removal_record: ModelRemovalRecord | None
    transition_batch: BattlefieldTransitionBatch | None
    status: LifecycleStatus | None = None

    def __post_init__(self) -> None:
        if self.model_destroyed_event_id is not None:
            object.__setattr__(
                self,
                "model_destroyed_event_id",
                _validate_identifier("model_destroyed_event_id", self.model_destroyed_event_id),
            )
        if self.removal_record is not None and type(self.removal_record) is not ModelRemovalRecord:
            raise GameLifecycleError("Rule destruction removal record is invalid.")
        if self.transition_batch is not None and type(self.transition_batch) is not (
            BattlefieldTransitionBatch
        ):
            raise GameLifecycleError("Rule destruction transition batch is invalid.")
        if self.status is not None and type(self.status) is not LifecycleStatus:
            raise GameLifecycleError("Rule destruction status must be LifecycleStatus or None.")
        completed = (
            self.model_destroyed_event_id is not None
            and self.removal_record is not None
            and self.transition_batch is not None
        )
        if self.status is None and not completed:
            raise GameLifecycleError("Completed rule destruction requires removal artifacts.")
