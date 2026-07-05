from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.setup_completion_helpers import enter_battle_for_fixture

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import DatasheetKeywordSet
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    StratagemDefinition,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import AbilityKind, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.army_mustering import (
    ArmyMusterRequest,
    EnhancementAssignment,
    muster_army,
)
from warhammer40k_core.engine.battle_formation_hooks import BattleFormationRequestContext
from warhammer40k_core.engine.command_points import CommandPointGainStatus, CommandPointSourceKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_rule_execution import (
    FactionRuleExecutionContext,
    FactionRuleExecutionResult,
    FactionRuleExecutionStatus,
)
from warhammer40k_core.engine.fight_order import (
    CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    FightPhaseState,
    FightsFirstRegistry,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_legality import MovementCapabilitySet
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases.shooting import ShootingPhaseState
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    MovementBudgetModifierContext,
    ObjectiveControlModifierContext,
    UnitCharacteristicModifierContext,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.stratagems import (
    DESTROYED_TARGET_UNIT_CONTEXT_KEY,
    ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY,
    FALL_BACK_UNIT_CONTEXT_KEY,
    JUST_SHOT_UNIT_CONTEXT_KEY,
    STRATAGEM_DECISION_TYPE,
    StratagemEligibilityContext,
    StratagemUseRecord,
    apply_stratagem_decision,
    request_stratagem_use_from_index,
)
from warhammer40k_core.engine.target_restriction_hooks import ShootingTargetRestrictionContext
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.triggered_movement import SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE
from warhammer40k_core.engine.unit_rule_effects import (
    charge_transit_through_non_vehicle_monster_models_allowed,
    movement_transit_through_terrain_features_allowed,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_court_of_the_phoenician_ir_support_2026_27 as court_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionStatus,
)

_MORE_DAKKA_GENERIC_EXECUTION_IDS = (
    "phase17f:phase17e:orks:more-dakka:rule",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991002",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991003",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991004",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991005",
    "phase17f:phase17e:stratagem:orks:more-dakka:000009992002",
    "phase17f:phase17e:stratagem:orks:more-dakka:000009992003",
    "phase17f:phase17e:stratagem:orks:more-dakka:000009992004",
    "phase17f:phase17e:stratagem:orks:more-dakka:000009992005",
    "phase17f:phase17e:stratagem:orks:more-dakka:000009992006",
    "phase17f:phase17e:stratagem:orks:more-dakka:000009992007",
)
_MORE_DAKKA_ENHANCEMENT_EXECUTION_IDS = (
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991002",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991003",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991004",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991005",
)
_SPECTACLE_GENERIC_EXECUTION_IDS = (
    "phase17f:phase17e:emperors-children:spectacle-of-slaughter:rule",
    ("phase17f:phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900002"),
    ("phase17f:phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900003"),
    ("phase17f:phase17e:stratagem:emperors-children:spectacle-of-slaughter:000010901002"),
    ("phase17f:phase17e:stratagem:emperors-children:spectacle-of-slaughter:000010901003"),
    ("phase17f:phase17e:stratagem:emperors-children:spectacle-of-slaughter:000010901004"),
)
_SPECTACLE_ENHANCEMENT_EXECUTION_IDS = (
    ("phase17f:phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900002"),
    ("phase17f:phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900003"),
)
_COURT_GENERIC_EXECUTION_IDS = (
    "phase17f:phase17e:emperors-children:court-of-the-phoenician:rule",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654002",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654003",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654004",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654005",
    "phase17f:phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655002",
    "phase17f:phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655003",
    "phase17f:phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655004",
    "phase17f:phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655005",
    "phase17f:phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655006",
    "phase17f:phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655007",
)
_COURT_ENHANCEMENT_EXECUTION_IDS = (
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654002",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654003",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654004",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654005",
)


@pytest.mark.integration
def test_ws14_more_dakka_generic_ir_rows_execute_from_lifecycle_runtime_bundle() -> None:
    config = _more_dakka_lifecycle_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.advance_until_decision_or_terminal()

    bundle = _runtime_content_bundle(lifecycle)

    assert "orks" in bundle.activation.selected_faction_ids
    assert "more-dakka" in bundle.activation.selected_detachment_ids
    assert set(_MORE_DAKKA_GENERIC_EXECUTION_IDS).issubset(
        bundle.activation.selected_execution_record_ids
    )

    context = FactionRuleExecutionContext(
        game_id=config.game_id,
        player_id="player-a",
        battle_round=1,
        phase=BattlePhaseKind.SHOOTING,
        active_player_id="player-a",
        source_unit_instance_id="army-alpha:boyz-1",
        trigger_payload={"event": "ws14-more-dakka-generic-ir-demo"},
    )
    results = tuple(
        bundle.faction_rule_execution_registry.execute(
            execution_id=execution_id,
            context=context,
        )
        for execution_id in _MORE_DAKKA_ENHANCEMENT_EXECUTION_IDS
    )

    assert tuple(result.status for result in results) == (
        FactionRuleExecutionStatus.APPLIED,
        FactionRuleExecutionStatus.APPLIED,
        FactionRuleExecutionStatus.APPLIED,
        FactionRuleExecutionStatus.APPLIED,
    )
    for result in results:
        record = bundle.faction_rule_execution_registry.record_by_execution_id(result.execution_id)
        assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
        assert record.rule_ir_hash is not None
        assert FactionRuleExecutionResult.from_payload(result.to_payload()) == result
        replay_payload = _json_object(result.replay_payload)
        rule_result_payload = _json_object(replay_payload["generic_rule_execution_result"])
        assert rule_result_payload["status"] == "applied"

    payload = lifecycle.to_payload()
    rebuilt = GameLifecycle.from_payload(payload)

    assert _runtime_content_bundle(rebuilt).to_summary_payload() == bundle.to_summary_payload()
    assert "object at 0x" not in json.dumps(payload, sort_keys=True)


@pytest.mark.integration
def test_ws14_more_dakka_stratagem_activation_binds_target_through_lifecycle_bundle() -> None:
    lifecycle = _more_dakka_battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _grant_cp(state, player_id="player-a", amount=2)
    bundle = _runtime_content_bundle(lifecycle)
    player_index = bundle.stratagem_indexes_by_player_id["player-a"]
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )

    status = request_stratagem_use_from_index(
        state=state,
        decisions=lifecycle.decision_controller,
        index=player_index,
        context=context,
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = lifecycle.pending_decision_request()
    assert request is not None
    assert request.decision_type == STRATAGEM_DECISION_TYPE
    selected_option = next(
        option
        for option in request.options
        if _option_stratagem_id(option.payload) == "000009992003"
    )

    result = DecisionResult.for_request(
        result_id="ws14-more-dakka-get-stuck-in-result",
        request=request,
        selected_option_id=selected_option.option_id,
    )
    lifecycle.submit_decision(result)

    assert state.command_point_total("player-a") == 1
    use_record = state.stratagem_use_records[-1]
    assert use_record.stratagem_id == "000009992003"
    assert use_record.command_point_cost == 2
    spent = _last_event_payload(lifecycle, "command_points_spent")
    assert spent["player_id"] == "player-a"
    assert spent["requested_amount"] == 2
    assert spent["applied_amount"] == 2
    assert spent["source_id"] == use_record.use_id
    assert spent["source_kind"] == "stratagem_spend"
    spent_transaction = _json_object(spent["transaction"])
    assert spent_transaction["amount"] == -2
    assert spent_transaction["transaction_id"] == use_record.command_point_transaction_id
    assert use_record.targeted_unit_instance_ids == ("army-alpha:boyz-1",)
    target_bound = _last_event_payload(lifecycle, "rule_execution_target_bound")
    assert target_bound["target_kind"] == "friendly_unit"
    assert target_bound["target_unit_instance_ids"] == ["army-alpha:boyz-1"]
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()
    assert "object at 0x" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


@pytest.mark.integration
def test_ws14_more_dakka_generic_enhancement_ir_binds_to_assigned_bearer() -> None:
    lifecycle = _more_dakka_battle_lifecycle()
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)

    assignment_payloads = [
        assignment.to_payload()
        for assignment in bundle.activation.selected_enhancement_assignments
        if assignment.player_id == "player-a"
    ]
    assert assignment_payloads == [
        {
            "assignment_id": "army-alpha:000009991004:boyz-1",
            "player_id": "player-a",
            "army_id": "army-alpha",
            "enhancement_id": "000009991004",
            "target_unit_selection_id": "boyz-1",
            "bearer_unit_instance_id": "army-alpha:boyz-1",
            "source_id": "ws14-more-dakka:assignment:boyz-1:000009991004",
        }
    ]

    bearer_effects = tuple(state.persisting_effects_for_unit("army-alpha:boyz-1"))
    generic_hit_effects = tuple(
        effect
        for effect in bearer_effects
        if _json_object(effect.effect_payload).get("execution_id")
        == "phase17f:phase17e:enhancement:orks:more-dakka:000009991004"
    )
    assert len(generic_hit_effects) == 1
    effect_payload = _json_object(generic_hit_effects[0].effect_payload)
    assert effect_payload["effect_kind"] == "generic_rule_execution"
    assert effect_payload["target_unit_instance_ids"] == ["army-alpha:boyz-1"]
    effect = _json_object(effect_payload["effect"])
    assert effect["kind"] == "modify_dice_roll"
    assignment = _json_object(effect_payload["enhancement_assignment"])
    assert assignment["bearer_unit_instance_id"] == "army-alpha:boyz-1"

    weapon_profile = next(
        wargear
        for wargear in _more_dakka_catalog().wargear
        if wargear.wargear_id == "core-mob-shoota"
    ).weapon_profiles[0]
    model_instance_id = state.army_definitions[0].units[0].own_models[0].model_instance_id
    assert (
        bundle.runtime_modifier_registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id="army-alpha:boyz-1",
                attacker_model_instance_id=model_instance_id,
                target_unit_instance_id="army-beta:boyz-2",
                weapon_profile=weapon_profile,
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == 1
    )
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()
    assert "object at 0x" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


@pytest.mark.integration
def test_ws14_more_dakka_detachment_rule_and_get_stuck_in_use_ir_runtime_hooks() -> None:
    lifecycle = _more_dakka_battle_lifecycle()
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)
    weapon_profile = _mob_shoota_profile()
    attacker_model_id = _first_model_id(state, unit_instance_id="army-alpha:boyz-1")
    _prepare_battle_phase(state, phase=BattlePhase.SHOOTING, active_player_id="player-a")

    baseline_profile = bundle.runtime_modifier_registry.modified_weapon_profile(
        _weapon_profile_context(
            state=state,
            weapon_profile=weapon_profile,
            attacker_model_id=attacker_model_id,
        )
    )

    assert WeaponKeyword.ASSAULT in baseline_profile.keywords
    assert not _profile_has_ability(baseline_profile, AbilityKind.SUSTAINED_HITS)

    _use_more_dakka_stratagem(
        lifecycle,
        stratagem_id="000009992003",
        target_unit_id="army-alpha:boyz-1",
        phase=BattlePhase.COMMAND,
        command_points=2,
    )
    _prepare_battle_phase(state, phase=BattlePhase.SHOOTING, active_player_id="player-a")
    waaagh_profile = bundle.runtime_modifier_registry.modified_weapon_profile(
        _weapon_profile_context(
            state=state,
            weapon_profile=weapon_profile,
            attacker_model_id=attacker_model_id,
        )
    )

    assert _profile_has_ability(waaagh_profile, AbilityKind.SUSTAINED_HITS)
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()


@pytest.mark.integration
def test_ws14_more_dakka_stratagem_ir_effects_drive_runtime_hooks() -> None:
    orks_lifecycle = _more_dakka_battle_lifecycle()
    orks_state = _state(orks_lifecycle)
    _use_more_dakka_stratagem(
        orks_lifecycle,
        stratagem_id="000009992002",
        target_unit_id="army-alpha:boyz-1",
        phase=BattlePhase.FIGHT,
    )
    reroll_context = source_backed_reroll_permission_context_for_unit(
        state=orks_state,
        player_id="player-a",
        unit_instance_id="army-alpha:boyz-1",
        model_instance_id=_first_model_id(orks_state, unit_instance_id="army-alpha:boyz-1"),
        roll_type="attack_sequence.wound",
        timing_window="attack.wound",
        target_unit_instance_id="army-beta:boyz-2",
    )
    assert reroll_context is not None
    assert reroll_context.source_payload["conditional_wound_reroll"] == {
        "reroll_unmodified_values": [1],
        "full_reroll_if_target_within_objective_range": True,
    }

    huge_lifecycle = _more_dakka_battle_lifecycle()
    huge_state = _state(huge_lifecycle)
    huge_bundle = _runtime_content_bundle(huge_lifecycle)
    _use_more_dakka_stratagem(
        huge_lifecycle,
        stratagem_id="000009992004",
        target_unit_id="army-alpha:walker-1",
        phase=BattlePhase.COMMAND,
    )
    walker_model_id = _first_model_id(huge_state, unit_instance_id="army-alpha:walker-1")
    assert (
        huge_bundle.runtime_modifier_registry.modified_movement_inches(
            MovementBudgetModifierContext(
                state=huge_state,
                unit_instance_id="army-alpha:walker-1",
                model_instance_id=walker_model_id,
                base_movement_inches=6.0,
                current_movement_inches=6.0,
            )
        )
        == 7.0
    )
    assert (
        huge_bundle.runtime_modifier_registry.modified_objective_control(
            ObjectiveControlModifierContext(
                state=huge_state,
                unit_instance_id="army-alpha:walker-1",
                model_instance_id=walker_model_id,
                base_objective_control=2,
                current_objective_control=2,
            )
        )
        == 3
    )
    assert (
        huge_bundle.runtime_modifier_registry.modified_unit_characteristic(
            UnitCharacteristicModifierContext(
                state=huge_state,
                unit_instance_id="army-alpha:walker-1",
                characteristic=Characteristic.LEADERSHIP,
                base_value=7,
                current_value=7,
            )
        )
        == 6
    )
    assert (
        huge_bundle.runtime_modifier_registry.hit_roll_modifier(
            HitRollModifierContext(
                state=huge_state,
                attacking_unit_instance_id="army-alpha:walker-1",
                attacker_model_instance_id=walker_model_id,
                target_unit_instance_id="army-beta:boyz-2",
                weapon_profile=_mob_shoota_profile(),
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == 1
    )

    long_lifecycle = _more_dakka_battle_lifecycle()
    long_state = _state(long_lifecycle)
    long_bundle = _runtime_content_bundle(long_lifecycle)
    _use_more_dakka_stratagem(
        long_lifecycle,
        stratagem_id="000009992005",
        target_unit_id="army-alpha:boyz-1",
        phase=BattlePhase.SHOOTING,
    )
    long_profile = long_bundle.runtime_modifier_registry.modified_weapon_profile(
        _weapon_profile_context(
            state=long_state,
            weapon_profile=_mob_shoota_profile(),
            attacker_model_id=_first_model_id(long_state, unit_instance_id="army-alpha:boyz-1"),
        )
    )
    assert WeaponKeyword.IGNORES_COVER in long_profile.keywords

    shells_lifecycle = _more_dakka_battle_lifecycle()
    shells_state = _state(shells_lifecycle)
    _place_units_for_more_dakka_shooting(shells_state)
    shells_bundle = _runtime_content_bundle(shells_lifecycle)
    _use_more_dakka_stratagem(
        shells_lifecycle,
        stratagem_id="000009992006",
        target_unit_id="army-alpha:boyz-1",
        phase=BattlePhase.SHOOTING,
    )
    shells_profile = shells_bundle.runtime_modifier_registry.modified_weapon_profile(
        _weapon_profile_context(
            state=shells_state,
            weapon_profile=_mob_shoota_profile(),
            attacker_model_id=_first_model_id(shells_state, unit_instance_id="army-alpha:boyz-1"),
        )
    )
    assert shells_profile.armor_penetration.final == 1


@pytest.mark.integration
def test_ws14_more_dakka_call_dat_dakka_binds_destroyed_target_and_requests_shooting() -> None:
    lifecycle = _more_dakka_battle_lifecycle()
    state = _state(lifecycle)
    _place_units_for_more_dakka_shooting(state)

    use_record, submit_status = _use_more_dakka_stratagem_through_lifecycle(
        lifecycle,
        stratagem_id="000009992007",
        target_unit_id="army-alpha:boyz-1",
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
        trigger_payload={
            JUST_SHOT_UNIT_CONTEXT_KEY: "army-beta:boyz-2",
            DESTROYED_TARGET_UNIT_CONTEXT_KEY: ["army-alpha:boyz-1"],
        },
    )

    assert use_record.targeted_unit_instance_ids == ("army-alpha:boyz-1",)
    assert state.out_of_phase_shooting_state is not None
    assert state.out_of_phase_shooting_state.player_id == "player-a"
    assert state.out_of_phase_shooting_state.selected_unit_instance_id == "army-alpha:boyz-1"
    assert state.out_of_phase_shooting_state.target_unit_ids == ("army-beta:boyz-2",)
    assert (
        _last_event_payload(lifecycle, "generic_stratagem_out_of_phase_shooting_requested")[
            "target_unit_instance_id"
        ]
        == "army-beta:boyz-2"
    )
    assert submit_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert submit_status.decision_request is not None
    assert submit_status.decision_request.decision_type == "submit_shooting_declaration"
    request = lifecycle.pending_decision_request()
    assert request is not None
    assert request == submit_status.decision_request
    assert request.decision_type == "submit_shooting_declaration"
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()


@pytest.mark.integration
def test_ws14_spectacle_of_slaughter_page_four_rows_execute_from_lifecycle_bundle() -> None:
    config = _spectacle_lifecycle_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.advance_until_decision_or_terminal()

    bundle = _runtime_content_bundle(lifecycle)

    assert "emperors-children" in bundle.activation.selected_faction_ids
    assert "spectacle-of-slaughter" in bundle.activation.selected_detachment_ids
    assert set(_SPECTACLE_GENERIC_EXECUTION_IDS).issubset(
        bundle.activation.selected_execution_record_ids
    )

    context = FactionRuleExecutionContext(
        game_id=config.game_id,
        player_id="player-a",
        battle_round=1,
        phase=BattlePhaseKind.FIGHT,
        active_player_id="player-a",
        source_unit_instance_id="army-alpha:blades-1",
        target_unit_instance_ids=("army-alpha:blades-1",),
        trigger_payload={"event": "ws14-spectacle-generic-ir-demo"},
    )
    results = tuple(
        bundle.faction_rule_execution_registry.execute(
            execution_id=execution_id,
            context=context,
        )
        for execution_id in _SPECTACLE_ENHANCEMENT_EXECUTION_IDS
    )

    assert tuple(result.status for result in results) == (
        FactionRuleExecutionStatus.APPLIED,
        FactionRuleExecutionStatus.APPLIED,
    )
    for result in results:
        record = bundle.faction_rule_execution_registry.record_by_execution_id(result.execution_id)
        assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
        assert record.rule_ir_hash is not None
        assert FactionRuleExecutionResult.from_payload(result.to_payload()) == result

    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()
    assert "object at 0x" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


@pytest.mark.integration
def test_ws14_spectacle_of_slaughter_rule_and_enhancements_bind_to_runtime_hooks() -> None:
    lifecycle = _spectacle_battle_lifecycle()
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)

    assignment_payloads = sorted(
        (
            assignment.to_payload()
            for assignment in bundle.activation.selected_enhancement_assignments
            if assignment.player_id == "player-a"
        ),
        key=lambda payload: str(payload["assignment_id"]),
    )
    assert assignment_payloads == [
        {
            "assignment_id": "army-alpha:000010900002:blades-1",
            "player_id": "player-a",
            "army_id": "army-alpha",
            "enhancement_id": "000010900002",
            "target_unit_selection_id": "blades-1",
            "bearer_unit_instance_id": "army-alpha:blades-1",
            "source_id": "ws14-spectacle:assignment:blades-1:000010900002",
        },
        {
            "assignment_id": "army-alpha:000010900003:blades-2",
            "player_id": "player-a",
            "army_id": "army-alpha",
            "enhancement_id": "000010900003",
            "target_unit_selection_id": "blades-2",
            "bearer_unit_instance_id": "army-alpha:blades-2",
            "source_id": "ws14-spectacle:assignment:blades-2:000010900003",
        },
    ]

    fights_first = FightsFirstRegistry.from_state(state)
    assert fights_first.has_unit("army-alpha:blades-1")
    assert fights_first.has_unit("army-alpha:blades-2")

    eager_model_id = _first_model_id(state, unit_instance_id="army-alpha:blades-2")
    assert (
        bundle.runtime_modifier_registry.modified_movement_inches(
            MovementBudgetModifierContext(
                state=state,
                unit_instance_id="army-alpha:blades-2",
                model_instance_id=eager_model_id,
                base_movement_inches=6.0,
                current_movement_inches=6.0,
            )
        )
        == 8.0
    )

    snap_restrictions = bundle.shooting_target_restriction_hook_registry.restrictions_for(
        ShootingTargetRestrictionContext(
            state=state,
            player_id="player-b",
            battle_round=state.battle_round,
            attacking_unit_instance_id="army-beta:blades-3",
            target_unit_instance_id="army-alpha:blades-1",
            attacker_model_instance_id=_first_model_id(
                state, unit_instance_id="army-beta:blades-3"
            ),
            shooting_type=ShootingType.SNAP,
        )
    )
    assert len(snap_restrictions) == 1
    assert snap_restrictions[0].violation_code == (
        "spectacle_of_slaughter_beguiling_grotesquerie_snap_target_forbidden"
    )
    normal_restrictions = bundle.shooting_target_restriction_hook_registry.restrictions_for(
        ShootingTargetRestrictionContext(
            state=state,
            player_id="player-b",
            battle_round=state.battle_round,
            attacking_unit_instance_id="army-beta:blades-3",
            target_unit_instance_id="army-alpha:blades-1",
            attacker_model_instance_id=_first_model_id(
                state, unit_instance_id="army-beta:blades-3"
            ),
            shooting_type=ShootingType.NORMAL,
        )
    )
    assert normal_restrictions == ()
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()


@pytest.mark.integration
def test_ws14_spectacle_of_slaughter_stratagems_execute_through_lifecycle() -> None:
    honour_lifecycle = _spectacle_battle_lifecycle()
    use_record, submit_status = _use_spectacle_stratagem_through_lifecycle(
        honour_lifecycle,
        stratagem_id="000010901002",
        target_unit_id="army-alpha:blades-1",
        phase=BattlePhase.FIGHT,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
    )
    assert use_record.targeted_unit_instance_ids == ("army-alpha:blades-1",)
    assert submit_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    honour_effect_payload = _last_event_payload(honour_lifecycle, "rule_execution_effect_applied")
    honour_effect = _json_object(honour_effect_payload["effect"])
    assert honour_effect["kind"] == "grant_weapon_ability"
    assert honour_effect_payload["target_unit_instance_ids"] == ["army-alpha:blades-1"]

    honour_hook_lifecycle = _spectacle_battle_lifecycle()
    honour_hook_state = _state(honour_hook_lifecycle)
    honour_hook_bundle = _runtime_content_bundle(honour_hook_lifecycle)
    _use_spectacle_stratagem(
        honour_hook_lifecycle,
        stratagem_id="000010901002",
        target_unit_id="army-alpha:blades-1",
        phase=BattlePhase.FIGHT,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
    )
    precision_profile = honour_hook_bundle.runtime_modifier_registry.modified_weapon_profile(
        _spectacle_weapon_profile_context(
            state=honour_hook_state,
            weapon_profile=_leader_blade_profile(),
            attacker_model_id=_first_model_id(
                honour_hook_state,
                unit_instance_id="army-alpha:blades-1",
            ),
            source_phase=BattlePhase.FIGHT,
        )
    )
    assert WeaponKeyword.PRECISION in precision_profile.keywords

    single_lifecycle = _spectacle_battle_lifecycle()
    _use_record, submit_status = _use_spectacle_stratagem_through_lifecycle(
        single_lifecycle,
        stratagem_id="000010901003",
        target_unit_id="army-alpha:blades-1",
        phase=BattlePhase.CHARGE,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )
    assert submit_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    single_effect_payload = _last_event_payload(single_lifecycle, "rule_execution_effect_applied")
    single_effect = _json_object(single_effect_payload["effect"])
    assert single_effect["kind"] == "movement_transit_permission"
    assert single_effect_payload["target_unit_instance_ids"] == ["army-alpha:blades-1"]

    single_hook_lifecycle = _spectacle_battle_lifecycle()
    single_hook_state = _state(single_hook_lifecycle)
    _use_spectacle_stratagem(
        single_hook_lifecycle,
        stratagem_id="000010901003",
        target_unit_id="army-alpha:blades-1",
        phase=BattlePhase.CHARGE,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )
    assert charge_transit_through_non_vehicle_monster_models_allowed(
        tuple(single_hook_state.persisting_effects_for_unit("army-alpha:blades-1")),
        owner_player_id="player-a",
    )

    intoxicated_lifecycle = _spectacle_battle_lifecycle()
    use_record, submit_status = _use_spectacle_stratagem_through_lifecycle(
        intoxicated_lifecycle,
        stratagem_id="000010901004",
        target_unit_id="army-alpha:blades-1",
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-b",
        trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
        trigger_payload={
            FALL_BACK_UNIT_CONTEXT_KEY: "army-beta:blades-3",
            ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY: ["army-alpha:blades-1"],
        },
    )
    assert use_record.targeted_unit_instance_ids == ("army-alpha:blades-1",)
    assert submit_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = intoxicated_lifecycle.pending_decision_request()
    assert request is not None
    assert request.decision_type == SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE
    request_payload = _json_object(request.payload)
    eligible_units = request_payload["eligible_units"]
    assert isinstance(eligible_units, list)
    assert len(eligible_units) == 1
    eligible_unit = _json_object(eligible_units[0])
    assert eligible_unit["unit_instance_id"] == "army-alpha:blades-1"
    descriptor = _json_object(request_payload["descriptor"])
    max_distance = descriptor["max_distance_inches"]
    assert isinstance(max_distance, int | float)
    assert 4 <= max_distance <= 6
    event_payload = _last_event_payload(
        intoxicated_lifecycle,
        "generic_stratagem_triggered_normal_move_requested",
    )
    assert event_payload["unit_instance_id"] == "army-alpha:blades-1"
    assert "object at 0x" not in json.dumps(intoxicated_lifecycle.to_payload(), sort_keys=True)
    assert (
        GameLifecycle.from_payload(intoxicated_lifecycle.to_payload()).to_payload()
        == intoxicated_lifecycle.to_payload()
    )


@pytest.mark.integration
def test_ws14_court_of_the_phoenician_rows_execute_from_lifecycle_bundle() -> None:
    config = _court_lifecycle_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.advance_until_decision_or_terminal()

    bundle = _runtime_content_bundle(lifecycle)

    assert "emperors-children" in bundle.activation.selected_faction_ids
    assert "court-of-the-phoenician" in bundle.activation.selected_detachment_ids
    assert set(_COURT_GENERIC_EXECUTION_IDS).issubset(
        bundle.activation.selected_execution_record_ids
    )

    context = FactionRuleExecutionContext(
        game_id=config.game_id,
        player_id="player-a",
        battle_round=1,
        phase=BattlePhaseKind.FIGHT,
        active_player_id="player-a",
        source_unit_instance_id="army-alpha:fulgrim-1",
        target_unit_instance_ids=("army-alpha:fulgrim-1",),
        trigger_payload={"event": "ws14-court-generic-ir-demo"},
    )
    results = tuple(
        bundle.faction_rule_execution_registry.execute(
            execution_id=execution_id,
            context=context,
        )
        for execution_id in _COURT_ENHANCEMENT_EXECUTION_IDS
    )

    assert tuple(result.status for result in results) == (
        FactionRuleExecutionStatus.APPLIED,
        FactionRuleExecutionStatus.APPLIED,
        FactionRuleExecutionStatus.APPLIED,
        FactionRuleExecutionStatus.APPLIED,
    )
    for result in results:
        record = bundle.faction_rule_execution_registry.record_by_execution_id(result.execution_id)
        assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
        assert record.rule_ir_hash is not None
        assert FactionRuleExecutionResult.from_payload(result.to_payload()) == result

    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()
    assert "object at 0x" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


@pytest.mark.integration
def test_ws14_court_of_the_phoenician_rule_and_enhancements_bind_to_runtime_hooks() -> None:
    lifecycle = _court_battle_lifecycle()
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)

    court_effects = tuple(
        effect
        for effect in state.persisting_effects_for_unit("army-alpha:fulgrim-1")
        if effect.source_rule_id == "gw-11e-phase17e-faction-coverage-2026-27:phase17e:"
        "emperors-children:court-of-the-phoenician:rule:source-text"
    )
    assert len(court_effects) == 4
    assert any(
        _effect_parameter(_json_object(_json_object(effect.effect_payload)["effect"]), "ability")
        == "sensational_performance"
        for effect in court_effects
    )

    lord_model_id = _first_model_id(state, unit_instance_id="army-alpha:lord-exultant-1")
    assert (
        bundle.runtime_modifier_registry.modified_movement_inches(
            MovementBudgetModifierContext(
                state=state,
                unit_instance_id="army-alpha:lord-exultant-1",
                model_instance_id=lord_model_id,
                base_movement_inches=6.0,
                current_movement_inches=6.0,
            )
        )
        == 7.0
    )

    daemon_model_id = _first_model_id(state, unit_instance_id="army-alpha:daemon-prince-1")
    daemon_base = _court_blade_profile()
    daemon_profile = bundle.runtime_modifier_registry.modified_weapon_profile(
        _court_weapon_profile_context(
            state=state,
            weapon_profile=daemon_base,
            attacker_model_id=daemon_model_id,
            attacking_unit_id="army-alpha:daemon-prince-1",
            target_unit_id="army-beta:enemy-character-1",
            source_phase=BattlePhase.FIGHT,
        )
    )
    assert daemon_profile.strength.final == daemon_base.strength.final + 1
    assert daemon_base.attack_profile.fixed_attacks is not None
    assert daemon_profile.attack_profile.fixed_attacks == (
        daemon_base.attack_profile.fixed_attacks + 1
    )

    fulgrim_model_id = _first_model_id(state, unit_instance_id="army-alpha:fulgrim-1")
    sensational_base = _court_blade_profile()
    pre_charge_profile = bundle.runtime_modifier_registry.modified_weapon_profile(
        _court_weapon_profile_context(
            state=state,
            weapon_profile=sensational_base,
            attacker_model_id=fulgrim_model_id,
            attacking_unit_id="army-alpha:fulgrim-1",
            target_unit_id="army-beta:enemy-character-1",
            source_phase=BattlePhase.FIGHT,
        )
    )
    assert pre_charge_profile.strength == sensational_base.strength
    assert pre_charge_profile.armor_penetration == sensational_base.armor_penetration

    _record_charge_move_effect(state, unit_instance_id="army-alpha:fulgrim-1")
    post_charge_profile = bundle.runtime_modifier_registry.modified_weapon_profile(
        _court_weapon_profile_context(
            state=state,
            weapon_profile=sensational_base,
            attacker_model_id=fulgrim_model_id,
            attacking_unit_id="army-alpha:fulgrim-1",
            target_unit_id="army-beta:enemy-character-1",
            source_phase=BattlePhase.FIGHT,
        )
    )
    assert post_charge_profile.strength.final == sensational_base.strength.final + 1
    assert post_charge_profile.armor_penetration.final == (
        sensational_base.armor_penetration.final + 1
    )
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()


@pytest.mark.integration
def test_ws14_court_of_the_phoenician_stratagems_execute_through_lifecycle() -> None:
    prideful_lifecycle = _court_battle_lifecycle()
    use_record, submit_status = _use_court_stratagem_through_lifecycle(
        prideful_lifecycle,
        stratagem_id="000010655003",
        target_unit_id="army-alpha:fulgrim-1",
        phase=BattlePhase.FIGHT,
        command_points=0,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    assert use_record.command_point_cost == 0
    assert (
        "warhammer_40000_11th:emperors_children:detachment:"
        "court_of_the_phoenician:master_of_the_pageant:cp_cost_reduction"
        in use_record.command_point_modifier_ids
    )
    assert submit_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    prideful_effect_lifecycle = _court_battle_lifecycle()
    _use_court_stratagem(
        prideful_effect_lifecycle,
        stratagem_id="000010655003",
        target_unit_id="army-alpha:fulgrim-1",
        phase=BattlePhase.FIGHT,
        command_points=0,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    prideful_state = _state(prideful_effect_lifecycle)
    reroll_context = source_backed_reroll_permission_context_for_unit(
        state=prideful_state,
        player_id="player-a",
        unit_instance_id="army-alpha:fulgrim-1",
        model_instance_id=_first_model_id(prideful_state, unit_instance_id="army-alpha:fulgrim-1"),
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
        target_unit_instance_id="army-beta:enemy-character-1",
    )
    assert reroll_context is not None

    restriction_lifecycle = _court_battle_lifecycle()
    restriction_state = _state(restriction_lifecycle)
    _prepare_battle_phase(
        restriction_state,
        phase=BattlePhase.CHARGE,
        active_player_id="player-a",
    )
    _grant_cp(restriction_state, player_id="player-a", amount=1)
    restriction_context = StratagemEligibilityContext.from_state(
        state=restriction_state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    restriction_status = request_stratagem_use_from_index(
        state=restriction_state,
        decisions=restriction_lifecycle.decision_controller,
        index=_runtime_content_bundle(restriction_lifecycle).stratagem_indexes_by_player_id[
            "player-a"
        ],
        context=restriction_context,
        stratagem_cost_modifier_registry=(
            _runtime_content_bundle(restriction_lifecycle).stratagem_cost_modifier_registry
        ),
    )
    assert restriction_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = restriction_lifecycle.pending_decision_request()
    assert request is not None
    assert not any(
        _option_stratagem_id(option.payload) == "000010655004"
        and _option_target_unit_id(option.payload) == "army-alpha:tears-1"
        for option in request.options
    )
    assert any(
        _option_stratagem_id(option.payload) == "000010655004"
        and _option_target_unit_id(option.payload) == "army-alpha:fulgrim-1"
        for option in request.options
    )

    sinuous_lifecycle = _court_battle_lifecycle()
    sinuous_state = _state(sinuous_lifecycle)
    _use_court_stratagem(
        sinuous_lifecycle,
        stratagem_id="000010655004",
        target_unit_id="army-alpha:fulgrim-1",
        phase=BattlePhase.CHARGE,
        command_points=0,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    sinuous_effects = tuple(sinuous_state.persisting_effects_for_unit("army-alpha:fulgrim-1"))
    assert movement_transit_through_terrain_features_allowed(
        sinuous_effects,
        owner_player_id="player-a",
        movement_mode="charge",
        unit_keywords=(
            court_ir.FULGRIM_KEYWORD,
            court_ir.DAEMON_KEYWORD,
            court_ir.CHARACTER_KEYWORD,
        ),
    )
    sinuous_capabilities = MovementCapabilitySet.from_keywords(
        (
            court_ir.FULGRIM_KEYWORD,
            court_ir.DAEMON_KEYWORD,
            court_ir.CHARACTER_KEYWORD,
        ),
        ruleset_descriptor=sinuous_lifecycle.config.ruleset_descriptor,
        movement_mode=MovementMode.CHARGE,
        unit_persisting_effects=sinuous_effects,
        owner_player_id="player-a",
    )
    assert sinuous_capabilities.can_move_through_terrain

    contempt_lifecycle = _court_battle_lifecycle()
    contempt_state = _state(contempt_lifecycle)
    contempt_bundle = _runtime_content_bundle(contempt_lifecycle)
    _use_court_stratagem(
        contempt_lifecycle,
        stratagem_id="000010655002",
        target_unit_id="army-alpha:fulgrim-1",
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    assert (
        contempt_bundle.runtime_modifier_registry.wound_roll_modifier(
            WoundRollModifierContext(
                state=contempt_state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id="army-beta:enemy-character-1",
                attacker_model_instance_id=_first_model_id(
                    contempt_state,
                    unit_instance_id="army-beta:enemy-character-1",
                ),
                target_unit_instance_id="army-alpha:fulgrim-1",
                weapon_profile=_court_shoota_profile(),
                strength=10,
                toughness=8,
            )
        )
        == -1
    )
    assert (
        contempt_bundle.runtime_modifier_registry.wound_roll_modifier(
            WoundRollModifierContext(
                state=contempt_state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id="army-beta:enemy-character-1",
                attacker_model_instance_id=_first_model_id(
                    contempt_state,
                    unit_instance_id="army-beta:enemy-character-1",
                ),
                target_unit_instance_id="army-alpha:fulgrim-1",
                weapon_profile=_court_shoota_profile(),
                strength=8,
                toughness=8,
            )
        )
        == 0
    )

    close_lifecycle = _court_battle_lifecycle()
    close_state = _state(close_lifecycle)
    _place_units_for_court_within_12(close_state)
    close_bundle = _runtime_content_bundle(close_lifecycle)
    close_base = _court_shoota_profile()
    _use_court_stratagem(
        close_lifecycle,
        stratagem_id="000010655005",
        target_unit_id="army-alpha:fulgrim-1",
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    close_profile = close_bundle.runtime_modifier_registry.modified_weapon_profile(
        _court_weapon_profile_context(
            state=close_state,
            weapon_profile=close_base,
            attacker_model_id=_first_model_id(close_state, unit_instance_id="army-alpha:fulgrim-1"),
            attacking_unit_id="army-alpha:fulgrim-1",
            target_unit_id="army-beta:enemy-character-1",
            source_phase=BattlePhase.SHOOTING,
        )
    )
    assert close_profile.strength.final == close_base.strength.final + 1
    assert close_profile.armor_penetration.final == close_base.armor_penetration.final + 1
    assert GameLifecycle.from_payload(close_lifecycle.to_payload()).to_payload() == (
        close_lifecycle.to_payload()
    )


def _more_dakka_lifecycle_config() -> GameConfig:
    catalog = _more_dakka_catalog()
    return GameConfig(
        game_id="ws14-more-dakka-generic-ir-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            _more_dakka_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                unit_selection_id="boyz-1",
                walker_unit_selection_id="walker-1",
            ),
            _more_dakka_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                unit_selection_id="boyz-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
        mission_setup=_mission_setup(),
    )


def _more_dakka_battle_lifecycle() -> GameLifecycle:
    config = _more_dakka_lifecycle_config()
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="ws14-more-dakka-battlefield",
        armies=armies,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    _record_fixed_secondary_choices_for_fixture(state, config=config)
    enter_battle_for_fixture(state)
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": DecisionController().to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )
    _apply_battle_formation_hooks_from_bundle(lifecycle)
    return lifecycle


def _more_dakka_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-boyz-like-infantry")
    boyz_datasheet = replace(
        base_datasheet,
        datasheet_id="ws14-orks-boyz",
        name="WS14 Orks Boyz",
        keywords=DatasheetKeywordSet(
            keywords=("Character", "Infantry"),
            faction_keywords=("Orks",),
        ),
        source_ids=("datasheet:ws14-orks-boyz",),
    )
    walker_datasheet = replace(
        base_datasheet,
        datasheet_id="ws14-orks-walker",
        name="WS14 Orks Walker",
        keywords=DatasheetKeywordSet(
            keywords=("Vehicle", "Walker"),
            faction_keywords=("Orks",),
        ),
        source_ids=("datasheet:ws14-orks-walker",),
    )
    mob_shoota = next(
        wargear for wargear in base_catalog.wargear if wargear.wargear_id == "core-mob-shoota"
    )
    return ArmyCatalog(
        catalog_id="ws14-more-dakka-demo",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="data-package:core-v2:ws14-more-dakka-demo:0.1.0",
        datasheets=(boyz_datasheet, walker_datasheet),
        wargear=(mob_shoota,),
        factions=(
            FactionDefinition(
                faction_id="orks",
                name="Orks",
                faction_keywords=("Orks",),
                source_ids=("faction:orks",),
            ),
        ),
        detachments=(
            DetachmentDefinition(
                detachment_id="more-dakka",
                name="More Dakka",
                faction_id="orks",
                detachment_point_cost=1,
                unit_datasheet_ids=("ws14-orks-boyz", "ws14-orks-walker"),
                force_disposition_ids=("purge-the-foe",),
                rule_source_ids=("phase17e:orks:more-dakka:rule",),
                enhancement_ids=(
                    "000009991002",
                    "000009991003",
                    "000009991004",
                    "000009991005",
                ),
                stratagem_ids=(
                    "000009992002",
                    "000009992003",
                    "000009992004",
                    "000009992005",
                    "000009992006",
                    "000009992007",
                ),
                source_ids=("detachment:more-dakka",),
            ),
        ),
        enhancements=(
            EnhancementDefinition(
                enhancement_id="000009991002",
                name="Da Gobshot Thunderbuss",
                source_id="phase17e:enhancement:orks:more-dakka:000009991002",
                points=15,
            ),
            EnhancementDefinition(
                enhancement_id="000009991003",
                name="Dead Shiny Shootas",
                source_id="phase17e:enhancement:orks:more-dakka:000009991003",
                points=35,
            ),
            EnhancementDefinition(
                enhancement_id="000009991004",
                name="Targetin Squigs",
                source_id="phase17e:enhancement:orks:more-dakka:000009991004",
                points=15,
            ),
            EnhancementDefinition(
                enhancement_id="000009991005",
                name="Zog Off and Eat Dakka",
                source_id="phase17e:enhancement:orks:more-dakka:000009991005",
                points=10,
            ),
        ),
        stratagems=(
            _more_dakka_stratagem("000009992002", "Orks Is Still Orks", 1),
            _more_dakka_stratagem("000009992003", "Get Stuck In Ladz", 2),
            _more_dakka_stratagem("000009992004", "Huge Show Offs", 1),
            _more_dakka_stratagem("000009992005", "Long Uncontrolled Bursts", 1),
            _more_dakka_stratagem("000009992006", "Speshul Shells", 1),
            _more_dakka_stratagem("000009992007", "Call Dat Dakka", 1),
        ),
        source_ids=("catalog:ws14-more-dakka-demo",),
    )


def _more_dakka_stratagem(
    stratagem_id: str,
    name: str,
    command_point_cost: int,
) -> StratagemDefinition:
    return StratagemDefinition(
        stratagem_id=stratagem_id,
        name=name,
        source_id=f"phase17e:stratagem:orks:more-dakka:{stratagem_id}",
        command_point_cost=command_point_cost,
        timing_tags=("shooting",),
    )


def _spectacle_lifecycle_config() -> GameConfig:
    catalog = _spectacle_catalog()
    return GameConfig(
        game_id="ws14-spectacle-of-slaughter-generic-ir-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            _spectacle_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                unit_selection_ids=("blades-1", "blades-2"),
                enhancement_assignments=(
                    ("000010900002", "blades-1"),
                    ("000010900003", "blades-2"),
                ),
            ),
            _spectacle_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                unit_selection_ids=("blades-3",),
                enhancement_assignments=(),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
        mission_setup=_mission_setup(),
    )


def _spectacle_battle_lifecycle() -> GameLifecycle:
    config = _spectacle_lifecycle_config()
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="ws14-spectacle-battlefield",
        armies=armies,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    _record_fixed_secondary_choices_for_fixture(state, config=config)
    enter_battle_for_fixture(state)
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": DecisionController().to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )
    _apply_battle_formation_hooks_from_bundle(lifecycle)
    return lifecycle


def _spectacle_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-boyz-like-infantry")
    flawless_blades_datasheet = replace(
        base_datasheet,
        datasheet_id="ws14-emperors-children-flawless-blades",
        name="WS14 Emperor's Children Flawless Blades",
        keywords=DatasheetKeywordSet(
            keywords=("Character", "Infantry"),
            faction_keywords=("Emperor's Children", "Flawless Blades"),
        ),
        source_ids=("datasheet:ws14-emperors-children-flawless-blades",),
    )
    core_weapons = tuple(
        wargear
        for wargear in base_catalog.wargear
        if wargear.wargear_id in {"core-leader-blade", "core-mob-shoota"}
    )
    return ArmyCatalog(
        catalog_id="ws14-spectacle-of-slaughter-demo",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="data-package:core-v2:ws14-spectacle-of-slaughter-demo:0.1.0",
        datasheets=(flawless_blades_datasheet,),
        wargear=core_weapons,
        factions=(
            FactionDefinition(
                faction_id="emperors-children",
                name="Emperor's Children",
                faction_keywords=("Emperor's Children",),
                source_ids=("faction:emperors-children",),
            ),
        ),
        detachments=(
            DetachmentDefinition(
                detachment_id="spectacle-of-slaughter",
                name="Spectacle of Slaughter",
                faction_id="emperors-children",
                detachment_point_cost=1,
                unit_datasheet_ids=("ws14-emperors-children-flawless-blades",),
                force_disposition_ids=("purge-the-foe",),
                rule_source_ids=("phase17e:emperors-children:spectacle-of-slaughter:rule",),
                enhancement_ids=("000010900002", "000010900003"),
                stratagem_ids=("000010901002", "000010901003", "000010901004"),
                source_ids=("detachment:spectacle-of-slaughter",),
            ),
        ),
        enhancements=(
            EnhancementDefinition(
                enhancement_id="000010900002",
                name="Beguiling Grotesquerie Upgrade",
                source_id=(
                    "phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900002"
                ),
                points=15,
            ),
            EnhancementDefinition(
                enhancement_id="000010900003",
                name="Eager Patrons Upgrade",
                source_id=(
                    "phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900003"
                ),
                points=20,
            ),
        ),
        stratagems=(
            _spectacle_stratagem("000010901002", "Honour Is For Fools"),
            _spectacle_stratagem("000010901003", "Single-Minded Strike"),
            _spectacle_stratagem("000010901004", "Intoxicated By Triumph"),
        ),
        source_ids=("catalog:ws14-spectacle-of-slaughter-demo",),
    )


def _spectacle_stratagem(stratagem_id: str, name: str) -> StratagemDefinition:
    return StratagemDefinition(
        stratagem_id=stratagem_id,
        name=name,
        source_id=f"phase17e:stratagem:emperors-children:spectacle-of-slaughter:{stratagem_id}",
        command_point_cost=1,
        timing_tags=("fight", "charge", "movement"),
    )


def _spectacle_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    unit_selection_ids: tuple[str, ...],
    enhancement_assignments: tuple[tuple[str, str], ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="emperors-children",
            detachment_ids=("spectacle-of-slaughter",),
            enhancement_ids=("000010900002", "000010900003"),
        ),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="ws14-emperors-children-flawless-blades",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-boyz-like",
                        model_count=10,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
        enhancement_assignments=tuple(
            EnhancementAssignment(
                enhancement_id=enhancement_id,
                target_unit_selection_id=target_unit_selection_id,
                source_id=(
                    f"ws14-spectacle:assignment:{target_unit_selection_id}:{enhancement_id}"
                ),
            )
            for enhancement_id, target_unit_selection_id in enhancement_assignments
        ),
        roster_legality_required=False,
    )


def _court_lifecycle_config() -> GameConfig:
    catalog = _court_catalog()
    return GameConfig(
        game_id="ws14-court-of-the-phoenician-generic-ir-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            _court_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                unit_selection_ids=(
                    "fulgrim-1",
                    "daemon-prince-1",
                    "lord-exultant-1",
                    "tears-1",
                    "soulstain-1",
                ),
                enhancement_assignments=(
                    ("000010654002", "tears-1"),
                    ("000010654003", "lord-exultant-1"),
                    ("000010654004", "soulstain-1"),
                    ("000010654005", "daemon-prince-1"),
                ),
            ),
            _court_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                unit_selection_ids=("enemy-character-1",),
                enhancement_assignments=(),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
        mission_setup=_mission_setup(),
    )


def _court_battle_lifecycle() -> GameLifecycle:
    config = _court_lifecycle_config()
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="ws14-court-battlefield",
        armies=armies,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    _record_fixed_secondary_choices_for_fixture(state, config=config)
    enter_battle_for_fixture(state)
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": DecisionController().to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )
    _apply_battle_formation_hooks_from_bundle(lifecycle)
    return lifecycle


def _court_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-boyz-like-infantry")
    core_weapons = tuple(
        wargear
        for wargear in base_catalog.wargear
        if wargear.wargear_id in {"core-leader-blade", "core-mob-shoota"}
    )
    return ArmyCatalog(
        catalog_id="ws14-court-of-the-phoenician-demo",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="data-package:core-v2:ws14-court-of-the-phoenician-demo:0.1.0",
        datasheets=(
            replace(
                base_datasheet,
                datasheet_id="ws14-court-fulgrim",
                name="WS14 Fulgrim",
                keywords=DatasheetKeywordSet(
                    keywords=(
                        court_ir.FULGRIM_KEYWORD,
                        court_ir.DAEMON_KEYWORD,
                        court_ir.CHARACTER_KEYWORD,
                        "MONSTER",
                    ),
                    faction_keywords=(court_ir.EMPERORS_CHILDREN_KEYWORD,),
                ),
                source_ids=("datasheet:ws14-court-fulgrim",),
            ),
            replace(
                base_datasheet,
                datasheet_id="ws14-court-daemon-prince",
                name="WS14 Emperor's Children Daemon Prince",
                keywords=DatasheetKeywordSet(
                    keywords=(
                        court_ir.DAEMON_PRINCE_KEYWORD,
                        court_ir.DAEMON_KEYWORD,
                        court_ir.CHARACTER_KEYWORD,
                        "MONSTER",
                    ),
                    faction_keywords=(court_ir.EMPERORS_CHILDREN_KEYWORD,),
                ),
                source_ids=("datasheet:ws14-court-daemon-prince",),
            ),
            replace(
                base_datasheet,
                datasheet_id="ws14-court-lord-exultant",
                name="WS14 Lord Exultant",
                keywords=DatasheetKeywordSet(
                    keywords=(court_ir.LORD_EXULTANT_KEYWORD, court_ir.CHARACTER_KEYWORD),
                    faction_keywords=(court_ir.EMPERORS_CHILDREN_KEYWORD,),
                ),
                source_ids=("datasheet:ws14-court-lord-exultant",),
            ),
            replace(
                base_datasheet,
                datasheet_id="ws14-court-infantry",
                name="WS14 Emperor's Children Infantry",
                keywords=DatasheetKeywordSet(
                    keywords=("INFANTRY",),
                    faction_keywords=(court_ir.EMPERORS_CHILDREN_KEYWORD,),
                ),
                source_ids=("datasheet:ws14-court-infantry",),
            ),
            replace(
                base_datasheet,
                datasheet_id="ws14-court-enemy-character",
                name="WS14 Enemy Character",
                keywords=DatasheetKeywordSet(
                    keywords=(court_ir.CHARACTER_KEYWORD, "INFANTRY"),
                    faction_keywords=("ENEMY", court_ir.EMPERORS_CHILDREN_KEYWORD),
                ),
                source_ids=("datasheet:ws14-court-enemy-character",),
            ),
        ),
        wargear=core_weapons,
        factions=(
            FactionDefinition(
                faction_id="emperors-children",
                name="Emperor's Children",
                faction_keywords=(court_ir.EMPERORS_CHILDREN_KEYWORD,),
                source_ids=("faction:emperors-children",),
            ),
            FactionDefinition(
                faction_id="ws14-opponent",
                name="WS14 Opponent",
                faction_keywords=("ENEMY",),
                source_ids=("faction:ws14-opponent",),
            ),
        ),
        detachments=(
            DetachmentDefinition(
                detachment_id="court-of-the-phoenician",
                name="Court of the Phoenician",
                faction_id="emperors-children",
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    "ws14-court-fulgrim",
                    "ws14-court-daemon-prince",
                    "ws14-court-lord-exultant",
                    "ws14-court-infantry",
                    "ws14-court-enemy-character",
                ),
                force_disposition_ids=("purge-the-foe",),
                rule_source_ids=("phase17e:emperors-children:court-of-the-phoenician:rule",),
                enhancement_ids=(
                    "000010654002",
                    "000010654003",
                    "000010654004",
                    "000010654005",
                ),
                stratagem_ids=(
                    "000010655002",
                    "000010655003",
                    "000010655004",
                    "000010655005",
                    "000010655006",
                    "000010655007",
                ),
                source_ids=("detachment:court-of-the-phoenician",),
            ),
        ),
        enhancements=(
            EnhancementDefinition(
                enhancement_id="000010654002",
                name="Tears of the Phoenix",
                source_id=(
                    "phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654002"
                ),
                points=15,
            ),
            EnhancementDefinition(
                enhancement_id="000010654003",
                name="Exalted Patron",
                source_id=(
                    "phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654003"
                ),
                points=20,
            ),
            EnhancementDefinition(
                enhancement_id="000010654004",
                name="Soulstain Made Manifest",
                source_id=(
                    "phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654004"
                ),
                points=20,
            ),
            EnhancementDefinition(
                enhancement_id="000010654005",
                name="Spiritsliver",
                source_id=(
                    "phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654005"
                ),
                points=25,
            ),
        ),
        stratagems=(
            _court_stratagem("000010655002", "Contemptuous Disregard"),
            _court_stratagem("000010655003", "Prideful Superiority"),
            _court_stratagem("000010655004", "Sinuous Breach"),
            _court_stratagem("000010655005", "Close-Quarters Excruciation"),
            _court_stratagem("000010655006", "Euphoric Inspiration"),
            _court_stratagem("000010655007", "Catalytic Stimulus"),
        ),
        source_ids=("catalog:ws14-court-of-the-phoenician-demo",),
    )


def _court_stratagem(stratagem_id: str, name: str) -> StratagemDefinition:
    return StratagemDefinition(
        stratagem_id=stratagem_id,
        name=name,
        source_id=f"phase17e:stratagem:emperors-children:court-of-the-phoenician:{stratagem_id}",
        command_point_cost=1,
        timing_tags=("shooting", "fight", "movement", "charge"),
    )


def _court_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    unit_selection_ids: tuple[str, ...],
    enhancement_assignments: tuple[tuple[str, str], ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="emperors-children",
            detachment_ids=("court-of-the-phoenician",),
            enhancement_ids=(
                "000010654002",
                "000010654003",
                "000010654004",
                "000010654005",
            ),
        ),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id=_court_datasheet_id_for_selection(unit_selection_id),
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-boyz-like",
                        model_count=10,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
        enhancement_assignments=tuple(
            EnhancementAssignment(
                enhancement_id=enhancement_id,
                target_unit_selection_id=target_unit_selection_id,
                source_id=f"ws14-court:assignment:{target_unit_selection_id}:{enhancement_id}",
            )
            for enhancement_id, target_unit_selection_id in enhancement_assignments
        ),
        roster_legality_required=False,
    )


def _court_datasheet_id_for_selection(unit_selection_id: str) -> str:
    if unit_selection_id == "fulgrim-1":
        return "ws14-court-fulgrim"
    if unit_selection_id == "daemon-prince-1":
        return "ws14-court-daemon-prince"
    if unit_selection_id == "lord-exultant-1":
        return "ws14-court-lord-exultant"
    if unit_selection_id in {"tears-1", "soulstain-1"}:
        return "ws14-court-infantry"
    if unit_selection_id == "enemy-character-1":
        return "ws14-court-enemy-character"
    raise AssertionError(f"Missing Court datasheet mapping for {unit_selection_id}.")


def _more_dakka_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    unit_selection_id: str,
    walker_unit_selection_id: str | None = None,
) -> ArmyMusterRequest:
    unit_selections = [
        UnitMusterSelection(
            unit_selection_id=unit_selection_id,
            datasheet_id="ws14-orks-boyz",
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="core-boyz-like",
                    model_count=10,
                ),
            ),
        )
    ]
    if walker_unit_selection_id is not None:
        unit_selections.append(
            UnitMusterSelection(
                unit_selection_id=walker_unit_selection_id,
                datasheet_id="ws14-orks-walker",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-boyz-like",
                        model_count=10,
                    ),
                ),
            )
        )
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="orks",
            detachment_ids=("more-dakka",),
            enhancement_ids=("000009991003", "000009991004", "000009991005"),
        ),
        unit_selections=tuple(unit_selections),
        enhancement_assignments=(
            EnhancementAssignment(
                enhancement_id="000009991004",
                target_unit_selection_id=unit_selection_id,
                source_id=(f"ws14-more-dakka:assignment:{unit_selection_id}:000009991004"),
            ),
        ),
        roster_legality_required=False,
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    bundle = object.__getattribute__(lifecycle, "_runtime_content_bundle")
    if type(bundle) is not RuntimeContentBundle:
        raise AssertionError("Runtime content bundle was not rebuilt.")
    return bundle


def _apply_battle_formation_hooks_from_bundle(lifecycle: GameLifecycle) -> None:
    state = _state(lifecycle)
    config = object.__getattribute__(lifecycle, "_config")
    if type(config) is not GameConfig:
        raise AssertionError("Lifecycle config was not loaded.")
    original_stage = state.stage
    original_setup_step_index = state.setup_step_index
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = state.setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS)
    try:
        request = _runtime_content_bundle(
            lifecycle
        ).battle_formation_hook_registry.next_request_for(
            BattleFormationRequestContext(
                state=state,
                decisions=lifecycle.decision_controller,
                config=config,
            )
        )
    finally:
        state.stage = original_stage
        state.setup_step_index = original_setup_step_index
    assert request is None


def _state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    assert state is not None
    return state


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _prepare_battle_phase(
    state: GameState,
    *,
    phase: BattlePhase,
    active_player_id: str,
) -> None:
    state.command_step_state = None
    state.movement_phase_state = None
    state.shooting_phase_state = None
    state.charge_phase_state = None
    state.fight_phase_state = None
    _set_current_battle_phase(state, phase)
    state.active_player_id = active_player_id
    if phase is BattlePhase.SHOOTING:
        state.shooting_phase_state = ShootingPhaseState(
            battle_round=state.battle_round,
            active_player_id=active_player_id,
        )
    if phase is BattlePhase.FIGHT:
        state.fight_phase_state = FightPhaseState.start(
            battle_round=state.battle_round,
            active_player_id=active_player_id,
            policy=RulesetDescriptor.warhammer_40000_eleventh().fight_policy,
            engaged_at_fight_step_start_unit_ids=(),
            fights_first_registry=FightsFirstRegistry.from_state(state),
        )


def _use_more_dakka_stratagem(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int = 1,
    active_player_id: str = "player-a",
    trigger_kind: TimingTriggerKind = TimingTriggerKind.START_PHASE,
    trigger_payload: JsonValue = None,
) -> StratagemUseRecord:
    state = _state(lifecycle)
    result = _more_dakka_stratagem_decision_result(
        lifecycle,
        stratagem_id=stratagem_id,
        target_unit_id=target_unit_id,
        phase=phase,
        command_points=command_points,
        active_player_id=active_player_id,
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )
    lifecycle.decision_controller.submit_result(result)
    config = object.__getattribute__(lifecycle, "_config")
    if type(config) is not GameConfig:
        raise AssertionError("Lifecycle config was not loaded.")
    use_record = apply_stratagem_decision(
        state=state,
        result=result,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        stratagem_handler_registry=(_runtime_content_bundle(lifecycle).stratagem_handler_registry),
        stratagem_cost_modifier_registry=(
            _runtime_content_bundle(lifecycle).stratagem_cost_modifier_registry
        ),
        shooting_unit_selected_grant_hooks=(
            _runtime_content_bundle(lifecycle).shooting_unit_selected_grant_hook_registry
        ),
    )
    assert state.stratagem_use_records[-1] == use_record
    return use_record


def _use_more_dakka_stratagem_through_lifecycle(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int = 1,
    active_player_id: str = "player-a",
    trigger_kind: TimingTriggerKind = TimingTriggerKind.START_PHASE,
    trigger_payload: JsonValue = None,
) -> tuple[StratagemUseRecord, LifecycleStatus]:
    state = _state(lifecycle)
    result = _more_dakka_stratagem_decision_result(
        lifecycle,
        stratagem_id=stratagem_id,
        target_unit_id=target_unit_id,
        phase=phase,
        command_points=command_points,
        active_player_id=active_player_id,
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )
    status = lifecycle.submit_decision(result)
    use_record = state.stratagem_use_records[-1]
    assert use_record.stratagem_id == stratagem_id
    assert use_record.targeted_unit_instance_ids == (target_unit_id,)
    return use_record, status


def _use_spectacle_stratagem(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int = 1,
    active_player_id: str = "player-a",
    trigger_kind: TimingTriggerKind = TimingTriggerKind.START_PHASE,
    trigger_payload: JsonValue = None,
) -> StratagemUseRecord:
    state = _state(lifecycle)
    result = _spectacle_stratagem_decision_result(
        lifecycle,
        stratagem_id=stratagem_id,
        target_unit_id=target_unit_id,
        phase=phase,
        command_points=command_points,
        active_player_id=active_player_id,
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )
    lifecycle.decision_controller.submit_result(result)
    config = object.__getattribute__(lifecycle, "_config")
    if type(config) is not GameConfig:
        raise AssertionError("Lifecycle config was not loaded.")
    use_record = apply_stratagem_decision(
        state=state,
        result=result,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        stratagem_handler_registry=(_runtime_content_bundle(lifecycle).stratagem_handler_registry),
        stratagem_cost_modifier_registry=(
            _runtime_content_bundle(lifecycle).stratagem_cost_modifier_registry
        ),
        shooting_unit_selected_grant_hooks=(
            _runtime_content_bundle(lifecycle).shooting_unit_selected_grant_hook_registry
        ),
    )
    assert state.stratagem_use_records[-1] == use_record
    return use_record


def _use_spectacle_stratagem_through_lifecycle(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int = 1,
    active_player_id: str = "player-a",
    trigger_kind: TimingTriggerKind = TimingTriggerKind.START_PHASE,
    trigger_payload: JsonValue = None,
) -> tuple[StratagemUseRecord, LifecycleStatus]:
    state = _state(lifecycle)
    result = _spectacle_stratagem_decision_result(
        lifecycle,
        stratagem_id=stratagem_id,
        target_unit_id=target_unit_id,
        phase=phase,
        command_points=command_points,
        active_player_id=active_player_id,
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )
    status = lifecycle.submit_decision(result)
    use_record = state.stratagem_use_records[-1]
    assert use_record.stratagem_id == stratagem_id
    assert use_record.targeted_unit_instance_ids == (target_unit_id,)
    return use_record, status


def _use_court_stratagem(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int = 1,
    active_player_id: str = "player-a",
    trigger_kind: TimingTriggerKind = TimingTriggerKind.DURING_PHASE,
    trigger_payload: JsonValue = None,
) -> StratagemUseRecord:
    state = _state(lifecycle)
    result = _court_stratagem_decision_result(
        lifecycle,
        stratagem_id=stratagem_id,
        target_unit_id=target_unit_id,
        phase=phase,
        command_points=command_points,
        active_player_id=active_player_id,
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )
    lifecycle.decision_controller.submit_result(result)
    config = object.__getattribute__(lifecycle, "_config")
    if type(config) is not GameConfig:
        raise AssertionError("Lifecycle config was not loaded.")
    use_record = apply_stratagem_decision(
        state=state,
        result=result,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        stratagem_handler_registry=(_runtime_content_bundle(lifecycle).stratagem_handler_registry),
        stratagem_cost_modifier_registry=(
            _runtime_content_bundle(lifecycle).stratagem_cost_modifier_registry
        ),
        shooting_unit_selected_grant_hooks=(
            _runtime_content_bundle(lifecycle).shooting_unit_selected_grant_hook_registry
        ),
    )
    assert state.stratagem_use_records[-1] == use_record
    return use_record


def _use_court_stratagem_through_lifecycle(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int = 1,
    active_player_id: str = "player-a",
    trigger_kind: TimingTriggerKind = TimingTriggerKind.DURING_PHASE,
    trigger_payload: JsonValue = None,
) -> tuple[StratagemUseRecord, LifecycleStatus]:
    state = _state(lifecycle)
    result = _court_stratagem_decision_result(
        lifecycle,
        stratagem_id=stratagem_id,
        target_unit_id=target_unit_id,
        phase=phase,
        command_points=command_points,
        active_player_id=active_player_id,
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )
    status = lifecycle.submit_decision(result)
    use_record = state.stratagem_use_records[-1]
    assert use_record.stratagem_id == stratagem_id
    assert use_record.targeted_unit_instance_ids == (target_unit_id,)
    return use_record, status


def _more_dakka_stratagem_decision_result(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int,
    active_player_id: str,
    trigger_kind: TimingTriggerKind,
    trigger_payload: JsonValue,
) -> DecisionResult:
    state = _state(lifecycle)
    _prepare_battle_phase(state, phase=phase, active_player_id=active_player_id)
    _grant_cp(state, player_id="player-a", amount=command_points)
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-a",
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )
    status = request_stratagem_use_from_index(
        state=state,
        decisions=lifecycle.decision_controller,
        index=_runtime_content_bundle(lifecycle).stratagem_indexes_by_player_id["player-a"],
        context=context,
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = lifecycle.pending_decision_request()
    assert request is not None
    selected_option = next(
        option
        for option in request.options
        if _option_stratagem_id(option.payload) == stratagem_id
        and _option_target_unit_id(option.payload) == target_unit_id
    )
    return DecisionResult.for_request(
        result_id=f"ws14-more-dakka-{stratagem_id}-result",
        request=request,
        selected_option_id=selected_option.option_id,
    )


def _spectacle_stratagem_decision_result(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int,
    active_player_id: str,
    trigger_kind: TimingTriggerKind,
    trigger_payload: JsonValue,
) -> DecisionResult:
    state = _state(lifecycle)
    _prepare_battle_phase(state, phase=phase, active_player_id=active_player_id)
    _grant_cp(state, player_id="player-a", amount=command_points)
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-a",
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )
    status = request_stratagem_use_from_index(
        state=state,
        decisions=lifecycle.decision_controller,
        index=_runtime_content_bundle(lifecycle).stratagem_indexes_by_player_id["player-a"],
        context=context,
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = lifecycle.pending_decision_request()
    assert request is not None
    selected_option = next(
        option
        for option in request.options
        if _option_stratagem_id(option.payload) == stratagem_id
        and _option_target_unit_id(option.payload) == target_unit_id
    )
    return DecisionResult.for_request(
        result_id=f"ws14-spectacle-{stratagem_id}-result",
        request=request,
        selected_option_id=selected_option.option_id,
    )


def _court_stratagem_decision_result(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int,
    active_player_id: str,
    trigger_kind: TimingTriggerKind,
    trigger_payload: JsonValue,
) -> DecisionResult:
    state = _state(lifecycle)
    _prepare_battle_phase(state, phase=phase, active_player_id=active_player_id)
    if command_points > 0:
        _grant_cp(state, player_id="player-a", amount=command_points)
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-a",
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )
    status = request_stratagem_use_from_index(
        state=state,
        decisions=lifecycle.decision_controller,
        index=_runtime_content_bundle(lifecycle).stratagem_indexes_by_player_id["player-a"],
        context=context,
        stratagem_cost_modifier_registry=(
            _runtime_content_bundle(lifecycle).stratagem_cost_modifier_registry
        ),
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = lifecycle.pending_decision_request()
    assert request is not None
    selected_option = next(
        option
        for option in request.options
        if _option_stratagem_id(option.payload) == stratagem_id
        and _option_target_unit_id(option.payload) == target_unit_id
    )
    return DecisionResult.for_request(
        result_id=f"ws14-court-{stratagem_id}-result",
        request=request,
        selected_option_id=selected_option.option_id,
    )


def _grant_cp(state: GameState, *, player_id: str, amount: int) -> None:
    result = state.gain_command_points(
        player_id=player_id,
        amount=amount,
        source_id=f"ws14-more-dakka-grant:{player_id}:{amount}",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    assert result.status is CommandPointGainStatus.APPLIED


def _record_fixed_secondary_choices_for_fixture(
    state: GameState,
    *,
    config: GameConfig,
) -> None:
    for player_id in config.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=config.fixed_secondary_mission_ids,
            )
        )


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Expected a JSON object.")
    return value


def _option_stratagem_id(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Stratagem option payload must be an object.")
    catalog_record = payload.get("catalog_record")
    if not isinstance(catalog_record, dict):
        raise GameLifecycleError("Stratagem option payload is missing catalog_record.")
    definition = catalog_record.get("definition")
    if not isinstance(definition, dict):
        raise GameLifecycleError("Stratagem option payload is missing definition.")
    stratagem_id = definition.get("stratagem_id")
    if stratagem_id is None:
        return None
    if type(stratagem_id) is not str:
        raise GameLifecycleError("Stratagem option stratagem_id must be a string.")
    return stratagem_id


def _option_target_unit_id(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Stratagem option payload must be an object.")
    target_binding = payload.get("target_binding")
    if not isinstance(target_binding, dict):
        raise GameLifecycleError("Stratagem option payload is missing target_binding.")
    target_unit_id = target_binding.get("target_unit_instance_id")
    if target_unit_id is None:
        return None
    if type(target_unit_id) is not str:
        raise GameLifecycleError("Stratagem option target_unit_instance_id must be a string.")
    return target_unit_id


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            return _json_object(event.payload)
    raise AssertionError(f"Missing event type: {event_type}")


def _mob_shoota_profile() -> WeaponProfile:
    return next(
        wargear
        for wargear in _more_dakka_catalog().wargear
        if wargear.wargear_id == "core-mob-shoota"
    ).weapon_profiles[0]


def _leader_blade_profile() -> WeaponProfile:
    return next(
        wargear
        for wargear in _spectacle_catalog().wargear
        if wargear.wargear_id == "core-leader-blade"
    ).weapon_profiles[0]


def _court_blade_profile() -> WeaponProfile:
    return next(
        wargear for wargear in _court_catalog().wargear if wargear.wargear_id == "core-leader-blade"
    ).weapon_profiles[0]


def _court_shoota_profile() -> WeaponProfile:
    return next(
        wargear for wargear in _court_catalog().wargear if wargear.wargear_id == "core-mob-shoota"
    ).weapon_profiles[0]


def _spectacle_weapon_profile_context(
    *,
    state: GameState,
    weapon_profile: WeaponProfile,
    attacker_model_id: str,
    source_phase: BattlePhase,
    attacking_unit_id: str = "army-alpha:blades-1",
    target_unit_id: str = "army-beta:blades-3",
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=state,
        source_phase=source_phase,
        attacking_unit_instance_id=attacking_unit_id,
        attacker_model_instance_id=attacker_model_id,
        target_unit_instance_id=target_unit_id,
        weapon_profile=weapon_profile,
    )


def _court_weapon_profile_context(
    *,
    state: GameState,
    weapon_profile: WeaponProfile,
    attacker_model_id: str,
    attacking_unit_id: str,
    target_unit_id: str,
    source_phase: BattlePhase,
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=state,
        source_phase=source_phase,
        attacking_unit_instance_id=attacking_unit_id,
        attacker_model_instance_id=attacker_model_id,
        target_unit_instance_id=target_unit_id,
        weapon_profile=weapon_profile,
    )


def _weapon_profile_context(
    *,
    state: GameState,
    weapon_profile: WeaponProfile,
    attacker_model_id: str,
    attacking_unit_id: str = "army-alpha:boyz-1",
    target_unit_id: str = "army-beta:boyz-2",
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=attacking_unit_id,
        attacker_model_instance_id=attacker_model_id,
        target_unit_instance_id=target_unit_id,
        weapon_profile=weapon_profile,
    )


def _profile_has_ability(profile: WeaponProfile, ability_kind: AbilityKind) -> bool:
    return any(ability.ability_kind is ability_kind for ability in profile.abilities)


def _first_model_id(state: GameState, *, unit_instance_id: str) -> str:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit.own_models[0].model_instance_id
    raise AssertionError(f"Missing unit: {unit_instance_id}")


def _place_units_for_more_dakka_shooting(state: GameState) -> None:
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:boyz-1",
        poses=tuple(
            Pose.at(x=(index % 5) * 1.5, y=10.0 + (index // 5) * 1.5) for index in range(10)
        ),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:boyz-2",
        poses=tuple(
            Pose.at(x=10.0 + (index % 5) * 1.5, y=10.0 + (index // 5) * 1.5) for index in range(10)
        ),
    )
    _clear_terrain(state)


def _place_units_for_court_within_12(state: GameState) -> None:
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:fulgrim-1",
        poses=tuple(
            Pose.at(x=10.0 + (index % 5) * 1.5, y=10.0 + (index // 5) * 1.5) for index in range(10)
        ),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-character-1",
        poses=tuple(
            Pose.at(x=16.0 + (index % 5) * 1.5, y=10.0 + (index // 5) * 1.5) for index in range(10)
        ),
    )
    _clear_terrain(state)


def _record_charge_move_effect(state: GameState, *, unit_instance_id: str) -> None:
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"ws14-court:charge-move:{unit_instance_id}:{state.battle_round}",
            source_rule_id="core-rules:charge-move",
            owner_player_id="player-a",
            target_unit_instance_ids=(unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.CHARGE,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id="player-a",
            ),
            effect_payload={"effect_kind": CHARGE_FIGHTS_FIRST_EFFECT_KIND},
        )
    )


def _replace_unit_poses(
    state: GameState,
    *,
    unit_instance_id: str,
    poses: tuple[Pose, ...],
) -> None:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    assert len(placement.model_placements) == len(poses)
    state.replace_battlefield_state(
        battlefield_state.with_unit_placement(
            placement.with_model_placements(
                tuple(
                    model_placement.with_pose(pose)
                    for model_placement, pose in zip(placement.model_placements, poses, strict=True)
                )
            )
        )
    )


def _clear_terrain(state: GameState) -> None:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    state.battlefield_state = replace(battlefield_state, terrain_features=())


def _effect_parameter(effect_payload: dict[str, JsonValue], key: str) -> JsonValue:
    parameters = effect_payload.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Expected RuleIR effect parameters.")
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise GameLifecycleError("Expected RuleIR effect parameter object.")
        if parameter.get("key") == key:
            return parameter.get("value")
    return None
