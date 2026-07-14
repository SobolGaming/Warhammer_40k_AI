from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.engine import (
    catalog_contextual_status_consumption as catalog_contextual_module,
)
from warhammer40k_core.engine import (
    catalog_tracked_target_runtime as catalog_tracked_target_runtime_module,
)
from warhammer40k_core.engine import tracked_targets as tracked_targets_module
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_round_hooks import (
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockForcedTestContext,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.catalog_battle_shock_runtime import (
    CATALOG_BATTLE_SHOCK_FAILED_HEAL_EVENT,
    CATALOG_BATTLE_SHOCK_FAILED_HEAL_ROLL_TYPE,
    CatalogBattleShockRerollRuntime,
    catalog_battle_shock_hook_bindings,
    catalog_forced_battle_shock_unit_ids,
    resolve_catalog_battle_shock_failed_heal,
)
from warhammer40k_core.engine.catalog_contextual_status_consumption import (
    CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
    CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
    CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
    CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
    CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID,
    consumer_ids_for_clause,
    hook_ids_for_effect,
)
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_clauses_from_record
from warhammer40k_core.engine.catalog_shadow_form_runtime import (
    CATALOG_SHADOW_FORM_SELECTED_EVENT,
    CATALOG_SHADOW_FORM_SELECTION_EFFECT_KIND,
    CATALOG_SHADOW_FORM_SUBMISSION_KIND,
    CatalogShadowFormRuntime,
)
from warhammer40k_core.engine.catalog_tracked_target_runtime import CatalogTrackedTargetRuntime
from warhammer40k_core.engine.command_points import initial_command_point_ledgers
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import EventLog, JsonValue, canonical_json
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.scoring import initial_victory_point_ledgers
from warhammer40k_core.engine.source_backed_rerolls import (
    SourceBackedRerollPermissionContext,
    source_backed_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.tracked_targets import (
    SELECT_TRACKED_TARGET_DECISION_TYPE,
    TrackedTargetOwnerScope,
    TrackedTargetRecord,
    TrackedTargetRole,
    apply_select_tracked_target_decision,
    build_select_tracked_target_request,
    invalid_select_tracked_target_status,
    tracked_target_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext, StartingStrengthRecord
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import RuleClause, RuleEffectKind, RuleEffectSpec, RuleIR
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_datasheet_ir_support_2026_27 as belakor_ir_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)

PREY_TARGET_TEXT = (
    "At the start of the first battle round, select one enemy unit to be this model's "
    "prey. Each time a model in this model's unit makes a melee attack that targets "
    "its prey, you can re-roll the Wound roll. Each time this model's prey is "
    "destroyed, select one new enemy unit to be this model's prey."
)
SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)
MIXED_QUARRY_TARGET_TEXT = (
    "At the start of the first battle round, select one enemy unit to be this model's "
    "quarry. Each time this model makes a melee attack that targets its quarry, "
    "re-roll Hit rolls. Each time this model makes a ranged attack that targets its "
    "quarry, re-roll Wound rolls."
)


def test_tracked_target_initial_selection_request_payload_is_json_safe() -> None:
    state = _battle_state_with_scenario(beta_unit_count=2)
    record = _tracked_target_catalog_record(trigger_kind=TimingTriggerKind.START_BATTLE_ROUND)
    runtime = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records((record,)),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )
    decisions = DecisionController()

    bindings = runtime.battle_round_start_bindings()
    request = runtime.battle_round_start_request(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )

    assert len(bindings) == 1
    assert request is not None
    assert request.decision_type == SELECT_TRACKED_TARGET_DECISION_TYPE
    canonical_json(request.payload)
    assert [option.option_id for option in request.options] == sorted(
        unit.unit_instance_id for unit in state.army_definitions[1].units
    )
    assert isinstance(request.payload, dict)
    assert request.payload["submission_kind"] == SELECT_TRACKED_TARGET_DECISION_TYPE
    assert request.payload["source_rule_id"] == record.definition.source_id
    assert request.payload["supported_attack_roll_pairs"] == [
        {"attack_kind": "melee", "roll_type": "attack_sequence.wound"}
    ]
    assert request.payload["supported_attack_kinds"] == ["melee"]
    assert request.payload["supported_roll_types"] == ["attack_sequence.wound"]


def test_tracked_target_selection_preserves_attack_roll_pair_correlation() -> None:
    state = _battle_state_with_scenario(beta_unit_count=2)
    record = _tracked_target_catalog_record(
        trigger_kind=TimingTriggerKind.START_BATTLE_ROUND,
        raw_text=MIXED_QUARRY_TARGET_TEXT,
        source_id="rule:mixed-quarry",
    )
    runtime = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records((record,)),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )

    request = runtime.battle_round_start_request(
        BattleRoundStartRequestContext(state=state, decisions=DecisionController())
    )

    assert request is not None
    assert isinstance(request.payload, dict)
    assert request.payload["supported_attack_roll_pairs"] == [
        {"attack_kind": "melee", "roll_type": "attack_sequence.hit"},
        {"attack_kind": "ranged", "roll_type": "attack_sequence.wound"},
    ]
    assert request.payload["supported_attack_kinds"] == ["melee", "ranged"]
    assert request.payload["supported_roll_types"] == [
        "attack_sequence.hit",
        "attack_sequence.wound",
    ]


def test_tracked_target_runtime_empty_indexes_have_no_hooks() -> None:
    state = _battle_state_with_scenario()
    runtime = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records(()),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )

    assert runtime.battle_round_start_bindings() == ()
    assert runtime.unit_destroyed_bindings() == ()


def test_catalog_shadow_form_runtime_records_selection_and_event() -> None:
    state = _battle_state_with_scenario()
    runtime = CatalogShadowFormRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records(_belakor_shadow_form_records()),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )
    decisions = DecisionController()

    bindings = runtime.battle_round_start_bindings()
    request = runtime.battle_round_start_request(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )

    assert len(bindings) == 1
    assert request is not None
    assert request.actor_id == "player-a"
    assert isinstance(request.payload, dict)
    assert request.payload["submission_kind"] == CATALOG_SHADOW_FORM_SUBMISSION_KIND
    assert request.payload["source_rule_id"] == belakor_ir_source.BELAKOR_SHADOW_FORM_SOURCE_ID
    selected_option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict)
        and option.payload["selected_shadow_form_source_id"]
        == belakor_ir_source.BELAKOR_WREATHED_IN_SHADOWS_SOURCE_ID
    )
    result = DecisionResult.for_request(
        result_id="result:shadow-form",
        request=request,
        selected_option_id=selected_option.option_id,
    )

    applied = runtime.apply_battle_round_start_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert applied
    selection_effects = [
        effect
        for effect in state.persisting_effects_for_unit(
            state.army_definitions[0].units[0].unit_instance_id
        )
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == CATALOG_SHADOW_FORM_SELECTION_EFFECT_KIND
    ]
    assert len(selection_effects) == 1
    assert any(
        event.event_type == CATALOG_SHADOW_FORM_SELECTED_EVENT
        for event in decisions.event_log.records
    )
    assert (
        runtime.battle_round_start_request(
            BattleRoundStartRequestContext(state=state, decisions=decisions)
        )
        is None
    )


def test_catalog_shadow_form_selection_rejects_adapter_drift() -> None:
    state = _battle_state_with_scenario()
    runtime = CatalogShadowFormRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records(_belakor_shadow_form_records()),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )
    decisions = DecisionController()
    request = runtime.battle_round_start_request(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    selected_option = request.options[0]
    result = DecisionResult.for_request(
        result_id="result:shadow-form-drift",
        request=request,
        selected_option_id=selected_option.option_id,
    )

    assert not runtime.apply_battle_round_start_result(
        BattleRoundStartResultContext(
            state=state,
            decisions=decisions,
            request=replace(request, decision_type="other_decision_type"),
            result=result,
        )
    )
    with pytest.raises(GameLifecycleError, match="requires an actor"):
        runtime.apply_battle_round_start_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=replace(result, actor_id=None),
            )
        )
    with pytest.raises(GameLifecycleError, match="payload drift"):
        runtime.apply_battle_round_start_result(
            BattleRoundStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=replace(result, payload={"drift": True}),
            )
        )


def test_catalog_contextual_status_consumption_classifies_belakor_rule_ir() -> None:
    consumer_ids: set[str] = set()
    hook_ids: set[str] = set()
    for row_id in (
        belakor_ir_source.BELAKOR_DARK_MASTER_ROW_ID,
        belakor_ir_source.BELAKOR_SHADOW_FORM_ROW_ID,
        belakor_ir_source.BELAKOR_WREATHED_IN_SHADOWS_ROW_ID,
        belakor_ir_source.BELAKOR_PALL_OF_DESPAIR_ROW_ID,
        belakor_ir_source.BELAKOR_SHADOW_LORD_ROW_ID,
    ):
        rule_ir = _belakor_rule_ir(row_id)
        for clause in rule_ir.clauses:
            consumer_ids.update(consumer_ids_for_clause(clause))
            for effect in clause.effects:
                hook_ids.update(hook_ids_for_effect(effect))

    assert {
        CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
        CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
        CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
        CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
        CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID,
    } <= consumer_ids
    assert {
        CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
        CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
        CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
        CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
        CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID,
    } <= hook_ids
    with pytest.raises(GameLifecycleError, match="RuleClause"):
        consumer_ids_for_clause(cast(RuleClause, object()))
    with pytest.raises(GameLifecycleError, match="RuleEffectSpec"):
        hook_ids_for_effect(cast(RuleEffectSpec, object()))


def test_catalog_contextual_status_effect_classifiers_are_fail_fast() -> None:
    bad_effect = cast(RuleEffectSpec, object())
    with pytest.raises(GameLifecycleError, match="RuleEffectSpec"):
        catalog_contextual_module._effect_is_shadow_of_chaos_status(bad_effect)  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="RuleEffectSpec"):
        catalog_contextual_module._effect_is_shadow_form_choice(bad_effect)  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="RuleEffectSpec"):
        catalog_contextual_module._effect_is_shooting_target_range_restriction(bad_effect)  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="RuleEffectSpec"):
        catalog_contextual_module._effect_is_battle_shock_forced_test(bad_effect)  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="RuleEffectSpec"):
        catalog_contextual_module._effect_is_battle_shock_failed_heal(bad_effect)  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="RuleEffectSpec"):
        catalog_contextual_module._attack_roll_reroll_consumer_id_for_effect(bad_effect)  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="RuleClause"):
        catalog_contextual_module.aura_attack_roll_reroll_consumer_ids_for_clause(
            cast(RuleClause, object())
        )


def test_catalog_battle_shock_runtime_detects_forced_test_effects() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    target_unit = state.army_definitions[1].units[0]
    pall_rule_ir = _belakor_rule_ir(belakor_ir_source.BELAKOR_PALL_OF_DESPAIR_ROW_ID)
    forced_effect = next(
        effect
        for clause in pall_rule_ir.clauses
        for effect in clause.effects
        if effect.kind is RuleEffectKind.SET_CONTEXTUAL_STATUS
    )
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="effect:forced-battle-shock",
            source_rule_id=pall_rule_ir.source_id,
            owner_player_id="player-a",
            target_unit_instance_ids=(target_unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
            effect_payload=cast(
                JsonValue,
                {
                    "effect_kind": GENERIC_RULE_EFFECT_KIND,
                    "effect": forced_effect.to_payload(),
                    "context": {"source_unit_instance_id": source_unit.unit_instance_id},
                },
            ),
        )
    )
    records = (
        _belakor_catalog_record(
            row_id=belakor_ir_source.BELAKOR_PALL_OF_DESPAIR_ROW_ID,
            ability_id="ability:pall-of-despair",
            name="Pall of Despair",
        ),
    )
    indexes = {
        "player-a": AbilityCatalogIndex.from_records(records),
        "player-b": AbilityCatalogIndex.from_records(()),
    }

    bindings = catalog_battle_shock_hook_bindings(
        ability_indexes_by_player_id=indexes,
        armies=tuple(state.army_definitions),
    )
    forced_ids = catalog_forced_battle_shock_unit_ids(
        BattleShockForcedTestContext(
            state=state,
            active_player_id="player-b",
            phase=BattlePhase.COMMAND,
            phase_start_battle_shocked_unit_ids=(),
        )
    )

    assert [binding.hook_id for binding in bindings] == [
        CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
        CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
    ]
    assert forced_ids == (target_unit.unit_instance_id,)
    assert (
        catalog_forced_battle_shock_unit_ids(
            BattleShockForcedTestContext(
                state=state,
                active_player_id="player-b",
                phase=BattlePhase.SHOOTING,
                phase_start_battle_shocked_unit_ids=(),
            )
        )
        == ()
    )


def test_catalog_battle_shock_failed_heal_resolves_generic_rule_ir_effect() -> None:
    state = _battle_state_with_scenario()
    decisions = DecisionController()
    source_unit = state.army_definitions[0].units[0]
    target_unit = state.army_definitions[1].units[0]
    pall_rule_ir = _belakor_rule_ir(belakor_ir_source.BELAKOR_PALL_OF_DESPAIR_ROW_ID)
    heal_effect = next(
        effect
        for clause in pall_rule_ir.clauses
        for effect in clause.effects
        if effect.kind is RuleEffectKind.RESTORE_LOST_WOUNDS
    )
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="effect:failed-battle-shock-heal",
            source_rule_id=pall_rule_ir.source_id,
            owner_player_id="player-a",
            target_unit_instance_ids=(target_unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
            effect_payload=cast(
                JsonValue,
                {
                    "effect_kind": GENERIC_RULE_EFFECT_KIND,
                    "effect": heal_effect.to_payload(),
                    "context": {"source_unit_instance_id": source_unit.unit_instance_id},
                },
            ),
        )
    )
    below_half_context = BelowHalfStrengthContext.from_unit(
        player_id="player-b",
        unit=target_unit,
        starting_strength=StartingStrengthRecord.from_unit(
            player_id="player-b",
            unit=target_unit,
        ),
        current_model_ids=target_unit.own_model_ids(),
    )
    request = BattleShockTestRequest.for_unit(
        request_id="request:failed-battle-shock",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-b",
        unit_instance_id=target_unit.unit_instance_id,
        reason=BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED,
        leadership_target=6,
        below_half_strength_context=below_half_context,
    )
    result = BattleShockResult.from_roll_state(
        result_id="result:failed-battle-shock",
        request=request,
        roll_state=DiceRollManager("catalog-battle-shock-result").roll_fixed(
            request.spec,
            [1, 1],
        ),
    )
    dice_manager = DiceRollManager(state.game_id, event_log=decisions.event_log)

    resolve_catalog_battle_shock_failed_heal(
        BattleShockOutcomeContext(
            state=state,
            decisions=decisions,
            dice_manager=dice_manager,
            result=result,
            active_player_id="player-b",
            phase=BattlePhase.COMMAND,
            auto_passed=False,
            phase_start_battle_shocked_unit_ids=(),
        )
    )

    event_types = [event.event_type for event in decisions.event_log.records]
    assert CATALOG_BATTLE_SHOCK_FAILED_HEAL_EVENT in event_types
    saw_heal_roll = False
    for event in decisions.event_log.records:
        if event.event_type != "dice_rolled":
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            continue
        spec = payload.get("spec")
        if not isinstance(spec, dict):
            continue
        if spec.get("roll_type") == CATALOG_BATTLE_SHOCK_FAILED_HEAL_ROLL_TYPE:
            saw_heal_roll = True
    assert saw_heal_roll
    catalog_event = next(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_BATTLE_SHOCK_FAILED_HEAL_EVENT
    )
    assert isinstance(catalog_event.payload, dict)
    assert catalog_event.payload["source_unit_instance_id"] == source_unit.unit_instance_id
    assert catalog_event.payload["target_unit_instance_id"] == target_unit.unit_instance_id


def test_catalog_battle_shock_runtime_noops_and_fail_fast_paths() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    target_unit = state.army_definitions[1].units[0]
    pall_rule_ir = _belakor_rule_ir(belakor_ir_source.BELAKOR_PALL_OF_DESPAIR_ROW_ID)
    forced_effect = next(
        effect
        for clause in pall_rule_ir.clauses
        for effect in clause.effects
        if effect.kind is RuleEffectKind.SET_CONTEXTUAL_STATUS
    )
    heal_effect = next(
        effect
        for clause in pall_rule_ir.clauses
        for effect in clause.effects
        if effect.kind is RuleEffectKind.RESTORE_LOST_WOUNDS
    )
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="effect:own-forced-battle-shock",
            source_rule_id=pall_rule_ir.source_id,
            owner_player_id="player-b",
            target_unit_instance_ids=(target_unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
            effect_payload=cast(
                JsonValue,
                {
                    "effect_kind": GENERIC_RULE_EFFECT_KIND,
                    "effect": forced_effect.to_payload(),
                    "context": {"source_unit_instance_id": source_unit.unit_instance_id},
                },
            ),
        )
    )
    assert (
        catalog_forced_battle_shock_unit_ids(
            BattleShockForcedTestContext(
                state=state,
                active_player_id="player-b",
                phase=BattlePhase.COMMAND,
                phase_start_battle_shocked_unit_ids=(),
            )
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="player_id is not in this game"):
        catalog_forced_battle_shock_unit_ids(
            BattleShockForcedTestContext(
                state=state,
                active_player_id="player-missing",
                phase=BattlePhase.COMMAND,
                phase_start_battle_shocked_unit_ids=(),
            )
        )

    records = (
        _belakor_catalog_record(
            row_id=belakor_ir_source.BELAKOR_PALL_OF_DESPAIR_ROW_ID,
            ability_id="ability:pall-of-despair",
            name="Pall of Despair",
        ),
    )
    with pytest.raises(GameLifecycleError, match="armies are invalid"):
        CatalogBattleShockRerollRuntime(
            ability_indexes_by_player_id={
                "player-a": AbilityCatalogIndex.from_records(records),
            },
            armies=(cast(ArmyDefinition, object()),),
        )

    state.record_persisting_effect(
        PersistingEffect(
            effect_id="effect:failed-battle-shock-own-heal",
            source_rule_id=pall_rule_ir.source_id,
            owner_player_id="player-b",
            target_unit_instance_ids=(target_unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
            effect_payload=cast(
                JsonValue,
                {
                    "effect_kind": GENERIC_RULE_EFFECT_KIND,
                    "effect": heal_effect.to_payload(),
                    "context": {"source_unit_instance_id": source_unit.unit_instance_id},
                },
            ),
        )
    )
    request = BattleShockTestRequest.for_unit(
        request_id="request:battle-shock-noop",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-b",
        unit_instance_id=target_unit.unit_instance_id,
        reason=BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED,
        leadership_target=6,
        below_half_strength_context=BelowHalfStrengthContext.from_unit(
            player_id="player-b",
            unit=target_unit,
            starting_strength=StartingStrengthRecord.from_unit(
                player_id="player-b",
                unit=target_unit,
            ),
            current_model_ids=target_unit.own_model_ids(),
        ),
    )
    failed_result = BattleShockResult.from_roll_state(
        result_id="result:battle-shock-noop-failed",
        request=request,
        roll_state=DiceRollManager("catalog-battle-shock-noop-failed").roll_fixed(
            request.spec,
            [1, 1],
        ),
    )
    passed_result = BattleShockResult.from_roll_state(
        result_id="result:battle-shock-noop-passed",
        request=request,
        roll_state=DiceRollManager("catalog-battle-shock-noop-passed").roll_fixed(
            request.spec,
            [6, 6],
        ),
    )
    decisions = DecisionController()
    base_context = BattleShockOutcomeContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        result=failed_result,
        active_player_id="player-b",
        phase=BattlePhase.SHOOTING,
        auto_passed=False,
        phase_start_battle_shocked_unit_ids=(),
    )

    resolve_catalog_battle_shock_failed_heal(base_context)
    resolve_catalog_battle_shock_failed_heal(replace(base_context, phase=BattlePhase.COMMAND))
    resolve_catalog_battle_shock_failed_heal(replace(base_context, result=passed_result))

    assert all(
        event.event_type != CATALOG_BATTLE_SHOCK_FAILED_HEAL_EVENT
        for event in decisions.event_log.records
    )


def test_tracked_target_runtime_fail_fast_and_empty_selection_paths() -> None:
    state = _battle_state_with_scenario()
    record = _tracked_target_catalog_record(trigger_kind=TimingTriggerKind.START_BATTLE_ROUND)
    decisions = DecisionController()
    runtime_missing_index = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={"player-b": AbilityCatalogIndex.from_records(())},
        armies=tuple(state.army_definitions),
    )

    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        runtime_missing_index.battle_round_start_request(
            BattleRoundStartRequestContext(state=state, decisions=decisions)
        )

    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    assert state.battlefield_state is not None
    no_source_models_state = _battle_state_with_scenario()
    assert no_source_models_state.battlefield_state is not None
    no_source_models_state.battlefield_state = (
        no_source_models_state.battlefield_state.with_removed_models(source_unit.own_model_ids())
    )
    runtime = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records((record,)),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(no_source_models_state.army_definitions),
    )
    assert (
        runtime.battle_round_start_request(
            BattleRoundStartRequestContext(state=no_source_models_state, decisions=decisions)
        )
        is None
    )

    active_state = _battle_state_with_scenario()
    active_source_unit = active_state.army_definitions[0].units[0]
    active_target_unit = active_state.army_definitions[1].units[0]
    _record_selection(
        state=active_state,
        source_unit_instance_id=active_source_unit.unit_instance_id,
        source_model_instance_id=active_source_unit.own_models[0].model_instance_id,
        target_unit_instance_id=active_target_unit.unit_instance_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
    )
    assert (
        build_select_tracked_target_request(
            state=active_state,
            actor_player_id="player-a",
            source_rule_id="rule:this_model",
            source_ability_id="ability:prey",
            source_clause_id="clause:select",
            source_effect_index=0,
            source_unit_instance_id=active_source_unit.unit_instance_id,
            source_model_instance_id=active_source_unit.own_models[0].model_instance_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
            supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
            target_allegiance="enemy",
            target_scope="enemy_unit",
            replacement=False,
        )
        is None
    )

    no_targets_state = _battle_state_with_scenario()
    beta = no_targets_state.army_definitions[1].units[0]
    assert no_targets_state.battlefield_state is not None
    no_targets_state.battlefield_state = no_targets_state.battlefield_state.with_removed_models(
        beta.own_model_ids()
    )
    assert (
        build_select_tracked_target_request(
            state=no_targets_state,
            actor_player_id="player-a",
            source_rule_id="rule:prey",
            source_ability_id="ability:prey",
            source_clause_id="clause:select",
            source_effect_index=0,
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
            supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
            target_allegiance="enemy",
            target_scope="enemy_unit",
            replacement=False,
        )
        is None
    )

    with pytest.raises(GameLifecycleError, match="allegiance and target_scope drift"):
        build_select_tracked_target_request(
            state=state,
            actor_player_id="player-a",
            source_rule_id="rule:prey",
            source_ability_id="ability:prey",
            source_clause_id="clause:select",
            source_effect_index=0,
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
            supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
            target_allegiance="enemy",
            target_scope="friendly_unit",
            replacement=False,
        )
    with pytest.raises(GameLifecycleError, match="replacement must be a bool"):
        build_select_tracked_target_request(
            state=state,
            actor_player_id="player-a",
            source_rule_id="rule:prey",
            source_ability_id="ability:prey",
            source_clause_id="clause:select",
            source_effect_index=0,
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
            supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
            target_allegiance="enemy",
            target_scope="enemy_unit",
            replacement=cast(bool, "yes"),
        )


def test_tracked_target_selection_records_active_target_and_round_trips() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id

    request = build_select_tracked_target_request(
        state=state,
        actor_player_id="player-a",
        source_rule_id="rule:prey",
        source_ability_id="ability:prey",
        source_clause_id="clause:select",
        source_effect_index=0,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
        role=TrackedTargetRole.PREY,
        supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
        target_allegiance="enemy",
        target_scope="enemy_unit",
        replacement=False,
    )

    assert request is not None
    assert request.decision_type == SELECT_TRACKED_TARGET_DECISION_TYPE
    canonical_json(request.payload)
    result = DecisionResult.for_request(
        result_id="result:prey",
        request=request,
        selected_option_id=target_unit_id,
    )
    record = apply_select_tracked_target_decision(
        state=state,
        request=request,
        result=result,
        decisions_event_log=EventLog(),
    )

    assert record.target_unit_instance_id == target_unit_id
    assert (
        state.active_tracked_target_for(
            source_rule_id="rule:prey",
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
        )
        == record
    )
    assert TrackedTargetRecord.from_payload(record.to_payload()) == record


def test_tracked_target_selection_rejects_non_option_before_mutation() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    request = build_select_tracked_target_request(
        state=state,
        actor_player_id="player-a",
        source_rule_id="rule:prey",
        source_ability_id="ability:prey",
        source_clause_id="clause:select",
        source_effect_index=0,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
        role=TrackedTargetRole.PREY,
        supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
        target_allegiance="enemy",
        target_scope="enemy_unit",
        replacement=False,
    )
    assert request is not None
    result = DecisionResult(
        result_id="result:bad",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="unit:not-an-option",
        payload=request.options[0].payload,
    )

    status = invalid_select_tracked_target_status(
        state=state,
        request=request,
        result=result,
    )

    assert status is not None
    assert state.tracked_target_records == []


def test_tracked_target_invalid_status_accepts_valid_and_rejects_stale_targets() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    target_unit = state.army_definitions[1].units[0]
    request = build_select_tracked_target_request(
        state=state,
        actor_player_id="player-a",
        source_rule_id="rule:prey",
        source_ability_id="ability:prey",
        source_clause_id="clause:select",
        source_effect_index=0,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
        role=TrackedTargetRole.PREY,
        supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
        target_allegiance="enemy",
        target_scope="enemy_unit",
        replacement=False,
    )
    assert request is not None
    result = DecisionResult.for_request(
        result_id="result:valid",
        request=request,
        selected_option_id=target_unit.unit_instance_id,
    )

    assert invalid_select_tracked_target_status(state=state, request=request, result=result) is None

    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        target_unit.own_model_ids()
    )
    status = invalid_select_tracked_target_status(state=state, request=request, result=result)

    assert status is not None
    status_payload = cast(dict[str, JsonValue], status.payload)
    assert status_payload["invalid_reason"] == "selected_target_no_longer_legal"


def test_tracked_target_reroll_requires_active_target_and_matching_model_scope() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    other_model_id = source_unit.own_models[1].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id
    _record_selection(
        state=state,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model_id,
        target_unit_instance_id=target_unit_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
    )

    assert (
        tracked_target_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=source_model_id,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
            attack_kind="melee",
            target_unit_instance_id=target_unit_id,
        )
        is not None
    )
    assert (
        tracked_target_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=other_model_id,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
            attack_kind="melee",
            target_unit_instance_id=target_unit_id,
        )
        is None
    )
    assert (
        tracked_target_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=source_model_id,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
            attack_kind="melee",
            target_unit_instance_id=source_unit.unit_instance_id,
        )
        is None
    )


def test_tracked_target_unit_scope_applies_to_other_models_in_unit() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    other_model_id = source_unit.own_models[1].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id
    _record_selection(
        state=state,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=None,
        target_unit_instance_id=target_unit_id,
        owner_scope=TrackedTargetOwnerScope.THIS_UNIT,
    )

    context = tracked_target_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=source_unit.unit_instance_id,
        model_instance_id=other_model_id,
        roll_type="attack_sequence.wound",
        timing_window="attack_sequence.wound",
        attack_kind="melee",
        target_unit_instance_id=target_unit_id,
    )

    assert context is not None
    assert context.source_payload["owner_scope"] == "this_unit"


def test_tracked_target_quarry_reroll_applies_to_hit_and_wound_rolls() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id
    state.record_tracked_target(
        TrackedTargetRecord(
            record_id="record:quarry",
            source_rule_id="rule:quarry",
            source_ability_id="ability:quarry",
            source_clause_id="clause:select",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.QUARRY,
            supported_attack_roll_pairs=(
                ("melee", "attack_sequence.hit"),
                ("melee", "attack_sequence.wound"),
            ),
            target_unit_instance_id=target_unit_id,
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id="request:quarry",
            selection_result_id="result:quarry",
            active=True,
        )
    )

    hit_context = tracked_target_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=source_unit.unit_instance_id,
        model_instance_id=source_model_id,
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
        attack_kind="melee",
        target_unit_instance_id=target_unit_id,
    )
    wound_context = tracked_target_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=source_unit.unit_instance_id,
        model_instance_id=source_model_id,
        roll_type="attack_sequence.wound",
        timing_window="attack_sequence.wound",
        attack_kind="melee",
        target_unit_instance_id=target_unit_id,
    )

    assert hit_context is not None
    assert wound_context is not None


def test_tracked_target_supported_roll_types_drive_rerolls_not_role_label() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id
    state.record_tracked_target(
        TrackedTargetRecord(
            record_id="record:quarry-wound-only",
            source_rule_id="rule:quarry",
            source_ability_id="ability:quarry",
            source_clause_id="clause:select",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.QUARRY,
            supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
            target_unit_instance_id=target_unit_id,
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id="request:quarry-wound-only",
            selection_result_id="result:quarry-wound-only",
            active=True,
        )
    )

    assert (
        tracked_target_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=source_model_id,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
            attack_kind="melee",
            target_unit_instance_id=target_unit_id,
        )
        is None
    )
    assert (
        tracked_target_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=source_model_id,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
            attack_kind="melee",
            target_unit_instance_id=target_unit_id,
        )
        is not None
    )


def test_tracked_target_supported_attack_kinds_gate_source_backed_rerolls() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id
    state.record_tracked_target(
        TrackedTargetRecord(
            record_id="record:melee-wound-only",
            source_rule_id="rule:melee-quarry",
            source_ability_id="ability:melee-quarry",
            source_clause_id="clause:select",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.QUARRY,
            supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
            target_unit_instance_id=target_unit_id,
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id="request:melee-wound-only",
            selection_result_id="result:melee-wound-only",
            active=True,
        )
    )

    assert (
        source_backed_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=source_model_id,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
            attack_kind="ranged",
            target_unit_instance_id=target_unit_id,
        )
        is None
    )
    melee_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=source_unit.unit_instance_id,
        model_instance_id=source_model_id,
        roll_type="attack_sequence.wound",
        timing_window="attack_sequence.wound",
        attack_kind="melee",
        target_unit_instance_id=target_unit_id,
    )
    assert melee_context is not None
    assert melee_context.source_payload["supported_attack_kinds"] == ["melee"]

    ranged_state = _battle_state_with_scenario()
    ranged_source_unit = ranged_state.army_definitions[0].units[0]
    ranged_source_model_id = ranged_source_unit.own_models[0].model_instance_id
    ranged_target_unit_id = ranged_state.army_definitions[1].units[0].unit_instance_id
    ranged_state.record_tracked_target(
        TrackedTargetRecord(
            record_id="record:ranged-wound-only",
            source_rule_id="rule:ranged-quarry",
            source_ability_id="ability:ranged-quarry",
            source_clause_id="clause:select",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id=ranged_source_unit.unit_instance_id,
            source_model_instance_id=ranged_source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.QUARRY,
            supported_attack_roll_pairs=(("ranged", "attack_sequence.wound"),),
            target_unit_instance_id=ranged_target_unit_id,
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id="request:ranged-wound-only",
            selection_result_id="result:ranged-wound-only",
            active=True,
        )
    )

    assert (
        source_backed_reroll_permission_context_for_unit(
            state=ranged_state,
            player_id="player-a",
            unit_instance_id=ranged_source_unit.unit_instance_id,
            model_instance_id=ranged_source_model_id,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
            attack_kind="melee",
            target_unit_instance_id=ranged_target_unit_id,
        )
        is None
    )
    assert (
        source_backed_reroll_permission_context_for_unit(
            state=ranged_state,
            player_id="player-a",
            unit_instance_id=ranged_source_unit.unit_instance_id,
            model_instance_id=ranged_source_model_id,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
            attack_kind="ranged",
            target_unit_instance_id=ranged_target_unit_id,
        )
        is not None
    )


def test_tracked_target_attack_roll_pairs_do_not_grant_cross_product_rerolls() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id
    state.record_tracked_target(
        TrackedTargetRecord(
            record_id="record:mixed-pairs",
            source_rule_id="rule:mixed-pairs",
            source_ability_id="ability:mixed-pairs",
            source_clause_id="clause:select",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.QUARRY,
            supported_attack_roll_pairs=(
                ("melee", "attack_sequence.hit"),
                ("ranged", "attack_sequence.wound"),
            ),
            target_unit_instance_id=target_unit_id,
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id="request:mixed-pairs",
            selection_result_id="result:mixed-pairs",
            active=True,
        )
    )

    def permission_context(
        *, attack_kind: str, roll_type: str
    ) -> SourceBackedRerollPermissionContext | None:
        return source_backed_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=source_model_id,
            roll_type=roll_type,
            timing_window=roll_type,
            attack_kind=attack_kind,
            target_unit_instance_id=target_unit_id,
        )

    melee_hit_context = permission_context(
        attack_kind="melee",
        roll_type="attack_sequence.hit",
    )
    ranged_wound_context = permission_context(
        attack_kind="ranged",
        roll_type="attack_sequence.wound",
    )

    assert melee_hit_context is not None
    assert melee_hit_context.source_payload["supported_attack_roll_pairs"] == [
        {"attack_kind": "melee", "roll_type": "attack_sequence.hit"},
        {"attack_kind": "ranged", "roll_type": "attack_sequence.wound"},
    ]
    assert ranged_wound_context is not None
    assert permission_context(attack_kind="melee", roll_type="attack_sequence.wound") is None
    assert permission_context(attack_kind="ranged", roll_type="attack_sequence.hit") is None


def test_tracked_target_reroll_rejects_duplicate_internal_permissions() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    target_unit_id = state.army_definitions[1].units[0].unit_instance_id
    _record_selection(
        state=state,
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model_id,
        target_unit_instance_id=target_unit_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
    )
    state.tracked_target_records.append(
        replace(state.tracked_target_records[0], record_id="record:duplicate")
    )

    with pytest.raises(GameLifecycleError, match="Multiple tracked-target reroll permissions"):
        tracked_target_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=source_unit.unit_instance_id,
            model_instance_id=source_model_id,
            roll_type="attack_sequence.wound",
            timing_window="attack_sequence.wound",
            attack_kind="melee",
            target_unit_instance_id=target_unit_id,
        )


def test_tracked_target_defensive_validation_rejects_malformed_records_and_payloads() -> None:
    with pytest.raises(GameLifecycleError, match="require source model"):
        TrackedTargetRecord(
            record_id="record:bad-model-scope",
            source_rule_id="rule:bad",
            source_ability_id="ability:bad",
            source_clause_id="clause:bad",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id="unit-a",
            source_model_instance_id=None,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
            supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
            target_unit_instance_id="unit-b",
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id="request:bad",
            selection_result_id="result:bad",
            active=True,
        )
    with pytest.raises(GameLifecycleError, match="must not store source model"):
        TrackedTargetRecord(
            record_id="record:bad-unit-scope",
            source_rule_id="rule:bad",
            source_ability_id="ability:bad",
            source_clause_id="clause:bad",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id="unit-a",
            source_model_instance_id="model-a",
            owner_scope=TrackedTargetOwnerScope.THIS_UNIT,
            role=TrackedTargetRole.PREY,
            supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
            target_unit_instance_id="unit-b",
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id="request:bad",
            selection_result_id="result:bad",
            active=True,
        )
    malformed_calls = (
        lambda: tracked_targets_module._payload_object([]),  # pyright: ignore[reportPrivateUsage]
        lambda: tracked_targets_module._payload_string(  # pyright: ignore[reportPrivateUsage]
            {},
            key="source_rule_id",
        ),
        lambda: tracked_targets_module._payload_optional_string(  # pyright: ignore[reportPrivateUsage]
            {},
            key="source_model_instance_id",
        ),
        lambda: tracked_targets_module._payload_int(  # pyright: ignore[reportPrivateUsage]
            {},
            key="source_effect_index",
        ),
        lambda: tracked_targets_module._payload_bool(  # pyright: ignore[reportPrivateUsage]
            {"replacement": "yes"},
            key="replacement",
        ),
        lambda: tracked_targets_module._payload_identifier_list(  # pyright: ignore[reportPrivateUsage]
            {"legal_target_unit_ids": "unit-b"},
            key="legal_target_unit_ids",
        ),
        lambda: tracked_targets_module._payload_supported_attack_roll_pairs(  # pyright: ignore[reportPrivateUsage]
            {"supported_attack_roll_pairs": [{"attack_kind": "melee"}]},
            key="supported_attack_roll_pairs",
        ),
        lambda: tracked_targets_module._validate_supported_attack_roll_pairs(  # pyright: ignore[reportPrivateUsage]
            cast(tuple[object, ...], [])
        ),
        lambda: tracked_targets_module._validate_supported_attack_roll_pairs(  # pyright: ignore[reportPrivateUsage]
            ()
        ),
        lambda: tracked_targets_module._validate_supported_attack_roll_pairs(  # pyright: ignore[reportPrivateUsage]
            (("melee",),)
        ),
        lambda: tracked_targets_module._validate_supported_attack_roll_pairs(  # pyright: ignore[reportPrivateUsage]
            (("melee", "attack_sequence.hit"), ("melee", "attack_sequence.hit"))
        ),
        lambda: tracked_targets_module._validate_supported_attack_kinds(  # pyright: ignore[reportPrivateUsage]
            cast(tuple[object, ...], [])
        ),
        lambda: tracked_targets_module._validate_supported_attack_kinds(  # pyright: ignore[reportPrivateUsage]
            ()
        ),
        lambda: tracked_targets_module._validate_supported_attack_kinds(  # pyright: ignore[reportPrivateUsage]
            ("melee", "melee")
        ),
        lambda: tracked_targets_module._validate_supported_roll_types(  # pyright: ignore[reportPrivateUsage]
            cast(tuple[object, ...], [])
        ),
        lambda: tracked_targets_module._validate_supported_roll_types(  # pyright: ignore[reportPrivateUsage]
            ()
        ),
        lambda: tracked_targets_module._validate_supported_roll_types(  # pyright: ignore[reportPrivateUsage]
            ("attack_sequence.hit", "attack_sequence.hit")
        ),
        lambda: tracked_targets_module._role_from_token(1),  # pyright: ignore[reportPrivateUsage]
        lambda: tracked_targets_module._role_from_token(  # pyright: ignore[reportPrivateUsage]
            "unsupported"
        ),
        lambda: tracked_targets_module._owner_scope_from_token(  # pyright: ignore[reportPrivateUsage]
            1
        ),
        lambda: tracked_targets_module._owner_scope_from_token(  # pyright: ignore[reportPrivateUsage]
            "unsupported"
        ),
        lambda: tracked_targets_module._validate_supported_token(  # pyright: ignore[reportPrivateUsage]
            "target_allegiance",
            "neutral",
            supported=("enemy",),
        ),
        lambda: tracked_targets_module._validate_identifier(  # pyright: ignore[reportPrivateUsage]
            "record_id",
            1,
        ),
        lambda: tracked_targets_module._validate_identifier(  # pyright: ignore[reportPrivateUsage]
            "record_id",
            "",
        ),
        lambda: tracked_targets_module._validate_non_negative_int(  # pyright: ignore[reportPrivateUsage]
            "source_effect_index",
            -1,
        ),
        lambda: tracked_targets_module._validate_positive_int(  # pyright: ignore[reportPrivateUsage]
            "selected_battle_round",
            0,
        ),
    )

    for malformed_call in malformed_calls:
        with pytest.raises(GameLifecycleError):
            malformed_call()


def test_tracked_target_runtime_reselection_defensive_paths() -> None:
    state = _battle_state_with_scenario(beta_unit_count=2)
    source_unit = state.army_definitions[0].units[0]
    destroyed_target = state.army_definitions[1].units[0]
    expired = TrackedTargetRecord(
        record_id="tracked:expired",
        source_rule_id="rule:tracked-target",
        source_ability_id="ability:tracked-target",
        source_clause_id="tracked:initial-clause",
        source_effect_index=0,
        owner_player_id="player-a",
        source_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_unit.own_models[0].model_instance_id,
        owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
        role=TrackedTargetRole.PREY,
        supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
        target_unit_instance_id=destroyed_target.unit_instance_id,
        target_allegiance="enemy",
        target_lifecycle="until_destroyed",
        selected_battle_round=1,
        selection_request_id="request:initial",
        selection_result_id="result:initial",
        active=False,
    )
    current_phase = state.current_battle_phase
    assert current_phase is not None
    context = UnitDestroyedContext(
        state=state,
        decisions=DecisionController(),
        completed_phase=current_phase,
        model_destroyed_event_id="event:destroyed-target",
        model_destroyed_payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": current_phase.value,
            "destroying_player_id": "player-a",
            "target_unit_instance_id": destroyed_target.unit_instance_id,
            "model_instance_id": destroyed_target.own_models[0].model_instance_id,
        },
        destroying_player_id="player-a",
        destroyed_unit_instance_id=destroyed_target.unit_instance_id,
        destroyed_player_id="player-b",
    )

    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        catalog_tracked_target_runtime_module._tracked_target_reselection_request(  # pyright: ignore[reportPrivateUsage]
            ability_indexes_by_player_id={},
            armies=tuple(state.army_definitions),
            context=context,
            expired_record=expired,
        )

    no_source_models_state = _battle_state_with_scenario(beta_unit_count=2)
    assert no_source_models_state.battlefield_state is not None
    no_source_models_state.battlefield_state = (
        no_source_models_state.battlefield_state.with_removed_models(source_unit.own_model_ids())
    )
    no_source_context = replace(context, state=no_source_models_state)
    assert (
        catalog_tracked_target_runtime_module._tracked_target_reselection_request(  # pyright: ignore[reportPrivateUsage]
            ability_indexes_by_player_id={
                "player-a": AbilityCatalogIndex.from_records((_tracked_target_catalog_record(),))
            },
            armies=tuple(no_source_models_state.army_definitions),
            context=no_source_context,
            expired_record=expired,
        )
        is None
    )

    owner_drift_expired = replace(
        expired, record_id="tracked:owner-drift", owner_player_id="player-b"
    )
    with pytest.raises(GameLifecycleError, match="owner drift"):
        catalog_tracked_target_runtime_module._tracked_target_reselection_request(  # pyright: ignore[reportPrivateUsage]
            ability_indexes_by_player_id={"player-b": AbilityCatalogIndex.from_records(())},
            armies=tuple(state.army_definitions),
            context=context,
            expired_record=owner_drift_expired,
        )

    record = _tracked_target_catalog_record()
    clause = catalog_rule_clauses_from_record(record)[0]
    with pytest.raises(GameLifecycleError, match="source unit drift"):
        catalog_tracked_target_runtime_module._reselection_request_for_clause(  # pyright: ignore[reportPrivateUsage]
            context=context,
            expired_record=replace(expired, source_unit_instance_id="unit:other"),
            record=record,
            clause=clause,
            unit=source_unit,
            related_records=(record,),
        )
    assert (
        catalog_tracked_target_runtime_module._reselection_request_for_clause(  # pyright: ignore[reportPrivateUsage]
            context=context,
            expired_record=replace(expired, role=TrackedTargetRole.QUARRY),
            record=record,
            clause=clause,
            unit=source_unit,
            related_records=(record,),
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="could not find source unit"):
        catalog_tracked_target_runtime_module._army_and_unit_for_unit_id(  # pyright: ignore[reportPrivateUsage]
            armies=tuple(state.army_definitions),
            unit_instance_id="unit:missing",
        )


def test_tracked_target_destroyed_target_expires_and_requests_reselection() -> None:
    state = _battle_state_with_scenario(beta_unit_count=2)
    source_unit = state.army_definitions[0].units[0]
    source_model_id = source_unit.own_models[0].model_instance_id
    destroyed_target = state.army_definitions[1].units[0]
    replacement_target = state.army_definitions[1].units[1]
    record = _tracked_target_catalog_record()
    state.record_tracked_target(
        TrackedTargetRecord(
            record_id="tracked:active",
            source_rule_id=record.definition.source_id,
            source_ability_id=record.definition.ability_id,
            source_clause_id="tracked:initial-clause",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id=source_unit.unit_instance_id,
            source_model_instance_id=source_model_id,
            owner_scope=TrackedTargetOwnerScope.THIS_MODEL,
            role=TrackedTargetRole.PREY,
            supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
            target_unit_instance_id=destroyed_target.unit_instance_id,
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id="request:initial",
            selection_result_id="result:initial",
            active=True,
        )
    )
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        destroyed_target.own_model_ids()
    )
    decisions = DecisionController()
    runtime = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records((record,)),
        },
        armies=tuple(state.army_definitions),
    )
    current_phase = state.current_battle_phase
    assert current_phase is not None

    runtime.unit_destroyed_handler(
        UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=current_phase,
            model_destroyed_event_id="event:destroyed-target",
            model_destroyed_payload={
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": current_phase.value,
                "destroying_player_id": "player-a",
                "target_unit_instance_id": destroyed_target.unit_instance_id,
                "model_instance_id": destroyed_target.own_models[0].model_instance_id,
            },
            destroying_player_id="player-a",
            destroyed_unit_instance_id=destroyed_target.unit_instance_id,
            destroyed_player_id="player-b",
        )
    )

    expired_record = state.tracked_target_records[0]
    assert not expired_record.active
    request = decisions.queue.pending_requests[0]
    assert request.decision_type == SELECT_TRACKED_TARGET_DECISION_TYPE
    assert request.options[0].option_id == replacement_target.unit_instance_id
    assert isinstance(request.payload, dict)
    request_payload = request.payload
    assert request_payload["replacement"] is True
    result = DecisionResult.for_request(
        result_id="result:replacement",
        request=request,
        selected_option_id=replacement_target.unit_instance_id,
    )
    replacement = apply_select_tracked_target_decision(
        state=state,
        request=request,
        result=result,
        decisions_event_log=decisions.event_log,
    )

    assert replacement.active
    assert replacement.target_unit_instance_id == replacement_target.unit_instance_id


def _record_selection(
    *,
    state: GameState,
    source_unit_instance_id: str,
    source_model_instance_id: str | None,
    target_unit_instance_id: str,
    owner_scope: TrackedTargetOwnerScope,
) -> None:
    state.record_tracked_target(
        TrackedTargetRecord(
            record_id=f"record:{owner_scope.value}",
            source_rule_id=f"rule:{owner_scope.value}",
            source_ability_id="ability:prey",
            source_clause_id="clause:select",
            source_effect_index=0,
            owner_player_id="player-a",
            source_unit_instance_id=source_unit_instance_id,
            source_model_instance_id=source_model_instance_id,
            owner_scope=owner_scope,
            role=TrackedTargetRole.PREY,
            supported_attack_roll_pairs=(("melee", "attack_sequence.wound"),),
            target_unit_instance_id=target_unit_instance_id,
            target_allegiance="enemy",
            target_lifecycle="until_destroyed",
            selected_battle_round=1,
            selection_request_id=f"request:{owner_scope.value}",
            selection_result_id=f"result:{owner_scope.value}",
            active=True,
        )
    )


def _battle_state_with_scenario(*, beta_unit_count: int = 1) -> GameState:
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="tracked-target-battlefield",
        armies=_mustered_armies(beta_unit_count=beta_unit_count),
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    state = GameState(
        game_id="tracked-target-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id="player-a",
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        command_point_ledgers=initial_command_point_ledgers(("player-a", "player-b")),
        victory_point_ledgers=initial_victory_point_ledgers(("player-a", "player-b")),
    )
    for army in scenario.armies:
        state.record_army_definition(army)
    state.battlefield_state = scenario.battlefield_state
    return state


def _mustered_armies(*, beta_unit_count: int = 1) -> tuple[ArmyDefinition, ...]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-a", army_id="army-alpha"),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_count=beta_unit_count,
            ),
        ),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_count: int = 1,
) -> ArmyMusterRequest:
    if unit_count < 1:
        raise AssertionError("unit_count must be positive")
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=(
                    f"{army_id}-unit" if unit_count == 1 else f"{army_id}-unit-{index}"
                ),
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for index in range(1, unit_count + 1)
        ),
    )


def _tracked_target_catalog_record(
    *,
    trigger_kind: TimingTriggerKind = TimingTriggerKind.AFTER_UNIT_DESTROYED,
    raw_text: str = PREY_TARGET_TEXT,
    source_id: str = "rule:tracked-target",
) -> AbilityCatalogRecord:
    source = RuleSourceText.from_raw(
        source_id=source_id,
        raw_text=raw_text,
    )
    rule_ir = compile_rule_source_text(
        source,
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    ).rule_ir
    return AbilityCatalogRecord(
        record_id="record:tracked-target",
        definition=AbilityDefinition(
            ability_id="ability:tracked-target",
            name="Tracked Target",
            source_id=source.source_id,
            when_descriptor="Battle-round start and tracked target destroyed.",
            effect_descriptor="Select prey and reselect when destroyed.",
            restrictions_descriptor="Enemy unit target.",
            timing=AbilityTimingDescriptor(trigger_kind=trigger_kind),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=cast(JsonValue, {"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-intercessor-like-infantry",
    )


def _belakor_catalog_record(
    *,
    row_id: str,
    ability_id: str,
    name: str,
) -> AbilityCatalogRecord:
    rule_ir = _belakor_rule_ir(row_id)
    return AbilityCatalogRecord(
        record_id=f"record:{ability_id}",
        definition=AbilityDefinition(
            ability_id=ability_id,
            name=name,
            source_id=rule_ir.source_id,
            when_descriptor="Source-backed Be'lakor runtime test ability.",
            effect_descriptor="Generic RuleIR effect.",
            restrictions_descriptor="Source-backed test restrictions.",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.START_BATTLE_ROUND),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=cast(JsonValue, {"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-intercessor-like-infantry",
    )


def _belakor_shadow_form_records() -> tuple[AbilityCatalogRecord, ...]:
    return (
        _belakor_catalog_record(
            row_id=belakor_ir_source.BELAKOR_SHADOW_FORM_ROW_ID,
            ability_id="ability:shadow-form",
            name="Shadow Form",
        ),
        _belakor_catalog_record(
            row_id=belakor_ir_source.BELAKOR_WREATHED_IN_SHADOWS_ROW_ID,
            ability_id="ability:wreathed-in-shadows",
            name="Wreathed in Shadows",
        ),
        _belakor_catalog_record(
            row_id=belakor_ir_source.BELAKOR_PALL_OF_DESPAIR_ROW_ID,
            ability_id="ability:pall-of-despair",
            name="Pall of Despair",
        ),
        _belakor_catalog_record(
            row_id=belakor_ir_source.BELAKOR_SHADOW_LORD_ROW_ID,
            ability_id="ability:shadow-lord",
            name="Shadow Lord",
        ),
    )


def _belakor_rule_ir(row_id: str) -> RuleIR:
    payload = belakor_ir_source.datasheet_rule_ir_payload_by_source_row_id(row_id)
    if payload is None:
        raise AssertionError(f"Missing Be'lakor RuleIR payload for row: {row_id}.")
    return RuleIR.from_payload(payload)
