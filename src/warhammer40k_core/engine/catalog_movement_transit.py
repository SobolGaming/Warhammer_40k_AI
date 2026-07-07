from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import AbilityCatalogRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)


@dataclass(frozen=True, slots=True)
class CatalogMovementTransitPermission:
    record_id: str
    ability_id: str
    source_rule_id: str
    clause_id: str
    movement_modes: tuple[str, ...]
    model_keyword_any: tuple[str, ...] = ()
    terrain_height_max_inches: float | None = None
    permission: str = "move_over_as_if_not_there"
    model_allegiance: str = "friendly"
    excluded_model_keyword_any: tuple[str, ...] = ()
    terrain_features: bool = False
    enemy_engagement_range_transit: bool = False
    enemy_engagement_range_end_allowed: bool = False
    desperate_escape_tests_auto_passed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _validate_identifier("record_id", self.record_id))
        object.__setattr__(self, "ability_id", _validate_identifier("ability_id", self.ability_id))
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("source_rule_id", self.source_rule_id),
        )
        object.__setattr__(self, "clause_id", _validate_identifier("clause_id", self.clause_id))
        object.__setattr__(
            self,
            "movement_modes",
            _validate_movement_mode_tokens(self.movement_modes),
        )
        object.__setattr__(self, "permission", _validate_identifier("permission", self.permission))
        object.__setattr__(
            self,
            "model_allegiance",
            _validate_identifier("model_allegiance", self.model_allegiance),
        )
        object.__setattr__(
            self,
            "model_keyword_any",
            _validate_keyword_tokens("model_keyword_any", self.model_keyword_any),
        )
        object.__setattr__(
            self,
            "excluded_model_keyword_any",
            _validate_keyword_tokens(
                "excluded_model_keyword_any",
                self.excluded_model_keyword_any,
            ),
        )
        object.__setattr__(
            self,
            "terrain_height_max_inches",
            _validate_optional_non_negative_float(
                "terrain_height_max_inches",
                self.terrain_height_max_inches,
            ),
        )
        for field_name, value in (
            ("terrain_features", self.terrain_features),
            ("enemy_engagement_range_transit", self.enemy_engagement_range_transit),
            ("enemy_engagement_range_end_allowed", self.enemy_engagement_range_end_allowed),
            ("desperate_escape_tests_auto_passed", self.desperate_escape_tests_auto_passed),
        ):
            _validate_bool(f"Catalog movement transit {field_name}", value)

    def applies_to_movement_mode(self, movement_mode: str) -> bool:
        return _movement_mode_token(movement_mode) in set(self.movement_modes)


@dataclass(frozen=True, slots=True)
class _SupportedMovementTransitEffectParameters:
    movement_modes: tuple[str, ...]
    permission: str
    model_allegiance: str
    model_keyword_any: tuple[str, ...] = ()
    excluded_model_keyword_any: tuple[str, ...] = ()
    terrain_height_max_inches: float | None = None
    terrain_features: bool = False
    enemy_engagement_range_transit: bool = False
    enemy_engagement_range_end_allowed: bool = False
    desperate_escape_tests_auto_passed: bool = False


def clause_is_supported_movement_transit_permission(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Movement transit permission classification requires RuleClause.")
    if not clause.is_supported:
        return False
    if clause.target is None:
        return False
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    trigger_parameters = parameter_payload(trigger.parameters)
    target_kind = clause.target.kind
    if not _movement_transit_trigger_matches_target(
        target_kind=target_kind,
        trigger_parameters=trigger_parameters,
    ):
        return False
    effects = tuple(
        effect
        for effect in clause.effects
        if effect.kind is RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION
    )
    if len(effects) != len(clause.effects) or not effects:
        return False
    movement_modes_value = trigger_parameters.get("movement_modes")
    if movement_modes_value is None:
        return False
    if type(movement_modes_value) is not tuple:
        raise GameLifecycleError("Catalog movement trigger movement_modes must be a tuple.")
    movement_modes = movement_mode_tokens_or_none(movement_modes_value)
    if movement_modes is None:
        return False
    supported_effects = tuple(
        _supported_movement_transit_effect_parameters(effect) for effect in effects
    )
    if any(supported_effect is None for supported_effect in supported_effects):
        return False
    supported = cast(
        tuple[_SupportedMovementTransitEffectParameters, ...],
        supported_effects,
    )
    if any(movement_modes != supported_effect.movement_modes for supported_effect in supported):
        return False
    permissions = {supported_effect.permission for supported_effect in supported}
    if target_kind is RuleTargetKind.THIS_MODEL:
        return permissions == {"move_over_as_if_not_there"} and len(supported) == 1
    if target_kind is RuleTargetKind.THIS_UNIT:
        return permissions == {"move_through_models", "move_through_terrain_features"}
    return False


def movement_transit_permissions_from_clause(
    *,
    record: AbilityCatalogRecord,
    clause: RuleClause,
) -> tuple[CatalogMovementTransitPermission, ...]:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Movement transit permission requires an ability record.")
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Movement transit permission requires a RuleClause.")
    if not clause_is_supported_movement_transit_permission(clause):
        return ()
    effects = tuple(
        effect
        for effect in clause.effects
        if effect.kind is RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION
    )
    permissions = tuple(
        permission
        for effect in effects
        if (
            permission := _movement_transit_permission_from_effect(
                record=record,
                clause=clause,
                effect=effect,
            )
        )
        is not None
    )
    if len(permissions) != len(effects):
        raise GameLifecycleError("Supported movement transit clause must produce permissions.")
    return tuple(
        sorted(
            permissions,
            key=lambda permission: (
                permission.permission,
                permission.model_allegiance,
                permission.record_id,
            ),
        )
    )


def movement_mode_token(value: object) -> str:
    return _movement_mode_token(value)


def movement_mode_tokens_or_none(values: object) -> tuple[str, ...] | None:
    if type(values) is not tuple:
        return None
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        token = _movement_mode_token_or_none(value)
        if token is None or token in seen:
            return None
        seen.add(token)
        validated.append(token)
    if not validated:
        return None
    return tuple(sorted(validated))


def _movement_transit_trigger_matches_target(
    *,
    target_kind: RuleTargetKind,
    trigger_parameters: Mapping[str, object],
) -> bool:
    if trigger_parameters.get("phase") != "movement" or trigger_parameters.get("edge") != "during":
        return False
    if target_kind is RuleTargetKind.THIS_MODEL:
        return (
            trigger_parameters.get("timing_window") == "model_makes_move"
            and trigger_parameters.get("subject") == "this_model"
        )
    if target_kind is RuleTargetKind.THIS_UNIT:
        return (
            trigger_parameters.get("timing_window") == "unit_makes_move"
            and trigger_parameters.get("subject") == "this_unit"
        )
    return False


def _movement_transit_permission_from_effect(
    *,
    record: AbilityCatalogRecord,
    clause: RuleClause,
    effect: RuleEffectSpec,
) -> CatalogMovementTransitPermission | None:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError("Movement transit permission requires an ability record.")
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Movement transit permission requires a RuleClause.")
    supported = _supported_movement_transit_effect_parameters(effect)
    if supported is None:
        return None
    return CatalogMovementTransitPermission(
        record_id=record.record_id,
        ability_id=record.definition.ability_id,
        source_rule_id=record.definition.source_id,
        clause_id=clause.clause_id,
        movement_modes=supported.movement_modes,
        model_keyword_any=supported.model_keyword_any,
        terrain_height_max_inches=supported.terrain_height_max_inches,
        permission=supported.permission,
        model_allegiance=supported.model_allegiance,
        excluded_model_keyword_any=supported.excluded_model_keyword_any,
        terrain_features=supported.terrain_features,
        enemy_engagement_range_transit=supported.enemy_engagement_range_transit,
        enemy_engagement_range_end_allowed=supported.enemy_engagement_range_end_allowed,
        desperate_escape_tests_auto_passed=supported.desperate_escape_tests_auto_passed,
    )


def _supported_movement_transit_effect_parameters(
    effect: RuleEffectSpec,
) -> _SupportedMovementTransitEffectParameters | None:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Movement transit permission requires RuleEffectSpec.")
    if effect.kind is not RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION:
        return None
    parameters = parameter_payload(effect.parameters)
    permission = parameters.get("permission")
    if permission == "move_over_as_if_not_there":
        return _supported_move_over_as_if_absent_parameters(parameters)
    if permission == "move_through_models":
        return _supported_move_through_models_parameters(parameters)
    if permission == "move_through_terrain_features":
        return _supported_move_through_terrain_parameters(parameters)
    return None


def _supported_move_over_as_if_absent_parameters(
    parameters: Mapping[str, object],
) -> _SupportedMovementTransitEffectParameters | None:
    if (
        parameters.get("model_allegiance") != "friendly"
        or parameters.get("terrain_scope") != "terrain_features"
    ):
        return None
    movement_modes_value = parameters.get("movement_modes")
    model_keyword_any_value = parameters.get("model_keyword_any")
    if movement_modes_value is None or model_keyword_any_value is None:
        return None
    if type(movement_modes_value) is not tuple or type(model_keyword_any_value) is not tuple:
        raise GameLifecycleError("Catalog movement transit parameters must be tuples.")
    movement_modes = _validate_movement_mode_tokens(cast(tuple[object, ...], movement_modes_value))
    model_keyword_any = _validate_keyword_tokens(
        "model_keyword_any",
        cast(tuple[object, ...], model_keyword_any_value),
    )
    if not set(movement_modes).issubset({"advance", "normal"}):
        return None
    if set(model_keyword_any) != {"MONSTER", "VEHICLE"}:
        return None
    terrain_height_max_inches = _validate_non_negative_float(
        "terrain_height_max_inches",
        parameters.get("terrain_height_max_inches"),
    )
    return _SupportedMovementTransitEffectParameters(
        movement_modes=movement_modes,
        permission="move_over_as_if_not_there",
        model_allegiance="friendly",
        model_keyword_any=model_keyword_any,
        terrain_height_max_inches=terrain_height_max_inches,
    )


def _supported_move_through_models_parameters(
    parameters: Mapping[str, object],
) -> _SupportedMovementTransitEffectParameters | None:
    movement_modes_value = parameters.get("movement_modes")
    if movement_modes_value is None:
        return None
    movement_modes = _validate_movement_mode_tokens(movement_modes_value)
    if not set(movement_modes).issubset({"advance", "fall_back", "normal"}):
        return None
    model_allegiance = parameters.get("model_allegiance")
    if type(model_allegiance) is not str or model_allegiance not in {
        "any",
        "enemy",
        "friendly",
    }:
        return None
    excluded_model_keywords_value = parameters.get("excluded_model_keyword_any", ())
    if type(excluded_model_keywords_value) is not tuple:
        raise GameLifecycleError("Catalog movement transit excluded keywords must be a tuple.")
    return _SupportedMovementTransitEffectParameters(
        movement_modes=movement_modes,
        permission="move_through_models",
        model_allegiance=model_allegiance,
        excluded_model_keyword_any=_validate_keyword_tokens(
            "excluded_model_keyword_any",
            cast(tuple[object, ...], excluded_model_keywords_value),
        ),
        enemy_engagement_range_transit=_movement_transit_optional_bool_parameter(
            parameters,
            "enemy_engagement_range_transit",
            default=False,
        ),
        enemy_engagement_range_end_allowed=_movement_transit_optional_bool_parameter(
            parameters,
            "enemy_engagement_range_end_allowed",
            default=False,
        ),
        desperate_escape_tests_auto_passed=_movement_transit_optional_bool_parameter(
            parameters,
            "desperate_escape_tests_auto_passed",
            default=False,
        ),
    )


def _supported_move_through_terrain_parameters(
    parameters: Mapping[str, object],
) -> _SupportedMovementTransitEffectParameters | None:
    movement_modes_value = parameters.get("movement_modes")
    if movement_modes_value is None:
        return None
    movement_modes = _validate_movement_mode_tokens(movement_modes_value)
    if not set(movement_modes).issubset({"advance", "fall_back", "normal"}):
        return None
    if parameters.get("terrain_features") is not True:
        return None
    return _SupportedMovementTransitEffectParameters(
        movement_modes=movement_modes,
        permission="move_through_terrain_features",
        model_allegiance="any",
        terrain_features=True,
    )


def _validate_keyword_tokens(field_name: str, values: object) -> tuple[str, ...]:
    if type(field_name) is not str or not field_name:
        raise GameLifecycleError("Catalog rule keyword validation requires a field name.")
    if type(values) is not tuple:
        raise GameLifecycleError(f"Catalog rule {field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not str or not value.strip():
            raise GameLifecycleError(f"Catalog rule {field_name} must contain keyword strings.")
        token = _catalog_keyword_token(value)
        if token in seen:
            raise GameLifecycleError(f"Catalog rule {field_name} must not duplicate keywords.")
        seen.add(token)
        validated.append(token)
    return tuple(validated)


def _validate_movement_mode_tokens(values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Catalog movement mode tokens must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        token = _movement_mode_token(value)
        if token in seen:
            raise GameLifecycleError("Catalog movement mode tokens must not duplicate values.")
        seen.add(token)
        validated.append(token)
    if not validated:
        raise GameLifecycleError("Catalog movement mode tokens must not be empty.")
    return tuple(sorted(validated))


def _movement_mode_token(value: object) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError("Catalog movement mode token must be a string.")
    token = value.strip().lower().replace(" ", "_").replace("-", "_")
    if token not in {"advance", "fall_back", "normal"}:
        raise GameLifecycleError("Catalog movement mode token is unsupported.")
    return token


def _movement_mode_token_or_none(value: object) -> str | None:
    if type(value) is not str or not value.strip():
        return None
    token = value.strip().lower().replace(" ", "_").replace("-", "_")
    if token not in {"advance", "fall_back", "normal"}:
        return None
    return token


def _movement_transit_optional_bool_parameter(
    parameters: Mapping[str, object],
    key: str,
    *,
    default: bool,
) -> bool:
    value = parameters.get(key, default)
    if type(value) is not bool:
        raise GameLifecycleError(f"Catalog movement transit {key} must be a bool.")
    return value


def _validate_optional_non_negative_float(field_name: str, value: object) -> float | None:
    if value is None:
        return None
    return _validate_non_negative_float(field_name, value)


def _validate_non_negative_float(field_name: str, value: object) -> float:
    if type(field_name) is not str or not field_name:
        raise GameLifecycleError("Float validation requires a field name.")
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(f"Catalog rule {field_name} must be numeric.")
    number = float(value)
    if not isfinite(number) or number < 0.0:
        raise GameLifecycleError(f"Catalog rule {field_name} must be finite and non-negative.")
    return number


def _validate_bool(field_name: str, value: object) -> None:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")


def _catalog_keyword_token(value: str) -> str:
    return value.strip().upper().replace(" ", "_").replace("-", "_")


_validate_identifier = IdentifierValidator(GameLifecycleError)
