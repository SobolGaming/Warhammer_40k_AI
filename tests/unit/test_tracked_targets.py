from __future__ import annotations

from typing import cast

from tests.shared.category_migration.tracked_targets import (
    BELAKOR_DARK_MASTER_ROW_ID,
    BELAKOR_PALL_OF_DESPAIR_ROW_ID,
    BELAKOR_SHADOW_FORM_ROW_ID,
    BELAKOR_SHADOW_FORM_SOURCE_ID,
    BELAKOR_SHADOW_LORD_ROW_ID,
    BELAKOR_SOURCE_PACKAGE_ID,
    BELAKOR_WREATHED_IN_SHADOWS_ROW_ID,
    BELAKOR_WREATHED_IN_SHADOWS_SOURCE_ID,
    CATALOG_BATTLE_SHOCK_FAILED_HEAL_EVENT,
    CATALOG_BATTLE_SHOCK_FAILED_HEAL_ROLL_TYPE,
    CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
    CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
    CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
    CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
    CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID,
    CATALOG_SELECTED_TARGET_TEST_MODIFIER_HOOK_ID,
    CATALOG_SHADOW_FORM_SELECTED_EVENT,
    CATALOG_SHADOW_FORM_SELECTION_EFFECT_KIND,
    CATALOG_SHADOW_FORM_SUBMISSION_KIND,
    GENERIC_RULE_EFFECT_KIND,
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    MIXED_QUARRY_TARGET_TEXT,
    PREY_TARGET_TEXT,
    SELECT_TRACKED_TARGET_DECISION_TYPE,
    SOURCE_KEYWORD_SEQUENCE_PARTS,
    TRACKED_TARGET_EXPIRED_EVENT_TYPE,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    BattlePhase,
    BattlePhaseKind,
    BattleRoundStartRequestContext,
    BattleRoundStartResultContext,
    BattleShockForcedTestContext,
    BattleShockOutcomeContext,
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
    BelowHalfStrengthContext,
    CatalogBattleShockRerollRuntime,
    CatalogShadowFormRuntime,
    CatalogTrackedTargetRuntime,
    DecisionController,
    DecisionResult,
    DetachmentSelection,
    DiceRollManager,
    EffectExpiration,
    EventLog,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    JsonValue,
    ModelProfileSelection,
    ObjectiveRuleScope,
    PersistingEffect,
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RulesetDescriptor,
    RuleSourceText,
    RuleTriggerKind,
    SourceBackedRerollPermissionContext,
    StartingStrengthRecord,
    TimingTriggerKind,
    TrackedTargetOwnerScope,
    TrackedTargetRecord,
    TrackedTargetRole,
    UnitDestroyedContext,
    UnitMusterSelection,
    _battle_state_with_scenario,
    _belakor_catalog_record,
    _belakor_rule_ir,
    _belakor_shadow_form_records,
    _muster_request,
    _mustered_armies,
    _record_selection,
    _shared_target_record,
    _tracked_target_catalog_record,
    _tracked_target_destroyed_context,
    apply_select_tracked_target_decision,
    belakor_source_package,
    build_select_tracked_target_request,
    canonical_json,
    catalog_battle_shock_hook_bindings,
    catalog_contextual_module,
    catalog_forced_battle_shock_unit_ids,
    catalog_rule_clauses_from_record,
    catalog_tracked_target_runtime_module,
    compile_rule_source_text,
    consumer_ids_for_clause,
    create_deterministic_battlefield_scenario,
    datasheet_keyword_lexicon_source,
    faction_pack_rule_ir,
    hook_ids_for_effect,
    initial_command_point_ledgers,
    initial_victory_point_ledgers,
    invalid_select_tracked_target_status,
    muster_army,
    pytest,
    replace,
    resolve_catalog_battle_shock_failed_heal,
    source_backed_reroll_permission_context_for_unit,
    tracked_target_reroll_permission_context_for_unit,
    tracked_targets_module,
)


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


def test_catalog_shadow_form_runtime_records_selection_and_event() -> None:
    state = _battle_state_with_scenario(
        alpha_datasheet_id="core-character-leader",
        alpha_model_profile_id="core-character-leader",
        alpha_model_count=1,
    )
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
    assert request.payload["source_rule_id"] == BELAKOR_SHADOW_FORM_SOURCE_ID
    selected_option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict)
        and option.payload["selected_shadow_form_source_id"]
        == BELAKOR_WREATHED_IN_SHADOWS_SOURCE_ID
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


def test_catalog_shadow_form_rejects_ambiguous_multi_model_source() -> None:
    state = _battle_state_with_scenario()
    runtime = CatalogShadowFormRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records(
                _belakor_shadow_form_records(datasheet_id="core-intercessor-like-infantry")
            ),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )

    with pytest.raises(GameLifecycleError, match="requires exactly one source model"):
        runtime.battle_round_start_request(
            BattleRoundStartRequestContext(state=state, decisions=DecisionController())
        )


def test_catalog_shadow_form_selection_rejects_adapter_drift() -> None:
    state = _battle_state_with_scenario(
        alpha_datasheet_id="core-character-leader",
        alpha_model_profile_id="core-character-leader",
        alpha_model_count=1,
    )
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
        BELAKOR_DARK_MASTER_ROW_ID,
        BELAKOR_SHADOW_FORM_ROW_ID,
        BELAKOR_WREATHED_IN_SHADOWS_ROW_ID,
        BELAKOR_PALL_OF_DESPAIR_ROW_ID,
        BELAKOR_SHADOW_LORD_ROW_ID,
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
    pall_rule_ir = _belakor_rule_ir(BELAKOR_PALL_OF_DESPAIR_ROW_ID)
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
                    "context": {
                        "source_unit_instance_id": source_unit.unit_instance_id,
                        "source_model_instance_id": source_unit.own_models[0].model_instance_id,
                    },
                },
            ),
        )
    )
    records = (
        _belakor_catalog_record(
            row_id=BELAKOR_PALL_OF_DESPAIR_ROW_ID,
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
        CATALOG_SELECTED_TARGET_TEST_MODIFIER_HOOK_ID,
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


@pytest.mark.parametrize("source_status", ["wounded", "full", "destroyed"])
def test_catalog_battle_shock_failed_heal_resolves_generic_rule_ir_effect(
    source_status: str,
) -> None:
    from tests.order89_healing_helpers import healing_scene

    from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
    from warhammer40k_core.engine.damage_allocation import model_by_id
    from warhammer40k_core.engine.healing import (
        HealingEffect,
        HealingEffectPayload,
        HealingStepKind,
    )

    lifecycle, _, model_ids, _ = healing_scene(
        wounded=(0, 1) if source_status == "wounded" else (1,),
        destroyed=(0, 2) if source_status == "destroyed" else (2,),
        battle_phase=BattlePhase.COMMAND,
    )
    state = lifecycle.state
    assert state is not None
    decisions = lifecycle.decision_controller
    source_unit = state.army_definitions[0].units[0]
    target_unit = state.army_definitions[1].units[0]
    pall_rule_ir = _belakor_rule_ir(BELAKOR_PALL_OF_DESPAIR_ROW_ID)
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
                    "context": {
                        "source_unit_instance_id": source_unit.unit_instance_id,
                        "source_model_instance_id": source_unit.own_models[0].model_instance_id,
                    },
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
    dice_manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=(
            DiceRollResult.from_values(
                roll_id="order89-aura-d3",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason="Catalog Battle-shock failed heal",
                    roll_type=CATALOG_BATTLE_SHOCK_FAILED_HEAL_ROLL_TYPE,
                    actor_id=source_unit.unit_instance_id,
                ),
                values=(6,),
                source="injected",
            ),
        ),
    )

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
    resolved = HealingEffect.from_payload(
        cast(HealingEffectPayload, catalog_event.payload["healing_effect"])
    )
    assert resolved.is_complete()
    assert resolved.amount > 1
    assert len(resolved.resolved_steps) == resolved.amount
    healed_ids = tuple(
        step.model_instance_id
        for step in resolved.resolved_steps
        if step.step_kind is HealingStepKind.HEAL_WOUND
    )
    assert healed_ids == ((model_ids[0],) if source_status == "wounded" else ())
    assert [
        model_by_id(state=state, model_instance_id=i).current_wounds for i in model_ids[:3]
    ] == [
        0 if source_status == "destroyed" else 2,
        1,
        0,
    ]
    assert decisions.queue.pending_requests == ()


def test_catalog_battle_shock_runtime_noops_and_fail_fast_paths() -> None:
    state = _battle_state_with_scenario()
    source_unit = state.army_definitions[0].units[0]
    target_unit = state.army_definitions[1].units[0]
    pall_rule_ir = _belakor_rule_ir(BELAKOR_PALL_OF_DESPAIR_ROW_ID)
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
                    "context": {
                        "source_unit_instance_id": source_unit.unit_instance_id,
                        "source_model_instance_id": source_unit.own_models[0].model_instance_id,
                    },
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
            row_id=BELAKOR_PALL_OF_DESPAIR_ROW_ID,
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
                    "context": {
                        "source_unit_instance_id": source_unit.unit_instance_id,
                        "source_model_instance_id": source_unit.own_models[0].model_instance_id,
                    },
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


def test_tracked_target_shared_target_preserves_all_reselection_requests() -> None:
    state = _battle_state_with_scenario(alpha_unit_count=2, beta_unit_count=2)
    source_units = state.army_definitions[0].units
    destroyed_target = state.army_definitions[1].units[0]
    reselect_record = _tracked_target_catalog_record(source_id="rule:shared-reselection")
    runtime = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records((reselect_record,)),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )
    tracked_records = (
        _shared_target_record(
            record_id="tracked:999-source-one",
            catalog_record=reselect_record,
            source_unit_instance_id=source_units[0].unit_instance_id,
            source_model_instance_id=source_units[0].own_models[0].model_instance_id,
            target_unit_instance_id=destroyed_target.unit_instance_id,
        ),
        _shared_target_record(
            record_id="tracked:000-source-two",
            catalog_record=reselect_record,
            source_unit_instance_id=source_units[1].unit_instance_id,
            source_model_instance_id=source_units[1].own_models[0].model_instance_id,
            target_unit_instance_id=destroyed_target.unit_instance_id,
        ),
    )
    for tracked_record in tracked_records:
        state.record_tracked_target(tracked_record)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        destroyed_target.own_model_ids()
    )
    decisions = DecisionController()

    context = _tracked_target_destroyed_context(
        state=state,
        decisions=decisions,
        destroyed_unit_instance_id=destroyed_target.unit_instance_id,
        destroyed_model_instance_id=destroyed_target.own_models[0].model_instance_id,
    )
    runtime.record_unit_destroyed(context)
    before = state.to_payload(), decisions.to_payload()
    candidates = runtime.unit_destroyed_candidates(context)
    assert (state.to_payload(), decisions.to_payload()) == before
    assert len(candidates) == 2
    from warhammer40k_core.engine.sequencing import (
        SequencingRequirement,
        sequencing_decision_event_from_request,
    )

    assert all(
        candidate.participant.requirement is SequencingRequirement.MANDATORY
        for candidate in candidates
    )
    runtime.unit_destroyed_handler(context)
    assert all(not record.active for record in state.tracked_target_records)
    assert len(decisions.queue.pending_requests) == 1
    order = decisions.queue.pending_requests[0]
    assert order.actor_id == "player-a"
    assert len(order.options) == 2
    first = next(
        candidate
        for candidate in candidates
        if "tracked:999-source-one" in candidate.participant.participant_id
    )
    ordering = DecisionResult.for_request(
        request=order,
        result_id="shared-tracked-target-order",
        selected_option_id=f"next:{first.participant.participant_id}",
    )
    decisions.submit_result(ordering)
    event_type, payload = sequencing_decision_event_from_request(request=order, result=ordering)
    decisions.event_log.append(event_type, payload)
    for index, source_unit in enumerate(source_units):
        runtime.unit_destroyed_handler(context)
        assert len(decisions.queue.pending_requests) == 1
        request = decisions.queue.pending_requests[0]
        assert request.decision_type == SELECT_TRACKED_TARGET_DECISION_TYPE
        assert isinstance(request.payload, dict)
        assert request.payload["source_unit_instance_id"] == source_unit.unit_instance_id
        assert request.payload["destroyed_trigger_event_id"] == context.model_destroyed_event_id
        result = DecisionResult.for_request(
            request=request,
            result_id=f"shared-tracked-target-{index}",
            selected_option_id=request.options[0].option_id,
        )
        decisions.submit_result(result)
        apply_select_tracked_target_decision(
            state=state,
            request=request,
            result=result,
            decisions_event_log=decisions.event_log,
        )
    assert runtime.unit_destroyed_handler(context) is None
    assert decisions.queue.to_payload()["pending_requests"] == []
    assert len(tuple(record for record in state.tracked_target_records if record.active)) == 2


__all__: list[str] = []
__all__ += ["AbilityCatalogRecord", "AbilityDefinition", "AbilitySourceKind"]
__all__ += ["AbilityTimingDescriptor", "ArmyCatalog", "ArmyMusterRequest"]
__all__ += ["BELAKOR_SOURCE_PACKAGE_ID", "DetachmentSelection", "EventLog"]
__all__ += ["GENERIC_RULE_IR_ABILITY_HANDLER_ID", "GameLifecycleStage", "GameState"]
__all__ += ["PREY_TARGET_TEXT", "ModelProfileSelection", "ObjectiveRuleScope", "RuleIR"]
__all__ += ["RuleSourceText", "RuleTriggerKind", "RulesetDescriptor"]
__all__ += ["SOURCE_KEYWORD_SEQUENCE_PARTS", "TRACKED_TARGET_EXPIRED_EVENT_TYPE"]
__all__ += ["UnitDestroyedContext", "UnitMusterSelection", "_muster_request", "_mustered_armies"]
__all__ += ["_record_selection", "belakor_source_package", "build_select_tracked_target_request"]
__all__ += ["canonical_json", "catalog_rule_clauses_from_record"]
__all__ += ["catalog_tracked_target_runtime_module", "compile_rule_source_text"]
__all__ += ["create_deterministic_battlefield_scenario", "datasheet_keyword_lexicon_source"]
__all__ += ["faction_pack_rule_ir", "initial_command_point_ledgers"]
__all__ += ["initial_victory_point_ledgers", "invalid_select_tracked_target_status"]
__all__ += ["muster_army", "tracked_targets_module"]
