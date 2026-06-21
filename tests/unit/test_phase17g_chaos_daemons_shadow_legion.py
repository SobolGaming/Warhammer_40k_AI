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
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.shadow_legion import (  # noqa: E501
    rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule as dark_pacts,
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
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.shooting import (
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingPhaseHandler,
    ShootingPhaseState,
    ShootingUnitSelection,
    _apply_shooting_unit_selected_grant_decision,  # pyright: ignore[reportPrivateUsage]
    _request_shooting_unit_selected_grant_decision_if_available,  # pyright: ignore[reportPrivateUsage]
    request_out_of_phase_shooting_declaration,
)
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
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
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import FIRE_OVERWATCH_RULE_ID
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool

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


def _shadow_legion_state(
    *,
    name: str = "Shadow Legion Unit",
    unit_keywords: tuple[str, ...] = ("Shadow Legion", "Undivided"),
    faction_keywords: tuple[str, ...] = ("Legiones Daemonica",),
) -> GameState:
    state = _battle_state()
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
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise AssertionError(f"Missing army for {player_id}.")
    return army.units[0]


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
