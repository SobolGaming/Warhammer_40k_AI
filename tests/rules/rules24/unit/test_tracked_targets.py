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


def test_tracked_target_reroll_selects_duplicate_internal_permissions_deterministically() -> None:
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

    context = tracked_target_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=source_unit.unit_instance_id,
        model_instance_id=source_model_id,
        roll_type="attack_sequence.wound",
        timing_window="attack_sequence.wound",
        attack_kind="melee",
        target_unit_instance_id=target_unit_id,
    )

    assert context is not None
    assert context.source_payload["tracked_target_record_id"] == min(
        record.record_id for record in state.tracked_target_records
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
        sequencing_active_player_id=cast(str, state.active_player_id),
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
            sequencing_active_player_id=cast(str, state.active_player_id),
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


@pytest.mark.parametrize("include_unrelated_reselection", [False, True])
def test_tracked_target_expiration_does_not_depend_on_reselection_records(
    *,
    include_unrelated_reselection: bool,
) -> None:
    state = _battle_state_with_scenario(beta_unit_count=2)
    source_unit = state.army_definitions[0].units[0]
    destroyed_target = state.army_definitions[1].units[0]
    selection_record = _tracked_target_catalog_record(
        trigger_kind=TimingTriggerKind.START_BATTLE_ROUND,
        source_id="rule:selection-without-reselection",
        include_reselection=False,
    )
    records = [selection_record]
    if include_unrelated_reselection:
        records.append(
            replace(
                _tracked_target_catalog_record(source_id="rule:unrelated-reselection"),
                record_id="record:unrelated-reselection",
            )
        )
    runtime = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records(tuple(records)),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )
    state.record_tracked_target(
        TrackedTargetRecord(
            record_id="tracked:selection-without-reselection",
            source_rule_id=selection_record.definition.source_id,
            source_ability_id=selection_record.definition.ability_id,
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
            selection_request_id="request:selection-without-reselection",
            selection_result_id="result:selection-without-reselection",
            active=True,
        )
    )
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(
        destroyed_target.own_model_ids()
    )
    decisions = DecisionController()
    current_phase = state.current_battle_phase
    assert current_phase is not None
    context = UnitDestroyedContext(
        sequencing_active_player_id=cast(str, state.active_player_id),
        state=state,
        decisions=decisions,
        completed_phase=current_phase,
        model_destroyed_event_id="event:destroyed-selection-target",
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

    assert len(runtime.unit_destroyed_bindings()) == 1
    runtime.unit_destroyed_handler(context)
    runtime.unit_destroyed_handler(context)

    assert not state.tracked_target_records[0].active
    assert decisions.queue.pending_requests == ()
    assert (
        sum(record.event_type == "tracked_target_expired" for record in decisions.event_log.records)
        == 1
    )


@pytest.mark.parametrize(
    ("reselect_record_id", "passive_record_id"),
    [
        ("tracked:000-reselect", "tracked:999-passive"),
        ("tracked:999-reselect", "tracked:000-passive"),
    ],
)
def test_tracked_target_shared_target_expires_all_records_before_reselection(
    *,
    reselect_record_id: str,
    passive_record_id: str,
) -> None:
    state = _battle_state_with_scenario(alpha_unit_count=2, beta_unit_count=2)
    source_units = state.army_definitions[0].units
    destroyed_target = state.army_definitions[1].units[0]
    reselect_record = _tracked_target_catalog_record(source_id="rule:shared-target-reselect")
    passive_record = _tracked_target_catalog_record(
        trigger_kind=TimingTriggerKind.START_BATTLE_ROUND,
        source_id="rule:shared-target-passive",
        include_reselection=False,
    )
    runtime = CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records(
                (reselect_record, replace(passive_record, record_id="record:shared-passive"))
            ),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )
    tracked_records = (
        _shared_target_record(
            record_id=reselect_record_id,
            catalog_record=reselect_record,
            source_unit_instance_id=source_units[0].unit_instance_id,
            source_model_instance_id=source_units[0].own_models[0].model_instance_id,
            target_unit_instance_id=destroyed_target.unit_instance_id,
        ),
        _shared_target_record(
            record_id=passive_record_id,
            catalog_record=passive_record,
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

    runtime.unit_destroyed_handler(context)

    assert all(not record.active for record in state.tracked_target_records)
    assert tuple(
        record.event_type
        for record in decisions.event_log.records
        if record.event_type != "timing_batch_transition"
    ) == (
        TRACKED_TARGET_EXPIRED_EVENT_TYPE,
        TRACKED_TARGET_EXPIRED_EVENT_TYPE,
        "decision_requested",
    )
    assert len(decisions.queue.pending_requests) == 1
    request = decisions.queue.pending_requests[0]
    assert isinstance(request.payload, dict)
    assert request.payload["source_rule_id"] == reselect_record.definition.source_id
    assert request.payload["source_unit_instance_id"] == source_units[0].unit_instance_id

    runtime.record_unit_destroyed(context)
    assert tuple(
        record.event_type
        for record in decisions.event_log.records
        if record.event_type != "timing_batch_transition"
    ) == (
        TRACKED_TARGET_EXPIRED_EVENT_TYPE,
        TRACKED_TARGET_EXPIRED_EVENT_TYPE,
        "decision_requested",
    )


__all__: list[str] = []
__all__ += ["AbilityCatalogRecord", "AbilityDefinition", "AbilitySourceKind"]
__all__ += ["AbilityTimingDescriptor", "ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest"]
__all__ += ["BELAKOR_DARK_MASTER_ROW_ID", "BELAKOR_PALL_OF_DESPAIR_ROW_ID"]
__all__ += ["BELAKOR_SHADOW_FORM_ROW_ID", "BELAKOR_SHADOW_FORM_SOURCE_ID"]
__all__ += ["BELAKOR_SHADOW_LORD_ROW_ID", "BELAKOR_SOURCE_PACKAGE_ID"]
__all__ += ["BELAKOR_WREATHED_IN_SHADOWS_ROW_ID", "BELAKOR_WREATHED_IN_SHADOWS_SOURCE_ID"]
__all__ += ["BattlePhase", "BattlePhaseKind", "BattleRoundStartResultContext"]
__all__ += ["BattleShockForcedTestContext", "BattleShockOutcomeContext", "BattleShockResult"]
__all__ += ["BattleShockTestReason", "BattleShockTestRequest", "BelowHalfStrengthContext"]
__all__ += ["CATALOG_BATTLE_SHOCK_FAILED_HEAL_EVENT"]
__all__ += ["CATALOG_BATTLE_SHOCK_FAILED_HEAL_ROLL_TYPE"]
__all__ += ["CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID"]
__all__ += ["CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID"]
__all__ += ["CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID", "CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID"]
__all__ += ["CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID"]
__all__ += ["CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID"]
__all__ += ["CATALOG_SELECTED_TARGET_TEST_MODIFIER_HOOK_ID", "CATALOG_SHADOW_FORM_SELECTED_EVENT"]
__all__ += ["CATALOG_SHADOW_FORM_SELECTION_EFFECT_KIND", "CATALOG_SHADOW_FORM_SUBMISSION_KIND"]
__all__ += ["CatalogBattleShockRerollRuntime", "CatalogShadowFormRuntime", "DetachmentSelection"]
__all__ += ["GENERIC_RULE_EFFECT_KIND", "DiceRollManager", "EffectExpiration"]
__all__ += ["GENERIC_RULE_IR_ABILITY_HANDLER_ID", "GameLifecycleStage", "GameState"]
__all__ += ["MIXED_QUARRY_TARGET_TEXT", "ModelProfileSelection", "ObjectiveRuleScope"]
__all__ += ["PREY_TARGET_TEXT", "PersistingEffect", "RuleClause", "RuleEffectKind"]
__all__ += ["RuleEffectSpec", "RuleIR", "RuleSourceText", "RuleTriggerKind", "RulesetDescriptor"]
__all__ += ["SOURCE_KEYWORD_SEQUENCE_PARTS", "SourceBackedRerollPermissionContext"]
__all__ += ["StartingStrengthRecord", "UnitMusterSelection", "_belakor_catalog_record"]
__all__ += ["_belakor_rule_ir", "_belakor_shadow_form_records", "_muster_request"]
__all__ += ["_mustered_armies", "belakor_source_package", "catalog_battle_shock_hook_bindings"]
__all__ += ["catalog_contextual_module", "catalog_forced_battle_shock_unit_ids"]
__all__ += ["compile_rule_source_text", "consumer_ids_for_clause"]
__all__ += ["create_deterministic_battlefield_scenario", "datasheet_keyword_lexicon_source"]
__all__ += ["faction_pack_rule_ir", "hook_ids_for_effect", "initial_command_point_ledgers"]
__all__ += ["initial_victory_point_ledgers", "muster_army"]
__all__ += ["resolve_catalog_battle_shock_failed_heal"]
__all__ += ["source_backed_reroll_permission_context_for_unit"]
