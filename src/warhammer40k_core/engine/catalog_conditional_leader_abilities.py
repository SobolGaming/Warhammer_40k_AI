from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID,
    CONDITIONAL_LEADING_ROLL_REROLL_DESCRIPTOR_ID,
    FACTION_RESOURCE_REFUND_ROLL_DESCRIPTOR_ID,
)
from warhammer40k_core.engine.catalog_datasheet_rule_descriptors import (
    conditional_leader_ability_grant_descriptor_for_clause,
    faction_resource_refund_roll_descriptor_for_clause,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    PersistingEffect,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    generic_rule_effect_payload,
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleIR,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class _ConditionalLeaderRuleSource:
    player_id: str
    record: AbilityCatalogRecord
    unit: UnitInstance
    clause: RuleClause
    rule_ir: RuleIR
    descriptor_id: str

    @property
    def effect_id(self) -> str:
        return (
            f"{self.rule_ir.source_id}:{self.unit.unit_instance_id}:"
            f"{self.clause.clause_id}:conditional-rule"
        )


@dataclass(frozen=True, slots=True)
class CatalogConditionalLeaderAbilityRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.ability_indexes_by_player_id), Mapping):
            raise GameLifecycleError("Conditional leader ability indexes must be a mapping.")
        if type(self.armies) is not tuple or not all(
            type(army) is ArmyDefinition for army in self.armies
        ):
            raise GameLifecycleError("Conditional leader abilities require ArmyDefinition values.")
        player_ids = {army.player_id for army in self.armies}
        if set(self.ability_indexes_by_player_id) != player_ids:
            raise GameLifecycleError("Conditional leader ability indexes must match armies.")
        if not all(
            type(index) is AbilityCatalogIndex
            for index in self.ability_indexes_by_player_id.values()
        ):
            raise GameLifecycleError("Conditional leader ability indexes are invalid.")

    def record_static_effects(self, *, state: GameState) -> tuple[PersistingEffect, ...]:
        _require_game_state(state)
        effects: list[PersistingEffect] = []
        for source in self._sources():
            effect = _persisting_effect_for_source(state=state, source=source)
            _record_static_effect(state=state, effect=effect)
            effects.append(effect)
        return tuple(sorted(effects, key=lambda effect: effect.effect_id))

    def _sources(self) -> tuple[_ConditionalLeaderRuleSource, ...]:
        sources: list[_ConditionalLeaderRuleSource] = []
        for army in self.armies:
            index = self.ability_indexes_by_player_id[army.player_id]
            for record in index.all_records():
                if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                    continue
                rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
                for unit in army.units:
                    if not catalog_rule_record_source_matches_unit(
                        record=record,
                        unit=unit,
                        current_model_instance_ids=unit.own_model_ids(),
                    ):
                        continue
                    for clause in catalog_rule_clauses_from_record(record):
                        descriptor_id = _conditional_descriptor_id_for_clause(clause)
                        if descriptor_id is None:
                            continue
                        sources.append(
                            _ConditionalLeaderRuleSource(
                                player_id=army.player_id,
                                record=record,
                                unit=unit,
                                clause=clause,
                                rule_ir=rule_ir,
                                descriptor_id=descriptor_id,
                            )
                        )
        return tuple(sorted(sources, key=lambda source: source.effect_id))


def _persisting_effect_for_source(
    *,
    state: GameState,
    source: _ConditionalLeaderRuleSource,
) -> PersistingEffect:
    effect = source.clause.effects[0]
    context = RuleExecutionContext(
        game_id=state.game_id,
        player_id=source.player_id,
        battle_round=1,
        phase=None,
        active_player_id=None,
        source_unit_instance_id=source.unit.unit_instance_id,
        source_keywords=tuple(sorted({*source.unit.keywords, *source.unit.faction_keywords})),
        state=state,
        record_persisting_effects=False,
    )
    payload = generic_rule_effect_payload(
        rule_ir=source.rule_ir,
        clause=source.clause,
        effect=effect,
        context=context,
        target_unit_instance_ids=(source.unit.unit_instance_id,),
        effect_index=0,
    )
    payload["descriptor_id"] = source.descriptor_id
    payload["template_id"] = source.clause.template_id
    return generic_rule_persisting_effect(
        effect_id=source.effect_id,
        source_rule_id=source.rule_ir.source_id,
        owner_player_id=source.player_id,
        target_unit_instance_ids=(source.unit.unit_instance_id,),
        started_battle_round=1,
        expiration=EffectExpiration.end_of_battle(),
        effect_payload=validate_json_value(payload),
    )


def _record_static_effect(*, state: GameState, effect: PersistingEffect) -> None:
    for existing in state.persisting_effects:
        if existing.effect_id != effect.effect_id:
            continue
        if existing != effect:
            raise GameLifecycleError("Conditional leader rule effect conflicts with state.")
        return
    state.record_persisting_effect(effect)


def _conditional_descriptor_id_for_clause(clause: RuleClause) -> str | None:
    if conditional_leader_ability_grant_descriptor_for_clause(clause) is not None:
        return CONDITIONAL_LEADER_ABILITY_DESCRIPTOR_ID
    if _conditional_leading_reroll_roll_type(clause) is not None:
        return CONDITIONAL_LEADING_ROLL_REROLL_DESCRIPTOR_ID
    if faction_resource_refund_roll_descriptor_for_clause(clause) is not None:
        return FACTION_RESOURCE_REFUND_ROLL_DESCRIPTOR_ID
    return None


def _conditional_leading_reroll_roll_type(clause: RuleClause) -> str | None:
    if (
        not clause.is_supported
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.DICE_ROLL
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.SELECTED_UNIT
        or len(clause.effects) != 1
        or not _has_leading_relationship(clause)
    ):
        return None
    trigger = parameter_payload(clause.trigger.parameters)
    effect = clause.effects[0]
    effect_parameters = parameter_payload(effect.parameters)
    roll_type = trigger.get("roll_type")
    if (
        trigger.get("edge") != "after"
        or trigger.get("subject") != "selected_unit"
        or type(roll_type) is not str
        or effect.kind is not RuleEffectKind.REROLL_PERMISSION
        or effect_parameters != {"roll_type": roll_type, "selection": "whole_roll"}
    ):
        return None
    return roll_type


def _has_leading_relationship(clause: RuleClause) -> bool:
    return any(
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters) == {"relationship": "this_model_leading_unit"}
        for condition in clause.conditions
    )


def _require_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Conditional leader rule runtime requires GameState.")
