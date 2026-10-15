from __future__ import annotations

from typing import Any, cast

from tests.shared.category_migration.phase17d_rule_execution import (
    CATALOG_SETUP_REACTIVE_SOURCE_KIND,
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
    FIGHTS_FIRST_CHARGE_EFFECT_KIND,
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    ONCE_PER_BATTLE_FIGHT_BOOST_TEXT,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    RULE_FREQUENCY_LIMIT_CONSUMED_EVENT,
    SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
    SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE,
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    SELECTED_TARGET_UNIT_CONTEXT_KEY,
    SETUP_REACTIVE_SHOOT_CHARGE_TEXT,
    SOURCE_KEYWORD_SEQUENCE_PARTS,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilityExecutionContext,
    AbilityResolutionStatus,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    AttachmentDeclaration,
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlePhase,
    BattlePhaseKind,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogDatasheetRuleRuntime,
    CatalogJsonObject,
    ChargeMoveProposal,
    ChargeTargetRestrictionHookRegistry,
    CommandPointLedger,
    CommandPointRuleMutationResult,
    CommandPointSourceKind,
    CompiledRuleSource,
    DatasheetAbilityDescriptor,
    DecisionController,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    DetachmentSelection,
    EffectError,
    EffectExpiration,
    EventLog,
    EventStreamCursor,
    GameConfig,
    GameLifecycle,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    HitRollModifierContext,
    JsonValue,
    KeywordGate,
    LifecycleStatusKind,
    LocalGameSession,
    MissionSetup,
    ModelInstance,
    ModelProfileSelection,
    MovementMode,
    MovementProposalRequest,
    ObjectiveRuleScope,
    ParameterizedSubmission,
    PathWitness,
    Pose,
    ProposalKind,
    ReactionQueue,
    ReactionWindow,
    ReplayRunner,
    ReplayRunStatus,
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleExecutionContext,
    RuleExecutionRegistry,
    RuleExecutionResult,
    RuleExecutionStatus,
    RuleIR,
    RuleIRError,
    RuleIRPayload,
    RuleParameter,
    RuleRuntimeBinding,
    RulesetDescriptor,
    RuleSourceText,
    RuleTrigger,
    RuleTriggerKind,
    RuntimeModifierRegistry,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    TextSpan,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
    UnitInstance,
    UnitMusterSelection,
    UnitPlacement,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
    _ability_record,
    _append_setup_reactive_arrival_event,
    _attached_leader_support_muster_request,
    _battle_state,
    _battle_state_with_attached_leader_support,
    _battle_state_with_extra_friendly_unit,
    _battle_state_with_scenario,
    _bodyguard_destroyed_attached_state,
    _catalog_with_champion_slayer_ability,
    _catalog_with_descriptor,
    _champion_slayer_ability_index,
    _champion_slayer_clause_record,
    _champion_slayer_descriptor,
    _champion_slayer_rule_ir,
    _command_point_spend_rule_ir,
    _compiled,
    _desperate_escape_modifier_rule_ir,
    _destroy_model,
    _event_payloads,
    _execution_context,
    _generic_catalog_descriptor,
    _json_object,
    _mission_setup,
    _muster_request,
    _muster_request_with_unit_ids,
    _mustered_armies,
    _mustered_armies_with_extra_friendly_unit,
    _next_psychic_request,
    _non_reaction_movement_request,
    _non_reaction_placement_request,
    _noop_rule_handler,
    _parameterized_result_for_request,
    _path_witness_for_unit_delta,
    _psychic_level_session,
    _reaction_queue_consistency_fixture,
    _reaction_queue_window,
    _record_decision_result,
    _request_setup_reactive_lifecycle_action,
    _rule_ir_with_aura_object_reference,
    _scenario,
    _scenario_with_extra_friendly_unit,
    _set_model_wounds,
    _setup_reactive_charge_move_request,
    _setup_reactive_config,
    _setup_reactive_lifecycle,
    _setup_reactive_single_model_state,
    _skullmaster_fury_text,
    _unit_by_id,
    _weapon_profile,
    _with_unit_keywords,
    _with_unit_model_poses,
    _with_unit_pose,
    apply_catalog_setup_reactive_charge_move,
    apply_catalog_setup_reactive_shoot_charge_result,
    apply_command_point_rule_mutation,
    build_player_ability_index,
    catalog_ability_records_from_catalog,
    catalog_restore_lost_wounds_after_destroying_unit,
    catalog_wound_roll_reroll_permission_for_attack,
    chapter_approved_2026_27_mission_pack,
    command_point_operation_and_delta,
    command_point_operation_shape_reason,
    command_point_rule_unavailable_reason,
    compile_rule_source_text,
    copy,
    create_deterministic_battlefield_scenario,
    datasheet_keyword_lexicon_source,
    default_ability_handler_registry,
    default_rule_execution_registry,
    destroy_model_by_rule,
    ensure_army_mustered_events_for_fixture,
    execute_abilities_from_index,
    execute_rule_ir,
    generic_rule_persisting_effect,
    generic_rule_wound_roll_modifier,
    hashlib,
    initial_command_point_ledgers,
    initial_victory_point_ledgers,
    invalid_catalog_setup_reactive_charge_move_status,
    invalid_catalog_setup_reactive_shoot_charge_status,
    is_catalog_setup_reactive_charge_move_request,
    json,
    muster_army,
    parameter_payload,
    psychic_uses,
    pytest,
    replace,
    request_catalog_setup_reactive_shoot_charge_if_available,
    rule_execution_status_from_token,
    rule_ir_from_execution_payload,
    rules_unit_persisting_effects,
    scoped_rule_ir_from_execution_payload,
    stratagem_decline_payload,
    validate_json_value,
    validate_reaction_queue_consistency,
    with_unit_keywords,
)


def test_phase17d_rule_execution_registry_order_is_binding_id_deterministic() -> None:
    effect_clause = _compiled("Add 1 to hit rolls for that unit.").rule_ir.clauses[0]
    effect = effect_clause.effects[0]
    target_clause = _compiled("Select one enemy unit.").rule_ir.clauses[0]
    first_effect = RuleRuntimeBinding(
        binding_id="phase17d:binding-a",
        template_id=None,
        effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
        handler=_noop_rule_handler,
    )
    second_effect = RuleRuntimeBinding(
        binding_id="phase17d:binding-b",
        template_id=None,
        effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
        handler=_noop_rule_handler,
    )
    first_target = RuleRuntimeBinding(
        binding_id="phase17d:target-binding-a",
        template_id=None,
        effect_kinds=(),
        handler=_noop_rule_handler,
        required_target_bindings=("unit_instance_ids",),
    )
    second_target = RuleRuntimeBinding(
        binding_id="phase17d:target-binding-b",
        template_id=None,
        effect_kinds=(),
        handler=_noop_rule_handler,
        required_target_bindings=("unit_instance_ids",),
    )

    forward = RuleExecutionRegistry.from_bindings(
        (first_effect, second_effect, first_target, second_target)
    )
    reverse = RuleExecutionRegistry.from_bindings(
        (second_target, first_target, second_effect, first_effect)
    )
    forward_payload_bytes = json.dumps(forward.to_payload(), separators=(",", ":")).encode("utf-8")
    reverse_payload_bytes = json.dumps(reverse.to_payload(), separators=(",", ":")).encode("utf-8")

    assert forward.binding_for_effect(clause=effect_clause, effect=effect) == first_effect
    assert reverse.binding_for_effect(clause=effect_clause, effect=effect) == first_effect
    assert forward.binding_for_clause(target_clause) == first_target
    assert reverse.binding_for_clause(target_clause) == first_target
    assert forward_payload_bytes == reverse_payload_bytes


def test_phase17d_rule_execution_result_and_binding_shape_validators_fail_fast() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    rule_ir = compiled.rule_ir

    with pytest.raises(GameLifecycleError, match="must contain effects"):
        RuleExecutionResult(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.APPLIED,
            created_persisting_effects=cast(Any, (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="event_records must contain events"):
        RuleExecutionResult(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.APPLIED,
            event_records=cast(Any, (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="Applied RuleExecutionResult"):
        RuleExecutionResult(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.APPLIED,
            reason="not-allowed",
        )
    with pytest.raises(GameLifecycleError, match="Non-applied RuleExecutionResult"):
        RuleExecutionResult(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.INVALID,
        )
    with pytest.raises(GameLifecycleError, match="effect_payloads must be a tuple"):
        RuleExecutionResult(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.APPLIED,
            effect_payloads=cast(Any, []),
        )
    with pytest.raises(GameLifecycleError, match="payload must be a JSON object"):
        RuleExecutionResult(
            rule_id=rule_ir.rule_id,
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            status=RuleExecutionStatus.APPLIED,
            effect_payloads=cast(Any, ([],)),
        )
    with pytest.raises(GameLifecycleError, match="binding_id must be a string"):
        RuleRuntimeBinding(
            binding_id=cast(str, 1),
            template_id=None,
            effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
            handler=_noop_rule_handler,
        )
    with pytest.raises(GameLifecycleError, match="binding_id must not be empty"):
        RuleRuntimeBinding(
            binding_id="",
            template_id=None,
            effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
            handler=_noop_rule_handler,
        )
    with pytest.raises(GameLifecycleError, match="effect_kinds must be a tuple"):
        RuleRuntimeBinding(
            binding_id="phase17d:bad-effect-kind-tuple",
            template_id=None,
            effect_kinds=cast(Any, []),
            handler=_noop_rule_handler,
        )
    with pytest.raises(GameLifecycleError, match="effect_kinds values must be RuleEffectKind"):
        RuleRuntimeBinding(
            binding_id="phase17d:bad-effect-kind-value",
            template_id=None,
            effect_kinds=cast(Any, ("bad",)),
            handler=_noop_rule_handler,
        )
    with pytest.raises(GameLifecycleError, match="effect_kinds values must not be duplicated"):
        RuleRuntimeBinding(
            binding_id="phase17d:duplicate-effect-kind",
            template_id=None,
            effect_kinds=(
                RuleEffectKind.MODIFY_DICE_ROLL,
                RuleEffectKind.MODIFY_DICE_ROLL,
            ),
            handler=_noop_rule_handler,
        )
    with pytest.raises(GameLifecycleError, match="required_state_inputs must be a tuple"):
        RuleRuntimeBinding(
            binding_id="phase17d:bad-required-state-inputs",
            template_id=None,
            effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
            handler=_noop_rule_handler,
            required_state_inputs=cast(Any, []),
        )
    with pytest.raises(
        GameLifecycleError,
        match="required_state_inputs must not contain duplicate",
    ):
        RuleRuntimeBinding(
            binding_id="phase17d:duplicate-required-state-inputs",
            template_id=None,
            effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
            handler=_noop_rule_handler,
            required_state_inputs=("state", "state"),
        )


def test_phase17d_target_only_clause_reports_missing_target_handler() -> None:
    compiled = _compiled("Select one enemy unit.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(target_unit_instance_ids=("army-beta:intercessor-unit-2",)),
        registry=RuleExecutionRegistry.empty(),
    )

    assert result.status is RuleExecutionStatus.UNSUPPORTED
    assert result.reason == "missing_target_handler"


def test_phase17d_generic_persisting_effect_rejects_invalid_payload_shape() -> None:
    with pytest.raises(EffectError, match="JSON object"):
        generic_rule_persisting_effect(
            effect_id="phase17d:effect",
            source_rule_id="phase17d:source",
            owner_player_id="player-a",
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            started_battle_round=1,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_phase(
                battle_round=1,
                phase=BattlePhaseKind.COMMAND,
                player_id="player-a",
            ),
            effect_payload="not-object",
        )
    with pytest.raises(EffectError, match="payload kind"):
        generic_rule_persisting_effect(
            effect_id="phase17d:effect",
            source_rule_id="phase17d:source",
            owner_player_id="player-a",
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            started_battle_round=1,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_phase(
                battle_round=1,
                phase=BattlePhaseKind.COMMAND,
                player_id="player-a",
            ),
            effect_payload={"effect_kind": "wrong"},
        )


def test_phase17d_leading_model_condition_fails_closed_without_state_or_source() -> None:
    compiled = _compiled(_skullmaster_fury_text())

    missing_state = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            source_unit_instance_id="army-alpha:leader-unit",
            target_unit_instance_ids=("army-alpha:leader-unit",),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )
    missing_source = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=_battle_state_with_attached_leader_support(),
            target_unit_instance_ids=("army-alpha:leader-unit",),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )

    assert missing_state.status is RuleExecutionStatus.INVALID
    assert missing_state.reason == "missing_input:game_state"
    assert missing_source.status is RuleExecutionStatus.INVALID
    assert missing_source.reason == "missing_input:source_unit_instance_id"


def test_phase17d_ability_bridge_passes_state_for_leading_model_condition() -> None:
    state = _bodyguard_destroyed_attached_state()
    leader_id = "army-alpha:leader-unit"
    compiled = _compiled(_skullmaster_fury_text())
    record = AbilityCatalogRecord(
        record_id="phase17d:leading-ability-record",
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="phase17d:skullmaster",
        definition=AbilityDefinition(
            ability_id="phase17d:leading-ability",
            name="phase17d leading ability",
            source_id="phase17d:leading-ability-source",
            when_descriptor="phase17d:when",
            effect_descriptor="phase17d:effect",
            restrictions_descriptor="phase17d:restrictions",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": compiled.rule_ir.to_payload()}),
        ),
    )

    result = default_ability_handler_registry().execute(
        record=record,
        context=AbilityExecutionContext(
            game_id="phase17d-game",
            player_id="player-a",
            battle_round=1,
            phase=BattlePhaseKind.CHARGE,
            active_player_id="player-a",
            trigger_kind=TimingTriggerKind.ANY_PHASE,
            source_unit_instance_id=leader_id,
            target_unit_instance_id=leader_id,
            source_keywords=(),
            state=state,
        ),
    )

    assert result.status is AbilityResolutionStatus.APPLIED


__all__: list[str] = []
__all__ += ["AbilityCatalogIndex", "ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest"]
__all__ += ["AttachmentDeclaration", "BattlePhase", "BattlefieldPlacementKind"]
__all__ += ["BattlefieldRuntimeState", "BattlefieldScenario"]
__all__ += ["CATALOG_SETUP_REACTIVE_SOURCE_KIND"]
__all__ += ["CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY", "CatalogAbilitySourceKind"]
__all__ += ["CatalogAbilitySupport", "CatalogDatasheetRuleRuntime", "CatalogJsonObject"]
__all__ += ["ChargeMoveProposal", "ChargeTargetRestrictionHookRegistry", "CommandPointLedger"]
__all__ += ["CommandPointRuleMutationResult", "CommandPointSourceKind", "CompiledRuleSource"]
__all__ += ["DatasheetAbilityDescriptor", "DecisionController", "DecisionOption"]
__all__ += ["DecisionRequest", "DecisionResult", "DetachmentSelection", "EventLog"]
__all__ += ["FIGHTS_FIRST_CHARGE_EFFECT_KIND", "EventStreamCursor", "GameConfig", "GameLifecycle"]
__all__ += ["GameLifecycleStage", "GameState", "HitRollModifierContext", "JsonValue"]
__all__ += ["KeywordGate", "LifecycleStatusKind", "LocalGameSession"]
__all__ += ["MOVEMENT_PROPOSAL_DECISION_TYPE", "MissionSetup", "ModelInstance"]
__all__ += ["ModelProfileSelection", "MovementMode", "MovementProposalRequest"]
__all__ += ["ONCE_PER_BATTLE_FIGHT_BOOST_TEXT", "ObjectiveRuleScope"]
__all__ += ["PLACEMENT_PROPOSAL_DECISION_TYPE", "ParameterizedSubmission", "PathWitness", "Pose"]
__all__ += ["RULE_FREQUENCY_LIMIT_CONSUMED_EVENT", "ProposalKind", "ReactionQueue"]
__all__ += ["ReactionWindow", "ReplayRunStatus", "ReplayRunner", "RuleClause", "RuleCondition"]
__all__ += ["RuleConditionKind", "RuleEffectSpec", "RuleExecutionContext", "RuleIR"]
__all__ += ["RuleIRError", "RuleIRPayload", "RuleParameter", "RuleSourceText", "RuleTrigger"]
__all__ += ["RuleTriggerKind", "RulesetDescriptor", "RuntimeModifierRegistry"]
__all__ += ["SELECTED_TARGET_UNIT_CONTEXT_KEY"]
__all__ += ["SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE"]
__all__ += ["SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE"]
__all__ += ["SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE"]
__all__ += ["SETUP_REACTIVE_SHOOT_CHARGE_TEXT", "SOURCE_KEYWORD_SEQUENCE_PARTS"]
__all__ += ["STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE", "SecondaryMissionChoice"]
__all__ += ["SecondaryMissionMode", "TextSpan", "TimingWindow", "TimingWindowDescriptor"]
__all__ += ["UnitInstance", "UnitMusterSelection", "UnitPlacement", "WeaponKeyword"]
__all__ += ["WeaponProfile", "WeaponProfileModifierContext", "WoundRollModifierContext"]
__all__ += ["_ability_record", "_append_setup_reactive_arrival_event"]
__all__ += ["_attached_leader_support_muster_request", "_battle_state"]
__all__ += ["_battle_state_with_extra_friendly_unit", "_battle_state_with_scenario"]
__all__ += ["_catalog_with_champion_slayer_ability", "_catalog_with_descriptor"]
__all__ += ["_champion_slayer_ability_index", "_champion_slayer_clause_record"]
__all__ += ["_champion_slayer_descriptor", "_champion_slayer_rule_ir"]
__all__ += ["_command_point_spend_rule_ir", "_desperate_escape_modifier_rule_ir"]
__all__ += ["_destroy_model", "_event_payloads", "_generic_catalog_descriptor", "_json_object"]
__all__ += ["_mission_setup", "_muster_request", "_muster_request_with_unit_ids"]
__all__ += ["_mustered_armies", "_mustered_armies_with_extra_friendly_unit"]
__all__ += ["_next_psychic_request", "_non_reaction_movement_request"]
__all__ += ["_non_reaction_placement_request", "_parameterized_result_for_request"]
__all__ += ["_path_witness_for_unit_delta", "_psychic_level_session"]
__all__ += ["_reaction_queue_consistency_fixture", "_reaction_queue_window"]
__all__ += ["_record_decision_result", "_request_setup_reactive_lifecycle_action"]
__all__ += ["_rule_ir_with_aura_object_reference", "_scenario"]
__all__ += ["_scenario_with_extra_friendly_unit", "_set_model_wounds"]
__all__ += ["_setup_reactive_charge_move_request", "_setup_reactive_config"]
__all__ += ["_setup_reactive_lifecycle", "_setup_reactive_single_model_state", "_unit_by_id"]
__all__ += ["_weapon_profile", "_with_unit_keywords", "_with_unit_model_poses", "_with_unit_pose"]
__all__ += ["apply_catalog_setup_reactive_charge_move"]
__all__ += ["apply_catalog_setup_reactive_shoot_charge_result"]
__all__ += ["apply_command_point_rule_mutation", "build_player_ability_index"]
__all__ += ["catalog_ability_records_from_catalog"]
__all__ += ["catalog_restore_lost_wounds_after_destroying_unit"]
__all__ += ["catalog_wound_roll_reroll_permission_for_attack"]
__all__ += ["chapter_approved_2026_27_mission_pack", "command_point_operation_and_delta"]
__all__ += ["command_point_operation_shape_reason", "command_point_rule_unavailable_reason"]
__all__ += ["compile_rule_source_text", "copy", "create_deterministic_battlefield_scenario"]
__all__ += ["datasheet_keyword_lexicon_source", "destroy_model_by_rule"]
__all__ += ["ensure_army_mustered_events_for_fixture", "execute_abilities_from_index"]
__all__ += ["generic_rule_wound_roll_modifier", "hashlib", "initial_command_point_ledgers"]
__all__ += ["initial_victory_point_ledgers", "invalid_catalog_setup_reactive_charge_move_status"]
__all__ += ["invalid_catalog_setup_reactive_shoot_charge_status"]
__all__ += ["is_catalog_setup_reactive_charge_move_request", "muster_army", "parameter_payload"]
__all__ += ["psychic_uses", "replace", "request_catalog_setup_reactive_shoot_charge_if_available"]
__all__ += ["rule_execution_status_from_token", "rule_ir_from_execution_payload"]
__all__ += ["rules_unit_persisting_effects", "scoped_rule_ir_from_execution_payload"]
__all__ += ["stratagem_decline_payload", "validate_reaction_queue_consistency"]
__all__ += ["with_unit_keywords"]
