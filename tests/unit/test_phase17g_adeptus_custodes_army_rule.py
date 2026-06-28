from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.unit.test_phase11c_command_phase import (
    _battle_state,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.faction_aliases import (
    ADEPTUS_CUSTODES_FACTION_ID,
    faction_reference_matches,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    FightEligibilityKind,
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
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adeptus_custodes import (
    army_rule,
)
from warhammer40k_core.engine.fight_order import (
    FightActivationSelection,
    FightPhaseState,
    FightsFirstRegistry,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    DECLINE_FIGHT_UNIT_GRANT_OPTION_ID,
    SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE,
    FightUnitSelectedContext,
    FightUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.phases.fight import (
    _apply_fight_unit_selected_grant_decision,  # pyright: ignore[reportPrivateUsage]
    _request_fight_unit_selected_grant_decision_if_available,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext
from warhammer40k_core.engine.unit_factory import UnitInstance


def test_adeptus_custodes_faction_alias_matches_army_keyword() -> None:
    assert faction_reference_matches(
        faction_id=ADEPTUS_CUSTODES_FACTION_ID,
        reference="ADEPTUS CUSTODES",
    )


def test_martial_katah_runtime_contribution_registers_hooks() -> None:
    contribution = army_rule.runtime_contribution()

    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert {
        binding.hook_id for binding in contribution.fight_unit_selected_grant_hook_bindings
    } == {
        army_rule.DACATARAI_HOOK_ID,
        army_rule.RENDAX_HOOK_ID,
    }
    assert (
        contribution.weapon_profile_modifier_bindings[0].modifier_id
        == army_rule.WEAPON_PROFILE_MODIFIER_ID
    )
    assert contribution.weapon_profile_modifier_bindings[0].source_id == army_rule.SOURCE_RULE_ID


def test_martial_katah_selected_to_fight_request_exposes_stance_options() -> None:
    state = _custodes_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()
    registry = FightUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().fight_unit_selected_grant_hook_bindings
    )
    activation = _fight_activation(state, unit)

    status = _request_fight_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        activation=activation,
        registry=registry,
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = _decision_request(status.decision_request)
    assert request.decision_type == SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE
    assert {option.option_id for option in request.options} == {
        DECLINE_FIGHT_UNIT_GRANT_OPTION_ID,
        army_rule.DACATARAI_HOOK_ID,
        army_rule.RENDAX_HOOK_ID,
    }
    dacatarai_payload = _option_payload(request, army_rule.DACATARAI_HOOK_ID)
    selected_grants = cast(
        list[dict[str, JsonValue]],
        dacatarai_payload["selected_fight_unit_grants"],
    )
    effect_payload = cast(dict[str, JsonValue], selected_grants[0]["unit_effect_payload"])
    assert effect_payload["effect_kind"] == army_rule.MARTIAL_KATAH_EFFECT_KIND
    assert effect_payload["selected_martial_katah"] == army_rule.MartialKatahStance.DACATARAI.value
    assert effect_payload["phase"] == BattlePhase.FIGHT.value
    assert effect_payload["target_unit_instance_ids"] == [unit.unit_instance_id]


def test_martial_katah_dacatarai_decision_records_effect_and_grants_sustained_hits() -> None:
    state = _custodes_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()
    registry = FightUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().fight_unit_selected_grant_hook_bindings
    )
    activation = _fight_activation(state, unit)
    state.fight_phase_state = (
        _fight_phase_state(state=state, unit=unit)
        .with_activation(activation)
        .with_active_activation(activation)
    )
    status = _request_fight_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        activation=activation,
        registry=registry,
    )
    if status is None:
        raise AssertionError("Expected Martial Ka'tah grant decision.")
    request = _decision_request(status.decision_request)

    result = DecisionResult.for_request(
        result_id="martial-katah-dacatarai-result",
        request=request,
        selected_option_id=army_rule.DACATARAI_HOOK_ID,
    )
    decisions.submit_result(result)
    _apply_fight_unit_selected_grant_decision(
        state=state,
        result=result,
        decisions=decisions,
        registry=registry,
    )

    assert (
        army_rule.active_martial_katah_for_unit(
            state,
            unit_instance_id=unit.unit_instance_id,
        )
        is army_rule.MartialKatahStance.DACATARAI
    )
    modified = army_rule.martial_katah_weapon_profile_modifier(
        _modifier_context(state=state, unit=unit, target=target, melee=True)
    )
    assert WeaponKeyword.SUSTAINED_HITS in modified.keywords
    assert WeaponKeyword.LETHAL_HITS not in modified.keywords
    assert any(ability.ability_id == "sustained-hits:1" for ability in modified.abilities)

    ranged = army_rule.martial_katah_weapon_profile_modifier(
        _modifier_context(state=state, unit=unit, target=target, melee=False)
    )
    assert ranged.keywords == ()
    assert ranged.abilities == ()


def test_martial_katah_rendax_grants_lethal_hits_to_melee_profiles() -> None:
    state = _custodes_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    _record_martial_katah_effect(
        state,
        unit=unit,
        stance=army_rule.MartialKatahStance.RENDAX,
    )

    modified = army_rule.martial_katah_weapon_profile_modifier(
        _modifier_context(state=state, unit=unit, target=target, melee=True)
    )

    assert WeaponKeyword.LETHAL_HITS in modified.keywords
    assert WeaponKeyword.SUSTAINED_HITS not in modified.keywords
    assert any(ability.ability_id == "lethal-hits" for ability in modified.abilities)
    assert army_rule.SOURCE_RULE_ID in modified.source_ids


def test_martial_katah_is_not_available_for_non_custodes_armies() -> None:
    state = _battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    registry = FightUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().fight_unit_selected_grant_hook_bindings
    )
    grants = registry.grants_for(
        FightUnitSelectedContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            fight_type=FightTypeKind.NORMAL.value,
            ordering_band=FightOrderingBandKind.REMAINING_COMBATS.value,
            request_id="martial-katah-test-request",
            result_id="martial-katah-test-result",
        )
    )

    assert grants == ()


def test_martial_katah_ability_name_allows_rule_without_faction_keyword() -> None:
    state = _battle_state()
    _mark_player_as_adeptus_custodes(
        state,
        player_id="player-a",
        faction_keywords=("IMPERIUM",),
    )
    unit = _unit_for_player(state, player_id="player-a")
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    registry = FightUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().fight_unit_selected_grant_hook_bindings
    )
    grants = registry.grants_for(
        FightUnitSelectedContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            fight_type=FightTypeKind.NORMAL.value,
            ordering_band=FightOrderingBandKind.REMAINING_COMBATS.value,
            request_id="martial-katah-ability-name-request",
            result_id="martial-katah-ability-name-result",
        )
    )

    assert {grant.hook_id for grant in grants} == {
        army_rule.DACATARAI_HOOK_ID,
        army_rule.RENDAX_HOOK_ID,
    }


def test_martial_katah_modifier_ignores_wrong_phase_and_missing_effect() -> None:
    state = _custodes_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    base = _weapon_profile(melee=True)

    wrong_phase = army_rule.martial_katah_weapon_profile_modifier(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=unit.own_models[0].model_instance_id,
            target_unit_instance_id=target.unit_instance_id,
            weapon_profile=base,
        )
    )
    missing_effect = army_rule.martial_katah_weapon_profile_modifier(
        _modifier_context(state=state, unit=unit, target=target, melee=True)
    )

    assert wrong_phase == base
    assert missing_effect == base
    assert (
        army_rule.active_martial_katah_for_unit(state, unit_instance_id=unit.unit_instance_id)
        is None
    )


def test_martial_katah_payload_and_handlers_are_fail_fast() -> None:
    state = _custodes_battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    _set_current_battle_phase(state, BattlePhase.FIGHT)

    with pytest.raises(GameLifecycleError, match="requires selected unit context"):
        army_rule.dacatarai_martial_katah_grant(cast(FightUnitSelectedContext, object()))
    with pytest.raises(GameLifecycleError, match="requires context"):
        army_rule.martial_katah_weapon_profile_modifier(
            cast(WeaponProfileModifierContext, object())
        )
    with pytest.raises(GameLifecycleError, match="must not contain duplicates"):
        army_rule.martial_katah_effect_payload(
            unit_instance_id=unit.unit_instance_id,
            target_unit_instance_ids=(unit.unit_instance_id, unit.unit_instance_id),
            trigger="test",
            phase=BattlePhase.FIGHT,
            selected_martial_katah=army_rule.MartialKatahStance.DACATARAI,
            source_context={"test": True},
        )
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        army_rule.martial_katah_effect_payload(
            unit_instance_id=unit.unit_instance_id,
            target_unit_instance_ids=(),
            trigger="test",
            phase=BattlePhase.FIGHT,
            selected_martial_katah=army_rule.MartialKatahStance.DACATARAI,
            source_context={"test": True},
        )
    with pytest.raises(GameLifecycleError, match="target lookup requires GameState"):
        army_rule.martial_katah_target_unit_ids(
            object(),
            unit_instance_id=unit.unit_instance_id,
        )

    with pytest.raises(GameLifecycleError, match="must be an object"):
        army_rule._martial_katah_payload(None)  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="effect kind drift"):
        army_rule._martial_katah_payload(  # pyright: ignore[reportPrivateUsage]
            _payload(
                effect_kind="wrong",
                unit_instance_id=unit.unit_instance_id,
                target_unit_instance_ids=[unit.unit_instance_id],
                trigger="test",
                phase=BattlePhase.FIGHT.value,
                selected_martial_katah=army_rule.MartialKatahStance.DACATARAI.value,
                source_context={"test": True},
            )
        )
    with pytest.raises(GameLifecycleError, match="target_unit_instance_ids must be a list"):
        army_rule._martial_katah_payload(  # pyright: ignore[reportPrivateUsage]
            _payload(
                effect_kind=army_rule.MARTIAL_KATAH_EFFECT_KIND,
                unit_instance_id=unit.unit_instance_id,
                target_unit_instance_ids=unit.unit_instance_id,
                trigger="test",
                phase=BattlePhase.FIGHT.value,
                selected_martial_katah=army_rule.MartialKatahStance.DACATARAI.value,
                source_context={"test": True},
            )
        )
    with pytest.raises(GameLifecycleError, match="missing source_context"):
        army_rule._martial_katah_payload(  # pyright: ignore[reportPrivateUsage]
            _payload(
                effect_kind=army_rule.MARTIAL_KATAH_EFFECT_KIND,
                unit_instance_id=unit.unit_instance_id,
                target_unit_instance_ids=[unit.unit_instance_id],
                trigger="test",
                phase=BattlePhase.FIGHT.value,
                selected_martial_katah=army_rule.MartialKatahStance.DACATARAI.value,
            )
        )
    with pytest.raises(GameLifecycleError, match="Unsupported Martial Ka'tah stance"):
        army_rule._stance_from_token("unsupported")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="stance must be a string"):
        army_rule._stance_from_token(1)  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="Unsupported Martial Ka'tah phase"):
        army_rule._battle_phase_from_token("unsupported")  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(GameLifecycleError, match="phase must be a BattlePhase"):
        army_rule._battle_phase_from_token(1)  # pyright: ignore[reportPrivateUsage]

    _record_martial_katah_effect(
        state,
        unit=unit,
        stance=army_rule.MartialKatahStance.DACATARAI,
        effect_id="martial-katah-test:duplicate-a",
    )
    _record_martial_katah_effect(
        state,
        unit=unit,
        stance=army_rule.MartialKatahStance.RENDAX,
        effect_id="martial-katah-test:duplicate-b",
    )
    with pytest.raises(GameLifecycleError, match="multiple active effects"):
        army_rule.active_martial_katah_for_unit(state, unit_instance_id=unit.unit_instance_id)


def _custodes_battle_state() -> GameState:
    state = _battle_state()
    _mark_player_as_adeptus_custodes(state, player_id="player-a")
    return state


def _mark_player_as_adeptus_custodes(
    state: GameState,
    *,
    player_id: str,
    datasheet_abilities: tuple[DatasheetAbilityDescriptor, ...] | None = None,
    faction_keywords: tuple[str, ...] = ("ADEPTUS CUSTODES",),
) -> None:
    resolved_abilities = (
        (_martial_katah_ability(),) if datasheet_abilities is None else datasheet_abilities
    )
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
                    faction_id=ADEPTUS_CUSTODES_FACTION_ID,
                ),
                units=tuple(
                    replace(
                        unit,
                        faction_keywords=faction_keywords,
                        datasheet_abilities=resolved_abilities,
                    )
                    for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies


def _martial_katah_ability() -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id="adeptus-custodes-test-martial-katah",
        name="Martial Ka'tah",
        source_id="adeptus-custodes-test:martial-katah",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Select Dacatarai or Rendax when this unit is selected to fight.",
    )


def _unit_for_player(state: GameState, *, player_id: str) -> UnitInstance:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise AssertionError(f"Missing army for {player_id}.")
    return army.units[0]


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _fight_activation(state: GameState, unit: UnitInstance) -> FightActivationSelection:
    return FightActivationSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        ordering_band=FightOrderingBandKind.REMAINING_COMBATS,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(FightEligibilityKind.CURRENTLY_ENGAGED,),
        request_id="martial-katah-fight-activation-request",
        result_id="martial-katah-fight-activation-result",
    )


def _record_martial_katah_effect(
    state: GameState,
    *,
    unit: UnitInstance,
    stance: army_rule.MartialKatahStance,
    effect_id: str | None = None,
) -> None:
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=(
                f"martial-katah-test:{stance.value}:{unit.unit_instance_id}"
                if effect_id is None
                else effect_id
            ),
            source_rule_id=army_rule.SOURCE_RULE_ID,
            owner_player_id="player-a",
            target_unit_instance_ids=army_rule.martial_katah_target_unit_ids(
                state,
                unit_instance_id=unit.unit_instance_id,
            ),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.FIGHT,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=BattlePhaseKind.FIGHT,
                player_id="player-a",
            ),
            effect_payload=army_rule.martial_katah_effect_payload(
                unit_instance_id=unit.unit_instance_id,
                target_unit_instance_ids=army_rule.martial_katah_target_unit_ids(
                    state,
                    unit_instance_id=unit.unit_instance_id,
                ),
                trigger="test",
                phase=BattlePhase.FIGHT,
                selected_martial_katah=stance,
                source_context={"test": True},
            ),
        )
    )


def _modifier_context(
    *,
    state: GameState,
    unit: UnitInstance,
    target: UnitInstance,
    melee: bool,
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        target_unit_instance_id=target.unit_instance_id,
        weapon_profile=_weapon_profile(melee=melee),
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


def _option_payload(request: DecisionRequest, option_id: str) -> dict[str, JsonValue]:
    for option in request.options:
        if option.option_id == option_id:
            return cast(dict[str, JsonValue], option.payload)
    raise AssertionError(f"Missing option {option_id}.")


def _decision_request(request: DecisionRequest | None) -> DecisionRequest:
    if request is None:
        raise AssertionError("Expected decision request.")
    return request


def _payload(**values: object) -> JsonValue:
    return cast(JsonValue, values)


def _fight_phase_state(*, state: GameState, unit: UnitInstance) -> FightPhaseState:
    return FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id="player-a",
        policy=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="phase17g-adeptus-custodes-test"
        ).fight_policy,
        engaged_at_fight_step_start_unit_ids=(unit.unit_instance_id,),
        fights_first_registry=FightsFirstRegistry(),
    )
