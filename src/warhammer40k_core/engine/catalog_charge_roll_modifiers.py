from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.generic_rule_strength_constraints import (
    TARGET_CONSTRAINT_TARGET_UNIT_BELOW_HALF_STRENGTH,
    TARGET_CONSTRAINT_TARGET_UNIT_BELOW_STARTING_STRENGTH,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_unit_geometry import (
    placed_alive_geometry_models_for_rules_unit,
)
from warhammer40k_core.engine.rules_units import (
    placed_alive_rules_unit_views,
    rules_unit_view_by_id,
)
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_CHARGE_ROLL_TYPES = frozenset({"charge", "charge_roll"})
_NEARBY_UNIT_GATE_SUBJECT = "nearby_unit"
_NEARBY_UNIT_RELATIONSHIP = "any_unit_within_distance_of_this_unit"
_TARGET_ALLEGIANCE_ENEMY = "enemy"
_SUPPORTED_NEARBY_TARGET_CONSTRAINTS = frozenset(
    {
        TARGET_CONSTRAINT_TARGET_UNIT_BELOW_STARTING_STRENGTH,
        TARGET_CONSTRAINT_TARGET_UNIT_BELOW_HALF_STRENGTH,
    }
)


@dataclass(frozen=True, slots=True)
class _ChargeRollModifierCandidate:
    modifier: RollModifier
    exclusive_group: str | None
    priority: int


@dataclass(frozen=True, slots=True)
class CatalogChargeRollModifierSource:
    rule_ir: RuleIR
    record_id: str
    source_id: str

    def __post_init__(self) -> None:
        if type(self.rule_ir) is not RuleIR:
            raise GameLifecycleError("Catalog charge modifier source requires RuleIR.")
        object.__setattr__(self, "record_id", _validate_identifier("record_id", self.record_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))


def validate_catalog_charge_roll_modifier_state(state: GameState) -> None:
    _require_game_state(state)


def clause_effect_is_supported_charge_roll_modifier(
    clause: RuleClause,
    effect: RuleEffectSpec,
) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog charge modifier requires RuleClause values.")
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog charge modifier requires RuleEffectSpec values.")
    if (
        not clause.is_supported
        or clause.duration is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or parameter_payload(clause.target.parameters)
        or len(clause.effects) != 1
        or clause.effects[0] != effect
        or effect.kind is not RuleEffectKind.MODIFY_DICE_ROLL
    ):
        return False

    effect_parameters = parameter_payload(effect.parameters)
    roll_type = effect_parameters.get("roll_type")
    if type(roll_type) is not str or roll_type not in _CHARGE_ROLL_TYPES:
        return False
    if type(effect_parameters.get("delta")) is not int:
        return False
    if not _trigger_is_supported(clause=clause, roll_type=roll_type):
        return False

    if not clause.conditions:
        return set(effect_parameters) == {"delta", "roll_type"}
    if len(clause.conditions) != 1 or not _condition_is_supported_nearby_strength_gate(
        clause.conditions[0]
    ):
        return False
    if set(effect_parameters) != {
        "delta",
        "modifier_exclusive_group",
        "modifier_priority",
        "roll_type",
    }:
        return False
    exclusive_group = effect_parameters.get("modifier_exclusive_group")
    priority = effect_parameters.get("modifier_priority")
    return (
        type(exclusive_group) is str
        and bool(exclusive_group.strip())
        and type(priority) is int
        and priority > 0
    )


def catalog_charge_roll_modifiers_from_rule_ir(
    *,
    state: GameState,
    rule_ir: RuleIR,
    record_id: str,
    source_id: str,
    charging_unit_instance_id: str,
) -> tuple[RollModifier, ...]:
    return catalog_charge_roll_modifiers_from_sources(
        state=state,
        sources=(
            CatalogChargeRollModifierSource(
                rule_ir=rule_ir,
                record_id=record_id,
                source_id=source_id,
            ),
        ),
        charging_unit_instance_id=charging_unit_instance_id,
    )


def catalog_charge_roll_modifiers_from_sources(
    *,
    state: GameState,
    sources: tuple[CatalogChargeRollModifierSource, ...],
    charging_unit_instance_id: str,
) -> tuple[RollModifier, ...]:
    _require_game_state(state)
    if type(sources) is not tuple or any(
        type(source) is not CatalogChargeRollModifierSource for source in sources
    ):
        raise GameLifecycleError(
            "Catalog charge modifier sources must contain CatalogChargeRollModifierSource values."
        )
    charging_unit_id = _validate_identifier(
        "charging_unit_instance_id",
        charging_unit_instance_id,
    )

    candidates: list[_ChargeRollModifierCandidate] = []
    for source in sources:
        candidates.extend(
            _catalog_charge_roll_modifier_candidates_from_rule_ir(
                state=state,
                source=source,
                charging_unit_instance_id=charging_unit_id,
            )
        )
    return tuple(
        sorted(
            _resolve_exclusive_candidates(candidates),
            key=lambda modifier: modifier.modifier_id,
        )
    )


def _catalog_charge_roll_modifier_candidates_from_rule_ir(
    *,
    state: GameState,
    source: CatalogChargeRollModifierSource,
    charging_unit_instance_id: str,
) -> tuple[_ChargeRollModifierCandidate, ...]:
    candidates: list[_ChargeRollModifierCandidate] = []
    rule_ir = source.rule_ir
    for clause in rule_ir.clauses:
        for effect_index, effect in enumerate(clause.effects):
            if not clause_effect_is_supported_charge_roll_modifier(clause, effect):
                continue
            if not _clause_conditions_apply(
                state=state,
                clause=clause,
                charging_unit_instance_id=charging_unit_instance_id,
            ):
                continue
            parameters = parameter_payload(effect.parameters)
            exclusive_group = parameters.get("modifier_exclusive_group")
            priority = parameters.get("modifier_priority", 0)
            if exclusive_group is not None:
                exclusive_group = _validate_identifier(
                    "modifier_exclusive_group",
                    exclusive_group,
                )
            if type(priority) is not int:
                raise GameLifecycleError("Catalog charge modifier priority must be an integer.")
            candidates.append(
                _ChargeRollModifierCandidate(
                    modifier=RollModifier(
                        modifier_id=(
                            f"{source.record_id}:{clause.clause_id}:effect-{effect_index:03d}"
                        ),
                        source_id=source.source_id,
                        operand=_required_int_parameter(parameters, key="delta"),
                        priority=priority,
                    ),
                    exclusive_group=exclusive_group,
                    priority=priority,
                )
            )
    return tuple(candidates)


def _trigger_is_supported(*, clause: RuleClause, roll_type: str) -> bool:
    trigger = clause.trigger
    if trigger is None:
        return True
    return trigger.kind is RuleTriggerKind.DICE_ROLL and parameter_payload(trigger.parameters) == {
        "roll_type": roll_type
    }


def _condition_is_supported_nearby_strength_gate(condition: RuleCondition) -> bool:
    if type(condition) is not RuleCondition:
        raise GameLifecycleError("Catalog charge modifier requires RuleCondition values.")
    if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT:
        return False
    parameters = parameter_payload(condition.parameters)
    if set(parameters) != {
        "distance_inches",
        "gate_subject",
        "relationship",
        "target_allegiance",
        "target_constraint",
    }:
        return False
    return (
        parameters.get("gate_subject") == _NEARBY_UNIT_GATE_SUBJECT
        and parameters.get("relationship") == _NEARBY_UNIT_RELATIONSHIP
        and parameters.get("target_allegiance") == _TARGET_ALLEGIANCE_ENEMY
        and parameters.get("target_constraint") in _SUPPORTED_NEARBY_TARGET_CONSTRAINTS
        and _positive_finite_distance(parameters.get("distance_inches")) is not None
    )


def _clause_conditions_apply(
    *,
    state: GameState,
    clause: RuleClause,
    charging_unit_instance_id: str,
) -> bool:
    from warhammer40k_core.engine.generic_rule_attack_conditions import (
        generic_rule_target_constraints_apply,
    )

    if not clause.conditions:
        return True
    condition = clause.conditions[0]
    parameters = parameter_payload(condition.parameters)
    distance_inches = _positive_finite_distance(parameters.get("distance_inches"))
    target_constraint = parameters.get("target_constraint")
    if distance_inches is None or type(target_constraint) is not str:
        raise GameLifecycleError("Catalog charge modifier condition shape drifted.")
    charging_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=charging_unit_instance_id,
    )
    source_models = placed_alive_geometry_models_for_rules_unit(
        state=state,
        unit_instance_id=charging_rules_unit.unit_instance_id,
    )
    if not source_models:
        raise GameLifecycleError("Catalog charge modifier requires a placed charging unit.")
    for candidate in placed_alive_rules_unit_views(state=state):
        if candidate.owner_player_id == charging_rules_unit.owner_player_id:
            continue
        target_models = placed_alive_geometry_models_for_rules_unit(
            state=state,
            unit_instance_id=candidate.unit_instance_id,
        )
        if not target_models:
            raise GameLifecycleError("Catalog charge modifier requires placed enemy unit models.")
        if _closest_distance_inches(source_models, target_models) > distance_inches:
            continue
        if generic_rule_target_constraints_apply(
            state=state,
            constraints=(target_constraint,),
            attacking_unit_instance_id=charging_rules_unit.unit_instance_id,
            attacker_model_instance_id=None,
            target_unit_instance_id=candidate.unit_instance_id,
            attack_strength=None,
            target_toughness=None,
        ):
            return True
    return False


def _closest_distance_inches(
    source_models: tuple[GeometryModel, ...],
    target_models: tuple[GeometryModel, ...],
) -> float:
    if not all(type(model) is GeometryModel for model in (*source_models, *target_models)):
        raise GameLifecycleError("Catalog charge modifier geometry contains invalid models.")
    return min(
        DistanceMeasurementContext.from_models(source, target).closest_distance_inches()
        for source in source_models
        for target in target_models
    )


def _resolve_exclusive_candidates(
    candidates: list[_ChargeRollModifierCandidate],
) -> tuple[RollModifier, ...]:
    ungrouped = [
        candidate.modifier for candidate in candidates if candidate.exclusive_group is None
    ]
    candidates_by_group: dict[str, list[_ChargeRollModifierCandidate]] = {}
    for candidate in candidates:
        if candidate.exclusive_group is None:
            continue
        candidates_by_group.setdefault(candidate.exclusive_group, []).append(candidate)
    for group, grouped_candidates in candidates_by_group.items():
        highest_priority = max(candidate.priority for candidate in grouped_candidates)
        selected = tuple(
            candidate for candidate in grouped_candidates if candidate.priority == highest_priority
        )
        if len(selected) != 1:
            raise GameLifecycleError(
                f"Catalog charge modifier exclusive group {group!r} has ambiguous priority."
            )
        ungrouped.append(selected[0].modifier)
    return tuple(ungrouped)


def _positive_finite_distance(value: object) -> float | None:
    if type(value) is int:
        distance = float(value)
    elif type(value) is float:
        distance = value
    else:
        return None
    if not math.isfinite(distance) or distance <= 0:
        return None
    return distance


def _required_int_parameter(parameters: Mapping[str, object], *, key: str) -> int:
    value = parameters.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Catalog charge modifier {key} must be an integer.")
    return value


def _require_game_state(value: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(value) is not GameState:
        raise GameLifecycleError("Catalog charge modifier consumption requires GameState.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
