from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollSpecPayload,
    DiceRollState,
    DiceRollStatePayload,
    RerollPermission,
    RerollPermissionPayload,
)
from warhammer40k_core.core.modified_dice import (
    ModifiedRollResult,
    ModifiedRollResultPayload,
    UnmodifiedRollResult,
)
from warhammer40k_core.core.modifiers import RollModifier, RollModifierPayload
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError

_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"{field_name} must be a positive integer.")
    return value


def _validate_advance_roll_spec(
    spec: DiceRollSpec,
    *,
    unit_instance_id: str,
) -> None:
    if type(spec) is not DiceRollSpec:
        raise GameLifecycleError("Advance roll spec must be a DiceRollSpec.")
    if spec.expression != DiceExpression(quantity=1, sides=6):
        raise GameLifecycleError("Advance roll spec must contain an unmodified D6.")
    if spec.roll_type != "advance_roll":
        raise GameLifecycleError("Advance roll spec roll_type must be advance_roll.")
    if spec.actor_id != unit_instance_id:
        raise GameLifecycleError("Advance roll spec actor_id must match unit_instance_id.")


def _validate_movement_roll_modifiers(
    field_name: str,
    value: object,
) -> tuple[RollModifier, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    modifiers: list[RollModifier] = []
    seen: set[str] = set()
    for modifier in cast(tuple[object, ...], value):
        if type(modifier) is not RollModifier:
            raise GameLifecycleError(f"{field_name} must contain RollModifier values.")
        if modifier.modifier_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate modifier IDs.")
        seen.add(modifier.modifier_id)
        modifiers.append(modifier)
    return tuple(modifiers)


class AdvanceRollRequestPayload(TypedDict):
    request_id: str
    game_id: str
    battle_round: int
    player_id: str
    unit_instance_id: str
    spec: DiceRollSpecPayload
    roll_modifiers: list[RollModifierPayload]
    reroll_permission: RerollPermissionPayload | None


class AdvanceRollResultPayload(TypedDict):
    request: AdvanceRollRequestPayload
    roll_state: DiceRollStatePayload
    value: int
    modified_roll: ModifiedRollResultPayload


@dataclass(frozen=True, slots=True)
class AdvanceRollRequest:
    request_id: str
    game_id: str
    battle_round: int
    player_id: str
    unit_instance_id: str
    spec: DiceRollSpec
    roll_modifiers: tuple[RollModifier, ...] = ()
    reroll_permission: RerollPermission | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("AdvanceRollRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("AdvanceRollRequest game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("AdvanceRollRequest battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("AdvanceRollRequest player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("AdvanceRollRequest unit_instance_id", self.unit_instance_id),
        )
        if type(self.spec) is not DiceRollSpec:
            raise GameLifecycleError("AdvanceRollRequest spec must be a DiceRollSpec.")
        modifiers = _validate_movement_roll_modifiers(
            "AdvanceRollRequest roll_modifiers",
            self.roll_modifiers,
        )
        object.__setattr__(self, "roll_modifiers", modifiers)
        _validate_advance_roll_spec(
            self.spec,
            unit_instance_id=self.unit_instance_id,
        )
        if self.reroll_permission is not None:
            if type(self.reroll_permission) is not RerollPermission:
                raise GameLifecycleError(
                    "AdvanceRollRequest reroll_permission must be a RerollPermission."
                )
            if self.reroll_permission.owning_player_id != self.player_id:
                raise GameLifecycleError(
                    "AdvanceRollRequest reroll_permission owner must match player_id."
                )
            if self.reroll_permission.eligible_roll_type != self.spec.roll_type:
                raise GameLifecycleError(
                    "AdvanceRollRequest reroll_permission must target advance_roll."
                )

    @classmethod
    def for_unit(
        cls,
        *,
        request_id: str,
        game_id: str,
        battle_round: int,
        player_id: str,
        unit_instance_id: str,
        roll_modifiers: tuple[RollModifier, ...] = (),
        reroll_permission: RerollPermission | None = None,
    ) -> Self:
        modifiers = _validate_movement_roll_modifiers(
            "AdvanceRollRequest roll_modifiers",
            roll_modifiers,
        )
        return cls(
            request_id=request_id,
            game_id=game_id,
            battle_round=battle_round,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            spec=DiceRollSpec(
                expression=DiceExpression(
                    quantity=1,
                    sides=6,
                ),
                reason=f"Advance roll for {unit_instance_id}",
                roll_type="advance_roll",
                actor_id=unit_instance_id,
            ),
            roll_modifiers=modifiers,
            reroll_permission=reroll_permission,
        )

    def to_payload(self) -> AdvanceRollRequestPayload:
        return {
            "request_id": self.request_id,
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "spec": self.spec.to_payload(),
            "roll_modifiers": [modifier.to_payload() for modifier in self.roll_modifiers],
            "reroll_permission": (
                None if self.reroll_permission is None else self.reroll_permission.to_payload()
            ),
        }

    @classmethod
    def from_payload(cls, payload: AdvanceRollRequestPayload) -> Self:
        reroll_permission_payload = payload["reroll_permission"]
        return cls(
            request_id=payload["request_id"],
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            spec=DiceRollSpec.from_payload(payload["spec"]),
            roll_modifiers=tuple(
                RollModifier.from_payload(modifier) for modifier in payload["roll_modifiers"]
            ),
            reroll_permission=(
                None
                if reroll_permission_payload is None
                else RerollPermission.from_payload(reroll_permission_payload)
            ),
        )


@dataclass(frozen=True, slots=True)
class AdvanceRollResult:
    request: AdvanceRollRequest
    roll_state: DiceRollState
    value: int

    def __post_init__(self) -> None:
        if type(self.request) is not AdvanceRollRequest:
            raise GameLifecycleError("AdvanceRollResult request must be an AdvanceRollRequest.")
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("AdvanceRollResult roll_state must be a DiceRollState.")
        if self.roll_state.original_result.spec != self.request.spec:
            raise GameLifecycleError("AdvanceRollResult roll_state spec must match request.")
        if type(self.value) is not int or self.value != self.modified_roll.final_value:
            raise GameLifecycleError("Advance result must match its bounded modifier trace.")

    @property
    def modified_roll(self) -> ModifiedRollResult:
        return ModifiedRollResult.from_unmodified(
            UnmodifiedRollResult.from_state(self.roll_state),
            modifiers=self.request.roll_modifiers,
        )

    @classmethod
    def from_roll_state(cls, *, request: AdvanceRollRequest, roll_state: DiceRollState) -> Self:
        modified = ModifiedRollResult.from_unmodified(
            UnmodifiedRollResult.from_state(roll_state),
            modifiers=request.roll_modifiers,
        )
        return cls(request=request, roll_state=roll_state, value=modified.final_value)

    def to_payload(self) -> AdvanceRollResultPayload:
        return {
            "request": self.request.to_payload(),
            "roll_state": self.roll_state.to_payload(),
            "value": self.value,
            "modified_roll": self.modified_roll.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: AdvanceRollResultPayload) -> Self:
        result = cls(
            request=AdvanceRollRequest.from_payload(payload["request"]),
            roll_state=DiceRollState.from_payload(payload["roll_state"]),
            value=payload["value"],
        )
        if ModifiedRollResult.from_payload(payload["modified_roll"]) != result.modified_roll:
            raise GameLifecycleError("Advance modifier trace drifted.")
        return result
