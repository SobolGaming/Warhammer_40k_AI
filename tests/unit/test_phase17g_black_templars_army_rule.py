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


def test_abhor_adds_precision_to_melee_attacks_against_psykers_only() -> None:
    state = _black_templars_battle_state()
    _record_vow(state, army_rule.TemplarVow.ABHOR_THE_WITCH)

    modified = army_rule.abhor_weapon_profile_modifier(
        _weapon_profile_context(
            state=state,
            target_unit_id=ENEMY_PSYKER_UNIT_ID,
            source_phase=BattlePhase.FIGHT,
        )
    )
    non_psyker = army_rule.abhor_weapon_profile_modifier(
        _weapon_profile_context(
            state=state,
            target_unit_id=ENEMY_NON_PSYKER_UNIT_ID,
            source_phase=BattlePhase.FIGHT,
        )
    )
    shooting = army_rule.abhor_weapon_profile_modifier(
        _weapon_profile_context(
            state=state,
            target_unit_id=ENEMY_PSYKER_UNIT_ID,
            source_phase=BattlePhase.SHOOTING,
        )
    )

    assert WeaponKeyword.PRECISION in modified.keywords
    assert army_rule.SOURCE_RULE_ID in modified.source_ids
    assert WeaponKeyword.PRECISION not in non_psyker.keywords
    assert WeaponKeyword.PRECISION not in shooting.keywords


def test_accept_any_challenge_adds_melee_wound_bonus_when_strength_is_not_higher() -> None:
    state = _black_templars_battle_state()
    _record_vow(state, army_rule.TemplarVow.ACCEPT_ANY_CHALLENGE)

    assert (
        army_rule.accept_any_challenge_wound_roll_modifier(
            _wound_context(
                state=state,
                source_phase=BattlePhase.FIGHT,
                strength=4,
                toughness=4,
            )
        )
        == 1
    )
    assert (
        army_rule.accept_any_challenge_wound_roll_modifier(
            _wound_context(
                state=state,
                source_phase=BattlePhase.FIGHT,
                strength=5,
                toughness=4,
            )
        )
        == 0
    )
    assert (
        army_rule.accept_any_challenge_wound_roll_modifier(
            _wound_context(
                state=state,
                source_phase=BattlePhase.SHOOTING,
                strength=4,
                toughness=4,
            )
        )
        == 0
    )


def test_abhor_charge_grant_records_reroll_and_restricts_targets_to_psykers() -> None:
    state = _black_templars_battle_state(
        phase=BattlePhase.CHARGE,
        enemy_origins={
            "enemy-psyker": Pose.at(17.0, 20.0),
            "enemy-non-psyker": Pose.at(18.5, 20.0),
        },
    )
    _record_vow(state, army_rule.TemplarVow.ABHOR_THE_WITCH)

    grant = army_rule.abhor_charge_declaration_grant(
        ChargeDeclarationContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
            selection_request_id="phase17g-black-templars-charge-selection-request",
            selection_result_id="phase17g-black-templars-charge-selection-result",
        )
    )

    assert grant is not None
    assert grant.unit_effect_payload is not None
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="phase17g-black-templars-abhor-charge-effect",
            source_rule_id=army_rule.SOURCE_RULE_ID,
            owner_player_id="player-a",
            target_unit_instance_ids=(BLACK_TEMPLARS_UNIT_ID,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.CHARGE,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=BattlePhaseKind.CHARGE,
                player_id="player-a",
            ),
            effect_payload=grant.unit_effect_payload,
        )
    )

    permission = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
        roll_type="charge_roll",
        timing_window="after_charge_roll",
    )
    psyker_restriction = army_rule.abhor_charge_target_restriction(
        ChargeTargetRestrictionContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            charging_unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
            target_unit_instance_id=ENEMY_PSYKER_UNIT_ID,
        )
    )
    non_psyker_restriction = army_rule.abhor_charge_target_restriction(
        ChargeTargetRestrictionContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            charging_unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
            target_unit_instance_id=ENEMY_NON_PSYKER_UNIT_ID,
        )
    )

    assert permission is not None
    assert required_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
        reachable_target_unit_instance_ids=(),
    ) == (ENEMY_PSYKER_UNIT_ID,)
    assert not charge_target_constraints_satisfied(
        state=state,
        unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
        candidate_target_unit_instance_ids=(),
    )
    assert permission.source_payload["effect_kind"] == army_rule.ABHOR_CHARGE_EFFECT_KIND
    assert psyker_restriction is None
    assert non_psyker_restriction is not None
    assert (
        non_psyker_restriction.violation_code
        == "black_templars_abhor_charge_requires_psyker_target"
    )


def test_charge_move_rejects_no_move_when_required_psyker_target_is_reachable() -> None:
    request = MovementProposalRequest(
        request_id="phase17g-black-templars-charge-proposal",
        decision_type="submit_movement_proposal",
        actor_id="player-a",
        game_id="phase17g-black-templars-charge-proposal",
        battle_round=1,
        phase=BattlePhase.CHARGE.value,
        unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id="phase17g-black-templars-charge-selection-request",
        source_decision_result_id="phase17g-black-templars-charge-selection-result",
        spatial_context_hash="0" * 64,
        movement_phase_action=CHARGE_MOVE_ACTION,
        context={
            "movement_mode": MovementMode.CHARGE.value,
            "maximum_distance_inches": 7,
            "reachable_target_unit_instance_ids": [
                ENEMY_PSYKER_UNIT_ID,
                ENEMY_NON_PSYKER_UNIT_ID,
            ],
            "reachable_target_distances_inches": {
                ENEMY_PSYKER_UNIT_ID: 5.0,
                ENEMY_NON_PSYKER_UNIT_ID: 6.0,
            },
            CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: [ENEMY_PSYKER_UNIT_ID],
        },
    )
    proposal = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
        movement_phase_action=CHARGE_MOVE_ACTION,
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(),
    )

    result = proposal.validation_result_for_request(request)

    assert not result.is_valid
    assert result.violations[0].violation_code == "charge_required_target_not_selected"
    assert result.violations[0].field == "charge_target_unit_instance_ids"


def test_suffer_not_the_unclean_grants_charge_after_fall_back() -> None:
    state = _black_templars_battle_state(phase=BattlePhase.MOVEMENT)
    _record_vow(state, army_rule.TemplarVow.SUFFER_NOT_THE_UNCLEAN)

    grant = army_rule.suffer_not_the_unclean_fall_back_eligibility(
        FallBackEligibilityContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
            movement_request_id="phase17g-black-templars-fall-back-request",
            movement_result_id="phase17g-black-templars-fall-back-result",
        )
    )

    assert grant is not None
    assert grant.can_declare_charge is True
    assert grant.can_shoot is False


def test_uphold_the_honour_records_command_phase_sticky_control() -> None:
    state = _black_templars_battle_state()
    _place_black_templars_on_center_objective(state)
    _record_vow(state, army_rule.TemplarVow.UPHOLD_THE_HONOUR)

    states = army_rule.uphold_objective_control_states(
        PhaseEndObjectiveControlContext(
            state=state,
            event_log=DecisionController().event_log,
            completed_phase=BattlePhase.COMMAND,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )

    assert len(states) == 1
    assert states[0].player_id == "player-a"
    assert states[0].source_rule_id == army_rule.SOURCE_RULE_ID
    assert states[0].originating_unit_instance_id == BLACK_TEMPLARS_UNIT_ID
    assert states[0].replay_payload == {
        "effect_kind": army_rule.UPHOLD_STICKY_EFFECT_KIND,
        "selected_vow_id": army_rule.TemplarVow.UPHOLD_THE_HONOUR.value,
        "objective_id": states[0].objective_id,
        "originating_unit_instance_id": BLACK_TEMPLARS_UNIT_ID,
        "controlling_player_id": "player-a",
    }


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest", "AttackProfile"]
__all__ += ["BLACK_TEMPLARS_DATASHEET_ID", "Callable", "Characteristic", "CharacteristicValue"]
__all__ += ["DamageProfile", "DatasheetDefinition", "DatasheetKeywordSet", "DecisionResult"]
__all__ += ["ENEMY_NON_PSYKER_DATASHEET_ID", "DetachmentDefinition", "DetachmentSelection"]
__all__ += ["ENEMY_PSYKER_DATASHEET_ID", "FactionDefinition", "GameConfig", "GameLifecycle"]
__all__ += ["GameLifecycleStage", "GameState", "GameStatePayload", "MissionSetup"]
__all__ += ["ModelPlacement", "ModelProfileSelection", "ObjectiveMarkerDefinition"]
__all__ += ["RangeProfile", "RulesetDescriptor"]
__all__ += ["SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE", "SecondaryMissionChoice"]
__all__ += ["SecondaryMissionMode", "SetupCompletionGate", "UnitInstance", "UnitMusterSelection"]
__all__ += ["UnitPlacement", "WeaponProfile", "WeaponProfileModifierContext"]
__all__ += ["WoundRollModifierContext", "_battle_ready_lifecycle", "_black_templars_config"]
__all__ += ["_black_templars_lifecycle_catalog", "_center_marker_definition"]
__all__ += ["_compact_unit_poses", "_complete_setup_through_gate", "_datasheet"]
__all__ += ["_fixed_secondary_choice", "_mission_setup", "_mustered_armies", "_require_state"]
__all__ += ["_runtime_content_bundle", "_unit_placement_at", "_unit_selection", "_weapon_profile"]
__all__ += ["_with_model_offsets", "build_runtime_content_bundle", "cast"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_deterministic_battlefield_scenario"]
__all__ += ["ensure_army_mustered_events_for_fixture", "json", "muster_army", "replace"]
