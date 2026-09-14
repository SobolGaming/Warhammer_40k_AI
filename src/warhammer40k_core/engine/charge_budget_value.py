from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import cast

import msgspec

from warhammer40k_core.core.modified_dice import ModifiedRollResult, ModifiedRollResultPayload
from warhammer40k_core.core.modifiers import resolve_distance_deltas
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError


class ChargeMoveDistanceModifier(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    modifier_id: str
    source_id: str
    delta_inches: float

    def __post_init__(self) -> None:
        validate = IdentifierValidator(GameLifecycleError)
        validate("Charge distance modifier_id", self.modifier_id)
        validate("Charge distance source_id", self.source_id)
        if type(self.delta_inches) not in {int, float} or not isfinite(self.delta_inches):
            raise GameLifecycleError("Charge distance modifier must be finite.")


class _BudgetPayload(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    modified_roll: ModifiedRollResultPayload
    distance_modifiers: tuple[ChargeMoveDistanceModifier, ...]
    maximum_distance_inches: float


@dataclass(frozen=True, slots=True)
class ChargeMovementBudget:
    modified_roll: ModifiedRollResult
    distance_modifiers: tuple[ChargeMoveDistanceModifier, ...]
    maximum_distance_inches: float

    def __post_init__(self) -> None:
        if type(self.modified_roll) is not ModifiedRollResult:
            raise GameLifecycleError("Charge budget requires its modified roll trace.")
        if self.modified_roll.unmodified.roll_type != "charge_roll":
            raise GameLifecycleError("Charge budget requires a Charge roll.")
        if type(self.distance_modifiers) is not tuple or any(
            type(row) is not ChargeMoveDistanceModifier or not row.source_id
            for row in self.distance_modifiers
        ):
            raise GameLifecycleError("Charge distance modifiers require source-linked records.")
        expected, _ = resolve_distance_deltas(
            float(self.modified_roll.final_value),
            tuple((row.modifier_id, row.delta_inches) for row in self.distance_modifiers),
        )
        if (
            type(self.maximum_distance_inches) not in {int, float}
            or self.maximum_distance_inches != expected
        ):
            raise GameLifecycleError("Charge movement budget distance trace drift.")

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "modified_roll": self.modified_roll.to_payload(),
                    "distance_modifiers": [
                        msgspec.to_builtins(row) for row in self.distance_modifiers
                    ],
                    "maximum_distance_inches": self.maximum_distance_inches,
                }
            ),
        )

    @classmethod
    def from_payload(cls, payload: object) -> ChargeMovementBudget:
        try:
            parsed = msgspec.convert(payload, type=_BudgetPayload, strict=True)
        except msgspec.ValidationError as exc:
            raise GameLifecycleError("Charge budget payload is invalid.") from exc
        result = cls(
            ModifiedRollResult.from_payload(parsed.modified_roll),
            parsed.distance_modifiers,
            parsed.maximum_distance_inches,
        )
        if result.to_payload() != payload:
            raise GameLifecycleError("Charge budget payload shape drift.")
        return result
