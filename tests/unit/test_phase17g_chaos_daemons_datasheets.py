from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import (
    battle_state,
    battle_state_with_center_objective_positions,
    center_marker_definition,
    default_unit_selection,
    unit_by_id,
    with_model_offsets,
)

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookRegistry,
    BattleShockModifierContext,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.damage_allocation import MortalWoundApplicationProgress
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    datasheets,
)
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.fight_phase_decisions import (
    invalid_fight_phase_faction_rule_status,
)
from warhammer40k_core.engine.fight_phase_end_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_END_OPTION_DECISION_TYPE,
    FightPhaseEndHookBinding,
    FightPhaseEndHookRegistry,
    FightPhaseEndRequestContext,
    FightPhaseEndRequestHandler,
    FightPhaseEndResultContext,
    FightPhaseEndResultHandler,
    apply_fight_phase_end_result,
    invalid_fight_phase_end_faction_rule_status,
    request_fight_phase_end_rule_if_available,
)
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    MovementBudgetModifierContext,
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.sticky_objective_control import PhaseEndObjectiveControlContext
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext


def test_daemon_lord_auras_apply_only_to_matching_legiones_daemonica_keywords() -> None:
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    state.game_id = "phase17g-daemon-lord-auras"
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-2"
    target_model_id = unit_by_id(state, target_unit_id).own_models[0].model_instance_id
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Monster", "Khorne", "Tzeentch"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(
            _datasheet_ability(datasheets.BLOODTHIRSTER_DAEMON_LORD_SOURCE_ID),
            _datasheet_ability(datasheets.LORD_OF_CHANGE_DAEMON_LORD_SOURCE_ID),
        ),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
    )
    _place_units_near_center(
        state,
        source_unit_id=source_unit_id,
        target_unit_id=target_unit_id,
        target_offset=(1.0, 0.0),
    )
    registry = _datasheet_runtime_modifier_registry()

    assert (
        registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=target_unit_id,
                attacker_model_instance_id=target_model_id,
                target_unit_instance_id="army-beta:intercessor-unit-3",
                weapon_profile=_melee_profile(),
                source_phase=BattlePhase.FIGHT,
            )
        )
        == 1
    )
    unmodified_ranged = registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=target_unit_id,
            attacker_model_instance_id=target_model_id,
            target_unit_instance_id="army-beta:intercessor-unit-3",
            weapon_profile=_ranged_profile(),
        )
    )
    assert unmodified_ranged.strength.final == 5

    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Tzeentch"),
        faction_keywords=("Legiones Daemonica",),
    )
    modified_ranged = registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=target_unit_id,
            attacker_model_instance_id=target_model_id,
            target_unit_instance_id="army-beta:intercessor-unit-3",
            weapon_profile=_ranged_profile(),
        )
    )
    assert modified_ranged.strength.final == 6
    assert datasheets.LORD_OF_CHANGE_DAEMON_LORD_SOURCE_ID in modified_ranged.source_ids


def test_skarbrand_and_keeper_weapon_auras_modify_friendly_melee_profiles() -> None:
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    state.game_id = "phase17g-chaos-daemons-melee-profile-auras"
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-2"
    target_model_id = unit_by_id(state, target_unit_id).own_models[0].model_instance_id
    registry = _datasheet_runtime_modifier_registry()

    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Monster", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(_datasheet_ability(datasheets.SKARBRAND_RAGE_EMBODIED_SOURCE_ID),),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
    )
    _place_units_near_center(
        state,
        source_unit_id=source_unit_id,
        target_unit_id=target_unit_id,
        target_offset=(1.0, 0.0),
    )

    rage_modified = registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=target_unit_id,
            attacker_model_instance_id=target_model_id,
            target_unit_instance_id="army-beta:intercessor-unit-3",
            weapon_profile=_melee_profile(),
        )
    )
    assert rage_modified.attack_profile.fixed_attacks == 2
    assert rage_modified.armor_penetration.final == -1
    assert datasheets.SKARBRAND_RAGE_EMBODIED_SOURCE_ID in rage_modified.source_ids

    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Monster", "Slaanesh"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(_datasheet_ability(datasheets.KEEPER_DAEMON_LORD_SLAANESH_SOURCE_ID),),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Slaanesh"),
        faction_keywords=("Legiones Daemonica",),
    )

    slaanesh_modified = registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=target_unit_id,
            attacker_model_instance_id=target_model_id,
            target_unit_instance_id="army-beta:intercessor-unit-3",
            weapon_profile=_melee_profile(),
        )
    )
    assert slaanesh_modified.attack_profile.fixed_attacks == 1
    assert slaanesh_modified.armor_penetration.final == -2
    assert datasheets.KEEPER_DAEMON_LORD_SLAANESH_SOURCE_ID in slaanesh_modified.source_ids


def test_rotigus_deluge_modifies_enemy_move_and_objective_control_within_aura() -> None:
    state = battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((1.0, 0.0),),
    )
    state.game_id = "phase17g-rotigus-deluge"
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-beta:intercessor-unit-3"
    target_model_id = unit_by_id(state, target_unit_id).own_models[0].model_instance_id
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Monster", "Nurgle"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(_datasheet_ability(datasheets.ROTIGUS_DELUGE_SOURCE_ID),),
    )
    registry = _datasheet_runtime_modifier_registry()

    movement_context = MovementBudgetModifierContext(
        state=state,
        unit_instance_id=target_unit_id,
        model_instance_id=target_model_id,
        base_movement_inches=6.0,
        current_movement_inches=6.0,
    )
    objective_control_context = ObjectiveControlModifierContext(
        state=state,
        unit_instance_id=target_unit_id,
        model_instance_id=target_model_id,
        base_objective_control=2,
        current_objective_control=2,
    )
    assert registry.modified_movement_inches(movement_context) == 4.0
    assert registry.modified_objective_control(objective_control_context) == 1

    _place_units_near_center(
        state,
        source_unit_id=source_unit_id,
        target_unit_id=target_unit_id,
        target_offset=(8.0, 0.0),
    )
    assert registry.modified_movement_inches(movement_context) == 6.0
    assert registry.modified_objective_control(objective_control_context) == 2


def test_nurglings_mischief_makers_modifies_enemy_melee_hits_in_engagement_range() -> None:
    state = battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((0.5, 0.0),),
    )
    state.game_id = "phase17g-mischief-makers"
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    source_unit_id = "army-alpha:intercessor-unit-1"
    attacking_unit_id = "army-beta:intercessor-unit-3"
    attacking_model_id = unit_by_id(state, attacking_unit_id).own_models[0].model_instance_id
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Swarm", "Nurgle"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(_datasheet_ability(datasheets.NURGLINGS_MISCHIEF_MAKERS_SOURCE_ID),),
    )
    registry = _datasheet_runtime_modifier_registry()

    assert (
        registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=attacking_unit_id,
                attacker_model_instance_id=attacking_model_id,
                target_unit_instance_id=source_unit_id,
                weapon_profile=_melee_profile(),
                source_phase=BattlePhase.FIGHT,
            )
        )
        == -1
    )

    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=attacking_unit_id,
        keywords=("Vehicle", "Titanic"),
        faction_keywords=(),
    )
    assert (
        registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=attacking_unit_id,
                attacker_model_instance_id=attacking_model_id,
                target_unit_instance_id=source_unit_id,
                weapon_profile=_melee_profile(),
                source_phase=BattlePhase.FIGHT,
            )
        )
        == 0
    )


def test_poxbringer_feculent_despair_modifies_enemy_battle_shock_within_aura() -> None:
    state = battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((1.0, 0.0),),
    )
    state.game_id = "phase17g-feculent-despair"
    state.active_player_id = "player-b"
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-beta:intercessor-unit-3"
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Nurgle"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(_datasheet_ability(datasheets.POXBRINGER_FECULENT_DESPAIR_SOURCE_ID),),
    )
    target_unit = unit_by_id(state, target_unit_id)
    request = BattleShockTestRequest.for_unit(
        request_id="phase17g-feculent-despair-request",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-b",
        unit_instance_id=target_unit_id,
        reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
        leadership_target=6,
        below_half_strength_context=BelowHalfStrengthContext.from_unit(
            player_id="player-b",
            unit=target_unit,
            starting_strength=state.starting_strength_record_for_unit(target_unit_id),
            current_model_ids=target_unit.own_model_ids(),
        ),
    )
    hooks = BattleShockHookRegistry.from_bindings(
        datasheets.runtime_contribution().battle_shock_hook_bindings
    )
    context = BattleShockModifierContext(
        state=state,
        request=request,
        active_player_id="player-b",
        phase=BattlePhase.COMMAND,
        phase_start_battle_shocked_unit_ids=(),
    )

    modifiers = hooks.modifiers_for(context)

    assert len(modifiers) == 1
    modifier = modifiers[0]
    assert modifier.modifier_id == (
        f"{datasheets.FECULENT_DESPAIR_HOOK_ID}:{request.request_id}:player-a"
    )
    assert modifier.source_id == datasheets.POXBRINGER_FECULENT_DESPAIR_SOURCE_ID
    assert modifier.operand == -1

    _place_units_near_center(
        state,
        source_unit_id=source_unit_id,
        target_unit_id=target_unit_id,
        target_offset=(8.0, 0.0),
    )
    assert hooks.modifiers_for(context) == ()


def test_infected_outbreak_records_sticky_state_when_plaguebearers_control_objective() -> None:
    state = battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((8.0, 0.0),),
    )
    state.game_id = "phase17g-infected-outbreak"
    state.active_player_id = "player-a"
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    plaguebearers = unit_by_id(state, "army-alpha:intercessor-unit-1")
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=plaguebearers.unit_instance_id,
        keywords=("Battleline", "Infantry", "Nurgle"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(
            _datasheet_ability(datasheets.PLAGUEBEARERS_INFECTED_OUTBREAK_SOURCE_ID),
        ),
    )
    decisions = DecisionController()
    contribution = datasheets.runtime_contribution()
    context = PhaseEndObjectiveControlContext(
        state=state,
        event_log=decisions.event_log,
        completed_phase=BattlePhase.COMMAND,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    sticky_states = contribution.phase_end_objective_control_hook_bindings[0].handler(context)

    assert len(sticky_states) == 1
    sticky_state = sticky_states[0]
    assert sticky_state.source_rule_id == datasheets.PLAGUEBEARERS_INFECTED_OUTBREAK_SOURCE_ID
    assert sticky_state.player_id == "player-a"
    assert sticky_state.objective_id == center_marker_definition(state).objective_marker_id
    replay_payload = cast(dict[str, JsonValue], sticky_state.replay_payload)
    assert replay_payload["hook_id"] == datasheets.INFECTED_OUTBREAK_HOOK_ID


def test_relentless_carnage_fight_end_handler_requests_and_resolves_mortal_wounds() -> None:
    state = battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((0.5, 0.0),),
    )
    state.game_id = "phase17g-relentless-carnage"
    state.active_player_id = "player-a"
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-beta:intercessor-unit-3"
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Monster", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(
            _datasheet_ability(datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID),
        ),
    )
    _set_fight_phase_end_state(state, engaged_unit_ids=(source_unit_id, target_unit_id))
    decisions = DecisionController()
    contribution = datasheets.runtime_contribution()
    handler = FightPhaseHandler(
        fight_phase_end_hooks=FightPhaseEndHookRegistry.from_bindings(
            contribution.fight_phase_end_hook_bindings
        )
    )
    starting_wounds = sum(
        model.wounds_remaining for model in unit_by_id(state, target_unit_id).own_models
    )

    status = handler.begin_phase(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = _decision_request(status.decision_request)
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request.actor_id == "player-a"
    assert (
        request_payload["source_rule_id"] == datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID
    )
    assert request_payload["eligible_enemy_unit_instance_ids"] == [target_unit_id]
    result = DecisionResult.for_request(
        result_id="result-relentless-carnage",
        request=request,
        selected_option_id=request.options[1].option_id,
    )
    assert (
        invalid_fight_phase_end_faction_rule_status(
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
    payload = _event_payload(decisions, datasheets.RELENTLESS_CARNAGE_RESOLVED_EVENT)
    assert payload["source_rule_id"] == datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID
    assert payload["hook_id"] == datasheets.RELENTLESS_CARNAGE_HOOK_ID
    assert payload["target_enemy_unit_instance_id"] == target_unit_id
    assert payload["mortal_wounds"] == 4
    d6_payload = cast(dict[str, JsonValue], payload["d6_result"])
    assert d6_payload["current_values"] == [6, 3, 3, 5, 2, 5, 4, 3]
    application = cast(dict[str, JsonValue], payload["mortal_wound_application"])
    assert application["mortal_wounds"] == 4
    assert (
        starting_wounds
        - sum(model.wounds_remaining for model in unit_by_id(state, target_unit_id).own_models)
        == 4
    )
    assert (
        datasheets.relentless_carnage_fight_phase_end_request(
            FightPhaseEndRequestContext(state=state, decisions=decisions)
        )
        is None
    )


def test_relentless_carnage_fight_end_handler_records_decline_without_damage() -> None:
    state = battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((0.5, 0.0),),
    )
    state.game_id = "phase17g-relentless-carnage-decline"
    state.active_player_id = "player-a"
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-beta:intercessor-unit-3"
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Monster", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(
            _datasheet_ability(datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID),
        ),
    )
    _set_fight_phase_end_state(state, engaged_unit_ids=(source_unit_id, target_unit_id))
    decisions = DecisionController()
    contribution = datasheets.runtime_contribution()
    handler = FightPhaseHandler(
        fight_phase_end_hooks=FightPhaseEndHookRegistry.from_bindings(
            contribution.fight_phase_end_hook_bindings
        )
    )
    starting_wounds = sum(
        model.wounds_remaining for model in unit_by_id(state, target_unit_id).own_models
    )
    status = handler.begin_phase(state=state, decisions=decisions)
    request = _decision_request(status.decision_request)
    decline_option = request.options[0]
    result = DecisionResult.for_request(
        result_id="result-relentless-carnage-decline",
        request=request,
        selected_option_id=decline_option.option_id,
    )
    decisions.submit_result(result)

    assert handler.apply_decision(state=state, result=result, decisions=decisions) is None

    payload = _event_payload(decisions, datasheets.RELENTLESS_CARNAGE_DECLINED_EVENT)
    assert payload["selected_option_id"] == decline_option.option_id
    assert payload["target_enemy_unit_instance_id"] is None
    assert (
        sum(model.wounds_remaining for model in unit_by_id(state, target_unit_id).own_models)
        == starting_wounds
    )


def test_relentless_carnage_records_zero_mortal_wounds_without_application() -> None:
    state = _relentless_carnage_state(game_id="phase17g-zero-mw-real-218")
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-beta:intercessor-unit-3"
    decisions = DecisionController()
    contribution = datasheets.runtime_contribution()
    handler = FightPhaseHandler(
        fight_phase_end_hooks=FightPhaseEndHookRegistry.from_bindings(
            contribution.fight_phase_end_hook_bindings
        )
    )
    starting_wounds = sum(
        model.wounds_remaining for model in unit_by_id(state, target_unit_id).own_models
    )
    status = handler.begin_phase(state=state, decisions=decisions)
    request = _decision_request(status.decision_request)
    result = DecisionResult.for_request(
        result_id="result-relentless-carnage-zero-mw",
        request=request,
        selected_option_id=request.options[1].option_id,
    )
    decisions.submit_result(result)

    assert handler.apply_decision(state=state, result=result, decisions=decisions) is None

    payload = _event_payload(decisions, datasheets.RELENTLESS_CARNAGE_RESOLVED_EVENT)
    assert payload["source_unit_instance_id"] == source_unit_id
    assert payload["target_enemy_unit_instance_id"] == target_unit_id
    assert payload["mortal_wounds"] == 0
    assert payload["mortal_wound_application"] is None
    assert (
        sum(model.wounds_remaining for model in unit_by_id(state, target_unit_id).own_models)
        == starting_wounds
    )


def test_relentless_carnage_prior_fight_phase_record_does_not_block_later_round() -> None:
    state = battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((0.5, 0.0),),
    )
    state.game_id = "phase17g-relentless-carnage-record-scope"
    state.active_player_id = "player-a"
    state.battle_round = 2
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-beta:intercessor-unit-3"
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Monster", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(
            _datasheet_ability(datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID),
        ),
    )
    _set_fight_phase_end_state(state, engaged_unit_ids=(source_unit_id, target_unit_id))
    decisions = DecisionController()
    decisions.event_log.append(
        datasheets.RELENTLESS_CARNAGE_RESOLVED_EVENT,
        _relentless_carnage_record_payload(
            battle_round=1,
            source_unit_instance_id=source_unit_id,
        ),
    )

    assert (
        datasheets.relentless_carnage_fight_phase_end_request(
            FightPhaseEndRequestContext(state=state, decisions=decisions)
        )
        is not None
    )
    decisions.event_log.append(
        datasheets.RELENTLESS_CARNAGE_RESOLVED_EVENT,
        _relentless_carnage_record_payload(
            battle_round=state.battle_round,
            source_unit_instance_id=source_unit_id,
        ),
    )
    assert (
        datasheets.relentless_carnage_fight_phase_end_request(
            FightPhaseEndRequestContext(state=state, decisions=decisions)
        )
        is None
    )


def test_relentless_carnage_result_handler_rejects_payload_drift() -> None:
    state = _relentless_carnage_state(game_id="phase17g-relentless-carnage-drift")
    decisions = DecisionController()
    request = _relentless_carnage_request(state=state, decisions=decisions)
    valid_result = DecisionResult.for_request(
        result_id="result-relentless-carnage-drift",
        request=request,
        selected_option_id=request.options[1].option_id,
    )
    context = FightPhaseEndResultContext(
        state=state,
        decisions=decisions,
        request=request,
        result=replace(
            valid_result,
            payload={
                **cast(dict[str, JsonValue], valid_result.payload),
                "source_rule_id": "phase17g-other-source",
            },
        ),
    )

    with pytest.raises(GameLifecycleError, match="payload drift"):
        datasheets.apply_relentless_carnage_fight_phase_end_result(context)

    submission_drift_context = replace(
        context,
        result=replace(
            valid_result,
            payload={
                **cast(dict[str, JsonValue], valid_result.payload),
                "submission_kind": "phase17g_other_submission",
            },
        ),
    )
    with pytest.raises(GameLifecycleError, match="submission kind drift"):
        datasheets.apply_relentless_carnage_fight_phase_end_result(submission_drift_context)

    missing_target_context = replace(
        context,
        result=replace(
            valid_result,
            payload={
                **cast(dict[str, JsonValue], valid_result.payload),
                "target_enemy_unit_instance_id": None,
            },
        ),
    )
    with pytest.raises(GameLifecycleError, match="target must be selected"):
        datasheets.apply_relentless_carnage_fight_phase_end_result(missing_target_context)


def test_relentless_carnage_result_handler_rejects_target_drift() -> None:
    state = _relentless_carnage_state(game_id="phase17g-relentless-carnage-target-drift")
    decisions = DecisionController()
    request = _relentless_carnage_request(state=state, decisions=decisions)
    valid_result = DecisionResult.for_request(
        result_id="result-relentless-carnage-target-drift",
        request=request,
        selected_option_id=request.options[1].option_id,
    )
    unknown_target_context = FightPhaseEndResultContext(
        state=state,
        decisions=decisions,
        request=request,
        result=replace(
            valid_result,
            payload={
                **cast(dict[str, JsonValue], valid_result.payload),
                "target_enemy_unit_instance_id": "army-beta:missing-unit",
            },
        ),
    )
    with pytest.raises(GameLifecycleError, match="not in the request snapshot"):
        datasheets.apply_relentless_carnage_fight_phase_end_result(unknown_target_context)

    _place_units_near_center(
        state,
        source_unit_id="army-alpha:intercessor-unit-1",
        target_unit_id="army-beta:intercessor-unit-3",
        target_offset=(8.0, 0.0),
    )
    no_longer_eligible_context = FightPhaseEndResultContext(
        state=state,
        decisions=decisions,
        request=request,
        result=valid_result,
    )
    with pytest.raises(GameLifecycleError, match="no longer eligible"):
        datasheets.apply_relentless_carnage_fight_phase_end_result(no_longer_eligible_context)


def test_relentless_carnage_result_handler_ignores_other_hooks_and_requires_source() -> None:
    state = _relentless_carnage_state(game_id="phase17g-relentless-carnage-source-drift")
    decisions = DecisionController()
    request = _relentless_carnage_request(state=state, decisions=decisions)
    result = DecisionResult.for_request(
        result_id="result-relentless-carnage-source-drift",
        request=request,
        selected_option_id=request.options[1].option_id,
    )
    other_hook_request = replace(
        request,
        payload={**cast(dict[str, JsonValue], request.payload), "hook_id": "phase17g-other-hook"},
    )
    assert (
        datasheets.apply_relentless_carnage_fight_phase_end_result(
            FightPhaseEndResultContext(
                state=state,
                decisions=decisions,
                request=other_hook_request,
                result=result,
            )
        )
        is False
    )

    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Character", "Monster", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(),
    )
    with pytest.raises(GameLifecycleError, match="source ability is missing"):
        datasheets.apply_relentless_carnage_fight_phase_end_result(
            FightPhaseEndResultContext(
                state=state,
                decisions=decisions,
                request=request,
                result=result,
            )
        )


def test_datasheet_public_handlers_reject_wrong_context_types() -> None:
    with pytest.raises(GameLifecycleError, match="HitRollModifierContext"):
        datasheets.daemon_lord_of_khorne_hit_roll_modifier(cast(HitRollModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="WeaponProfileModifierContext"):
        datasheets.daemon_lord_of_tzeentch_weapon_profile_modifier(
            cast(WeaponProfileModifierContext, object())
        )
    with pytest.raises(GameLifecycleError, match="WeaponProfileModifierContext"):
        datasheets.rage_embodied_weapon_profile_modifier(
            cast(WeaponProfileModifierContext, object())
        )
    with pytest.raises(GameLifecycleError, match="WeaponProfileModifierContext"):
        datasheets.daemon_lord_of_slaanesh_weapon_profile_modifier(
            cast(WeaponProfileModifierContext, object())
        )
    with pytest.raises(GameLifecycleError, match="MovementBudgetModifierContext"):
        datasheets.deluge_movement_budget_modifier(cast(MovementBudgetModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="ObjectiveControlModifierContext"):
        datasheets.deluge_objective_control_modifier(
            cast(ObjectiveControlModifierContext, object())
        )
    with pytest.raises(GameLifecycleError, match="HitRollModifierContext"):
        datasheets.mischief_makers_hit_roll_modifier(cast(HitRollModifierContext, object()))
    with pytest.raises(GameLifecycleError, match="BattleShockModifierContext"):
        datasheets.feculent_despair_battle_shock_modifiers(
            cast(BattleShockModifierContext, object())
        )
    with pytest.raises(GameLifecycleError, match="phase-end context"):
        datasheets.infected_outbreak_sticky_objective_states(
            cast(PhaseEndObjectiveControlContext, object())
        )
    with pytest.raises(GameLifecycleError, match="Fight-end request context"):
        datasheets.relentless_carnage_fight_phase_end_request(
            cast(FightPhaseEndRequestContext, object())
        )
    with pytest.raises(GameLifecycleError, match="Fight-end result context"):
        datasheets.apply_relentless_carnage_fight_phase_end_result(
            cast(FightPhaseEndResultContext, object())
        )
    with pytest.raises(GameLifecycleError, match="FNP continuation requires context"):
        datasheets.apply_relentless_carnage_mortal_wound_feel_no_pain_decision(
            cast(MortalWoundFeelNoPainContinuationContext, object())
        )


def test_daemon_lord_modifiers_ignore_wrong_weapon_types_and_duplicate_sources() -> None:
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    state.game_id = "phase17g-daemon-lord-weapon-types"
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-2"
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Monster", "Khorne", "Tzeentch"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(
            _datasheet_ability(datasheets.BLOODTHIRSTER_DAEMON_LORD_SOURCE_ID),
            _datasheet_ability(datasheets.LORD_OF_CHANGE_DAEMON_LORD_SOURCE_ID),
        ),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Khorne", "Tzeentch"),
        faction_keywords=("Legiones Daemonica",),
    )
    _place_units_near_center(
        state,
        source_unit_id=source_unit_id,
        target_unit_id=target_unit_id,
        target_offset=(1.0, 0.0),
    )
    target_model_id = unit_by_id(state, target_unit_id).own_models[0].model_instance_id
    registry = _datasheet_runtime_modifier_registry()

    assert (
        registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=target_unit_id,
                attacker_model_instance_id=target_model_id,
                target_unit_instance_id="army-beta:intercessor-unit-3",
                weapon_profile=_ranged_profile(),
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == 0
    )
    assert (
        registry.modified_weapon_profile(
            WeaponProfileModifierContext(
                state=state,
                source_phase=BattlePhase.FIGHT,
                attacking_unit_instance_id=target_unit_id,
                attacker_model_instance_id=target_model_id,
                target_unit_instance_id="army-beta:intercessor-unit-3",
                weapon_profile=_melee_profile(),
            )
        )
        == _melee_profile()
    )
    already_modified = replace(
        _ranged_profile(),
        source_ids=(datasheets.LORD_OF_CHANGE_DAEMON_LORD_SOURCE_ID,),
    )
    assert (
        registry.modified_weapon_profile(
            WeaponProfileModifierContext(
                state=state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=target_unit_id,
                attacker_model_instance_id=target_model_id,
                target_unit_instance_id="army-beta:intercessor-unit-3",
                weapon_profile=already_modified,
            )
        )
        == already_modified
    )


def test_relentless_carnage_mortal_wound_routing_records_pending_fnp() -> None:
    state = _relentless_carnage_state(game_id="phase17g-relentless-carnage-pending-fnp")
    decisions = DecisionController()
    resolution_payload: dict[str, JsonValue] = {
        "target_enemy_unit_instance_id": "army-beta:intercessor-unit-3",
    }
    progress = MortalWoundApplicationProgress.start(
        application_id="phase17g-relentless-carnage-pending-application",
        source_rule_id=datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID,
        source_context={
            "source_kind": datasheets.RELENTLESS_CARNAGE_SOURCE_KIND,
            "phase": BattlePhase.FIGHT.value,
            "resolution_payload": resolution_payload,
        },
        target_unit_instance_id="army-beta:intercessor-unit-3",
        defender_player_id="player-b",
        mortal_wounds=1,
        spill_over=True,
    )
    routed_request = _generic_fight_end_request(state)

    status = datasheets._resolve_routed_relentless_carnage_mortal_wounds(  # pyright: ignore[reportPrivateUsage]
        state=state,
        decisions=decisions,
        feel_no_pain_result_id=None,
        routed_request=routed_request,
        routed_application=None,
        routed_progress=progress,
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request == routed_request
    payload = _event_payload(decisions, datasheets.RELENTLESS_CARNAGE_PENDING_EVENT)
    assert payload["remaining_mortal_wounds"] == 1
    assert payload["feel_no_pain_request_id"] == routed_request.request_id


def test_datasheet_private_helpers_fail_fast_on_invalid_inputs() -> None:
    state = _relentless_carnage_state(game_id="phase17g-datasheet-helper-guards")
    decisions = DecisionController()
    progress = MortalWoundApplicationProgress.start(
        application_id="phase17g-helper-guard-application",
        source_rule_id=datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID,
        source_context={
            "source_kind": datasheets.RELENTLESS_CARNAGE_SOURCE_KIND,
            "phase": BattlePhase.FIGHT.value,
            "resolution_payload": {
                "target_enemy_unit_instance_id": "army-beta:intercessor-unit-3",
            },
        },
        target_unit_instance_id="army-beta:intercessor-unit-3",
        defender_player_id="player-b",
        mortal_wounds=1,
        spill_over=True,
    )

    with pytest.raises(GameLifecycleError, match="requires GameState"):
        datasheets._resolve_routed_relentless_carnage_mortal_wounds(  # pyright: ignore[reportPrivateUsage]
            state=object(),
            decisions=decisions,
            feel_no_pain_result_id=None,
            routed_request=None,
            routed_application=None,
            routed_progress=progress,
        )
    with pytest.raises(GameLifecycleError, match="requires DecisionController"):
        datasheets._resolve_routed_relentless_carnage_mortal_wounds(  # pyright: ignore[reportPrivateUsage]
            state=state,
            decisions=object(),
            feel_no_pain_result_id=None,
            routed_request=None,
            routed_application=None,
            routed_progress=progress,
        )
    with pytest.raises(GameLifecycleError, match="requires progress"):
        datasheets._resolve_routed_relentless_carnage_mortal_wounds(  # pyright: ignore[reportPrivateUsage]
            state=state,
            decisions=decisions,
            feel_no_pain_result_id=None,
            routed_request=None,
            routed_application=None,
            routed_progress=cast(MortalWoundApplicationProgress, object()),
        )
    with pytest.raises(GameLifecycleError, match="did not produce application"):
        datasheets._resolve_routed_relentless_carnage_mortal_wounds(  # pyright: ignore[reportPrivateUsage]
            state=state,
            decisions=decisions,
            feel_no_pain_result_id=None,
            routed_request=None,
            routed_application=None,
            routed_progress=progress,
        )
    for source_context in (
        None,
        {"source_kind": "phase17g-other-source", "phase": BattlePhase.FIGHT.value},
        {
            "source_kind": datasheets.RELENTLESS_CARNAGE_SOURCE_KIND,
            "phase": BattlePhase.COMMAND.value,
        },
        {
            "source_kind": datasheets.RELENTLESS_CARNAGE_SOURCE_KIND,
            "phase": BattlePhase.FIGHT.value,
        },
    ):
        with pytest.raises(GameLifecycleError):
            datasheets._relentless_carnage_mortal_wound_source_context_from_payload(  # pyright: ignore[reportPrivateUsage]
                cast(JsonValue, source_context)
            )

    with pytest.raises(GameLifecycleError, match="target lookup requires GameState"):
        datasheets._enemy_rules_unit_ids_within_source_engagement_range(  # pyright: ignore[reportPrivateUsage]
            state=object(),
            source_unit_instance_id="army-alpha:intercessor-unit-1",
        )
    state_without_battlefield = _relentless_carnage_state(
        game_id="phase17g-datasheet-helper-no-battlefield"
    )
    state_without_battlefield.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        datasheets._enemy_rules_unit_ids_within_source_engagement_range(  # pyright: ignore[reportPrivateUsage]
            state=state_without_battlefield,
            source_unit_instance_id="army-alpha:intercessor-unit-1",
        )
    with pytest.raises(GameLifecycleError, match="Rules-unit geometry lookup requires GameState"):
        datasheets._alive_geometry_models_for_rules_unit(  # pyright: ignore[reportPrivateUsage]
            state=object(),
            scenario=cast(BattlefieldScenario, object()),
            rules_unit=cast(RulesUnitView, object()),
        )
    with pytest.raises(GameLifecycleError, match="Unit geometry lookup requires GameState"):
        datasheets._alive_geometry_models_for_unit(  # pyright: ignore[reportPrivateUsage]
            state=object(),
            scenario=cast(BattlefieldScenario, object()),
            unit=cast(UnitInstance, object()),
        )
    with pytest.raises(GameLifecycleError, match="Engagement range lookup requires GameState"):
        datasheets._any_models_within_engagement_range(  # pyright: ignore[reportPrivateUsage]
            state=object(),
            first_models=(),
            second_models=(),
        )
    with pytest.raises(GameLifecycleError, match="Datasheet ability lookup requires UnitInstance"):
        datasheets._unit_has_datasheet_ability_source(  # pyright: ignore[reportPrivateUsage]
            cast(UnitInstance, object()),
            datasheets.BLOODTHIRSTER_DAEMON_LORD_SOURCE_ID,
        )
    with pytest.raises(GameLifecycleError, match="Chaos Daemons army lookup requires GameState"):
        datasheets._chaos_daemons_armies(object())  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="Unit instance is unknown"):
        datasheets._unit_by_id((), unit_instance_id="phase17g-missing")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="Active player lookup requires GameState"):
        datasheets._active_player_id(object())  # pyright: ignore[reportPrivateUsage]
    inactive_state = _relentless_carnage_state(game_id="phase17g-datasheet-helper-inactive")
    inactive_state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires active_player_id"):
        datasheets._active_player_id(inactive_state)  # pyright: ignore[reportPrivateUsage]


def test_relentless_carnage_does_not_request_without_source_or_engaged_enemy() -> None:
    missing_source_state = battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((0.5, 0.0),),
    )
    missing_source_state.game_id = "phase17g-relentless-carnage-no-source"
    missing_source_state.active_player_id = "player-a"
    _set_current_battle_phase(missing_source_state, BattlePhase.FIGHT)
    _mark_player_as_chaos_daemons(missing_source_state, player_id="player-a")
    _set_fight_phase_end_state(
        missing_source_state,
        engaged_unit_ids=("army-alpha:intercessor-unit-1", "army-beta:intercessor-unit-3"),
    )

    assert (
        datasheets.relentless_carnage_fight_phase_end_request(
            FightPhaseEndRequestContext(
                state=missing_source_state,
                decisions=DecisionController(),
            )
        )
        is None
    )

    no_target_state = battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((8.0, 0.0),),
    )
    no_target_state.game_id = "phase17g-relentless-carnage-no-target"
    no_target_state.active_player_id = "player-a"
    _set_current_battle_phase(no_target_state, BattlePhase.FIGHT)
    _mark_player_as_chaos_daemons(no_target_state, player_id="player-a")
    _replace_unit_keywords_and_abilities(
        no_target_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        keywords=("Character", "Monster", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(
            _datasheet_ability(datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID),
        ),
    )
    _set_fight_phase_end_state(
        no_target_state,
        engaged_unit_ids=("army-alpha:intercessor-unit-1", "army-beta:intercessor-unit-3"),
    )

    assert (
        datasheets.relentless_carnage_fight_phase_end_request(
            FightPhaseEndRequestContext(state=no_target_state, decisions=DecisionController())
        )
        is None
    )


def test_datasheet_runtime_contribution_registers_all_consumed_bindings() -> None:
    contribution = datasheets.runtime_contribution()

    assert [binding.modifier_id for binding in contribution.hit_roll_modifier_bindings] == [
        datasheets.KHORNE_HIT_MODIFIER_ID,
        datasheets.MISCHIEF_MAKERS_HIT_MODIFIER_ID,
    ]
    assert [binding.modifier_id for binding in contribution.movement_budget_modifier_bindings] == [
        datasheets.DELUGE_MOVEMENT_MODIFIER_ID,
    ]
    assert [
        binding.modifier_id for binding in contribution.objective_control_modifier_bindings
    ] == [
        datasheets.DELUGE_OBJECTIVE_CONTROL_MODIFIER_ID,
    ]
    assert [binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings] == [
        datasheets.RAGE_EMBODIED_ATTACKS_MODIFIER_ID,
        datasheets.SLAANESH_AP_MODIFIER_ID,
        datasheets.TZEENTCH_STRENGTH_MODIFIER_ID,
    ]
    assert [binding.hook_id for binding in contribution.battle_shock_hook_bindings] == [
        datasheets.FECULENT_DESPAIR_HOOK_ID
    ]
    objective_hook_ids = [
        binding.hook_id for binding in contribution.phase_end_objective_control_hook_bindings
    ]
    assert objective_hook_ids == [datasheets.INFECTED_OUTBREAK_HOOK_ID]
    assert [binding.hook_id for binding in contribution.fight_phase_end_hook_bindings] == [
        datasheets.RELENTLESS_CARNAGE_HOOK_ID
    ]
    fnp_hook_ids = [
        binding.hook_id for binding in contribution.mortal_wound_feel_no_pain_hook_bindings
    ]
    assert fnp_hook_ids == [datasheets.RELENTLESS_CARNAGE_FNP_HOOK_ID]


def test_infected_outbreak_and_daemon_lord_paths_ignore_nonmatching_windows() -> None:
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    state.game_id = "phase17g-datasheet-nonmatching"
    state.active_player_id = "player-a"
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-2"
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Monster", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(_datasheet_ability(datasheets.BLOODTHIRSTER_DAEMON_LORD_SOURCE_ID),),
    )
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=target_unit_id,
        keywords=("Infantry", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
    )
    _place_units_near_center(
        state,
        source_unit_id=source_unit_id,
        target_unit_id=target_unit_id,
        target_offset=(8.0, 0.0),
    )
    registry = _datasheet_runtime_modifier_registry()

    assert (
        registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=target_unit_id,
                attacker_model_instance_id=unit_by_id(state, target_unit_id)
                .own_models[0]
                .model_instance_id,
                target_unit_instance_id="army-beta:intercessor-unit-3",
                weapon_profile=_melee_profile(),
                source_phase=BattlePhase.FIGHT,
            )
        )
        == 0
    )

    contribution = datasheets.runtime_contribution()
    assert (
        contribution.phase_end_objective_control_hook_bindings[0].handler(
            PhaseEndObjectiveControlContext(
                state=state,
                event_log=DecisionController().event_log,
                completed_phase=BattlePhase.FIGHT,
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            )
        )
        == ()
    )


def test_fight_phase_end_hook_registry_routes_request_and_result() -> None:
    state = _generic_fight_end_state("phase17g-generic-fight-end-hook")
    decisions = DecisionController()
    request = _generic_fight_end_request(state)

    def request_handler(context: FightPhaseEndRequestContext) -> DecisionRequest:
        assert context.state is state
        return request

    def result_handler(context: FightPhaseEndResultContext) -> bool:
        assert context.request.request_id == request.request_id
        assert context.result.selected_option_id == request.options[0].option_id
        return True

    registry = FightPhaseEndHookRegistry.from_bindings(
        (
            FightPhaseEndHookBinding(
                hook_id="phase17g-generic-fight-end-hook",
                source_id="phase17g-generic-fight-end-source",
                request_handler=request_handler,
                result_handler=result_handler,
            ),
        )
    )

    status = request_fight_phase_end_rule_if_available(
        registry=registry,
        state=state,
        decisions=decisions,
    )
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request == request
    result = DecisionResult.for_request(
        result_id="phase17g-generic-fight-end-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    decisions.submit_result(result)

    assert (
        apply_fight_phase_end_result(
            registry=registry,
            state=state,
            decisions=decisions,
            result=result,
        )
        is None
    )


def test_fight_phase_end_hook_registry_returns_status_and_rejects_unhandled_result() -> None:
    state = _generic_fight_end_state("phase17g-generic-fight-end-status")
    request = _generic_fight_end_request(state)
    result = DecisionResult.for_request(
        result_id="phase17g-generic-fight-end-status-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    decisions = DecisionController()
    decisions.request_decision(request)
    decisions.submit_result(result)
    blocked_status = LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message="phase17g-generic-blocked",
    )

    status_registry = FightPhaseEndHookRegistry.from_bindings(
        (
            FightPhaseEndHookBinding(
                hook_id="phase17g-generic-fight-end-status-hook",
                source_id="phase17g-generic-fight-end-status-source",
                result_handler=lambda context: blocked_status,
            ),
        )
    )
    assert (
        apply_fight_phase_end_result(
            registry=status_registry,
            state=state,
            decisions=decisions,
            result=result,
        )
        == blocked_status
    )

    with pytest.raises(GameLifecycleError, match="was not handled"):
        apply_fight_phase_end_result(
            registry=FightPhaseEndHookRegistry.empty(),
            state=state,
            decisions=decisions,
            result=result,
        )


def test_fight_phase_end_hook_registry_rejects_invalid_binding_outputs() -> None:
    state = _generic_fight_end_state("phase17g-generic-fight-end-invalid")
    decisions = DecisionController()
    context = FightPhaseEndRequestContext(state=state, decisions=decisions)

    def invalid_request_handler(hook_context: FightPhaseEndRequestContext) -> object:
        assert hook_context is context
        return "not-a-request"

    invalid_request_registry = FightPhaseEndHookRegistry.from_bindings(
        (
            FightPhaseEndHookBinding(
                hook_id="phase17g-invalid-request-hook",
                source_id="phase17g-invalid-request-source",
                request_handler=cast(FightPhaseEndRequestHandler, invalid_request_handler),
            ),
        )
    )

    with pytest.raises(GameLifecycleError, match="DecisionRequest or None"):
        invalid_request_registry.next_request_for(context)

    request = _generic_fight_end_request(state)
    result = DecisionResult.for_request(
        result_id="phase17g-invalid-result-output",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    result_context = FightPhaseEndResultContext(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )

    def invalid_result_handler(hook_context: FightPhaseEndResultContext) -> object:
        assert hook_context is result_context
        return "not-a-result"

    invalid_result_registry = FightPhaseEndHookRegistry.from_bindings(
        (
            FightPhaseEndHookBinding(
                hook_id="phase17g-invalid-result-hook",
                source_id="phase17g-invalid-result-source",
                result_handler=cast(FightPhaseEndResultHandler, invalid_result_handler),
            ),
        )
    )

    with pytest.raises(GameLifecycleError, match="bool or status"):
        invalid_result_registry.apply_result(result_context)


def test_fight_phase_end_hook_registry_guardrails() -> None:
    state = _generic_fight_end_state("phase17g-fight-end-guardrails")
    decisions = DecisionController()
    request = _generic_fight_end_request(state)
    result = DecisionResult.for_request(
        result_id="phase17g-fight-end-guardrails-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )

    with pytest.raises(GameLifecycleError, match="state must be GameState"):
        FightPhaseEndRequestContext(
            state=cast(GameState, object()),
            decisions=decisions,
        )
    with pytest.raises(GameLifecycleError, match="decisions must be DecisionController"):
        FightPhaseEndRequestContext(
            state=state,
            decisions=cast(DecisionController, object()),
        )
    with pytest.raises(GameLifecycleError, match="state must be GameState"):
        FightPhaseEndResultContext(
            state=cast(GameState, object()),
            decisions=decisions,
            request=request,
            result=result,
        )
    with pytest.raises(GameLifecycleError, match="decisions must be DecisionController"):
        FightPhaseEndResultContext(
            state=state,
            decisions=cast(DecisionController, object()),
            request=request,
            result=result,
        )
    with pytest.raises(GameLifecycleError, match="request must be DecisionRequest"):
        FightPhaseEndResultContext(
            state=state,
            decisions=decisions,
            request=cast(DecisionRequest, object()),
            result=result,
        )
    with pytest.raises(GameLifecycleError, match="result must be DecisionResult"):
        FightPhaseEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=cast(DecisionResult, object()),
        )
    with pytest.raises(GameLifecycleError, match="decision_type drift"):
        FightPhaseEndResultContext(
            state=state,
            decisions=decisions,
            request=replace(request, decision_type="phase17g_other_decision"),
            result=result,
        )
    with pytest.raises(GameLifecycleError, match="requires a handler"):
        FightPhaseEndHookBinding(
            hook_id="phase17g-empty-hook",
            source_id="phase17g-empty-source",
        )
    with pytest.raises(GameLifecycleError, match="request_handler must be callable"):
        FightPhaseEndHookBinding(
            hook_id="phase17g-noncallable-request-hook",
            source_id="phase17g-noncallable-request-source",
            request_handler=cast(FightPhaseEndRequestHandler, object()),
        )
    with pytest.raises(GameLifecycleError, match="result_handler must be callable"):
        FightPhaseEndHookBinding(
            hook_id="phase17g-noncallable-result-hook",
            source_id="phase17g-noncallable-result-source",
            result_handler=cast(FightPhaseEndResultHandler, object()),
        )

    registry = FightPhaseEndHookRegistry.from_bindings(
        (
            FightPhaseEndHookBinding(
                hook_id="phase17g-result-only-hook",
                source_id="phase17g-result-only-source",
                result_handler=lambda context: False,
            ),
            FightPhaseEndHookBinding(
                hook_id="phase17g-empty-request-hook",
                source_id="phase17g-empty-request-source",
                request_handler=lambda context: None,
            ),
        )
    )
    assert registry.all_bindings()
    assert (
        registry.next_request_for(FightPhaseEndRequestContext(state=state, decisions=decisions))
        is None
    )
    assert (
        request_fight_phase_end_rule_if_available(
            registry=FightPhaseEndHookRegistry.empty(),
            state=state,
            decisions=decisions,
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="request hooks require context"):
        registry.next_request_for(cast(FightPhaseEndRequestContext, object()))
    with pytest.raises(GameLifecycleError, match="result hooks require context"):
        registry.apply_result(cast(FightPhaseEndResultContext, object()))


def test_fight_phase_end_hook_registry_rejects_multiple_requests_and_results() -> None:
    state = _generic_fight_end_state("phase17g-fight-end-multiple-hooks")
    decisions = DecisionController()
    request = _generic_fight_end_request(state)
    other_request = replace(request, request_id="phase17g-fight-end-other-request")
    context = FightPhaseEndRequestContext(state=state, decisions=decisions)
    multiple_request_registry = FightPhaseEndHookRegistry.from_bindings(
        (
            FightPhaseEndHookBinding(
                hook_id="phase17g-request-one-hook",
                source_id="phase17g-request-one-source",
                request_handler=lambda hook_context: request,
            ),
            FightPhaseEndHookBinding(
                hook_id="phase17g-request-two-hook",
                source_id="phase17g-request-two-source",
                request_handler=lambda hook_context: other_request,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="multiple simultaneous requests"):
        multiple_request_registry.next_request_for(context)

    result = DecisionResult.for_request(
        result_id="phase17g-fight-end-multiple-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    result_context = FightPhaseEndResultContext(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    multiple_result_registry = FightPhaseEndHookRegistry.from_bindings(
        (
            FightPhaseEndHookBinding(
                hook_id="phase17g-result-one-hook",
                source_id="phase17g-result-one-source",
                result_handler=lambda hook_context: True,
            ),
            FightPhaseEndHookBinding(
                hook_id="phase17g-result-two-hook",
                source_id="phase17g-result-two-source",
                result_handler=lambda hook_context: True,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="handled by multiple hooks"):
        multiple_result_registry.apply_result(result_context)


def test_fight_phase_end_context_requires_end_window() -> None:
    for game_id, phase, fight_state_kind, message in (
        (
            "phase17g-context-setup-stage",
            BattlePhase.FIGHT,
            "end",
            "battle stage",
        ),
        (
            "phase17g-context-command-phase",
            BattlePhase.COMMAND,
            "end",
            "Fight phase",
        ),
        (
            "phase17g-context-missing-state",
            BattlePhase.FIGHT,
            "missing",
            "fight phase state",
        ),
        (
            "phase17g-context-pile-in",
            BattlePhase.FIGHT,
            "pile_in",
            "Fight phase end step",
        ),
        (
            "phase17g-context-complete",
            BattlePhase.FIGHT,
            "complete",
            "incomplete Fight phase",
        ),
    ):
        state = _generic_fight_end_state(game_id)
        _set_current_battle_phase(state, phase)
        if game_id == "phase17g-context-setup-stage":
            state.stage = GameLifecycleStage.SETUP
        policy = RulesetDescriptor.warhammer_40000_eleventh().fight_policy
        if fight_state_kind == "missing":
            state.fight_phase_state = None
        elif fight_state_kind == "pile_in":
            fight_state = state.fight_phase_state
            assert fight_state is not None
            state.fight_phase_state = fight_state.with_current_step(
                current_step=FightPhaseStepKind.PILE_IN,
                policy=policy,
            )
        elif fight_state_kind == "complete":
            fight_state = state.fight_phase_state
            assert fight_state is not None
            state.fight_phase_state = fight_state.with_phase_complete()

        with pytest.raises(GameLifecycleError, match=message):
            FightPhaseEndRequestContext(state=state, decisions=DecisionController())


@pytest.mark.parametrize(
    ("replacement", "field"),
    [
        ({"request_id": "phase17g-other-request"}, "request_id"),
        ({"decision_type": "phase17g_other_decision"}, "decision_type"),
        ({"actor_id": "player-b"}, "actor_id"),
        ({"selected_option_id": "phase17g-missing-option"}, "selected_option_id"),
    ],
)
def test_fight_phase_end_finite_decision_validation_rejects_mismatches(
    replacement: dict[str, str],
    field: str,
) -> None:
    state = _generic_fight_end_state(f"phase17g-fight-end-finite-{field}")
    request = _generic_fight_end_request(state)
    result = replace(
        DecisionResult.for_request(
            result_id=f"phase17g-fight-end-finite-{field}-result",
            request=request,
            selected_option_id=request.options[0].option_id,
        ),
        **replacement,
    )

    status = invalid_fight_phase_end_faction_rule_status(
        state=state,
        request=request,
        result=result,
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, JsonValue], status.payload)["field"] == field


@pytest.mark.parametrize(
    ("payload_overrides", "request_payload_overrides", "expected_reason"),
    [
        ({"game_id": "phase17g-drift-other-game"}, {}, "game_id_drift"),
        ({"battle_round": 99}, {}, "battle_round_drift"),
        ({"phase": BattlePhase.COMMAND.value}, {}, "payload_phase_drift"),
        ({"active_player_id": "player-b"}, {}, "active_player_drift"),
        ({}, {"game_id": "phase17g-request-drift-other-game"}, "request_game_id_drift"),
        ({}, {"battle_round": 99}, "request_battle_round_drift"),
        ({}, {"phase": BattlePhase.COMMAND.value}, "request_phase_drift"),
        ({}, {"active_player_id": "player-b"}, "request_active_player_drift"),
    ],
)
def test_fight_phase_end_drift_validation_rejects_payload_snapshots(
    payload_overrides: dict[str, JsonValue],
    request_payload_overrides: dict[str, JsonValue],
    expected_reason: str,
) -> None:
    state = _generic_fight_end_state(f"phase17g-fight-end-drift-{expected_reason}")
    request = _generic_fight_end_request(
        state,
        payload_overrides=payload_overrides,
        request_payload_overrides=request_payload_overrides,
    )
    result = DecisionResult.for_request(
        result_id=f"phase17g-fight-end-drift-{expected_reason}-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )

    status = invalid_fight_phase_end_faction_rule_status(
        state=state,
        request=request,
        result=result,
    )

    assert status is not None
    assert cast(dict[str, JsonValue], status.payload)["invalid_reason"] == expected_reason


@pytest.mark.parametrize(
    ("phase", "fight_state_kind", "expected_reason"),
    [
        (BattlePhase.COMMAND, "end", "phase_drift"),
        (BattlePhase.FIGHT, "missing", "fight_phase_state_missing"),
        (BattlePhase.FIGHT, "pile_in", "fight_phase_end_window_not_open"),
        (BattlePhase.FIGHT, "complete", "fight_phase_end_window_closed"),
    ],
)
def test_fight_phase_end_drift_validation_rejects_state_window_drift(
    phase: BattlePhase,
    fight_state_kind: str,
    expected_reason: str,
) -> None:
    state = _generic_fight_end_state(f"phase17g-fight-end-state-{expected_reason}")
    _set_current_battle_phase(state, phase)
    policy = RulesetDescriptor.warhammer_40000_eleventh().fight_policy
    if fight_state_kind == "missing":
        state.fight_phase_state = None
    elif fight_state_kind == "pile_in":
        fight_state = state.fight_phase_state
        assert fight_state is not None
        state.fight_phase_state = fight_state.with_current_step(
            current_step=FightPhaseStepKind.PILE_IN,
            policy=policy,
        )
    elif fight_state_kind == "complete":
        fight_state = state.fight_phase_state
        assert fight_state is not None
        state.fight_phase_state = fight_state.with_phase_complete()
    request = _generic_fight_end_request(state, phase=BattlePhase.FIGHT)
    result = DecisionResult.for_request(
        result_id=f"phase17g-fight-end-state-{expected_reason}-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )

    status = invalid_fight_phase_end_faction_rule_status(
        state=state,
        request=request,
        result=result,
    )

    assert status is not None
    assert cast(dict[str, JsonValue], status.payload)["invalid_reason"] == expected_reason


def test_fight_phase_faction_rule_dispatches_start_and_end_decisions() -> None:
    end_state = _generic_fight_end_state("phase17g-fight-dispatch-end")
    end_request = _generic_fight_end_request(end_state)
    end_result = DecisionResult.for_request(
        result_id="phase17g-fight-dispatch-end-result",
        request=end_request,
        selected_option_id=end_request.options[0].option_id,
    )
    assert (
        invalid_fight_phase_faction_rule_status(
            state=end_state,
            request=end_request,
            result=end_result,
        )
        is None
    )

    start_state = battle_state()
    start_state.game_id = "phase17g-fight-dispatch-start"
    start_state.active_player_id = "player-a"
    _set_current_battle_phase(start_state, BattlePhase.FIGHT)
    start_request = _generic_fight_start_request(start_state)
    start_result = DecisionResult.for_request(
        result_id="phase17g-fight-dispatch-start-result",
        request=start_request,
        selected_option_id=start_request.options[0].option_id,
    )
    assert (
        invalid_fight_phase_faction_rule_status(
            state=start_state,
            request=start_request,
            result=start_result,
        )
        is None
    )


def _datasheet_runtime_modifier_registry() -> RuntimeModifierRegistry:
    contribution = datasheets.runtime_contribution()
    return RuntimeModifierRegistry.from_bindings(
        hit_roll_modifier_bindings=contribution.hit_roll_modifier_bindings,
        movement_budget_modifier_bindings=contribution.movement_budget_modifier_bindings,
        objective_control_modifier_bindings=contribution.objective_control_modifier_bindings,
        weapon_profile_modifier_bindings=contribution.weapon_profile_modifier_bindings,
    )


def _datasheet_ability(source_id: str) -> DatasheetAbilityDescriptor:
    ability_id_suffix = source_id.split("Datasheets_abilities:", maxsplit=1)[1].replace(":", "-")
    return DatasheetAbilityDescriptor(
        ability_id=f"phase17g-datasheet:{ability_id_suffix}",
        name="Source Backed Datasheet Ability",
        source_id=source_id,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="source-backed datasheet test ability",
    )


def _melee_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-daemon-melee-profile",
        name="Daemon melee profile",
        range_profile=RangeProfile.melee(),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 5),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -1),
        damage_profile=DamageProfile.fixed(1),
    )


def _ranged_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-daemon-ranged-profile",
        name="Daemon ranged profile",
        range_profile=RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 5),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -1),
        damage_profile=DamageProfile.fixed(1),
    )


def _mark_player_as_chaos_daemons(state: GameState, *, player_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id="chaos-daemons",
                ),
            )
        )
    state.army_definitions = updated_armies


def _replace_unit_keywords_and_abilities(
    state: GameState,
    *,
    unit_instance_id: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
    datasheet_abilities: tuple[DatasheetAbilityDescriptor, ...] | None = None,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    replaced = False
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id != unit_instance_id:
                updated_units.append(unit)
                continue
            replaced = True
            updated_units.append(
                replace(
                    unit,
                    keywords=keywords,
                    faction_keywords=faction_keywords,
                    datasheet_abilities=(
                        unit.datasheet_abilities
                        if datasheet_abilities is None
                        else datasheet_abilities
                    ),
                )
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not replaced:
        raise AssertionError(f"missing unit {unit_instance_id}")
    state.army_definitions = updated_armies


def _place_units_near_center(
    state: GameState,
    *,
    source_unit_id: str,
    target_unit_id: str,
    target_offset: tuple[float, float],
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    marker = center_marker_definition(state)
    source = state.battlefield_state.unit_placement_by_id(source_unit_id)
    target = state.battlefield_state.unit_placement_by_id(target_unit_id)
    battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(source, marker, offsets=((0.0, 0.0),))
    )
    battlefield_state = battlefield_state.with_unit_placement(
        with_model_offsets(target, marker, offsets=(target_offset,))
    )
    state.battlefield_state = battlefield_state


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _set_fight_phase_end_state(
    state: GameState,
    *,
    engaged_unit_ids: tuple[str, ...],
) -> None:
    policy = RulesetDescriptor.warhammer_40000_eleventh().fight_policy
    state.fight_phase_state = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id="player-a",
        policy=policy,
        engaged_at_fight_step_start_unit_ids=engaged_unit_ids,
        fights_first_registry=FightsFirstRegistry(),
    ).with_current_step(current_step=FightPhaseStepKind.END, policy=policy)


def _decision_request(value: DecisionRequest | None) -> DecisionRequest:
    if value is None:
        raise AssertionError("expected decision request")
    return value


def _event_payload(decisions: DecisionController, event_type: str) -> dict[str, JsonValue]:
    for event in decisions.event_log.records:
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")


def _relentless_carnage_record_payload(
    *,
    battle_round: int,
    source_unit_instance_id: str,
) -> dict[str, JsonValue]:
    return {
        "source_rule_id": datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID,
        "phase": BattlePhase.FIGHT.value,
        "battle_round": battle_round,
        "active_player_id": "player-a",
        "source_unit_instance_id": source_unit_instance_id,
    }


def _generic_fight_end_state(game_id: str) -> GameState:
    state = battle_state()
    state.game_id = game_id
    state.active_player_id = "player-a"
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    _set_fight_phase_end_state(state, engaged_unit_ids=("army-alpha:intercessor-unit-1",))
    return state


def _relentless_carnage_state(
    *,
    game_id: str,
    target_offset: tuple[float, float] = (0.5, 0.0),
) -> GameState:
    state = battle_state_with_center_objective_positions(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=(target_offset,),
    )
    state.game_id = game_id
    state.active_player_id = "player-a"
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-beta:intercessor-unit-3"
    _mark_player_as_chaos_daemons(state, player_id="player-a")
    _replace_unit_keywords_and_abilities(
        state,
        unit_instance_id=source_unit_id,
        keywords=("Character", "Monster", "Khorne"),
        faction_keywords=("Legiones Daemonica",),
        datasheet_abilities=(
            _datasheet_ability(datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_SOURCE_ID),
        ),
    )
    _set_fight_phase_end_state(state, engaged_unit_ids=(source_unit_id, target_unit_id))
    return state


def _relentless_carnage_request(
    *,
    state: GameState,
    decisions: DecisionController,
) -> DecisionRequest:
    request = datasheets.relentless_carnage_fight_phase_end_request(
        FightPhaseEndRequestContext(state=state, decisions=decisions)
    )
    return _decision_request(request)


def _generic_fight_end_request(
    state: GameState,
    *,
    phase: BattlePhase = BattlePhase.FIGHT,
    payload_overrides: dict[str, JsonValue] | None = None,
    request_payload_overrides: dict[str, JsonValue] | None = None,
) -> DecisionRequest:
    base_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": "player-a",
        "phase": phase.value,
        "submission_kind": "phase17g_generic_fight_end",
    }
    option_payload = {**base_payload, **({} if payload_overrides is None else payload_overrides)}
    request_payload = {
        **base_payload,
        **({} if request_payload_overrides is None else request_payload_overrides),
    }
    return DecisionRequest(
        request_id=f"{state.game_id}:fight-end-request",
        decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_END_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload=request_payload,
        options=(
            DecisionOption(
                option_id=f"{state.game_id}:fight-end-option",
                label="phase17g_generic_fight_end",
                payload=option_payload,
            ),
        ),
    )


def _generic_fight_start_request(state: GameState) -> DecisionRequest:
    payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": "player-a",
        "phase": BattlePhase.FIGHT.value,
        "submission_kind": "phase17g_generic_fight_start",
    }
    return DecisionRequest(
        request_id=f"{state.game_id}:fight-start-request",
        decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
        actor_id="player-a",
        payload=payload,
        options=(
            DecisionOption(
                option_id=f"{state.game_id}:fight-start-option",
                label="phase17g_generic_fight_start",
                payload=payload,
            ),
        ),
    )
