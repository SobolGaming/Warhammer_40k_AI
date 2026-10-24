from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest

from tests.phase11c_command_phase_helpers import (
    battle_state,
)
from tests.phase15c_fight_order_helpers import (
    decision_request,
    drain_fight_movement_requests,
    fight_config,
    fight_lifecycle,
)
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetKeywordSet,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
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
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    EffectExpirationBoundary,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adeptus_custodes import (
    army_rule,
)
from warhammer40k_core.engine.fight_order import (
    FIGHT_ACTIVATION_DECISION_TYPE,
    FightActivationSelection,
    FightPhaseState,
    FightsFirstRegistry,
    fight_activation_option_id,
)
from warhammer40k_core.engine.fight_resolution import SUBMIT_MELEE_DECLARATION_DECISION_TYPE
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    DECLINE_FIGHT_UNIT_GRANT_OPTION_ID,
    SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE,
    FightUnitSelectedContext,
    FightUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.phases.fight import (
    _apply_fight_unit_selected_grant_decision,  # pyright: ignore[reportPrivateUsage]
    _request_fight_unit_selected_grant_decision_if_available,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.pose import Pose


def test_adeptus_custodes_faction_alias_matches_army_keyword() -> None:
    assert faction_reference_matches(
        faction_id=ADEPTUS_CUSTODES_FACTION_ID,
        reference="ADEPTUS CUSTODES",
    )


def test_martial_katah_runtime_contribution_registers_hooks() -> None:
    contribution = army_rule.runtime_contribution()

    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert army_rule.CONTRIBUTION_ID == army_rule.HOOK_ID
    assert not contribution.contribution_id.endswith(":scaffold")
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
    timed_effects = cast(list[dict[str, JsonValue]], selected_grants[0]["timed_effects"])
    effect_payload = cast(dict[str, JsonValue], timed_effects[0]["effect_payload"])
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


def test_martial_katah_effect_applies_to_attached_rules_unit_components() -> None:
    state = _custodes_battle_state()
    attached_id, bodyguard, leader = _attach_custodes_rules_unit(state)
    target = _unit_for_player(state, player_id="player-b")
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    _record_martial_katah_effect(
        state,
        unit=bodyguard,
        stance=army_rule.MartialKatahStance.DACATARAI,
    )

    assert army_rule.martial_katah_target_unit_ids(
        state,
        unit_instance_id=leader.unit_instance_id,
    ) == (
        attached_id,
        bodyguard.unit_instance_id,
        leader.unit_instance_id,
    )
    assert (
        army_rule.active_martial_katah_for_unit(
            state,
            unit_instance_id=leader.unit_instance_id,
        )
        is army_rule.MartialKatahStance.DACATARAI
    )

    modified = army_rule.martial_katah_weapon_profile_modifier(
        _modifier_context(state=state, unit=leader, target=target, melee=True)
    )

    assert WeaponKeyword.SUSTAINED_HITS in modified.keywords
    assert any(ability.ability_id == "sustained-hits:1" for ability in modified.abilities)


def test_martial_katah_is_not_available_for_non_custodes_armies() -> None:
    state = battle_state()
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


def test_martial_katah_source_id_allows_rule_without_faction_keyword() -> None:
    state = battle_state()
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
            request_id="martial-katah-source-id-request",
            result_id="martial-katah-source-id-result",
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
    state = battle_state()
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
                    with_unit_keywords(
                        replace(
                            unit,
                            datasheet_abilities=resolved_abilities,
                        ),
                        faction_keywords=faction_keywords,
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
        source_id=army_rule.SOURCE_RULE_ID,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Select Dacatarai or Rendax when this unit is selected to fight.",
    )


def _unit_for_player(state: GameState, *, player_id: str) -> UnitInstance:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise AssertionError(f"Missing army for {player_id}.")
    return army.units[0]


def _attach_custodes_rules_unit(state: GameState) -> tuple[str, UnitInstance, UnitInstance]:
    bodyguard = _unit_for_player(state, player_id="player-a")
    leader = _cloned_unit_instance(
        bodyguard,
        unit_instance_id="army-alpha:martial-katah-leader",
        model_id_prefix="army-alpha:martial-katah-leader",
    )
    attached_id = "attached-unit:army-alpha:martial-katah"
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
        ),
        source_id="martial-katah-test:attached-unit",
        attachment_source_ids=("martial-katah-test:attachment-eligibility",),
    )
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != "player-a":
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                units=tuple(sorted((*army.units, leader), key=lambda unit: unit.unit_instance_id)),
                attached_units=(*army.attached_units, formation),
            )
        )
    state.army_definitions = updated_armies
    attached_starting_model_count = len(bodyguard.own_models) + len(leader.own_models)
    state.starting_strength_records.append(
        StartingStrengthRecord(
            player_id="player-a",
            unit_instance_id=attached_id,
            starting_model_count=attached_starting_model_count,
            single_model_starting_wounds=None,
            source_id="martial-katah-test:attached-unit:starting-strength",
        )
    )
    state.starting_strength_records.sort(key=lambda record: record.unit_instance_id)
    return attached_id, bodyguard, leader


def _cloned_unit_instance(
    unit: UnitInstance,
    *,
    unit_instance_id: str,
    model_id_prefix: str,
) -> UnitInstance:
    return replace(
        unit,
        unit_instance_id=unit_instance_id,
        own_models=tuple(
            replace(
                model,
                model_instance_id=f"{model_id_prefix}:{index:03}",
            )
            for index, model in enumerate(unit.own_models, start=1)
        ),
    )


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


@pytest.fixture(scope="session")
def shared_custodes_fight_config() -> Iterator[GameConfig]:
    """Share definitions; native checkpoints receive independent mutable graphs."""
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base = catalog.datasheet_by_id("core-character-leader")
    custodian = replace(
        base,
        datasheet_id="batch18-custodian",
        name="Canonical Custodes fighter",
        keywords=DatasheetKeywordSet(
            keywords=base.keywords.keywords, faction_keywords=("Adeptus Custodes",)
        ),
        abilities=(_martial_katah_ability(),),
    )
    catalog = replace(
        catalog,
        datasheets=(*catalog.datasheets, custodian),
        factions=(
            *catalog.factions,
            FactionDefinition(
                faction_id=ADEPTUS_CUSTODES_FACTION_ID,
                name="Adeptus Custodes",
                faction_keywords=("Adeptus Custodes",),
                source_ids=(army_rule.SOURCE_RULE_ID,),
            ),
        ),
        detachments=(
            *catalog.detachments,
            DetachmentDefinition(
                canonical_detachment_id="shield-host",
                detachment_id="shield-host",
                name="Shield Host",
                faction_id=ADEPTUS_CUSTODES_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(custodian.datasheet_id,),
                force_disposition_ids=("purge-the-foe",),
                source_ids=("batch18:canonical-detachment",),
            ),
        ),
    )
    config = fight_config(
        game_id="batch18-custodes-native-fight",
        alpha_unit_ids=("custodian", "unselected"),
        enemy_unit_ids=("enemy",),
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        alpha_unit_specs=dict.fromkeys(
            ("custodian", "unselected"), (custodian.datasheet_id, "core-character-leader", 1)
        ),
        catalog=catalog,
        alpha_faction_id=ADEPTUS_CUSTODES_FACTION_ID,
        alpha_detachment_ids=("shield-host",),
    )
    before = json.dumps(config.to_payload(), sort_keys=True)
    yield config
    assert json.dumps(config.to_payload(), sort_keys=True) == before


def _native_katah_request(config: GameConfig) -> tuple[LocalGameSession, DecisionRequest]:
    lifecycle, _units = fight_lifecycle(
        config=deepcopy(config),
        game_id=config.game_id,
        alpha_unit_ids=("custodian", "unselected"),
        enemy_unit_ids=("enemy",),
        origins={
            "custodian": Pose.at(10.0, 10.0),
            "unselected": Pose.at(30.0, 30.0),
            "enemy": Pose.at(11.0, 10.0),
        },
        charge_fights_first_unit_keys=("custodian",),
    )
    session = LocalGameSession(lifecycle=lifecycle)
    activation = decision_request(
        drain_fight_movement_requests(lifecycle, session.advance_until_decision_or_terminal())
    )
    assert activation.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    status = session.submit_option(
        request_id=activation.request_id,
        option_id=fight_activation_option_id(
            unit_instance_id="army-alpha:custodian", fight_type=FightTypeKind.NORMAL
        ),
        result_id="batch18:select-fighter",
    )
    request = decision_request(status)
    assert request.decision_type == SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert {option.option_id for option in request.options} == {
        DECLINE_FIGHT_UNIT_GRANT_OPTION_ID,
        army_rule.DACATARAI_HOOK_ID,
        army_rule.RENDAX_HOOK_ID,
    }
    return session, request


def _native_katah_registry(lifecycle: GameLifecycle) -> RuntimeModifierRegistry:
    require_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_bundle().runtime_modifier_registry


@pytest.mark.parametrize(
    ("option_id", "keyword", "ability_id"),
    [
        (army_rule.DACATARAI_HOOK_ID, WeaponKeyword.SUSTAINED_HITS, "sustained-hits:1"),
        (army_rule.RENDAX_HOOK_ID, WeaponKeyword.LETHAL_HITS, "lethal-hits"),
    ],
    ids=("dacatarai", "rendax"),
)
def test_native_katah_choice_reaches_loaded_profile_and_expires_with_unit_scope(
    shared_custodes_fight_config: GameConfig,
    option_id: str,
    keyword: WeaponKeyword,
    ability_id: str,
) -> None:
    """Native fight checkpoint -> finite stance -> loaded profile query; no attack rolls."""
    session, request = _native_katah_request(shared_custodes_fight_config)
    lifecycle = session.lifecycle
    state = lifecycle.state
    assert state is not None
    unit = state.army_definitions[0].unit_by_id("army-alpha:custodian")
    target = state.army_definitions[1].unit_by_id("army-beta:enemy")
    registry = _native_katah_registry(lifecycle)
    context = _modifier_context(state=state, unit=unit, target=target, melee=True)
    assert registry.modified_weapon_profile(context) == context.weapon_profile
    status = session.submit_option(
        request_id=request.request_id, option_id=option_id, result_id="batch18:choose-stance"
    )
    declaration = decision_request(drain_fight_movement_requests(lifecycle, status))
    assert declaration.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
    profile = registry.modified_weapon_profile(context)
    assert keyword in profile.keywords
    assert set(profile.keywords).intersection(
        {WeaponKeyword.SUSTAINED_HITS, WeaponKeyword.LETHAL_HITS}
    ) == {keyword}
    assert any(ability.ability_id == ability_id for ability in profile.abilities)
    assert army_rule.SOURCE_RULE_ID in profile.source_ids
    for other in ("army-alpha:unselected", "army-beta:enemy"):
        other_unit = next(
            a.unit_by_id(other) for a in state.army_definitions if other.startswith(a.army_id + ":")
        )
        neutral = replace(
            context,
            attacking_unit_instance_id=other,
            attacker_model_instance_id=other_unit.own_model_ids()[0],
        )
        assert registry.modified_weapon_profile(neutral) == neutral.weapon_profile
    ranged = replace(context, weapon_profile=_weapon_profile(melee=False))
    assert registry.modified_weapon_profile(ranged) == ranged.weapon_profile
    wrong_phase = replace(context, source_phase=BattlePhase.SHOOTING)
    assert registry.modified_weapon_profile(wrong_phase) == wrong_phase.weapon_profile
    # State round-trip and normal expiry owner; no full-session replay claim.
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    assert restored.to_payload() == state.to_payload()
    assert keyword in registry.modified_weapon_profile(replace(context, state=restored)).keywords
    boundary = EffectExpirationBoundary.phase_end(
        battle_round=state.battle_round, phase=BattlePhaseKind.FIGHT, player_id="player-a"
    )
    expired = restored.expire_persisting_effects_at_boundary(boundary)
    assert len([e for e in expired if e.source_rule_id == army_rule.SOURCE_RULE_ID]) == 1
    assert (
        registry.modified_weapon_profile(replace(context, state=restored)) == context.weapon_profile
    )
    assert keyword in registry.modified_weapon_profile(context).keywords
    assert restored.expire_persisting_effects_at_boundary(boundary) == ()
    assert (
        json.loads(json.dumps(lifecycle.decision_controller.to_payload()))
        == lifecycle.decision_controller.to_payload()
    )


def test_native_katah_invalid_choice_retries_then_decline_leaves_profile_plain(
    shared_custodes_fight_config: GameConfig,
) -> None:
    session, request = _native_katah_request(shared_custodes_fight_config)
    lifecycle = session.lifecycle
    option = request.option_by_id(army_rule.DACATARAI_HOOK_ID)
    drift = dict(cast(dict[str, JsonValue], option.payload))
    drift["battle_round"] = 99
    for actor, payload in (
        ("player-b", option.payload),
        ("player-a", "malformed"),
        ("player-a", cast(JsonValue, drift)),
    ):
        before = lifecycle.to_payload()
        status = lifecycle.submit_decision(
            DecisionResult(
                result_id=f"batch18:invalid:{actor}:{type(payload).__name__}",
                request_id=request.request_id,
                decision_type=request.decision_type,
                actor_id=actor,
                selected_option_id=option.option_id,
                payload=payload,
            )
        )
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert lifecycle.to_payload() == before
        assert lifecycle.decision_controller.queue.peek_next() == request
    status = session.submit_option(
        request_id=request.request_id,
        option_id=DECLINE_FIGHT_UNIT_GRANT_OPTION_ID,
        result_id="batch18:decline",
    )
    declaration = decision_request(drain_fight_movement_requests(lifecycle, status))
    assert declaration.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
    state = lifecycle.state
    assert state is not None
    assert state.fight_phase_state is not None
    unit = state.army_definitions[0].unit_by_id("army-alpha:custodian")
    target = state.army_definitions[1].unit_by_id("army-beta:enemy")
    context = _modifier_context(state=state, unit=unit, target=target, melee=True)
    assert (
        _native_katah_registry(lifecycle).modified_weapon_profile(context) == context.weapon_profile
    )
    assert not any(e.source_rule_id == army_rule.SOURCE_RULE_ID for e in state.persisting_effects)
