from __future__ import annotations

from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_target_resolution import (
    canonical_keyword,
    unit_has_required_keywords,
)
from warhammer40k_core.engine.rules_unit_geometry import geometry_models_for_rules_unit
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
)
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleParameterValue,
    RuleTargetKind,
    parameter_payload,
)

AURA_ALLEGIANCE_ANY = "any"
AURA_ALLEGIANCE_ENEMY = "enemy"
AURA_ALLEGIANCE_FRIENDLY = "friendly"
AURA_ANCHOR_MODEL = "model"
AURA_ANCHOR_UNIT = "unit"


def aura_affected_unit_ids(
    *,
    clause: RuleClause,
    state: GameState,
    source_unit_instance_id: str,
    source_model_instance_id: str | None,
) -> tuple[str, ...]:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Aura evaluation requires RuleClause.")
    if type(state) is not GameState:
        raise GameLifecycleError("Aura evaluation requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Aura evaluation requires battlefield_state.")
    source_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=source_unit_instance_id,
    )
    distance_parameters = _aura_distance_parameters(clause)
    source_geometries = _aura_source_geometries(
        state=state,
        source_rules_unit=source_rules_unit,
        source_model_instance_id=source_model_instance_id,
        anchor_kind=_aura_anchor_kind(distance_parameters),
    )
    if not source_geometries:
        return ()
    distance_inches = _aura_distance_inches(distance_parameters)
    allegiance = _aura_allegiance(clause)
    required_keywords = _required_keywords(clause.conditions)
    excluded_keywords = _excluded_keywords(clause.conditions)
    include_source_unit = _aura_includes_source_unit(clause)
    affected: list[str] = []
    for target_rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        if (
            target_rules_unit.unit_instance_id == source_rules_unit.unit_instance_id
            and not include_source_unit
        ):
            continue
        if (
            allegiance == AURA_ALLEGIANCE_FRIENDLY
            and target_rules_unit.owner_player_id != source_rules_unit.owner_player_id
        ):
            continue
        if (
            allegiance == AURA_ALLEGIANCE_ENEMY
            and target_rules_unit.owner_player_id == source_rules_unit.owner_player_id
        ):
            continue
        if required_keywords and not unit_has_required_keywords(
            unit_keywords=target_rules_unit.keywords,
            faction_keywords=target_rules_unit.faction_keywords,
            required_keywords=required_keywords,
        ):
            continue
        if _rules_unit_has_excluded_keyword(
            rules_unit=target_rules_unit,
            excluded_keywords=excluded_keywords,
        ):
            continue
        target_geometries = _placed_alive_rules_unit_geometries(
            state=state,
            rules_unit=target_rules_unit,
        )
        if target_geometries and _unit_within_aura(
            source_geometries=source_geometries,
            target_geometries=target_geometries,
            distance_inches=distance_inches,
        ):
            affected.append(target_rules_unit.unit_instance_id)
    return tuple(sorted(affected))


def _aura_source_geometries(
    *,
    state: GameState,
    source_rules_unit: RulesUnitView,
    source_model_instance_id: str | None,
    anchor_kind: str,
) -> tuple[GeometryModel, ...]:
    source_geometries = _placed_alive_rules_unit_geometries(
        state=state,
        rules_unit=source_rules_unit,
    )
    if anchor_kind == AURA_ANCHOR_UNIT:
        return source_geometries
    if anchor_kind != AURA_ANCHOR_MODEL:
        raise GameLifecycleError("Aura anchor kind is unsupported.")
    if source_model_instance_id is None:
        raise GameLifecycleError("Aura this_model anchor requires source_model_instance_id.")
    if source_model_instance_id not in {
        model.model_instance_id for model in source_rules_unit.alive_models()
    }:
        raise GameLifecycleError("Aura source model must be alive in the source rules unit.")
    matching_geometries = tuple(
        geometry for geometry in source_geometries if geometry.model_id == source_model_instance_id
    )
    if len(matching_geometries) != 1:
        raise GameLifecycleError("Aura source model must have exactly one battlefield placement.")
    return matching_geometries


def _placed_alive_rules_unit_geometries(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[GeometryModel, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Aura evaluation requires battlefield_state.")
    alive_model_ids = {model.model_instance_id for model in rules_unit.alive_models()}
    if not alive_model_ids.intersection(battlefield.placed_model_ids()):
        return ()
    return tuple(
        geometry
        for geometry in geometry_models_for_rules_unit(
            state=state,
            unit_instance_id=rules_unit.unit_instance_id,
        )
        if geometry.model_id in alive_model_ids
    )


def _unit_within_aura(
    *,
    source_geometries: tuple[GeometryModel, ...],
    target_geometries: tuple[GeometryModel, ...],
    distance_inches: float,
) -> bool:
    return any(
        DistanceMeasurementContext.from_models(
            source_geometry, target_geometry
        ).closest_distance_inches()
        <= distance_inches
        for source_geometry in source_geometries
        for target_geometry in target_geometries
    )


def _aura_distance_parameters(clause: RuleClause) -> dict[str, RuleParameterValue]:
    distance_conditions = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )
    if len(distance_conditions) != 1:
        raise GameLifecycleError("Aura clause requires exactly one distance predicate.")
    return parameter_payload(distance_conditions[0].parameters)


def _aura_distance_inches(parameters: dict[str, RuleParameterValue]) -> float:
    distance = parameters.get("distance_inches")
    if isinstance(distance, int | float) and type(distance) is not bool:
        return float(distance)
    raise GameLifecycleError("Aura clause requires a structured distance predicate.")


def _aura_anchor_kind(parameters: dict[str, RuleParameterValue]) -> str:
    object_reference = parameters.get("object_reference")
    if type(object_reference) is not str or not object_reference.strip():
        raise GameLifecycleError("Aura distance predicate requires object_reference.")
    if object_reference == "this_model":
        return AURA_ANCHOR_MODEL
    if object_reference in {"this_unit", "unit"}:
        return AURA_ANCHOR_UNIT
    if object_reference == "this":
        object_kind = parameters.get("object_kind")
        if object_kind == "model":
            return AURA_ANCHOR_MODEL
        if object_kind == "unit":
            return AURA_ANCHOR_UNIT
        raise GameLifecycleError("Aura 'this' reference requires model or unit object_kind.")
    raise GameLifecycleError("Aura distance predicate object_reference is unsupported.")


def _aura_allegiance(clause: RuleClause) -> str:
    if clause.target is None or clause.target.kind is not RuleTargetKind.AURA_UNITS:
        raise GameLifecycleError("Aura clause requires an aura_units target.")
    allegiance = parameter_payload(clause.target.parameters).get("allegiance")
    if type(allegiance) is not str:
        raise GameLifecycleError("Aura target requires structured allegiance.")
    if allegiance not in {
        AURA_ALLEGIANCE_ANY,
        AURA_ALLEGIANCE_ENEMY,
        AURA_ALLEGIANCE_FRIENDLY,
    }:
        raise GameLifecycleError("Aura target allegiance is unsupported.")
    return allegiance


def _aura_includes_source_unit(clause: RuleClause) -> bool:
    if clause.target is None or clause.target.kind is not RuleTargetKind.AURA_UNITS:
        raise GameLifecycleError("Aura clause requires an aura_units target.")
    value = parameter_payload(clause.target.parameters).get("include_source_unit", False)
    if type(value) is not bool:
        raise GameLifecycleError("Aura include_source_unit must be a boolean.")
    return value


def _required_keywords(conditions: tuple[RuleCondition, ...]) -> tuple[str, ...]:
    return _condition_keywords(
        conditions,
        parameter_keys=(
            "required_keyword",
            "required_keyword_sequence",
            "required_faction_keyword_sequence",
        ),
    )


def _excluded_keywords(conditions: tuple[RuleCondition, ...]) -> tuple[str, ...]:
    return _condition_keywords(
        conditions,
        parameter_keys=(
            "excluded_keyword",
            "excluded_keyword_sequence",
            "excluded_keywords",
            "excluded_keyword_any",
        ),
    )


def _condition_keywords(
    conditions: tuple[RuleCondition, ...],
    *,
    parameter_keys: tuple[str, ...],
) -> tuple[str, ...]:
    keywords: set[str] = set()
    for condition in conditions:
        if condition.kind is not RuleConditionKind.KEYWORD_GATE:
            continue
        parameters = parameter_payload(condition.parameters)
        for key in parameter_keys:
            value = parameters.get(key)
            if value is None:
                continue
            if type(value) is str:
                keywords.add(value)
                continue
            if not isinstance(value, tuple) or not value:
                raise GameLifecycleError(f"Aura keyword gate {key} must be a keyword sequence.")
            if any(type(keyword) is not str or not keyword.strip() for keyword in value):
                raise GameLifecycleError(f"Aura keyword gate {key} contains an invalid keyword.")
            keywords.update(value)
    return tuple(sorted(keywords))


def _rules_unit_has_excluded_keyword(
    *,
    rules_unit: RulesUnitView,
    excluded_keywords: tuple[str, ...],
) -> bool:
    if not excluded_keywords:
        return False
    unit_keywords = {
        canonical_keyword(keyword)
        for keyword in (*rules_unit.keywords, *rules_unit.faction_keywords)
    }
    return bool(
        unit_keywords.intersection(canonical_keyword(keyword) for keyword in excluded_keywords)
    )
