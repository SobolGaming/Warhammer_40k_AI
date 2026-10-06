from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.core.keyword_membership import keyword_inventory_contains
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.rules.rule_ir import RuleParameterValue


def scoped_roll_model_ids_for_effect(
    *,
    source_rules_unit: RulesUnitView,
    current_roll_model_instance_ids: tuple[str, ...],
    effect_parameters: Mapping[str, RuleParameterValue],
) -> tuple[str, ...]:
    if type(source_rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Catalog model scope requires a RulesUnitView.")
    current_ids = _current_model_ids(current_roll_model_instance_ids)
    required_model_keyword = effect_parameters.get("required_model_keyword")
    if required_model_keyword is None:
        return tuple(sorted(current_ids))
    if type(required_model_keyword) is not str or not required_model_keyword.strip():
        raise GameLifecycleError("Catalog model scope keyword is malformed.")
    return tuple(
        sorted(
            model.model_instance_id
            for component in source_rules_unit.components
            for model in component.unit.own_models
            if keyword_inventory_contains(
                keywords=model.keywords,
                keyword=required_model_keyword,
                name_keywords=()
                if model.keyword_assignment.name_keyword is None
                else (model.keyword_assignment.name_keyword,),
                ordinary_keywords=model.keyword_assignment.keywords
                if model.keyword_assignment.name_is_ordinary_keyword
                else (),
                normalizer=lambda token: token.upper().replace(" ", "_").replace("-", "_"),
            )
            and (model.is_alive or model.model_instance_id in source_rules_unit.retained_model_ids)
            and model.model_instance_id in current_ids
        )
    )


def _current_model_ids(values: tuple[str, ...]) -> frozenset[str]:
    if type(values) is not tuple or not all(
        type(value) is str and value.strip() for value in values
    ):
        raise GameLifecycleError("Catalog model scope requires current model IDs.")
    if len(values) != len(set(values)):
        raise GameLifecycleError("Catalog model scope current model IDs must be unique.")
    return frozenset(values)
