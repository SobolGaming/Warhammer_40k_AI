# pyright: reportPrivateUsage=false
from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.support.catalog_package_fixtures import (
    bloodcrushers_army,
    bloodcrushers_package,
    bloodcrushers_unit,
    flesh_hounds_army,
    flesh_hounds_package,
    flesh_hounds_unit,
)
from tests.support.catalog_rule_ir_fixtures import model_bearing_wargear
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_armies,
    battle_state_with_army,
    bloodcrushers_battlefield_state,
    current_model_ids,
    player_ability_index,
    set_current_model_wounds,
    single_model_unit_placement,
)
from tools.generate_ability_support_matrix import _ability_support_catalog_package

from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock import collect_battle_shock_test_requests
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState, PlacedArmy
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
    catalog_charge_roll_modifiers_for_unit,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
    record_catalog_feel_no_pain_sources_for_unit,
)
from warhammer40k_core.engine.catalog_static_attack_modifier_runtime import (
    record_catalog_static_rule_effects,
)
from warhammer40k_core.engine.charge_declaration import ChargeRollRequest, ChargeRollResult
from warhammer40k_core.engine.damage_allocation import FeelNoPainAttackCondition
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
)
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    RuntimeModifierRegistry,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.rule_ir import (
    RuleIR,
    RuleIRPayload,
)


def test_phase17k_instrument_of_chaos_catalog_ir_modifies_charge_roll_result() -> None:
    package = bloodcrushers_package()
    unit = bloodcrushers_unit(
        package=package,
        selected_wargear_id="000001115:instrument-of-chaos",
    )
    army = bloodcrushers_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    state = battle_state_with_army(army=army, battlefield=battlefield)
    destroyed_bearer_battlefield = battlefield.with_removed_models(
        (
            model_bearing_wargear(
                unit,
                "000001115:instrument-of-chaos",
            ).model_instance_id,
        )
    )
    destroyed_bearer_state = battle_state_with_army(
        army=army,
        battlefield=destroyed_bearer_battlefield,
    )
    records_by_name = {record.definition.name: record for record in player_index.all_records()}

    modifiers = catalog_charge_roll_modifiers_for_unit(
        state=state,
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids(
            battlefield=battlefield,
            unit=unit,
        ),
    )
    destroyed_bearer_modifiers = catalog_charge_roll_modifiers_for_unit(
        state=destroyed_bearer_state,
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids(
            battlefield=destroyed_bearer_battlefield,
            unit=unit,
        ),
    )
    request = ChargeRollRequest(
        request_id="phase17k-charge-roll",
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        source_decision_request_id="phase17k-charge-selection-request",
        source_decision_result_id="phase17k-charge-selection-result",
        roll_modifiers=modifiers,
    )
    roll_state = DiceRollManager("phase17k-game").roll_fixed(request.spec, [3, 4])
    result = ChargeRollResult.from_roll_state(
        request=request,
        roll_state=roll_state,
        reachable_target_distances_inches={},
    )
    destroyed_bearer_request = ChargeRollRequest(
        request_id="phase17k-charge-roll-destroyed-bearer",
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        source_decision_request_id="phase17k-charge-selection-request",
        source_decision_result_id="phase17k-charge-selection-destroyed-bearer-result",
        roll_modifiers=destroyed_bearer_modifiers,
    )
    destroyed_bearer_roll_state = DiceRollManager("phase17k-game").roll_fixed(
        destroyed_bearer_request.spec,
        [3, 4],
    )
    destroyed_bearer_result = ChargeRollResult.from_roll_state(
        request=destroyed_bearer_request,
        roll_state=destroyed_bearer_roll_state,
        reachable_target_distances_inches={},
    )

    assert records_by_name["Instrument of Chaos"].definition.timing.trigger_kind is (
        TimingTriggerKind.AFTER_DICE_ROLL
    )
    assert len(modifiers) == 1
    assert destroyed_bearer_modifiers == ()
    assert modifiers[0].operand == 1
    assert request.spec.expression.modifier == 1
    assert destroyed_bearer_request.spec.expression.modifier == 0
    assert result.value == 8
    assert destroyed_bearer_result.value == 7
    assert result.to_payload()["request"]["roll_modifiers"][0]["operand"] == 1
    with pytest.raises(GameLifecycleError, match="current model evidence must be a tuple"):
        catalog_charge_roll_modifiers_for_unit(
            state=state,
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=cast(tuple[str, ...], ["not-a-tuple"]),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence must not be empty"):
        catalog_charge_roll_modifiers_for_unit(
            state=state,
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence must not duplicate"):
        catalog_charge_roll_modifiers_for_unit(
            state=state,
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=(
                unit.own_models[0].model_instance_id,
                unit.own_models[0].model_instance_id,
            ),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence contains unknown"):
        catalog_charge_roll_modifiers_for_unit(
            state=state,
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=("army-khorne:bloodcrushers-1:model:missing",),
        )
    with pytest.raises(GameLifecycleError, match="requires an AbilityCatalogIndex"):
        catalog_charge_roll_modifiers_for_unit(
            state=state,
            ability_index=cast(AbilityCatalogIndex, object()),
            unit=unit,
            current_model_instance_ids=current_model_ids(
                battlefield=battlefield,
                unit=unit,
            ),
        )
    with pytest.raises(GameLifecycleError, match="requires a UnitInstance"):
        catalog_charge_roll_modifiers_for_unit(
            state=state,
            ability_index=player_index,
            unit=cast(UnitInstance, object()),
            current_model_instance_ids=current_model_ids(
                battlefield=battlefield,
                unit=unit,
            ),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence must contain IDs"):
        catalog_charge_roll_modifiers_for_unit(
            state=state,
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=("",),
        )
    with pytest.raises(GameLifecycleError, match="classification requires RuleIR"):
        catalog_rule_ir_consumers_for_rule(cast(RuleIR, object()))
    with pytest.raises(GameLifecycleError, match="classification requires RuleIR"):
        catalog_rule_ir_hook_ids_for_rule(cast(RuleIR, object()))


def test_phase17k_daemonic_icon_catalog_ir_modifies_battle_shock_leadership() -> None:
    package = bloodcrushers_package()
    unit = bloodcrushers_unit(
        package=package,
        selected_wargear_id="000001115:daemonic-icon",
    )
    army = bloodcrushers_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    bearer = model_bearing_wargear(unit, "000001115:daemonic-icon")
    alive_bearer_battlefield = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in unit.own_models if model != bearer)
    )
    destroyed_bearer_battlefield = battlefield.with_removed_models(
        (
            bearer.model_instance_id,
            next(model.model_instance_id for model in unit.own_models if model != bearer),
        )
    )
    alive_bearer_unit = replace(
        unit,
        own_models=tuple(
            model if model == bearer else replace(model, wounds_remaining=0)
            for model in unit.own_models
        ),
    )
    destroyed_model_ids = set(destroyed_bearer_battlefield.removed_model_ids)
    destroyed_bearer_unit = replace(
        unit,
        own_models=tuple(
            replace(model, wounds_remaining=0)
            if model.model_instance_id in destroyed_model_ids
            else model
            for model in unit.own_models
        ),
    )
    alive_bearer_army = replace(army, units=(alive_bearer_unit,))
    destroyed_bearer_army = replace(army, units=(destroyed_bearer_unit,))
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    starting_strength = (StartingStrengthRecord.from_unit(player_id=army.player_id, unit=unit),)

    requests_without_index = collect_battle_shock_test_requests(
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        army=alive_bearer_army,
        battlefield_state=alive_bearer_battlefield,
        starting_strength_records=starting_strength,
        battle_shocked_unit_ids=(),
    )
    alive_bearer_requests_with_index = collect_battle_shock_test_requests(
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        army=alive_bearer_army,
        battlefield_state=alive_bearer_battlefield,
        starting_strength_records=starting_strength,
        battle_shocked_unit_ids=(),
        ability_index=player_index,
    )
    destroyed_bearer_requests_with_index = collect_battle_shock_test_requests(
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        army=destroyed_bearer_army,
        battlefield_state=destroyed_bearer_battlefield,
        starting_strength_records=starting_strength,
        battle_shocked_unit_ids=(),
        ability_index=player_index,
    )

    assert records_by_name["Daemonic Icon"].definition.timing.trigger_kind is (
        TimingTriggerKind.PASSIVE_QUERY
    )
    assert records_by_name["Daemonic Icon"].definition.name == "Daemonic Icon"
    assert len(requests_without_index) == 1
    assert len(alive_bearer_requests_with_index) == 1
    assert len(destroyed_bearer_requests_with_index) == 1
    assert requests_without_index[0].leadership_target == 7
    assert alive_bearer_requests_with_index[0].leadership_target == 6
    assert destroyed_bearer_requests_with_index[0].leadership_target == 7


def test_phase17k_collar_of_khorne_catalog_ir_records_bearer_psychic_fnp_source() -> None:
    package = flesh_hounds_package()
    unit = flesh_hounds_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    bearer = model_bearing_wargear(unit, "test-flesh-hounds:collar-of-khorne")
    destroyed_bearer_battlefield = battlefield.with_removed_models((bearer.model_instance_id,))
    state = battle_state_with_army(army=army, battlefield=battlefield)
    destroyed_bearer_state = battle_state_with_army(
        army=army,
        battlefield=destroyed_bearer_battlefield,
    )
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    collar_record = records_by_name["Collar of Khorne"]
    replay_payload = collar_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    collar_rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))

    recorded_sources = record_catalog_feel_no_pain_sources_for_unit(
        state=state,
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids(
            battlefield=battlefield,
            unit=unit,
        ),
    )
    duplicate_recorded_sources = record_catalog_feel_no_pain_sources_for_unit(
        state=state,
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids(
            battlefield=battlefield,
            unit=unit,
        ),
    )
    destroyed_bearer_sources = record_catalog_feel_no_pain_sources_for_unit(
        state=destroyed_bearer_state,
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids(
            battlefield=destroyed_bearer_battlefield,
            unit=unit,
        ),
    )
    stored_sources = state.feel_no_pain_sources_for_model(
        model_instance_id=bearer.model_instance_id
    )

    assert collar_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert catalog_rule_ir_consumers_for_rule(collar_rule_ir) == (
        CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(collar_rule_ir)) == {
        CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
    }
    assert recorded_sources == duplicate_recorded_sources
    assert len(recorded_sources) == 1
    assert recorded_sources[0][0] == bearer.model_instance_id
    assert stored_sources == (recorded_sources[0][1],)
    assert stored_sources[0].threshold == 3
    assert stored_sources[0].attack_condition is FeelNoPainAttackCondition.PSYCHIC_ATTACK
    assert stored_sources[0].mortal_wounds is True
    assert all(
        state.feel_no_pain_sources_for_model(model_instance_id=model.model_instance_id) == ()
        for model in unit.own_models
        if model.model_instance_id != bearer.model_instance_id
    )
    assert destroyed_bearer_sources == ()
    assert (
        destroyed_bearer_state.feel_no_pain_sources_for_model(
            model_instance_id=bearer.model_instance_id
        )
        == ()
    )


def test_world_eaters_maulerfiend_exact_rule_ir_resolves_scent_and_savage_exaltation() -> None:
    package = _ability_support_catalog_package(datasheet_ids=("000002639", "000004091"))
    factory = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    )

    def army_for_datasheet(
        *,
        datasheet_id: str,
        army_id: str,
        player_id: str,
        faction_id: str,
        force_disposition_id: str,
    ) -> ArmyDefinition:
        datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
        model_profile = datasheet.model_profiles[0]
        unit = factory.instantiate_unit(
            army_id=army_id,
            datasheet=datasheet,
            selection=UnitMusterSelection(
                unit_selection_id=f"{datasheet_id}-1",
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id=model_profile.model_profile_id,
                        model_count=1,
                    ),
                ),
            ),
        )
        return ArmyDefinition(
            army_id=army_id,
            player_id=player_id,
            catalog_id=package.army_catalog.catalog_id,
            source_package_id=package.army_catalog.source_package_id,
            ruleset_id=package.army_catalog.ruleset_id,
            detachment_selection=DetachmentSelection(
                faction_id=faction_id,
                detachment_ids=(f"test-{faction_id.casefold()}",),
            ),
            force_disposition_id=force_disposition_id,
            units=(unit,),
        )

    world_eaters = army_for_datasheet(
        datasheet_id="000002639",
        army_id="world-eaters-army",
        player_id="world-eaters-player",
        faction_id="WE",
        force_disposition_id="take-and-hold",
    )
    opponent = army_for_datasheet(
        datasheet_id="000004091",
        army_id="opponent-army",
        player_id="opponent-player",
        faction_id="EC",
        force_disposition_id="purge-the-foe",
    )
    maulerfiend = world_eaters.units[0]
    target = opponent.units[0]
    battlefield = BattlefieldRuntimeState(
        battlefield_id="world-eaters-maulerfiend-runtime",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=world_eaters.army_id,
                player_id=world_eaters.player_id,
                unit_placements=(single_model_unit_placement(world_eaters, maulerfiend, x=10.0),),
            ),
            PlacedArmy(
                army_id=opponent.army_id,
                player_id=opponent.player_id,
                unit_placements=(single_model_unit_placement(opponent, target, x=23.0),),
            ),
        ),
    )
    state = battle_state_with_armies(
        armies=(world_eaters, opponent),
        battlefield=battlefield,
        active_player_id=world_eaters.player_id,
        phase=BattlePhase.CHARGE,
    )
    world_eaters_index = player_ability_index(package=package, army=world_eaters)

    def scent_modifiers() -> tuple[tuple[int, int], ...]:
        return tuple(
            (modifier.operand, modifier.priority)
            for modifier in catalog_charge_roll_modifiers_for_unit(
                state=state,
                ability_index=world_eaters_index,
                unit=maulerfiend,
                current_model_instance_ids=maulerfiend.own_model_ids(),
            )
        )

    assert scent_modifiers() == ()
    target_model = target.own_models[0]
    set_current_model_wounds(
        state,
        model_instance_id=target_model.model_instance_id,
        wounds_remaining=target_model.starting_wounds - 1,
    )
    assert scent_modifiers() == ((1, 1),)
    set_current_model_wounds(
        state,
        model_instance_id=target_model.model_instance_id,
        wounds_remaining=(target_model.starting_wounds - 1) // 2,
    )
    assert scent_modifiers() == ((2, 2),)

    record_catalog_static_rule_effects(
        state=state,
        ability_indexes_by_player_id={
            world_eaters.player_id: world_eaters_index,
            opponent.player_id: AbilityCatalogIndex.from_records(()),
        },
        armies=(world_eaters, opponent),
    )
    fists_profile = next(
        wargear.weapon_profiles[0]
        for wargear in package.army_catalog.wargear
        if wargear.wargear_id == "000002639:maulerfiend-fists"
    )
    magma_profile = next(
        wargear.weapon_profiles[0]
        for wargear in package.army_catalog.wargear
        if wargear.wargear_id == "000002639:magma-cutter"
    )
    modifier_registry = RuntimeModifierRegistry.empty()

    def attack_modifiers(*, melee: bool) -> tuple[int, int]:
        weapon_profile = fists_profile if melee else magma_profile
        phase = BattlePhase.FIGHT if melee else BattlePhase.SHOOTING
        return (
            modifier_registry.hit_roll_modifier(
                HitRollModifierContext(
                    state=state,
                    attacking_unit_instance_id=maulerfiend.unit_instance_id,
                    attacker_model_instance_id=maulerfiend.own_models[0].model_instance_id,
                    target_unit_instance_id=target.unit_instance_id,
                    weapon_profile=weapon_profile,
                    source_phase=phase,
                )
            ),
            modifier_registry.wound_roll_modifier(
                WoundRollModifierContext(
                    state=state,
                    source_phase=phase,
                    attacking_unit_instance_id=maulerfiend.unit_instance_id,
                    attacker_model_instance_id=maulerfiend.own_models[0].model_instance_id,
                    target_unit_instance_id=target.unit_instance_id,
                    weapon_profile=weapon_profile,
                    strength=weapon_profile.strength.final,
                    toughness=10,
                )
            ),
        )

    assert attack_modifiers(melee=True) == (1, 1)
    assert attack_modifiers(melee=False) == (0, 0)
