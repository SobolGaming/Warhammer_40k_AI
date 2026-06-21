from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.unit.test_phase11c_command_phase import (
    _battle_state,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
from warhammer40k_core.core.faction_aliases import (
    CHAOS_DAEMONS_FACTION_ID,
    CHAOS_SPACE_MARINES_FACTION_ID,
    faction_alias_for_id,
    faction_reference_matches,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    FightEligibilityKind,
    FightOrderingBandKind,
    FightTypeKind,
)
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHandler,
    AttackSequenceCompletedHookBinding,
    AttackSequenceCompletedHookRegistry,
    attack_sequence_completed_event_id,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule,
)
from warhammer40k_core.engine.fight_order import FightActivationSelection
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.shooting import (
    ShootingPhaseState,
    ShootingUnitSelection,
    _apply_shooting_unit_selected_grant_decision,  # pyright: ignore[reportPrivateUsage]
    _request_shooting_unit_selected_grant_decision_if_available,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


def test_faction_aliases_include_common_faction_keyword_references() -> None:
    chaos_space_marines = faction_alias_for_id(CHAOS_SPACE_MARINES_FACTION_ID)

    assert chaos_space_marines is not None
    assert chaos_space_marines.name == "Chaos Space Marines"
    assert "Heretic Astartes" in chaos_space_marines.reference_tokens()
    assert faction_reference_matches(
        faction_id=CHAOS_SPACE_MARINES_FACTION_ID,
        reference="HERETIC ASTARTES",
    )
    assert faction_reference_matches(
        faction_id=CHAOS_DAEMONS_FACTION_ID,
        reference="Legiones Daemonica",
    )


def test_attack_sequence_completed_hook_registry_is_ordered_and_fail_fast() -> None:
    state = _csm_battle_state()
    decisions = DecisionController()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    attack_sequence = AttackSequence(
        sequence_id="dark-pact-registry-sequence",
        source_phase=BattlePhase.SHOOTING,
        attacker_player_id="player-a",
        attacking_unit_instance_id=unit.unit_instance_id,
        attack_pools=(
            _attack_pool(
                attacker=unit,
                target=target,
                weapon_profile=_weapon_profile(melee=False),
            ),
        ),
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": "player-a",
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )
    expected_status = LifecycleStatus.advanced(stage=GameLifecycleStage.BATTLE)
    seen_hooks: list[str] = []

    def no_status_handler(hook_context: AttackSequenceCompletedContext) -> None:
        assert hook_context is context
        seen_hooks.append("a")

    def status_handler(hook_context: AttackSequenceCompletedContext) -> LifecycleStatus:
        assert hook_context is context
        seen_hooks.append("b")
        return expected_status

    registry = AttackSequenceCompletedHookRegistry.from_bindings(
        (
            AttackSequenceCompletedHookBinding(
                hook_id="b-status",
                source_id="test-source",
                handler=status_handler,
            ),
            AttackSequenceCompletedHookBinding(
                hook_id="a-none",
                source_id="test-source",
                handler=no_status_handler,
            ),
        )
    )

    assert tuple(binding.hook_id for binding in registry.all_bindings()) == (
        "a-none",
        "b-status",
    )
    assert (
        attack_sequence_completed_event_id(
            decisions=decisions,
            attack_sequence=attack_sequence,
        )
        == completed_event.event_id
    )
    assert registry.resolve_completed_sequence(context) is expected_status
    assert seen_hooks == ["a", "b"]
    assert AttackSequenceCompletedHookRegistry.empty().all_bindings() == ()

    duplicate_binding = AttackSequenceCompletedHookBinding(
        hook_id="duplicate",
        source_id="test-source",
        handler=no_status_handler,
    )
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        AttackSequenceCompletedHookRegistry.from_bindings((duplicate_binding, duplicate_binding))
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        AttackSequenceCompletedHookRegistry.from_bindings(
            cast(tuple[AttackSequenceCompletedHookBinding, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="handler is not callable"):
        AttackSequenceCompletedHookBinding(
            hook_id="bad-handler",
            source_id="test-source",
            handler=cast(AttackSequenceCompletedHandler, None),
        )
    with pytest.raises(GameLifecycleError, match="must return status or None"):
        AttackSequenceCompletedHookRegistry.from_bindings(
            (
                AttackSequenceCompletedHookBinding(
                    hook_id="bad-status",
                    source_id="test-source",
                    handler=lambda _context: cast(LifecycleStatus, "bad-status"),
                ),
            )
        ).resolve_completed_sequence(context)
    with pytest.raises(GameLifecycleError, match="Completed attack sequence event is missing"):
        attack_sequence_completed_event_id(
            decisions=DecisionController(),
            attack_sequence=attack_sequence,
        )


def test_dark_pacts_runtime_contribution_registers_engine_hooks() -> None:
    contribution = army_rule.runtime_contribution()

    assert {
        binding.hook_id for binding in contribution.shooting_unit_selected_grant_hook_bindings
    } == {
        army_rule.SHOOTING_LETHAL_HITS_HOOK_ID,
        army_rule.SHOOTING_SUSTAINED_HITS_HOOK_ID,
    }
    assert {
        binding.hook_id for binding in contribution.fight_unit_selected_grant_hook_bindings
    } == {
        army_rule.FIGHT_LETHAL_HITS_HOOK_ID,
        army_rule.FIGHT_SUSTAINED_HITS_HOOK_ID,
    }
    assert (
        contribution.attack_sequence_completed_hook_bindings[0].hook_id
        == army_rule.ATTACK_SEQUENCE_COMPLETED_HOOK_ID
    )
    assert (
        contribution.weapon_profile_modifier_bindings[0].modifier_id
        == army_rule.WEAPON_PROFILE_MODIFIER_ID
    )


def test_dark_pacts_shooting_decision_records_effect_and_grants_lethal_hits() -> None:
    state = _csm_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    selection = _shooting_selection(state, unit)
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    ).with_unit_selection(selection)
    decisions = DecisionController()
    registry = ShootingUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().shooting_unit_selected_grant_hook_bindings
    )

    status = _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=registry,
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = _decision_request(status.decision_request)
    assert request.decision_type == "select_shooting_unit_grant"
    assert {option.option_id for option in request.options} == {
        "decline_shooting_unit_grant",
        army_rule.SHOOTING_LETHAL_HITS_HOOK_ID,
        army_rule.SHOOTING_SUSTAINED_HITS_HOOK_ID,
    }
    lethal_option = _option_payload(request, army_rule.SHOOTING_LETHAL_HITS_HOOK_ID)
    selected_grants = cast(
        list[dict[str, JsonValue]],
        lethal_option["selected_shooting_unit_grants"],
    )
    effect_payload = cast(dict[str, JsonValue], selected_grants[0]["unit_effect_payload"])
    assert effect_payload["selected_dark_pact"] == army_rule.DarkPactKind.LETHAL_HITS.value
    assert effect_payload["phase"] == BattlePhase.SHOOTING.value

    result = DecisionResult.for_request(
        result_id="dark-pact-shooting-result",
        request=request,
        selected_option_id=army_rule.SHOOTING_LETHAL_HITS_HOOK_ID,
    )
    decisions.submit_result(result)
    _apply_shooting_unit_selected_grant_decision(
        state=state,
        result=result,
        decisions=decisions,
        registry=registry,
    )

    assert (
        army_rule.active_dark_pact_for_unit(
            state,
            unit_instance_id=unit.unit_instance_id,
            phase=BattlePhase.SHOOTING,
        )
        is army_rule.DarkPactKind.LETHAL_HITS
    )
    modified = army_rule.dark_pact_weapon_profile_modifier(
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


def test_dark_pacts_fight_grant_and_melee_profile_add_sustained_hits() -> None:
    state = _csm_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    registry = FightUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().fight_unit_selected_grant_hook_bindings
    )
    activation = _fight_activation(state, unit)
    grants = registry.grants_for(
        FightUnitSelectedContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            fight_type=activation.fight_type.value,
            ordering_band=activation.ordering_band.value,
            request_id=activation.request_id,
            result_id=activation.result_id,
        )
    )

    assert {grant.hook_id for grant in grants} == {
        army_rule.FIGHT_LETHAL_HITS_HOOK_ID,
        army_rule.FIGHT_SUSTAINED_HITS_HOOK_ID,
    }
    _record_dark_pact_effect(
        state,
        unit=unit,
        phase=BattlePhase.FIGHT,
        pact=army_rule.DarkPactKind.SUSTAINED_HITS_1,
    )
    modified = army_rule.dark_pact_weapon_profile_modifier(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=unit.own_models[0].model_instance_id,
            target_unit_instance_id=target.unit_instance_id,
            weapon_profile=_weapon_profile(melee=True),
        )
    )

    assert WeaponKeyword.SUSTAINED_HITS in modified.keywords
    assert any(ability.ability_id == "sustained-hits:1" for ability in modified.abilities)


def test_dark_pacts_failed_leadership_test_applies_d3_mortal_wounds() -> None:
    state = _csm_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _record_dark_pact_effect(
        state,
        unit=unit,
        phase=BattlePhase.SHOOTING,
        pact=army_rule.DarkPactKind.LETHAL_HITS,
    )
    decisions = DecisionController()
    attack_sequence = AttackSequence(
        sequence_id="dark-pact-sequence",
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
                roll_id="dark-pact-leadership-roll",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=2, sides=6),
                    reason=f"Dark Pact Leadership test for {unit.unit_instance_id}",
                    roll_type=army_rule.DARK_PACT_LEADERSHIP_ROLL_TYPE,
                    actor_id=unit.unit_instance_id,
                ),
                values=(1, 1),
                source="fixed",
            ),
            DiceRollResult.from_values(
                roll_id="dark-pact-mortal-wounds-roll",
                spec=DiceRollManager.d3_source_spec(
                    reason=f"Dark Pact mortal wounds for {unit.unit_instance_id}",
                    roll_type=army_rule.DARK_PACT_MORTAL_WOUNDS_ROLL_TYPE,
                    actor_id=unit.unit_instance_id,
                ),
                values=(5,),
                source="fixed",
            ),
        ),
    )
    starting_wounds = sum(model.wounds_remaining for model in unit.own_models)

    army_rule.resolve_dark_pact_attack_sequence_completion(
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

    payload = _last_event_payload(decisions, "chaos_space_marines_dark_pact_resolved")
    assert payload["passed"] is False
    assert cast(dict[str, JsonValue], payload["d3_result"])["value"] == 3
    application = cast(dict[str, JsonValue], payload["mortal_wound_application"])
    assert application["mortal_wounds"] == 3
    refreshed_unit = _unit_for_player(state, player_id="player-a")
    ending_wounds = sum(model.wounds_remaining for model in refreshed_unit.own_models)
    assert starting_wounds - ending_wounds == 3


def _csm_battle_state() -> GameState:
    state = _battle_state()
    _mark_player_as_chaos_space_marines(state, player_id="player-a")
    return state


def _mark_player_as_chaos_space_marines(state: GameState, *, player_id: str) -> None:
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
                    faction_id=CHAOS_SPACE_MARINES_FACTION_ID,
                ),
                units=tuple(
                    replace(unit, faction_keywords=("Heretic Astartes",)) for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies


def _unit_for_player(state: GameState, *, player_id: str) -> UnitInstance:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise AssertionError(f"Missing army for {player_id}.")
    return army.units[0]


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _shooting_selection(state: GameState, unit: UnitInstance) -> ShootingUnitSelection:
    return ShootingUnitSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        request_id="select-shooting-unit-request",
        result_id="select-shooting-unit-result",
    )


def _fight_activation(state: GameState, unit: UnitInstance) -> FightActivationSelection:
    return FightActivationSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        ordering_band=FightOrderingBandKind.REMAINING_COMBATS,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(FightEligibilityKind.CURRENTLY_ENGAGED,),
        request_id="fight-activation-request",
        result_id="fight-activation-result",
    )


def _record_dark_pact_effect(
    state: GameState,
    *,
    unit: UnitInstance,
    phase: BattlePhase,
    pact: army_rule.DarkPactKind,
) -> None:
    phase_kind = (
        BattlePhaseKind.SHOOTING if phase is BattlePhase.SHOOTING else BattlePhaseKind.FIGHT
    )
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"test-dark-pact:{phase.value}:{pact.value}:{unit.unit_instance_id}",
            source_rule_id=army_rule.SOURCE_RULE_ID,
            owner_player_id="player-a",
            target_unit_instance_ids=army_rule.dark_pact_target_unit_ids(
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
            effect_payload=army_rule.dark_pact_effect_payload(
                unit_instance_id=unit.unit_instance_id,
                target_unit_instance_ids=army_rule.dark_pact_target_unit_ids(
                    state,
                    unit_instance_id=unit.unit_instance_id,
                ),
                trigger="test",
                phase=phase,
                selected_dark_pact=pact,
                source_context={"test": True},
            ),
        )
    )


def _weapon_profile(*, melee: bool) -> WeaponProfile:
    return WeaponProfile(
        profile_id="test-melee-profile" if melee else "test-ranged-profile",
        name="Test melee weapon" if melee else "Test ranged weapon",
        range_profile=RangeProfile.melee() if melee else RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(
            Characteristic.WEAPON_SKILL if melee else Characteristic.BALLISTIC_SKILL,
            3,
        ),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("test-profile",),
    )


def _attack_pool(
    *,
    attacker: UnitInstance,
    target: UnitInstance,
    weapon_profile: WeaponProfile,
) -> RangedAttackPool:
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id="test-wargear",
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=target.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=(target.own_models[0].model_instance_id,),
        target_in_range_model_ids=(target.own_models[0].model_instance_id,),
    )


def _option_payload(request: DecisionRequest, option_id: str) -> dict[str, JsonValue]:
    for option in request.options:
        if option.option_id == option_id:
            return cast(dict[str, JsonValue], option.payload)
    raise AssertionError(f"Missing option {option_id}.")


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
