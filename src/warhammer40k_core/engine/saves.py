from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
)
from warhammer40k_core.core.ruleset_descriptor import CoverEffect
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.geometry.visibility import BenefitOfCoverResult, BenefitOfCoverResultPayload


class SaveKind(StrEnum):
    ARMOUR = "armour"
    INVULNERABLE = "invulnerable"


class SaveResolutionRule(StrEnum):
    UNMODIFIED_ONE = "unmodified_1"
    INVULNERABLE_SAVE = "invulnerable_save"
    ARMOUR_SAVE = "armour_save"
    FAILED = "failed"


class SaveOptionPayload(TypedDict):
    save_kind: str
    target_number: int
    characteristic_target_number: int
    armor_penetration: int
    cover_applied: bool
    cover_result: BenefitOfCoverResultPayload | None
    source_rule_ids: list[str]


class SavingThrowPayload(TypedDict):
    save_kind: str
    target_number: int
    roll_state: DiceRollStatePayload
    unmodified_roll: int
    final_roll: int
    successful: bool
    resolution_rule: str
    option: SaveOptionPayload


class PlungingFireModifierResultPayload(TypedDict):
    source_rule_id: str
    status: str
    reason: str | None
    input_ballistic_skill: int
    final_ballistic_skill: int
    required_height_advantage_inches: float
    actual_height_advantage_inches: float
    target_fully_visible: bool


@dataclass(frozen=True, slots=True)
class SaveOption:
    save_kind: SaveKind
    target_number: int
    characteristic_target_number: int
    armor_penetration: int
    cover_applied: bool = False
    cover_result: BenefitOfCoverResult | None = None
    source_rule_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "save_kind", save_kind_from_token(self.save_kind))
        object.__setattr__(
            self,
            "target_number",
            _validate_save_target("SaveOption target_number", self.target_number),
        )
        object.__setattr__(
            self,
            "characteristic_target_number",
            _validate_save_target(
                "SaveOption characteristic_target_number",
                self.characteristic_target_number,
            ),
        )
        if type(self.armor_penetration) is not int:
            raise GameLifecycleError("SaveOption armor_penetration must be an integer.")
        if type(self.cover_applied) is not bool:
            raise GameLifecycleError("SaveOption cover_applied must be a bool.")
        if self.cover_result is not None and type(self.cover_result) is not BenefitOfCoverResult:
            raise GameLifecycleError("SaveOption cover_result must be BenefitOfCoverResult.")
        object.__setattr__(
            self,
            "source_rule_ids",
            _validate_identifier_tuple("SaveOption source_rule_ids", self.source_rule_ids),
        )
        if self.save_kind is SaveKind.INVULNERABLE and self.cover_applied:
            raise GameLifecycleError("Invulnerable saves must not apply Benefit of Cover.")

    @property
    def can_succeed_on_d6(self) -> bool:
        return self.target_number <= 6

    def to_payload(self) -> SaveOptionPayload:
        return {
            "save_kind": self.save_kind.value,
            "target_number": self.target_number,
            "characteristic_target_number": self.characteristic_target_number,
            "armor_penetration": self.armor_penetration,
            "cover_applied": self.cover_applied,
            "cover_result": None if self.cover_result is None else self.cover_result.to_payload(),
            "source_rule_ids": list(self.source_rule_ids),
        }

    @classmethod
    def from_payload(cls, payload: SaveOptionPayload) -> Self:
        cover_payload = payload["cover_result"]
        return cls(
            save_kind=save_kind_from_token(payload["save_kind"]),
            target_number=payload["target_number"],
            characteristic_target_number=payload["characteristic_target_number"],
            armor_penetration=payload["armor_penetration"],
            cover_applied=payload["cover_applied"],
            cover_result=(
                None if cover_payload is None else BenefitOfCoverResult.from_payload(cover_payload)
            ),
            source_rule_ids=tuple(payload["source_rule_ids"]),
        )


@dataclass(frozen=True, slots=True)
class SavingThrow:
    save_kind: SaveKind
    target_number: int
    roll_state: DiceRollState
    unmodified_roll: int
    final_roll: int
    successful: bool
    resolution_rule: SaveResolutionRule
    option: SaveOption

    def __post_init__(self) -> None:
        object.__setattr__(self, "save_kind", save_kind_from_token(self.save_kind))
        object.__setattr__(
            self,
            "resolution_rule",
            save_resolution_rule_from_token(self.resolution_rule),
        )
        object.__setattr__(
            self,
            "target_number",
            _validate_save_target("SavingThrow target_number", self.target_number),
        )
        if self.save_kind is not self.option.save_kind:
            raise GameLifecycleError("SavingThrow save_kind must match option.")
        if self.target_number != self.option.characteristic_target_number:
            raise GameLifecycleError("SavingThrow target_number must match save characteristic.")
        if type(self.unmodified_roll) is not int or not 1 <= self.unmodified_roll <= 6:
            raise GameLifecycleError("SavingThrow unmodified_roll must be a D6 value.")
        if type(self.final_roll) is not int:
            raise GameLifecycleError("SavingThrow final_roll must be an integer.")
        if type(self.successful) is not bool:
            raise GameLifecycleError("SavingThrow successful must be a bool.")
        expected_final_roll = _final_roll_for_save_option(
            option=self.option,
            unmodified_roll=self.unmodified_roll,
        )
        if self.final_roll != expected_final_roll:
            raise GameLifecycleError("SavingThrow final_roll does not match save option.")
        expected_success = self.resolution_rule in {
            SaveResolutionRule.INVULNERABLE_SAVE,
            SaveResolutionRule.ARMOUR_SAVE,
        }
        if self.resolution_rule is SaveResolutionRule.UNMODIFIED_ONE and self.unmodified_roll != 1:
            raise GameLifecycleError("Unmodified-one save resolution requires a roll of 1.")
        if self.resolution_rule is SaveResolutionRule.INVULNERABLE_SAVE:
            if self.save_kind is not SaveKind.INVULNERABLE:
                raise GameLifecycleError("Invulnerable save resolution requires an InSv option.")
            if self.unmodified_roll < self.target_number:
                raise GameLifecycleError("Invulnerable save resolution does not match the roll.")
        if self.resolution_rule is SaveResolutionRule.ARMOUR_SAVE:
            if self.save_kind is not SaveKind.ARMOUR:
                raise GameLifecycleError("Armour save resolution requires an armour option.")
            if self.unmodified_roll == 1 or self.final_roll < self.target_number:
                raise GameLifecycleError("Armour save resolution does not match the roll.")
        if self.resolution_rule is SaveResolutionRule.FAILED:
            if self.unmodified_roll == 1:
                raise GameLifecycleError("A roll of 1 must use unmodified-one save resolution.")
            if self.final_roll >= self.target_number:
                raise GameLifecycleError("Failed save resolution does not match the roll.")
        if self.successful != expected_success:
            raise GameLifecycleError("SavingThrow success flag does not match roll semantics.")

    def to_payload(self) -> SavingThrowPayload:
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("SavingThrow roll_state must be DiceRollState.")
        return {
            "save_kind": self.save_kind.value,
            "target_number": self.target_number,
            "roll_state": self.roll_state.to_payload(),
            "unmodified_roll": self.unmodified_roll,
            "final_roll": self.final_roll,
            "successful": self.successful,
            "resolution_rule": self.resolution_rule.value,
            "option": self.option.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class PlungingFireModifierResult:
    source_rule_id: str
    status: str
    reason: str | None
    input_ballistic_skill: int
    final_ballistic_skill: int
    required_height_advantage_inches: float
    actual_height_advantage_inches: float
    target_fully_visible: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("PlungingFireModifierResult source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "status",
            _validate_identifier("PlungingFireModifierResult status", self.status),
        )
        if self.status not in {"applied", "not_applicable", "unsupported"}:
            raise GameLifecycleError("PlungingFireModifierResult status is unsupported.")
        object.__setattr__(
            self,
            "reason",
            _validate_optional_identifier("PlungingFireModifierResult reason", self.reason),
        )
        object.__setattr__(
            self,
            "input_ballistic_skill",
            _validate_save_target(
                "PlungingFireModifierResult input Ballistic Skill",
                self.input_ballistic_skill,
            ),
        )
        object.__setattr__(
            self,
            "final_ballistic_skill",
            _validate_save_target(
                "PlungingFireModifierResult final Ballistic Skill",
                self.final_ballistic_skill,
            ),
        )
        if type(self.required_height_advantage_inches) is not float:
            raise GameLifecycleError("PlungingFireModifierResult required height must be float.")
        if type(self.actual_height_advantage_inches) is not float:
            raise GameLifecycleError("PlungingFireModifierResult actual height must be float.")
        if type(self.target_fully_visible) is not bool:
            raise GameLifecycleError("PlungingFireModifierResult visibility must be bool.")
        if self.status == "applied" and self.reason is not None:
            raise GameLifecycleError("Applied Plunging Fire must not include a reason.")
        if self.status != "applied" and self.reason is None:
            raise GameLifecycleError("Non-applied Plunging Fire requires a reason.")

    def to_payload(self) -> PlungingFireModifierResultPayload:
        return {
            "source_rule_id": self.source_rule_id,
            "status": self.status,
            "reason": self.reason,
            "input_ballistic_skill": self.input_ballistic_skill,
            "final_ballistic_skill": self.final_ballistic_skill,
            "required_height_advantage_inches": self.required_height_advantage_inches,
            "actual_height_advantage_inches": self.actual_height_advantage_inches,
            "target_fully_visible": self.target_fully_visible,
        }


@dataclass(frozen=True, slots=True)
class PlungingFireModifier:
    source_rule_id: str
    supported: bool
    required_height_advantage_inches: float = 3.0
    ballistic_skill_modifier: int = -1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("PlungingFireModifier source_rule_id", self.source_rule_id),
        )
        if type(self.supported) is not bool:
            raise GameLifecycleError("PlungingFireModifier supported must be a bool.")
        if type(self.required_height_advantage_inches) is not float:
            raise GameLifecycleError("PlungingFireModifier required height must be a float.")
        if self.required_height_advantage_inches <= 0.0:
            raise GameLifecycleError("PlungingFireModifier required height must be positive.")
        if type(self.ballistic_skill_modifier) is not int:
            raise GameLifecycleError("PlungingFireModifier BS modifier must be an int.")

    def apply(
        self,
        *,
        ballistic_skill: int,
        attacker_z_inches: float,
        target_z_inches: float,
        target_fully_visible: bool,
    ) -> PlungingFireModifierResult:
        skill = _validate_save_target("Plunging Fire ballistic_skill", ballistic_skill)
        if type(attacker_z_inches) is not float:
            raise GameLifecycleError("Plunging Fire attacker height must be a float.")
        if type(target_z_inches) is not float:
            raise GameLifecycleError("Plunging Fire target height must be a float.")
        if type(target_fully_visible) is not bool:
            raise GameLifecycleError("Plunging Fire visibility evidence must be a bool.")
        height_advantage = attacker_z_inches - target_z_inches
        if not self.supported:
            return PlungingFireModifierResult(
                source_rule_id=self.source_rule_id,
                status="unsupported",
                reason="ruleset_does_not_support_plunging_fire",
                input_ballistic_skill=skill,
                final_ballistic_skill=skill,
                required_height_advantage_inches=self.required_height_advantage_inches,
                actual_height_advantage_inches=height_advantage,
                target_fully_visible=target_fully_visible,
            )
        if height_advantage < self.required_height_advantage_inches:
            return PlungingFireModifierResult(
                source_rule_id=self.source_rule_id,
                status="not_applicable",
                reason="height_advantage_not_met",
                input_ballistic_skill=skill,
                final_ballistic_skill=skill,
                required_height_advantage_inches=self.required_height_advantage_inches,
                actual_height_advantage_inches=height_advantage,
                target_fully_visible=target_fully_visible,
            )
        if not target_fully_visible:
            return PlungingFireModifierResult(
                source_rule_id=self.source_rule_id,
                status="not_applicable",
                reason="target_not_fully_visible",
                input_ballistic_skill=skill,
                final_ballistic_skill=skill,
                required_height_advantage_inches=self.required_height_advantage_inches,
                actual_height_advantage_inches=height_advantage,
                target_fully_visible=target_fully_visible,
            )
        return PlungingFireModifierResult(
            source_rule_id=self.source_rule_id,
            status="applied",
            reason=None,
            input_ballistic_skill=skill,
            final_ballistic_skill=max(2, skill + self.ballistic_skill_modifier),
            required_height_advantage_inches=self.required_height_advantage_inches,
            actual_height_advantage_inches=height_advantage,
            target_fully_visible=target_fully_visible,
        )


def save_kind_from_token(token: object) -> SaveKind:
    if type(token) is SaveKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("SaveKind token must be a string.")
    try:
        return SaveKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported SaveKind token: {token}.") from exc


def save_resolution_rule_from_token(token: object) -> SaveResolutionRule:
    if type(token) is SaveResolutionRule:
        return token
    if type(token) is not str:
        raise GameLifecycleError("SaveResolutionRule token must be a string.")
    try:
        return SaveResolutionRule(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported SaveResolutionRule token: {token}.") from exc


def save_options_for_model(
    *,
    model: ModelInstance,
    armor_penetration: int,
    cover_result: BenefitOfCoverResult | None = None,
    no_saves_allowed: bool = False,
) -> tuple[SaveOption, ...]:
    if type(model) is not ModelInstance:
        raise GameLifecycleError("Saving throws require a ModelInstance.")
    if type(armor_penetration) is not int:
        raise GameLifecycleError("Saving throw AP must be an integer.")
    if cover_result is not None and type(cover_result) is not BenefitOfCoverResult:
        raise GameLifecycleError("Saving throw cover_result must be BenefitOfCoverResult.")
    if type(no_saves_allowed) is not bool:
        raise GameLifecycleError("Saving throw no_saves_allowed must be a bool.")
    if no_saves_allowed:
        return ()

    options: list[SaveOption] = []
    armor_save = _model_characteristic(model, Characteristic.SAVE)
    if armor_save is not None:
        options.append(
            SaveOption(
                save_kind=SaveKind.ARMOUR,
                characteristic_target_number=armor_save,
                target_number=_armour_save_target_number(
                    armor_save=armor_save,
                    armor_penetration=armor_penetration,
                    cover_result=cover_result,
                ),
                armor_penetration=armor_penetration,
                cover_applied=_cover_applies_to_armour_save(
                    armor_save=armor_save,
                    armor_penetration=armor_penetration,
                    cover_result=cover_result,
                ),
                cover_result=cover_result,
                source_rule_ids=(
                    ("benefit_of_cover",)
                    if _cover_applies_to_armour_save(
                        armor_save=armor_save,
                        armor_penetration=armor_penetration,
                        cover_result=cover_result,
                    )
                    else ()
                ),
            )
        )

    invulnerable_save = _model_characteristic(model, Characteristic.INVULNERABLE_SAVE)
    if invulnerable_save is not None:
        options.append(
            SaveOption(
                save_kind=SaveKind.INVULNERABLE,
                characteristic_target_number=invulnerable_save,
                target_number=invulnerable_save,
                armor_penetration=armor_penetration,
            )
        )
    return tuple(options)


def mandatory_save_option(options: tuple[SaveOption, ...]) -> SaveOption | None:
    selectable = _selectable_save_options(options)
    invulnerable_options = tuple(
        option for option in selectable if option.save_kind is SaveKind.INVULNERABLE
    )
    if invulnerable_options:
        return min(
            invulnerable_options,
            key=lambda option: (
                option.target_number,
                option.characteristic_target_number,
                option.source_rule_ids,
            ),
        )
    armour_options = tuple(option for option in selectable if option.save_kind is SaveKind.ARMOUR)
    if not armour_options:
        return None
    if len(armour_options) != 1:
        raise GameLifecycleError("Saving throw options must contain at most one armour save.")
    return armour_options[0]


def saving_throw_roll_spec(
    *,
    save_kind: SaveKind,
    player_id: str,
    allocated_model_id: str,
    attack_context_id: str,
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"{save_kind.value} save for {allocated_model_id} from {attack_context_id}",
        roll_type=f"attack_sequence.save.{save_kind.value}",
        actor_id=player_id,
    )


def resolve_saving_throw(
    *,
    roll_state: DiceRollState,
    option: SaveOption | None = None,
    options: tuple[SaveOption, ...] | None = None,
) -> SavingThrow:
    if type(roll_state) is not DiceRollState:
        raise GameLifecycleError("Saving throw roll_state must be DiceRollState.")
    save_options = _save_options_for_resolution(option=option, options=options)
    unmodified = roll_state.current_total
    resolved_option, resolution_rule = _resolve_save_option_for_roll(
        options=save_options,
        unmodified_roll=unmodified,
    )
    final_roll = _final_roll_for_save_option(
        option=resolved_option,
        unmodified_roll=unmodified,
    )
    return SavingThrow(
        save_kind=resolved_option.save_kind,
        target_number=resolved_option.characteristic_target_number,
        roll_state=roll_state,
        unmodified_roll=unmodified,
        final_roll=final_roll,
        successful=(
            resolution_rule
            in {SaveResolutionRule.INVULNERABLE_SAVE, SaveResolutionRule.ARMOUR_SAVE}
        ),
        resolution_rule=resolution_rule,
        option=resolved_option,
    )


def _save_options_for_resolution(
    *,
    option: SaveOption | None,
    options: tuple[SaveOption, ...] | None,
) -> tuple[SaveOption, ...]:
    if option is not None and options is not None:
        raise GameLifecycleError("Saving throw resolution must receive option or options.")
    if option is not None:
        if type(option) is not SaveOption:
            raise GameLifecycleError("Saving throw option must be SaveOption.")
        return _selectable_save_options((option,))
    if options is None:
        raise GameLifecycleError("Saving throw resolution requires save options.")
    save_options = _selectable_save_options(options)
    if not save_options:
        raise GameLifecycleError("Saving throw resolution requires at least one save option.")
    return save_options


def _resolve_save_option_for_roll(
    *,
    options: tuple[SaveOption, ...],
    unmodified_roll: int,
) -> tuple[SaveOption, SaveResolutionRule]:
    if type(unmodified_roll) is not int or not 1 <= unmodified_roll <= 6:
        raise GameLifecycleError("Saving throw unmodified_roll must be a D6 value.")
    if unmodified_roll == 1:
        return (
            _last_checked_save_option(options),
            SaveResolutionRule.UNMODIFIED_ONE,
        )
    invulnerable_option = next(
        (option for option in options if option.save_kind is SaveKind.INVULNERABLE),
        None,
    )
    if (
        invulnerable_option is not None
        and unmodified_roll >= invulnerable_option.characteristic_target_number
    ):
        return invulnerable_option, SaveResolutionRule.INVULNERABLE_SAVE
    armour_option = next(
        (option for option in options if option.save_kind is SaveKind.ARMOUR),
        None,
    )
    if armour_option is not None and (
        _final_roll_for_save_option(option=armour_option, unmodified_roll=unmodified_roll)
        >= armour_option.characteristic_target_number
    ):
        return armour_option, SaveResolutionRule.ARMOUR_SAVE
    return _last_checked_save_option(options), SaveResolutionRule.FAILED


def _last_checked_save_option(options: tuple[SaveOption, ...]) -> SaveOption:
    armour_option = next(
        (option for option in options if option.save_kind is SaveKind.ARMOUR),
        None,
    )
    if armour_option is not None:
        return armour_option
    invulnerable_option = next(
        (option for option in options if option.save_kind is SaveKind.INVULNERABLE),
        None,
    )
    if invulnerable_option is None:
        raise GameLifecycleError("Saving throw resolution requires at least one save option.")
    return invulnerable_option


def _final_roll_for_save_option(*, option: SaveOption, unmodified_roll: int) -> int:
    if option.save_kind is SaveKind.INVULNERABLE:
        return unmodified_roll
    cover_modifier = 1 if option.cover_applied else 0
    return unmodified_roll + option.armor_penetration + cover_modifier


def cover_result_has_bonus(cover_result: BenefitOfCoverResult | None) -> bool:
    if cover_result is None:
        return False
    if type(cover_result) is not BenefitOfCoverResult:
        raise GameLifecycleError("cover_result must be BenefitOfCoverResult.")
    return cover_result.has_benefit and cover_result.cover_effect is CoverEffect.SAVE_BONUS


def _armour_save_target_number(
    *,
    armor_save: int,
    armor_penetration: int,
    cover_result: BenefitOfCoverResult | None,
) -> int:
    target = armor_save - armor_penetration
    if _cover_applies_to_armour_save(
        armor_save=armor_save,
        armor_penetration=armor_penetration,
        cover_result=cover_result,
    ):
        target -= 1
    return max(target, 2)


def _cover_applies_to_armour_save(
    *,
    armor_save: int,
    armor_penetration: int,
    cover_result: BenefitOfCoverResult | None,
) -> bool:
    if not cover_result_has_bonus(cover_result):
        return False
    if cover_result is None:
        return False
    return not (
        armor_penetration == 0
        and armor_save <= 3
        and cover_result.ap_zero_save_bonus_excluded_for_save_3_plus_or_better
    )


def _selectable_save_options(options: tuple[SaveOption, ...]) -> tuple[SaveOption, ...]:
    if type(options) is not tuple:
        raise GameLifecycleError("Saving throw options must be a tuple.")
    validated: list[SaveOption] = []
    seen: set[SaveKind] = set()
    for option in options:
        if type(option) is not SaveOption:
            raise GameLifecycleError("Saving throw options must contain SaveOption values.")
        if option.save_kind in seen:
            raise GameLifecycleError("Saving throw options must not duplicate save kinds.")
        seen.add(option.save_kind)
        validated.append(option)
    return tuple(sorted(validated, key=lambda option: option.save_kind.value))


def _model_characteristic(model: ModelInstance, characteristic: Characteristic) -> int | None:
    for value in model.characteristics:
        if value.characteristic is characteristic:
            return value.final
    return None


def _validate_save_target(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 2:
        raise GameLifecycleError(f"{field_name} must be at least 2.")
    return value


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)
