# pyright: reportPrivateUsage=false
from __future__ import annotations

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
    battle_state_with_army,
    bloodcrushers_battlefield_state,
    current_model_ids,
    player_ability_index,
)

from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
)
from warhammer40k_core.engine.battle_shock import collect_battle_shock_test_requests
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_FEEL_NO_PAIN_SOURCE_CONSUMER_ID,
    catalog_charge_roll_modifiers_for_unit,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
    record_catalog_feel_no_pain_sources_for_unit,
)
from warhammer40k_core.engine.charge_declaration import ChargeRollRequest, ChargeRollResult
from warhammer40k_core.engine.damage_allocation import FeelNoPainAttackCondition
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
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
    destroyed_bearer_battlefield = battlefield.with_removed_models(
        (
            model_bearing_wargear(
                unit,
                "000001115:instrument-of-chaos",
            ).model_instance_id,
        )
    )
    records_by_name = {record.definition.name: record for record in player_index.all_records()}

    modifiers = catalog_charge_roll_modifiers_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids(
            battlefield=battlefield,
            unit=unit,
        ),
    )
    destroyed_bearer_modifiers = catalog_charge_roll_modifiers_for_unit(
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
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=cast(tuple[str, ...], ["not-a-tuple"]),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence must not be empty"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence must not duplicate"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=(
                unit.own_models[0].model_instance_id,
                unit.own_models[0].model_instance_id,
            ),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence contains unknown"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=("army-khorne:bloodcrushers-1:model:missing",),
        )
    with pytest.raises(GameLifecycleError, match="requires an AbilityCatalogIndex"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=cast(AbilityCatalogIndex, object()),
            unit=unit,
            current_model_instance_ids=current_model_ids(
                battlefield=battlefield,
                unit=unit,
            ),
        )
    with pytest.raises(GameLifecycleError, match="requires a UnitInstance"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=cast(UnitInstance, object()),
            current_model_instance_ids=current_model_ids(
                battlefield=battlefield,
                unit=unit,
            ),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence must contain IDs"):
        catalog_charge_roll_modifiers_for_unit(
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
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    starting_strength = (StartingStrengthRecord.from_unit(player_id=army.player_id, unit=unit),)

    requests_without_index = collect_battle_shock_test_requests(
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        army=army,
        battlefield_state=alive_bearer_battlefield,
        starting_strength_records=starting_strength,
    )
    alive_bearer_requests_with_index = collect_battle_shock_test_requests(
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        army=army,
        battlefield_state=alive_bearer_battlefield,
        starting_strength_records=starting_strength,
        ability_index=player_index,
    )
    destroyed_bearer_requests_with_index = collect_battle_shock_test_requests(
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        army=army,
        battlefield_state=destroyed_bearer_battlefield,
        starting_strength_records=starting_strength,
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
