from __future__ import annotations

from typing import Protocol

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.selected_target_context import selected_target_unit_ids_or_none
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleTargetKind,
    RuleTargetSpec,
    parameter_payload,
)

UNIT_EFFECT_TARGET_KINDS = (
    RuleTargetKind.ENEMY_UNIT,
    RuleTargetKind.FRIENDLY_UNIT,
    RuleTargetKind.SELECTED_TARGET,
    RuleTargetKind.SELECTED_UNIT,
    RuleTargetKind.THIS_MODEL,
    RuleTargetKind.THIS_UNIT,
)
TARGET_SCOPED_EFFECT_KINDS = (
    RuleEffectKind.FORCE_DESPERATE_ESCAPE_TESTS,
    RuleEffectKind.GRANT_ABILITY,
    RuleEffectKind.GRANT_WEAPON_ABILITY,
    RuleEffectKind.INFLICT_MORTAL_WOUNDS,
    RuleEffectKind.MODIFY_CHARACTERISTIC,
    RuleEffectKind.MODIFY_DICE_ROLL,
    RuleEffectKind.MODIFY_MOVE_DISTANCE,
    RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
    RuleEffectKind.PLACEMENT_PERMISSION,
    RuleEffectKind.PLACEMENT_RESTRICTION,
    RuleEffectKind.REROLL_PERMISSION,
    RuleEffectKind.RESTORE_LOST_WOUNDS,
    RuleEffectKind.SET_CONTEXTUAL_STATUS,
    RuleEffectKind.SET_CHARACTERISTIC,
)

_validate_identifier = IdentifierValidator(GameLifecycleError)


class RuleTargetExecutionContext(Protocol):
    @property
    def state(self) -> GameState | None: ...

    @property
    def source_unit_instance_id(self) -> str | None: ...

    @property
    def target_unit_instance_ids(self) -> tuple[str, ...]: ...

    @property
    def trigger_payload(self) -> JsonValue: ...


def effect_clause_target_unavailable_reason(
    *,
    clause: RuleClause,
    context: RuleTargetExecutionContext,
) -> str | None:
    if not clause_requires_unit_target(clause):
        return None
    selected_target_reason = selected_target_clause_unavailable_reason(
        clause=clause,
        context=context,
    )
    if selected_target_reason is not None:
        return selected_target_reason
    target_unit_instance_ids = target_unit_instance_ids_for_clause(
        clause=clause,
        context=context,
        target_unit_instance_ids=None,
    )
    if target_unit_instance_ids:
        target_keyword_reason = target_spec_keyword_unavailable_reason(
            clause=clause,
            context=context,
            target_unit_instance_ids=target_unit_instance_ids,
        )
        if target_keyword_reason is not None:
            return target_keyword_reason
        return None
    if clause.target is not None and clause.target.kind in {
        RuleTargetKind.THIS_MODEL,
        RuleTargetKind.THIS_UNIT,
    }:
        return "missing_input:source_unit_instance_id"
    return "missing_target:unit_instance_ids"


def target_binding_clause_unavailable_reason(
    *,
    clause: RuleClause,
    context: RuleTargetExecutionContext,
) -> str | None:
    if clause.target is None or clause.target.kind not in UNIT_EFFECT_TARGET_KINDS:
        return None
    selected_target_reason = selected_target_clause_unavailable_reason(
        clause=clause,
        context=context,
    )
    if selected_target_reason is not None:
        return selected_target_reason
    target_unit_instance_ids = target_unit_instance_ids_for_clause(
        clause=clause,
        context=context,
        target_unit_instance_ids=None,
    )
    if target_unit_instance_ids:
        target_keyword_reason = target_spec_keyword_unavailable_reason(
            clause=clause,
            context=context,
            target_unit_instance_ids=target_unit_instance_ids,
        )
        if target_keyword_reason is not None:
            return target_keyword_reason
        return None
    if clause.target.kind in {RuleTargetKind.THIS_MODEL, RuleTargetKind.THIS_UNIT}:
        return "missing_input:source_unit_instance_id"
    return "missing_target:unit_instance_ids"


def selected_target_clause_unavailable_reason(
    *,
    clause: RuleClause,
    context: RuleTargetExecutionContext,
) -> str | None:
    if clause.target is None or clause.target.kind is not RuleTargetKind.SELECTED_TARGET:
        return None
    selected_target_unit_ids = selected_target_unit_ids_or_none(context.trigger_payload)
    if selected_target_unit_ids is None:
        return "missing_selected_target_context"
    if not selected_target_unit_ids:
        return "no_selected_target_units"
    if not context.target_unit_instance_ids:
        return None
    selected_target_unit_id_set = set(selected_target_unit_ids)
    if all(unit_id in selected_target_unit_id_set for unit_id in context.target_unit_instance_ids):
        return None
    return "unit_not_selected_as_target"


def target_spec_keyword_unavailable_reason(
    *,
    clause: RuleClause,
    context: RuleTargetExecutionContext,
    target_unit_instance_ids: tuple[str, ...],
) -> str | None:
    if clause.target is None:
        return None
    required_keywords = required_target_keywords(clause.target)
    if not required_keywords:
        return None
    if context.state is None:
        return "missing_input:game_state"
    for unit_id in target_unit_instance_ids:
        unit = unit_instance_by_id(state=context.state, unit_instance_id=unit_id)
        if not unit_has_required_keywords(
            unit_keywords=unit.keywords,
            faction_keywords=unit.faction_keywords,
            required_keywords=required_keywords,
        ):
            return "unit_missing_required_keyword"
    return None


def required_target_keywords(target: object) -> tuple[str, ...]:
    if type(target) is not RuleTargetSpec:
        raise GameLifecycleError("Target keyword validation requires RuleTargetSpec.")
    parameters = parameter_payload(target.parameters)
    keywords: list[str] = []
    required_keyword = parameters.get("required_keyword")
    if type(required_keyword) is str:
        keywords.append(required_keyword)
    required_keyword_sequence = parameters.get("required_keyword_sequence")
    if type(required_keyword_sequence) is tuple:
        keywords.extend(required_keyword_sequence)
    return tuple(sorted({canonical_keyword(keyword) for keyword in keywords}))


def unit_instance_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army_definition in state.army_definitions:
        for unit in army_definition.units:
            if unit.unit_instance_id == requested_id:
                return unit
    raise GameLifecycleError("Rule execution target unit is unknown.")


def clause_requires_unit_target(clause: RuleClause) -> bool:
    return (
        clause.target is not None
        and clause.target.kind in UNIT_EFFECT_TARGET_KINDS
        and any(effect.kind in TARGET_SCOPED_EFFECT_KINDS for effect in clause.effects)
    )


def target_unit_instance_ids_for_clause(
    *,
    clause: RuleClause,
    context: RuleTargetExecutionContext,
    target_unit_instance_ids: tuple[str, ...] | None,
) -> tuple[str, ...]:
    if clause.target is not None and clause.target.kind in {
        RuleTargetKind.THIS_MODEL,
        RuleTargetKind.THIS_UNIT,
    }:
        if context.source_unit_instance_id is None:
            return ()
        return (context.source_unit_instance_id,)
    if clause.target is not None and clause.target.kind is RuleTargetKind.SELECTED_TARGET:
        if target_unit_instance_ids is not None:
            return target_unit_instance_ids
        if context.target_unit_instance_ids:
            return context.target_unit_instance_ids
        selected_target_unit_ids = selected_target_unit_ids_or_none(context.trigger_payload)
        if selected_target_unit_ids is None:
            return ()
        return selected_target_unit_ids
    if target_unit_instance_ids is not None:
        return target_unit_instance_ids
    if context.target_unit_instance_ids:
        return context.target_unit_instance_ids
    return ()


def unit_has_required_keywords(
    *,
    unit_keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
    required_keywords: tuple[str, ...],
) -> bool:
    unit_keyword_set = {
        canonical_keyword(keyword) for keyword in (*unit_keywords, *faction_keywords)
    }
    return {canonical_keyword(keyword) for keyword in required_keywords}.issubset(unit_keyword_set)


def canonical_keyword(keyword: str) -> str:
    return keyword.strip().upper().replace("_", " ").replace("-", " ")
