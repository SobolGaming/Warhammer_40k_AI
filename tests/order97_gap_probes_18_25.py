"""Reproducible observations of source-backed gaps found by the Order 97 audit.

Run with ``uv run --no-sync python -m tests.order97_gap_probes_18_25``.
These probes report current behavior; they do not redefine the source obligation.
"""

from __future__ import annotations

import json
from dataclasses import replace

from tests.phase15d_fight_resolution_helpers import melee_fixture, melee_proposal, melee_request
from warhammer40k_core.core.weapon_profiles import AbilityKind
from warhammer40k_core.engine.fight_resolution import (
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
    validate_melee_declaration_rules,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.transports import (
    DisembarkResolution,
    EmbarkSelection,
    TransportMovementStatus,
    TransportRestrictionOverride,
    TransportRestrictionOverrideKind,
)
from warhammer40k_core.engine.weapon_abilities import blast_attack_bonus
from warhammer40k_core.geometry.pose import Pose


def probe_extra_attacks() -> dict[str, object]:
    catalog, ruleset, scenario, attacker, target, _ = melee_fixture(
        include_extra_attacks=True, target_b_pose=Pose.at(30, 30)
    )
    attacker = replace(
        attacker,
        own_models=tuple(
            replace(model, wargear_ids=("core-leader-blade", "core-extra-blade"))
            for model in attacker.own_models
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
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
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
    return {
        "requirement_ids": ["24.11-mandatory-extra-weapons"],
        "source_row_ids": ["rule:24:24.11:1"],
        "owner": (
            "src/warhammer40k_core/engine/fight_weapon_selection.py:"
            "validate_melee_declaration_rules"
        ),
        "input": {
            "equipped_wargear": attacker.own_models[0].wargear_ids,
            "selected_wargear": ["core-leader-blade"],
            "available_wargear": [
                row["wargear_id"] for row in request.available_weapons if isinstance(row, dict)
            ],
        },
        "expected": {
            "is_valid": False,
            "reason": "The model must also declare its eligible Extra Attacks weapon.",
        },
        "observed": validation.to_payload(),
    }


def probe_parameterized_blast() -> dict[str, object]:
    return {
        "requirement_ids": ["24.05-blast-x-per-five"],
        "source_row_ids": ["rule:24:24.05:1"],
        "owner": "src/warhammer40k_core/engine/weapon_abilities.py:blast_attack_bonus",
        "input": {"base_attacks": 3, "blast_x": 2, "target_model_count": 12},
        "expected": {"total_attacks": 7, "parameterized_blast_descriptor": True},
        "observed": {
            "total_attacks": 3 + blast_attack_bonus(target_model_count=12),
            "parameterized_blast_descriptor": "blast"
            in tuple(str(kind.value) for kind in AbilityKind),
        },
    }


def probe_no_move_embark() -> dict[str, object]:
    rejection: str | None = None
    try:
        EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:passengers",
            transport_unit_instance_id="army-alpha:transport",
            movement_phase_action=TransportMovementStatus.NOT_MOVED,
            restriction_overrides=(
                TransportRestrictionOverride(
                    override_kind=TransportRestrictionOverrideKind.ALLOW_EMBARK_AFTER_DISEMBARK,
                    source_rule_id="order97:faq:no-move-embark-permission",
                ),
            ),
        )
    except GameLifecycleError as error:
        rejection = str(error)
    return {
        "requirement_ids": ["c2df3e97-f21e-4fc9-943e-37072c08c10e-aerialists-post-disembark"],
        "source_row_ids": ["faq:c2df3e97-f21e-4fc9-943e-37072c08c10e"],
        "owner": "src/warhammer40k_core/engine/transports.py:EmbarkSelection",
        "input": {"movement_phase_action": "not_moved", "explicit_post_disembark_permission": True},
        "expected": {"representable_without_invented_movement": True},
        "observed": {
            "representable_without_invented_movement": rejection is None,
            "rejection": rejection,
        },
        "qualification": (
            "This probes the Core permission contract. "
            "Loading the named faction ability is outside this Core audit."
        ),
    }


def probe_attack_sequence_grant_retention() -> dict[str, object]:
    from tests.phase13b_shooting_declaration_helpers import _attack_pool_for_test
    from tests.support.ability_presence_fixtures import ability_presence_fixture
    from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
    from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind
    from warhammer40k_core.core.weapon_profiles import DamageProfile, WeaponKeyword
    from warhammer40k_core.engine.abilities import AbilityCatalogIndex
    from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
    from warhammer40k_core.engine.attack_sequence import (
        AttackSequence,
        AttackSequenceEvent,
        AttackSequenceHooks,
        AttackSequenceStep,
        resolve_attack_sequence_until_blocked,
    )
    from warhammer40k_core.engine.catalog_rule_consumption import CatalogWeaponKeywordGrantRuntime
    from warhammer40k_core.engine.damage_allocation import model_by_id, unit_by_id
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext

    config, state, decisions = ability_presence_fixture(
        embarked=False,
        ability_text=(
            "Ranged weapons equipped by models in this unit have the [LETHAL HITS] ability."
        ),
    )
    leader = unit_by_id(state=state, unit_instance_id="army-alpha:leader")
    bodyguard = unit_by_id(state=state, unit_instance_id="army-alpha:passengers")
    original = next(
        row for row in leader.datasheet_abilities if row.ability_id == "p01c-test-ability"
    )
    descriptor = replace(
        original,
        source_kind=CatalogAbilitySourceKind.WARGEAR,
        source_wargear_id="core-leader-blade",
    )
    leader = replace(
        leader,
        datasheet_abilities=tuple(
            row for row in leader.datasheet_abilities if row.ability_id != descriptor.ability_id
        ),
    )
    bearer = replace(
        bodyguard.own_models[0],
        wargear_ids=(*bodyguard.own_models[0].wargear_ids, "core-leader-blade"),
        wounds_remaining=1,
    )
    bodyguard = replace(
        bodyguard,
        own_models=(bearer, *bodyguard.own_models[1:]),
        datasheet_abilities=(*bodyguard.datasheet_abilities, descriptor),
    )
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                leader
                if u.unit_instance_id == leader.unit_instance_id
                else bodyguard
                if u.unit_instance_id == bodyguard.unit_instance_id
                else u
                for u in army.units
            ),
        )
        for army in state.army_definitions
    ]
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
    profile = next(
        item for item in catalog.wargear if item.wargear_id == "core-bolt-rifle"
    ).weapon_profiles[0]
    view = rules_unit_view_by_id(state=state, unit_instance_id=leader.unit_instance_id)
    attacker = state.army_definitions[1].units[0]
    context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=view.unit_instance_id,
        attacker_model_instance_id=leader.own_models[0].model_instance_id,
        target_unit_instance_id=attacker.unit_instance_id,
        weapon_profile=profile,
    )
    before = WeaponKeyword.LETHAL_HITS in runtime.weapon_profile_modifier(context).keywords
    attack_profile = replace(
        profile,
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -10),
        damage_profile=DamageProfile.fixed(1),
    )
    observations: list[dict[str, object]] = []

    def observe(event: AttackSequenceEvent) -> AttackSequenceEvent:
        if (
            event.step is AttackSequenceStep.DAMAGE
            and not model_by_id(state=state, model_instance_id=bearer.model_instance_id).is_alive
        ):
            observations.append(
                {
                    "attack_index": event.attack_index,
                    "attack_count": 3,
                    "grant_active": WeaponKeyword.LETHAL_HITS
                    in runtime.weapon_profile_modifier(context).keywords,
                    "surviving_target_models": len(
                        rules_unit_view_by_id(
                            state=state, unit_instance_id=leader.unit_instance_id
                        ).alive_models()
                    ),
                }
            )
        return event

    remaining, _, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=config.ruleset_descriptor,
        attack_sequence=AttackSequence.start(
            sequence_id="order97:grant-retention",
            attacker_player_id="player-b",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=bodyguard,
                    weapon_profile=attack_profile,
                    attacks=3,
                    target_unit_instance_id=view.unit_instance_id,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        hooks=AttackSequenceHooks((observe,)),
        dice_manager=DiceRollManager("order97:grant-retention", event_log=decisions.event_log),
    )
    return {
        "requirement_ids": ["19.04-attack-sequence-source-retention"],
        "source_row_ids": ["rule:19:19.04:1"],
        "owner": (
            "src/warhammer40k_core/engine/ability_presence.py:active_ability_model_ids_for_unit"
        ),
        "expected": {
            "grant_before_attack": True,
            "grant_after_first_bearer_casualty_before_final_attack": True,
        },
        "observed": {
            "grant_before_attack": before,
            "damage_window_observations": observations,
            "remaining_sequence": remaining is not None,
            "status": None if status is None else status.status_kind.value,
        },
    }


def probe_psychic_ability_damage_classification() -> dict[str, object]:
    from tests.phase13b_shooting_declaration_helpers import (
        _replace_unit_instance_in_state,
        _shooting_lifecycle,
        _state,
    )
    from warhammer40k_core.engine.damage_allocation import (
        FeelNoPainAttackCondition,
        FeelNoPainSource,
    )
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.thousand_sons import (
        army_rule,
    )

    branches: list[dict[str, object]] = []
    for psychic_only in (False, True):
        lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
        state = _state(lifecycle)
        defender = units["enemy"]
        bearer = defender.own_models[0]
        _replace_unit_instance_in_state(
            state=state,
            replacement=replace(
                defender,
                own_models=(replace(bearer, wounds_remaining=1), *defender.own_models[1:]),
            ),
        )
        for model in defender.own_models:
            state.record_model_feel_no_pain_sources(
                model_instance_id=model.model_instance_id,
                sources=(
                    FeelNoPainSource(
                        source_id="order97:ability-damage-fnp",
                        threshold=2,
                        attack_condition=(
                            FeelNoPainAttackCondition.PSYCHIC_ATTACK if psychic_only else None
                        ),
                    ),
                ),
            )
        decisions = lifecycle.decision_controller
        result = army_rule._resolve_doombolt(  # pyright: ignore[reportPrivateUsage]
            state=state,
            decisions=decisions,
            dice_manager=DiceRollManager("order97:psychic-mortal", event_log=decisions.event_log),
            ritual=next(
                ritual
                for ritual in army_rule.RITUALS
                if ritual.ritual_id is army_rule.CabalRitualId.DOOMBOLT
            ),
            resolution_payload={
                "psychic_test_result": 7,
                "target_rules_unit_instance_id": defender.unit_instance_id,
                "target_owner_player_id": "player-b",
                "player_id": "player-a",
                "result_id": "order97:doombolt",
            },
        )
        events = decisions.event_log.records
        applications = [
            event.payload
            for event in events
            if event.event_type == "thousand_sons_cabal_mortal_wounds_resolved"
        ]
        branches.append(
            {
                "psychic_only_source": psychic_only,
                "pending_request": (
                    None
                    if result is None
                    else result.decision_request.decision_type
                    if result.decision_request is not None
                    else result.status_kind.value
                ),
                "roll_types": [
                    event.payload["spec"]["roll_type"]
                    for event in events
                    if event.event_type == "dice_rolled"
                    and isinstance(event.payload, dict)
                    and isinstance(event.payload["spec"], dict)
                ],
                "resolved_applications": applications,
            }
        )
    return {
        "requirement_ids": ["22.03-psychic-damage-tag"],
        "source_row_ids": ["rule:22:22.03:1"],
        "owners": [
            "src/warhammer40k_core/engine/mortal_wound_model_allocation.py:"
            "mortal_wound_feel_no_pain_sources",
            "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/"
            "thousand_sons/army_rule.py:_resolve_doombolt",
        ],
        "expected": {
            "psychic_source_damage_can_preserve_psychic_only_fnp_eligibility": True,
        },
        "observed": branches,
        "qualification": (
            "This calls the actual named Cabal damage consumer, not an invented tagged "
            "mortal packet. Its source context carries the successful Psychic test, "
            "but the mortal-wound FNP owner accepts no Psychic classification and "
            "filters the Psychic-only source. The selected Core clause requires this "
            "classification for authenticated Psychic abilities. The pinned official "
            "July Thousand Sons update refers to Doombolt but does not transcribe its "
            "own Psychic title; verify that source identity before certifying the named "
            "consumer as compliant. The generic source-classification limitation is "
            "observed independently of that remaining source qualification."
        ),
    }


def probe_coherency_destroyed_model_mission_count() -> dict[str, object]:
    from tests.phase13b_shooting_declaration_helpers import (
        _replace_unit_instance_in_state,
        _shooting_lifecycle,
        _state,
        _unit_placement_at,
    )
    from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
    from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.secondary_scoring_conditions import (
        SecondaryScoringConditionContext,
        evaluate_secondary_scoring_condition,
    )

    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    assert state.mission_setup is not None
    enemy = units["enemy"]
    isolated = enemy.own_models[-1]
    isolated = replace(
        isolated,
        characteristics=(
            *(
                value
                for value in isolated.characteristics
                if value.characteristic is not Characteristic.WOUNDS
            ),
            CharacteristicValue.from_raw(Characteristic.WOUNDS, 10),
        ),
        starting_wounds=10,
        wounds_remaining=10,
    )
    enemy = replace(enemy, own_models=(*enemy.own_models[:-1], isolated))
    _replace_unit_instance_in_state(state=state, replacement=enemy)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _unit_placement_at(
            enemy,
            army_id="army-beta",
            player_id="player-b",
            poses=(
                Pose.at(35, 35),
                Pose.at(36.5, 35),
                Pose.at(38, 35),
                Pose.at(39.5, 35),
                Pose.at(50, 35),
            ),
        )
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record = state.record_objective_control_boundary(
        decisions=lifecycle.decision_controller,
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=None,
    )
    state.resolve_end_turn_cleanup_boundary(completed_phase=BattlePhase.FIGHT)
    cleanup = state.end_turn_cleanup_states[-1]
    assert cleanup.removed_model_instance_ids == (isolated.model_instance_id,)
    condition = "each_enemy_model_w10_or_more_destroyed_this_turn"
    result = evaluate_secondary_scoring_condition(
        condition=condition,
        context=SecondaryScoringConditionContext(
            record=record,
            mission_setup=state.mission_setup,
            player_id="player-a",
            unit_destruction_states=tuple(state.secondary_unit_destruction_states),
            objective_cleanse_states=(),
            terrain_plunder_states=(),
            enemy_unit_ids_in_player_deployment_zone=(),
            starting_strength_records=tuple(state.starting_strength_records),
        ),
    )
    return {
        "requirement_ids": ["faq-904b8b36-09f0-4449-a9c3-45892664ef60-obligation-01"],
        "source_row_ids": ["faq:904b8b36-09f0-4449-a9c3-45892664ef60"],
        "owners": [
            "src/warhammer40k_core/engine/game_state.py:GameState.resolve_end_turn_cleanup_boundary",
            "src/warhammer40k_core/engine/secondary_unit_destruction_tracking.py:"
            "secondary_unit_destruction_from_primary",
            "src/warhammer40k_core/engine/secondary_scoring_conditions.py:"
            "evaluate_secondary_scoring_condition",
        ],
        "input": {
            "scoring_player": "player-a",
            "enemy_isolated_model": isolated.model_instance_id,
            "isolated_model_starting_wounds": isolated.initial_wounds,
            "remaining_component_model_count": 4,
            "secondary_scoring_condition": condition,
        },
        "expected": {"score_count": 1, "destroyed_model_ids": [isolated.model_instance_id]},
        "observed": {
            "cleanup_removed_model_ids": cleanup.removed_model_instance_ids,
            "removal_kind": cleanup.removals[0].removal_kind.value,
            "destroyed_model_rules_triggered": cleanup.removals[0].destroyed_model_rules_triggered,
            "primary_departure_count": len(state.primary_battlefield_departure_states),
            "secondary_destruction_count": len(state.secondary_unit_destruction_states),
            "score_condition_result": result,
        },
        "qualification": (
            "This exercises the actual cleanup and Bring It Down condition consumer "
            "with a real domain unit. It does not claim a completed scoring-ledger "
            "transaction or facade replay. The Secondary model inventory is projected "
            "only after unit/component completion, so a qualifying coherency casualty "
            "in a surviving component is absent. Repair the shared per-model destruction "
            "evidence route and audit other destruction causes using the same inventory."
        ),
    }


def disembark_band_resolution(mode: str, distance: float) -> DisembarkResolution:
    from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID, disembark_session
    from tests.order60_emergency_disembark_helpers import emergency_disembark_poses_around
    from tests.phase13b_shooting_declaration_helpers import _unit_placement_at
    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.transports import (
        DisembarkModeKind,
        DisembarkSelection,
        TransportMovementStatus,
        resolve_disembark_internal,
    )

    session = disembark_session(
        unit_poses={"army-alpha:remaining-unit": tuple(Pose.at(30 + i * 1.5, 10) for i in range(5))}
    )
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    passenger = unit_by_id(state=state, unit_instance_id=PASSENGER_ID)
    transport = unit_by_id(state=state, unit_instance_id=TRANSPORT_ID)
    passenger_diameter = passenger.own_models[0].base_size.diameter_mm
    transport_diameter = transport.own_models[0].base_size.diameter_mm
    assert passenger_diameter is not None
    assert transport_diameter is not None
    radius = transport_diameter / 50.8 + distance - passenger_diameter / 50.8
    placement = _unit_placement_at(
        passenger,
        army_id="army-alpha",
        player_id="player-a",
        poses=emergency_disembark_poses_around(
            center_x=10,
            center_y=10,
            count=len(passenger.own_models),
            radius_inches=radius,
            step_degrees=30,
        ),
    )
    movement = (
        TransportMovementStatus.NORMAL_MOVE
        if mode == "rapid_disembark"
        else TransportMovementStatus.NOT_MOVED
    )
    return resolve_disembark_internal(
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
            transport_movement_status=movement,
        ),
        unit=passenger,
        transport_placement=scenario.battlefield_state.unit_placement_by_id(TRANSPORT_ID),
        turn_player_id="player-a",
        require_started_phase_embarked=False,
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        terrain_features=(),
        objective_markers=(),
    )


def probe_exact_disembark_band_boundary() -> dict[str, object]:
    observations: list[dict[str, object]] = []
    for mode in ("rapid_disembark", "tactical_disembark"):
        for distance in (2.99, 3.0, 3.01):
            result = disembark_band_resolution(mode, distance)
            observations.append(
                {
                    "mode": mode,
                    "analytic_wholly_within_distance_inches": distance,
                    "expected_valid": distance <= 3,
                    "observed_valid": result.is_valid,
                    "violation_codes": sorted(
                        {violation.violation_code.value for violation in result.violations}
                    ),
                }
            )
    return {
        "requirement_ids": ["18.04-rapid-tactical-distance"],
        "source_row_ids": ["rule:18:18.04:1"],
        "owner": "src/warhammer40k_core/engine/transport_disembark_geometry.py:"
        "_model_wholly_within_any_transport_model",
        "expected": {"exact_three_inch_wholly_within_boundary_inclusive": True},
        "observed": observations,
        "qualification": (
            "The canonical circular passenger and Transport bases are placed using "
            "the analytic center-radius formula, with other units clear of the band. "
            "Both ordinary modes reject exact three-inch containment while accepting "
            "2.99 inches. The shared owner instead checks buffered Shapely polygon "
            "approximations. Correct inclusive containment through the shared geometry "
            "owner and audit the other modes and wholly-within callers."
        ),
    }


if __name__ == "__main__":
    print(
        json.dumps(
            {
                "schema_version": 1,
                "observations": [
                    probe_extra_attacks(),
                    probe_parameterized_blast(),
                    probe_no_move_embark(),
                    probe_attack_sequence_grant_retention(),
                    probe_psychic_ability_damage_classification(),
                    probe_coherency_destroyed_model_mission_count(),
                    probe_exact_disembark_band_boundary(),
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
