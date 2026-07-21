# pyright: reportPrivateUsage=false
from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest
from tests.support.catalog_package_fixtures import (
    flesh_hounds_army,
    named_weapon_choice_unit,
    post_shoot_cover_denial_package,
)
from tests.support.catalog_rule_ir_fixtures import (
    effect,
)
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_armies,
    completed_post_shoot_attack_sequence,
    flesh_hounds_battlefield_state,
    player_ability_index,
)

from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
)
from warhammer40k_core.engine.attack_sequence import (
    AttackSequenceStep,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    successful_hit_target_unit_ids_for_sequence,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
    CatalogPostShootHitTargetStatusRuntime,
    _available_catalog_post_shoot_hit_target_status_groups,
    _catalog_post_shoot_hit_target_status_groups_from_clause,
    _clause_is_supported_post_shoot_hit_target_status_denial,
    _effect_is_supported_status_denial,
    _post_shoot_hit_target_status_attack_sequence_from_payload,
    _post_shoot_hit_target_status_option_id,
    _post_shoot_hit_target_status_selected_payload,
    _post_shoot_status_source_model_ids,
    _validate_non_empty_text,
    _validate_post_shoot_hit_target_status_option,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
)
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
)
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleIR,
    RuleIRPayload,
    RuleParameterValue,
    RuleTargetKind,
    RuleTargetSpec,
    parameter_payload,
    parameters_from_pairs,
)


def test_phase17k_post_shoot_hit_target_status_fail_fast_validation_paths() -> None:
    package = post_shoot_cover_denial_package()
    unit = named_weapon_choice_unit(package=package)
    target_unit = named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    army = flesh_hounds_army(package=package, unit=unit)
    enemy_army = flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = player_ability_index(package=package, army=army)
    enemy_player_index = player_ability_index(package=package, army=enemy_army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    cover_record = records_by_name["Purge and Cleanse"]
    replay_payload = cast(dict[str, JsonValue], cover_record.definition.replay_payload)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    clause = rule_ir.clauses[0]
    current_model_ids = (unit.own_models[0].model_instance_id,)
    battlefield = flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()
    attack_sequence = completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        target=target_unit,
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )

    assert (
        CatalogPostShootHitTargetStatusRuntime(
            ability_indexes_by_player_id={
                army.player_id: player_index,
                enemy_army.player_id: enemy_player_index,
            },
            armies=(army, enemy_army),
        )
        .bindings()[0]
        .hook_id
        == CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID
    )
    assert (
        CatalogPostShootHitTargetStatusRuntime(
            ability_indexes_by_player_id={
                army.player_id: AbilityCatalogIndex.from_records(()),
                enemy_army.player_id: AbilityCatalogIndex.from_records(()),
            },
            armies=(army, enemy_army),
        ).bindings()
        == ()
    )
    assert (
        _available_catalog_post_shoot_hit_target_status_groups(
            ability_indexes_by_player_id={army.player_id: player_index},
            armies=(army, enemy_army),
            context=context,
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="requires context"):
        _available_catalog_post_shoot_hit_target_status_groups(
            ability_indexes_by_player_id={army.player_id: player_index},
            armies=(army, enemy_army),
            context=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="index is missing player"):
        _available_catalog_post_shoot_hit_target_status_groups(
            ability_indexes_by_player_id={},
            armies=(army, enemy_army),
            context=context,
        )
    with pytest.raises(GameLifecycleError, match="requires an ability record"):
        _catalog_post_shoot_hit_target_status_groups_from_clause(
            context=context,
            record=cast(Any, object()),
            unit=unit,
            current_model_instance_ids=current_model_ids,
            clause=clause,
        )
    with pytest.raises(GameLifecycleError, match="requires a rule clause"):
        _catalog_post_shoot_hit_target_status_groups_from_clause(
            context=context,
            record=cover_record,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            clause=cast(Any, object()),
        )

    def clause_with_trigger_parameter(key: str, value: RuleParameterValue) -> RuleClause:
        assert clause.trigger is not None
        parameters = dict(parameter_payload(clause.trigger.parameters))
        parameters[key] = value
        return replace(
            clause,
            trigger=replace(
                clause.trigger,
                parameters=parameters_from_pairs(
                    tuple(
                        (parameter_key, parameter_value)
                        for parameter_key, parameter_value in parameters.items()
                    )
                ),
            ),
        )

    this_unit_clause = clause_with_trigger_parameter("subject", "this_unit")
    assert _post_shoot_status_source_model_ids(
        record=cover_record,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        clause=this_unit_clause,
        attack_sequence=attack_sequence,
    ) == (None,)
    with pytest.raises(GameLifecycleError, match="requires an ability record"):
        _post_shoot_status_source_model_ids(
            record=cast(Any, object()),
            unit=unit,
            current_model_instance_ids=current_model_ids,
            clause=clause,
            attack_sequence=attack_sequence,
        )
    with pytest.raises(GameLifecycleError, match="requires a triggered clause"):
        _post_shoot_status_source_model_ids(
            record=cover_record,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            clause=replace(clause, trigger=None),
            attack_sequence=attack_sequence,
        )
    with pytest.raises(GameLifecycleError, match="requires an AttackSequence"):
        _post_shoot_status_source_model_ids(
            record=cover_record,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            clause=clause,
            attack_sequence=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="unsupported subject"):
        _post_shoot_status_source_model_ids(
            record=cover_record,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            clause=clause_with_trigger_parameter("subject", "unsupported_subject"),
            attack_sequence=attack_sequence,
        )
    with pytest.raises(GameLifecycleError, match="requires an ability record"):
        _post_shoot_hit_target_status_option_id(
            record=cast(Any, object()),
            unit=unit,
            clause=clause,
            effect_index=0,
            status="benefit_of_cover",
            source_model_instance_id=unit.own_models[0].model_instance_id,
            target_unit_instance_id=target_unit.unit_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="requires a rule clause"):
        _post_shoot_hit_target_status_option_id(
            record=cover_record,
            unit=unit,
            clause=cast(Any, object()),
            effect_index=0,
            status="benefit_of_cover",
            source_model_instance_id=unit.own_models[0].model_instance_id,
            target_unit_instance_id=target_unit.unit_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="effect_index must be non-negative"):
        _post_shoot_hit_target_status_option_id(
            record=cover_record,
            unit=unit,
            clause=clause,
            effect_index=-1,
            status="benefit_of_cover",
            source_model_instance_id=unit.own_models[0].model_instance_id,
            target_unit_instance_id=target_unit.unit_instance_id,
        )

    assert not _clause_is_supported_post_shoot_hit_target_status_denial(
        clause_with_trigger_parameter("edge", "during")
    )
    assert not _clause_is_supported_post_shoot_hit_target_status_denial(
        clause_with_trigger_parameter("subject", "unsupported_subject")
    )
    assert not _clause_is_supported_post_shoot_hit_target_status_denial(
        replace(clause, duration=None)
    )
    assert not _clause_is_supported_post_shoot_hit_target_status_denial(
        replace(
            clause,
            target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=clause.source_span),
        )
    )
    assert not _effect_is_supported_status_denial(
        effect(RuleEffectKind.GRANT_ABILITY, ability="can_advance_and_charge")
    )
    with pytest.raises(GameLifecycleError, match="requires RuleClause values"):
        _clause_is_supported_post_shoot_hit_target_status_denial(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec values"):
        _effect_is_supported_status_denial(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="selected payload must be an object"):
        _post_shoot_hit_target_status_selected_payload({})
    with pytest.raises(GameLifecycleError, match="payload requires attack_sequence"):
        _post_shoot_hit_target_status_attack_sequence_from_payload({})
    with pytest.raises(GameLifecycleError, match="requires option values"):
        _validate_post_shoot_hit_target_status_option(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="requires a field name"):
        _validate_non_empty_text("", "Benefit of Cover")
    with pytest.raises(GameLifecycleError, match="status_label must be a string"):
        _validate_non_empty_text("status_label", 1)
    with pytest.raises(GameLifecycleError, match="status_label must not be empty"):
        _validate_non_empty_text("status_label", " ")

    with pytest.raises(GameLifecycleError, match="wargear_ids must be a tuple"):
        successful_hit_target_unit_ids_for_sequence(
            decisions=decisions,
            sequence=attack_sequence,
            wargear_ids=cast(Any, ["bolt-of-change"]),
        )
    with pytest.raises(GameLifecycleError, match="wargear_ids must not duplicate IDs"):
        successful_hit_target_unit_ids_for_sequence(
            decisions=decisions,
            sequence=attack_sequence,
            wargear_ids=("bolt-of-change", "bolt-of-change"),
        )

    def assert_hit_lookup_raises(payload: JsonValue, match: str) -> None:
        lookup_decisions = DecisionController()
        lookup_decisions.event_log.append("attack_sequence_step", payload)
        with pytest.raises(GameLifecycleError, match=match):
            successful_hit_target_unit_ids_for_sequence(
                decisions=lookup_decisions,
                sequence=attack_sequence,
            )

    assert_hit_lookup_raises("not-an-object", "payload must be an object")
    assert_hit_lookup_raises(
        {
            "sequence_id": attack_sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": "not-an-object",
        },
        "hit payload must be an object",
    )
    assert_hit_lookup_raises(
        {
            "sequence_id": attack_sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": "zero",
            "payload": {"successful": True},
        },
        "pool_index must be an int",
    )
    assert_hit_lookup_raises(
        {
            "sequence_id": attack_sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 99,
            "payload": {"successful": True},
        },
        "pool_index is out of range",
    )
