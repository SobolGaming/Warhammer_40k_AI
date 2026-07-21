# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.support.catalog_package_fixtures import (
    daemon_prince_unit,
    flesh_hounds_army,
    soul_grinder_unit,
    undivided_daemon_package,
)
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_armies,
    battle_state_with_army,
    bloodcrushers_battlefield_state,
    datasheet_weapon_profile,
    model_characteristic,
    player_ability_index,
    set_current_model_wounds,
    set_state_battle_phase,
    single_model_unit_placement,
)
from tests.support.wahapedia_bridge_fixtures import (
    daemon_prince_bridge_artifacts,
    soul_grinder_bridge_artifacts,
)
from tests.support.wahapedia_source_fixtures import catalog_package_id, catalog_version

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    DatasheetMusteringOptionEffectKind,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    WeaponKeyword,
)
from warhammer40k_core.engine import army_mustering
from warhammer40k_core.engine.abilities import (
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.ability_catalog import build_player_ability_index
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState, PlacedArmy
from warhammer40k_core.engine.catalog_any_phase_once_per_battle import (
    SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
    CatalogAnyPhaseOncePerBattleRuntime,
    apply_any_phase_once_per_battle_result,
    invalid_any_phase_once_per_battle_status,
)
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_once_per_battle_runtime import CatalogOncePerBattleRuntime
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEvent,
    RuntimeContentEventHandlerRegistry,
    RuntimeContentEventIndex,
)
from warhammer40k_core.engine.fight_phase_start_hooks import (
    FightPhaseStartHookRegistry,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    DECLINE_FIGHT_UNIT_GRANT_OPTION_ID,
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedGrantRegistry,
    fight_unit_selected_grant_options,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    MusteringOptionSelection,
    UnitMusterSelection,
    resolve_mustering_option_selections,
)
from warhammer40k_core.engine.list_validation_errors import ListValidationError
from warhammer40k_core.engine.phase import (
    BattlePhase,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    MovementBudgetModifierContext,
    RuntimeModifierRegistry,
    SaveOptionModifierContext,
    UnitCharacteristicModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookRegistry,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package


def test_phase17k_player_ability_index_uses_mustering_added_wargear() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=soul_grinder_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001151")
    torrent_id = "000001151:torrent-of-burning-blood"
    khorne_allegiance_option_id = "000001151:daemonic-allegiance:khorne"
    slaanesh_allegiance_option_id = "000001151:daemonic-allegiance:slaanesh"
    torrent_record = AbilityCatalogRecord(
        record_id="phase17k:test:soul-grinder:torrent-of-burning-blood",
        definition=AbilityDefinition(
            ability_id="phase17k:soul-grinder:torrent-of-burning-blood",
            name="Torrent of Burning Blood Gate",
            source_id="phase17k:test:soul-grinder:torrent-of-burning-blood",
            when_descriptor="Catalog bridge mustering-added wargear source test.",
            effect_descriptor="Synthetic wargear-source ability for mustering-added wargear.",
            restrictions_descriptor=f"Selected wargear required: {torrent_id}.",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
            replay_payload=validate_json_value({"source_wargear_id": torrent_id}),
        ),
        source_kind=AbilitySourceKind.WARGEAR,
        datasheet_id=datasheet.datasheet_id,
        wargear_id=torrent_id,
    )
    khorne_unit = soul_grinder_unit(
        package,
        requested_wargear_selections=(),
        mustering_option_selections=(
            MusteringOptionSelection(option_id=khorne_allegiance_option_id),
        ),
    )
    slaanesh_unit = soul_grinder_unit(
        package,
        requested_wargear_selections=(),
        mustering_option_selections=(
            MusteringOptionSelection(option_id=slaanesh_allegiance_option_id),
        ),
    )

    khorne_records_by_name = {
        record.definition.name: record
        for record in build_player_ability_index(
            (torrent_record,),
            army=flesh_hounds_army(
                package=package,
                unit=khorne_unit,
                player_id="player-khorne-soul-grinder",
            ),
            catalog=package.army_catalog,
        ).all_records()
    }
    slaanesh_records_by_name = {
        record.definition.name: record
        for record in build_player_ability_index(
            (torrent_record,),
            army=flesh_hounds_army(
                package=package,
                unit=slaanesh_unit,
                player_id="player-slaanesh-soul-grinder",
            ),
            catalog=package.army_catalog,
        ).all_records()
    }

    assert khorne_records_by_name["Torrent of Burning Blood Gate"].wargear_id == torrent_id
    assert "Torrent of Burning Blood Gate" not in slaanesh_records_by_name


def test_phase17k_runtime_content_activation_uses_mustering_added_wargear() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=soul_grinder_bridge_artifacts(),
    )
    torrent_id = "000001151:torrent-of-burning-blood"
    khorne_unit = soul_grinder_unit(
        package,
        requested_wargear_selections=(),
        mustering_option_selections=(
            MusteringOptionSelection(option_id="000001151:daemonic-allegiance:khorne"),
        ),
    )
    slaanesh_unit = soul_grinder_unit(
        package,
        requested_wargear_selections=(),
        mustering_option_selections=(
            MusteringOptionSelection(option_id="000001151:daemonic-allegiance:slaanesh"),
        ),
    )

    khorne_activation = RuntimeContentActivation.from_armies(
        armies=(flesh_hounds_army(package=package, unit=khorne_unit),),
        catalog=package.army_catalog,
    )
    slaanesh_activation = RuntimeContentActivation.from_armies(
        armies=(flesh_hounds_army(package=package, unit=slaanesh_unit),),
        catalog=package.army_catalog,
    )

    assert torrent_id in khorne_activation.selected_wargear_ids
    assert torrent_id not in slaanesh_activation.selected_wargear_ids


def test_phase17k_daemon_prince_bridge_supports_daemonic_allegiance_choices() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=daemon_prince_bridge_artifacts(),
    )
    for datasheet_id, model_profile_id in (
        ("000001149", "000001149:daemon-prince-of-chaos"),
        ("000002758", "000002758:daemon-prince-of-chaos-with-wings"),
    ):
        datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
        options_by_id = {option.option_id: option for option in datasheet.mustering_options}
        nurgle_option_id = f"{datasheet_id}:daemonic-allegiance:nurgle"
        tzeentch_option_id = f"{datasheet_id}:daemonic-allegiance:tzeentch"
        abilities_by_name = {ability.name: ability for ability in datasheet.abilities}

        with pytest.raises(ListValidationError, match="required option group"):
            resolve_mustering_option_selections(datasheet=datasheet, requested_selections=())
        assert set(options_by_id) == {
            f"{datasheet_id}:daemonic-allegiance:khorne",
            nurgle_option_id,
            f"{datasheet_id}:daemonic-allegiance:slaanesh",
            tzeentch_option_id,
        }
        nurgle_option = options_by_id[nurgle_option_id]
        assert nurgle_option.selection_group_id == f"{datasheet_id}:daemonic-allegiance"
        assert nurgle_option.model_profile_id == model_profile_id
        assert nurgle_option.required is True
        assert tuple(effect.kind for effect in nurgle_option.effects) == (
            DatasheetMusteringOptionEffectKind.ADD_KEYWORD,
        )
        assert nurgle_option.effects[0].keyword == "NURGLE"
        assert "Daemon Prince of Tzeentch" in abilities_by_name
        assert (
            abilities_by_name["Daemon Prince of Tzeentch"].source_kind
            is CatalogAbilitySourceKind.DATASHEET
        )

        unit = UnitFactory(
            catalog=package.army_catalog,
            model_geometries=package.model_geometries,
        ).instantiate_unit(
            army_id="army-daemons",
            selection=UnitMusterSelection(
                unit_selection_id=f"{datasheet_id}-prince-1",
                datasheet_id=datasheet.datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id=model_profile_id,
                        model_count=1,
                    ),
                ),
                mustering_option_selections=(
                    MusteringOptionSelection(option_id=tzeentch_option_id),
                ),
            ),
            datasheet=datasheet,
        )
        assert "TZEENTCH" in unit.keywords
        assert unit.mustering_option_selections == (
            MusteringOptionSelection(option_id=tzeentch_option_id),
        )
        assert unit.own_models[0].wargear_ids == (
            f"{datasheet_id}:infernal-cannon",
            f"{datasheet_id}:hellforged-weapons",
        )


def test_phase17k_daemon_prince_allegiance_modifiers_use_generic_runtime_queries() -> None:
    package = undivided_daemon_package()

    def runtime_for(allegiance: str) -> tuple[UnitInstance, GameState, RuntimeModifierRegistry]:
        unit = daemon_prince_unit(
            package=package,
            datasheet_id="000001149",
            allegiance=allegiance,
            unit_selection_id=f"daemon-prince-{allegiance.lower()}",
        )
        army = flesh_hounds_army(package=package, unit=unit)
        state = battle_state_with_army(
            army=army,
            battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
        )
        catalog_runtime = CatalogDatasheetRuleRuntime(
            {army.player_id: player_ability_index(package=package, army=army)},
            (army,),
        )
        return (
            unit,
            state,
            RuntimeModifierRegistry.from_bindings(
                unit_characteristic_modifier_bindings=(
                    catalog_runtime.unit_characteristic_modifier_bindings()
                ),
                movement_budget_modifier_bindings=(
                    catalog_runtime.movement_budget_modifier_bindings()
                ),
                weapon_profile_modifier_bindings=(
                    catalog_runtime.weapon_profile_modifier_bindings()
                ),
            ),
        )

    hellforged = datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000001149",
        profile_name="Hellforged weapons - strike",
    )
    infernal_cannon = datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000001149",
        profile_name="Infernal cannon",
    )
    khorne_unit, khorne_state, khorne_registry = runtime_for("KHORNE")
    khorne_context = WeaponProfileModifierContext(
        state=khorne_state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=khorne_unit.unit_instance_id,
        attacker_model_instance_id=khorne_unit.own_models[0].model_instance_id,
        target_unit_instance_id=khorne_unit.unit_instance_id,
        weapon_profile=hellforged,
    )
    assert (
        khorne_registry.modified_weapon_profile(khorne_context).strength.final
        == hellforged.strength.final + 2
    )
    assert (
        khorne_registry.modified_weapon_profile(
            replace(khorne_context, weapon_profile=infernal_cannon)
        ).strength.final
        == infernal_cannon.strength.final
    )
    assert khorne_unit.own_models[0].is_alive
    set_current_model_wounds(
        khorne_state,
        model_instance_id=khorne_unit.own_models[0].model_instance_id,
        wounds_remaining=0,
    )
    assert (
        khorne_registry.modified_weapon_profile(khorne_context).strength.final
        == hellforged.strength.final
    )

    tzeentch_unit, tzeentch_state, tzeentch_registry = runtime_for("TZEENTCH")
    tzeentch_context = replace(
        khorne_context,
        state=tzeentch_state,
        attacking_unit_instance_id=tzeentch_unit.unit_instance_id,
        attacker_model_instance_id=tzeentch_unit.own_models[0].model_instance_id,
        target_unit_instance_id=tzeentch_unit.unit_instance_id,
    )
    modified_infernal = tzeentch_registry.modified_weapon_profile(
        replace(tzeentch_context, weapon_profile=infernal_cannon)
    )
    assert modified_infernal.attack_profile.fixed_attacks == (
        (infernal_cannon.attack_profile.fixed_attacks or 0) + 3
    )
    assert (
        tzeentch_registry.modified_weapon_profile(tzeentch_context).attack_profile
        == hellforged.attack_profile
    )

    nurgle_unit, nurgle_state, nurgle_registry = runtime_for("NURGLE")
    base_toughness = model_characteristic(nurgle_unit, Characteristic.TOUGHNESS)
    assert nurgle_registry.modified_unit_characteristic(
        UnitCharacteristicModifierContext(
            state=nurgle_state,
            unit_instance_id=nurgle_unit.unit_instance_id,
            characteristic=Characteristic.TOUGHNESS,
            base_value=base_toughness,
            current_value=base_toughness,
        )
    ) == (base_toughness + 1)

    slaanesh_unit, slaanesh_state, slaanesh_registry = runtime_for("SLAANESH")
    base_movement = float(model_characteristic(slaanesh_unit, Characteristic.MOVEMENT))
    slaanesh_context = MovementBudgetModifierContext(
        state=slaanesh_state,
        unit_instance_id=slaanesh_unit.unit_instance_id,
        model_instance_id=slaanesh_unit.own_models[0].model_instance_id,
        base_movement_inches=base_movement,
        current_movement_inches=base_movement,
    )
    assert slaanesh_registry.modified_movement_inches(slaanesh_context) == (base_movement + 2.0)
    assert slaanesh_state.battlefield_state is not None
    slaanesh_state.battlefield_state = slaanesh_state.battlefield_state.with_removed_models(
        (slaanesh_unit.own_models[0].model_instance_id,)
    )
    assert slaanesh_unit.own_models[0].is_alive
    assert slaanesh_registry.modified_movement_inches(slaanesh_context) == base_movement


def test_phase17k_malefic_destruction_persists_generic_scoped_attacks_modifier() -> None:
    package = undivided_daemon_package()
    unit = daemon_prince_unit(
        package=package,
        datasheet_id="000002758",
        allegiance="KHORNE",
        unit_selection_id="winged-prince-malefic",
    )
    army = flesh_hounds_army(package=package, unit=unit)
    state = battle_state_with_army(
        army=army,
        battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
    )
    set_state_battle_phase(state, BattlePhase.FIGHT)
    decisions = DecisionController()
    runtime = CatalogOncePerBattleRuntime(
        ability_indexes_by_player_id={
            army.player_id: player_ability_index(package=package, army=army)
        },
        armies=(army,),
    )
    registry = FightPhaseStartHookRegistry.from_bindings(runtime.fight_phase_start_bindings())
    destroyed_state = battle_state_with_army(
        army=army,
        battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
    )
    set_state_battle_phase(destroyed_state, BattlePhase.FIGHT)
    set_current_model_wounds(
        destroyed_state,
        model_instance_id=unit.own_models[0].model_instance_id,
        wounds_remaining=0,
    )
    assert unit.own_models[0].is_alive
    assert (
        registry.next_request_for(
            FightPhaseStartRequestContext(
                state=destroyed_state,
                decisions=DecisionController(),
            )
        )
        is None
    )
    request = registry.next_request_for(
        FightPhaseStartRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    use_option = next(
        option
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["activate"]
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="winged-prince-malefic-result",
        request=request,
        selected_option_id=use_option.option_id,
    )
    record = decisions.submit_result(result)
    assert (
        registry.apply_result(
            FightPhaseStartResultContext(
                state=state,
                decisions=decisions,
                request=record.request,
                result=record.result,
            )
        )
        is True
    )
    strike = datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000002758",
        profile_name="Hellforged weapons - strike",
    )
    infernal = datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000002758",
        profile_name="Infernal cannon",
    )
    context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        target_unit_instance_id=unit.unit_instance_id,
        weapon_profile=strike,
    )
    modifier_registry = RuntimeModifierRegistry.from_bindings()
    assert modifier_registry.modified_weapon_profile(context).attack_profile.fixed_attacks == (
        (strike.attack_profile.fixed_attacks or 0) + 3
    )
    assert (
        modifier_registry.modified_weapon_profile(
            replace(context, weapon_profile=infernal)
        ).attack_profile
        == infernal.attack_profile
    )


def test_phase17k_harbinger_of_death_requires_generic_finite_weapon_choice() -> None:
    package = undivided_daemon_package()
    unit = daemon_prince_unit(
        package=package,
        datasheet_id="000002758",
        allegiance="NURGLE",
        unit_selection_id="winged-prince-harbinger",
    )
    army = flesh_hounds_army(package=package, unit=unit)
    state = battle_state_with_army(
        army=army,
        battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
    )
    set_state_battle_phase(state, BattlePhase.FIGHT)
    runtime = CatalogDatasheetRuleRuntime(
        {army.player_id: player_ability_index(package=package, army=army)},
        (army,),
    )
    grant_registry = FightUnitSelectedGrantRegistry.from_bindings(
        runtime.fight_unit_selected_grant_bindings()
    )
    grant_context = FightUnitSelectedContext(
        state=state,
        player_id=army.player_id,
        battle_round=1,
        unit_instance_id=unit.unit_instance_id,
        fight_type="normal",
        ordering_band="remaining_combats",
        request_id="fight-activation-request",
        result_id="fight-activation-result",
    )
    grants = grant_registry.grants_for(grant_context)
    options = fight_unit_selected_grant_options(
        unit_instance_id=unit.unit_instance_id,
        activation_request_id="fight-activation-request",
        activation_result_id="fight-activation-result",
        grants=grants,
    )
    assert tuple(grant.label for grant in grants) == (
        "Lethal Hits",
        "Precision",
        "Sustained Hits",
    )
    assert all(not grant.decline_allowed for grant in grants)
    assert DECLINE_FIGHT_UNIT_GRANT_OPTION_ID not in {option.option_id for option in options}
    assert len(options) == 3
    optional_grant = replace(
        grants[0],
        hook_id="optional-fight-grant",
        label="Optional fight grant",
        decline_allowed=True,
    )
    combined_options = fight_unit_selected_grant_options(
        unit_instance_id=unit.unit_instance_id,
        activation_request_id="fight-activation-request",
        activation_result_id="fight-activation-result",
        grants=(*grants, optional_grant),
    )
    assert len(combined_options) == 6
    combined = next(option for option in combined_options if ":with:" in option.option_id)
    assert (
        len(
            cast(
                list[JsonValue],
                cast(dict[str, JsonValue], combined.payload)["selected_fight_unit_grants"],
            )
        )
        == 2
    )
    sustained = next(grant for grant in grants if grant.label == "Sustained Hits")
    assert FightUnitSelectedGrant.from_payload(sustained.to_payload()) == sustained
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="harbinger-sustained-hits-effect",
            source_rule_id=sustained.source_id,
            owner_player_id=army.player_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            started_battle_round=1,
            started_phase=BattlePhaseKind.FIGHT,
            expiration=EffectExpiration.end_phase(
                battle_round=1,
                phase=BattlePhaseKind.FIGHT,
                player_id=army.player_id,
            ),
            effect_payload=sustained.unit_effect_payload,
        )
    )
    strike = datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000002758",
        profile_name="Hellforged weapons - strike",
    )
    infernal = datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000002758",
        profile_name="Infernal cannon",
    )
    context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=unit.unit_instance_id,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        target_unit_instance_id=unit.unit_instance_id,
        weapon_profile=strike,
    )
    modifier_registry = RuntimeModifierRegistry.from_bindings()
    assert (
        WeaponKeyword.SUSTAINED_HITS in modifier_registry.modified_weapon_profile(context).keywords
    )
    assert (
        WeaponKeyword.SUSTAINED_HITS
        not in modifier_registry.modified_weapon_profile(
            replace(context, weapon_profile=infernal)
        ).keywords
    )
    set_current_model_wounds(
        state,
        model_instance_id=unit.own_models[0].model_instance_id,
        wounds_remaining=0,
    )
    assert unit.own_models[0].is_alive
    assert grant_registry.grants_for(grant_context) == ()


def test_phase17k_unholy_vigour_any_phase_decision_is_replay_safe_and_runtime_consumed() -> None:
    package = undivided_daemon_package()
    unit = daemon_prince_unit(
        package=package,
        datasheet_id="000001149",
        allegiance="NURGLE",
        unit_selection_id="daemon-prince-unholy-vigour",
    )
    army = flesh_hounds_army(package=package, unit=unit)
    state = battle_state_with_army(
        army=army,
        battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
    )
    set_state_battle_phase(state, BattlePhase.MOVEMENT)
    decisions = DecisionController()
    runtime = CatalogAnyPhaseOncePerBattleRuntime(
        {army.player_id: player_ability_index(package=package, army=army)},
        (army,),
    )
    handler_registry = RuntimeContentEventHandlerRegistry.from_bindings(
        runtime.event_handler_bindings()
    )
    event_index = RuntimeContentEventIndex.from_subscriptions(
        runtime.event_subscriptions(),
        handler_registry=handler_registry,
    )
    event = RuntimeContentEvent(
        event_id="unholy-vigour-movement-start",
        game_id=state.game_id,
        player_id=army.player_id,
        battle_round=1,
        trigger_kind=TimingTriggerKind.START_PHASE,
        phase=BattlePhaseKind.MOVEMENT,
        active_player_id=army.player_id,
    )
    event_results = event_index.dispatch(
        event,
        state=state,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=package.army_catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.from_bindings(),
    )
    request = decisions.queue.peek_next()
    assert len(event_results) == 1
    assert request.decision_type == SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE
    assert type(request).from_payload(request.to_payload()).to_payload() == request.to_payload()
    use_option = next(
        option
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["activate"]
    )
    result = DecisionResult.for_request(
        result_id="unholy-vigour-use-result",
        request=request,
        selected_option_id=use_option.option_id,
    )
    malformed = invalid_any_phase_once_per_battle_status(
        state=state,
        decisions=decisions,
        request=request,
        result=replace(result, payload={"activate": True}),
    )
    assert malformed is not None
    assert cast(dict[str, JsonValue], malformed.payload)["field"] == "payload"
    assert decisions.queue.peek_next() == request
    assert state.persisting_effects_for_unit(unit.unit_instance_id) == ()
    state.battle_round = 2
    stale = invalid_any_phase_once_per_battle_status(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    assert stale is not None
    assert cast(dict[str, JsonValue], stale.payload)["field"] == "battle_round"
    state.battle_round = 1
    assert (
        invalid_any_phase_once_per_battle_status(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
        is None
    )
    record = decisions.submit_result(result)
    apply_any_phase_once_per_battle_result(
        state=state,
        decisions=decisions,
        request=record.request,
        result=record.result,
    )
    assert len(state.persisting_effects_for_unit(unit.unit_instance_id)) == 1
    infernal = datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000001149",
        profile_name="Infernal cannon",
    )
    save_options = RuntimeModifierRegistry.from_bindings().modified_save_options(
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=unit.unit_instance_id,
            save_options=(
                SaveOption(
                    save_kind=SaveKind.ARMOUR,
                    target_number=3,
                    characteristic_target_number=3,
                    armor_penetration=0,
                ),
                SaveOption(
                    save_kind=SaveKind.INVULNERABLE,
                    target_number=4,
                    characteristic_target_number=4,
                    armor_penetration=0,
                ),
            ),
            source_phase=BattlePhase.MOVEMENT,
            attacking_unit_instance_id=unit.unit_instance_id,
            attacker_model_instance_id=unit.own_models[0].model_instance_id,
            weapon_profile=infernal,
        )
    )
    assert (
        next(
            option for option in save_options if option.save_kind is SaveKind.INVULNERABLE
        ).target_number
        == 3
    )


def test_phase17k_unholy_vigour_submits_through_local_game_session() -> None:
    package = undivided_daemon_package()
    catalog = replace(
        package.army_catalog,
        detachments=(
            DetachmentDefinition(
                detachment_id="phase17k-daemons",
                name="Phase 17K Daemons",
                faction_id=package.army_catalog.factions[0].faction_id,
                detachment_point_cost=1,
                unit_datasheet_ids=("000001149", "000002758"),
                force_disposition_ids=("phase17k-force",),
                source_ids=("test:phase17k-daemons",),
            ),
        ),
    )
    source_selection = UnitMusterSelection(
        unit_selection_id="facade-daemon-prince",
        datasheet_id="000001149",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="000001149:daemon-prince-of-chaos", model_count=1
            ),
        ),
        mustering_option_selections=(
            MusteringOptionSelection(option_id="000001149:daemonic-allegiance:nurgle"),
        ),
    )
    enemy_selection = UnitMusterSelection(
        unit_selection_id="facade-winged-prince",
        datasheet_id="000002758",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="000002758:daemon-prince-of-chaos-with-wings",
                model_count=1,
            ),
        ),
        mustering_option_selections=(
            MusteringOptionSelection(option_id="000002758:daemonic-allegiance:khorne"),
        ),
    )
    detachment_selection = DetachmentSelection(
        faction_id=catalog.factions[0].faction_id,
        detachment_ids=("phase17k-daemons",),
    )
    muster_requests = (
        ArmyMusterRequest(
            army_id="army-daemons",
            player_id="player-daemons",
            catalog_id=catalog.catalog_id,
            source_package_id=catalog.source_package_id,
            ruleset_id=catalog.ruleset_id,
            detachment_selection=detachment_selection,
            force_disposition_id="phase17k-force",
            unit_selections=(source_selection,),
        ),
        ArmyMusterRequest(
            army_id="army-enemy",
            player_id="player-enemy",
            catalog_id=catalog.catalog_id,
            source_package_id=catalog.source_package_id,
            ruleset_id=catalog.ruleset_id,
            detachment_selection=detachment_selection,
            force_disposition_id="phase17k-force",
            unit_selections=(enemy_selection,),
        ),
    )
    source_army, enemy_army = tuple(
        army_mustering.muster_army(catalog=catalog, request=muster_request)
        for muster_request in muster_requests
    )
    source = source_army.units[0]
    enemy = enemy_army.units[0]
    battlefield = BattlefieldRuntimeState(
        battlefield_id="unholy-vigour-facade",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=source_army.army_id,
                player_id=source_army.player_id,
                unit_placements=(single_model_unit_placement(source_army, source, x=12.0),),
            ),
            PlacedArmy(
                army_id=enemy_army.army_id,
                player_id=enemy_army.player_id,
                unit_placements=(single_model_unit_placement(enemy_army, enemy, x=30.0),),
            ),
        ),
    )
    state = battle_state_with_armies(
        armies=(source_army, enemy_army),
        battlefield=battlefield,
        phase=BattlePhase.MOVEMENT,
        active_player_id=source_army.player_id,
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    config = GameConfig(
        game_id=state.game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=descriptor,
        army_catalog=catalog,
        army_muster_requests=muster_requests,
        player_ids=(source_army.player_id, enemy_army.player_id),
        turn_order=(source_army.player_id, enemy_army.player_id),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
    )
    lifecycle = GameLifecycle.from_payload(
        cast(
            Any,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": DecisionController().to_payload(),
                "reaction_queue": ReactionQueue().to_payload(),
            },
        )
    )
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.advance_until_decision_or_terminal()
    request = status.decision_request
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert request is not None
    assert request.decision_type == SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE
    assert request.actor_id == source_army.player_id
    actor_view = session.view(viewer_player_id=source_army.player_id)
    opponent_view = session.view(viewer_player_id=enemy_army.player_id)
    assert actor_view["pending_decision"] is not None
    assert opponent_view["pending_decision"] is not None
    assert actor_view["pending_decision"]["decision_type"] == request.decision_type
    assert opponent_view["pending_decision"]["decision_type"] == request.decision_type
    use_option = next(
        option
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["activate"]
    )
    submitted = session.submit_option(
        request_id=request.request_id,
        option_id=use_option.option_id,
        result_id="unholy-vigour-facade-result",
    )
    assert submitted.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.state is not None
    assert len(lifecycle.state.persisting_effects_for_unit(source.unit_instance_id)) == 1
    assert len(lifecycle.decision_controller.records) == 1
    assert "object at 0x" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


def test_phase17k_daemonic_lord_and_stealth_aura_use_group_aware_generic_queries() -> None:
    package = undivided_daemon_package()
    source = daemon_prince_unit(
        package=package,
        datasheet_id="000001149",
        allegiance="NURGLE",
        unit_selection_id="daemon-prince-aura-source",
    )
    support = soul_grinder_unit(
        package,
        requested_wargear_selections=(),
        mustering_option_selections=(
            MusteringOptionSelection(option_id="000001151:daemonic-allegiance:khorne"),
        ),
    )
    support = replace(support, keywords=tuple(sorted((*support.keywords, "INFANTRY"))))
    attacker = daemon_prince_unit(
        package=package,
        datasheet_id="000001149",
        allegiance="TZEENTCH",
        unit_selection_id="daemon-prince-attacker",
        army_id="army-enemy",
    )
    friendly_army = replace(
        flesh_hounds_army(package=package, unit=source),
        units=(source, support),
    )
    enemy_army = flesh_hounds_army(
        package=package,
        unit=attacker,
        army_id="army-enemy",
        player_id="player-enemy",
    )

    def battlefield(support_x: float) -> BattlefieldRuntimeState:
        return BattlefieldRuntimeState(
            battlefield_id=f"daemon-prince-aura-{support_x}",
            battlefield_width_inches=60.0,
            battlefield_depth_inches=44.0,
            placed_armies=(
                PlacedArmy(
                    army_id=friendly_army.army_id,
                    player_id=friendly_army.player_id,
                    unit_placements=(
                        single_model_unit_placement(friendly_army, source, x=12.0),
                        single_model_unit_placement(friendly_army, support, x=support_x),
                    ),
                ),
                PlacedArmy(
                    army_id=enemy_army.army_id,
                    player_id=enemy_army.player_id,
                    unit_placements=(single_model_unit_placement(enemy_army, attacker, x=40.0),),
                ),
            ),
        )

    state = battle_state_with_armies(
        armies=(friendly_army, enemy_army),
        battlefield=battlefield(14.0),
        phase=BattlePhase.SHOOTING,
        active_player_id=enemy_army.player_id,
    )
    runtime = CatalogDatasheetRuleRuntime(
        {
            friendly_army.player_id: player_ability_index(package=package, army=friendly_army),
            enemy_army.player_id: player_ability_index(package=package, army=enemy_army),
        },
        (friendly_army, enemy_army),
    )
    infernal = datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id="000001149",
        profile_name="Infernal cannon",
    )
    hit_registry = RuntimeModifierRegistry.from_bindings(
        hit_roll_modifier_bindings=runtime.hit_roll_modifier_bindings()
    )
    hit_context = HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=source.unit_instance_id,
        weapon_profile=infernal,
        source_phase=BattlePhase.SHOOTING,
    )
    restriction_registry = ShootingTargetRestrictionHookRegistry.from_bindings(
        runtime.shooting_target_restriction_bindings()
    )
    restriction_context = ShootingTargetRestrictionContext(
        state=state,
        player_id=enemy_army.player_id,
        battle_round=1,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=source.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
    )
    assert hit_registry.hit_roll_modifier(hit_context) == -1
    support_hit_context = replace(
        hit_context,
        target_unit_instance_id=support.unit_instance_id,
    )
    assert hit_registry.hit_roll_modifier(support_hit_context) == -1
    assert (
        hit_registry.hit_roll_modifier(
            replace(
                hit_context,
                source_phase=BattlePhase.FIGHT,
                weapon_profile=datasheet_weapon_profile(
                    package.army_catalog,
                    datasheet_id="000001149",
                    profile_name="Hellforged weapons - strike",
                ),
            )
        )
        == 0
    )
    restrictions = restriction_registry.restrictions_for(restriction_context)
    assert len(restrictions) == 1
    assert restrictions[0].violation_code == "conditional_lone_operative_range"

    state.battlefield_state = battlefield(30.0)
    assert restriction_registry.restrictions_for(restriction_context) == ()
    assert hit_registry.hit_roll_modifier(support_hit_context) == 0

    state.battlefield_state = battlefield(14.0)
    set_current_model_wounds(
        state,
        model_instance_id=source.own_models[0].model_instance_id,
        wounds_remaining=0,
    )
    assert source.own_models[0].is_alive
    assert hit_registry.hit_roll_modifier(support_hit_context) == 0
    assert restriction_registry.restrictions_for(restriction_context) == ()
