from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.unit.test_phase11c_command_phase import (
    _battle_state,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.faction_aliases import (
    CHAOS_DAEMONS_FACTION_ID,
    CHAOS_SPACE_MARINES_FACTION_ID,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    FightOrderingBandKind,
    FightTypeKind,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.advance_eligibility_hooks import AdvanceEligibilityContext
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    AttachedUnitFormation,
    EnhancementAssignment,
    RosterUnitPointValue,
    WarlordSelection,
    muster_army,
    validate_roster_legality,
)
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHookRegistry,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.damage_allocation import (
    FeelNoPainSource,
    feel_no_pain_roll_spec,
    is_mortal_wound_feel_no_pain_request,
    mortal_wound_feel_no_pain_source_context,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.enhancement_effects import (
    EnhancementEffectRegistry,
    apply_enhancement_effects,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.shadow_legion import (  # noqa: E501
    enhancements,
    rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule as dark_pacts,
)
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    FightPhaseStartHookRegistry,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import FightUnitSelectedContext
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    BattleSize,
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
    MortalWoundFeelNoPainContinuationHookRegistry,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.phases.fight import (
    FightPhaseHandler,
    invalid_fight_phase_start_faction_rule_status,
)
from warhammer40k_core.engine.phases.shooting import (
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingPhaseHandler,
    ShootingPhaseState,
    ShootingUnitSelection,
    _apply_shooting_unit_selected_grant_decision,
    _request_shooting_unit_selected_grant_decision_if_available,
    request_out_of_phase_shooting_declaration,
)
from warhammer40k_core.engine.prebattle import scout_ability_instances_for_rules_unit
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
    ShootingUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.target_restriction_hooks import ShootingTargetRestrictionContext
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_abilities import (
    scouts_ability_descriptors_for_unit,
    scouts_distance_inches_from_descriptor,
)
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import FIRE_OVERWATCH_RULE_ID
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose

_DAEMON_DATASHEET_ID = "phase17g-shadow-legion-daemon"
_BELAKOR_DATASHEET_ID = "phase17g-shadow-legion-belakor"
_CHAOS_LORD_DATASHEET_ID = "phase17g-shadow-legion-chaos-lord"
_DAMNED_DATASHEET_ID = "phase17g-shadow-legion-damned"
_DAEMON_PRINCE_DATASHEET_ID = "phase17g-shadow-legion-daemon-prince"
_EPIC_HERO_DATASHEET_ID = "phase17g-shadow-legion-epic-hero"
_NOISE_MARINES_DATASHEET_ID = "phase17g-shadow-legion-noise-marines"


def test_shadow_legion_runtime_contribution_registers_engine_hooks() -> None:
    contribution = rule.runtime_contribution()
    shooting_grant_hook_ids = {
        binding.hook_id for binding in contribution.shooting_unit_selected_grant_hook_bindings
    }
    fight_grant_hook_ids = {
        binding.hook_id for binding in contribution.fight_unit_selected_grant_hook_bindings
    }

    assert contribution.contribution_id == rule.CONTRIBUTION_ID
    assert contribution.advance_eligibility_hook_bindings[0].hook_id == (
        rule.ADVANCE_ELIGIBILITY_HOOK_ID
    )
    assert contribution.shooting_target_restriction_hook_bindings[0].hook_id == (
        rule.SLAANESH_TARGET_RESTRICTION_HOOK_ID
    )
    assert shooting_grant_hook_ids == {
        rule.SHOOTING_LETHAL_HITS_HOOK_ID,
        rule.SHOOTING_SUSTAINED_HITS_HOOK_ID,
    }
    assert fight_grant_hook_ids == {
        rule.FIGHT_LETHAL_HITS_HOOK_ID,
        rule.FIGHT_SUSTAINED_HITS_HOOK_ID,
    }
    assert contribution.attack_sequence_completed_hook_bindings[0].hook_id == (
        rule.ATTACK_SEQUENCE_COMPLETED_HOOK_ID
    )
    assert contribution.mortal_wound_feel_no_pain_hook_bindings[0].source_kind == (
        dark_pacts.SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND
    )
    assert contribution.hit_roll_modifier_bindings[0].modifier_id == rule.TZEENTCH_HIT_MODIFIER_ID
    assert contribution.wound_roll_modifier_bindings[0].modifier_id == (
        rule.NURGLE_WOUND_MODIFIER_ID
    )
    assert contribution.weapon_profile_modifier_bindings[0].modifier_id == (
        rule.WEAPON_PROFILE_MODIFIER_ID
    )


def test_shadow_legion_enhancement_runtime_contribution_registers_exact_hooks() -> None:
    contribution = enhancements.runtime_contribution()

    assert contribution.contribution_id == enhancements.CONTRIBUTION_ID
    assert (
        contribution.contribution_id
        == "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:enhancements"
    )
    assert "fade_to_darkness" not in contribution.contribution_id
    assert not contribution.contribution_id.endswith(":scaffold")
    assert contribution.enhancement_effect_bindings[0].effect_id == (
        enhancements.LEAPING_SHADOWS_EFFECT_ID
    )
    assert contribution.enhancement_effect_bindings[0].source_id == (
        enhancements.LEAPING_SHADOWS_SOURCE_RULE_ID
    )
    assert contribution.enhancement_effect_bindings[0].enhancement_id == (
        enhancements.LEAPING_SHADOWS_ENHANCEMENT_ID
    )
    assert contribution.objective_control_modifier_bindings[0].modifier_id == (
        enhancements.MANTLE_OF_GLOOM_OBJECTIVE_CONTROL_MODIFIER_ID
    )
    assert contribution.objective_control_modifier_bindings[0].source_id == (
        enhancements.MANTLE_OF_GLOOM_SOURCE_RULE_ID
    )
    assert contribution.unit_destroyed_hook_bindings[0].hook_id == (
        enhancements.UNIT_DESTROYED_HOOK_ID
    )
    assert contribution.unit_destroyed_hook_bindings[0].source_id == enhancements.SOURCE_RULE_ID
    assert contribution.turn_end_hook_bindings[0].hook_id == enhancements.TURN_END_HOOK_ID
    assert contribution.turn_end_hook_bindings[0].source_id == enhancements.SOURCE_RULE_ID
    assert contribution.fight_phase_start_hook_bindings[0].hook_id == (
        enhancements.MALICE_MADE_MANIFEST_HOOK_ID
    )
    assert contribution.fight_phase_start_hook_bindings[0].source_id == (
        enhancements.MALICE_MADE_MANIFEST_SOURCE_RULE_ID
    )
    assert contribution.mortal_wound_feel_no_pain_hook_bindings[0].hook_id == (
        enhancements.MALICE_MADE_MANIFEST_MORTAL_WOUND_FNP_HOOK_ID
    )
    assert contribution.mortal_wound_feel_no_pain_hook_bindings[0].source_kind == (
        enhancements.MALICE_MADE_MANIFEST_MORTAL_WOUNDS_SOURCE_KIND
    )


def test_leaping_shadows_grants_scouts_nine_to_bearers_attached_rules_unit() -> None:
    state = _shadow_legion_state(
        unit_keywords=("Shadow Legion", "Undivided", "Character"),
        player_a_unit_selection_ids=("bodyguard-unit", "leader-unit"),
    )
    bodyguard = _unit_for_player_by_index(state, player_id="player-a", index=0)
    leader = _unit_for_player_by_index(state, player_id="player-a", index=1)
    _attach_shadow_legion_units(state, bodyguard=bodyguard, leader=leader)
    _assign_leaping_shadows(state, unit=leader)
    decisions = DecisionController()

    apply_enhancement_effects(
        state=state,
        registry=EnhancementEffectRegistry.from_bindings(
            enhancements.runtime_contribution().enhancement_effect_bindings
        ),
        decisions=decisions,
    )
    apply_enhancement_effects(
        state=state,
        registry=EnhancementEffectRegistry.from_bindings(
            enhancements.runtime_contribution().enhancement_effect_bindings
        ),
        decisions=decisions,
    )

    refreshed_bodyguard = _refreshed_unit(state, bodyguard)
    refreshed_leader = _refreshed_unit(state, leader)
    bodyguard_scouts = scouts_ability_descriptors_for_unit(refreshed_bodyguard)
    leader_scouts = scouts_ability_descriptors_for_unit(refreshed_leader)
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=leader.unit_instance_id)
    scout_instances = scout_ability_instances_for_rules_unit(
        view=rules_unit,
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
    )

    assert [
        scouts_distance_inches_from_descriptor(descriptor) for descriptor in bodyguard_scouts
    ] == [9.0]
    leader_scout_distances = [
        scouts_distance_inches_from_descriptor(descriptor) for descriptor in leader_scouts
    ]
    assert leader_scout_distances == [9.0]
    assert {descriptor.source_id for descriptor in (*bodyguard_scouts, *leader_scouts)} == {
        enhancements.LEAPING_SHADOWS_SOURCE_RULE_ID
    }
    assert {instance.distance_inches for instance in scout_instances} == {9.0}
    assert {instance.source_id for instance in scout_instances} == {
        enhancements.LEAPING_SHADOWS_SOURCE_RULE_ID
    }
    assert _event_count(decisions, "enhancement_effects_applied") == 1
    effect_event = _last_event_payload(decisions, "enhancement_effects_applied")
    effect_payloads = cast(list[JsonValue], effect_event["effects"])
    applied_target_unit_ids: set[str] = set()
    for payload in effect_payloads:
        effect_payload = cast(dict[str, JsonValue], payload)
        target_unit_instance_id = effect_payload["target_unit_instance_id"]
        assert isinstance(target_unit_instance_id, str)
        applied_target_unit_ids.add(target_unit_instance_id)
    assert applied_target_unit_ids == {bodyguard.unit_instance_id, leader.unit_instance_id}


def test_mantle_of_gloom_reduces_enemy_oc_in_engagement_with_bearers_attached_unit() -> None:
    state = _shadow_legion_state(
        unit_keywords=("Shadow Legion", "Undivided", "Character"),
        player_a_unit_selection_ids=("bodyguard-unit", "leader-unit"),
    )
    bodyguard = _unit_for_player_by_index(state, player_id="player-a", index=0)
    leader = _unit_for_player_by_index(state, player_id="player-a", index=1)
    target = _unit_for_player(state, player_id="player-b")
    _attach_shadow_legion_units(state, bodyguard=bodyguard, leader=leader)
    _assign_mantle_of_gloom(state, unit=leader)
    _place_unit_poses(
        state,
        unit_instance_id=bodyguard.unit_instance_id,
        poses=_unit_line_poses(x=10.0, y=20.0),
    )
    _place_unit_poses(
        state,
        unit_instance_id=leader.unit_instance_id,
        poses=_unit_line_poses(x=30.0, y=20.0),
    )
    _place_unit_poses(
        state,
        unit_instance_id=target.unit_instance_id,
        poses=_unit_line_poses(x=12.0, y=20.0),
    )
    registry = RuntimeModifierRegistry.from_bindings(
        objective_control_modifier_bindings=(
            enhancements.runtime_contribution().objective_control_modifier_bindings
        )
    )

    assert (
        enhancements.mantle_of_gloom_modified_objective_control(
            state=state,
            unit_instance_id=target.unit_instance_id,
            current_objective_control=2,
        )
        == 1
    )
    assert (
        enhancements.mantle_of_gloom_modified_objective_control(
            state=state,
            unit_instance_id=target.unit_instance_id,
            current_objective_control=1,
        )
        == 0
    )
    assert (
        registry.modified_objective_control(
            ObjectiveControlModifierContext(
                state=state,
                unit_instance_id=target.unit_instance_id,
                model_instance_id=target.own_models[0].model_instance_id,
                base_objective_control=2,
                current_objective_control=2,
            )
        )
        == 1
    )
    assert (
        registry.modified_objective_control(
            ObjectiveControlModifierContext(
                state=state,
                unit_instance_id=bodyguard.unit_instance_id,
                model_instance_id=bodyguard.own_models[0].model_instance_id,
                base_objective_control=2,
                current_objective_control=2,
            )
        )
        == 2
    )


def test_mantle_of_gloom_ignores_enemy_units_outside_engagement_range() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided", "Character"))
    bearer = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_mantle_of_gloom(state, unit=bearer)
    _place_unit_poses(
        state,
        unit_instance_id=bearer.unit_instance_id,
        poses=_unit_line_poses(x=10.0, y=20.0),
    )
    _place_unit_poses(
        state,
        unit_instance_id=target.unit_instance_id,
        poses=_unit_line_poses(x=30.0, y=20.0),
    )

    assert (
        enhancements.mantle_of_gloom_modified_objective_control(
            state=state,
            unit_instance_id=target.unit_instance_id,
            current_objective_control=2,
        )
        == 2
    )


def test_mantle_of_gloom_requires_living_bearer_in_attached_rules_unit() -> None:
    state = _shadow_legion_state(
        unit_keywords=("Shadow Legion", "Undivided", "Character"),
        player_a_unit_selection_ids=("bodyguard-unit", "leader-unit"),
    )
    bodyguard = _unit_for_player_by_index(state, player_id="player-a", index=0)
    leader = _unit_for_player_by_index(state, player_id="player-a", index=1)
    target = _unit_for_player(state, player_id="player-b")
    _attach_shadow_legion_units(state, bodyguard=bodyguard, leader=leader)
    _assign_mantle_of_gloom(state, unit=leader)
    _place_unit_poses(
        state,
        unit_instance_id=bodyguard.unit_instance_id,
        poses=_unit_line_poses(x=10.0, y=20.0),
    )
    _place_unit_poses(
        state,
        unit_instance_id=leader.unit_instance_id,
        poses=_unit_line_poses(x=30.0, y=20.0),
    )
    _place_unit_poses(
        state,
        unit_instance_id=target.unit_instance_id,
        poses=_unit_line_poses(x=12.0, y=20.0),
    )
    _destroy_unit_own_models(state, unit_instance_id=leader.unit_instance_id)

    assert (
        enhancements.mantle_of_gloom_modified_objective_control(
            state=state,
            unit_instance_id=target.unit_instance_id,
            current_objective_control=2,
        )
        == 2
    )


def test_mantle_of_gloom_assignment_requires_shadow_legion_bearer() -> None:
    state = _shadow_legion_state(unit_keywords=("Undivided", "Character"))
    bearer = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_mantle_of_gloom(state, unit=bearer)
    _place_malice_made_manifest_engagement(state, bearer=bearer, target=target)

    with pytest.raises(
        GameLifecycleError, match=r"Mantle of Gloom requires a Shadow Legion model\."
    ):
        enhancements.mantle_of_gloom_modified_objective_control(
            state=state,
            unit_instance_id=target.unit_instance_id,
            current_objective_control=2,
        )


def test_malice_made_manifest_fight_start_applies_three_mortal_wounds_on_six() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided", "Character"))
    state.game_id = "j"
    bearer = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_malice_made_manifest(state, unit=bearer)
    _place_malice_made_manifest_engagement(state, bearer=bearer, target=target)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()
    starting_wounds = sum(model.wounds_remaining for model in target.own_models)

    request = _decision_request(
        enhancements.malice_made_manifest_fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
    )

    assert request.decision_type == SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["source_rule_id"] == enhancements.MALICE_MADE_MANIFEST_SOURCE_RULE_ID
    assert request_payload["hook_id"] == enhancements.MALICE_MADE_MANIFEST_HOOK_ID
    assert request_payload["enhancement_id"] == enhancements.MALICE_MADE_MANIFEST_ENHANCEMENT_ID
    assert request_payload["bearer_unit_instance_id"] == bearer.unit_instance_id
    assert request_payload["eligible_enemy_unit_instance_ids"] == [target.unit_instance_id]

    result = DecisionResult.for_request(
        result_id="result-malice-made-manifest-six",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    handled = enhancements.apply_malice_made_manifest_fight_phase_start_result(
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert handled is True
    payload = _last_event_payload(decisions, enhancements.MALICE_MADE_MANIFEST_RESOLVED_EVENT)
    assert payload["source_rule_id"] == enhancements.MALICE_MADE_MANIFEST_SOURCE_RULE_ID
    assert payload["hook_id"] == enhancements.MALICE_MADE_MANIFEST_HOOK_ID
    assert payload["target_enemy_unit_instance_id"] == target.unit_instance_id
    assert payload["mortal_wounds"] == 3
    d6_payload = cast(dict[str, JsonValue], payload["d6_result"])
    assert d6_payload["current_total"] == 6
    application = cast(dict[str, JsonValue], payload["mortal_wound_application"])
    assert application["mortal_wounds"] == 3
    assert (
        starting_wounds
        - sum(model.wounds_remaining for model in _refreshed_unit(state, target).own_models)
        == 3
    )
    assert (
        enhancements.malice_made_manifest_fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
        is None
    )


def test_malice_made_manifest_routes_mortal_wound_feel_no_pain_choice() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided", "Character"))
    state.game_id = "phase17g-malice-actual-7"
    bearer = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_malice_made_manifest(state, unit=bearer)
    _place_malice_made_manifest_engagement(state, bearer=bearer, target=target)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    source_a = FeelNoPainSource(source_id="malice-fnp-a", threshold=5)
    source_b = FeelNoPainSource(source_id="malice-fnp-b", threshold=6)
    state.record_model_feel_no_pain_sources(
        model_instance_id=target.own_models[0].model_instance_id,
        sources=(source_a, source_b),
    )
    decisions = DecisionController()
    starting_wounds = sum(model.wounds_remaining for model in target.own_models)
    request = _decision_request(
        enhancements.malice_made_manifest_fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
    )
    result = DecisionResult.for_request(
        result_id="result-malice-made-manifest-fnp",
        request=request,
        selected_option_id=request.options[0].option_id,
    )

    status = enhancements.apply_malice_made_manifest_fight_phase_start_result(
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert type(status) is not bool
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    fnp_request = _decision_request(status.decision_request)
    assert is_mortal_wound_feel_no_pain_request(fnp_request)
    source_context = mortal_wound_feel_no_pain_source_context(fnp_request)
    assert isinstance(source_context, dict)
    assert source_context["source_kind"] == (
        enhancements.MALICE_MADE_MANIFEST_MORTAL_WOUNDS_SOURCE_KIND
    )
    pending_payload = cast(dict[str, JsonValue], source_context["resolution_payload"])
    assert pending_payload["hook_id"] == enhancements.MALICE_MADE_MANIFEST_HOOK_ID
    assert pending_payload["mortal_wounds"] == 1
    assert {option.option_id for option in fnp_request.options} == {
        source_a.source_id,
        source_b.source_id,
    }

    fnp_result = DecisionResult.for_request(
        result_id="result-malice-fnp-source-a",
        request=fnp_request,
        selected_option_id=source_a.source_id,
    )
    decisions.submit_result(fnp_result)
    continuation_status = MortalWoundFeelNoPainContinuationHookRegistry.from_bindings(
        enhancements.runtime_contribution().mortal_wound_feel_no_pain_hook_bindings
    ).apply_decision(
        MortalWoundFeelNoPainContinuationContext(
            state=state,
            decisions=decisions,
            request=fnp_request,
            result=fnp_result,
            source_context=source_context,
            dice_manager=DiceRollManager(
                state.game_id,
                event_log=decisions.event_log,
                injected_results=(
                    DiceRollResult.from_values(
                        roll_id="malice-fnp-roll",
                        spec=feel_no_pain_roll_spec(
                            source=source_a,
                            player_id="player-b",
                            model_instance_id=target.own_models[0].model_instance_id,
                            wound_index=1,
                        ),
                        values=(1,),
                        source="fixed",
                    ),
                ),
            ),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )

    assert continuation_status is None
    payload = _last_event_payload(decisions, enhancements.MALICE_MADE_MANIFEST_RESOLVED_EVENT)
    assert payload["feel_no_pain_result_id"] == fnp_result.result_id
    application = cast(dict[str, JsonValue], payload["mortal_wound_application"])
    assert application["mortal_wounds"] == 1
    assert (
        starting_wounds
        - sum(model.wounds_remaining for model in _refreshed_unit(state, target).own_models)
        == 1
    )


def test_malice_made_manifest_fight_handler_requests_and_resolves_start_choice() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided", "Character"))
    state.game_id = "j"
    bearer = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_malice_made_manifest(state, unit=bearer)
    _place_malice_made_manifest_engagement(state, bearer=bearer, target=target)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()
    handler = FightPhaseHandler(
        fight_phase_start_hooks=FightPhaseStartHookRegistry.from_bindings(
            enhancements.runtime_contribution().fight_phase_start_hook_bindings
        ),
    )

    status = handler.begin_phase(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = _decision_request(status.decision_request)
    assert request.decision_type == SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE
    result = DecisionResult.for_request(
        result_id="result-malice-made-manifest-handler",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    assert (
        invalid_fight_phase_start_faction_rule_status(
            state=state,
            request=request,
            result=result,
        )
        is None
    )
    decisions.submit_result(result)

    resolved_status = handler.apply_decision(
        state=state,
        result=result,
        decisions=decisions,
    )

    assert resolved_status is None
    assert decisions.records[-1].result == result
    payload = _last_event_payload(decisions, enhancements.MALICE_MADE_MANIFEST_RESOLVED_EVENT)
    assert payload["target_enemy_unit_instance_id"] == target.unit_instance_id
    assert payload["mortal_wounds"] == 3


def test_malice_made_manifest_fight_start_rejects_battle_round_drift_before_recording() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided", "Character"))
    state.game_id = "phase17g-malice-drift"
    bearer = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_malice_made_manifest(state, unit=bearer)
    _place_malice_made_manifest_engagement(state, bearer=bearer, target=target)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()
    request = _decision_request(
        enhancements.malice_made_manifest_fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
    )
    result = DecisionResult.for_request(
        result_id="result-malice-made-manifest-drift",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    state.battle_round += 1

    rejected = invalid_fight_phase_start_faction_rule_status(
        state=state,
        request=request,
        result=result,
    )

    assert rejected is not None
    assert rejected.status_kind is LifecycleStatusKind.INVALID
    rejected_payload = cast(dict[str, JsonValue], rejected.payload)
    assert rejected_payload["invalid_reason"] == "battle_round_drift"
    assert decisions.records == ()
    assert (
        tuple(
            event
            for event in decisions.event_log.records
            if event.event_type == enhancements.MALICE_MADE_MANIFEST_RESOLVED_EVENT
        )
        == ()
    )


def test_malice_made_manifest_fight_start_records_no_effect_on_one() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided", "Character"))
    state.game_id = "malice-seed-2"
    bearer = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_malice_made_manifest(state, unit=bearer)
    _place_malice_made_manifest_engagement(state, bearer=bearer, target=target)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()
    starting_wounds = sum(model.wounds_remaining for model in target.own_models)
    request = _decision_request(
        enhancements.malice_made_manifest_fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
    )
    result = DecisionResult.for_request(
        result_id="result-malice-made-manifest-one",
        request=request,
        selected_option_id=request.options[0].option_id,
    )

    handled = enhancements.apply_malice_made_manifest_fight_phase_start_result(
        FightPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert handled is True
    payload = _last_event_payload(decisions, enhancements.MALICE_MADE_MANIFEST_NO_EFFECT_EVENT)
    d6_payload = cast(dict[str, JsonValue], payload["d6_result"])
    assert d6_payload["current_total"] == 1
    assert payload["mortal_wounds"] == 0
    assert payload["target_enemy_unit_instance_id"] == target.unit_instance_id
    assert (
        sum(model.wounds_remaining for model in _refreshed_unit(state, target).own_models)
        == starting_wounds
    )
    assert (
        enhancements.malice_made_manifest_fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
        is None
    )


def test_malice_made_manifest_request_requires_fight_start_context() -> None:
    with pytest.raises(GameLifecycleError, match=r"requires a Fight-start context"):
        enhancements.malice_made_manifest_fight_phase_start_request(
            cast(FightPhaseStartRequestContext, object())
        )


def test_malice_made_manifest_rejects_target_drift_before_damage() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided", "Character"))
    bearer = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_malice_made_manifest(state, unit=bearer)
    _place_malice_made_manifest_engagement(state, bearer=bearer, target=target)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()
    request = _decision_request(
        enhancements.malice_made_manifest_fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
    )
    result = DecisionResult.for_request(
        result_id="result-malice-made-manifest-target-drift",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    _place_unit_poses(
        state,
        unit_instance_id=target.unit_instance_id,
        poses=_unit_line_poses(x=40.0, y=40.0),
    )

    with pytest.raises(GameLifecycleError, match=r"target is no longer eligible"):
        enhancements.apply_malice_made_manifest_fight_phase_start_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
            )
        )

    assert _event_count(decisions, enhancements.MALICE_MADE_MANIFEST_RESOLVED_EVENT) == 0


def test_malice_made_manifest_rejects_assignment_drift_before_damage() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided", "Character"))
    bearer = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_malice_made_manifest(state, unit=bearer)
    _place_malice_made_manifest_engagement(state, bearer=bearer, target=target)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()
    request = _decision_request(
        enhancements.malice_made_manifest_fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
    )
    result = DecisionResult.for_request(
        result_id="result-malice-made-manifest-assignment-drift",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    state.army_definitions = [
        replace(army, enhancement_assignments=()) if army.player_id == "player-a" else army
        for army in state.army_definitions
    ]

    with pytest.raises(GameLifecycleError, match=r"assignment no longer matches unit"):
        enhancements.apply_malice_made_manifest_fight_phase_start_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
            )
        )

    assert _event_count(decisions, enhancements.MALICE_MADE_MANIFEST_RESOLVED_EVENT) == 0


def test_malice_made_manifest_rejects_option_payload_drift() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided", "Character"))
    bearer = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_malice_made_manifest(state, unit=bearer)
    _place_malice_made_manifest_engagement(state, bearer=bearer, target=target)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()
    request = _decision_request(
        enhancements.malice_made_manifest_fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=decisions)
        )
    )
    option_payload = cast(dict[str, JsonValue], request.options[0].payload)
    result = DecisionResult(
        result_id="result-malice-made-manifest-payload-drift",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=request.options[0].option_id,
        payload={**option_payload, "hook_id": "drifted-hook"},
    )

    with pytest.raises(GameLifecycleError, match=r"result payload drift"):
        enhancements.apply_malice_made_manifest_fight_phase_start_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
            )
        )


def test_malice_made_manifest_assignment_requires_shadow_legion_bearer() -> None:
    state = _shadow_legion_state(unit_keywords=("Undivided", "Character"))
    bearer = _unit_for_player(state, player_id="player-a")
    _assign_malice_made_manifest(state, unit=bearer)
    _set_current_battle_phase(state, BattlePhase.FIGHT)

    with pytest.raises(
        GameLifecycleError,
        match=r"Malice Made Manifest requires a Shadow Legion model\.",
    ):
        enhancements.malice_made_manifest_fight_phase_start_request(
            FightPhaseStartRequestContext(state=state, decisions=DecisionController())
        )


def test_shadow_legion_mustering_grants_keywords_and_deep_strike() -> None:
    catalog = _shadow_legion_catalog()
    request = _shadow_legion_muster_request(
        catalog,
        units=(
            ("daemon-unit", _DAEMON_DATASHEET_ID),
            ("belakor", _BELAKOR_DATASHEET_ID),
            ("chaos-lord", _CHAOS_LORD_DATASHEET_ID),
            ("damned-unit", _DAMNED_DATASHEET_ID),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="belakor",
            source_id="phase17g:shadow-legion:warlord",
        ),
        unit_points=(
            _unit_points("daemon-unit", 100),
            _unit_points("belakor", 325),
            _unit_points("chaos-lord", 90),
            _unit_points("damned-unit", 60),
        ),
    )

    army = muster_army(catalog=catalog, request=request)

    daemon = _unit_by_datasheet(army, _DAEMON_DATASHEET_ID)
    belakor = _unit_by_datasheet(army, _BELAKOR_DATASHEET_ID)
    chaos_lord = _unit_by_datasheet(army, _CHAOS_LORD_DATASHEET_ID)
    damned = _unit_by_datasheet(army, _DAMNED_DATASHEET_ID)
    assert _has_keyword(daemon, rule.SHADOW_LEGION_KEYWORD)
    assert not _has_keyword(daemon, rule.UNDIVIDED_KEYWORD)
    assert _has_keyword(belakor, rule.SHADOW_LEGION_KEYWORD)
    assert _has_keyword(belakor, rule.UNDIVIDED_KEYWORD)
    assert not _has_keyword(belakor, "DEEP STRIKE")
    assert _has_keyword(chaos_lord, rule.SHADOW_LEGION_KEYWORD)
    assert _has_keyword(chaos_lord, rule.UNDIVIDED_KEYWORD)
    assert _has_keyword(chaos_lord, "DEEP STRIKE")
    assert _has_keyword(damned, rule.SHADOW_LEGION_KEYWORD)
    assert _has_keyword(damned, rule.UNDIVIDED_KEYWORD)
    assert _has_keyword(damned, "DEEP STRIKE")


def test_shadow_legion_roster_reports_thralls_and_forbidden_units() -> None:
    catalog = _shadow_legion_catalog()
    request = _shadow_legion_muster_request(
        catalog,
        units=(
            ("daemon-unit", _DAEMON_DATASHEET_ID),
            ("daemon-prince", _DAEMON_PRINCE_DATASHEET_ID),
            ("epic-hero", _EPIC_HERO_DATASHEET_ID),
            ("noise-marines", _NOISE_MARINES_DATASHEET_ID),
            ("chaos-lord", _CHAOS_LORD_DATASHEET_ID),
        ),
        unit_points=(
            _unit_points("daemon-unit", 100),
            _unit_points("daemon-prince", 200),
            _unit_points("epic-hero", 300),
            _unit_points("noise-marines", 0),
            _unit_points("chaos-lord", 1001),
        ),
        warlord_selection=WarlordSelection(
            unit_selection_id="daemon-unit",
            source_id="phase17g:shadow-legion:warlord",
        ),
    )

    report = validate_roster_legality(catalog=catalog, request=request)

    assert {violation.violation_code for violation in report.violations} >= {
        "shadow_legion_forbidden_daemon_prince_or_epic_hero",
        "shadow_legion_thralls_heretic_astartes_unit_forbidden",
        "shadow_legion_thralls_points_limit_exceeded",
    }
    with pytest.raises(ValueError, match="shadow_legion_forbidden_daemon_prince_or_epic_hero"):
        report.assert_legal()


def test_shadow_legion_mark_abilities_apply_through_engine_hook_contexts() -> None:
    khorne_state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Khorne"))
    khorne_unit = _unit_for_player(khorne_state, player_id="player-a")

    advance_grant = rule.murderers_cowl_advance_eligibility(
        AdvanceEligibilityContext(
            state=khorne_state,
            player_id="player-a",
            battle_round=khorne_state.battle_round,
            unit_instance_id=khorne_unit.unit_instance_id,
            movement_request_id="shadow-legion-advance-request",
            movement_result_id="shadow-legion-advance-result",
        )
    )

    assert advance_grant is not None
    assert advance_grant.can_shoot
    assert advance_grant.can_declare_charge

    tzeentch_state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Tzeentch"))
    tzeentch_target = _unit_for_player(tzeentch_state, player_id="player-a")
    enemy = _unit_for_player(tzeentch_state, player_id="player-b")
    assert (
        rule.penumbral_puppetry_hit_roll_modifier(
            HitRollModifierContext(
                state=tzeentch_state,
                attacking_unit_instance_id=enemy.unit_instance_id,
                attacker_model_instance_id=enemy.own_models[0].model_instance_id,
                target_unit_instance_id=tzeentch_target.unit_instance_id,
                weapon_profile=_weapon_profile(melee=False),
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == -1
    )
    assert (
        rule.penumbral_puppetry_hit_roll_modifier(
            HitRollModifierContext(
                state=tzeentch_state,
                attacking_unit_instance_id=enemy.unit_instance_id,
                attacker_model_instance_id=enemy.own_models[0].model_instance_id,
                target_unit_instance_id=tzeentch_target.unit_instance_id,
                weapon_profile=_weapon_profile(melee=True),
                source_phase=BattlePhase.FIGHT,
            )
        )
        == -1
    )

    nurgle_state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Nurgle"))
    nurgle_target = _unit_for_player(nurgle_state, player_id="player-a")
    enemy = _unit_for_player(nurgle_state, player_id="player-b")
    assert (
        rule.gloam_rot_wound_roll_modifier(
            WoundRollModifierContext(
                state=nurgle_state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=enemy.unit_instance_id,
                attacker_model_instance_id=enemy.own_models[0].model_instance_id,
                target_unit_instance_id=nurgle_target.unit_instance_id,
                weapon_profile=_weapon_profile(melee=False),
                strength=5,
                toughness=4,
            )
        )
        == -1
    )
    assert (
        rule.gloam_rot_wound_roll_modifier(
            WoundRollModifierContext(
                state=nurgle_state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=enemy.unit_instance_id,
                attacker_model_instance_id=enemy.own_models[0].model_instance_id,
                target_unit_instance_id=nurgle_target.unit_instance_id,
                weapon_profile=_weapon_profile(melee=False),
                strength=4,
                toughness=4,
            )
        )
        == 0
    )

    slaanesh_state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Slaanesh"))
    slaanesh_target = _unit_for_player(slaanesh_state, player_id="player-a")
    enemy = _unit_for_player(slaanesh_state, player_id="player-b")
    snap_restriction = rule.shadows_caress_snap_target_restriction(
        ShootingTargetRestrictionContext(
            state=slaanesh_state,
            player_id="player-b",
            battle_round=slaanesh_state.battle_round,
            attacking_unit_instance_id=enemy.unit_instance_id,
            target_unit_instance_id=slaanesh_target.unit_instance_id,
            attacker_model_instance_id=enemy.own_models[0].model_instance_id,
            shooting_type=ShootingType.SNAP,
        )
    )
    normal_restriction = rule.shadows_caress_snap_target_restriction(
        ShootingTargetRestrictionContext(
            state=slaanesh_state,
            player_id="player-b",
            battle_round=slaanesh_state.battle_round,
            attacking_unit_instance_id=enemy.unit_instance_id,
            target_unit_instance_id=slaanesh_target.unit_instance_id,
            attacker_model_instance_id=enemy.own_models[0].model_instance_id,
            shooting_type=ShootingType.NORMAL,
        )
    )

    assert snap_restriction is not None
    assert snap_restriction.violation_code == "shadow_legion_shadows_caress_snap_target_forbidden"
    assert normal_restriction is None


def test_shadow_legion_dark_pacts_grant_and_belakor_auto_pass_completion() -> None:
    state = _shadow_legion_state(
        name="Be'lakor",
        unit_keywords=("Shadow Legion", "Undivided"),
    )
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    selection = _shooting_selection(state, unit)
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    ).with_unit_selection(selection)
    decisions = DecisionController()
    contribution = rule.runtime_contribution()
    grant_registry = ShootingUnitSelectedGrantRegistry.from_bindings(
        contribution.shooting_unit_selected_grant_hook_bindings
    )

    status = _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=grant_registry,
    )
    request = _decision_request(None if status is None else status.decision_request)
    result = DecisionResult.for_request(
        result_id="shadow-legion-belakor-dark-pact-result",
        request=request,
        selected_option_id=rule.SHOOTING_LETHAL_HITS_HOOK_ID,
    )
    decisions.submit_result(result)
    _apply_shooting_unit_selected_grant_decision(
        state=state,
        result=result,
        decisions=decisions,
        registry=grant_registry,
    )

    modified = dark_pacts.dark_pact_weapon_profile_modifier(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=unit.own_models[0].model_instance_id,
            target_unit_instance_id=target.unit_instance_id,
            weapon_profile=_weapon_profile(melee=False),
        )
    )
    assert WeaponKeyword.LETHAL_HITS in modified.keywords
    assert rule.SOURCE_RULE_ID in modified.source_ids
    assert dark_pacts.SOURCE_RULE_ID not in modified.source_ids

    attack_pool = _attack_pool(attacker=unit, target=target, weapon_profile=modified)
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(unit.unit_instance_id,),
        shot_unit_ids=(unit.unit_instance_id,),
        attack_pools=(attack_pool,),
        attack_sequence=AttackSequence(
            sequence_id="shadow-legion-belakor-sequence",
            attacker_player_id="player-a",
            attacking_unit_instance_id=unit.unit_instance_id,
            attack_pools=(attack_pool,),
            source_phase=BattlePhase.SHOOTING,
            used_pool_indices=(0,),
            pool_index=1,
        ),
    )

    completion_status = ShootingPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="phase17g-shadow-legion-belakor"
        ),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        attack_sequence_completed_hooks=AttackSequenceCompletedHookRegistry.from_bindings(
            contribution.attack_sequence_completed_hook_bindings
        ),
    ).begin_phase(state=state, decisions=decisions)

    assert completion_status.status_kind is LifecycleStatusKind.ADVANCED
    assert _event_count(decisions, "chaos_space_marines_dark_pact_resolved") == 1
    payload = _last_event_payload(decisions, "chaos_space_marines_dark_pact_resolved")
    assert payload["source_rule_id"] == rule.SOURCE_RULE_ID
    assert payload["hook_id"] == rule.ATTACK_SEQUENCE_COMPLETED_HOOK_ID
    assert payload["hook_id"] != dark_pacts.ATTACK_SEQUENCE_COMPLETED_HOOK_ID
    assert payload["leadership_auto_pass"] is True
    assert payload["leadership_roll"] is None
    assert payload["d3_result"] is None
    ShootingPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="phase17g-shadow-legion-belakor"
        ),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        attack_sequence_completed_hooks=AttackSequenceCompletedHookRegistry.from_bindings(
            contribution.attack_sequence_completed_hook_bindings
        ),
    ).begin_phase(state=state, decisions=decisions)
    assert _event_count(decisions, "chaos_space_marines_dark_pact_resolved") == 1


def test_shadow_legion_dark_pacts_failed_leadership_routes_fnp_decision() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided"))
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _record_shadow_dark_pact_effect(
        state,
        unit=unit,
        phase=BattlePhase.SHOOTING,
        pact=dark_pacts.DarkPactKind.LETHAL_HITS,
    )
    source_a = FeelNoPainSource(source_id="shadow-legion-fnp-a", threshold=5)
    source_b = FeelNoPainSource(source_id="shadow-legion-fnp-b", threshold=6)
    state.record_model_feel_no_pain_sources(
        model_instance_id=unit.own_models[0].model_instance_id,
        sources=(source_a, source_b),
    )
    decisions = DecisionController()
    attack_sequence = AttackSequence(
        sequence_id="shadow-legion-fnp-sequence",
        attacker_player_id="player-a",
        attacking_unit_instance_id=unit.unit_instance_id,
        attack_pools=(
            _attack_pool(
                attacker=unit,
                target=target,
                weapon_profile=_weapon_profile(melee=False),
            ),
        ),
        source_phase=BattlePhase.SHOOTING,
        used_pool_indices=(0,),
        pool_index=1,
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": "player-a",
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=(
            DiceRollResult.from_values(
                roll_id="shadow-legion-fnp-leadership-roll",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=2, sides=6),
                    reason=f"Dark Pact Leadership test for {unit.unit_instance_id}",
                    roll_type=dark_pacts.DARK_PACT_LEADERSHIP_ROLL_TYPE,
                    actor_id=unit.unit_instance_id,
                ),
                values=(1, 1),
                source="fixed",
            ),
            DiceRollResult.from_values(
                roll_id="shadow-legion-fnp-mortal-wounds-roll",
                spec=DiceRollManager.d3_source_spec(
                    reason=f"Dark Pact mortal wounds for {unit.unit_instance_id}",
                    roll_type=dark_pacts.DARK_PACT_MORTAL_WOUNDS_ROLL_TYPE,
                    actor_id=unit.unit_instance_id,
                ),
                values=(1,),
                source="fixed",
            ),
        ),
    )
    starting_wounds = sum(model.wounds_remaining for model in unit.own_models)
    contribution = rule.runtime_contribution()

    status = AttackSequenceCompletedHookRegistry.from_bindings(
        contribution.attack_sequence_completed_hook_bindings
    ).resolve_completed_sequence(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=manager,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=attack_sequence,
            attack_sequence_completed_event_id=completed_event.event_id,
        )
    )
    request = _decision_request(None if status is None else status.decision_request)

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert is_mortal_wound_feel_no_pain_request(request)
    source_context = mortal_wound_feel_no_pain_source_context(request)
    assert isinstance(source_context, dict)
    assert source_context["source_kind"] == (
        dark_pacts.SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND
    )
    pending_payload = cast(dict[str, JsonValue], source_context["resolution_payload"])
    assert pending_payload["hook_id"] == rule.ATTACK_SEQUENCE_COMPLETED_HOOK_ID
    assert pending_payload["hook_id"] != dark_pacts.ATTACK_SEQUENCE_COMPLETED_HOOK_ID
    assert {option.option_id for option in request.options} == {
        source_a.source_id,
        source_b.source_id,
    }
    assert not _has_event(decisions, "chaos_space_marines_dark_pact_resolved")
    assert sum(model.wounds_remaining for model in _refreshed_unit(state, unit).own_models) == (
        starting_wounds
    )

    result = DecisionResult.for_request(
        result_id="shadow-legion-fnp-source-a",
        request=request,
        selected_option_id=source_a.source_id,
    )
    decisions.submit_result(result)
    continuation_status = MortalWoundFeelNoPainContinuationHookRegistry.from_bindings(
        contribution.mortal_wound_feel_no_pain_hook_bindings
    ).apply_decision(
        MortalWoundFeelNoPainContinuationContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            source_context=source_context,
            dice_manager=DiceRollManager(
                state.game_id,
                event_log=decisions.event_log,
                injected_results=(
                    DiceRollResult.from_values(
                        roll_id="shadow-legion-fnp-roll",
                        spec=feel_no_pain_roll_spec(
                            source=source_a,
                            player_id="player-a",
                            model_instance_id=unit.own_models[0].model_instance_id,
                            wound_index=1,
                        ),
                        values=(1,),
                        source="fixed",
                    ),
                ),
            ),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )

    assert continuation_status is None
    payload = _last_event_payload(decisions, "chaos_space_marines_dark_pact_resolved")
    assert payload["source_rule_id"] == rule.SOURCE_RULE_ID
    assert payload["hook_id"] == rule.ATTACK_SEQUENCE_COMPLETED_HOOK_ID
    assert payload["hook_id"] != dark_pacts.ATTACK_SEQUENCE_COMPLETED_HOOK_ID
    assert payload["leadership_auto_pass"] is False
    assert payload["feel_no_pain_result_id"] == result.result_id
    application = cast(dict[str, JsonValue], payload["mortal_wound_application"])
    assert application["mortal_wounds"] == 1
    assert (
        starting_wounds
        - sum(model.wounds_remaining for model in _refreshed_unit(state, unit).own_models)
        == 1
    )


def test_shadow_legion_out_of_phase_shooting_requests_dark_pacts_grant() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided"))
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    decisions = DecisionController()
    grant_registry = ShootingUnitSelectedGrantRegistry.from_bindings(
        rule.runtime_contribution().shooting_unit_selected_grant_hook_bindings
    )

    grant_status = request_out_of_phase_shooting_declaration(
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="phase17g-shadow-legion-out-of-phase"
        ),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        parent_phase=BattlePhase.MOVEMENT,
        source_rule_id=FIRE_OVERWATCH_RULE_ID,
        source_decision_request_id="shadow-legion-fire-overwatch-request",
        source_decision_result_id="shadow-legion-fire-overwatch-result",
        source_context={
            "source_kind": "fire_overwatch",
            "triggering_enemy_unit_instance_id": target.unit_instance_id,
        },
        target_unit_ids=(target.unit_instance_id,),
        shooting_unit_selected_grant_hooks=grant_registry,
    )
    request = _decision_request(grant_status.decision_request)

    assert request.decision_type == SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE
    assert state.out_of_phase_shooting_state is not None
    assert state.out_of_phase_shooting_state.target_unit_ids == (target.unit_instance_id,)

    result = DecisionResult.for_request(
        result_id="shadow-legion-out-of-phase-dark-pact-result",
        request=request,
        selected_option_id=rule.SHOOTING_LETHAL_HITS_HOOK_ID,
    )
    decisions.submit_result(result)
    declaration_status = ShootingPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="phase17g-shadow-legion-out-of-phase"
        ),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        shooting_unit_selected_grant_hooks=grant_registry,
    ).apply_decision(
        state=state,
        result=result,
        decisions=decisions,
    )
    declaration_request = _decision_request(
        None if declaration_status is None else declaration_status.decision_request
    )

    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
    assert (
        dark_pacts.active_dark_pact_for_unit(
            state,
            unit_instance_id=unit.unit_instance_id,
            phase=BattlePhase.SHOOTING,
        )
        is dark_pacts.DarkPactKind.LETHAL_HITS
    )
    assert state.out_of_phase_shooting_state is not None
    assert state.out_of_phase_shooting_state.grant_effect_ids


def test_shadow_legion_fight_grants_dark_pacts_for_undivided_units() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided"))
    unit = _unit_for_player(state, player_id="player-a")
    _set_current_battle_phase(state, BattlePhase.FIGHT)

    grants = tuple(
        binding.handler(
            FightUnitSelectedContext(
                state=state,
                player_id="player-a",
                battle_round=state.battle_round,
                unit_instance_id=unit.unit_instance_id,
                fight_type=FightTypeKind.NORMAL.value,
                ordering_band=FightOrderingBandKind.REMAINING_COMBATS.value,
                request_id="shadow-legion-fight-request",
                result_id="shadow-legion-fight-result",
            )
        )
        for binding in rule.runtime_contribution().fight_unit_selected_grant_hook_bindings
    )

    assert {grant.hook_id for grant in grants if grant is not None} == {
        rule.FIGHT_LETHAL_HITS_HOOK_ID,
        rule.FIGHT_SUSTAINED_HITS_HOOK_ID,
    }


def test_fade_to_darkness_requires_current_fight_destroyed_enemy_marker() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided"))
    unit = _unit_for_player(state, player_id="player-a")
    _assign_fade_to_darkness(state, unit=unit)
    _set_current_battle_phase(state, BattlePhase.FIGHT)

    assert (
        enhancements.fade_to_darkness_turn_end_request(
            TurnEndRequestContext(
                state=state,
                decisions=DecisionController(),
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )


def test_fade_to_darkness_ignores_unattributed_fight_enemy_destruction() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided"))
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_fade_to_darkness(state, unit=unit)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()

    _record_fade_to_darkness_destroyed_enemy(
        state=state,
        decisions=decisions,
        attacker=None,
        target=target,
    )

    assert _event_count(decisions, enhancements.ELIGIBLE_EVENT) == 0
    assert (
        enhancements.fade_to_darkness_turn_end_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )


def test_fade_to_darkness_ignores_non_assigned_attacker() -> None:
    state = _shadow_legion_state(
        unit_keywords=("Shadow Legion", "Undivided"),
        player_a_unit_selection_ids=("intercessor-unit-1", "intercessor-unit-2"),
    )
    fade_unit = _unit_for_player_by_index(state, player_id="player-a", index=0)
    non_fade_unit = _unit_for_player_by_index(state, player_id="player-a", index=1)
    target = _unit_for_player(state, player_id="player-b")
    _assign_fade_to_darkness(state, unit=fade_unit)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()

    _record_fade_to_darkness_destroyed_enemy(
        state=state,
        decisions=decisions,
        attacker=non_fade_unit,
        target=target,
    )

    assert _event_count(decisions, enhancements.ELIGIBLE_EVENT) == 0
    assert (
        enhancements.fade_to_darkness_turn_end_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )


def test_fade_to_darkness_records_one_marker_for_assigned_attacker() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided"))
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_fade_to_darkness(state, unit=unit)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()

    _record_fade_to_darkness_destroyed_enemy(
        state=state,
        decisions=decisions,
        attacker=unit,
        target=target,
    )
    _record_fade_to_darkness_destroyed_enemy(
        state=state,
        decisions=decisions,
        attacker=unit,
        target=target,
    )

    assert _event_count(decisions, enhancements.ELIGIBLE_EVENT) == 1
    payload = _last_event_payload(decisions, enhancements.ELIGIBLE_EVENT)
    assert payload["target_unit_instance_id"] == unit.unit_instance_id
    assert payload["destroyed_enemy_unit_instance_id"] == target.unit_instance_id


def test_fade_to_darkness_turn_end_choice_moves_unit_to_strategic_reserves_once() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided"))
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_fade_to_darkness(state, unit=unit)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()
    _record_fade_to_darkness_destroyed_enemy(
        state=state,
        decisions=decisions,
        attacker=unit,
        target=target,
    )

    request = _decision_request(
        enhancements.fade_to_darkness_turn_end_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
    )

    assert request.decision_type == SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["source_rule_id"] == enhancements.SOURCE_RULE_ID
    assert request_payload["hook_id"] == enhancements.TURN_END_HOOK_ID
    assert request_payload["enhancement_id"] == enhancements.ENHANCEMENT_ID
    assert request_payload["target_unit_instance_id"] == unit.unit_instance_id
    assert request_payload["destroyed_enemy_unit_instance_ids"] == [target.unit_instance_id]
    assert {option.option_id for option in request.options} == {
        f"chaos-daemons:shadow-legion:fade-to-darkness:{unit.unit_instance_id}:use",
        f"chaos-daemons:shadow-legion:fade-to-darkness:{unit.unit_instance_id}:decline",
    }

    result = DecisionResult.for_request(
        result_id="result-fade-to-darkness-use",
        request=request,
        selected_option_id=(
            f"chaos-daemons:shadow-legion:fade-to-darkness:{unit.unit_instance_id}:use"
        ),
    )
    handled = enhancements.apply_fade_to_darkness_turn_end_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert handled is True
    reserve_state = state.reserve_state_for_unit(unit.unit_instance_id)
    assert reserve_state is not None
    assert reserve_state.source_rule_ids == (enhancements.SOURCE_RULE_ID,)
    assert state.battlefield_state is not None
    assert all(
        placement.unit_instance_id != unit.unit_instance_id
        for placed_army in state.battlefield_state.placed_armies
        for placement in placed_army.unit_placements
    )
    used_payload = _last_event_payload(decisions, enhancements.USED_EVENT)
    assert used_payload["use_ability"] is True
    assert used_payload["destroyed_enemy_unit_instance_ids"] == [target.unit_instance_id]
    reserve_payload = cast(dict[str, JsonValue], used_payload["reserve_state"])
    assert reserve_payload["unit_instance_id"] == unit.unit_instance_id
    assert (
        enhancements.fade_to_darkness_turn_end_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="no longer eligible"):
        enhancements.apply_fade_to_darkness_turn_end_result(
            TurnEndResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
            )
        )


def test_fade_to_darkness_turn_end_decline_records_no_reserve_mutation() -> None:
    state = _shadow_legion_state(unit_keywords=("Shadow Legion", "Undivided"))
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _assign_fade_to_darkness(state, unit=unit)
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()
    _record_fade_to_darkness_destroyed_enemy(
        state=state,
        decisions=decisions,
        attacker=unit,
        target=target,
    )
    request = _decision_request(
        enhancements.fade_to_darkness_turn_end_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
    )

    result = DecisionResult.for_request(
        result_id="result-fade-to-darkness-decline",
        request=request,
        selected_option_id=(
            f"chaos-daemons:shadow-legion:fade-to-darkness:{unit.unit_instance_id}:decline"
        ),
    )
    handled = enhancements.apply_fade_to_darkness_turn_end_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    assert handled is True
    assert state.reserve_state_for_unit(unit.unit_instance_id) is None
    assert state.battlefield_state is not None
    assert (
        state.battlefield_state.unit_placement_by_id(unit.unit_instance_id).unit_instance_id
        == unit.unit_instance_id
    )
    declined_payload = _last_event_payload(decisions, enhancements.DECLINED_EVENT)
    assert declined_payload["use_ability"] is False
    assert declined_payload["destroyed_enemy_unit_instance_ids"] == [target.unit_instance_id]
    assert (
        enhancements.fade_to_darkness_turn_end_request(
            TurnEndRequestContext(
                state=state,
                decisions=decisions,
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )


def _shadow_legion_state(
    *,
    name: str = "Shadow Legion Unit",
    unit_keywords: tuple[str, ...] = ("Shadow Legion", "Undivided"),
    faction_keywords: tuple[str, ...] = ("Legiones Daemonica",),
    player_a_unit_selection_ids: tuple[str, ...] = ("intercessor-unit-1",),
) -> GameState:
    state = _battle_state(
        player_a_units=tuple(
            _core_unit_selection(unit_selection_id)
            for unit_selection_id in player_a_unit_selection_ids
        )
    )
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != "player-a":
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id=CHAOS_DAEMONS_FACTION_ID,
                    detachment_ids=(rule.DETACHMENT_ID,),
                ),
                units=tuple(
                    replace(
                        unit,
                        name=name,
                        keywords=tuple(dict.fromkeys((*unit.keywords, *unit_keywords))),
                        faction_keywords=faction_keywords,
                    )
                    for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies
    return state


def _core_unit_selection(unit_selection_id: str) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-intercessor-like-infantry",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )


def _record_shadow_dark_pact_effect(
    state: GameState,
    *,
    unit: UnitInstance,
    phase: BattlePhase,
    pact: dark_pacts.DarkPactKind,
) -> None:
    phase_kind = (
        BattlePhaseKind.SHOOTING if phase is BattlePhase.SHOOTING else BattlePhaseKind.FIGHT
    )
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"shadow-legion-dark-pact:{phase.value}:{pact.value}:{unit.unit_instance_id}",
            source_rule_id=rule.SOURCE_RULE_ID,
            owner_player_id="player-a",
            target_unit_instance_ids=dark_pacts.dark_pact_target_unit_ids(
                state,
                unit_instance_id=unit.unit_instance_id,
            ),
            started_battle_round=state.battle_round,
            started_phase=phase_kind,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=phase_kind,
                player_id="player-a",
            ),
            effect_payload=dark_pacts.dark_pact_effect_payload(
                unit_instance_id=unit.unit_instance_id,
                target_unit_instance_ids=dark_pacts.dark_pact_target_unit_ids(
                    state,
                    unit_instance_id=unit.unit_instance_id,
                ),
                trigger="test",
                phase=phase,
                selected_dark_pact=pact,
                source_context={"source_rule_id": rule.SOURCE_RULE_ID},
            ),
        )
    )


def _assign_fade_to_darkness(state: GameState, *, unit: UnitInstance) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != "player-a":
            updated_armies.append(army)
            continue
        prefix = f"{army.army_id}:"
        if not unit.unit_instance_id.startswith(prefix):
            raise AssertionError(f"Unit {unit.unit_instance_id} is not owned by {army.army_id}.")
        updated_armies.append(
            replace(
                army,
                enhancement_assignments=(
                    EnhancementAssignment(
                        enhancement_id=enhancements.ENHANCEMENT_ID,
                        target_unit_selection_id=unit.unit_instance_id.removeprefix(prefix),
                        source_id=enhancements.SOURCE_RULE_ID,
                    ),
                ),
            )
        )
    state.army_definitions = updated_armies


def _assign_leaping_shadows(state: GameState, *, unit: UnitInstance) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != "player-a":
            updated_armies.append(army)
            continue
        prefix = f"{army.army_id}:"
        if not unit.unit_instance_id.startswith(prefix):
            raise AssertionError(f"Unit {unit.unit_instance_id} is not owned by {army.army_id}.")
        updated_armies.append(
            replace(
                army,
                enhancement_assignments=(
                    EnhancementAssignment(
                        enhancement_id=enhancements.LEAPING_SHADOWS_ENHANCEMENT_ID,
                        target_unit_selection_id=unit.unit_instance_id.removeprefix(prefix),
                        source_id=enhancements.LEAPING_SHADOWS_SOURCE_RULE_ID,
                    ),
                ),
            )
        )
    state.army_definitions = updated_armies


def _assign_mantle_of_gloom(state: GameState, *, unit: UnitInstance) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != "player-a":
            updated_armies.append(army)
            continue
        prefix = f"{army.army_id}:"
        if not unit.unit_instance_id.startswith(prefix):
            raise AssertionError(f"Unit {unit.unit_instance_id} is not owned by {army.army_id}.")
        updated_armies.append(
            replace(
                army,
                enhancement_assignments=(
                    EnhancementAssignment(
                        enhancement_id=enhancements.MANTLE_OF_GLOOM_ENHANCEMENT_ID,
                        target_unit_selection_id=unit.unit_instance_id.removeprefix(prefix),
                        source_id=enhancements.MANTLE_OF_GLOOM_SOURCE_RULE_ID,
                    ),
                ),
            )
        )
    state.army_definitions = updated_armies


def _destroy_unit_own_models(state: GameState, *, unit_instance_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    removed_model_ids: list[str] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id != unit_instance_id:
                updated_units.append(unit)
                continue
            removed_model_ids.extend(model.model_instance_id for model in unit.own_models)
            updated_units.append(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=0) for model in unit.own_models
                    ),
                )
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not removed_model_ids:
        raise AssertionError(f"Unit {unit_instance_id} was not found.")
    if state.battlefield_state is None:
        raise AssertionError("Expected battlefield_state.")
    state.army_definitions = updated_armies
    state.battlefield_state = state.battlefield_state.with_removed_models(tuple(removed_model_ids))


def _assign_malice_made_manifest(state: GameState, *, unit: UnitInstance) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != "player-a":
            updated_armies.append(army)
            continue
        prefix = f"{army.army_id}:"
        if not unit.unit_instance_id.startswith(prefix):
            raise AssertionError(f"Unit {unit.unit_instance_id} is not owned by {army.army_id}.")
        updated_armies.append(
            replace(
                army,
                enhancement_assignments=(
                    EnhancementAssignment(
                        enhancement_id=enhancements.MALICE_MADE_MANIFEST_ENHANCEMENT_ID,
                        target_unit_selection_id=unit.unit_instance_id.removeprefix(prefix),
                        source_id=enhancements.MALICE_MADE_MANIFEST_SOURCE_RULE_ID,
                    ),
                ),
            )
        )
    state.army_definitions = updated_armies


def _attach_shadow_legion_units(
    state: GameState,
    *,
    bodyguard: UnitInstance,
    leader: UnitInstance,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != "player-a":
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                attached_units=(
                    AttachedUnitFormation(
                        attached_unit_instance_id=f"attached-unit:{army.army_id}:bodyguard-unit",
                        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
                        leader_unit_instance_ids=(leader.unit_instance_id,),
                        component_unit_instance_ids=tuple(
                            sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
                        ),
                        source_id="phase17g:shadow-legion:test-attached-unit",
                    ),
                ),
            )
        )
    state.army_definitions = updated_armies


def _place_malice_made_manifest_engagement(
    state: GameState,
    *,
    bearer: UnitInstance,
    target: UnitInstance,
) -> None:
    _place_unit_poses(
        state,
        unit_instance_id=bearer.unit_instance_id,
        poses=_unit_line_poses(x=10.0, y=20.0),
    )
    _place_unit_poses(
        state,
        unit_instance_id=target.unit_instance_id,
        poses=_unit_line_poses(x=12.0, y=20.0),
    )


def _place_unit_poses(
    state: GameState,
    *,
    unit_instance_id: str,
    poses: tuple[Pose, ...],
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(_with_model_poses(placement, poses=poses))
    )


def _unit_line_poses(*, x: float, y: float) -> tuple[Pose, ...]:
    return tuple(Pose.at(x, y + index * 1.8) for index in range(5))


def _with_model_poses(
    unit_placement: UnitPlacement,
    *,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    if len(poses) != len(unit_placement.model_placements):
        raise AssertionError("test pose fixture must match unit model count")
    return UnitPlacement(
        army_id=unit_placement.army_id,
        player_id=unit_placement.player_id,
        unit_instance_id=unit_placement.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=placement.army_id,
                player_id=placement.player_id,
                unit_instance_id=placement.unit_instance_id,
                model_instance_id=placement.model_instance_id,
                pose=pose,
            )
            for placement, pose in zip(unit_placement.model_placements, poses, strict=True)
        ),
    )


def _record_fade_to_darkness_destroyed_enemy(
    *,
    state: GameState,
    decisions: DecisionController,
    attacker: UnitInstance | None,
    target: UnitInstance,
) -> None:
    payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "phase": BattlePhase.FIGHT.value,
        "destroying_player_id": "player-a",
        "target_unit_instance_id": target.unit_instance_id,
        "model_instance_id": target.own_models[0].model_instance_id,
    }
    if attacker is not None:
        payload["attacking_unit_instance_id"] = attacker.unit_instance_id
        payload["attacker_model_instance_id"] = attacker.own_models[0].model_instance_id
    event = decisions.event_log.append(
        "model_destroyed",
        payload,
    )
    enhancements.record_fade_to_darkness_destroyed_enemy_unit(
        UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
            model_destroyed_event_id=event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], event.payload),
            destroying_player_id="player-a",
            destroyed_unit_instance_id=target.unit_instance_id,
            destroyed_player_id="player-b",
        )
    )


def _shadow_legion_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    datasheets = (
        _shadow_datasheet(
            base_datasheet,
            datasheet_id=_DAEMON_DATASHEET_ID,
            name="Bloodletters",
            keywords=("Infantry", "Khorne"),
            faction_keywords=("Legiones Daemonica",),
        ),
        _shadow_datasheet(
            base_datasheet,
            datasheet_id=_BELAKOR_DATASHEET_ID,
            name="Be'lakor",
            keywords=("Monster", "Character", "Epic Hero", "Undivided"),
            faction_keywords=("Legiones Daemonica",),
        ),
        _shadow_datasheet(
            base_datasheet,
            datasheet_id=_CHAOS_LORD_DATASHEET_ID,
            name="Chaos Lord",
            keywords=("Infantry", "Character"),
            faction_keywords=("Heretic Astartes",),
        ),
        _shadow_datasheet(
            base_datasheet,
            datasheet_id=_DAMNED_DATASHEET_ID,
            name="Traitor Enforcer",
            keywords=("Infantry", "Damned"),
            faction_keywords=("Heretic Astartes",),
        ),
        _shadow_datasheet(
            base_datasheet,
            datasheet_id=_DAEMON_PRINCE_DATASHEET_ID,
            name="Daemon Prince",
            keywords=("Monster", "Character"),
            faction_keywords=("Legiones Daemonica",),
        ),
        _shadow_datasheet(
            base_datasheet,
            datasheet_id=_EPIC_HERO_DATASHEET_ID,
            name="Skarbrand",
            keywords=("Monster", "Epic Hero"),
            faction_keywords=("Legiones Daemonica",),
        ),
        _shadow_datasheet(
            base_datasheet,
            datasheet_id=_NOISE_MARINES_DATASHEET_ID,
            name="Noise Marines",
            keywords=("Infantry", "Slaanesh"),
            faction_keywords=("Heretic Astartes",),
        ),
    )
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, *datasheets),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=CHAOS_DAEMONS_FACTION_ID,
                name="Chaos Daemons",
                faction_keywords=("Legiones Daemonica",),
                source_ids=("phase17g:test:chaos-daemons",),
            ),
            FactionDefinition(
                faction_id=CHAOS_SPACE_MARINES_FACTION_ID,
                name="Chaos Space Marines",
                faction_keywords=("Heretic Astartes",),
                source_ids=("phase17g:test:chaos-space-marines",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id=rule.DETACHMENT_ID,
                name="Shadow Legion",
                faction_id=CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=2,
                unit_datasheet_ids=(
                    _DAEMON_DATASHEET_ID,
                    _BELAKOR_DATASHEET_ID,
                    _DAEMON_PRINCE_DATASHEET_ID,
                    _EPIC_HERO_DATASHEET_ID,
                ),
                force_disposition_ids=("phase17g-shadow-legion-force",),
                source_ids=("phase17g:test:chaos-daemons:shadow-legion",),
            ),
        ),
    )


def _shadow_datasheet(
    base_datasheet: DatasheetDefinition,
    *,
    datasheet_id: str,
    name: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=datasheet_id,
        name=name,
        keywords=DatasheetKeywordSet(
            keywords=keywords,
            faction_keywords=faction_keywords,
        ),
        attachment_eligibilities=(),
        source_ids=(f"phase17g:test:{datasheet_id}",),
    )


def _shadow_legion_muster_request(
    catalog: ArmyCatalog,
    *,
    units: tuple[tuple[str, str], ...],
    unit_points: tuple[RosterUnitPointValue, ...] = (),
    warlord_selection: WarlordSelection | None = None,
    battle_size: BattleSize = BattleSize.STRIKE_FORCE,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id="army-alpha",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=CHAOS_DAEMONS_FACTION_ID,
            detachment_ids=(rule.DETACHMENT_ID,),
        ),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=selection_id,
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for selection_id, datasheet_id in units
        ),
        unit_points=unit_points,
        warlord_selection=warlord_selection,
        battle_size=battle_size,
    )


def _unit_points(unit_selection_id: str, points: int) -> RosterUnitPointValue:
    return RosterUnitPointValue(
        unit_selection_id=unit_selection_id,
        points=points,
        source_id=f"points:{unit_selection_id}",
    )


def _unit_for_player(state: GameState, *, player_id: str) -> UnitInstance:
    return _unit_for_player_by_index(state, player_id=player_id, index=0)


def _unit_for_player_by_index(state: GameState, *, player_id: str, index: int) -> UnitInstance:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise AssertionError(f"Missing army for {player_id}.")
    return army.units[index]


def _refreshed_unit(state: GameState, unit: UnitInstance) -> UnitInstance:
    for army in state.army_definitions:
        for candidate in army.units:
            if candidate.unit_instance_id == unit.unit_instance_id:
                return candidate
    raise AssertionError(f"Missing unit {unit.unit_instance_id}.")


def _unit_by_datasheet(army: ArmyDefinition, datasheet_id: str) -> UnitInstance:
    for unit in army.units:
        if unit.datasheet_id == datasheet_id:
            return unit
    raise AssertionError(f"Missing datasheet {datasheet_id}.")


def _has_keyword(unit: UnitInstance, keyword: str) -> bool:
    return keyword.upper() in {stored.upper() for stored in unit.keywords}


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _shooting_selection(state: GameState, unit: UnitInstance) -> ShootingUnitSelection:
    return ShootingUnitSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        request_id="shadow-legion-shooting-selection-request",
        result_id="shadow-legion-shooting-selection-result",
    )


def _weapon_profile(*, melee: bool) -> WeaponProfile:
    return WeaponProfile(
        profile_id="shadow-legion-melee-profile" if melee else "shadow-legion-ranged-profile",
        name="Shadow Legion melee weapon" if melee else "Shadow Legion ranged weapon",
        range_profile=RangeProfile.melee() if melee else RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(
            Characteristic.WEAPON_SKILL if melee else Characteristic.BALLISTIC_SKILL,
            3,
        ),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("shadow-legion-test-profile",),
    )


def _attack_pool(
    *,
    attacker: UnitInstance,
    target: UnitInstance,
    weapon_profile: WeaponProfile,
) -> RangedAttackPool:
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id="shadow-legion-test-wargear",
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=target.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=(target.own_models[0].model_instance_id,),
        target_in_range_model_ids=(target.own_models[0].model_instance_id,),
    )


def _decision_request(request: DecisionRequest | None) -> DecisionRequest:
    if request is None:
        raise AssertionError("Expected decision request.")
    return request


def _last_event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, JsonValue]:
    for event in reversed(decisions.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"Missing event {event_type}.")


def _has_event(decisions: DecisionController, event_type: str) -> bool:
    return any(event.event_type == event_type for event in decisions.event_log.records)


def _event_count(decisions: DecisionController, event_type: str) -> int:
    return sum(1 for event in decisions.event_log.records if event.event_type == event_type)
