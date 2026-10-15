from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase17g_black_templars_army_rule import (
    BLACK_TEMPLARS_DATASHEET_ID,
    BLACK_TEMPLARS_UNIT_ID,
    CHARGE_MOVE_ACTION,
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
    ENEMY_NON_PSYKER_DATASHEET_ID,
    ENEMY_NON_PSYKER_UNIT_ID,
    ENEMY_PSYKER_DATASHEET_ID,
    ENEMY_PSYKER_UNIT_ID,
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    AttackProfile,
    BattlePhase,
    BattlePhaseKind,
    Callable,
    Characteristic,
    CharacteristicValue,
    ChargeDeclarationContext,
    ChargeMoveProposal,
    ChargeTargetRestrictionContext,
    DamageProfile,
    DatasheetDefinition,
    DatasheetKeywordSet,
    DecisionController,
    DecisionResult,
    DetachmentDefinition,
    DetachmentSelection,
    EffectExpiration,
    FactionDefinition,
    FallBackEligibilityContext,
    GameConfig,
    GameLifecycle,
    GameLifecycleStage,
    GameState,
    GameStatePayload,
    MissionSetup,
    ModelPlacement,
    ModelProfileSelection,
    MovementMode,
    MovementProposalRequest,
    ObjectiveMarkerDefinition,
    PersistingEffect,
    PhaseEndObjectiveControlContext,
    Pose,
    ProposalKind,
    RangeProfile,
    RulesetDescriptor,
    RuntimeModifierRegistry,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    SetupCompletionGate,
    UnitInstance,
    UnitMusterSelection,
    UnitPlacement,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
    _battle_ready_lifecycle,
    _black_templars_battle_state,
    _black_templars_config,
    _black_templars_lifecycle_catalog,
    _center_marker_definition,
    _compact_unit_poses,
    _complete_setup_through_gate,
    _datasheet,
    _fixed_secondary_choice,
    _mission_setup,
    _mustered_armies,
    _place_black_templars_on_center_objective,
    _record_vow,
    _require_state,
    _runtime_content_bundle,
    _unit_placement_at,
    _unit_selection,
    _weapon_profile,
    _weapon_profile_context,
    _with_model_offsets,
    _wound_context,
    army_rule,
    build_runtime_content_bundle,
    chapter_approved_2026_27_mission_pack,
    charge_target_constraints_satisfied,
    create_deterministic_battlefield_scenario,
    ensure_army_mustered_events_for_fixture,
    json,
    muster_army,
    replace,
    required_charge_target_unit_instance_ids,
    source_backed_reroll_permission_context_for_unit,
)


def test_runtime_bundle_loads_black_templars_vow_surfaces() -> None:
    bundle = build_runtime_content_bundle(_black_templars_config())
    summary = bundle.to_summary_payload()

    assert army_rule.HOOK_ID in summary["battle_round_start_hook_ids"]
    assert army_rule.ABHOR_CHARGE_DECLARATION_HOOK_ID in summary["charge_declaration_hook_ids"]
    assert (
        army_rule.ABHOR_CHARGE_TARGET_RESTRICTION_HOOK_ID
        in summary["charge_target_restriction_hook_ids"]
    )
    assert army_rule.SUFFER_FALL_BACK_ELIGIBILITY_HOOK_ID in summary["fall_back_hook_ids"]
    assert (
        army_rule.UPHOLD_OBJECTIVE_CONTROL_HOOK_ID
        in summary["phase_end_objective_control_hook_ids"]
    )
    assert army_rule.ABHOR_MELEE_PRECISION_MODIFIER_ID in summary["weapon_profile_modifier_ids"]
    assert army_rule.ACCEPT_ANY_CHALLENGE_WOUND_MODIFIER_ID in summary["wound_roll_modifier_ids"]


def test_lifecycle_requests_templar_vow_and_records_selected_vow() -> None:
    lifecycle = _battle_ready_lifecycle()
    contribution = army_rule.runtime_contribution()
    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")

    status = lifecycle.advance_until_decision_or_terminal()

    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert {option.option_id for option in request.options} == {
        "black_templars:templar_vows:abhor_the_witch",
        "black_templars:templar_vows:accept_any_challenge",
        "black_templars:templar_vows:suffer_not_the_unclean",
        "black_templars:templar_vows:uphold_the_honour",
    }

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-black-templars-select-abhor",
            request=request,
            selected_option_id="black_templars:templar_vows:abhor_the_witch",
        )
    )

    state = _require_state(lifecycle)
    assert (
        army_rule.active_templar_vow_for_player(state, player_id="player-a")
        is army_rule.TemplarVow.ABHOR_THE_WITCH
    )
    restored = cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
    assert restored == state.to_payload()


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest", "AttackProfile"]
__all__ += ["BLACK_TEMPLARS_DATASHEET_ID", "BLACK_TEMPLARS_UNIT_ID", "BattlePhase"]
__all__ += ["CHARGE_MOVE_ACTION", "BattlePhaseKind"]
__all__ += ["CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY", "Callable", "Characteristic"]
__all__ += ["CharacteristicValue", "ChargeDeclarationContext", "ChargeMoveProposal"]
__all__ += ["ChargeTargetRestrictionContext", "DamageProfile", "DatasheetDefinition"]
__all__ += ["DatasheetKeywordSet", "DecisionController", "DetachmentDefinition"]
__all__ += ["ENEMY_NON_PSYKER_DATASHEET_ID", "ENEMY_NON_PSYKER_UNIT_ID", "DetachmentSelection"]
__all__ += ["ENEMY_PSYKER_DATASHEET_ID", "ENEMY_PSYKER_UNIT_ID", "EffectExpiration"]
__all__ += ["FactionDefinition", "FallBackEligibilityContext", "GameConfig", "GameLifecycle"]
__all__ += ["GameLifecycleStage", "GameState", "MissionSetup", "ModelPlacement"]
__all__ += ["ModelProfileSelection", "MovementMode", "MovementProposalRequest"]
__all__ += ["ObjectiveMarkerDefinition", "PersistingEffect", "PhaseEndObjectiveControlContext"]
__all__ += ["Pose", "ProposalKind", "RangeProfile", "RulesetDescriptor"]
__all__ += ["RuntimeModifierRegistry", "SecondaryMissionChoice", "SecondaryMissionMode"]
__all__ += ["SetupCompletionGate", "UnitInstance", "UnitMusterSelection", "UnitPlacement"]
__all__ += ["WeaponKeyword", "WeaponProfile", "WeaponProfileModifierContext"]
__all__ += ["WoundRollModifierContext", "_black_templars_battle_state"]
__all__ += ["_black_templars_lifecycle_catalog", "_center_marker_definition"]
__all__ += ["_compact_unit_poses", "_complete_setup_through_gate", "_datasheet"]
__all__ += ["_fixed_secondary_choice", "_mission_setup", "_mustered_armies"]
__all__ += ["_place_black_templars_on_center_objective", "_record_vow", "_runtime_content_bundle"]
__all__ += ["_unit_placement_at", "_unit_selection", "_weapon_profile", "_weapon_profile_context"]
__all__ += ["_with_model_offsets", "_wound_context", "chapter_approved_2026_27_mission_pack"]
__all__ += ["charge_target_constraints_satisfied", "create_deterministic_battlefield_scenario"]
__all__ += ["ensure_army_mustered_events_for_fixture", "muster_army", "replace"]
__all__ += ["required_charge_target_unit_instance_ids"]
__all__ += ["source_backed_reroll_permission_context_for_unit"]
