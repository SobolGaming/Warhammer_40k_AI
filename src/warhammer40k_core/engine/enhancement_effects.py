from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    DatasheetAbilityDescriptor,
    DatasheetAbilityDescriptorPayload,
)
from warhammer40k_core.core.modifiers import ModifierOperation
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    EnhancementAssignment,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class EnhancementCharacteristicModifierPayload(TypedDict):
    effect_id: str
    source_id: str
    enhancement_id: str
    target_unit_instance_id: str
    characteristic: str
    operation: str
    operand: int
    modifier_id: str
    replay_payload: JsonValue


class EnhancementPersistingEffectGrantPayload(TypedDict):
    effect_id: str
    source_id: str
    enhancement_id: str
    target_unit_instance_id: str
    persisting_effect: JsonValue
    replay_payload: JsonValue


class EnhancementUnitKeywordGrantPayload(TypedDict):
    effect_id: str
    source_id: str
    enhancement_id: str
    target_unit_instance_id: str
    keyword: str
    replay_payload: JsonValue


class EnhancementDatasheetAbilityGrantPayload(TypedDict):
    effect_id: str
    source_id: str
    enhancement_id: str
    target_unit_instance_id: str
    datasheet_ability: DatasheetAbilityDescriptorPayload
    replay_payload: JsonValue


type EnhancementEffectHandler = Callable[
    ["EnhancementEffectContext"],
    tuple[object, ...],
]


@dataclass(frozen=True, slots=True)
class EnhancementEffectContext:
    state: GameState
    army: ArmyDefinition
    assignment: EnhancementAssignment
    target_unit: UnitInstance

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("EnhancementEffectContext state must be a GameState.")
        if type(self.army) is not ArmyDefinition:
            raise GameLifecycleError("EnhancementEffectContext army must be an ArmyDefinition.")
        if type(self.assignment) is not EnhancementAssignment:
            raise GameLifecycleError(
                "EnhancementEffectContext assignment must be an EnhancementAssignment."
            )
        if type(self.target_unit) is not UnitInstance:
            raise GameLifecycleError("EnhancementEffectContext target_unit must be a UnitInstance.")
        if self.target_unit not in self.army.units:
            raise GameLifecycleError("EnhancementEffectContext target unit is not in the army.")


@dataclass(frozen=True, slots=True)
class EnhancementCharacteristicModifier:
    effect_id: str
    source_id: str
    enhancement_id: str
    target_unit_instance_id: str
    characteristic: Characteristic
    operation: ModifierOperation
    operand: int
    modifier_id: str
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "effect_id", _validate_identifier("effect_id", self.effect_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "enhancement_id",
            _validate_identifier("enhancement_id", self.enhancement_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        if type(self.characteristic) is not Characteristic:
            raise GameLifecycleError(
                "EnhancementCharacteristicModifier characteristic must be a Characteristic."
            )
        if type(self.operation) is not ModifierOperation:
            raise GameLifecycleError(
                "EnhancementCharacteristicModifier operation must be a ModifierOperation."
            )
        if type(self.operand) is not int:
            raise GameLifecycleError("EnhancementCharacteristicModifier operand must be an int.")
        object.__setattr__(
            self,
            "modifier_id",
            _validate_identifier("modifier_id", self.modifier_id),
        )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))

    def to_payload(self) -> EnhancementCharacteristicModifierPayload:
        return {
            "effect_id": self.effect_id,
            "source_id": self.source_id,
            "enhancement_id": self.enhancement_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "characteristic": self.characteristic.value,
            "operation": self.operation.value,
            "operand": self.operand,
            "modifier_id": self.modifier_id,
            "replay_payload": self.replay_payload,
        }


@dataclass(frozen=True, slots=True)
class EnhancementPersistingEffectGrant:
    effect_id: str
    source_id: str
    enhancement_id: str
    target_unit_instance_id: str
    persisting_effect: PersistingEffect
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "effect_id", _validate_identifier("effect_id", self.effect_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "enhancement_id",
            _validate_identifier("enhancement_id", self.enhancement_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        if type(self.persisting_effect) is not PersistingEffect:
            raise GameLifecycleError(
                "EnhancementPersistingEffectGrant persisting_effect must be a PersistingEffect."
            )
        if self.persisting_effect.source_rule_id != self.source_id:
            raise GameLifecycleError("Enhancement persisting effect source drift.")
        if self.target_unit_instance_id not in self.persisting_effect.target_unit_instance_ids:
            raise GameLifecycleError("Enhancement persisting effect target drift.")
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))

    def to_payload(self) -> EnhancementPersistingEffectGrantPayload:
        return {
            "effect_id": self.effect_id,
            "source_id": self.source_id,
            "enhancement_id": self.enhancement_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "persisting_effect": validate_json_value(self.persisting_effect.to_payload()),
            "replay_payload": self.replay_payload,
        }


@dataclass(frozen=True, slots=True)
class EnhancementUnitKeywordGrant:
    effect_id: str
    source_id: str
    enhancement_id: str
    target_unit_instance_id: str
    keyword: str
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "effect_id", _validate_identifier("effect_id", self.effect_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "enhancement_id",
            _validate_identifier("enhancement_id", self.enhancement_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        object.__setattr__(self, "keyword", _validate_identifier("keyword", self.keyword))
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))

    def to_payload(self) -> EnhancementUnitKeywordGrantPayload:
        return {
            "effect_id": self.effect_id,
            "source_id": self.source_id,
            "enhancement_id": self.enhancement_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "keyword": self.keyword,
            "replay_payload": self.replay_payload,
        }


@dataclass(frozen=True, slots=True)
class EnhancementDatasheetAbilityGrant:
    effect_id: str
    source_id: str
    enhancement_id: str
    target_unit_instance_id: str
    datasheet_ability: DatasheetAbilityDescriptor
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "effect_id", _validate_identifier("effect_id", self.effect_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "enhancement_id",
            _validate_identifier("enhancement_id", self.enhancement_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        if type(self.datasheet_ability) is not DatasheetAbilityDescriptor:
            raise GameLifecycleError(
                "EnhancementDatasheetAbilityGrant datasheet_ability must be a descriptor."
            )
        if self.datasheet_ability.source_id != self.source_id:
            raise GameLifecycleError("Enhancement datasheet ability source drift.")
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))

    def to_payload(self) -> EnhancementDatasheetAbilityGrantPayload:
        return {
            "effect_id": self.effect_id,
            "source_id": self.source_id,
            "enhancement_id": self.enhancement_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "datasheet_ability": self.datasheet_ability.to_payload(),
            "replay_payload": self.replay_payload,
        }


@dataclass(frozen=True, slots=True)
class EnhancementEffectBinding:
    effect_id: str
    source_id: str
    enhancement_id: str
    handler: EnhancementEffectHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "effect_id", _validate_identifier("effect_id", self.effect_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "enhancement_id",
            _validate_identifier("enhancement_id", self.enhancement_id),
        )
        if not callable(self.handler):
            raise GameLifecycleError("EnhancementEffectBinding handler must be callable.")


def _enhancement_effect_sort_key(
    effect: EnhancementCharacteristicModifier
    | EnhancementPersistingEffectGrant
    | EnhancementUnitKeywordGrant
    | EnhancementDatasheetAbilityGrant,
) -> str:
    return effect.effect_id


@dataclass(frozen=True, slots=True)
class EnhancementEffectRegistry:
    bindings: tuple[EnhancementEffectBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_effect_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[EnhancementEffectBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[EnhancementEffectBinding, ...]:
        return self.bindings

    def effects_for(
        self,
        context: EnhancementEffectContext,
    ) -> tuple[object, ...]:
        if type(context) is not EnhancementEffectContext:
            raise GameLifecycleError("Enhancement effects require a context.")
        effects: list[
            EnhancementCharacteristicModifier
            | EnhancementPersistingEffectGrant
            | EnhancementUnitKeywordGrant
            | EnhancementDatasheetAbilityGrant
        ] = []
        allowed_target_unit_ids = _effect_target_unit_instance_ids(context)
        for binding in self.bindings:
            if binding.enhancement_id != context.assignment.enhancement_id:
                continue
            binding_effects = binding.handler(context)
            if type(binding_effects) is not tuple:
                raise GameLifecycleError("Enhancement effect handlers must return a tuple.")
            for effect in binding_effects:
                if type(effect) is EnhancementCharacteristicModifier:
                    supported_effect: (
                        EnhancementCharacteristicModifier
                        | EnhancementPersistingEffectGrant
                        | EnhancementUnitKeywordGrant
                        | EnhancementDatasheetAbilityGrant
                    ) = effect
                elif type(effect) in (
                    EnhancementPersistingEffectGrant,
                    EnhancementUnitKeywordGrant,
                    EnhancementDatasheetAbilityGrant,
                ):
                    supported_effect = cast(
                        EnhancementPersistingEffectGrant
                        | EnhancementUnitKeywordGrant
                        | EnhancementDatasheetAbilityGrant,
                        effect,
                    )
                else:
                    raise GameLifecycleError(
                        "Enhancement effect handlers must return supported enhancement effects."
                    )
                if supported_effect.effect_id != binding.effect_id:
                    raise GameLifecycleError("Enhancement effect handler returned effect_id drift.")
                if supported_effect.source_id != binding.source_id:
                    raise GameLifecycleError("Enhancement effect handler returned source_id drift.")
                if supported_effect.enhancement_id != binding.enhancement_id:
                    raise GameLifecycleError(
                        "Enhancement effect handler returned enhancement_id drift."
                    )
                if supported_effect.target_unit_instance_id not in allowed_target_unit_ids:
                    raise GameLifecycleError(
                        "Enhancement effect handler returned target unit drift."
                    )
                effects.append(supported_effect)
        return tuple(sorted(effects, key=_enhancement_effect_sort_key))


def apply_enhancement_effects(
    *,
    state: GameState,
    registry: EnhancementEffectRegistry,
    decisions: DecisionController,
) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Enhancement effect application requires GameState.")
    if type(registry) is not EnhancementEffectRegistry:
        raise GameLifecycleError("Enhancement effect application requires a registry.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Enhancement effect application requires DecisionController.")
    if not registry.bindings:
        return

    updated_armies: list[ArmyDefinition] = []
    event_payloads: list[dict[str, JsonValue]] = []
    for army in state.army_definitions:
        updated_army = army
        for assignment in army.enhancement_assignments:
            target_unit = _unit_for_assignment(updated_army, assignment=assignment)
            context = EnhancementEffectContext(
                state=state,
                army=updated_army,
                assignment=assignment,
                target_unit=target_unit,
            )
            for effect in registry.effects_for(context):
                if type(effect) is EnhancementCharacteristicModifier:
                    updated_army, payload = _apply_characteristic_modifier(
                        army=updated_army,
                        effect=effect,
                    )
                    if payload is not None:
                        event_payloads.append(payload)
                    continue
                if type(effect) is EnhancementPersistingEffectGrant:
                    if not any(
                        stored.effect_id == effect.persisting_effect.effect_id
                        for stored in state.persisting_effects
                    ):
                        state.record_persisting_effect(effect.persisting_effect)
                        event_payloads.append(cast(dict[str, JsonValue], effect.to_payload()))
                    continue
                if type(effect) is EnhancementUnitKeywordGrant:
                    updated_army, payload = _apply_unit_keyword_grant(
                        army=updated_army,
                        effect=effect,
                    )
                    if payload is not None:
                        event_payloads.append(payload)
                    continue
                if type(effect) is EnhancementDatasheetAbilityGrant:
                    updated_army, payload = _apply_datasheet_ability_grant(
                        army=updated_army,
                        effect=effect,
                    )
                    if payload is not None:
                        event_payloads.append(payload)
                    continue
                raise GameLifecycleError("Enhancement effect application received unknown effect.")
        updated_armies.append(updated_army)

    if not event_payloads:
        return
    state.army_definitions = sorted(updated_armies, key=lambda stored: stored.player_id)
    decisions.event_log.append(
        "enhancement_effects_applied",
        {
            "game_id": state.game_id,
            "effects": event_payloads,
        },
    )


def _apply_characteristic_modifier(
    *,
    army: ArmyDefinition,
    effect: EnhancementCharacteristicModifier,
) -> tuple[ArmyDefinition, dict[str, JsonValue] | None]:
    model_payloads: list[JsonValue] = []
    updated_units: list[UnitInstance] = []
    target_seen = False
    for unit in army.units:
        if unit.unit_instance_id != effect.target_unit_instance_id:
            updated_units.append(unit)
            continue
        target_seen = True
        updated_models: list[ModelInstance] = []
        for model in unit.own_models:
            updated_model, payload = _apply_model_characteristic_modifier(
                model=model,
                effect=effect,
            )
            updated_models.append(updated_model)
            if payload is not None:
                model_payloads.append(payload)
        updated_units.append(replace(unit, own_models=tuple(updated_models)))
    if not target_seen:
        raise GameLifecycleError("Enhancement effect target unit is not in the army.")
    if not model_payloads:
        return army, None
    updated_army = replace(
        army,
        units=tuple(sorted(updated_units, key=lambda stored: stored.unit_instance_id)),
    )
    return updated_army, {
        **cast(dict[str, JsonValue], effect.to_payload()),
        "player_id": army.player_id,
        "army_id": army.army_id,
        "model_modifiers": model_payloads,
    }


def _apply_unit_keyword_grant(
    *,
    army: ArmyDefinition,
    effect: EnhancementUnitKeywordGrant,
) -> tuple[ArmyDefinition, dict[str, JsonValue] | None]:
    updated_units: list[UnitInstance] = []
    target_seen = False
    payload: dict[str, JsonValue] | None = None
    requested_keyword = _canonical_keyword(effect.keyword)
    for unit in army.units:
        if unit.unit_instance_id != effect.target_unit_instance_id:
            updated_units.append(unit)
            continue
        target_seen = True
        existing = {_canonical_keyword(keyword) for keyword in unit.keywords}
        if requested_keyword in existing:
            updated_units.append(unit)
            continue
        updated_keywords = tuple(sorted((*unit.keywords, effect.keyword)))
        updated_units.append(replace(unit, keywords=updated_keywords))
        payload = {
            **cast(dict[str, JsonValue], effect.to_payload()),
            "player_id": army.player_id,
            "army_id": army.army_id,
            "before_keywords": list(unit.keywords),
            "after_keywords": list(updated_keywords),
        }
    if not target_seen:
        raise GameLifecycleError("Enhancement keyword grant target unit is not in the army.")
    if payload is None:
        return army, None
    updated_army = replace(
        army,
        units=tuple(sorted(updated_units, key=lambda stored: stored.unit_instance_id)),
    )
    return updated_army, payload


def _apply_datasheet_ability_grant(
    *,
    army: ArmyDefinition,
    effect: EnhancementDatasheetAbilityGrant,
) -> tuple[ArmyDefinition, dict[str, JsonValue] | None]:
    updated_units: list[UnitInstance] = []
    target_seen = False
    payload: dict[str, JsonValue] | None = None
    for unit in army.units:
        if unit.unit_instance_id != effect.target_unit_instance_id:
            updated_units.append(unit)
            continue
        target_seen = True
        if any(
            ability.ability_id == effect.datasheet_ability.ability_id
            for ability in unit.datasheet_abilities
        ):
            updated_units.append(unit)
            continue
        updated_abilities = tuple(
            sorted(
                (*unit.datasheet_abilities, effect.datasheet_ability),
                key=lambda ability: ability.ability_id,
            )
        )
        updated_units.append(replace(unit, datasheet_abilities=updated_abilities))
        payload = {
            **cast(dict[str, JsonValue], effect.to_payload()),
            "player_id": army.player_id,
            "army_id": army.army_id,
            "before_datasheet_ability_ids": [
                ability.ability_id for ability in unit.datasheet_abilities
            ],
            "after_datasheet_ability_ids": [ability.ability_id for ability in updated_abilities],
        }
    if not target_seen:
        raise GameLifecycleError("Enhancement datasheet ability target unit is not in the army.")
    if payload is None:
        return army, None
    updated_army = replace(
        army,
        units=tuple(sorted(updated_units, key=lambda stored: stored.unit_instance_id)),
    )
    return updated_army, payload


def _apply_model_characteristic_modifier(
    *,
    model: ModelInstance,
    effect: EnhancementCharacteristicModifier,
) -> tuple[ModelInstance, dict[str, JsonValue] | None]:
    updated_characteristics: list[CharacteristicValue] = []
    characteristic_seen = False
    payload: dict[str, JsonValue] | None = None
    for value in model.characteristics:
        if value.characteristic is not effect.characteristic:
            updated_characteristics.append(value)
            continue
        characteristic_seen = True
        updated_value = _modified_characteristic_value(value, effect=effect)
        updated_characteristics.append(updated_value)
        if updated_value != value:
            payload = {
                "model_instance_id": model.model_instance_id,
                "before_final": value.final,
                "after_final": updated_value.final,
                "modifier_id": effect.modifier_id,
            }
    if not characteristic_seen:
        raise GameLifecycleError("Enhancement effect target model is missing characteristic.")
    if payload is None:
        return model, None
    return replace(model, characteristics=tuple(updated_characteristics)), payload


def _modified_characteristic_value(
    value: CharacteristicValue,
    *,
    effect: EnhancementCharacteristicModifier,
) -> CharacteristicValue:
    if type(value) is not CharacteristicValue:
        raise GameLifecycleError("Enhancement effect requires CharacteristicValue.")
    if effect.modifier_id in value.applied_modifier_ids:
        return value
    if not value.is_numeric:
        raise GameLifecycleError("Enhancement effect cannot modify dash characteristics.")
    if effect.operation is not ModifierOperation.ADD:
        raise GameLifecycleError("Enhancement effect operation is unsupported.")
    return CharacteristicValue(
        characteristic=value.characteristic,
        raw=value.raw,
        base=value.base,
        final=value.final + effect.operand,
        applied_modifier_ids=(*value.applied_modifier_ids, effect.modifier_id),
        value_kind=value.value_kind,
    )


def _unit_for_assignment(
    army: ArmyDefinition,
    *,
    assignment: EnhancementAssignment,
) -> UnitInstance:
    expected_unit_instance_id = f"{army.army_id}:{assignment.target_unit_selection_id}"
    for unit in army.units:
        if unit.unit_instance_id == expected_unit_instance_id:
            return unit
    raise GameLifecycleError("EnhancementAssignment target unit was not mustered.")


def _effect_target_unit_instance_ids(context: EnhancementEffectContext) -> frozenset[str]:
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    view = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.target_unit.unit_instance_id,
    )
    return frozenset(component.unit.unit_instance_id for component in view.components)


def _validate_effect_bindings(value: object) -> tuple[EnhancementEffectBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("EnhancementEffectRegistry bindings must be a tuple.")
    bindings: list[EnhancementEffectBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not EnhancementEffectBinding:
            raise GameLifecycleError(
                "EnhancementEffectRegistry bindings must contain EnhancementEffectBinding values."
            )
        if binding.effect_id in seen:
            raise GameLifecycleError("EnhancementEffectRegistry effect IDs must be unique.")
        seen.add(binding.effect_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.effect_id))


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Enhancement effect {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Enhancement effect {field_name} must not be empty.")
    return stripped


def _canonical_keyword(value: str) -> str:
    return value.strip().replace("_", " ").replace("-", " ").upper()
