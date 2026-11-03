"""Active catalog self thresholds, evaluated against current charge and source lifetime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.weapon_profiles import RangeProfileKind
from warhammer40k_core.engine.abilities import AbilityCatalogIndex, AbilitySourceKind
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)


@dataclass(frozen=True, slots=True)
class CatalogSelfHitThreshold:
    source_rule_id: str
    clause_id: str
    rule_ir_hash: str
    critical_threshold: int

    @property
    def source_id(self) -> str:
        return f"{self.source_rule_id}:{self.clause_id}:{self.rule_ir_hash}:critical-hit-threshold"


def charged_melee_self_threshold(clause: RuleClause) -> int | None:
    """Admit only the complete supported passive self clause, never selected targets."""
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog self hit threshold requires RuleClause.")
    if (
        clause.unsupported_reason is not None
        or clause.diagnostics
        or clause.conditions
        or clause.duration is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.target.parameters
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.DICE_ROLL
        or parameter_payload(clause.trigger.parameters) != {"roll_type": "hit"}
        or len(clause.effects) != 1
    ):
        return None
    effect = clause.effects[0]
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return None
    parameters = parameter_payload(effect.parameters)
    threshold = parameters.get("critical_threshold")
    if (
        type(threshold) is not int
        or not 2 <= threshold <= 6
        or parameters
        != {
            "status": "critical_hit_threshold",
            "roll_type": "hit",
            "attack_role": "attacker",
            "critical_threshold": threshold,
            "weapon_scope": "melee",
            "requires_charge_move_this_turn": True,
        }
        or parameters.get("requires_charge_move_this_turn") is not True
    ):
        return None
    return threshold


def catalog_self_hit_thresholds(
    context: HitRollMinimumUnmodifiedSuccessContext,
    *,
    ability_indexes: tuple[tuple[str, AbilityCatalogIndex], ...],
) -> tuple[CatalogSelfHitThreshold, ...]:
    from warhammer40k_core.engine.abilities import ability_record_is_active_generic_rule_ir
    from warhammer40k_core.engine.catalog_attack_context_rule_runtime import (
        CatalogDatasheetClauseSource,
        current_effect_target_model_ids,
        source_applies_to_rules_unit,
    )
    from warhammer40k_core.engine.catalog_rule_consumption import (
        catalog_rule_clauses_from_record,
        catalog_rule_record_source_matches_unit,
    )
    from warhammer40k_core.engine.fights_first import (
        CHARGE_FIGHTS_FIRST_EFFECT_KIND,
        FightsFirstRegistry,
    )
    from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.runtime_modifier_permissions import (
        permission_index_for_owner,
        validate_permission_indexes,
    )

    validate_permission_indexes(ability_indexes)
    if not ability_indexes:
        return ()
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return ()
    view = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    index = permission_index_for_owner(ability_indexes, view.owner_player_id)
    if not FightsFirstRegistry.from_state(context.state).has_unit_lineage(
        state=context.state,
        unit_instance_id=view.unit_instance_id,
        effect_kind=CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    ):
        return ()
    contributions: dict[str, CatalogSelfHitThreshold] = {}
    for record in index.all_records():
        if (
            record.source_kind is not AbilitySourceKind.DATASHEET
            or not ability_record_is_active_generic_rule_ir(record)
        ):
            continue
        for component in view.components:
            unit = component.unit
            if not catalog_rule_record_source_matches_unit(
                record=record,
                unit=unit,
                current_model_instance_ids=unit.own_model_ids(),
            ):
                continue
            rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
            for clause in catalog_rule_clauses_from_record(record):
                threshold = charged_melee_self_threshold(clause)
                if threshold is None:
                    continue
                source = CatalogDatasheetClauseSource(
                    view.owner_player_id,
                    record,
                    unit,
                    clause,
                    rule_ir,
                )
                if not source_applies_to_rules_unit(
                    source=source,
                    context_unit_id=view.unit_instance_id,
                    state=context.state,
                ) or context.attacker_model_instance_id not in current_effect_target_model_ids(
                    state=context.state,
                    source=source,
                ):
                    continue
                contribution = CatalogSelfHitThreshold(
                    rule_ir.source_id,
                    clause.clause_id,
                    rule_ir.ir_hash(),
                    threshold,
                )
                contributions[contribution.source_id] = contribution
    return tuple(contributions[key] for key in sorted(contributions))


if TYPE_CHECKING:
    from warhammer40k_core.engine.runtime_modifiers import HitRollMinimumUnmodifiedSuccessContext
