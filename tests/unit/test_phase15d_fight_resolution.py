from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import (
    ConsolidationModeKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import AttackProfile, WeaponKeyword
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelDisplacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_resolution import (
    CONSOLIDATE_ACTION,
    MELEE_TARGETING_RULE_ID,
    PILE_IN_ACTION,
    FightMovementEndpointPayload,
    FightMovementProposal,
    MeleeDeclarationProposal,
    MeleeDeclarationProposalRequest,
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
    available_melee_weapons_payloads,
    build_fight_movement_request,
    build_melee_declaration_request,
    fight_movement_proposal_from_payload,
    fight_movement_proposal_payload_parse_failure,
    fight_movement_resolution_violation,
    fight_movement_rule_validation,
    legal_consolidation_modes,
    legal_pile_in_target_unit_ids,
    melee_attack_sequence_from_proposal,
    melee_declaration_proposal_from_payload,
    melee_target_unit_ids,
    resolve_fight_movement,
    validate_melee_declaration_rules,
)
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
    WargearSelection,
)
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    UnitCoherencyResult,
    UnitCoherencyStatus,
    UnitCoherencyViolation,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathWitness,
    TerrainPathLegalityResult,
    TerrainTraversalViolation,
)
from warhammer40k_core.geometry.pose import Pose


def test_phase15d_melee_split_lowers_to_shared_attack_sequence_pools() -> None:
    catalog, ruleset, scenario, attacker, target_a, target_b = _melee_fixture()
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    proposal = _melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(
                    MeleeTargetAllocation(target_a.unit_instance_id, attacks=2),
                    MeleeTargetAllocation(target_b.unit_instance_id, attacks=3),
                ),
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
    sequence = melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("phase15d-split"),
        sequence_id="phase15d-split-sequence",
    )

    assert validation.is_valid
    assert sequence.source_phase is BattlePhase.FIGHT
    assert [pool.target_unit_instance_id for pool in sequence.attack_pools] == [
        target_a.unit_instance_id,
        target_b.unit_instance_id,
    ]
    assert [pool.attacks for pool in sequence.attack_pools] == [2, 3]
    assert {pool.targeting_rule_ids for pool in sequence.attack_pools} == {
        (MELEE_TARGETING_RULE_ID,)
    }


def test_phase15d_melee_targets_are_model_engagement_scoped() -> None:
    catalog, ruleset, scenario, attacker, _target_a, target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    proposal = _melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(target_b.unit_instance_id),),
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

    assert not validation.is_valid
    assert validation.violations[0].violation_code == "melee_target_not_engaged_with_model"


def test_phase15d_extra_attacks_weapon_can_be_added_to_primary_melee_weapon() -> None:
    catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        include_extra_attacks=True,
    )
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    proposal = _melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(target_a.unit_instance_id),),
            ),
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-extra-blade",
                weapon_profile_id="core-extra-blade:standard",
                target_allocations=(MeleeTargetAllocation(target_a.unit_instance_id),),
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
    sequence = melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("phase15d-extra-attacks"),
        sequence_id="phase15d-extra-attacks-sequence",
    )

    assert validation.is_valid
    assert [pool.wargear_id for pool in sequence.attack_pools] == [
        "core-leader-blade",
        "core-extra-blade",
    ]
    assert [pool.attacks for pool in sequence.attack_pools] == [5, 5]


def test_phase15d_melee_request_and_proposal_payloads_round_trip() -> None:
    catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    available_weapons = available_melee_weapons_payloads(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit=attacker,
        army_catalog=catalog,
    )
    request_decision = build_melee_declaration_request(
        request_id="phase15d-melee-round-trip-request",
        game_id="phase15d-game",
        battle_round=1,
        active_player_id="player-a",
        actor_id="player-a",
        unit_instance_id=attacker.unit_instance_id,
        source_decision_request_id="phase15d-source-request",
        source_decision_result_id="phase15d-source-result",
        ruleset_descriptor=ruleset,
        available_weapons=available_weapons,
        target_unit_instance_ids=(target_a.unit_instance_id,),
    )
    request = MeleeDeclarationProposalRequest.from_decision_request(request_decision)
    proposal = _melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(target_a.unit_instance_id),),
            ),
        ),
    )
    parsed = melee_declaration_proposal_from_payload(proposal.to_payload())

    assert request.to_payload()["decision_type"] == "submit_melee_declaration"
    assert parsed == proposal
    assert parsed.validation_result_for_request(request).is_valid

    with pytest.raises(GameLifecycleError, match="wrong decision_type"):
        MeleeDeclarationProposalRequest.from_decision_request(
            replace(request_decision, decision_type="select_unit")
        )
    with pytest.raises(GameLifecycleError, match="must be an object"):
        melee_declaration_proposal_from_payload(())


def test_phase15d_melee_proposal_validation_rejects_stale_or_drifted_context() -> None:
    catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    proposal = _melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(target_a.unit_instance_id),),
            ),
        ),
    )

    cases = (
        (
            replace(proposal, proposal_request_id="phase15d-stale-request"),
            "stale_proposal_request",
            "stale",
        ),
        (replace(proposal, player_id="player-b"), "proposal_player_drift", "invalid"),
        (replace(proposal, battle_round=2), "proposal_battle_round_drift", "invalid"),
        (
            replace(proposal, unit_instance_id=target_a.unit_instance_id),
            "proposal_unit_drift",
            "invalid",
        ),
        (
            replace(proposal, source_decision_request_id="phase15d-other-source-request"),
            "source_decision_request_drift",
            "invalid",
        ),
        (
            replace(proposal, source_decision_result_id="phase15d-other-source-result"),
            "source_decision_result_drift",
            "invalid",
        ),
    )

    for drifted, expected_code, expected_status in cases:
        validation = drifted.validation_result_for_request(request)

        assert not validation.is_valid
        assert validation.violations[0].violation_code == expected_code
        assert validation.status == expected_status


def test_phase15d_melee_split_rejects_more_targets_than_attacks() -> None:
    catalog, ruleset, scenario, attacker, target_a, target_b = _melee_fixture()
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    proposal = _melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(
                    MeleeTargetAllocation(target_a.unit_instance_id, attacks=1),
                    MeleeTargetAllocation(target_b.unit_instance_id, attacks=1),
                    MeleeTargetAllocation("army-beta:target-c", attacks=1),
                    MeleeTargetAllocation("army-beta:target-d", attacks=1),
                    MeleeTargetAllocation("army-beta:target-e", attacks=1),
                    MeleeTargetAllocation("army-beta:target-f", attacks=1),
                ),
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

    assert not validation.is_valid
    assert validation.violations[0].violation_code == "melee_target_count_exceeds_attacks"


def test_phase15d_melee_rule_validation_rejects_weapon_selection_invariants() -> None:
    catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        include_extra_attacks=True,
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    primary = MeleeWeaponDeclaration(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id="core-leader-blade",
        weapon_profile_id="core-leader-blade:standard",
        target_allocations=(MeleeTargetAllocation(target_a.unit_instance_id),),
    )
    extra_only = MeleeWeaponDeclaration(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id="core-extra-blade",
        weapon_profile_id="core-extra-blade:standard",
        target_allocations=(MeleeTargetAllocation(target_a.unit_instance_id),),
    )
    unavailable = MeleeWeaponDeclaration(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id="core-missing-blade",
        weapon_profile_id="core-missing-blade:standard",
        target_allocations=(MeleeTargetAllocation(target_a.unit_instance_id),),
    )

    cases = (
        (
            replace(request, ruleset_descriptor_hash="phase15d-stale-ruleset"),
            _melee_proposal(request=request, attacker=attacker, declarations=(primary,)),
            "ruleset_descriptor_hash_drift",
        ),
        (
            request,
            _melee_proposal(request=request, attacker=attacker, declarations=()),
            "melee_declaration_required",
        ),
        (
            request,
            _melee_proposal(request=request, attacker=attacker, declarations=(primary, primary)),
            "duplicate_melee_weapon_declaration",
        ),
        (
            request,
            _melee_proposal(request=request, attacker=attacker, declarations=(unavailable,)),
            "melee_weapon_not_available",
        ),
        (
            request,
            _melee_proposal(request=request, attacker=attacker, declarations=(extra_only,)),
            "melee_primary_weapon_required",
        ),
    )

    for case_request, proposal, expected_code in cases:
        validation = validate_melee_declaration_rules(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            request=case_request,
            proposal=proposal,
            army_catalog=catalog,
        )

        assert not validation.is_valid
        assert validation.violations[0].violation_code == expected_code


def test_phase15d_melee_rejects_multiple_primary_weapons_per_model() -> None:
    catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    leader_blade = next(
        wargear for wargear in catalog.wargear if wargear.wargear_id == "core-leader-blade"
    )
    leader_profile = leader_blade.weapon_profiles[0]
    second_profile = replace(
        leader_profile,
        profile_id="core-second-blade:standard",
        name="Core second blade",
    )
    catalog = replace(
        catalog,
        wargear=(
            *catalog.wargear,
            Wargear(
                wargear_id="core-second-blade",
                name="Core second blade",
                weapon_profiles=(second_profile,),
            ),
        ),
    )
    attacker = replace(
        attacker,
        wargear_selections=(
            WargearSelection(
                option_id="phase15d-two-primary-weapons",
                model_profile_id="core-character-leader",
                wargear_ids=("core-leader-blade", "core-second-blade"),
            ),
        ),
    )
    scenario = BattlefieldScenario(
        armies=(replace(scenario.armies[0], units=(attacker,)), scenario.armies[1]),
        battlefield_state=scenario.battlefield_state,
    )
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    proposal = _melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(target_a.unit_instance_id),),
            ),
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-second-blade",
                weapon_profile_id="core-second-blade:standard",
                target_allocations=(MeleeTargetAllocation(target_a.unit_instance_id),),
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

    assert not validation.is_valid
    assert validation.violations[0].violation_code == "melee_model_declared_multiple_weapons"


def test_phase15d_random_attack_melee_target_allocation_is_explicitly_unsupported() -> None:
    catalog, ruleset, scenario, attacker, target_a, target_b = _melee_fixture()
    leader_blade = next(
        wargear for wargear in catalog.wargear if wargear.wargear_id == "core-leader-blade"
    )
    leader_profile = leader_blade.weapon_profiles[0]
    random_profile = replace(
        leader_profile,
        attack_profile=AttackProfile.dice(DiceExpression(quantity=1, sides=6)),
    )
    catalog = replace(
        catalog,
        wargear=(
            Wargear(
                wargear_id=leader_blade.wargear_id,
                name=leader_blade.name,
                weapon_profiles=(random_profile,),
            ),
            *tuple(
                wargear
                for wargear in catalog.wargear
                if wargear.wargear_id != leader_blade.wargear_id
            ),
        ),
    )
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )

    single_target = validate_melee_declaration_rules(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=_melee_proposal(
            request=request,
            attacker=attacker,
            declarations=(
                MeleeWeaponDeclaration(
                    attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                    wargear_id="core-leader-blade",
                    weapon_profile_id="core-leader-blade:standard",
                    target_allocations=(
                        MeleeTargetAllocation(target_a.unit_instance_id, attacks=1),
                    ),
                ),
            ),
        ),
        army_catalog=catalog,
    )
    split = validate_melee_declaration_rules(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=_melee_proposal(
            request=request,
            attacker=attacker,
            declarations=(
                MeleeWeaponDeclaration(
                    attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                    wargear_id="core-leader-blade",
                    weapon_profile_id="core-leader-blade:standard",
                    target_allocations=(
                        MeleeTargetAllocation(target_a.unit_instance_id, attacks=1),
                        MeleeTargetAllocation(target_b.unit_instance_id, attacks=1),
                    ),
                ),
            ),
        ),
        army_catalog=catalog,
    )

    assert single_target.violations[0].violation_code == (
        "random_melee_single_target_count_declared"
    )
    assert split.violations[0].violation_code == "random_melee_split_unsupported"


def test_phase15d_melee_split_rejects_missing_or_drifted_attack_counts() -> None:
    catalog, ruleset, scenario, attacker, target_a, target_b = _melee_fixture()
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    cases = (
        (
            (MeleeTargetAllocation(target_a.unit_instance_id, attacks=4),),
            "melee_attack_count_drift",
        ),
        (
            (
                MeleeTargetAllocation(target_a.unit_instance_id, attacks=2),
                MeleeTargetAllocation(target_b.unit_instance_id),
            ),
            "split_melee_attack_count_required",
        ),
        (
            (
                MeleeTargetAllocation(target_a.unit_instance_id, attacks=2),
                MeleeTargetAllocation(target_b.unit_instance_id, attacks=2),
            ),
            "split_melee_attack_count_drift",
        ),
    )

    for allocations, expected_code in cases:
        proposal = _melee_proposal(
            request=request,
            attacker=attacker,
            declarations=(
                MeleeWeaponDeclaration(
                    attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                    wargear_id="core-leader-blade",
                    weapon_profile_id="core-leader-blade:standard",
                    target_allocations=allocations,
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

        assert not validation.is_valid
        assert validation.violations[0].violation_code == expected_code


def test_phase15d_melee_rejects_unengaged_model_and_split_drift_at_sequence_build() -> None:
    catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_a_pose=Pose.at(30.0, 30.0),
        target_b_pose=Pose.at(34.0, 30.0),
    )
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    unengaged = _melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(target_a.unit_instance_id),),
            ),
        ),
    )

    validation = validate_melee_declaration_rules(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=unengaged,
        army_catalog=catalog,
    )

    assert not validation.is_valid
    assert validation.violations[0].violation_code == "melee_model_not_engaged"

    catalog, ruleset, scenario, attacker, target_a, target_b = _melee_fixture()
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    drifted_split = _melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(
                    MeleeTargetAllocation(target_a.unit_instance_id, attacks=2),
                    MeleeTargetAllocation(target_b.unit_instance_id, attacks=2),
                ),
            ),
        ),
    )

    with pytest.raises(GameLifecycleError, match="split attack total drifted"):
        melee_attack_sequence_from_proposal(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            proposal=drifted_split,
            army_catalog=catalog,
            dice_manager=DiceRollManager("phase15d-split-drift"),
            sequence_id="phase15d-split-drift-sequence",
        )


def test_phase15d_melee_sequence_fails_fast_when_target_engagement_drifts() -> None:
    catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_a_pose=Pose.at(30.0, 30.0),
        target_b_pose=Pose.at(34.0, 30.0),
    )
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    drifted = _melee_proposal(
        request=request,
        attacker=attacker,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(target_a.unit_instance_id),),
            ),
        ),
    )

    with pytest.raises(GameLifecycleError, match="target engagement drifted"):
        melee_attack_sequence_from_proposal(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            proposal=drifted,
            army_catalog=catalog,
            dice_manager=DiceRollManager("phase15d-target-drift"),
            sequence_id="phase15d-target-drift-sequence",
        )


def test_phase15d_available_melee_weapons_fail_fast_on_missing_catalog_wargear() -> None:
    catalog, ruleset, scenario, attacker, _target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    attacker = replace(
        attacker,
        wargear_selections=(
            WargearSelection(
                option_id="phase15d-missing-catalog-wargear",
                model_profile_id="core-character-leader",
                wargear_ids=("core-missing-blade",),
            ),
        ),
    )

    with pytest.raises(GameLifecycleError, match="wargear_id is not in the ArmyCatalog"):
        available_melee_weapons_payloads(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            unit=attacker,
            army_catalog=catalog,
        )


def test_phase15d_melee_dataclasses_fail_fast_on_malformed_values() -> None:
    catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _melee_request(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        attacker=attacker,
    )
    allocation = MeleeTargetAllocation(target_a.unit_instance_id, attacks=5)
    declaration = MeleeWeaponDeclaration(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id="core-leader-blade",
        weapon_profile_id="core-leader-blade:standard",
        target_allocations=(allocation,),
    )

    assert allocation.to_payload().get("attacks") == 5
    assert declaration.target_unit_instance_ids == (target_a.unit_instance_id,)
    with pytest.raises(GameLifecycleError, match="greater than zero"):
        MeleeTargetAllocation(target_a.unit_instance_id, attacks=0)
    with pytest.raises(GameLifecycleError, match="proposal_kind drift"):
        replace(request, proposal_kind="other_melee_declaration")
    with pytest.raises(GameLifecycleError, match="proposal_kind drift"):
        MeleeDeclarationProposal(
            proposal_request_id=request.request_id,
            proposal_kind="other_melee_declaration",
            player_id=request.actor_id,
            battle_round=request.battle_round,
            unit_instance_id=attacker.unit_instance_id,
            source_decision_request_id=request.source_decision_request_id,
            source_decision_result_id=request.source_decision_result_id,
            declarations=(declaration,),
        )
    with pytest.raises(GameLifecycleError, match="declarations must be a tuple"):
        MeleeDeclarationProposal(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
            player_id=request.actor_id,
            battle_round=request.battle_round,
            unit_instance_id=attacker.unit_instance_id,
            source_decision_request_id=request.source_decision_request_id,
            source_decision_result_id=request.source_decision_result_id,
            declarations=cast(tuple[MeleeWeaponDeclaration, ...], []),
        )
    with pytest.raises(GameLifecycleError, match="declarations must contain melee declarations"):
        MeleeDeclarationProposal(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
            player_id=request.actor_id,
            battle_round=request.battle_round,
            unit_instance_id=attacker.unit_instance_id,
            source_decision_request_id=request.source_decision_request_id,
            source_decision_result_id=request.source_decision_result_id,
            declarations=(cast(MeleeWeaponDeclaration, object()),),
        )
    with pytest.raises(GameLifecycleError, match="target_allocations must be a tuple"):
        MeleeWeaponDeclaration(
            attacker_model_instance_id=attacker.own_models[0].model_instance_id,
            wargear_id="core-leader-blade",
            weapon_profile_id="core-leader-blade:standard",
            target_allocations=cast(tuple[MeleeTargetAllocation, ...], []),
        )
    with pytest.raises(GameLifecycleError, match="must contain melee allocations"):
        MeleeWeaponDeclaration(
            attacker_model_instance_id=attacker.own_models[0].model_instance_id,
            wargear_id="core-leader-blade",
            weapon_profile_id="core-leader-blade:standard",
            target_allocations=(cast(MeleeTargetAllocation, object()),),
        )
    with pytest.raises(GameLifecycleError, match="must not duplicate target units"):
        MeleeWeaponDeclaration(
            attacker_model_instance_id=attacker.own_models[0].model_instance_id,
            wargear_id="core-leader-blade",
            weapon_profile_id="core-leader-blade:standard",
            target_allocations=(allocation, allocation),
        )
    with pytest.raises(GameLifecycleError, match="requires at least one target allocation"):
        MeleeWeaponDeclaration(
            attacker_model_instance_id=attacker.own_models[0].model_instance_id,
            wargear_id="core-leader-blade",
            weapon_profile_id="core-leader-blade:standard",
            target_allocations=(),
        )


def test_phase15d_pile_in_rejects_endpoint_only_witness() -> None:
    _catalog, _ruleset, scenario, attacker, target_a, _target_b = _melee_fixture()
    request = _fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        attacker=attacker,
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target_a.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.5,
            endpoint_only=True,
        ),
    )

    validation = proposal.validation_result_for_request(request)

    assert not validation.is_valid
    assert validation.violations[0].violation_code == "endpoint_only_path"


def test_phase15d_pile_in_resolves_with_path_witness_endpoint_record() -> None:
    _catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        attacker=attacker,
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target_a.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )

    request_validation = proposal.validation_result_for_request(request)
    rule_validation = fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=proposal,
        eligible_unit_ids=(attacker.unit_instance_id,),
    )
    resolution = resolve_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
    )
    resolution_violation = fight_movement_resolution_violation(
        proposal_request=request,
        proposal=proposal,
        resolution=resolution,
        scenario=scenario,
        ruleset_descriptor=ruleset,
    )
    before = scenario.battlefield_state.unit_placement_by_id(attacker.unit_instance_id)
    transition_batch = resolution.transition_batch(before=before)

    assert request_validation.is_valid
    assert rule_validation.is_valid
    assert resolution.is_valid
    assert resolution_violation is None
    assert legal_pile_in_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=attacker.unit_instance_id,
    ) == (target_a.unit_instance_id,)
    assert resolution.endpoint_witness["target_unit_instance_ids"] == [target_a.unit_instance_id]
    assert resolution.endpoint_witness["moved_model_instance_ids"] == [
        attacker.own_models[0].model_instance_id
    ]
    assert len(transition_batch.displacements) == 1
    assert transition_batch.displacements[0].source_step == PILE_IN_ACTION
    with pytest.raises(GameLifecycleError, match="displacement requires witness"):
        replace(resolution, witness=None).transition_batch(before=before)


def test_phase15d_fight_movement_payloads_and_parse_failures_are_typed() -> None:
    _catalog, _ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        attacker=attacker,
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target_a.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )

    parsed = fight_movement_proposal_from_payload(proposal.to_payload())
    missing_field = fight_movement_proposal_payload_parse_failure(
        proposal_request=request,
        error=KeyError("witness"),
    )
    malformed = fight_movement_proposal_payload_parse_failure(
        proposal_request=request,
        error=GameLifecycleError("bad witness"),
    )

    assert parsed == proposal
    assert missing_field.violations[0].violation_code == "proposal_payload_missing_field"
    assert missing_field.violations[0].field == "witness"
    assert malformed.violations[0].violation_code == "proposal_payload_malformed"
    with pytest.raises(GameLifecycleError, match="must be an object"):
        fight_movement_proposal_from_payload(())


def test_phase15d_fight_movement_request_validation_rejects_stale_or_drifted_payloads() -> None:
    _catalog, _ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        attacker=attacker,
    )
    base = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
    )
    targeted_without_witness = replace(
        base,
        pile_in_target_unit_instance_ids=(target_a.unit_instance_id,),
    )
    no_move_with_witness = replace(
        base,
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.0,
            endpoint_only=False,
        ),
    )
    drifted_kind = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
    )
    cases = (
        (
            replace(base, proposal_request_id="phase15d-stale-movement-request"),
            request,
            "stale_proposal_request",
        ),
        (drifted_kind, request, "proposal_kind_drift"),
        (replace(base, unit_instance_id=target_a.unit_instance_id), request, "proposal_unit_drift"),
        (base, replace(request, phase=BattlePhase.SHOOTING.value), "proposal_phase_drift"),
        (
            base,
            replace(request, movement_phase_action=CONSOLIDATE_ACTION),
            "proposal_action_drift",
        ),
        (
            base,
            replace(request, context={"movement_mode": MovementMode.CONSOLIDATE.value}),
            "proposal_movement_mode_drift",
        ),
        (no_move_with_witness, request, "no_move_witness_forbidden"),
        (targeted_without_witness, request, "fight_movement_witness_required"),
    )

    with pytest.raises(GameLifecycleError, match="requires a request"):
        base.validation_result_for_request(cast(MovementProposalRequest, object()))
    for proposal, proposal_request, expected_code in cases:
        validation = proposal.validation_result_for_request(proposal_request)

        assert not validation.is_valid
        assert validation.violations[0].violation_code == expected_code


def test_phase15d_fight_movement_dataclasses_fail_fast_on_malformed_values() -> None:
    _catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        attacker=attacker,
    )
    valid = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target_a.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )
    resolution = resolve_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=valid,
    )
    objective_payload = FightMovementProposal(
        proposal_request_id="phase15d-objective-proposal",
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
        consolidation_mode=ConsolidationModeKind.OBJECTIVE,
        objective_id="phase15d-objective",
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.0,
            endpoint_only=False,
        ),
    ).to_payload()
    ongoing_payload = FightMovementProposal(
        proposal_request_id="phase15d-ongoing-proposal",
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
        consolidation_mode=ConsolidationModeKind.ONGOING,
        consolidate_target_unit_instance_ids=(target_a.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.0,
            endpoint_only=False,
        ),
    ).to_payload()

    assert objective_payload.get("consolidation_mode") == ConsolidationModeKind.OBJECTIVE.value
    assert objective_payload.get("objective_id") == "phase15d-objective"
    assert ongoing_payload.get("consolidate_target_unit_instance_ids") == [
        target_a.unit_instance_id
    ]
    with pytest.raises(GameLifecycleError, match="Pile In proposal action/mode drift"):
        FightMovementProposal(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.PILE_IN,
            unit_instance_id=attacker.unit_instance_id,
            movement_phase_action=CONSOLIDATE_ACTION,
            movement_mode=MovementMode.PILE_IN,
        )
    with pytest.raises(GameLifecycleError, match="Consolidate proposal action/mode drift"):
        FightMovementProposal(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.CONSOLIDATE,
            unit_instance_id=attacker.unit_instance_id,
            movement_phase_action=CONSOLIDATE_ACTION,
            movement_mode=MovementMode.PILE_IN,
        )
    with pytest.raises(GameLifecycleError, match="proposal kind must be pile_in or consolidate"):
        FightMovementProposal(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.MELEE_DECLARATION,
            unit_instance_id=attacker.unit_instance_id,
            movement_phase_action=PILE_IN_ACTION,
            movement_mode=MovementMode.PILE_IN,
        )
    with pytest.raises(GameLifecycleError, match="action must be pile_in or consolidate"):
        FightMovementProposal(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.PILE_IN,
            unit_instance_id=attacker.unit_instance_id,
            movement_phase_action="normal_move",
            movement_mode=MovementMode.PILE_IN,
        )
    with pytest.raises(GameLifecycleError, match="mode must be pile_in or consolidate"):
        FightMovementProposal(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.PILE_IN,
            unit_instance_id=attacker.unit_instance_id,
            movement_phase_action=PILE_IN_ACTION,
            movement_mode=MovementMode.NORMAL,
        )
    with pytest.raises(GameLifecycleError, match="target_unit_instance_ids must be a tuple"):
        FightMovementProposal(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.PILE_IN,
            unit_instance_id=attacker.unit_instance_id,
            movement_phase_action=PILE_IN_ACTION,
            movement_mode=MovementMode.PILE_IN,
            pile_in_target_unit_instance_ids=cast(tuple[str, ...], [target_a.unit_instance_id]),
        )
    with pytest.raises(GameLifecycleError, match="objective_id must be a string"):
        FightMovementProposal(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.CONSOLIDATE,
            unit_instance_id=attacker.unit_instance_id,
            movement_phase_action=CONSOLIDATE_ACTION,
            movement_mode=MovementMode.CONSOLIDATE,
            objective_id=cast(str, 42),
        )
    with pytest.raises(GameLifecycleError, match="witness must be a PathWitness"):
        FightMovementProposal(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.PILE_IN,
            unit_instance_id=attacker.unit_instance_id,
            movement_phase_action=PILE_IN_ACTION,
            movement_mode=MovementMode.PILE_IN,
            witness=cast(PathWitness, object()),
        )
    with pytest.raises(GameLifecycleError, match="attempted_placement must be UnitPlacement"):
        replace(resolution, attempted_placement=cast(UnitPlacement, object()))
    with pytest.raises(GameLifecycleError, match="witness must be PathWitness"):
        replace(resolution, witness=cast(PathWitness, object()))
    with pytest.raises(GameLifecycleError, match="endpoint_witness"):
        replace(resolution, endpoint_witness=cast(FightMovementEndpointPayload, []))
    with pytest.raises(GameLifecycleError, match="coherency_result must be UnitCoherencyResult"):
        replace(resolution, coherency_result=cast(UnitCoherencyResult, object()))
    with pytest.raises(GameLifecycleError, match="rollback_record must be MovementRollbackRecord"):
        replace(resolution, rollback_record=cast(MovementRollbackRecord, object()))
    with pytest.raises(GameLifecycleError, match="Path validation results must be a tuple"):
        replace(resolution, path_validation_results=cast(tuple[PathValidationResult, ...], []))
    with pytest.raises(GameLifecycleError, match="must contain PathValidationResult"):
        replace(
            resolution,
            path_validation_results=(cast(PathValidationResult, object()),),
        )
    with pytest.raises(GameLifecycleError, match="Terrain path legality results must be a tuple"):
        replace(
            resolution,
            terrain_path_legality_results=cast(tuple[TerrainPathLegalityResult, ...], []),
        )
    with pytest.raises(GameLifecycleError, match="must contain TerrainPathLegalityResult"):
        replace(
            resolution,
            terrain_path_legality_results=(cast(TerrainPathLegalityResult, object()),),
        )


def test_phase15d_consolidate_no_move_proposal_is_valid_without_witness() -> None:
    _catalog, _ruleset, _scenario, attacker, _target_a, _target_b = _melee_fixture()
    request = _fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        attacker=attacker,
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
    )

    validation = proposal.validation_result_for_request(request)

    assert validation.is_valid


def test_phase15d_consolidate_no_move_resolution_is_json_safe() -> None:
    _catalog, ruleset, scenario, attacker, _target_a, _target_b = _melee_fixture()
    request = _fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        attacker=attacker,
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
    )

    resolution = resolve_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
    )
    resolution_violation = fight_movement_resolution_violation(
        proposal_request=request,
        proposal=proposal,
        resolution=resolution,
        scenario=scenario,
        ruleset_descriptor=ruleset,
    )
    payload = resolution.to_payload()

    assert resolution.is_valid
    assert resolution_violation is None
    assert payload["movement_mode"] == MovementMode.CONSOLIDATE.value
    assert payload["endpoint_witness"]["moved_model_instance_ids"] == []
    assert payload["rollback_record"] is None


def test_phase15d_fight_movement_reports_coherency_rollback_violation() -> None:
    _catalog, ruleset, scenario, attacker, _target_a, _target_b = _melee_fixture()
    request = _fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        attacker=attacker,
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
    )
    resolution = resolve_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
    )
    before = scenario.battlefield_state.unit_placement_by_id(attacker.unit_instance_id)
    model_id = attacker.own_models[0].model_instance_id
    coherency_result = UnitCoherencyResult(
        status=UnitCoherencyStatus.BROKEN,
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        unit_instance_id=attacker.unit_instance_id,
        coherency_policy=ruleset.coherency_policy,
        model_instance_ids=(model_id,),
        violations=(
            UnitCoherencyViolation(
                model_instance_id=model_id,
                violation_code="phase15d-forced-coherency-break",
            ),
        ),
    )
    rollback = MovementRollbackRecord(
        unit_instance_id=attacker.unit_instance_id,
        displacement_kind=ModelDisplacementKind.CONSOLIDATE,
        before_placement=before,
        attempted_placement=before,
        coherency_result=coherency_result,
    )
    rollback_resolution = replace(resolution, rollback_record=rollback)
    violation = fight_movement_resolution_violation(
        proposal_request=request,
        proposal=proposal,
        resolution=rollback_resolution,
        scenario=scenario,
        ruleset_descriptor=ruleset,
    )

    assert not rollback_resolution.is_valid
    assert violation is not None
    assert violation.violations[0].violation_code == "unit_coherency_invalid"


def test_phase15d_fight_movement_rule_validation_rejects_illegal_pile_in_targets() -> None:
    _catalog, ruleset, scenario, attacker, target_a, target_b = _melee_fixture()
    request = _fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        attacker=attacker,
    )
    incomplete = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target_a.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )

    ineligible_validation = fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=incomplete,
        eligible_unit_ids=(),
    )
    incomplete_validation = fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=incomplete,
        eligible_unit_ids=(attacker.unit_instance_id,),
    )

    assert ineligible_validation.violations[0].violation_code == (
        "fight_movement_unit_not_eligible"
    )
    assert incomplete_validation.violations[0].violation_code == (
        "pile_in_engaged_targets_must_be_complete"
    )

    _catalog, ruleset, scenario, attacker, target_a, target_b = _melee_fixture(
        target_a_pose=Pose.at(14.0, 10.0),
        target_b_pose=Pose.at(30.0, 30.0),
    )
    not_legal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target_b.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )

    target_validation = fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=not_legal,
        eligible_unit_ids=(attacker.unit_instance_id,),
    )

    assert legal_pile_in_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=attacker.unit_instance_id,
    ) == (target_a.unit_instance_id,)
    assert target_validation.violations[0].violation_code == "pile_in_target_not_legal"


def test_phase15d_fight_movement_rule_validation_rejects_missing_or_absent_pile_in_targets() -> (
    None
):
    _catalog, ruleset, scenario, attacker, _target_a, _target_b = _melee_fixture(
        target_a_pose=Pose.at(30.0, 30.0),
        target_b_pose=Pose.at(34.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        attacker=attacker,
    )
    no_legal_targets = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=("army-beta:target-a",),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )

    no_legal_validation = fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=no_legal_targets,
        eligible_unit_ids=(attacker.unit_instance_id,),
    )

    assert no_legal_validation.violations[0].violation_code == "pile_in_no_legal_targets"

    _catalog, ruleset, scenario, attacker, _target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        attacker=attacker,
    )
    missing_target = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        objective_id="phase15d-pile-in-is-not-objective-movement",
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )

    missing_target_validation = fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=missing_target,
        eligible_unit_ids=(attacker.unit_instance_id,),
    )

    assert missing_target_validation.violations[0].violation_code == "pile_in_target_required"


def test_phase15d_consolidate_ongoing_resolves_with_selected_engaged_targets() -> None:
    _catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        attacker=attacker,
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
        consolidation_mode=ConsolidationModeKind.ONGOING,
        consolidate_target_unit_instance_ids=(target_a.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )

    request_validation = proposal.validation_result_for_request(request)
    rule_validation = fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=proposal,
        eligible_unit_ids=(attacker.unit_instance_id,),
    )
    resolution = resolve_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
    )
    resolution_violation = fight_movement_resolution_violation(
        proposal_request=request,
        proposal=proposal,
        resolution=resolution,
        scenario=scenario,
        ruleset_descriptor=ruleset,
    )

    assert request_validation.is_valid
    assert rule_validation.is_valid
    assert resolution.is_valid
    assert resolution_violation is None
    assert legal_consolidation_modes(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=attacker.unit_instance_id,
        objective_markers=(),
    ) == (ConsolidationModeKind.ONGOING,)
    assert resolution.endpoint_witness["target_unit_instance_ids"] == [target_a.unit_instance_id]
    assert resolution.endpoint_witness["engaged_after_unit_ids"] == [target_a.unit_instance_id]


def test_phase15d_consolidate_rule_validation_covers_modes_and_objectives() -> None:
    _catalog, ruleset, scenario, attacker, target_a, target_b = _melee_fixture()
    request = _fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        attacker=attacker,
    )
    wrong_mode = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
        consolidation_mode=ConsolidationModeKind.ENGAGING,
        consolidate_target_unit_instance_ids=(target_a.unit_instance_id, target_b.unit_instance_id),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )
    incomplete_targets = replace(
        wrong_mode,
        consolidation_mode=ConsolidationModeKind.ONGOING,
        consolidate_target_unit_instance_ids=(target_a.unit_instance_id,),
    )

    wrong_mode_validation = fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=wrong_mode,
        eligible_unit_ids=(attacker.unit_instance_id,),
    )
    incomplete_validation = fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=incomplete_targets,
        eligible_unit_ids=(attacker.unit_instance_id,),
    )

    assert wrong_mode_validation.violations[0].violation_code == "consolidation_mode_drift"
    assert incomplete_validation.violations[0].violation_code == (
        "ongoing_consolidation_targets_must_be_complete"
    )
    missing_mode = replace(
        wrong_mode,
        consolidation_mode=None,
        consolidate_target_unit_instance_ids=(target_a.unit_instance_id,),
    )
    missing_mode_validation = fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=missing_mode,
        eligible_unit_ids=(attacker.unit_instance_id,),
    )

    assert missing_mode_validation.violations[0].violation_code == "consolidation_mode_required"

    _catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_a_pose=Pose.at(14.0, 10.0),
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        attacker=attacker,
    )
    engaging = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
        consolidation_mode=ConsolidationModeKind.ENGAGING,
        consolidate_target_unit_instance_ids=(target_a.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )
    wrong_engaging_mode = replace(
        engaging,
        consolidation_mode=ConsolidationModeKind.ONGOING,
    )
    illegal_engaging_target = replace(
        engaging,
        consolidate_target_unit_instance_ids=("army-beta:missing-target",),
    )

    assert fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=engaging,
        eligible_unit_ids=(attacker.unit_instance_id,),
    ).is_valid
    assert legal_consolidation_modes(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=attacker.unit_instance_id,
        objective_markers=(),
    ) == (ConsolidationModeKind.ENGAGING,)
    assert (
        fight_movement_rule_validation(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            proposal_request=request,
            proposal=wrong_engaging_mode,
            eligible_unit_ids=(attacker.unit_instance_id,),
        )
        .violations[0]
        .violation_code
        == "consolidation_mode_drift"
    )
    assert (
        fight_movement_rule_validation(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            proposal_request=request,
            proposal=illegal_engaging_target,
            eligible_unit_ids=(attacker.unit_instance_id,),
        )
        .violations[0]
        .violation_code
        == "engaging_consolidation_target_not_legal"
    )

    objective_marker = ObjectiveMarker(
        objective_marker_id="phase15d-objective",
        name="phase15d-objective",
        x_inches=12.0,
        y_inches=10.0,
    )
    _catalog, ruleset, scenario, attacker, _target_a, _target_b = _melee_fixture(
        target_a_pose=Pose.at(30.0, 30.0),
        target_b_pose=Pose.at(34.0, 30.0),
    )
    objective_request = _fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        attacker=attacker,
        context={"objective_markers": [objective_marker.to_payload()]},
    )
    objective = FightMovementProposal(
        proposal_request_id=objective_request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
        consolidation_mode=ConsolidationModeKind.OBJECTIVE,
        objective_id=objective_marker.objective_marker_id,
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )
    no_mode = replace(objective, objective_id="phase15d-missing-objective")
    objective_mode_drift = replace(
        objective,
        consolidation_mode=ConsolidationModeKind.ENGAGING,
    )

    assert fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=objective_request,
        proposal=objective,
        eligible_unit_ids=(attacker.unit_instance_id,),
    ).is_valid
    assert legal_consolidation_modes(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=attacker.unit_instance_id,
        objective_markers=(objective_marker,),
    ) == (ConsolidationModeKind.OBJECTIVE,)
    assert (
        fight_movement_rule_validation(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            proposal_request=objective_request,
            proposal=objective_mode_drift,
            eligible_unit_ids=(attacker.unit_instance_id,),
        )
        .violations[0]
        .violation_code
        == "consolidation_mode_drift"
    )
    assert (
        fight_movement_rule_validation(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            proposal_request=objective_request,
            proposal=no_mode,
            eligible_unit_ids=(attacker.unit_instance_id,),
        )
        .violations[0]
        .violation_code
        == "objective_consolidation_target_not_legal"
    )

    empty_request = _fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        attacker=attacker,
    )
    no_legal_mode = replace(objective, proposal_request_id=empty_request.request_id)

    assert (
        fight_movement_rule_validation(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            proposal_request=empty_request,
            proposal=no_legal_mode,
            eligible_unit_ids=(attacker.unit_instance_id,),
        )
        .violations[0]
        .violation_code
        == "consolidation_no_legal_mode"
    )


def test_phase15d_fight_movement_reports_path_violation_before_endpoint_checks() -> None:
    _catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        attacker=attacker,
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target_a.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=3.5,
            endpoint_only=False,
        ),
    )

    request_validation = proposal.validation_result_for_request(request)
    rule_validation = fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=proposal,
        eligible_unit_ids=(attacker.unit_instance_id,),
    )
    resolution = resolve_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
    )
    resolution_violation = fight_movement_resolution_violation(
        proposal_request=request,
        proposal=proposal,
        resolution=resolution,
        scenario=scenario,
        ruleset_descriptor=ruleset,
    )
    terrain_violation = fight_movement_resolution_violation(
        proposal_request=request,
        proposal=proposal,
        resolution=replace(
            resolution,
            path_validation_results=(),
            terrain_path_legality_results=(
                TerrainPathLegalityResult.invalid(
                    TerrainTraversalViolation(
                        violation_code="terrain_blocked",
                        message="Terrain blocked.",
                    ),
                    segments=(),
                    sampled_pose_count=1,
                ),
            ),
        ),
        scenario=scenario,
        ruleset_descriptor=ruleset,
    )

    assert request_validation.is_valid
    assert rule_validation.is_valid
    assert not resolution.is_valid
    assert resolution_violation is not None
    assert resolution_violation.violations[0].violation_code == "movement_distance_exceeded"
    assert resolution_violation.violations[0].field == "witness"
    assert terrain_violation is not None
    assert terrain_violation.violations[0].violation_code == "terrain_blocked"
    before = scenario.battlefield_state.unit_placement_by_id(attacker.unit_instance_id)
    with pytest.raises(GameLifecycleError, match="Invalid fight movement"):
        resolution.transition_batch(before=before)


def test_phase15d_fight_movement_reports_endpoint_violations() -> None:
    _catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        attacker=attacker,
    )
    away = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target_a.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=-0.25,
            endpoint_only=False,
        ),
    )
    away_resolution = resolve_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=away,
    )
    away_violation = fight_movement_resolution_violation(
        proposal_request=request,
        proposal=away,
        resolution=away_resolution,
        scenario=scenario,
        ruleset_descriptor=ruleset,
    )

    assert away_resolution.is_valid
    assert away_violation is not None
    assert away_violation.violations[0].violation_code == "moved_model_not_closer_to_target"

    _catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_a_pose=Pose.at(14.5, 10.0),
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        attacker=attacker,
    )
    not_engaged_after = replace(
        away,
        proposal_request_id=request.request_id,
        pile_in_target_unit_instance_ids=(target_a.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )
    not_engaged_resolution = resolve_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=not_engaged_after,
    )
    not_engaged_violation = fight_movement_resolution_violation(
        proposal_request=request,
        proposal=not_engaged_after,
        resolution=not_engaged_resolution,
        scenario=scenario,
        ruleset_descriptor=ruleset,
    )

    assert not_engaged_resolution.is_valid
    assert not_engaged_violation is not None
    assert not_engaged_violation.violations[0].violation_code == "pile_in_unit_not_engaged_after"


def test_phase15d_consolidate_reports_engaging_and_objective_endpoint_violations() -> None:
    _catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_a_pose=Pose.at(14.0, 10.0),
        target_b_pose=Pose.at(30.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        attacker=attacker,
    )
    engaging = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
        consolidation_mode=ConsolidationModeKind.ENGAGING,
        consolidate_target_unit_instance_ids=(target_a.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )

    engaging_resolution = resolve_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=engaging,
    )
    engaging_violation = fight_movement_resolution_violation(
        proposal_request=request,
        proposal=engaging,
        resolution=engaging_resolution,
        scenario=scenario,
        ruleset_descriptor=ruleset,
    )

    assert engaging_resolution.is_valid
    assert engaging_violation is not None
    assert engaging_violation.violations[0].violation_code == (
        "engaging_consolidation_target_not_engaged_after"
    )

    objective_marker = ObjectiveMarker(
        objective_marker_id="phase15d-endpoint-objective",
        name="phase15d-endpoint-objective",
        x_inches=12.0,
        y_inches=10.0,
    )
    _catalog, ruleset, scenario, attacker, _target_a, _target_b = _melee_fixture(
        target_a_pose=Pose.at(30.0, 30.0),
        target_b_pose=Pose.at(34.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        attacker=attacker,
        context={"objective_markers": [objective_marker.to_payload()]},
    )
    objective = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
        consolidation_mode=ConsolidationModeKind.OBJECTIVE,
        objective_id=objective_marker.objective_marker_id,
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=-3.0,
            endpoint_only=False,
        ),
    )
    objective_resolution = resolve_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=objective,
    )
    objective_violation = fight_movement_resolution_violation(
        proposal_request=request,
        proposal=objective,
        resolution=objective_resolution,
        scenario=scenario,
        ruleset_descriptor=ruleset,
    )

    assert objective_resolution.is_valid
    assert objective_violation is not None
    assert objective_violation.violations[0].violation_code == (
        "objective_consolidation_not_in_range"
    )


def test_phase15d_resolve_fight_movement_fails_fast_on_wrong_context() -> None:
    _catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    targeted_without_witness = FightMovementProposal(
        proposal_request_id="phase15d-no-witness",
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target_a.unit_instance_id,),
    )

    with pytest.raises(GameLifecycleError, match="requires a BattlefieldScenario"):
        resolve_fight_movement(
            scenario=cast(BattlefieldScenario, object()),
            ruleset_descriptor=ruleset,
            proposal=targeted_without_witness,
        )
    with pytest.raises(GameLifecycleError, match="requires a RulesetDescriptor"):
        resolve_fight_movement(
            scenario=scenario,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            proposal=targeted_without_witness,
        )
    with pytest.raises(GameLifecycleError, match="requires a PathWitness"):
        resolve_fight_movement(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            proposal=targeted_without_witness,
        )


def _melee_fixture(
    *,
    include_extra_attacks: bool = False,
    target_a_pose: Pose | None = None,
    target_b_pose: Pose | None = None,
) -> tuple[
    ArmyCatalog,
    RulesetDescriptor,
    BattlefieldScenario,
    UnitInstance,
    UnitInstance,
    UnitInstance,
]:
    resolved_target_a_pose = Pose.at(12.0, 10.0) if target_a_pose is None else target_a_pose
    resolved_target_b_pose = Pose.at(10.0, 12.0) if target_b_pose is None else target_b_pose
    catalog = _catalog(include_extra_attacks=include_extra_attacks)
    ruleset = RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase15d-test")
    armies = _armies(catalog)
    attacker = armies[0].unit_by_id("army-alpha:attacker")
    if include_extra_attacks:
        attacker = replace(
            attacker,
            wargear_selections=(
                WargearSelection(
                    option_id="phase15d-extra-attacks",
                    model_profile_id="core-character-leader",
                    wargear_ids=("core-leader-blade", "core-extra-blade"),
                ),
            ),
        )
        armies = (
            replace(armies[0], units=(attacker,)),
            armies[1],
        )
    target_a = armies[1].unit_by_id("army-beta:target-a")
    target_b = armies[1].unit_by_id("army-beta:target-b")
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase15d-battlefield",
        armies=armies,
    )
    battlefield = scenario.battlefield_state
    battlefield = battlefield.with_unit_placement(
        _unit_placement(
            attacker, army_id="army-alpha", player_id="player-a", pose=Pose.at(10.0, 10.0)
        )
    )
    battlefield = battlefield.with_unit_placement(
        _unit_placement(
            target_a, army_id="army-beta", player_id="player-b", pose=resolved_target_a_pose
        )
    )
    battlefield = battlefield.with_unit_placement(
        _unit_placement(
            target_b,
            army_id="army-beta",
            player_id="player-b",
            pose=resolved_target_b_pose,
        )
    )
    return (
        catalog,
        ruleset,
        BattlefieldScenario(armies=armies, battlefield_state=battlefield),
        attacker,
        target_a,
        target_b,
    )


def _fight_movement_request(
    *,
    proposal_kind: ProposalKind,
    attacker: UnitInstance,
    context: dict[str, object] | None = None,
) -> MovementProposalRequest:
    request_context: dict[str, JsonValue] = {"movement_mode": proposal_kind.value}
    if context is not None:
        request_context.update(cast(dict[str, JsonValue], context))
    request = build_fight_movement_request(
        state_game_id="phase15d-fight-movement",
        battle_round=1,
        active_player_id="player-a",
        request_id=f"phase15d-{proposal_kind.value}-request",
        actor_id="player-a",
        unit_instance_id=attacker.unit_instance_id,
        proposal_kind=proposal_kind,
        source_decision_request_id="phase15d-fight-activation-request",
        source_decision_result_id="phase15d-fight-activation-result",
        context=request_context,
    )
    return MovementProposalRequest.from_decision_request_payload(request.payload)


def _movement_witness_for_unit(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
    dx: float,
    endpoint_only: bool,
) -> PathWitness:
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        end = Pose.at(
            start.position.x + dx,
            start.position.y,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        if endpoint_only:
            model_paths.append((placement.model_instance_id, (start, end)))
            continue
        midpoint = Pose.at(
            start.position.x + (dx / 2.0),
            start.position.y,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _catalog(*, include_extra_attacks: bool) -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    if not include_extra_attacks:
        return catalog
    leader_blade = next(
        wargear for wargear in catalog.wargear if wargear.wargear_id == "core-leader-blade"
    )
    leader_profile = leader_blade.weapon_profiles[0]
    extra_profile = replace(
        leader_profile,
        profile_id="core-extra-blade:standard",
        name="Core extra blade",
        keywords=(WeaponKeyword.EXTRA_ATTACKS,),
    )
    return replace(
        catalog,
        wargear=(
            *catalog.wargear,
            Wargear(
                wargear_id="core-extra-blade",
                name="Core extra blade",
                weapon_profiles=(extra_profile,),
            ),
        ),
    )


def _armies(catalog: ArmyCatalog) -> tuple[ArmyDefinition, ArmyDefinition]:
    return (
        muster_army(
            catalog=catalog,
            request=_army_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                unit_ids=("attacker",),
            ),
        ),
        muster_army(
            catalog=catalog,
            request=_army_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                unit_ids=("target-a", "target-b"),
            ),
        ),
    )


def _army_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    unit_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
        ),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_id,
                datasheet_id="core-character-leader",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            )
            for unit_id in unit_ids
        ),
    )


def _unit_placement(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    pose: Pose,
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=unit.own_models[0].model_instance_id,
                pose=pose,
            ),
        ),
    )


def _melee_request(
    *,
    catalog: ArmyCatalog,
    ruleset: RulesetDescriptor,
    scenario: BattlefieldScenario,
    attacker: UnitInstance,
) -> MeleeDeclarationProposalRequest:
    return MeleeDeclarationProposalRequest(
        request_id="phase15d-melee-request",
        actor_id="player-a",
        game_id="phase15d-game",
        battle_round=1,
        active_player_id="player-a",
        unit_instance_id=attacker.unit_instance_id,
        source_decision_request_id="phase15d-source-request",
        source_decision_result_id="phase15d-source-result",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        available_weapons=available_melee_weapons_payloads(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            unit=attacker,
            army_catalog=catalog,
        ),
        target_unit_instance_ids=melee_target_unit_ids(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            unit_instance_id=attacker.unit_instance_id,
        ),
    )


def _melee_proposal(
    *,
    request: MeleeDeclarationProposalRequest,
    attacker: UnitInstance,
    declarations: tuple[MeleeWeaponDeclaration, ...],
) -> MeleeDeclarationProposal:
    return MeleeDeclarationProposal(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        player_id=request.actor_id,
        battle_round=request.battle_round,
        unit_instance_id=attacker.unit_instance_id,
        source_decision_request_id=request.source_decision_request_id,
        source_decision_result_id=request.source_decision_result_id,
        declarations=declarations,
    )
