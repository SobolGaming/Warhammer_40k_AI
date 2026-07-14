from __future__ import annotations

from math import isfinite
from typing import cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.weapon_profiles import (
    WeaponKeyword,
    canonical_weapon_keyword_tokens,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleParameterValue,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTriggerKind,
    parameter_payload,
)

_SUPPORTED_DURATION_ENDPOINTS = frozenset({"phase", "turn", "battle_round", "battle"})
_SUPPORTED_ATTACK_KINDS = frozenset({"melee", "ranged"})
_SUPPORTED_EFFECT_TARGET_KINDS = frozenset(
    {
        RuleTargetKind.ENEMY_UNIT,
        RuleTargetKind.FRIENDLY_UNIT,
        RuleTargetKind.SELECTED_TARGET,
        RuleTargetKind.SELECTED_UNIT,
        RuleTargetKind.THIS_MODEL,
        RuleTargetKind.THIS_UNIT,
    }
)
_ATTACKER_EFFECT_TARGET_KINDS = frozenset(
    {
        RuleTargetKind.FRIENDLY_UNIT,
        RuleTargetKind.THIS_MODEL,
        RuleTargetKind.THIS_UNIT,
    }
)
_TARGET_EFFECT_TARGET_KINDS = frozenset(
    {
        RuleTargetKind.ENEMY_UNIT,
        RuleTargetKind.SELECTED_TARGET,
        RuleTargetKind.SELECTED_UNIT,
    }
)
_SUPPORTED_WEAPON_CHARACTERISTICS = frozenset(
    {
        Characteristic.ARMOR_PENETRATION.value,
        Characteristic.ATTACKS.value,
        Characteristic.BALLISTIC_SKILL.value,
        Characteristic.DAMAGE.value,
        Characteristic.STRENGTH.value,
        Characteristic.WEAPON_SKILL.value,
    }
)
_SUPPORTED_ROLL_MODIFIER_TYPES = frozenset(
    {
        "attack_sequence_damage",
        "attack_sequence_hit",
        "attack_sequence_save",
        "attack_sequence_wound",
        "damage",
        "damage_roll",
        "hit",
        "hit_roll",
        "save",
        "save_roll",
        "wound",
        "wound_roll",
    }
)
_SUPPORTED_REROLL_TYPES = frozenset(
    {
        "attack_sequence_hit",
        "attack_sequence_wound",
        "hit",
        "hit_roll",
        "wound",
        "wound_roll",
    }
)
_VALUE_REQUIRED_WEAPON_KEYWORDS = frozenset(
    {
        WeaponKeyword.CLEAVE.value,
        WeaponKeyword.MELTA.value,
        WeaponKeyword.RAPID_FIRE.value,
        WeaponKeyword.SUSTAINED_HITS.value,
    }
)
_WEAPON_SELECTOR_KEYS = frozenset(
    {
        "attack_role",
        "weapon_name",
        "weapon_names",
        "weapon_scope",
    }
)
_IMMEDIATE_BATTLE_SHOCK_PARAMETER_KEYS = frozenset(
    {
        "reason",
        "required",
        "rules_context",
        "status",
        "target_scope",
    }
)
_FIGHT_START_TRIGGER_PARAMETER_KEYS = frozenset({"edge", "owner", "phase"})
_FIGHT_START_TARGET_PARAMETER_KEYS = frozenset({"allegiance"})
_SELECTION_DISTANCE_PARAMETER_KEYS = frozenset(
    {
        "distance_inches",
        "negated",
        "object_kind",
        "object_reference",
        "predicate",
        "qualifier",
        "range_kind",
    }
)
_SELECTION_VISIBILITY_PARAMETER_KEYS = frozenset(
    {
        "observer",
        "predicate",
        "target_reference",
    }
)


def clause_is_fight_start_selected_target_selection(clause: RuleClause) -> bool:
    return fight_start_selected_target_selection_is_supported(clause)


def fight_start_selected_target_selection_is_supported(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog selected-target classifier requires RuleClause.")
    return (
        clause.is_supported
        and clause.template_id == "phase17c:selected-target-constraint"
        and _fight_start_selection_trigger_is_supported(clause)
        and _fight_start_selection_target_is_supported(clause.target)
        and all(
            selected_target_selection_condition_is_supported(condition)
            for condition in clause.conditions
        )
        and not clause.effects
        and clause.duration is None
    )


def selected_target_selection_condition_is_supported(condition: RuleCondition) -> bool:
    if type(condition) is not RuleCondition:
        raise GameLifecycleError(
            "Selected-target selection condition support requires RuleCondition."
        )
    parameters = parameter_payload(condition.parameters)
    if condition.kind is RuleConditionKind.DISTANCE_PREDICATE:
        return _selection_distance_condition_is_supported(parameters)
    if condition.kind is RuleConditionKind.VISIBILITY_PREDICATE:
        return _selection_visibility_condition_is_supported(parameters)
    return False


def fight_start_selected_target_effect_clauses_after(
    clauses: tuple[RuleClause, ...],
    selection_index: int,
) -> tuple[RuleClause, ...]:
    if type(clauses) is not tuple or any(type(clause) is not RuleClause for clause in clauses):
        raise GameLifecycleError(
            "Fight-start selected-target discovery requires RuleClause values."
        )
    if type(selection_index) is not int or not 0 <= selection_index < len(clauses):
        raise GameLifecycleError("Fight-start selected-target selection_index is invalid.")
    selection_clause = clauses[selection_index]
    selected: list[RuleClause] = []
    for clause in clauses[selection_index + 1 :]:
        if clause.template_id == "phase17c:selected-target-constraint":
            break
        if fight_start_selected_target_pair_is_supported(
            selection_clause=selection_clause,
            effect_clause=clause,
        ):
            selected.append(clause)
    return tuple(selected)


def fight_start_selected_target_pair_is_supported(
    *,
    selection_clause: RuleClause,
    effect_clause: RuleClause,
) -> bool:
    if type(selection_clause) is not RuleClause or type(effect_clause) is not RuleClause:
        raise GameLifecycleError(
            "Fight-start selected-target pair support requires RuleClause values."
        )
    return clause_is_fight_start_selected_target_selection(
        selection_clause
    ) and selected_target_persisting_effect_clause_is_supported(effect_clause)


def selected_target_persisting_effect_clause_is_supported(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Selected-target effect support requires RuleClause.")
    return (
        clause.is_supported
        and bool(clause.effects)
        and _effect_target_is_supported(clause.target)
        and _effect_trigger_is_supported(clause)
        and _effect_duration_is_supported(clause.duration)
        and _effect_attack_kind_is_consistent(clause)
        and all(
            _effect_condition_is_supported(condition, clause=clause)
            for condition in clause.conditions
        )
        and all(
            _selected_target_effect_is_supported(effect, clause=clause) for effect in clause.effects
        )
    )


def selected_target_effect_clause_is_supported(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Selected-target effect support requires RuleClause.")
    return clause_has_immediate_selected_target_effect(
        clause
    ) or selected_target_persisting_effect_clause_is_supported(clause)


def selected_target_effect_attack_role(
    *,
    clause: RuleClause,
    effect: RuleEffectSpec,
) -> str:
    if type(clause) is not RuleClause or type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Selected-target attack-role resolution requires RuleIR values.")
    if effect not in clause.effects:
        raise GameLifecycleError("Selected-target attack-role effect is not owned by the clause.")
    attack_role = _resolved_effect_attack_role(clause=clause, effect=effect)
    if attack_role is None:
        raise GameLifecycleError("Selected-target attack-role shape is unsupported.")
    return attack_role


def selected_target_effect_weapon_scope(
    *,
    clause: RuleClause,
    effect: RuleEffectSpec,
) -> str | None:
    if type(clause) is not RuleClause or type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Selected-target weapon-scope resolution requires RuleIR values.")
    if effect not in clause.effects:
        raise GameLifecycleError("Selected-target weapon-scope effect is not owned by the clause.")
    if not selected_target_persisting_effect_clause_is_supported(clause):
        raise GameLifecycleError("Selected-target weapon-scope shape is unsupported.")
    attack_kind = _effect_attack_kind(clause)
    explicit_scope = parameter_payload(effect.parameters).get("weapon_scope")
    if explicit_scope is not None and type(explicit_scope) is not str:
        raise GameLifecycleError("Selected-target weapon_scope must be a string.")
    return attack_kind if attack_kind is not None else explicit_scope


def clause_has_immediate_selected_target_effect(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Selected-target effect support requires RuleClause.")
    return (
        clause.is_supported
        and clause.trigger is None
        and not clause.conditions
        and clause.duration is None
        and clause.target is not None
        and clause.target.kind in {RuleTargetKind.SELECTED_UNIT, RuleTargetKind.SELECTED_TARGET}
        and not clause.target.parameters
        and bool(clause.effects)
        and all(
            effect_is_immediate_selected_target_battle_shock(effect) for effect in clause.effects
        )
    )


def effect_is_immediate_selected_target_battle_shock(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Selected-target effect support requires RuleEffectSpec.")
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        frozenset(parameters) == _IMMEDIATE_BATTLE_SHOCK_PARAMETER_KEYS
        and parameters.get("reason") == "forced_by_ability"
        and parameters.get("rules_context") == "battle_shock"
        and parameters.get("status") == "force_battle_shock_test"
        and parameters.get("required") is True
        and parameters.get("target_scope") == "selected_unit"
    )


def selected_target_pair_requires_source_model(
    *,
    selection_clause: RuleClause,
    effect_clauses: tuple[RuleClause, ...],
) -> bool:
    if type(selection_clause) is not RuleClause:
        raise GameLifecycleError("Selected-target model-scope resolution requires RuleClause.")
    if type(effect_clauses) is not tuple or any(
        type(clause) is not RuleClause for clause in effect_clauses
    ):
        raise GameLifecycleError(
            "Selected-target model-scope resolution requires effect RuleClause values."
        )
    return selected_target_selection_clause_binds_source_model(selection_clause) or any(
        selected_target_effect_clause_has_this_model_semantics(clause) for clause in effect_clauses
    )


def selected_target_selection_clause_binds_source_model(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Selected-target source-model binding requires RuleClause.")
    if clause.trigger is not None:
        trigger_parameters = parameter_payload(clause.trigger.parameters)
        if (
            trigger_parameters.get("subject") == "this_model"
            or trigger_parameters.get("attacker_model_reference") == "this_model"
        ):
            return True
    return any(
        (
            condition.kind is RuleConditionKind.DISTANCE_PREDICATE
            and parameter_payload(condition.parameters).get("object_kind") == "model"
            and parameter_payload(condition.parameters).get("object_reference") == "this"
        )
        or (
            condition.kind is RuleConditionKind.VISIBILITY_PREDICATE
            and parameter_payload(condition.parameters).get("observer") == "this_model"
        )
        for condition in clause.conditions
    )


def _fight_start_selection_trigger_is_supported(clause: RuleClause) -> bool:
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    parameters = parameter_payload(trigger.parameters)
    parameter_keys = frozenset(parameters)
    return (
        parameter_keys == _FIGHT_START_TRIGGER_PARAMETER_KEYS
        and parameters.get("edge") == "start"
        and parameters.get("owner") is None
        and parameters.get("phase") == BattlePhase.FIGHT.value
    )


def _fight_start_selection_target_is_supported(target: RuleTargetSpec | None) -> bool:
    if target is None or target.kind is not RuleTargetKind.ENEMY_UNIT:
        return False
    parameters = parameter_payload(target.parameters)
    return (
        frozenset(parameters) == _FIGHT_START_TARGET_PARAMETER_KEYS
        and parameters.get("allegiance") == "enemy"
    )


def _selection_distance_condition_is_supported(
    parameters: dict[str, RuleParameterValue],
) -> bool:
    if (
        frozenset(parameters) != _SELECTION_DISTANCE_PARAMETER_KEYS
        or parameters.get("negated") is not False
        or parameters.get("object_kind") not in {"model", "unit"}
        or parameters.get("object_reference") != "this"
        or parameters.get("qualifier") is not None
    ):
        return False
    range_kind = parameters.get("range_kind")
    distance_inches = parameters.get("distance_inches")
    if range_kind == "engagement_range":
        return parameters.get("predicate") == "within_engagement_range" and distance_inches is None
    if range_kind != "numeric_range" or parameters.get("predicate") != "within":
        return False
    if not isinstance(distance_inches, (int, float)) or type(distance_inches) is bool:
        return False
    numeric_distance = float(distance_inches)
    return isfinite(numeric_distance) and numeric_distance > 0.0


def _selection_visibility_condition_is_supported(
    parameters: dict[str, RuleParameterValue],
) -> bool:
    return (
        frozenset(parameters) == _SELECTION_VISIBILITY_PARAMETER_KEYS
        and parameters.get("observer") in {"this_model", "this_unit"}
        and parameters.get("predicate") == "visible_to"
        and parameters.get("target_reference") == "selected_unit"
    )


def selected_target_effect_clause_has_this_model_semantics(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Selected-target model-scope resolution requires RuleClause.")
    if clause.target is not None and clause.target.kind is RuleTargetKind.THIS_MODEL:
        return True
    if clause.trigger is not None:
        parameters = parameter_payload(clause.trigger.parameters)
        if parameters.get("actor") == "this_model":
            return True
    return any(
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters).get("relationship") == "this_model_makes_attack"
        for condition in clause.conditions
    )


def _effect_target_is_supported(target: RuleTargetSpec | None) -> bool:
    if target is None or target.kind not in _SUPPORTED_EFFECT_TARGET_KINDS:
        return False
    parameters = parameter_payload(target.parameters)
    if target.kind in {
        RuleTargetKind.SELECTED_TARGET,
        RuleTargetKind.SELECTED_UNIT,
        RuleTargetKind.THIS_MODEL,
        RuleTargetKind.THIS_UNIT,
    }:
        return not parameters
    if target.kind is RuleTargetKind.ENEMY_UNIT:
        return frozenset(parameters) in {frozenset(), frozenset({"allegiance"})} and (
            parameters.get("allegiance", "enemy") == "enemy"
        )
    if frozenset(parameters) - {
        "allegiance",
        "required_keyword",
        "required_keyword_sequence",
    }:
        return False
    return (
        parameters.get("allegiance", "friendly") == "friendly"
        and _optional_non_empty_string(parameters.get("required_keyword"))
        and _optional_non_empty_string_tuple(parameters.get("required_keyword_sequence"))
    )


def _effect_trigger_is_supported(clause: RuleClause) -> bool:
    trigger = clause.trigger
    if trigger is None:
        return True
    if trigger.kind is not RuleTriggerKind.DICE_ROLL:
        return False
    parameters = parameter_payload(trigger.parameters)
    actor = parameters.get("actor")
    target_kind = None if clause.target is None else clause.target.kind
    parameter_keys = frozenset(parameters)
    supported_keys = frozenset({"actor", "target_reference", "timing_window"})
    return (
        parameter_keys in {supported_keys, supported_keys | {"attack_kind"}}
        and _optional_attack_kind_is_supported(parameters.get("attack_kind"))
        and parameters.get("target_reference") == "selected_unit"
        and parameters.get("timing_window") == "attack_sequence.attack"
        and (
            (actor == "this_model" and target_kind is RuleTargetKind.THIS_MODEL)
            or (actor == "this_unit" and target_kind is RuleTargetKind.THIS_UNIT)
        )
    )


def _effect_duration_is_supported(duration: RuleDuration | None) -> bool:
    if duration is None:
        return False
    parameters = parameter_payload(duration.parameters)
    if duration.kind is RuleDurationKind.PERMANENT:
        return not parameters
    return (
        duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT
        and frozenset(parameters) == frozenset({"endpoint"})
        and parameters.get("endpoint") in _SUPPORTED_DURATION_ENDPOINTS
    )


def _effect_condition_is_supported(
    condition: RuleCondition,
    *,
    clause: RuleClause,
) -> bool:
    parameters = parameter_payload(condition.parameters)
    if condition.kind is RuleConditionKind.KEYWORD_GATE:
        return (
            clause.target is not None
            and clause.target.kind is RuleTargetKind.FRIENDLY_UNIT
            and frozenset(parameters) == frozenset({"required_keyword"})
            and _non_empty_string(parameters.get("required_keyword"))
        )
    if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT:
        return False
    relationship = parameters.get("relationship")
    if relationship == "target_unit_has_status":
        return (
            frozenset(parameters) == frozenset({"relationship", "status"})
            and parameters.get("status") == "battle_shocked"
        )
    if relationship not in {"attack_targets_selected_unit", "this_model_makes_attack"}:
        return False
    if relationship == "this_model_makes_attack" and (
        clause.target is None or clause.target.kind is not RuleTargetKind.THIS_MODEL
    ):
        return False
    parameter_keys = frozenset(parameters)
    supported_keys = frozenset({"gate_subject", "relationship", "target_reference"})
    return (
        parameter_keys in {supported_keys, supported_keys | {"attack_kind"}}
        and _optional_attack_kind_is_supported(parameters.get("attack_kind"))
        and parameters.get("gate_subject") == "attack_target"
        and parameters.get("target_reference") == "selected_unit"
    )


def _selected_target_effect_is_supported(
    effect: RuleEffectSpec,
    *,
    clause: RuleClause,
) -> bool:
    parameters = parameter_payload(effect.parameters)
    if effect.kind is RuleEffectKind.MODIFY_CHARACTERISTIC:
        effect_is_supported = _characteristic_modifier_is_supported(parameters)
    elif effect.kind is RuleEffectKind.MODIFY_DICE_ROLL:
        effect_is_supported = _dice_roll_modifier_is_supported(parameters)
    elif effect.kind is RuleEffectKind.REROLL_PERMISSION:
        effect_is_supported = _reroll_permission_is_supported(parameters)
    elif effect.kind is RuleEffectKind.GRANT_WEAPON_ABILITY:
        effect_is_supported = _weapon_ability_grant_is_supported(parameters)
    else:
        return False
    return (
        effect_is_supported
        and _resolved_effect_attack_role(clause=clause, effect=effect) is not None
        and _effect_weapon_scope_matches_attack_kind(clause=clause, effect=effect)
    )


def _effect_attack_kind_is_consistent(clause: RuleClause) -> bool:
    return len(set(_effect_attack_kind_values(clause))) <= 1


def _effect_attack_kind(clause: RuleClause) -> str | None:
    values = _effect_attack_kind_values(clause)
    return None if not values else values[0]


def _effect_attack_kind_values(clause: RuleClause) -> tuple[str, ...]:
    values: list[str] = []
    if clause.trigger is not None:
        trigger_attack_kind = parameter_payload(clause.trigger.parameters).get("attack_kind")
        if type(trigger_attack_kind) is str:
            values.append(trigger_attack_kind)
    for condition in clause.conditions:
        condition_attack_kind = parameter_payload(condition.parameters).get("attack_kind")
        if type(condition_attack_kind) is str:
            values.append(condition_attack_kind)
    return tuple(values)


def _effect_weapon_scope_matches_attack_kind(
    *,
    clause: RuleClause,
    effect: RuleEffectSpec,
) -> bool:
    attack_kind = _effect_attack_kind(clause)
    if attack_kind is None:
        return True
    if effect.kind is RuleEffectKind.REROLL_PERMISSION:
        return False
    explicit_scope = parameter_payload(effect.parameters).get("weapon_scope")
    return explicit_scope is None or explicit_scope == attack_kind


def _resolved_effect_attack_role(
    *,
    clause: RuleClause,
    effect: RuleEffectSpec,
) -> str | None:
    if clause.target is None:
        return None
    target_kind = clause.target.kind
    if target_kind in _ATTACKER_EFFECT_TARGET_KINDS:
        target_role = "attacker"
    elif target_kind in _TARGET_EFFECT_TARGET_KINDS:
        target_role = "target"
    else:
        return None

    trigger_role: str | None = None
    if clause.trigger is not None:
        actor = parameter_payload(clause.trigger.parameters).get("actor")
        if actor in {"this_model", "this_unit"}:
            trigger_role = "attacker"
    if trigger_role is not None and trigger_role != target_role:
        return None

    explicit_role = parameter_payload(effect.parameters).get("attack_role")
    if explicit_role is not None and explicit_role != target_role:
        return None
    return target_role


def _characteristic_modifier_is_supported(
    parameters: dict[str, RuleParameterValue],
) -> bool:
    allowed_keys = _WEAPON_SELECTOR_KEYS | {"characteristic", "delta"}
    return (
        not frozenset(parameters) - allowed_keys
        and {"characteristic", "delta"}.issubset(parameters)
        and parameters.get("characteristic") in _SUPPORTED_WEAPON_CHARACTERISTICS
        and type(parameters.get("delta")) is int
        and _attack_role_is_supported(parameters.get("attack_role"))
        and _weapon_selector_is_supported(parameters)
    )


def _dice_roll_modifier_is_supported(parameters: dict[str, RuleParameterValue]) -> bool:
    allowed_keys = _WEAPON_SELECTOR_KEYS | {"delta", "roll_type"}
    roll_type = parameters.get("roll_type")
    return (
        not frozenset(parameters) - allowed_keys
        and {"delta", "roll_type"}.issubset(parameters)
        and type(parameters.get("delta")) is int
        and type(roll_type) is str
        and _lookup_token(roll_type) in _SUPPORTED_ROLL_MODIFIER_TYPES
        and _attack_role_is_supported(parameters.get("attack_role"))
        and _weapon_selector_is_supported(parameters)
    )


def _reroll_permission_is_supported(parameters: dict[str, RuleParameterValue]) -> bool:
    allowed_keys = _WEAPON_SELECTOR_KEYS | {
        "reroll_unmodified_value",
        "roll_type",
        "timing_window",
    }
    roll_type = parameters.get("roll_type")
    reroll_value = parameters.get("reroll_unmodified_value")
    timing_window = parameters.get("timing_window")
    return (
        not frozenset(parameters) - allowed_keys
        and "roll_type" in parameters
        and type(roll_type) is str
        and _lookup_token(roll_type) in _SUPPORTED_REROLL_TYPES
        and (reroll_value is None or (type(reroll_value) is int and 1 <= reroll_value <= 6))
        and (timing_window is None or _non_empty_string(timing_window))
        and _attack_role_is_supported(parameters.get("attack_role"))
        and _weapon_selector_is_supported(parameters)
    )


def _weapon_ability_grant_is_supported(parameters: dict[str, RuleParameterValue]) -> bool:
    allowed_keys = _WEAPON_SELECTOR_KEYS | {"weapon_ability", "weapon_ability_value"}
    keyword = parameters.get("weapon_ability")
    if (
        frozenset(parameters) - allowed_keys
        or type(keyword) is not str
        or keyword not in canonical_weapon_keyword_tokens()
        or keyword == WeaponKeyword.HUNTER.value
        or not _attack_role_is_supported(parameters.get("attack_role"))
        or not _weapon_selector_is_supported(parameters)
    ):
        return False
    value = parameters.get("weapon_ability_value")
    if keyword not in _VALUE_REQUIRED_WEAPON_KEYWORDS:
        return value is None
    if keyword == WeaponKeyword.SUSTAINED_HITS.value:
        return (type(value) is int and value >= 1) or _non_empty_string(value)
    return type(value) is int and value >= 1


def _weapon_selector_is_supported(parameters: dict[str, RuleParameterValue]) -> bool:
    scope = parameters.get("weapon_scope")
    if scope is not None and scope not in {"all", "melee", "ranged"}:
        return False
    name = parameters.get("weapon_name")
    names = parameters.get("weapon_names")
    if name is not None and names is not None:
        return False
    return _optional_non_empty_string(name) and _optional_non_empty_string_tuple(names)


def _attack_role_is_supported(value: RuleParameterValue | None) -> bool:
    return value is None or value in {"attacker", "target"}


def _optional_attack_kind_is_supported(value: RuleParameterValue | None) -> bool:
    return value is None or value in _SUPPORTED_ATTACK_KINDS


def _optional_non_empty_string(value: object) -> bool:
    return value is None or _non_empty_string(value)


def _non_empty_string(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _optional_non_empty_string_tuple(value: object) -> bool:
    if value is None:
        return True
    if type(value) is not tuple or not value:
        return False
    return all(type(item) is str and bool(item.strip()) for item in cast(tuple[object, ...], value))


def _lookup_token(value: str) -> str:
    return "_".join(value.casefold().replace(".", "_").replace("-", "_").split())
