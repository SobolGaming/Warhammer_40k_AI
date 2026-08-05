from __future__ import annotations

from typing import cast

from tests.support.catalog_package_fixtures import post_shoot_charge_target_effect_package

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    effect_with_selected_target,
)
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.rule_execution import RuleExecutionContext
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload


def selected_target_charge_persisting_effect(
    *,
    state: GameState,
    effect_id: str,
    owner_player_id: str,
    source_rules_unit_instance_id: str,
    source_component_unit_instance_id: str,
    selected_target_unit_instance_id: str,
) -> PersistingEffect:
    package = post_shoot_charge_target_effect_package()
    descriptor = next(
        ability
        for ability in package.army_catalog.datasheet_by_id("test-lord-of-change").abilities
        if ability.name == "Lethal Obsession"
    )
    if descriptor.rule_ir_payload is None:
        raise AssertionError("Lethal Obsession fixture requires source-backed RuleIR.")
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, descriptor.rule_ir_payload))
    effect_clauses = tuple(clause for clause in rule_ir.clauses if clause.effects)
    if len(effect_clauses) != 1:
        raise AssertionError("Lethal Obsession fixture requires one effect clause.")
    clause = effect_clauses[0]
    if clause.target is None or clause.duration is None or len(clause.effects) != 1:
        raise AssertionError("Lethal Obsession fixture RuleIR shape drifted.")
    transformed_effect = effect_with_selected_target(
        clause.effects[0],
        selected_target_unit_instance_id=selected_target_unit_instance_id,
        clause=clause,
    )
    execution_context = RuleExecutionContext(
        game_id=state.game_id,
        player_id=owner_player_id,
        battle_round=state.battle_round,
        phase=BattlePhaseKind.SHOOTING,
        active_player_id=owner_player_id,
        timing_window_id="attack_sequence_completed",
        source_unit_instance_id=source_component_unit_instance_id,
        target_unit_instance_ids=(source_rules_unit_instance_id,),
        trigger_payload={
            "selected_target_unit_instance_id": selected_target_unit_instance_id,
            "selected_target_unit_instance_ids": [selected_target_unit_instance_id],
        },
        record_persisting_effects=False,
    )
    return PersistingEffect(
        effect_id=effect_id,
        source_rule_id=rule_ir.source_id,
        owner_player_id=owner_player_id,
        target_unit_instance_ids=(source_rules_unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=owner_player_id,
        ),
        effect_payload=validate_json_value(
            {
                "effect_kind": GENERIC_RULE_EFFECT_KIND,
                "rule_id": rule_ir.rule_id,
                "source_id": rule_ir.source_id,
                "rule_ir_hash": rule_ir.ir_hash(),
                "clause_id": clause.clause_id,
                "effect_index": 0,
                "source_span": clause.source_span.to_payload(),
                "target": clause.target.to_payload(),
                "target_unit_instance_ids": [source_rules_unit_instance_id],
                "duration": clause.duration.to_payload(),
                "effect": transformed_effect.to_payload(),
                "conditions": [condition.to_payload() for condition in clause.conditions],
                "context": execution_context.to_payload(),
                "catalog_selected_target": {
                    "hook_id": "test:lethal-obsession:post-shoot",
                    "submission_kind": "select_catalog_post_shoot_hit_target_effect",
                    "catalog_record_id": "test:lethal-obsession:record",
                    "ability_id": "test:lethal-obsession:ability",
                    "ability_name": "Lethal Obsession",
                    "source_unit_instance_id": source_component_unit_instance_id,
                    "source_model_instance_id": None,
                    "selection_clause_id": rule_ir.clauses[0].clause_id,
                    "selected_target_unit_instance_id": selected_target_unit_instance_id,
                    "attack_sequence_id": "test:lethal-obsession:attack-sequence",
                    "attack_sequence_completed_event_id": "test:lethal-obsession:completed",
                },
            }
        ),
    )
