from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.allocated_attack_damage_modifiers import (
    AllocatedAttackDamageModifierBinding,
    AllocatedAttackDamageModifierContext,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.saves import SaveOption
from warhammer40k_core.engine.source_backed_rerolls import (
    SourceBackedRerollPermissionContext,
    select_source_backed_reroll_permission_context,
    source_backed_reroll_permission_contexts_for_unit,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


type UnitCharacteristicModifierHandler = Callable[
    ["UnitCharacteristicModifierContext"],
    int,
]
type HitRollModifierHandler = Callable[["HitRollModifierContext"], int]
type WoundRollModifierHandler = Callable[["WoundRollModifierContext"], int]
type DamageRollModifierHandler = Callable[["DamageRollModifierContext"], int]
type SaveOptionModifierHandler = Callable[
    ["SaveOptionModifierContext"],
    tuple[SaveOption, ...],
]
type MovementBudgetModifierHandler = Callable[["MovementBudgetModifierContext"], float]
type ObjectiveControlModifierHandler = Callable[["ObjectiveControlModifierContext"], int]
type AdvanceRollModifierHandler = Callable[
    ["AdvanceRollModifierContext"],
    tuple[RollModifier, ...],
]
type ChargeRollModifierHandler = Callable[
    ["ChargeRollModifierContext"],
    tuple[RollModifier, ...],
]
type WeaponProfileModifierHandler = Callable[["WeaponProfileModifierContext"], WeaponProfile]
type AttackRerollPermissionHandler = Callable[
    ["AttackRerollPermissionContext"],
    SourceBackedRerollPermissionContext | None,
]
type FailedSaveDamageReplacementHandler = Callable[
    ["FailedSaveDamageReplacementContext"],
    "FailedSaveDamageReplacement | None",
]


@dataclass(frozen=True, slots=True)
class UnitCharacteristicModifierContext:
    state: GameState
    unit_instance_id: str
    characteristic: Characteristic
    base_value: int
    current_value: int

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Unit characteristic modifier state must be GameState.")
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "characteristic",
            _characteristic_from_token(self.characteristic),
        )
        object.__setattr__(
            self,
            "base_value",
            _validate_non_negative_int("base_value", self.base_value),
        )
        object.__setattr__(
            self,
            "current_value",
            _validate_non_negative_int("current_value", self.current_value),
        )


@dataclass(frozen=True, slots=True)
class HitRollModifierContext:
    state: GameState
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    weapon_profile: WeaponProfile
    source_phase: BattlePhase

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Hit roll modifier state must be GameState.")
        object.__setattr__(
            self,
            "attacking_unit_instance_id",
            _validate_identifier(
                "attacking_unit_instance_id",
                self.attacking_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier("attacker_model_instance_id", self.attacker_model_instance_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError("Hit roll modifier profile must be WeaponProfile.")
        object.__setattr__(self, "source_phase", _battle_phase_from_token(self.source_phase))


@dataclass(frozen=True, slots=True)
class HitRollMinimumUnmodifiedSuccessContext:
    state: GameState
    source_phase: BattlePhase
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    weapon_profile: WeaponProfile
    targeting_rule_ids: tuple[str, ...]
    current_minimum_unmodified_success: int

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Hit roll minimum success state must be GameState.")
        object.__setattr__(self, "source_phase", _battle_phase_from_token(self.source_phase))
        object.__setattr__(
            self,
            "attacking_unit_instance_id",
            _validate_identifier(
                "attacking_unit_instance_id",
                self.attacking_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier("attacker_model_instance_id", self.attacker_model_instance_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError("Hit roll minimum success profile must be WeaponProfile.")
        object.__setattr__(
            self,
            "targeting_rule_ids",
            _validate_identifier_tuple(
                "targeting_rule_ids",
                self.targeting_rule_ids,
                min_length=0,
                sort_values=True,
            ),
        )
        object.__setattr__(
            self,
            "current_minimum_unmodified_success",
            _validate_d6_target(
                "current_minimum_unmodified_success",
                self.current_minimum_unmodified_success,
            ),
        )


@dataclass(frozen=True, slots=True)
class WoundRollModifierContext:
    state: GameState
    source_phase: BattlePhase
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    weapon_profile: WeaponProfile
    strength: int
    toughness: int

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Wound roll modifier state must be GameState.")
        object.__setattr__(self, "source_phase", _battle_phase_from_token(self.source_phase))
        object.__setattr__(
            self,
            "attacking_unit_instance_id",
            _validate_identifier(
                "attacking_unit_instance_id",
                self.attacking_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier(
                "attacker_model_instance_id",
                self.attacker_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError("Wound roll modifier profile must be WeaponProfile.")
        object.__setattr__(self, "strength", _validate_positive_int("strength", self.strength))
        object.__setattr__(self, "toughness", _validate_positive_int("toughness", self.toughness))


@dataclass(frozen=True, slots=True)
class DamageRollModifierContext:
    state: GameState
    source_phase: BattlePhase
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    weapon_profile: WeaponProfile
    current_value: int

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Damage roll modifier state must be GameState.")
        object.__setattr__(self, "source_phase", _battle_phase_from_token(self.source_phase))
        object.__setattr__(
            self,
            "attacking_unit_instance_id",
            _validate_identifier(
                "attacking_unit_instance_id",
                self.attacking_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier(
                "attacker_model_instance_id",
                self.attacker_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError("Damage roll modifier profile must be WeaponProfile.")
        object.__setattr__(
            self,
            "current_value",
            _validate_positive_int("current_value", self.current_value),
        )


@dataclass(frozen=True, slots=True)
class SaveOptionModifierContext:
    state: GameState
    target_unit_instance_id: str
    save_options: tuple[SaveOption, ...]
    source_phase: BattlePhase | None = None
    attacking_unit_instance_id: str | None = None
    attacker_model_instance_id: str | None = None
    weapon_profile: WeaponProfile | None = None
    allocated_model_instance_id: str | None = None

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Save option modifier state must be GameState.")
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        object.__setattr__(
            self,
            "save_options",
            _validate_save_option_tuple("save_options", self.save_options),
        )
        object.__setattr__(
            self,
            "source_phase",
            None if self.source_phase is None else _battle_phase_from_token(self.source_phase),
        )
        object.__setattr__(
            self,
            "attacking_unit_instance_id",
            _validate_optional_identifier(
                "attacking_unit_instance_id",
                self.attacking_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_optional_identifier(
                "attacker_model_instance_id",
                self.attacker_model_instance_id,
            ),
        )
        if self.weapon_profile is not None and type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError("Save option modifier profile must be WeaponProfile.")
        object.__setattr__(
            self,
            "allocated_model_instance_id",
            _validate_optional_identifier(
                "allocated_model_instance_id",
                self.allocated_model_instance_id,
            ),
        )


@dataclass(frozen=True, slots=True)
class MovementBudgetModifierContext:
    state: GameState
    unit_instance_id: str
    model_instance_id: str
    base_movement_inches: float
    current_movement_inches: float

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Movement budget modifier state must be GameState.")
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier("model_instance_id", self.model_instance_id),
        )
        object.__setattr__(
            self,
            "base_movement_inches",
            _validate_non_negative_float("base_movement_inches", self.base_movement_inches),
        )
        object.__setattr__(
            self,
            "current_movement_inches",
            _validate_non_negative_float("current_movement_inches", self.current_movement_inches),
        )


@dataclass(frozen=True, slots=True)
class ObjectiveControlModifierContext:
    state: GameState
    unit_instance_id: str
    model_instance_id: str
    base_objective_control: int
    current_objective_control: int

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Objective Control modifier state must be GameState.")
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier("model_instance_id", self.model_instance_id),
        )
        object.__setattr__(
            self,
            "base_objective_control",
            _validate_non_negative_int("base_objective_control", self.base_objective_control),
        )
        object.__setattr__(
            self,
            "current_objective_control",
            _validate_non_negative_int(
                "current_objective_control",
                self.current_objective_control,
            ),
        )


@dataclass(frozen=True, slots=True)
class AdvanceRollModifierContext:
    state: GameState
    unit_instance_id: str
    current_roll_modifiers: tuple[RollModifier, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Advance roll modifier state must be GameState.")
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "current_roll_modifiers",
            _validate_roll_modifier_tuple(
                "current_roll_modifiers",
                self.current_roll_modifiers,
            ),
        )


@dataclass(frozen=True, slots=True)
class ChargeRollModifierContext:
    state: GameState
    unit_instance_id: str
    current_roll_modifiers: tuple[RollModifier, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Charge roll modifier state must be GameState.")
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "current_roll_modifiers",
            _validate_roll_modifier_tuple(
                "current_roll_modifiers",
                self.current_roll_modifiers,
            ),
        )


@dataclass(frozen=True, slots=True)
class WeaponProfileModifierContext:
    state: GameState
    source_phase: BattlePhase
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    weapon_profile: WeaponProfile

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Weapon profile modifier state must be GameState.")
        object.__setattr__(self, "source_phase", _battle_phase_from_token(self.source_phase))
        object.__setattr__(
            self,
            "attacking_unit_instance_id",
            _validate_identifier(
                "attacking_unit_instance_id",
                self.attacking_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier(
                "attacker_model_instance_id",
                self.attacker_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError("Weapon profile modifier profile must be WeaponProfile.")


@dataclass(frozen=True, slots=True)
class AttackRerollPermissionContext:
    state: GameState
    player_id: str
    attacking_unit_instance_id: str
    attacker_model_instance_id: str | None
    target_unit_instance_id: str
    source_phase: BattlePhase
    roll_type: str
    timing_window: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Attack reroll permission state must be GameState.")
        for field_name in (
            "player_id",
            "attacking_unit_instance_id",
            "target_unit_instance_id",
            "roll_type",
            "timing_window",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        if self.attacker_model_instance_id is not None:
            object.__setattr__(
                self,
                "attacker_model_instance_id",
                _validate_identifier(
                    "attacker_model_instance_id",
                    self.attacker_model_instance_id,
                ),
            )
        object.__setattr__(self, "source_phase", _battle_phase_from_token(self.source_phase))


@dataclass(frozen=True, slots=True)
class FailedSaveDamageReplacementContext:
    state: GameState
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    allocated_model_instance_id: str
    source_phase: BattlePhase

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("Failed-save damage replacement state must be GameState.")
        for field_name in (
            "attacking_unit_instance_id",
            "attacker_model_instance_id",
            "target_unit_instance_id",
            "allocated_model_instance_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        object.__setattr__(self, "source_phase", _battle_phase_from_token(self.source_phase))


@dataclass(frozen=True, slots=True)
class FailedSaveDamageReplacement:
    source_id: str
    source_unit_instance_id: str
    replacement_damage: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "source_unit_instance_id",
            _validate_identifier(
                "source_unit_instance_id",
                self.source_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "replacement_damage",
            _validate_non_negative_int("replacement_damage", self.replacement_damage),
        )


@dataclass(frozen=True, slots=True)
class UnitCharacteristicModifierBinding:
    modifier_id: str
    source_id: str
    handler: UnitCharacteristicModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="unit characteristic modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class HitRollModifierBinding:
    modifier_id: str
    source_id: str
    handler: HitRollModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="Hit roll modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class WoundRollModifierBinding:
    modifier_id: str
    source_id: str
    handler: WoundRollModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="Wound roll modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class DamageRollModifierBinding:
    modifier_id: str
    source_id: str
    handler: DamageRollModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="Damage roll modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class SaveOptionModifierBinding:
    modifier_id: str
    source_id: str
    handler: SaveOptionModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="save option modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class MovementBudgetModifierBinding:
    modifier_id: str
    source_id: str
    handler: MovementBudgetModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="movement budget modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class ObjectiveControlModifierBinding:
    modifier_id: str
    source_id: str
    handler: ObjectiveControlModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="Objective Control modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class AdvanceRollModifierBinding:
    modifier_id: str
    source_id: str
    handler: AdvanceRollModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="advance roll modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class ChargeRollModifierBinding:
    modifier_id: str
    source_id: str
    handler: ChargeRollModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="charge roll modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class WeaponProfileModifierBinding:
    modifier_id: str
    source_id: str
    handler: WeaponProfileModifierHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="weapon profile modifier",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class AttackRerollPermissionBinding:
    modifier_id: str
    source_id: str
    handler: AttackRerollPermissionHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="attack reroll permission",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class FailedSaveDamageReplacementBinding:
    modifier_id: str
    source_id: str
    handler: FailedSaveDamageReplacementHandler

    def __post_init__(self) -> None:
        _validate_modifier_binding(
            field_prefix="failed-save damage replacement",
            modifier_id=self.modifier_id,
            source_id=self.source_id,
            handler=self.handler,
        )


@dataclass(frozen=True, slots=True)
class RuntimeModifierRegistry:
    unit_characteristic_modifier_bindings: tuple[UnitCharacteristicModifierBinding, ...] = ()
    hit_roll_modifier_bindings: tuple[HitRollModifierBinding, ...] = ()
    wound_roll_modifier_bindings: tuple[WoundRollModifierBinding, ...] = ()
    damage_roll_modifier_bindings: tuple[DamageRollModifierBinding, ...] = ()
    allocated_attack_damage_modifier_bindings: tuple[
        AllocatedAttackDamageModifierBinding,
        ...,
    ] = ()
    save_option_modifier_bindings: tuple[SaveOptionModifierBinding, ...] = ()
    movement_budget_modifier_bindings: tuple[MovementBudgetModifierBinding, ...] = ()
    objective_control_modifier_bindings: tuple[ObjectiveControlModifierBinding, ...] = ()
    advance_roll_modifier_bindings: tuple[AdvanceRollModifierBinding, ...] = ()
    charge_roll_modifier_bindings: tuple[ChargeRollModifierBinding, ...] = ()
    weapon_profile_modifier_bindings: tuple[WeaponProfileModifierBinding, ...] = ()
    attack_reroll_permission_bindings: tuple[AttackRerollPermissionBinding, ...] = ()
    failed_save_damage_replacement_bindings: tuple[
        FailedSaveDamageReplacementBinding,
        ...,
    ] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_characteristic_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry unit_characteristic_modifier_bindings",
                self.unit_characteristic_modifier_bindings,
                UnitCharacteristicModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "hit_roll_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry hit_roll_modifier_bindings",
                self.hit_roll_modifier_bindings,
                HitRollModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "wound_roll_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry wound_roll_modifier_bindings",
                self.wound_roll_modifier_bindings,
                WoundRollModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "damage_roll_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry damage_roll_modifier_bindings",
                self.damage_roll_modifier_bindings,
                DamageRollModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "allocated_attack_damage_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry allocated_attack_damage_modifier_bindings",
                self.allocated_attack_damage_modifier_bindings,
                AllocatedAttackDamageModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "save_option_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry save_option_modifier_bindings",
                self.save_option_modifier_bindings,
                SaveOptionModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "movement_budget_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry movement_budget_modifier_bindings",
                self.movement_budget_modifier_bindings,
                MovementBudgetModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "objective_control_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry objective_control_modifier_bindings",
                self.objective_control_modifier_bindings,
                ObjectiveControlModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "advance_roll_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry advance_roll_modifier_bindings",
                self.advance_roll_modifier_bindings,
                AdvanceRollModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "charge_roll_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry charge_roll_modifier_bindings",
                self.charge_roll_modifier_bindings,
                ChargeRollModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "weapon_profile_modifier_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry weapon_profile_modifier_bindings",
                self.weapon_profile_modifier_bindings,
                WeaponProfileModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "attack_reroll_permission_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry attack_reroll_permission_bindings",
                self.attack_reroll_permission_bindings,
                AttackRerollPermissionBinding,
            ),
        )
        object.__setattr__(
            self,
            "failed_save_damage_replacement_bindings",
            _validate_bindings(
                "RuntimeModifierRegistry failed_save_damage_replacement_bindings",
                self.failed_save_damage_replacement_bindings,
                FailedSaveDamageReplacementBinding,
            ),
        )

    @classmethod
    def empty(cls) -> Self:
        return cls()

    @classmethod
    def from_bindings(
        cls,
        *,
        unit_characteristic_modifier_bindings: tuple[
            UnitCharacteristicModifierBinding,
            ...,
        ] = (),
        hit_roll_modifier_bindings: tuple[HitRollModifierBinding, ...] = (),
        wound_roll_modifier_bindings: tuple[WoundRollModifierBinding, ...] = (),
        damage_roll_modifier_bindings: tuple[DamageRollModifierBinding, ...] = (),
        allocated_attack_damage_modifier_bindings: tuple[
            AllocatedAttackDamageModifierBinding,
            ...,
        ] = (),
        save_option_modifier_bindings: tuple[SaveOptionModifierBinding, ...] = (),
        movement_budget_modifier_bindings: tuple[MovementBudgetModifierBinding, ...] = (),
        objective_control_modifier_bindings: tuple[ObjectiveControlModifierBinding, ...] = (),
        advance_roll_modifier_bindings: tuple[AdvanceRollModifierBinding, ...] = (),
        charge_roll_modifier_bindings: tuple[ChargeRollModifierBinding, ...] = (),
        weapon_profile_modifier_bindings: tuple[WeaponProfileModifierBinding, ...] = (),
        attack_reroll_permission_bindings: tuple[AttackRerollPermissionBinding, ...] = (),
        failed_save_damage_replacement_bindings: tuple[
            FailedSaveDamageReplacementBinding,
            ...,
        ] = (),
    ) -> Self:
        return cls(
            unit_characteristic_modifier_bindings=unit_characteristic_modifier_bindings,
            hit_roll_modifier_bindings=hit_roll_modifier_bindings,
            wound_roll_modifier_bindings=wound_roll_modifier_bindings,
            damage_roll_modifier_bindings=damage_roll_modifier_bindings,
            allocated_attack_damage_modifier_bindings=(allocated_attack_damage_modifier_bindings),
            save_option_modifier_bindings=save_option_modifier_bindings,
            movement_budget_modifier_bindings=movement_budget_modifier_bindings,
            objective_control_modifier_bindings=objective_control_modifier_bindings,
            advance_roll_modifier_bindings=advance_roll_modifier_bindings,
            charge_roll_modifier_bindings=charge_roll_modifier_bindings,
            weapon_profile_modifier_bindings=weapon_profile_modifier_bindings,
            attack_reroll_permission_bindings=attack_reroll_permission_bindings,
            failed_save_damage_replacement_bindings=(failed_save_damage_replacement_bindings),
        )

    def all_unit_characteristic_bindings(self) -> tuple[UnitCharacteristicModifierBinding, ...]:
        return self.unit_characteristic_modifier_bindings

    def all_hit_roll_bindings(self) -> tuple[HitRollModifierBinding, ...]:
        return self.hit_roll_modifier_bindings

    def all_wound_roll_bindings(self) -> tuple[WoundRollModifierBinding, ...]:
        return self.wound_roll_modifier_bindings

    def all_damage_roll_bindings(self) -> tuple[DamageRollModifierBinding, ...]:
        return self.damage_roll_modifier_bindings

    def all_allocated_attack_damage_bindings(
        self,
    ) -> tuple[AllocatedAttackDamageModifierBinding, ...]:
        return self.allocated_attack_damage_modifier_bindings

    def all_save_option_bindings(self) -> tuple[SaveOptionModifierBinding, ...]:
        return self.save_option_modifier_bindings

    def all_movement_budget_bindings(self) -> tuple[MovementBudgetModifierBinding, ...]:
        return self.movement_budget_modifier_bindings

    def all_objective_control_bindings(self) -> tuple[ObjectiveControlModifierBinding, ...]:
        return self.objective_control_modifier_bindings

    def all_advance_roll_bindings(self) -> tuple[AdvanceRollModifierBinding, ...]:
        return self.advance_roll_modifier_bindings

    def all_charge_roll_bindings(self) -> tuple[ChargeRollModifierBinding, ...]:
        return self.charge_roll_modifier_bindings

    def all_weapon_profile_bindings(self) -> tuple[WeaponProfileModifierBinding, ...]:
        return self.weapon_profile_modifier_bindings

    def all_attack_reroll_permission_bindings(
        self,
    ) -> tuple[AttackRerollPermissionBinding, ...]:
        return self.attack_reroll_permission_bindings

    def attack_reroll_permission_context(
        self,
        context: AttackRerollPermissionContext,
    ) -> SourceBackedRerollPermissionContext | None:
        return select_source_backed_reroll_permission_context(
            self.attack_reroll_permission_contexts(context)
        )

    def attack_reroll_permission_contexts(
        self,
        context: AttackRerollPermissionContext,
    ) -> tuple[SourceBackedRerollPermissionContext, ...]:
        if type(context) is not AttackRerollPermissionContext:
            raise GameLifecycleError("Attack reroll permissions require a context.")
        return tuple(
            candidate
            for binding in self.attack_reroll_permission_bindings
            if (candidate := binding.handler(context)) is not None
        )

    def failed_save_damage_replacement(
        self,
        context: FailedSaveDamageReplacementContext,
    ) -> FailedSaveDamageReplacement | None:
        if type(context) is not FailedSaveDamageReplacementContext:
            raise GameLifecycleError("Failed-save damage replacements require a context.")
        candidates = tuple(
            candidate
            for binding in self.failed_save_damage_replacement_bindings
            if (candidate := binding.handler(context)) is not None
        )
        if len(candidates) > 1:
            raise GameLifecycleError("Multiple failed-save damage replacements are available.")
        return candidates[0] if candidates else None

    def modified_unit_characteristic(self, context: UnitCharacteristicModifierContext) -> int:
        if type(context) is not UnitCharacteristicModifierContext:
            raise GameLifecycleError("Unit characteristic modifiers require a context.")
        from warhammer40k_core.engine.generic_rule_attack_hooks import (
            generic_rule_modified_unit_characteristic,
        )

        current = context.current_value
        for binding in self.unit_characteristic_modifier_bindings:
            current = _validate_non_negative_int(
                f"{binding.modifier_id} returned value",
                binding.handler(replace(context, current_value=current)),
            )
        return generic_rule_modified_unit_characteristic(replace(context, current_value=current))

    def hit_roll_modifier(self, context: HitRollModifierContext) -> int:
        if type(context) is not HitRollModifierContext:
            raise GameLifecycleError("Hit roll modifiers require a context.")
        from warhammer40k_core.engine.generic_rule_attack_hooks import (
            generic_rule_hit_roll_modifier,
        )

        total = 0
        for binding in self.hit_roll_modifier_bindings:
            total += _validate_int(
                f"{binding.modifier_id} returned modifier",
                binding.handler(context),
            )
        total += generic_rule_hit_roll_modifier(context)
        return total

    def minimum_unmodified_hit_success(
        self,
        context: HitRollMinimumUnmodifiedSuccessContext,
    ) -> int:
        if type(context) is not HitRollMinimumUnmodifiedSuccessContext:
            raise GameLifecycleError("Hit roll minimum success modifiers require a context.")
        from warhammer40k_core.engine.generic_rule_attack_hooks import (
            generic_rule_minimum_unmodified_hit_success,
        )

        return _validate_d6_target(
            "generic hit roll minimum success",
            generic_rule_minimum_unmodified_hit_success(context),
        )

    def wound_roll_modifier(self, context: WoundRollModifierContext) -> int:
        if type(context) is not WoundRollModifierContext:
            raise GameLifecycleError("Wound roll modifiers require a context.")
        from warhammer40k_core.engine.generic_rule_attack_hooks import (
            generic_rule_wound_roll_modifier,
        )

        total = 0
        for binding in self.wound_roll_modifier_bindings:
            total += _validate_int(
                f"{binding.modifier_id} returned modifier",
                binding.handler(context),
            )
        total += generic_rule_wound_roll_modifier(context)
        return total

    def damage_roll_modifier(self, context: DamageRollModifierContext) -> int:
        if type(context) is not DamageRollModifierContext:
            raise GameLifecycleError("Damage roll modifiers require a context.")
        from warhammer40k_core.engine.generic_rule_attack_hooks import (
            generic_rule_damage_roll_modifier,
        )

        total = 0
        for binding in self.damage_roll_modifier_bindings:
            total += _validate_int(
                f"{binding.modifier_id} returned modifier",
                binding.handler(context),
            )
        total += generic_rule_damage_roll_modifier(context)
        return total

    def allocated_attack_damage_modifier(
        self,
        context: AllocatedAttackDamageModifierContext,
    ) -> int:
        if type(context) is not AllocatedAttackDamageModifierContext:
            raise GameLifecycleError("Allocated-attack Damage modifiers require a context.")
        total = 0
        for binding in self.allocated_attack_damage_modifier_bindings:
            total += _validate_int(
                f"{binding.modifier_id} returned modifier",
                binding.handler(context),
            )
        return total

    def modified_save_options(
        self,
        context: SaveOptionModifierContext,
    ) -> tuple[SaveOption, ...]:
        if type(context) is not SaveOptionModifierContext:
            raise GameLifecycleError("Save option modifiers require a context.")
        from warhammer40k_core.engine.generic_rule_attack_hooks import (
            generic_rule_modified_save_options,
        )

        current = context.save_options
        for binding in self.save_option_modifier_bindings:
            current = _validate_save_option_tuple(
                f"{binding.modifier_id} returned save_options",
                binding.handler(replace(context, save_options=current)),
            )
        return generic_rule_modified_save_options(replace(context, save_options=current))

    def modified_movement_inches(self, context: MovementBudgetModifierContext) -> float:
        if type(context) is not MovementBudgetModifierContext:
            raise GameLifecycleError("Movement budget modifiers require a context.")
        from warhammer40k_core.engine.generic_rule_attack_hooks import (
            generic_rule_modified_movement_inches,
        )

        current = context.current_movement_inches
        for binding in self.movement_budget_modifier_bindings:
            current = _validate_non_negative_float(
                f"{binding.modifier_id} returned movement",
                binding.handler(replace(context, current_movement_inches=current)),
            )
        return generic_rule_modified_movement_inches(
            replace(context, current_movement_inches=current)
        )

    def modified_objective_control(self, context: ObjectiveControlModifierContext) -> int:
        if type(context) is not ObjectiveControlModifierContext:
            raise GameLifecycleError("Objective Control modifiers require a context.")
        from warhammer40k_core.engine.generic_rule_attack_hooks import (
            generic_rule_modified_objective_control,
        )

        current = context.current_objective_control
        for binding in self.objective_control_modifier_bindings:
            current = _validate_non_negative_int(
                f"{binding.modifier_id} returned Objective Control",
                binding.handler(replace(context, current_objective_control=current)),
            )
        return generic_rule_modified_objective_control(
            replace(context, current_objective_control=current)
        )

    def advance_roll_modifiers(
        self,
        context: AdvanceRollModifierContext,
    ) -> tuple[RollModifier, ...]:
        if type(context) is not AdvanceRollModifierContext:
            raise GameLifecycleError("Advance roll modifiers require a context.")
        current = context.current_roll_modifiers
        for binding in self.advance_roll_modifier_bindings:
            current = _validate_roll_modifier_tuple(
                f"{binding.modifier_id} returned advance roll modifiers",
                binding.handler(replace(context, current_roll_modifiers=current)),
            )
        return current

    def charge_roll_modifiers(
        self,
        context: ChargeRollModifierContext,
    ) -> tuple[RollModifier, ...]:
        if type(context) is not ChargeRollModifierContext:
            raise GameLifecycleError("Charge roll modifiers require a context.")
        from warhammer40k_core.engine.generic_rule_attack_hooks import (
            generic_rule_charge_roll_modifiers,
        )

        current = context.current_roll_modifiers
        for binding in self.charge_roll_modifier_bindings:
            current = _validate_roll_modifier_tuple(
                f"{binding.modifier_id} returned charge roll modifiers",
                binding.handler(replace(context, current_roll_modifiers=current)),
            )
        return generic_rule_charge_roll_modifiers(replace(context, current_roll_modifiers=current))

    def modified_weapon_profile(
        self,
        context: WeaponProfileModifierContext,
    ) -> WeaponProfile:
        if type(context) is not WeaponProfileModifierContext:
            raise GameLifecycleError("Weapon profile modifiers require a context.")
        from warhammer40k_core.engine.generic_rule_attack_hooks import (
            generic_rule_modified_weapon_profile,
        )

        current = context.weapon_profile
        for binding in self.weapon_profile_modifier_bindings:
            current = _validate_weapon_profile(
                f"{binding.modifier_id} returned weapon profile",
                binding.handler(replace(context, weapon_profile=current)),
            )
        return generic_rule_modified_weapon_profile(replace(context, weapon_profile=current))


def unified_attack_reroll_permission_contexts_for_unit(
    *,
    state: GameState,
    player_id: str,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str | None,
    target_unit_instance_id: str | None,
    source_phase: BattlePhase,
    attack_kind: str,
    roll_type: str,
    registry: RuntimeModifierRegistry,
) -> tuple[SourceBackedRerollPermissionContext, ...]:
    source_backed_contexts = source_backed_reroll_permission_contexts_for_unit(
        state=state,
        player_id=player_id,
        unit_instance_id=attacking_unit_instance_id,
        model_instance_id=attacker_model_instance_id,
        roll_type=roll_type,
        timing_window=roll_type,
        attack_kind=attack_kind,
        target_unit_instance_id=target_unit_instance_id,
    )
    if target_unit_instance_id is None or roll_type.startswith("attack_sequence.save."):
        return source_backed_contexts
    catalog_contexts = registry.attack_reroll_permission_contexts(
        AttackRerollPermissionContext(
            state=state,
            player_id=player_id,
            attacking_unit_instance_id=attacking_unit_instance_id,
            attacker_model_instance_id=attacker_model_instance_id,
            target_unit_instance_id=target_unit_instance_id,
            source_phase=source_phase,
            roll_type=roll_type,
            timing_window=roll_type,
        )
    )
    return (*source_backed_contexts, *catalog_contexts)


def _validate_bindings[T](
    field_name: str,
    value: object,
    binding_type: type[T],
) -> tuple[T, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    bindings: list[T] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not binding_type:
            raise GameLifecycleError(f"{field_name} must contain {binding_type.__name__}.")
        modifier_id = cast(
            UnitCharacteristicModifierBinding
            | HitRollModifierBinding
            | WoundRollModifierBinding
            | DamageRollModifierBinding
            | AllocatedAttackDamageModifierBinding
            | SaveOptionModifierBinding
            | MovementBudgetModifierBinding
            | ObjectiveControlModifierBinding
            | AdvanceRollModifierBinding
            | ChargeRollModifierBinding
            | WeaponProfileModifierBinding
            | AttackRerollPermissionBinding
            | FailedSaveDamageReplacementBinding,
            binding,
        ).modifier_id
        if modifier_id in seen:
            raise GameLifecycleError(f"{field_name} modifier IDs must be unique.")
        seen.add(modifier_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=_modifier_id_for_binding))


def _modifier_id_for_binding(binding: object) -> str:
    if type(binding) in {
        UnitCharacteristicModifierBinding,
        HitRollModifierBinding,
        WoundRollModifierBinding,
        SaveOptionModifierBinding,
        DamageRollModifierBinding,
        AllocatedAttackDamageModifierBinding,
        MovementBudgetModifierBinding,
        ObjectiveControlModifierBinding,
        AdvanceRollModifierBinding,
        ChargeRollModifierBinding,
        WeaponProfileModifierBinding,
        AttackRerollPermissionBinding,
        FailedSaveDamageReplacementBinding,
    }:
        return cast(
            UnitCharacteristicModifierBinding
            | HitRollModifierBinding
            | WoundRollModifierBinding
            | DamageRollModifierBinding
            | AllocatedAttackDamageModifierBinding
            | SaveOptionModifierBinding
            | MovementBudgetModifierBinding
            | ObjectiveControlModifierBinding
            | AdvanceRollModifierBinding
            | ChargeRollModifierBinding
            | WeaponProfileModifierBinding
            | AttackRerollPermissionBinding
            | FailedSaveDamageReplacementBinding,
            binding,
        ).modifier_id
    raise GameLifecycleError("Runtime modifier binding has an unsupported type.")


def _validate_modifier_binding(
    *,
    field_prefix: str,
    modifier_id: object,
    source_id: object,
    handler: object,
) -> None:
    _validate_identifier(f"{field_prefix} modifier_id", modifier_id)
    _validate_identifier(f"{field_prefix} source_id", source_id)
    if not callable(handler):
        raise GameLifecycleError(f"{field_prefix} handler must be callable.")


def _validate_save_option_tuple(field_name: str, value: object) -> tuple[SaveOption, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    options: list[SaveOption] = []
    for option in cast(tuple[object, ...], value):
        if type(option) is not SaveOption:
            raise GameLifecycleError(f"{field_name} must contain SaveOption values.")
        options.append(option)
    return tuple(options)


def _validate_roll_modifier_tuple(field_name: str, value: object) -> tuple[RollModifier, ...]:
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


def _validate_weapon_profile(field_name: str, value: object) -> WeaponProfile:
    if type(value) is not WeaponProfile:
        raise GameLifecycleError(f"{field_name} must be a WeaponProfile.")
    return value


def _characteristic_from_token(token: object) -> Characteristic:
    if type(token) is Characteristic:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Runtime modifier characteristic must be a Characteristic.")
    try:
        return Characteristic(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported runtime modifier characteristic: {token}.") from exc


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Runtime modifier BattlePhase must be a BattlePhase.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported runtime modifier BattlePhase: {token}.") from exc


def _validate_non_negative_float(field_name: str, value: object) -> float:
    if type(value) not in {int, float}:
        raise GameLifecycleError(f"{field_name} must be numeric.")
    numeric = float(cast(int | float, value))
    if numeric < 0.0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return numeric


def _validate_non_negative_int(field_name: str, value: object) -> int:
    integer = _validate_int(field_name, value)
    if integer < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return integer


def _validate_positive_int(field_name: str, value: object) -> int:
    integer = _validate_int(field_name, value)
    if integer <= 0:
        raise GameLifecycleError(f"{field_name} must be positive.")
    return integer


def _validate_d6_target(field_name: str, value: object) -> int:
    integer = _validate_int(field_name, value)
    if not 2 <= integer <= 6:
        raise GameLifecycleError(f"{field_name} must be between 2 and 6.")
    return integer


def _validate_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_identifier_tuple(
    field_name: str,
    value: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(field_name, item) for item in cast(tuple[object, ...], value)
    )
    if len(identifiers) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    if sort_values:
        return tuple(sorted(identifiers))
    return identifiers


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)
