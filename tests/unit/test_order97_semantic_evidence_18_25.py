"""Narrow real-domain evidence for independently enumerated Orders 18-25 clauses."""

from __future__ import annotations

from dataclasses import replace

import pytest
from tests.phase13b_shooting_declaration_helpers import (
    _first_weapon_profile,
    _shooting_lifecycle,
    _state,
)
from tests.phase15d_fight_resolution_helpers import melee_fixture, melee_proposal, melee_request
from tests.support.ability_presence_fixtures import ability_presence_fixture

from warhammer40k_core.core.core_ability_family import CoreAbilityFamily
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.catalog_rule_consumption import CatalogWeaponKeywordGrantRuntime
from warhammer40k_core.engine.damage_allocation import destroy_model_by_rule
from warhammer40k_core.engine.deployment_ability_queries import rules_unit_has_infiltrators
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.fight_resolution import (
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
    melee_attack_sequence_from_proposal,
    validate_melee_declaration_rules,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lone_operative import lone_operative_profile_for_rules_unit
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.reserve_declarations import (
    _deep_strike_option_for_unit,  # pyright: ignore[reportPrivateUsage]
    reserve_legality_context_for_player,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext
from warhammer40k_core.engine.scout_abilities import scout_ability_instances_for_rules_unit
from warhammer40k_core.engine.unit_abilities import (
    deadly_demise_profile_for_unit,
    unit_has_deadly_demise,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import LANCE_RULE_ID
from warhammer40k_core.geometry.pose import Pose


def _descriptor(family: CoreAbilityFamily, *parameters: str) -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id=f"order97:{family.value}",
        name=family.value.replace("_", " ").title(),
        source_id=f"order97:source:{family.value}",
        source_kind=CatalogAbilitySourceKind.CORE,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        effect_description="Source-backed core-family fixture.",
        parameter_tokens=parameters,
    )


def _replace_unit(state: GameState, replacement: UnitInstance) -> None:
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                replacement if unit.unit_instance_id == replacement.unit_instance_id else unit
                for unit in army.units
            ),
        )
        for army in state.army_definitions
    ]


@pytest.mark.parametrize("token", ["1", "D3", "D6"])
def test_deadly_demise_numeric_instances_share_family(token: str) -> None:
    _, state, _ = ability_presence_fixture(embarked=False)
    unit = state.army_definitions[0].units[0]
    unit = replace(unit, datasheet_abilities=(_descriptor(CoreAbilityFamily.DEADLY_DEMISE, token),))
    assert unit_has_deadly_demise(unit)
    profile = deadly_demise_profile_for_unit(unit)
    assert profile is not None
    assert profile.mortal_wounds_token == token


@pytest.mark.parametrize("all_components", [False, True])
def test_attached_deep_strike_and_infiltrators_require_every_component(
    all_components: bool,
) -> None:
    config, state, _ = ability_presence_fixture(embarked=False)
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    for component in view.components:
        if component.unit.unit_instance_id == "army-alpha:leader" or all_components:
            _replace_unit(
                state,
                replace(
                    component.unit,
                    datasheet_abilities=(
                        *component.unit.datasheet_abilities,
                        _descriptor(CoreAbilityFamily.DEEP_STRIKE),
                        _descriptor(CoreAbilityFamily.INFILTRATORS),
                    ),
                ),
            )
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    assert rules_unit_has_infiltrators(state=state, view=view) is all_components
    context = reserve_legality_context_for_player(state=state, config=config, player_id="player-a")
    option = _deep_strike_option_for_unit(state=state, config=config, context=context, unit=view)
    assert (option is not None) is all_components


@pytest.mark.parametrize("all_components", [False, True])
def test_attached_scouts_require_every_component(all_components: bool) -> None:
    config, state, _ = ability_presence_fixture(embarked=False)
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    for component in view.components:
        if component.unit.unit_instance_id == "army-alpha:leader" or all_components:
            _replace_unit(
                state,
                replace(
                    component.unit,
                    datasheet_abilities=(
                        *component.unit.datasheet_abilities,
                        _descriptor(CoreAbilityFamily.SCOUTS, "6"),
                    ),
                ),
            )
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    instances = scout_ability_instances_for_rules_unit(
        state=state, view=view, army_catalog=config.army_catalog
    )
    assert bool(instances) is all_components
    if all_components:
        assert {instance.model_instance_id for instance in instances} == {
            model.model_instance_id for model in view.alive_models()
        }


def test_lone_operative_activates_after_last_nonqualifying_component_dies() -> None:
    _, state, _ = ability_presence_fixture(embarked=False)
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    leader = next(
        component.unit
        for component in view.components
        if component.unit.unit_instance_id == "army-alpha:leader"
    )
    _replace_unit(
        state,
        replace(
            leader,
            datasheet_abilities=(
                *leader.datasheet_abilities,
                _descriptor(CoreAbilityFamily.LONE_OPERATIVE, "12"),
            ),
        ),
    )
    view = rules_unit_view_by_id(state=state, unit_instance_id=leader.unit_instance_id)
    assert lone_operative_profile_for_rules_unit(view) is None
    bodyguard = next(
        component.unit
        for component in view.components
        if component.unit.unit_instance_id == "army-alpha:passengers"
    )
    for model in bodyguard.own_models:
        destroy_model_by_rule(state=state, model_instance_id=model.model_instance_id)
    current = rules_unit_view_by_id(state=state, unit_instance_id=leader.unit_instance_id)
    profile = lone_operative_profile_for_rules_unit(current)
    assert profile is not None
    assert profile.range_inches == 12


def test_attached_weapon_grant_expires_when_its_source_component_dies() -> None:
    config, state, _ = ability_presence_fixture(
        embarked=False,
        ability_text=(
            "While this model is leading a unit, ranged weapons equipped by models "
            "in that unit have the [LETHAL HITS] ability."
        ),
    )
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    leader = next(
        component.unit
        for component in view.components
        if component.unit.unit_instance_id == "army-alpha:leader"
    )
    # The source and consumer are different physical components of the attached unit.
    records = catalog_ability_records_from_catalog(config.army_catalog)
    runtime = CatalogWeaponKeywordGrantRuntime(
        {player: AbilityCatalogIndex.from_records(records) for player in state.player_ids},
        tuple(state.army_definitions),
    )
    passenger = next(
        component.unit
        for component in view.components
        if component.unit.unit_instance_id == "army-alpha:passengers"
    )
    profile = next(
        w for w in config.army_catalog.wargear if w.wargear_id == "core-bolt-rifle"
    ).weapon_profiles[0]
    context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=view.unit_instance_id,
        attacker_model_instance_id=passenger.own_models[0].model_instance_id,
        target_unit_instance_id=state.army_definitions[1].units[0].unit_instance_id,
        weapon_profile=profile,
    )
    assert WeaponKeyword.LETHAL_HITS in runtime.weapon_profile_modifier(context).keywords
    destroy_model_by_rule(state=state, model_instance_id=leader.own_models[0].model_instance_id)
    assert WeaponKeyword.LETHAL_HITS not in runtime.weapon_profile_modifier(context).keywords


def test_extra_attacks_only_model_can_select_its_weapon() -> None:
    catalog, ruleset, scenario, attacker, target, _ = melee_fixture(
        include_extra_attacks=True, target_b_pose=Pose.at(30, 30)
    )
    attacker = replace(
        attacker,
        own_models=tuple(
            replace(model, wargear_ids=("core-extra-blade",)) for model in attacker.own_models
        ),
        wargear_selections=tuple(
            replace(selection, wargear_ids=("core-extra-blade",))
            for selection in attacker.wargear_selections
        ),
    )
    scenario = replace(
        scenario, armies=(replace(scenario.armies[0], units=(attacker,)), scenario.armies[1])
    )
    request = melee_request(catalog=catalog, ruleset=ruleset, scenario=scenario, attacker=attacker)
    proposal = melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-extra-blade",
                weapon_profile_id="core-extra-blade:standard",
                target_allocations=(MeleeTargetAllocation(target.unit_instance_id),),
            ),
        ),
    )
    validation = validate_melee_declaration_rules(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=proposal,
        army_catalog=catalog,
    )
    assert validation.is_valid
    sequence = melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("order97-extra-only"),
        sequence_id="order97-extra-only",
    )
    assert sequence.attack_pools[0].wargear_id == "core-extra-blade"


def test_lance_without_charge_has_no_wound_bonus() -> None:
    catalog, ruleset, scenario, attacker, target, _ = melee_fixture(
        leader_keywords=(WeaponKeyword.LANCE,), target_b_pose=Pose.at(30, 30)
    )
    request = melee_request(catalog=catalog, ruleset=ruleset, scenario=scenario, attacker=attacker)
    proposal = melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(target.unit_instance_id),),
            ),
        ),
    )
    sequence = melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("order97-no-charge"),
        sequence_id="order97-no-charge",
    )
    assert LANCE_RULE_ID not in sequence.attack_pools[0].targeting_rule_ids


def test_emergency_disembark_forbids_a_charge_after_accepted_setup() -> None:
    from tests.order60_emergency_disembark_helpers import (
        order60_emergency_session,
        order60_passenger_placement,
        order60_resolve_emergency,
    )

    session = order60_emergency_session()
    result = order60_resolve_emergency(session, order60_passenger_placement(session))
    assert result.is_valid
    assert result.disembarked_unit_state is not None
    assert result.disembarked_unit_state.can_declare_charge is False


@pytest.mark.parametrize("mode", ["combat_disembark", "emergency_disembark"])
def test_disembark_six_inch_modes_reject_passenger_beyond_band(mode: str) -> None:
    from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID
    from tests.order60_emergency_disembark_helpers import (
        order60_emergency_session,
        order60_passenger_placement,
    )

    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.transports import (
        DisembarkModeKind,
        DisembarkSelection,
        TransportMovementStatus,
        TransportOperationViolationCode,
        resolve_disembark_internal,
    )

    session = order60_emergency_session()
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    placement = order60_passenger_placement(session)
    placement = replace(
        placement,
        model_placements=tuple(
            replace(row, pose=Pose.at(row.pose.position.x + 9, row.pose.position.y))
            for row in placement.model_placements
        ),
    )
    result = resolve_disembark_internal(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        cargo_state=state.transport_cargo_states[0],
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=PASSENGER_ID,
            transport_unit_instance_id=TRANSPORT_ID,
            attempted_placement=placement,
            disembark_mode=DisembarkModeKind(mode),
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=unit_by_id(state=state, unit_instance_id=PASSENGER_ID),
        transport_placement=scenario.battlefield_state.unit_placement_by_id(TRANSPORT_ID),
        turn_player_id="player-a",
        require_started_phase_embarked=False,
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        terrain_features=(),
        objective_markers=(),
    )
    assert not result.is_valid
    assert TransportOperationViolationCode.DISEMBARK_DISTANCE in {
        row.violation_code for row in result.violations
    }
    assert result.transition_batch is None


def test_embark_rejects_the_datasheet_passenger_keyword_restriction() -> None:
    from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID, disembark_session

    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.transports import (
        EmbarkSelection,
        TransportMovementStatus,
        TransportOperationViolationCode,
        resolve_embark,
    )

    session = disembark_session(embarked_passenger=False)
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    cargo = state.transport_cargo_states[0]
    cargo = replace(
        cargo, capacity_profile=replace(cargo.capacity_profile, allowed_keywords=("MONSTER",))
    )
    result = resolve_embark(
        scenario=scenario,
        cargo_state=cargo,
        selection=EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=PASSENGER_ID,
            transport_unit_instance_id=TRANSPORT_ID,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
        ),
        unit_placement=scenario.battlefield_state.unit_placement_by_id(PASSENGER_ID),
        transport_placement=scenario.battlefield_state.unit_placement_by_id(TRANSPORT_ID),
        movement_history=(),
        turn_player_id="player-a",
    )
    assert not result.is_valid
    assert any(
        row.violation_code is TransportOperationViolationCode.CAPACITY_EXCEEDED
        and row.message == "Transport capacity profile does not allow this unit."
        for row in result.violations
    )
    assert result.transition_batch is None


def test_strategic_reserve_cap_counts_cargo_but_does_not_limit_battle_entry() -> None:
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.reserves import (
        ReserveKind,
        ReserveOrigin,
        ReserveState,
        StrategicReserveDeclaration,
    )

    allowed = StrategicReserveDeclaration(
        player_id="player-a",
        unit_instance_id="army-alpha:transport",
        reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
        declared_during_step="declare_battle_formations",
        unit_points=450,
        embarked_unit_points=50,
        points_limit=500,
    )
    assert allowed.unit_points + allowed.embarked_unit_points == 500
    with pytest.raises(GameLifecycleError, match="exceeds points limit"):
        replace(allowed, embarked_unit_points=51)
    during = ReserveState.entered_during_battle(
        player_id="player-a",
        unit_instance_id=allowed.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        battle_round=2,
        phase=BattlePhase.MOVEMENT,
        points_contribution=501,
    )
    assert during.points_contribution > allowed.points_limit
    assert during.is_unarrived
    assert ReserveState.from_payload(during.to_payload()) == during


@pytest.mark.parametrize(
    "mode",
    [
        "tactical_disembark",
        "rapid_disembark",
        "combat_disembark",
        "emergency_disembark",
        "assault_disembark",
        "shock_disembark",
    ],
)
def test_every_disembark_mode_records_the_shared_turn_state(mode: str) -> None:
    from warhammer40k_core.engine.transports import (
        DisembarkedUnitState,
        DisembarkModeKind,
        TransportMovementStatus,
        TransportRestrictionOverride,
        TransportRestrictionOverrideKind,
    )

    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    selected_mode = DisembarkModeKind(mode)
    overrides: tuple[TransportRestrictionOverride, ...] = ()
    if selected_mode in {DisembarkModeKind.ASSAULT_DISEMBARK, DisembarkModeKind.SHOCK_DISEMBARK}:
        overrides = (
            TransportRestrictionOverride(
                override_kind=TransportRestrictionOverrideKind.ALLOW_ASSAULT_DISEMBARK
                if selected_mode is DisembarkModeKind.ASSAULT_DISEMBARK
                else TransportRestrictionOverrideKind.ALLOW_SHOCK_DISEMBARK,
                source_rule_id="order97:disembark-permission",
            ),
        )
    if selected_mode is DisembarkModeKind.EMERGENCY_DISEMBARK:
        record = DisembarkedUnitState.for_destroyed_transport(
            player_id="player-a",
            battle_round=state.battle_round,
            turn_player_id="player-a",
            unit_instance_id=units["intercessor-1"].unit_instance_id,
            transport_unit_instance_id="army-alpha:transport",
            disembark_mode=selected_mode,
        )
    else:
        record = DisembarkedUnitState.for_mode(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=units["intercessor-1"].unit_instance_id,
            transport_unit_instance_id="army-alpha:transport",
            disembark_mode=selected_mode,
            transport_movement_status=TransportMovementStatus.NORMAL_MOVE
            if selected_mode
            in {
                DisembarkModeKind.RAPID_DISEMBARK,
                DisembarkModeKind.ASSAULT_DISEMBARK,
                DisembarkModeKind.SHOCK_DISEMBARK,
            }
            else TransportMovementStatus.NOT_MOVED,
            restriction_overrides=overrides,
        )
    state.record_disembarked_unit_state(record)
    assert (
        state.disembarked_unit_state_for_unit(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=units["intercessor-1"].unit_instance_id,
        )
        == record
    )
    assert DisembarkedUnitState.from_payload(record.to_payload()) == record


def test_roster_rejects_a_warlord_without_the_army_faction_keyword() -> None:
    from warhammer40k_core.engine.army_mustering import WarlordSelection, validate_roster_legality

    config, _, _ = ability_presence_fixture(embarked=False)
    request = replace(
        config.army_muster_requests[0],
        warlord_selection=WarlordSelection(
            unit_selection_id="leader",
            model_profile_id="core-character-leader",
            model_index=1,
            source_id="order97:warlord",
        ),
    )
    catalog = replace(
        config.army_catalog,
        factions=(
            *config.army_catalog.factions,
            replace(
                config.army_catalog.factions[0],
                faction_id="other-faction",
                faction_keywords=("OTHER_FACTION",),
                army_rule_ids=(),
            ),
        ),
        datasheets=tuple(
            replace(sheet, keywords=replace(sheet.keywords, faction_keywords=("OTHER_FACTION",)))
            if sheet.datasheet_id == "core-character-leader"
            else sheet
            for sheet in config.army_catalog.datasheets
        ),
    )
    report = validate_roster_legality(catalog=catalog, request=request)
    assert {"unit_selection_invalid", "warlord_unknown_unit"} <= {
        row.violation_code for row in report.violations
    }


def test_roster_unit_points_survive_mustering_and_round_trip() -> None:
    from warhammer40k_core.engine.army_mustering import ArmyDefinition, muster_army
    from warhammer40k_core.engine.roster_points import RosterUnitPointValue

    config, _, _ = ability_presence_fixture(embarked=False)
    request = config.army_muster_requests[0]
    points = tuple(
        RosterUnitPointValue(
            unit_selection_id=selection.unit_selection_id,
            points=100,
            source_id="order97:unit-points",
        )
        for selection in sorted(
            request.unit_selections, key=lambda selection: selection.unit_selection_id
        )
    )
    request = replace(request, unit_points=points)
    army = muster_army(catalog=config.army_catalog, request=request)
    assert army.unit_points == points
    assert ArmyDefinition.from_payload(army.to_payload()).unit_points == points


def test_revived_model_keeps_spent_physical_one_shot_weapon() -> None:
    from tests.order90_revival_helpers import offboard_scene

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.damage_allocation import model_by_id
    from warhammer40k_core.engine.healing import resolve_healing_until_blocked
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.weapon_instances import equipped_weapon_instances_for_model

    lifecycle, effect, model_id = offboard_scene()
    state = lifecycle.state
    assert state is not None
    model = model_by_id(state=state, model_instance_id=model_id)
    weapon = equipped_weapon_instances_for_model(model)[0]
    profile = next(
        item
        for item in lifecycle.config.army_catalog.wargear
        if item.wargear_id == weapon.wargear_id
    ).weapon_profiles[0]
    identity = {
        "model_instance_id": model_id,
        "weapon_instance_id": weapon.weapon_instance_id,
        "wargear_id": weapon.wargear_id,
        "weapon_profile_id": profile.profile_id,
    }
    state.record_one_shot_weapon_selected(
        **identity, source_phase=BattlePhase.SHOOTING, selection_id="order97:prior-shot"
    )
    assert not state.one_shot_weapon_available(**identity)
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="order97:revive-spent",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert model_by_id(state=state, model_instance_id=model_id).is_alive
    assert not state.one_shot_weapon_available(**identity)
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    assert restored.lifecycle.state is not None
    assert not restored.lifecycle.state.one_shot_weapon_available(**identity)


def test_new_unit_identity_has_fresh_one_shot_weapons() -> None:
    from warhammer40k_core.engine.unit_factory import UnitFactory
    from warhammer40k_core.engine.weapon_instances import equipped_weapon_instances_for_model

    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    original = units["intercessor-1"]
    weapon = equipped_weapon_instances_for_model(original.own_models[0])[0]
    profile = next(
        item
        for item in lifecycle.config.army_catalog.wargear
        if item.wargear_id == weapon.wargear_id
    ).weapon_profiles[0]
    original_identity = {
        "model_instance_id": original.own_models[0].model_instance_id,
        "weapon_instance_id": weapon.weapon_instance_id,
        "wargear_id": weapon.wargear_id,
        "weapon_profile_id": profile.profile_id,
    }
    state.record_one_shot_weapon_selected(
        **original_identity, source_phase=BattlePhase.SHOOTING, selection_id="order97:original-shot"
    )
    selection = next(
        row
        for row in lifecycle.config.army_muster_requests[0].unit_selections
        if row.unit_selection_id == "intercessor-1"
    )
    added = UnitFactory(catalog=lifecycle.config.army_catalog).instantiate_unit(
        army_id="army-alpha",
        selection=replace(selection, unit_selection_id="new-unit"),
        datasheet=lifecycle.config.army_catalog.datasheet_by_id(selection.datasheet_id),
    )
    added_weapon = equipped_weapon_instances_for_model(added.own_models[0])[0]
    assert added_weapon.weapon_instance_id != weapon.weapon_instance_id
    assert state.one_shot_weapon_available(
        model_instance_id=added.own_models[0].model_instance_id,
        weapon_instance_id=added_weapon.weapon_instance_id,
        wargear_id=added_weapon.wargear_id,
        weapon_profile_id=profile.profile_id,
    )
    assert not state.one_shot_weapon_available(**original_identity)


@pytest.mark.parametrize("source_scope", ["bodyguard", "bearer"])
def test_attached_grants_follow_the_living_bodyguard_or_equipped_bearer(source_scope: str) -> None:
    from warhammer40k_core.engine.damage_allocation import unit_by_id

    config, state, _ = ability_presence_fixture(
        embarked=False,
        ability_text=(
            "Ranged weapons equipped by models in this unit have the [LETHAL HITS] ability."
        ),
    )
    leader = unit_by_id(state=state, unit_instance_id="army-alpha:leader")
    bodyguard = unit_by_id(state=state, unit_instance_id="army-alpha:passengers")
    descriptor = next(
        row for row in leader.datasheet_abilities if row.ability_id == "p01c-test-ability"
    )
    if source_scope == "bearer":
        descriptor = replace(
            descriptor,
            source_kind=CatalogAbilitySourceKind.WARGEAR,
            source_wargear_id="core-leader-blade",
        )
        bodyguard = replace(
            bodyguard,
            own_models=(
                replace(
                    bodyguard.own_models[0],
                    wargear_ids=(*bodyguard.own_models[0].wargear_ids, "core-leader-blade"),
                ),
                *bodyguard.own_models[1:],
            ),
        )
    leader = replace(
        leader,
        datasheet_abilities=tuple(
            row for row in leader.datasheet_abilities if row.ability_id != descriptor.ability_id
        ),
    )
    bodyguard = replace(bodyguard, datasheet_abilities=(*bodyguard.datasheet_abilities, descriptor))
    _replace_unit(state, leader)
    _replace_unit(state, bodyguard)
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(sheet, abilities=bodyguard.datasheet_abilities)
            if sheet.datasheet_id == bodyguard.datasheet_id
            else replace(sheet, abilities=leader.datasheet_abilities)
            if sheet.datasheet_id == leader.datasheet_id
            else sheet
            for sheet in config.army_catalog.datasheets
        ),
    )
    records = catalog_ability_records_from_catalog(catalog)
    runtime = CatalogWeaponKeywordGrantRuntime(
        {player: AbilityCatalogIndex.from_records(records) for player in state.player_ids},
        tuple(state.army_definitions),
    )
    view = rules_unit_view_by_id(state=state, unit_instance_id=leader.unit_instance_id)
    profile = next(
        item for item in catalog.wargear if item.wargear_id == "core-bolt-rifle"
    ).weapon_profiles[0]
    context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=view.unit_instance_id,
        attacker_model_instance_id=leader.own_models[0].model_instance_id,
        target_unit_instance_id=state.army_definitions[1].units[0].unit_instance_id,
        weapon_profile=profile,
    )
    assert WeaponKeyword.LETHAL_HITS in runtime.weapon_profile_modifier(context).keywords
    casualties = bodyguard.own_models if source_scope == "bodyguard" else bodyguard.own_models[:1]
    for model in casualties:
        destroy_model_by_rule(state=state, model_instance_id=model.model_instance_id)
    assert WeaponKeyword.LETHAL_HITS not in runtime.weapon_profile_modifier(context).keywords
    assert leader.own_models[0].is_alive
    if source_scope == "bearer":
        assert (
            len(
                unit_by_id(
                    state=state, unit_instance_id=bodyguard.unit_instance_id
                ).alive_own_models()
            )
            == 4
        )


def test_revived_source_becomes_available_to_ability_consumers_again() -> None:
    from tests.order90_revival_helpers import offboard_scene

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.ability_presence import active_ability_model_ids_for_unit
    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.healing import resolve_healing_until_blocked
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    lifecycle, effect, model_id = offboard_scene(revive_leader=True)
    state = lifecycle.state
    assert state is not None
    source_unit = unit_by_id(state=state, unit_instance_id="army-alpha:leader")
    assert active_ability_model_ids_for_unit(state=state, unit=source_unit) == ()
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="order97:revive-ability-source",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert active_ability_model_ids_for_unit(state=state, unit=source_unit) == (model_id,)


def test_committed_flight_grants_general_terrain_transit() -> None:
    from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
    from warhammer40k_core.engine.movement_legality import MovementCapabilitySet

    for mode in (
        MovementMode.NORMAL,
        MovementMode.ADVANCE,
        MovementMode.FALL_BACK,
        MovementMode.CHARGE,
    ):
        capabilities = MovementCapabilitySet.from_keywords(
            ("FLY",),
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            movement_mode=mode,
            take_to_the_skies=True,
        )
        assert capabilities.can_move_through_terrain
        assert capabilities.ignores_vertical_distance


@pytest.mark.parametrize("keyword", ["MONSTER", "VEHICLE"])
def test_large_models_can_mix_close_quarters_and_ordinary_weapon_declarations(keyword: str) -> None:
    from tests.unit_keyword_helpers import with_unit_keywords

    from warhammer40k_core.engine.phases.shooting_declaration_validation import (
        _validate_model_pistol_exclusivity,
    )
    from warhammer40k_core.engine.shooting_types import ShootingType
    from warhammer40k_core.engine.weapon_declaration import WeaponDeclaration
    from warhammer40k_core.engine.weapon_instances import equipped_weapon_instances_for_model

    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    unit = with_unit_keywords(units["intercessor-1"], keywords=(keyword,))
    _replace_unit(state, unit)
    profile = _first_weapon_profile(lifecycle, unit)
    declaration = WeaponDeclaration(
        weapon_instance_id=equipped_weapon_instances_for_model(unit.own_models[0])[
            0
        ].weapon_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        wargear_id="core-bolt-rifle",
        weapon_profile_id=profile.profile_id,
        target_unit_instance_id=units["enemy"].unit_instance_id,
    )
    observed: dict[tuple[str, str], bool] = {}
    for selected_profile in (profile, replace(profile, keywords=(WeaponKeyword.CLOSE_QUARTERS,))):
        validation = _validate_model_pistol_exclusivity(
            state=state,
            selected_unit=unit,
            declaration=declaration,
            weapon_profile=selected_profile,
            model_pistol_declaration_kind=observed,
            proposal_request_id="order97:mixed-weapons",
        )
        assert validation is None


def test_firing_deck_requires_shooting_phase_and_never_changes_equipped_weapons() -> None:
    from tests.firing_deck_helpers import TRANSPORT, submit_firing_deck
    from tests.optional_firing_deck_helpers import optional_firing_deck_session
    from tests.optional_shooting_helpers import finish_selected_weapons

    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.firing_deck_restrictions import record_firing_deck_restriction
    from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind

    session, request, proposal = optional_firing_deck_session(contribute=True)
    state = session.lifecycle.state
    assert state is not None
    before = unit_by_id(state=state, unit_instance_id=TRANSPORT).own_models[0].wargear_ids
    status = submit_firing_deck(session, request, proposal)
    assert status.status_kind is not LifecycleStatusKind.INVALID
    finish_selected_weapons(session, "order97:finish-deck")
    assert unit_by_id(state=state, unit_instance_id=TRANSPORT).own_models[0].wargear_ids == before
    assert any(
        event.event_type == "attack_sequence_completed"
        for event in session.lifecycle.decision_controller.event_log.records
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    with pytest.raises(GameLifecycleError, match="owner's Shooting phase"):
        record_firing_deck_restriction(
            state=state,
            transport_unit_instance_id=TRANSPORT,
            embarked_unit_instance_ids=("army-alpha:passenger-1",),
            result_id="order97:wrong-window",
        )


@pytest.mark.parametrize("elevated_target", [False, True])
def test_plunging_fire_requires_a_ground_level_target(elevated_target: bool) -> None:
    from tests.phase13b_shooting_declaration_helpers import (
        _scenario_with_replaced_unit,
        _scenario_with_unit_pose,
    )
    from tests.unit_keyword_helpers import with_unit_keywords

    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.shooting_targets import (
        PLUNGING_FIRE_RULE_ID,
        shooting_target_candidates_for_unit,
    )

    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    attacker = with_unit_keywords(
        units["intercessor-1"], keywords=(*units["intercessor-1"].keywords, "TOWERING")
    )
    defender = units["enemy"]
    scenario = _scenario_with_replaced_unit(
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
        ),
        replacement=attacker,
    )
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=defender,
        army_id="army-beta",
        player_id="player-b",
        poses=tuple(
            Pose.at(20, 35 + i * 1.5, 3 if elevated_target else 0)
            for i in range(len(defender.own_models))
        ),
    )
    candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=attacker,
        weapon_profile=_first_weapon_profile(lifecycle, attacker),
        target_unit_ids=(defender.unit_instance_id,),
    )
    assert candidates[0].is_legal
    assert (PLUNGING_FIRE_RULE_ID in candidates[0].targeting_rule_ids) is (not elevated_target)


def test_scout_candidates_require_own_zone_and_have_only_one_action() -> None:
    from tests.phase13b_shooting_declaration_helpers import _unit_placement_at

    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, SetupStep
    from warhammer40k_core.engine.prebattle import (
        _validate_prebattle_state,  # pyright: ignore[reportPrivateUsage]
        scout_move_candidates_for_player,
    )
    from warhammer40k_core.engine.prebattle_records import (
        PreBattleActionKind,
        PreBattleActionRecord,
    )

    config, state, _ = ability_presence_fixture(embarked=False, attached=False)
    assert state.battlefield_state is not None
    assert state.mission_setup is not None
    unit = unit_by_id(state=state, unit_instance_id="army-alpha:leader")
    unit = replace(
        unit,
        datasheet_abilities=(*unit.datasheet_abilities, _descriptor(CoreAbilityFamily.SCOUTS, "6")),
    )
    _replace_unit(state, unit)
    zone = next(z for z in state.mission_setup.deployment_zones if z.player_id == "player-a")
    origin = Pose.at((zone.min_x + zone.max_x) / 2, (zone.min_y + zone.max_y) / 2)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(unit, army_id="army-alpha", player_id="player-a", poses=(origin,))
    )
    assert unit.unit_instance_id in {
        v.unit_instance_id
        for v in scout_move_candidates_for_player(
            state=state, army_catalog=config.army_catalog, player_id="player-a"
        )
    }
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            unit, army_id="army-alpha", player_id="player-a", poses=(Pose.at(30, 22),)
        )
    )
    assert unit.unit_instance_id not in {
        v.unit_instance_id
        for v in scout_move_candidates_for_player(
            state=state, army_catalog=config.army_catalog, player_id="player-a"
        )
    }
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(unit, army_id="army-alpha", player_id="player-a", poses=(origin,))
    )
    state.prebattle_action_records.append(
        PreBattleActionRecord(
            action_id="order97:scout",
            game_id=state.game_id,
            player_id="player-a",
            setup_step=SetupStep.RESOLVE_PREBATTLE_ACTIONS,
            action_kind=PreBattleActionKind.SCOUT_MOVE,
            source_rule_id="scouts",
            request_id="order97:request",
            result_id="order97:result",
            unit_instance_id=unit.unit_instance_id,
        )
    )
    assert unit.unit_instance_id not in {
        v.unit_instance_id
        for v in scout_move_candidates_for_player(
            state=state, army_catalog=config.army_catalog, player_id="player-a"
        )
    }
    with pytest.raises(GameLifecycleError, match="setup stage"):
        _validate_prebattle_state(state, SetupStep.RESOLVE_PREBATTLE_ACTIONS)
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = state.setup_sequence.index(SetupStep.DEPLOY_ARMIES)
    with pytest.raises(GameLifecycleError, match="setup step drift"):
        _validate_prebattle_state(state, SetupStep.RESOLVE_PREBATTLE_ACTIONS)


@pytest.mark.parametrize("distance", [8.0, 8.01])
def test_deep_strike_enemy_zone_still_requires_more_than_eight_inches(distance: float) -> None:
    from tests.phase10p_reserves_helpers import (
        battle_state_with_reserve,
        single_model_reserve_placement,
    )
    from tests.phase13b_shooting_declaration_helpers import _unit_placement_at
    from tests.unit_keyword_helpers import with_unit_keywords

    from warhammer40k_core.core.deployment_zones import DeploymentZone
    from warhammer40k_core.engine.battlefield_state import (
        BattlefieldPlacementKind,
        BattlefieldScenario,
    )
    from warhammer40k_core.engine.reserves import (
        ReserveKind,
        ReservePlacementViolationCode,
        resolve_reserve_arrival,
    )

    state, scenario, reserve, unit = battle_state_with_reserve(reserve_base_diameter_mm=32)
    unit = with_unit_keywords(unit, keywords=(*unit.keywords, "DEEP_STRIKE"))
    enemy = scenario.armies[1].units[0]
    enemy_diameter = enemy.own_models[0].base_size.diameter_mm
    assert enemy_diameter is not None
    enemy_radius = enemy_diameter / 25.4 / 2
    radius = 32 / 25.4 / 2
    battlefield = scenario.battlefield_state.with_unit_placement(
        _unit_placement_at(
            enemy,
            army_id=scenario.armies[1].army_id,
            player_id="player-b",
            poses=tuple(Pose.at(35 + i * 1.5, 22) for i in range(len(enemy.own_models))),
        )
    )
    scenario = BattlefieldScenario(
        armies=(
            replace(
                scenario.armies[0],
                units=tuple(
                    unit if u.unit_instance_id == unit.unit_instance_id else u
                    for u in scenario.armies[0].units
                ),
            ),
            scenario.armies[1],
        ),
        battlefield_state=battlefield,
    )
    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        reserve_state=replace(reserve, reserve_kind=ReserveKind.DEEP_STRIKE),
        attempted_placement=single_model_reserve_placement(
            reserve_unit=unit, pose=Pose.at(35 - enemy_radius - radius - distance, 22)
        ),
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
        enemy_deployment_zones=(
            DeploymentZone.rectangle(
                "order97:enemy-zone", "player-b", min_x=20, min_y=10, max_x=44, max_y=30
            ),
        ),
    )
    assert result.is_valid is (distance > 8)
    assert (
        ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE
        in {v.violation_code for v in result.violations}
    ) is (distance == 8)


def test_melta_keeps_declared_half_range_when_target_geometry_later_changes() -> None:
    from typing import cast

    from tests.phase13b_shooting_declaration_helpers import (
        _catalog_with_extra_bolt_profile,
        _decision_request,
        _last_event_payload,
        _proposal_from_request,
        _select_shooting_unit_and_type,
        _submit_payload,
        _unit_placement_at,
        _weapon_profile_by_wargear,
    )

    from warhammer40k_core.core.weapon_profiles import AbilityDescriptor
    from warhammer40k_core.engine.attack_sequence_hit_wound import _melta_damage_modifier
    from warhammer40k_core.engine.weapon_declaration import (
        RangedAttackPool,
        RangedAttackPoolPayload,
    )

    profile = replace(
        _weapon_profile_by_wargear(
            wargear_id="core-bolt-rifle", weapon_profile_id="core-bolt-rifle:standard"
        ),
        profile_id="order97:melta",
        keywords=(WeaponKeyword.MELTA,),
        abilities=(AbilityDescriptor.melta(2),),
    )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(19, 35),
        catalog=_catalog_with_extra_bolt_profile(profile),
    )
    selection = _decision_request(lifecycle.advance_until_decision_or_terminal())
    request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="order97:select-melta",
    )
    proposal = _proposal_from_request(
        request=request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_profile_id=profile.profile_id,
    )
    _submit_payload(
        lifecycle, request=request, payload=proposal.to_payload(), result_id="order97:declare-melta"
    )
    accepted = _last_event_payload(lifecycle, "shooting_declaration_accepted")
    pools = cast(list[RangedAttackPoolPayload], accepted["attack_pools"])
    pool = RangedAttackPool.from_payload(pools[0])
    assert _melta_damage_modifier(pool, target_keywords=units["enemy"].keywords) == 2
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    target = units["enemy"]
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            target,
            army_id="army-beta",
            player_id="player-b",
            poses=tuple(Pose.at(50, 35 + i * 1.5) for i in range(len(target.own_models))),
        )
    )
    assert _melta_damage_modifier(pool, target_keywords=target.keywords) == 2


@pytest.mark.parametrize("distance", [8.0, 8.01])
def test_infiltrators_enemy_model_distance_is_independent_of_zone(distance: float) -> None:
    from tests.phase13b_shooting_declaration_helpers import _unit_placement_at

    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.deployment import (
        DeploymentPlacementViolation,
        DeploymentPlacementViolationCode,
    )
    from warhammer40k_core.engine.deployment_geometry import append_geometry_violations

    _, state, _ = ability_presence_fixture(embarked=False, attached=False)
    assert state.battlefield_state is not None
    assert state.mission_setup is not None
    unit = unit_by_id(state=state, unit_instance_id="army-alpha:leader")
    unit = replace(
        unit,
        datasheet_abilities=(
            *unit.datasheet_abilities,
            _descriptor(CoreAbilityFamily.INFILTRATORS),
        ),
    )
    _replace_unit(state, unit)
    enemy = state.army_definitions[1].units[0]
    own_diameter = unit.own_models[0].base_size.diameter_mm
    enemy_diameter = enemy.own_models[0].base_size.diameter_mm
    assert own_diameter is not None
    assert enemy_diameter is not None
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            enemy,
            army_id=state.army_definitions[1].army_id,
            player_id="player-b",
            poses=tuple(Pose.at(40 + i * 1.5, 22) for i in range(len(enemy.own_models))),
        )
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            unit,
            army_id="army-alpha",
            player_id="player-a",
            poses=(Pose.at(40 - (own_diameter + enemy_diameter) / 25.4 / 2 - distance, 22),),
        )
    )
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
    )
    violations: list[DeploymentPlacementViolation] = []
    append_geometry_violations(
        violations=violations,
        state=state,
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        view=rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id),
        models=tuple(
            m
            for m in scenario.placed_geometry_models()
            if m.model_id == unit.own_models[0].model_instance_id
        ),
        deployment_zones=tuple(
            z for z in state.mission_setup.deployment_zones if z.player_id == "player-a"
        ),
    )
    assert (
        DeploymentPlacementViolationCode.INFILTRATORS_ENEMY_UNIT_DISTANCE
        in {v.violation_code for v in violations}
    ) is (distance == 8)


def test_deadly_demise_rolls_random_damage_separately_for_each_target() -> None:
    from tests.phase13b_shooting_declaration_helpers import _fixed_roll_result

    from warhammer40k_core.engine.attack_sequence_model import deadly_demise_mortal_wounds_roll_spec
    from warhammer40k_core.engine.damage_allocation import (
        DestructionReactionKind,
        DestructionReactionSource,
    )
    from warhammer40k_core.engine.deadly_demise import deadly_demise_mortal_wounds_for_target

    source = DestructionReactionSource(
        source_id="order97:demise",
        source_rule_id="order97:demise",
        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
        optional=False,
        payload={"trigger_roll_threshold": 6, "range_inches": 6.0, "mortal_wounds": {"kind": "d6"}},
    )
    targets = ("army-alpha:intercessor-1", "army-alpha:intercessor-2")
    manager = DiceRollManager(
        "order97:demise",
        injected_results=tuple(
            _fixed_roll_result(
                roll_id=f"order97:demise-{i}",
                spec=deadly_demise_mortal_wounds_roll_spec(
                    source=source, player_id="player-b", target_unit_instance_id=target, sides=6
                ),
                value=value,
            )
            for i, (target, value) in enumerate(zip(targets, (1, 6), strict=True))
        ),
    )
    results = [
        deadly_demise_mortal_wounds_for_target(
            manager=manager,
            source=source,
            descriptor={"mortal_wounds": {"kind": "d6"}},
            player_id="player-b",
            target_unit_instance_id=target,
        )
        for target in targets
    ]
    assert [amount for amount, _ in results] == [1, 6]
    assert results[0][1] != results[1][1]


@pytest.mark.parametrize("distance", [6.0, 6.01])
def test_deadly_demise_target_query_uses_the_six_inch_base_boundary(distance: float) -> None:
    from tests.phase13b_shooting_declaration_helpers import _unit_placement_at

    from warhammer40k_core.engine.deadly_demise import deadly_demise_target_unit_ids

    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    source = units["enemy"]
    target = units["intercessor-1"]
    source_diameter = source.own_models[0].base_size.diameter_mm
    target_diameter = target.own_models[0].base_size.diameter_mm
    assert source_diameter is not None
    assert target_diameter is not None
    target_x = 5 + (source_diameter + target_diameter) / 50.8 + distance
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            source,
            army_id="army-beta",
            player_id="player-b",
            poses=tuple(Pose.at(5, 20 + i * 1.5) for i in range(len(source.own_models))),
        )
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            target,
            army_id="army-alpha",
            player_id="player-a",
            poses=tuple(Pose.at(target_x + i * 1.5, 20) for i in range(len(target.own_models))),
        )
    )
    targets = deadly_demise_target_unit_ids(
        state=state,
        source_model_instance_id=source.own_models[0].model_instance_id,
        range_inches=6,
        event_records=lifecycle.decision_controller.event_log.records,
    )
    assert (target.unit_instance_id in targets) is (distance == 6)


def test_engaged_emergency_fallback_uses_the_same_closest_pose_proof() -> None:
    from fractions import Fraction

    from warhammer40k_core.geometry.base import CircularBase
    from warhammer40k_core.geometry.emergency_setup_proof import (
        EmergencySetupQuery,
        emergency_setup_pose_exists,
    )
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    passenger = Model("order97:passenger", Pose.at(0, 0), CircularBase(0.5), ModelVolume(2))
    transport = Model("order97:transport", Pose.at(10, 10), CircularBase(2), ModelVolume(3))
    # A vertically separated enemy blocks Engagement Range across the whole setup band.
    enemy = Model("order97:enemy", Pose.at(10, 10, 4), CircularBase(12), ModelVolume(1))
    query = EmergencySetupQuery(
        passenger=passenger,
        transports=(transport,),
        blockers=(enemy,),
        enemies=(enemy,),
        partners=(),
        terrain=(),
        objective_disks=(),
        width=Fraction(30),
        depth=Fraction(30),
        neighbor_limit=Fraction(2),
        vertical_limit=Fraction(5),
        span_limit=Fraction(8),
        engagement=Fraction(1),
        engagement_vertical=Fraction(5),
        setup_distance=Fraction(6),
        oversized_distance=Fraction(1),
        ordinary_size_fit=True,
        require_unengaged=True,
        closer_than=None,
        closest_tolerance=Fraction("0.04"),
    )
    assert not emergency_setup_pose_exists(query)
    engaged = replace(query, require_unengaged=False)
    assert emergency_setup_pose_exists(engaged)
    assert emergency_setup_pose_exists(
        replace(engaged, closer_than=replace(passenger, pose=Pose.at(12.6, 10)))
    )
    assert not emergency_setup_pose_exists(
        replace(engaged, closer_than=replace(passenger, pose=Pose.at(12.5, 10)))
    )


def test_emergency_consumer_accepts_engaged_closest_setup_only_when_required() -> None:
    from tests.order60_emergency_disembark_helpers import (
        order60_emergency_session,
        order60_passenger_placement,
        order60_resolve_emergency,
    )
    from tests.phase13b_shooting_declaration_helpers import _unit_placement_at

    from warhammer40k_core.engine.transports import TransportOperationViolationCode

    session = order60_emergency_session()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    enemy = state.army_definitions[1].units[0]
    blocker = enemy.own_models[0]
    diameter = blocker.base_size.diameter_mm
    assert diameter is not None
    # An elevated enemy covers every legal ground setup pose in Engagement Range
    # without colliding with the passenger volumes. Other enemies remain far away.
    from warhammer40k_core.geometry.model_geometry import ModelGeometry

    base = replace(blocker.base_size, diameter_mm=18 * 25.4)
    blocker = replace(
        blocker,
        base_size=base,
        geometry=ModelGeometry.from_base_size(base, geometry_source_id="order97:engaging-blocker"),
    )
    enemy = replace(enemy, own_models=(blocker, *enemy.own_models[1:]))
    _replace_unit(state, enemy)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            enemy,
            army_id="army-beta",
            player_id="player-b",
            poses=(Pose.at(10, 10, 4), *(Pose.at(35, 30 + i * 1.5) for i in range(4))),
        )
    )
    closest = order60_passenger_placement(session)
    accepted = order60_resolve_emergency(session, closest)
    assert accepted.is_valid, accepted.violations
    farther = replace(
        closest,
        model_placements=tuple(
            replace(
                row,
                pose=Pose.at(
                    10 + 1.05 * (row.pose.position.x - 10),
                    10 + 1.05 * (row.pose.position.y - 10),
                ),
            )
            for row in closest.model_placements
        ),
    )
    rejected = order60_resolve_emergency(session, farther)
    assert not rejected.is_valid
    assert TransportOperationViolationCode.EMERGENCY_DISEMBARK_NOT_CLOSEST in {
        violation.violation_code for violation in rejected.violations
    }


@pytest.mark.parametrize("mode", ["rapid_disembark", "tactical_disembark"])
@pytest.mark.parametrize("distance", [2.99, 3.01])
def test_rapid_and_tactical_disembark_enforce_three_inch_setup_band(
    mode: str, distance: float
) -> None:
    from tests.order97_gap_probes_18_25 import disembark_band_resolution

    from warhammer40k_core.engine.transports import TransportOperationViolationCode

    result = disembark_band_resolution(mode, distance)
    assert result.is_valid is (distance < 3.0), result.violations
    assert (
        TransportOperationViolationCode.DISEMBARK_DISTANCE
        in {violation.violation_code for violation in result.violations}
    ) is (distance > 3.0)
