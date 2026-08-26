from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDurationKind,
    RuleEffectKind,
    RuleTargetKind,
    parameter_payload,
)

CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID = "catalog-ir:can-advance-and-charge"
CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID = (
    "catalog-ir:can-advance-and-shoot-and-charge"
)

_CONSUMER_ID_BY_ABILITY = {
    "can_advance_and_charge": CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    "can_advance_and_shoot_and_charge": (CATALOG_IR_CAN_ADVANCE_AND_SHOOT_AND_CHARGE_CONSUMER_ID),
}


def consumer_ids_for_clause(clause: RuleClause) -> tuple[str, ...]:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog advance eligibility requires RuleClause.")
    return tuple(
        consumer_id
        for ability, consumer_id in _CONSUMER_ID_BY_ABILITY.items()
        if clause_grants_advance_eligibility(clause, ability=ability)
    )


def clause_grants_advance_eligibility(clause: RuleClause, *, ability: str) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog advance eligibility requires RuleClause.")
    if type(ability) is not str or not ability.strip():
        raise GameLifecycleError("Catalog advance eligibility ability must be non-empty.")
    requested_ability = ability.strip()
    if clause.target is not None and clause.target.kind is RuleTargetKind.THIS_UNIT:
        return any(
            _effect_grants_ability(
                effect_parameters=parameter_payload(effect.parameters), ability=requested_ability
            )
            for effect in clause.effects
            if effect.kind is RuleEffectKind.GRANT_ABILITY
        )
    if (
        clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_MODEL
        or clause.target.parameters
        or clause.trigger is not None
        or clause.conditions
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.PERMANENT
        or clause.duration.parameters
        or len(clause.effects) != 1
    ):
        return False
    effect = clause.effects[0]
    return effect.kind is RuleEffectKind.GRANT_ABILITY and parameter_payload(effect.parameters) == {
        "ability": requested_ability,
        "target_scope": "this_model",
    }


def validate_model_scoped_source_evidence(
    *,
    source_model_instance_id: str,
    source_is_wargear: bool,
    wargear_bearer_model_instance_ids: tuple[str, ...],
    rules_unit: RulesUnitView,
) -> None:
    if source_is_wargear and wargear_bearer_model_instance_ids != (source_model_instance_id,):
        raise GameLifecycleError(
            "Catalog this-model advance eligibility source must be the current wargear bearer."
        )
    if tuple(sorted(model.model_instance_id for model in rules_unit.alive_models())) != (
        source_model_instance_id,
    ):
        raise GameLifecycleError(
            "Catalog this-model advance eligibility requires a singleton alive rules unit."
        )


def _effect_grants_ability(*, effect_parameters: Mapping[str, object], ability: str) -> bool:
    value = effect_parameters.get("ability")
    return type(value) is str and _lookup_token(value) == _lookup_token(ability)


def _lookup_token(value: str) -> str:
    return "_".join(value.strip().casefold().replace("-", " ").split())
