from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    ConsolidationModeKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AttackProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.attack_sequence import (
    AttackSequenceStep,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND,
    FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
)
from warhammer40k_core.engine.fight_on_death import restore_model_awaiting_fight_on_death
from warhammer40k_core.engine.fight_resolution import (
    CONSOLIDATE_ACTION,
    MELEE_TARGETING_RULE_ID,
    PILE_IN_ACTION,
    FightMovementEndpointPayload,
    FightMovementProposal,
    FightMovementResolution,
    MeleeDeclarationProposal,
    MeleeDeclarationProposalRequest,
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
    available_melee_weapons_payloads,
    build_fight_movement_request,
    build_melee_declaration_request,
    fight_movement_maximum_distance_inches,
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
from warhammer40k_core.engine.fight_rules_unit_melee import (
    record_rules_unit_one_shot_melee_weapon_uses,
    rules_unit_available_melee_weapons_payloads,
    rules_unit_melee_attack_sequence_from_proposal,
    rules_unit_melee_target_unit_ids,
    validate_rules_unit_melee_declaration,
)
from warhammer40k_core.engine.fight_rules_unit_movement import (
    apply_fight_rules_unit_movement_resolution,
    fight_rules_unit_movement_resolution_violation,
    fight_rules_unit_movement_rule_validation,
    fight_rules_unit_movement_transition_batch,
    fight_rules_unit_movement_witness_matches_current_status,
    legal_rules_unit_consolidation_modes,
    legal_rules_unit_pile_in_target_unit_ids,
    resolve_rules_unit_fight_movement,
    rules_unit_fight_movement_maximum_distance_inches,
)
from warhammer40k_core.engine.fight_rules_unit_movement_types import (
    FightRulesUnitPlacement,
    RulesUnitFightMovementResolution,
    RulesUnitFightMovementResolutionPayload,
    RulesUnitMovementRollbackRecord,
    fight_rules_unit_movement_endpoint_from_completed_event,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    UnitCoherencyResult,
    UnitCoherencyStatus,
    UnitCoherencyViolation,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.engine.weapon_abilities import CLEAVE_RULE_ID, LANCE_RULE_ID
from warhammer40k_core.geometry.pathing import (
    PathConstraintViolation,
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


def test_phase15d_attached_rules_unit_melee_preserves_component_provenance() -> None:
    (
        catalog,
        ruleset,
        scenario,
        state,
        rules_unit,
        bodyguard,
        leader,
        target,
    ) = _attached_melee_fixture(leader_keywords=(WeaponKeyword.ONE_SHOT,))
    target_ids = rules_unit_melee_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        rules_unit=rules_unit,
        state=state,
    )
    available = rules_unit_available_melee_weapons_payloads(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        rules_unit=rules_unit,
        army_catalog=catalog,
        state=state,
        source_decision_result_id="phase15d-attached-source-result",
    )
    request = _rules_unit_melee_request(
        ruleset=ruleset,
        rules_unit=rules_unit,
        available=available,
        target_ids=target_ids,
    )
    proposal = MeleeDeclarationProposal(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        player_id=request.actor_id,
        battle_round=request.battle_round,
        unit_instance_id=rules_unit.unit_instance_id,
        source_decision_request_id=request.source_decision_request_id,
        source_decision_result_id=request.source_decision_result_id,
        declarations=tuple(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=component.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(target.unit_instance_id),),
            )
            for component in (bodyguard, leader)
        ),
    )

    validation = validate_rules_unit_melee_declaration(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=proposal,
        army_catalog=catalog,
        state=state,
    )
    sequence = rules_unit_melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("phase15d-attached-melee"),
        sequence_id="phase15d-attached-melee-sequence",
        state=state,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    records = record_rules_unit_one_shot_melee_weapon_uses(
        state=state,
        scenario=scenario,
        proposal=proposal,
        army_catalog=catalog,
        result_id="phase15d-attached-melee-result",
    )

    assert validation.is_valid
    assert target_ids == (target.unit_instance_id,)
    assert {
        cast(str, cast(dict[str, JsonValue], row)["rules_unit_instance_id"]) for row in available
    } == {rules_unit.unit_instance_id}
    assert {
        cast(str, cast(dict[str, JsonValue], row)["component_unit_instance_id"])
        for row in available
    } == {
        bodyguard.unit_instance_id,
        leader.unit_instance_id,
    }
    assert sequence.attacking_unit_instance_id == rules_unit.unit_instance_id
    assert {pool.attacker_model_instance_id for pool in sequence.attack_pools} == {
        bodyguard.own_models[0].model_instance_id,
        leader.own_models[0].model_instance_id,
    }
    assert len(records) == 2
    assert len({record.selection_id for record in records}) == 2


def test_phase15d_attached_melee_canonicalizes_attached_enemy_target() -> None:
    (
        catalog,
        ruleset,
        scenario,
        state,
        attacker_rules_unit,
        bodyguard,
        leader,
        target_component,
    ) = _attached_melee_fixture(
        leader_keywords=(WeaponKeyword.PRECISION,),
        target_attached=True,
    )
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_component.unit_instance_id,
    )
    modifier_contexts: list[WeaponProfileModifierContext] = []

    def canonical_target_modifier(context: WeaponProfileModifierContext) -> WeaponProfile:
        modifier_contexts.append(context)
        if context.target_unit_instance_id != target_rules_unit.unit_instance_id:
            return context.weapon_profile
        return replace(
            context.weapon_profile,
            strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 9),
        )

    runtime_modifiers = RuntimeModifierRegistry.from_bindings(
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id="test:phase15d:canonical-target-modifier",
                source_id="test:phase15d:canonical-target-modifier",
                handler=canonical_target_modifier,
            ),
        )
    )
    physical_target_aliases = {
        target_id
        for component in (bodyguard, leader)
        for target_id in melee_target_unit_ids(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            unit_instance_id=component.unit_instance_id,
            state=state,
        )
    }
    target_ids = rules_unit_melee_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        rules_unit=attacker_rules_unit,
        state=state,
    )
    available = rules_unit_available_melee_weapons_payloads(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        rules_unit=attacker_rules_unit,
        army_catalog=catalog,
        state=state,
        source_decision_result_id="phase15d-attached-source-result",
    )
    request = _rules_unit_melee_request(
        ruleset=ruleset,
        rules_unit=attacker_rules_unit,
        available=available,
        target_ids=target_ids,
    )
    declarations = tuple(
        MeleeWeaponDeclaration(
            attacker_model_instance_id=component.own_models[0].model_instance_id,
            wargear_id="core-leader-blade",
            weapon_profile_id="core-leader-blade:standard",
            target_allocations=(MeleeTargetAllocation(target_rules_unit.unit_instance_id),),
        )
        for component in (bodyguard, leader)
    )
    proposal = MeleeDeclarationProposal(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        player_id=request.actor_id,
        battle_round=request.battle_round,
        unit_instance_id=attacker_rules_unit.unit_instance_id,
        source_decision_request_id=request.source_decision_request_id,
        source_decision_result_id=request.source_decision_result_id,
        declarations=declarations,
    )

    validation = validate_rules_unit_melee_declaration(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=proposal,
        army_catalog=catalog,
        state=state,
    )
    sequence = rules_unit_melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("phase15d-attached-target"),
        sequence_id="phase15d-attached-target-sequence",
        state=state,
        runtime_modifier_registry=runtime_modifiers,
    )
    alias_proposal = replace(
        proposal,
        declarations=(
            replace(
                declarations[0],
                target_allocations=(MeleeTargetAllocation(target_component.unit_instance_id),),
            ),
            declarations[1],
        ),
    )
    alias_validation = validate_rules_unit_melee_declaration(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=alias_proposal,
        army_catalog=catalog,
        state=state,
    )

    assert target_rules_unit.is_attached_rules_unit
    assert physical_target_aliases == set(target_rules_unit.component_unit_instance_ids)
    assert target_ids == (target_rules_unit.unit_instance_id,)
    assert {
        tuple(
            cast(
                list[str],
                cast(dict[str, JsonValue], row)["engaged_target_unit_instance_ids"],
            )
        )
        for row in available
    } == {(target_rules_unit.unit_instance_id,)}
    assert validation.is_valid
    assert {pool.target_unit_instance_id for pool in sequence.attack_pools} == {
        target_rules_unit.unit_instance_id
    }
    expected_target_model_ids = {
        model.model_instance_id for model in target_rules_unit.alive_models()
    }
    leader_target_model_ids = set(
        target_rules_unit.character_model_ids(target_rules_unit.alive_models())
    )
    assert all(
        set(pool.target_in_range_model_ids) == expected_target_model_ids
        for pool in sequence.attack_pools
    )
    assert all(
        leader_target_model_ids.issubset(pool.target_visible_model_ids)
        for pool in sequence.attack_pools
    )
    assert all(
        WeaponKeyword.PRECISION in pool.weapon_profile.keywords for pool in sequence.attack_pools
    )
    assert all(pool.weapon_profile.strength.final == 9 for pool in sequence.attack_pools)
    assert {context.target_unit_instance_id for context in modifier_contexts} == {
        target_rules_unit.unit_instance_id
    }
    assert {context.attacking_unit_instance_id for context in modifier_contexts} == {
        bodyguard.unit_instance_id,
        leader.unit_instance_id,
    }
    assert alias_validation.violations[0].violation_code == "melee_target_identity_not_canonical"


def test_phase15d_attached_melee_excludes_unengaged_leader_evidence() -> None:
    (
        catalog,
        ruleset,
        scenario,
        state,
        attacker_rules_unit,
        bodyguard,
        leader,
        target_bodyguard,
    ) = _attached_melee_fixture(
        leader_keywords=(WeaponKeyword.PRECISION,),
        target_attached=True,
    )
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_bodyguard.unit_instance_id,
    )
    target_leader = next(
        component.unit for component in target_rules_unit.components if component.role == "leader"
    )
    target_leader_placement = scenario.battlefield_state.unit_placement_by_id(
        target_leader.unit_instance_id
    )
    battlefield = scenario.battlefield_state.with_unit_placement(
        target_leader_placement.with_model_placements(
            tuple(
                replace(model, pose=Pose.at(14.0, 10.8))
                for model in target_leader_placement.model_placements
            )
        )
    )
    scenario = replace(scenario, battlefield_state=battlefield)
    state.replace_battlefield_state(battlefield)
    request, proposal = _attached_rules_unit_melee_request_and_proposal(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        state=state,
        rules_unit=attacker_rules_unit,
        components=(bodyguard, leader),
        target_unit_instance_id=target_rules_unit.unit_instance_id,
    )

    assert validate_rules_unit_melee_declaration(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=proposal,
        army_catalog=catalog,
        state=state,
    ).is_valid
    sequence = rules_unit_melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("phase15d-unengaged-target-leader"),
        sequence_id="phase15d-unengaged-target-leader-sequence",
        state=state,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    bodyguard_model_ids = {model.model_instance_id for model in target_bodyguard.alive_own_models()}
    leader_model_ids = {model.model_instance_id for model in target_leader.alive_own_models()}

    assert all(
        set(pool.target_in_range_model_ids) == bodyguard_model_ids for pool in sequence.attack_pools
    )
    assert all(
        not leader_model_ids.intersection(pool.target_visible_model_ids)
        for pool in sequence.attack_pools
    )


def test_phase15d_attached_melee_unions_alias_targeting_permission_sources() -> None:
    (
        catalog,
        ruleset,
        scenario,
        state,
        attacker_rules_unit,
        bodyguard,
        _destroyed_leader,
        target_bodyguard,
    ) = _attached_melee_fixture(
        leader_alive=False,
        target_attached=True,
    )
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_bodyguard.unit_instance_id,
    )
    target_leader = next(
        component.unit for component in target_rules_unit.components if component.role == "leader"
    )
    battlefield = scenario.battlefield_state
    for target_unit, pose in (
        (target_bodyguard, Pose.at(12.2, 9.6)),
        (target_leader, Pose.at(11.5, 9.6)),
    ):
        placement = battlefield.unit_placement_by_id(target_unit.unit_instance_id)
        battlefield = battlefield.with_unit_placement(
            placement.with_model_placements(
                tuple(replace(model, pose=pose) for model in placement.model_placements)
            )
        )
    scenario = replace(scenario, battlefield_state=battlefield)
    state.replace_battlefield_state(battlefield)
    source_rule_id = "test:phase15d:attached-alias-targeting"
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="phase15d-attached-alias-targeting",
            source_rule_id=source_rule_id,
            owner_player_id=attacker_rules_unit.owner_player_id,
            target_unit_instance_ids=(attacker_rules_unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id=attacker_rules_unit.owner_player_id,
            ),
            effect_payload={
                "effect_kind": FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND,
                "activation_result_id": "phase15d-attached-source-result",
                "source_id": source_rule_id,
                "model_proximity_inches": 0.5,
            },
        )
    )
    request, proposal = _attached_rules_unit_melee_request_and_proposal(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        state=state,
        rules_unit=attacker_rules_unit,
        components=(bodyguard,),
        target_unit_instance_id=target_rules_unit.unit_instance_id,
    )
    physical_rows = available_melee_weapons_payloads(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit=bodyguard,
        army_catalog=catalog,
        state=state,
        source_decision_result_id=request.source_decision_result_id,
    )

    assert {
        target_id
        for row in physical_rows
        for target_id in cast(
            list[str], cast(dict[str, JsonValue], row)["engaged_target_unit_instance_ids"]
        )
    } == set(target_rules_unit.component_unit_instance_ids)
    assert validate_rules_unit_melee_declaration(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=proposal,
        army_catalog=catalog,
        state=state,
    ).is_valid
    sequence = rules_unit_melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("phase15d-attached-alias-targeting"),
        sequence_id="phase15d-attached-alias-targeting-sequence",
        state=state,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    pool = sequence.attack_pools[0]

    assert source_rule_id in pool.targeting_rule_ids
    assert target_leader.own_models[0].model_instance_id in pool.target_in_range_model_ids


def test_phase15d_attached_melee_cleave_uses_rules_unit_count_and_keywords() -> None:
    (
        catalog,
        ruleset,
        scenario,
        state,
        attacker_rules_unit,
        bodyguard,
        leader,
        target_bodyguard,
    ) = _attached_melee_fixture(
        leader_keywords=(WeaponKeyword.CLEAVE,),
        leader_abilities=(AbilityDescriptor.cleave(2, target_keywords=("CHARACTER",)),),
        target_attached=True,
        target_bodyguard_model_count=5,
    )
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_bodyguard.unit_instance_id,
    )
    request, base_proposal = _attached_rules_unit_melee_request_and_proposal(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        state=state,
        rules_unit=attacker_rules_unit,
        components=(bodyguard, leader),
        target_unit_instance_id=target_rules_unit.unit_instance_id,
    )
    proposal = replace(
        base_proposal,
        declarations=tuple(
            replace(
                declaration,
                target_allocations=(replace(declaration.target_allocations[0], attacks=7),),
            )
            for declaration in base_proposal.declarations
        ),
    )

    validation = validate_rules_unit_melee_declaration(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=proposal,
        army_catalog=catalog,
        state=state,
    )
    sequence = rules_unit_melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("phase15d-attached-target-cleave"),
        sequence_id="phase15d-attached-target-cleave-sequence",
        state=state,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    assert len(target_bodyguard.alive_own_models()) == 5
    assert len(target_rules_unit.alive_models()) == 6
    assert "CHARACTER" not in target_bodyguard.keywords
    assert "CHARACTER" in target_rules_unit.keywords
    assert validation.is_valid
    assert {pool.attacks for pool in sequence.attack_pools} == {7}
    assert all(f"{CLEAVE_RULE_ID}:2" in pool.targeting_rule_ids for pool in sequence.attack_pools)


@pytest.mark.parametrize("base_precision", [False, True])
def test_phase15d_epic_challenge_and_charge_follow_attached_lineage(
    base_precision: bool,
) -> None:
    keywords = (
        (WeaponKeyword.LANCE, WeaponKeyword.PRECISION) if base_precision else (WeaponKeyword.LANCE,)
    )
    (
        catalog,
        ruleset,
        scenario,
        state,
        rules_unit,
        bodyguard,
        leader,
        target,
    ) = _attached_melee_fixture(leader_keywords=keywords)
    request, proposal = _attached_rules_unit_melee_request_and_proposal(
        catalog=catalog,
        ruleset=ruleset,
        scenario=scenario,
        state=state,
        rules_unit=rules_unit,
        components=(bodyguard, leader),
        target_unit_instance_id=target.unit_instance_id,
    )
    expiration = EffectExpiration.end_turn(
        battle_round=state.battle_round,
        player_id=rules_unit.owner_player_id,
    )
    effects = (
        PersistingEffect(
            effect_id="phase15d-epic-unrelated-target",
            source_rule_id="test:phase15d:epic-unrelated",
            owner_player_id=rules_unit.owner_player_id,
            target_unit_instance_ids=(target.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload={
                "effect_kind": "epic_challenge_precision",
                "model_instance_id": leader.own_models[0].model_instance_id,
            },
        ),
        PersistingEffect(
            effect_id="phase15d-epic-non-object",
            source_rule_id="test:phase15d:epic-non-object",
            owner_player_id=rules_unit.owner_player_id,
            target_unit_instance_ids=(rules_unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload="not-an-object",
        ),
        PersistingEffect(
            effect_id="phase15d-epic-wrong-kind",
            source_rule_id="test:phase15d:epic-wrong-kind",
            owner_player_id=rules_unit.owner_player_id,
            target_unit_instance_ids=(rules_unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload={"effect_kind": "not-epic-challenge"},
        ),
        PersistingEffect(
            effect_id="phase15d-epic-wrong-model",
            source_rule_id="test:phase15d:epic-wrong-model",
            owner_player_id=rules_unit.owner_player_id,
            target_unit_instance_ids=(rules_unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload={
                "effect_kind": "epic_challenge_precision",
                "model_instance_id": target.own_models[0].model_instance_id,
            },
        ),
        PersistingEffect(
            effect_id="phase15d-epic-exact",
            source_rule_id="test:phase15d:epic-exact",
            owner_player_id=rules_unit.owner_player_id,
            target_unit_instance_ids=(rules_unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload={
                "effect_kind": "epic_challenge_precision",
                "model_instance_id": leader.own_models[0].model_instance_id,
            },
        ),
        PersistingEffect(
            effect_id="phase15d-attached-charge",
            source_rule_id="core-rules:charge:fights-first",
            owner_player_id=rules_unit.owner_player_id,
            target_unit_instance_ids=(rules_unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload={"effect_kind": "charge_grants_fights_first"},
        ),
    )
    for effect in effects:
        state.record_persisting_effect(effect)

    assert validate_rules_unit_melee_declaration(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=proposal,
        army_catalog=catalog,
        state=state,
    ).is_valid
    sequence = rules_unit_melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager(f"phase15d-epic-lineage:{base_precision}"),
        sequence_id=f"phase15d-epic-lineage-sequence:{base_precision}",
        state=state,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    leader_pool = next(
        pool
        for pool in sequence.attack_pools
        if pool.attacker_model_instance_id == leader.own_models[0].model_instance_id
    )

    assert WeaponKeyword.PRECISION in leader_pool.weapon_profile.keywords
    assert all(LANCE_RULE_ID in pool.targeting_rule_ids for pool in sequence.attack_pools)


def test_phase15d_extended_melee_targeting_is_model_scoped_and_source_linked() -> None:
    catalog, ruleset, scenario, attacker, target, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
        attacker_datasheet_id="core-intercessor-like-infantry",
        attacker_model_profile_id="core-intercessor-like",
        attacker_model_count=5,
        attacker_wargear_ids=("core-leader-blade",),
    )
    state = _attack_sequence_state(
        game_id="phase15d-extended-melee-targeting",
        ruleset=ruleset,
        scenario=scenario,
    )
    activation_result_id = "phase15d-extended-melee-activation"
    expiration = EffectExpiration.end_turn(
        battle_round=state.battle_round,
        player_id="player-a",
    )
    for effect in (
        PersistingEffect(
            effect_id="phase15d-extended-unrelated-target",
            source_rule_id="test:phase15d:extended-unrelated",
            owner_player_id="player-a",
            target_unit_instance_ids=(target.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload={
                "effect_kind": FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND,
                "activation_result_id": activation_result_id,
                "source_id": "test:phase15d:extended-unrelated",
                "model_proximity_inches": 6.0,
            },
        ),
        PersistingEffect(
            effect_id="phase15d-extended-non-object",
            source_rule_id="test:phase15d:extended-non-object",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload="not-an-object",
        ),
        PersistingEffect(
            effect_id="phase15d-extended-wrong-kind",
            source_rule_id="test:phase15d:extended-wrong-kind",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload={"effect_kind": "not-melee-targeting"},
        ),
        PersistingEffect(
            effect_id="phase15d-extended-wrong-activation",
            source_rule_id="test:phase15d:extended-wrong-activation",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload={
                "effect_kind": FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND,
                "activation_result_id": "phase15d-other-activation",
            },
        ),
        PersistingEffect(
            effect_id="phase15d-extended-valid",
            source_rule_id="test:phase15d:extended-valid",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload={
                "effect_kind": FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND,
                "activation_result_id": activation_result_id,
                "source_id": "test:phase15d:extended-valid",
                "model_proximity_inches": 6.0,
            },
        ),
    ):
        state.record_persisting_effect(effect)
    available = available_melee_weapons_payloads(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit=attacker,
        army_catalog=catalog,
        state=state,
        source_decision_result_id=activation_result_id,
    )
    engaged_rows = tuple(
        cast(dict[str, JsonValue], row)
        for row in available
        if cast(dict[str, JsonValue], row)["engaged_target_unit_instance_ids"]
    )
    request = MeleeDeclarationProposalRequest(
        request_id="phase15d-extended-melee-request",
        actor_id="player-a",
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id="player-a",
        unit_instance_id=attacker.unit_instance_id,
        source_decision_request_id="phase15d-extended-source-request",
        source_decision_result_id=activation_result_id,
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        available_weapons=available,
        target_unit_instance_ids=(target.unit_instance_id,),
    )
    proposal = MeleeDeclarationProposal(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        player_id=request.actor_id,
        battle_round=request.battle_round,
        unit_instance_id=attacker.unit_instance_id,
        source_decision_request_id=request.source_decision_request_id,
        source_decision_result_id=request.source_decision_result_id,
        declarations=tuple(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=cast(str, row["model_instance_id"]),
                wargear_id=cast(str, row["wargear_id"]),
                weapon_profile_id=cast(str, row["weapon_profile_id"]),
                target_allocations=(MeleeTargetAllocation(target.unit_instance_id),),
            )
            for row in engaged_rows
        ),
    )

    validation = validate_melee_declaration_rules(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=proposal,
        army_catalog=catalog,
        state=state,
    )
    sequence = melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("phase15d-extended-melee"),
        sequence_id="phase15d-extended-melee-sequence",
        state=state,
    )
    extended_model_id = attacker.own_models[1].model_instance_id
    extended_pool = next(
        pool
        for pool in sequence.attack_pools
        if pool.attacker_model_instance_id == extended_model_id
    )

    assert validation.is_valid
    assert len(engaged_rows) > 1
    assert "test:phase15d:extended-valid" in extended_pool.targeting_rule_ids
    assert extended_pool.target_in_range_model_ids == (target.own_models[0].model_instance_id,)


def test_phase15d_attached_rules_unit_melee_rejects_component_identity_and_omissions() -> None:
    (
        catalog,
        ruleset,
        scenario,
        state,
        rules_unit,
        bodyguard,
        _leader,
        target,
    ) = _attached_melee_fixture()
    available = rules_unit_available_melee_weapons_payloads(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        rules_unit=rules_unit,
        army_catalog=catalog,
        state=state,
        source_decision_result_id="phase15d-attached-source-result",
    )
    request = _rules_unit_melee_request(
        ruleset=ruleset,
        rules_unit=rules_unit,
        available=available,
        target_ids=(target.unit_instance_id,),
    )
    declaration = MeleeWeaponDeclaration(
        attacker_model_instance_id=bodyguard.own_models[0].model_instance_id,
        wargear_id="core-leader-blade",
        weapon_profile_id="core-leader-blade:standard",
        target_allocations=(MeleeTargetAllocation(target.unit_instance_id),),
    )
    incomplete = MeleeDeclarationProposal(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        player_id=request.actor_id,
        battle_round=request.battle_round,
        unit_instance_id=rules_unit.unit_instance_id,
        source_decision_request_id=request.source_decision_request_id,
        source_decision_result_id=request.source_decision_result_id,
        declarations=(declaration,),
    )

    identity_drift = validate_rules_unit_melee_declaration(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=replace(request, unit_instance_id=bodyguard.unit_instance_id),
        proposal=incomplete,
        army_catalog=catalog,
        state=state,
    )
    missing_component = validate_rules_unit_melee_declaration(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=incomplete,
        army_catalog=catalog,
        state=state,
    )
    outside_model = validate_rules_unit_melee_declaration(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=replace(
            incomplete,
            declarations=(
                replace(
                    declaration,
                    attacker_model_instance_id=target.own_models[0].model_instance_id,
                ),
            ),
        ),
        army_catalog=catalog,
        state=state,
    )

    assert identity_drift.violations[0].violation_code == "melee_rules_unit_identity_drift"
    assert missing_component.violations[0].violation_code == "melee_declaration_required"
    assert outside_model.violations[0].violation_code == "melee_model_outside_rules_unit"
    with pytest.raises(GameLifecycleError, match="canonical rules-unit identity"):
        rules_unit_melee_attack_sequence_from_proposal(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            proposal=replace(incomplete, unit_instance_id=bodyguard.unit_instance_id),
            army_catalog=catalog,
            dice_manager=DiceRollManager("phase15d-attached-component-identity"),
            sequence_id="phase15d-attached-component-identity-sequence",
            state=state,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="produced no attack pools"):
        rules_unit_melee_attack_sequence_from_proposal(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            proposal=replace(incomplete, declarations=()),
            army_catalog=catalog,
            dice_manager=DiceRollManager("phase15d-attached-empty"),
            sequence_id="phase15d-attached-empty-sequence",
            state=state,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )


def test_phase15d_rules_unit_melee_delegates_standalone_unit_semantics() -> None:
    catalog, ruleset, scenario, attacker, target, target_b = _melee_fixture(
        leader_keywords=(WeaponKeyword.ONE_SHOT,),
    )
    state = _attack_sequence_state(
        game_id="phase15d-standalone-rules-unit",
        ruleset=ruleset,
        scenario=scenario,
    )
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=attacker.unit_instance_id)
    direct_available = available_melee_weapons_payloads(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit=attacker,
        army_catalog=catalog,
        state=state,
        source_decision_result_id="phase15d-standalone-source-result",
    )
    available = rules_unit_available_melee_weapons_payloads(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        rules_unit=rules_unit,
        army_catalog=catalog,
        state=state,
        source_decision_result_id="phase15d-standalone-source-result",
    )
    request = _rules_unit_melee_request(
        ruleset=ruleset,
        rules_unit=rules_unit,
        available=available,
        target_ids=(target.unit_instance_id, target_b.unit_instance_id),
    )
    proposal = MeleeDeclarationProposal(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        player_id=request.actor_id,
        battle_round=request.battle_round,
        unit_instance_id=rules_unit.unit_instance_id,
        source_decision_request_id=request.source_decision_request_id,
        source_decision_result_id=request.source_decision_result_id,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(target.unit_instance_id),),
            ),
        ),
    )

    validation = validate_rules_unit_melee_declaration(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=proposal,
        army_catalog=catalog,
        state=state,
    )
    sequence = rules_unit_melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("phase15d-standalone-rules-unit"),
        sequence_id="phase15d-standalone-rules-unit-sequence",
        state=state,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    records = record_rules_unit_one_shot_melee_weapon_uses(
        state=state,
        scenario=scenario,
        proposal=proposal,
        army_catalog=catalog,
        result_id="phase15d-standalone-rules-unit-result",
    )

    assert validation.is_valid
    assert available == direct_available
    assert all(
        "rules_unit_instance_id" not in cast(dict[str, JsonValue], payload)
        and "component_unit_instance_id" not in cast(dict[str, JsonValue], payload)
        for payload in available
    )
    assert tuple(
        tuple(
            cast(
                list[str],
                cast(dict[str, JsonValue], payload)["engaged_target_unit_instance_ids"],
            )
        )
        for payload in available
    ) == ((target.unit_instance_id, target_b.unit_instance_id),)
    assert sequence.attacking_unit_instance_id == attacker.unit_instance_id
    assert len(sequence.attack_pools) == 1
    assert len(records) == 1


def test_phase15d_standalone_attacker_can_select_only_standalone_target_from_mixed_request() -> (
    None
):
    catalog = _catalog(include_extra_attacks=False)
    ruleset = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase15d-mixed-target-test"
    )
    alpha = muster_army(
        catalog=catalog,
        request=_army_request(
            catalog=catalog,
            army_id="army-alpha",
            player_id="player-a",
            unit_ids=("attacker",),
        ),
    )
    beta = muster_army(
        catalog=catalog,
        request=_army_request(
            catalog=catalog,
            army_id="army-beta",
            player_id="player-b",
            unit_ids=("target-bodyguard", "target-leader", "standalone-target"),
        ),
    )
    attacker = alpha.unit_by_id("army-alpha:attacker")
    target_bodyguard = beta.unit_by_id("army-beta:target-bodyguard")
    target_leader = beta.unit_by_id("army-beta:target-leader")
    standalone_target = beta.unit_by_id("army-beta:standalone-target")
    target_formation = AttachedUnitFormation(
        attached_unit_instance_id="attached-unit:army-beta:mixed-target",
        bodyguard_unit_instance_id=target_bodyguard.unit_instance_id,
        leader_unit_instance_ids=(target_leader.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((target_bodyguard.unit_instance_id, target_leader.unit_instance_id))
        ),
        source_id="test:phase15d:mixed-target",
        attachment_source_ids=("test:phase15d:mixed-target:eligibility",),
    )
    beta = replace(beta, attached_units=(target_formation,))
    armies = (alpha, beta)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase15d-mixed-target-battlefield",
        armies=armies,
    )
    battlefield = scenario.battlefield_state
    for unit, army_id, player_id, pose in (
        (attacker, "army-alpha", "player-a", Pose.at(10.0, 10.0)),
        (target_bodyguard, "army-beta", "player-b", Pose.at(12.0, 9.6)),
        (target_leader, "army-beta", "player-b", Pose.at(12.0, 10.4)),
        (standalone_target, "army-beta", "player-b", Pose.at(10.0, 12.0)),
    ):
        battlefield = battlefield.with_unit_placement(
            _unit_placement(unit, army_id=army_id, player_id=player_id, pose=pose)
        )
    scenario = BattlefieldScenario(armies=armies, battlefield_state=battlefield)
    state = _attack_sequence_state(
        game_id="phase15d-mixed-target",
        ruleset=ruleset,
        scenario=scenario,
    )
    attacker_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=attacker.unit_instance_id,
    )
    target_ids = rules_unit_melee_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        rules_unit=attacker_rules_unit,
        state=state,
    )
    available = rules_unit_available_melee_weapons_payloads(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        rules_unit=attacker_rules_unit,
        army_catalog=catalog,
        state=state,
        source_decision_result_id="phase15d-mixed-target-source-result",
    )
    request = _rules_unit_melee_request(
        ruleset=ruleset,
        rules_unit=attacker_rules_unit,
        available=available,
        target_ids=target_ids,
    )
    proposal = MeleeDeclarationProposal(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        player_id=request.actor_id,
        battle_round=request.battle_round,
        unit_instance_id=attacker.unit_instance_id,
        source_decision_request_id=request.source_decision_request_id,
        source_decision_result_id=request.source_decision_result_id,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=attacker.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(standalone_target.unit_instance_id),),
            ),
        ),
    )

    validation = validate_rules_unit_melee_declaration(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=proposal,
        army_catalog=catalog,
        state=state,
    )

    assert target_ids == tuple(
        sorted((target_formation.attached_unit_instance_id, standalone_target.unit_instance_id))
    )
    assert validation.is_valid


def test_phase15d_attached_rules_unit_melee_skips_destroyed_component() -> None:
    (
        catalog,
        ruleset,
        scenario,
        state,
        rules_unit,
        bodyguard,
        _leader,
        target,
    ) = _attached_melee_fixture(
        leader_keywords=(WeaponKeyword.ONE_SHOT,),
        leader_alive=False,
    )
    available = rules_unit_available_melee_weapons_payloads(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        rules_unit=rules_unit,
        army_catalog=catalog,
        state=state,
        source_decision_result_id="phase15d-attached-source-result",
    )
    request = _rules_unit_melee_request(
        ruleset=ruleset,
        rules_unit=rules_unit,
        available=available,
        target_ids=(target.unit_instance_id,),
    )
    proposal = MeleeDeclarationProposal(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        player_id=request.actor_id,
        battle_round=request.battle_round,
        unit_instance_id=rules_unit.unit_instance_id,
        source_decision_request_id=request.source_decision_request_id,
        source_decision_result_id=request.source_decision_result_id,
        declarations=(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=bodyguard.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(target.unit_instance_id),),
            ),
        ),
    )

    validation = validate_rules_unit_melee_declaration(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        request=request,
        proposal=proposal,
        army_catalog=catalog,
        state=state,
    )
    sequence = rules_unit_melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("phase15d-destroyed-component"),
        sequence_id="phase15d-destroyed-component-sequence",
        state=state,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    records = record_rules_unit_one_shot_melee_weapon_uses(
        state=state,
        scenario=scenario,
        proposal=proposal,
        army_catalog=catalog,
        result_id="phase15d-destroyed-component-result",
    )

    assert validation.is_valid
    assert len(available) == 1
    assert sequence.attack_pools[0].attacker_model_instance_id == (
        bodyguard.own_models[0].model_instance_id
    )
    assert len(records) == 1


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


def test_phase14e_melee_cleave_adds_single_target_attacks_from_target_model_count() -> None:
    catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        leader_keywords=(WeaponKeyword.CLEAVE,),
        leader_abilities=(AbilityDescriptor.cleave(2),),
        target_a_datasheet_id="core-intercessor-like-infantry",
        target_a_model_profile_id="core-intercessor-like",
        target_a_model_count=10,
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
                target_allocations=(MeleeTargetAllocation(target_a.unit_instance_id, attacks=9),),
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
        dice_manager=DiceRollManager("phase14e-melee-cleave"),
        sequence_id="phase14e-melee-cleave-sequence",
    )

    assert validation.is_valid
    assert len(target_a.alive_own_models()) == 10
    assert sequence.attack_pools[0].attacks == 9
    assert sequence.attack_pools[0].targeting_rule_ids == (
        MELEE_TARGETING_RULE_ID,
        f"{CLEAVE_RULE_ID}:4",
    )


def test_phase14e_melee_lance_uses_charge_move_wound_modifier() -> None:
    catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        leader_keywords=(WeaponKeyword.LANCE,),
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
    state = _attack_sequence_state(
        game_id="phase14e-melee-lance",
        ruleset=ruleset,
        scenario=scenario,
    )
    _record_charge_move_effect(state=state, unit=attacker)
    sequence = melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("phase14e-melee-lance-attacks"),
        sequence_id="phase14e-melee-lance-sequence",
        state=state,
    )
    attack_context_id = sequence.attack_context_id()
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=sequence.current_pool().weapon_profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id=sequence.attacker_player_id,
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=sequence.current_pool().weapon_profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id=sequence.attacker_player_id,
    )
    decisions = DecisionController()
    dice_manager = DiceRollManager(
        "phase14e-melee-lance-resolution",
        event_log=decisions.event_log,
        injected_results=(
            _fixed_roll_result(roll_id="phase14e-lance-hit", spec=hit_spec, value=3),
            _fixed_roll_result(roll_id="phase14e-lance-wound", spec=wound_spec, value=2),
        ),
    )

    resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset,
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )
    wound_payload = _attack_step_payload(decisions, AttackSequenceStep.WOUND)

    assert LANCE_RULE_ID in sequence.attack_pools[0].targeting_rule_ids
    assert wound_payload["modifier"] == 1
    assert wound_payload["capped_modifier"] == 1
    assert wound_payload["final_roll"] == 3
    assert wound_payload["successful"] is True


def test_hit_roll_bonus_cap_applies_after_weapon_skill_modifier() -> None:
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
    state = _attack_sequence_state(
        game_id="ws-penalty-hit-roll-bonus",
        ruleset=ruleset,
        scenario=scenario,
    )
    sequence = melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("ws-penalty-hit-roll-bonus-attacks"),
        sequence_id="ws-penalty-hit-roll-bonus",
        state=state,
    )
    base_profile = replace(
        sequence.current_pool().weapon_profile,
        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 4),
    )
    worsened_profile = replace(
        base_profile,
        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 5),
    )
    sequence = replace(
        sequence,
        attack_pools=(
            replace(
                sequence.current_pool(),
                attacks=1,
                weapon_profile=worsened_profile,
                hit_roll_modifier=2,
            ),
        ),
    )
    attack_context_id = sequence.attack_context_id()
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=worsened_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id=sequence.attacker_player_id,
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=worsened_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id=sequence.attacker_player_id,
    )
    decisions = DecisionController()

    resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset,
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "ws-penalty-hit-roll-bonus-resolution",
            event_log=decisions.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="ws-penalty-hit-roll-bonus-hit", spec=hit_spec, value=4),
                _fixed_roll_result(
                    roll_id="ws-penalty-hit-roll-bonus-wound",
                    spec=wound_spec,
                    value=1,
                ),
            ),
        ),
    )
    hit_payload = _attack_step_payload(decisions, AttackSequenceStep.HIT)

    assert hit_payload["target_number"] == 5
    assert hit_payload["modifier"] == 2
    assert hit_payload["capped_modifier"] == 1
    assert hit_payload["final_roll"] == 5
    assert hit_payload["successful"] is True


def test_phase18b_command_reroll_window_opens_after_fight_hit_roll() -> None:
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
    state = _attack_sequence_state(
        game_id="phase18b-fight-command-reroll-hit",
        ruleset=ruleset,
        scenario=scenario,
    )
    state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="phase18b-fight-command-reroll-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )
    sequence = melee_attack_sequence_from_proposal(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        army_catalog=catalog,
        dice_manager=DiceRollManager("phase18b-fight-command-reroll-attacks"),
        sequence_id="phase18b-fight-command-reroll-hit",
        state=state,
    )
    attack_context_id = sequence.attack_context_id()
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=sequence.current_pool().weapon_profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id=sequence.attacker_player_id,
    )
    decisions = DecisionController()

    _remaining, _allocated, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset,
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase18b-fight-command-reroll-hit",
            event_log=decisions.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase18b-fight-command-reroll-hit-roll",
                    spec=hit_spec,
                    value=2,
                ),
            ),
        ),
        stratagem_index=eleventh_edition_stratagem_index(),
    )

    assert status is not None
    stratagem_request = status.decision_request
    assert stratagem_request is not None
    assert stratagem_request.decision_type == "use_stratagem"
    assert stratagem_request.actor_id == "player-a"
    status_payload = cast(dict[str, object], status.payload)
    assert status_payload["phase"] == BattlePhase.FIGHT.value
    assert status_payload["phase_body_status"] == "attack_hit_command_reroll_pending"
    option_ids = {option.option_id for option in stratagem_request.options}
    assert any(option_id.startswith("use-stratagem:command-reroll:") for option_id in option_ids)
    payload = cast(dict[str, object], stratagem_request.payload)
    context = cast(dict[str, object], payload["stratagem_context"])
    trigger_payload = cast(dict[str, object], context["trigger_payload"])
    assert trigger_payload["roll_type"] == "attack_sequence.hit"
    assert trigger_payload["affected_unit_instance_id"] == attacker.unit_instance_id


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
        own_models=tuple(
            replace(model, wargear_ids=("core-leader-blade", "core-second-blade"))
            if model.model_profile_id == "core-character-leader"
            else model
            for model in attacker.own_models
        ),
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
        own_models=tuple(
            replace(model, wargear_ids=("core-missing-blade",))
            if model.model_profile_id == "core-character-leader"
            else model
            for model in attacker.own_models
        ),
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


def test_phase15d_attached_pile_in_moves_every_component_atomically() -> None:
    (
        _catalog,
        ruleset,
        scenario,
        state,
        rules_unit,
        bodyguard,
        leader,
        target,
    ) = _attached_melee_fixture()
    leader_placement = scenario.battlefield_state.unit_placement_by_id(leader.unit_instance_id)
    spaced_leader_placement = leader_placement.with_model_placements(
        tuple(
            placement.with_pose(Pose.at(10.0, 11.4))
            for placement in leader_placement.model_placements
        )
    )
    spaced_battlefield = scenario.battlefield_state.with_unit_placement(spaced_leader_placement)
    scenario = replace(scenario, battlefield_state=spaced_battlefield)
    state.replace_battlefield_state(spaced_battlefield)
    request = _rules_unit_fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        rules_unit=rules_unit,
    )
    witness = _movement_witness_for_rules_unit(
        scenario=scenario,
        rules_unit=rules_unit,
        dx=0.25,
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=rules_unit.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target.unit_instance_id,),
        witness=witness,
    )

    assert legal_rules_unit_pile_in_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=rules_unit.unit_instance_id,
        state=state,
    ) == (target.unit_instance_id,)
    assert fight_rules_unit_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=proposal,
        eligible_unit_ids=(rules_unit.unit_instance_id,),
        state=state,
    ).is_valid
    assert (
        fight_rules_unit_movement_witness_matches_current_status(
            state=state,
            scenario=scenario,
            proposal_request=request,
            proposal=proposal,
        )
        is None
    )

    resolution = resolve_rules_unit_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        maximum_distance_inches=3.0,
        state=state,
    )
    assert isinstance(resolution, RulesUnitFightMovementResolution)
    assert (
        fight_rules_unit_movement_resolution_violation(
            proposal_request=request,
            proposal=proposal,
            resolution=resolution,
            scenario=scenario,
            ruleset_descriptor=ruleset,
            state=state,
        )
        is None
    )
    transition = fight_rules_unit_movement_transition_batch(
        scenario=scenario,
        resolution=resolution,
    )
    updated = apply_fight_rules_unit_movement_resolution(
        battlefield_state=scenario.battlefield_state,
        resolution=resolution,
    )
    round_trip = RulesUnitFightMovementResolution.from_payload(resolution.to_payload())

    moved_model_ids = {
        bodyguard.own_models[0].model_instance_id,
        leader.own_models[0].model_instance_id,
    }
    assert {record.model_instance_id for record in transition.displacements} == moved_model_ids
    assert resolution.endpoint_witness["target_unit_instance_ids"] == [target.unit_instance_id]
    assert resolution.endpoint_witness["engaged_after_unit_ids"] == [target.unit_instance_id]
    assert round_trip.to_payload() == resolution.to_payload()
    for model_id in moved_model_ids:
        assert (
            updated.model_placement_by_id(model_id).pose.position.x
            == scenario.battlefield_state.model_placement_by_id(model_id).pose.position.x + 0.25
        )


def test_phase15d_retained_destroyed_source_base_stays_a_fixed_endpoint_blocker() -> None:
    (
        _catalog,
        ruleset,
        scenario,
        state,
        rules_unit,
        bodyguard,
        leader,
        target,
    ) = _attached_melee_fixture()
    battlefield = scenario.battlefield_state
    bodyguard_placement = battlefield.unit_placement_by_id(bodyguard.unit_instance_id)
    leader_placement = battlefield.unit_placement_by_id(leader.unit_instance_id)
    target_placement = battlefield.unit_placement_by_id(target.unit_instance_id)
    battlefield = battlefield.with_unit_placement(
        bodyguard_placement.with_model_placements(
            tuple(
                placement.with_pose(Pose.at(10.0, 10.0))
                for placement in bodyguard_placement.model_placements
            )
        )
    )
    battlefield = battlefield.with_unit_placement(
        leader_placement.with_model_placements(
            tuple(
                placement.with_pose(Pose.at(8.0, 10.0))
                for placement in leader_placement.model_placements
            )
        )
    )
    battlefield = battlefield.with_unit_placement(
        target_placement.with_model_placements(
            tuple(
                placement.with_pose(Pose.at(13.0, 10.0))
                for placement in target_placement.model_placements
            )
        )
    )
    state.replace_battlefield_state(battlefield)
    destroyed_model = bodyguard.own_models[0]
    destroyed_placement = battlefield.model_placement_by_id(destroyed_model.model_instance_id)
    damage = apply_damage_to_model(
        state=state,
        target_unit_instance_id=bodyguard.unit_instance_id,
        model_instance_id=destroyed_model.model_instance_id,
        damage=destroyed_model.wounds_remaining,
        damage_kind=DamageKind.NORMAL,
    )
    assert damage.destroyed
    restore_model_awaiting_fight_on_death(
        state=state,
        placement=destroyed_placement,
        effect_id="phase15d:fight-on-death:fixed-source-blocker",
        source_rule_id="phase15d:test:fight-on-death",
        source_phase=BattlePhaseKind.FIGHT,
    )
    current_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=rules_unit.unit_instance_id,
    )
    retained_battlefield = state.battlefield_state
    assert retained_battlefield is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=retained_battlefield,
        present_destroyed_model_ids=(destroyed_model.model_instance_id,),
    )
    living_model = current_rules_unit.alive_models()[0]
    living_start = scenario.battlefield_state.model_placement_by_id(
        living_model.model_instance_id
    ).pose
    witness = PathWitness.for_paths(
        (
            (
                living_model.model_instance_id,
                (
                    living_start,
                    Pose.at(9.0, 10.0),
                    destroyed_placement.pose,
                ),
            ),
        )
    )
    request = _rules_unit_fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        rules_unit=current_rules_unit,
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=current_rules_unit.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target.unit_instance_id,),
        witness=witness,
    )

    witness_with_destroyed_model = PathWitness.for_paths(
        (
            *tuple(
                (
                    model_id,
                    witness.poses_for_model(model_id),
                )
                for model_id in witness.model_ids()
            ),
            (
                destroyed_model.model_instance_id,
                (
                    destroyed_placement.pose,
                    Pose.at(
                        destroyed_placement.pose.position.x + 0.25,
                        destroyed_placement.pose.position.y,
                    ),
                ),
            ),
        )
    )
    destroyed_model_witness_violation = fight_rules_unit_movement_witness_matches_current_status(
        state=state,
        scenario=scenario,
        proposal_request=request,
        proposal=replace(proposal, witness=witness_with_destroyed_model),
    )
    assert destroyed_model_witness_violation is not None
    assert (
        destroyed_model_witness_violation.violations[0].violation_code
        == "fight_movement_witness_model_drift"
    )

    assert (
        fight_rules_unit_movement_witness_matches_current_status(
            state=state,
            scenario=scenario,
            proposal_request=request,
            proposal=proposal,
        )
        is None
    )
    resolution = resolve_rules_unit_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        maximum_distance_inches=3.0,
        state=state,
    )
    assert isinstance(resolution, RulesUnitFightMovementResolution)
    assert not resolution.is_valid
    violation = fight_rules_unit_movement_resolution_violation(
        proposal_request=request,
        proposal=proposal,
        resolution=resolution,
        scenario=scenario,
        ruleset_descriptor=ruleset,
        state=state,
    )
    assert violation is not None
    assert violation.violations[0].violation_code == "end_on_model_overlap"
    with pytest.raises(GameLifecycleError, match="cannot mutate"):
        apply_fight_rules_unit_movement_resolution(
            battlefield_state=scenario.battlefield_state,
            resolution=resolution,
        )
    assert (
        scenario.battlefield_state.model_placement_by_id(destroyed_model.model_instance_id).pose
        == destroyed_placement.pose
    )


def test_phase15d_retained_destroyed_target_still_supports_fight_movement_measurement() -> None:
    _catalog, ruleset, scenario, attacker, target, _target_b = _melee_fixture(
        target_a_pose=Pose.at(14.5, 10.0),
        target_b_pose=Pose.at(30.0, 30.0),
    )
    state = _attack_sequence_state(
        game_id="phase15d-retained-target-movement-measurement",
        ruleset=ruleset,
        scenario=scenario,
    )
    target_model = target.own_models[0]
    target_placement = scenario.battlefield_state.model_placement_by_id(
        target_model.model_instance_id
    )
    damage = apply_damage_to_model(
        state=state,
        target_unit_instance_id=target.unit_instance_id,
        model_instance_id=target_model.model_instance_id,
        damage=target_model.wounds_remaining,
        damage_kind=DamageKind.NORMAL,
    )
    assert damage.destroyed
    restore_model_awaiting_fight_on_death(
        state=state,
        placement=target_placement,
        effect_id="phase15d:fight-on-death:measurement-target",
        source_rule_id="phase15d:test:fight-on-death",
        source_phase=BattlePhaseKind.FIGHT,
    )
    retained_battlefield = state.battlefield_state
    assert retained_battlefield is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=retained_battlefield,
        present_destroyed_model_ids=(target_model.model_instance_id,),
    )

    assert legal_rules_unit_pile_in_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=attacker.unit_instance_id,
        state=state,
    ) == (target.unit_instance_id,)
    assert legal_rules_unit_consolidation_modes(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=attacker.unit_instance_id,
        objective_markers=(),
        state=state,
    ) == (ConsolidationModeKind.ENGAGING,)


def test_phase15d_grouped_completed_event_accepts_living_component_subset() -> None:
    (
        _catalog,
        ruleset,
        scenario,
        state,
        rules_unit,
        bodyguard,
        leader,
        target,
    ) = _attached_melee_fixture()
    battlefield = scenario.battlefield_state
    component_poses = (
        (bodyguard, Pose.at(5.0, 10.0)),
        (leader, Pose.at(10.0, 10.0)),
        (target, Pose.at(12.0, 10.0)),
    )
    for unit, pose in component_poses:
        placement = battlefield.unit_placement_by_id(unit.unit_instance_id)
        battlefield = battlefield.with_unit_placement(
            placement.with_model_placements(
                tuple(
                    model_placement.with_pose(pose)
                    for model_placement in placement.model_placements
                )
            )
        )
    state.replace_battlefield_state(battlefield)

    destroyed_model = bodyguard.own_models[0]
    destroyed_placement = battlefield.model_placement_by_id(destroyed_model.model_instance_id)
    damage = apply_damage_to_model(
        state=state,
        target_unit_instance_id=bodyguard.unit_instance_id,
        model_instance_id=destroyed_model.model_instance_id,
        damage=destroyed_model.wounds_remaining,
        damage_kind=DamageKind.NORMAL,
    )
    assert damage.destroyed
    restore_model_awaiting_fight_on_death(
        state=state,
        placement=destroyed_placement,
        effect_id="phase15d:fight-on-death:completed-event-component-subset",
        source_rule_id="phase15d:test:fight-on-death",
        source_phase=BattlePhaseKind.FIGHT,
    )
    retained_battlefield = state.battlefield_state
    assert retained_battlefield is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=retained_battlefield,
        present_destroyed_model_ids=(destroyed_model.model_instance_id,),
    )
    current_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=rules_unit.unit_instance_id,
    )
    living_model = leader.own_models[0]
    living_start = scenario.battlefield_state.model_placement_by_id(
        living_model.model_instance_id
    ).pose
    witness = PathWitness.for_paths(
        (
            (
                living_model.model_instance_id,
                (
                    living_start,
                    Pose.at(10.125, 10.0),
                    Pose.at(10.25, 10.0),
                ),
            ),
        )
    )
    request = _rules_unit_fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        rules_unit=current_rules_unit,
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=current_rules_unit.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target.unit_instance_id,),
        witness=witness,
    )
    resolution = resolve_rules_unit_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        maximum_distance_inches=3.0,
        state=state,
    )
    assert isinstance(resolution, RulesUnitFightMovementResolution)
    assert resolution.is_valid
    assert (
        fight_rules_unit_movement_resolution_violation(
            proposal_request=request,
            proposal=proposal,
            resolution=resolution,
            scenario=scenario,
            ruleset_descriptor=ruleset,
            state=state,
        )
        is None
    )
    assert resolution.before_rules_unit_placement.component_unit_instance_ids == (
        leader.unit_instance_id,
    )
    assert current_rules_unit.component_unit_instance_ids == tuple(
        sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
    )
    event_payload: dict[str, object] = {
        "unit_instance_id": resolution.unit_instance_id,
        "proposal_kind": proposal.proposal_kind.value,
        "resolution": resolution.to_payload(),
        "transition_batch": resolution.transition_batch().to_payload(),
    }

    assert (
        fight_rules_unit_movement_endpoint_from_completed_event(
            payload=cast(dict[str, JsonValue], event_payload),
            component_unit_instance_ids=current_rules_unit.component_unit_instance_ids,
        )
        == resolution.attempted_rules_unit_placement
    )


def test_phase15d_grouped_fight_placement_and_rollback_records_fail_fast() -> None:
    ruleset, scenario, _state, _rules_unit, _request, _proposal, resolution = (
        _resolved_attached_pile_in_fixture()
    )
    before = resolution.before_rules_unit_placement
    attempted = resolution.attempted_rules_unit_placement
    reversed_placement = FightRulesUnitPlacement(
        rules_unit_instance_id=before.rules_unit_instance_id,
        component_unit_placements=tuple(reversed(before.component_unit_placements)),
    )
    assert reversed_placement.component_unit_instance_ids == tuple(
        sorted(reversed_placement.component_unit_instance_ids)
    )
    assert reversed_placement.model_placements == before.model_placements
    assert FightRulesUnitPlacement.from_payload(before.to_payload()) == before

    foreign_component = scenario.battlefield_state.unit_placement_by_id("army-beta:target")
    malformed_placements: tuple[tuple[Callable[[], FightRulesUnitPlacement], str], ...] = (
        (
            lambda: FightRulesUnitPlacement(
                rules_unit_instance_id="army-alpha:bodyguard",
                component_unit_placements=before.component_unit_placements,
            ),
            "canonical attached-unit identity",
        ),
        (
            lambda: FightRulesUnitPlacement(
                rules_unit_instance_id=before.rules_unit_instance_id,
                component_unit_placements=cast(tuple[UnitPlacement, ...], []),
            ),
            "must be a tuple",
        ),
        (
            lambda: FightRulesUnitPlacement(
                rules_unit_instance_id=before.rules_unit_instance_id,
                component_unit_placements=(),
            ),
            "requires present components",
        ),
        (
            lambda: FightRulesUnitPlacement(
                rules_unit_instance_id=before.rules_unit_instance_id,
                component_unit_placements=(cast(UnitPlacement, object()),),
            ),
            "must be UnitPlacement",
        ),
        (
            lambda: FightRulesUnitPlacement(
                rules_unit_instance_id=before.rules_unit_instance_id,
                component_unit_placements=(
                    before.component_unit_placements[0],
                    before.component_unit_placements[0],
                ),
            ),
            "component IDs must be unique",
        ),
        (
            lambda: FightRulesUnitPlacement(
                rules_unit_instance_id=before.rules_unit_instance_id,
                component_unit_placements=(
                    before.component_unit_placements[0],
                    foreign_component,
                ),
            ),
            "must share one owner",
        ),
    )
    for construct, message in malformed_placements:
        with pytest.raises(GameLifecycleError, match=message):
            construct()

    model_ids = tuple(model.model_instance_id for model in before.model_placements)
    coherency_violation = UnitCoherencyViolation(
        model_instance_id=model_ids[0],
        violation_code="phase15d-grouped-coherency-break",
    )
    broken_coherency = UnitCoherencyResult(
        status=UnitCoherencyStatus.BROKEN,
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        unit_instance_id=before.rules_unit_instance_id,
        coherency_policy=ruleset.coherency_policy,
        model_instance_ids=model_ids,
        violations=(coherency_violation,),
    )
    rollback = RulesUnitMovementRollbackRecord(
        unit_instance_id=before.rules_unit_instance_id,
        displacement_kind=ModelDisplacementKind.PILE_IN,
        before_rules_unit_placement=before,
        attempted_rules_unit_placement=attempted,
        coherency_result=broken_coherency,
    )
    assert RulesUnitMovementRollbackRecord.from_payload(rollback.to_payload()) == rollback

    one_component = FightRulesUnitPlacement(
        rules_unit_instance_id=before.rules_unit_instance_id,
        component_unit_placements=(attempted.component_unit_placements[0],),
    )
    first_component = attempted.component_unit_placements[0]
    first_model = first_component.model_placements[0]
    drifted_component = first_component.with_model_placements(
        (
            replace(
                first_model,
                model_instance_id=f"{first_component.unit_instance_id}:tampered-model",
            ),
        )
    )
    model_drift = FightRulesUnitPlacement(
        rules_unit_instance_id=before.rules_unit_instance_id,
        component_unit_placements=(drifted_component, *attempted.component_unit_placements[1:]),
    )
    assert resolution.coherency_result is not None
    malformed_rollbacks = (
        ({"displacement_kind": cast(ModelDisplacementKind, object())}, "must be typed"),
        (
            {"before_rules_unit_placement": cast(FightRulesUnitPlacement, object())},
            "before placement must be grouped",
        ),
        (
            {"attempted_rules_unit_placement": cast(FightRulesUnitPlacement, object())},
            "attempted placement must be grouped",
        ),
        (
            {"coherency_result": cast(UnitCoherencyResult, object())},
            "coherency result must be typed",
        ),
        ({"unit_instance_id": "attached-unit:drifted"}, "identity drift"),
        ({"attempted_rules_unit_placement": one_component}, "component identity drift"),
        ({"attempted_rules_unit_placement": model_drift}, "model identity drift"),
        (
            {
                "coherency_result": replace(
                    broken_coherency,
                    unit_instance_id="attached-unit:drifted",
                )
            },
            "coherency identity drift",
        ),
        (
            {
                "coherency_result": replace(
                    broken_coherency,
                    model_instance_ids=model_ids[:-1],
                    violations=(),
                    status=UnitCoherencyStatus.COHERENT,
                )
            },
            "coherency model identity drift",
        ),
        ({"coherency_result": resolution.coherency_result}, "requires broken coherency"),
    )
    for changes, message in malformed_rollbacks:
        with pytest.raises(GameLifecycleError, match=message):
            replace(rollback, **changes)


def test_phase15d_grouped_fight_resolution_rejects_context_and_evidence_drift() -> None:
    ruleset, _scenario, _state, _rules_unit, _request, _proposal, resolution = (
        _resolved_attached_pile_in_fixture()
    )
    before = resolution.before_rules_unit_placement
    attempted = resolution.attempted_rules_unit_placement
    drifted_identity = FightRulesUnitPlacement(
        rules_unit_instance_id="attached-unit:drifted",
        component_unit_placements=attempted.component_unit_placements,
    )
    one_component = FightRulesUnitPlacement(
        rules_unit_instance_id=attempted.rules_unit_instance_id,
        component_unit_placements=(attempted.component_unit_placements[0],),
    )
    first_component = attempted.component_unit_placements[0]
    first_model = first_component.model_placements[0]
    model_drift = FightRulesUnitPlacement(
        rules_unit_instance_id=attempted.rules_unit_instance_id,
        component_unit_placements=(
            first_component.with_model_placements(
                (
                    replace(
                        first_model,
                        model_instance_id=f"{first_component.unit_instance_id}:drifted-model",
                    ),
                )
            ),
            *attempted.component_unit_placements[1:],
        ),
    )
    invalid_path = PathValidationResult.invalid(
        PathConstraintViolation(
            violation_code="phase15d-grouped-path-invalid",
            message="phase15d-grouped-path-invalid",
        ),
        sampled_pose_count=1,
        model_collision_check_count=1,
        terrain_collision_check_count=0,
        engagement_check_count=0,
    )
    invalid_terrain = TerrainPathLegalityResult.invalid(
        TerrainTraversalViolation(
            violation_code="phase15d-grouped-terrain-invalid",
            message="phase15d-grouped-terrain-invalid",
        ),
        segments=(),
        sampled_pose_count=1,
    )
    assert resolution.coherency_result is not None
    model_ids = tuple(model.model_instance_id for model in before.model_placements)
    broken_coherency = UnitCoherencyResult(
        status=UnitCoherencyStatus.BROKEN,
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        unit_instance_id=before.rules_unit_instance_id,
        coherency_policy=ruleset.coherency_policy,
        model_instance_ids=model_ids,
        violations=(
            UnitCoherencyViolation(
                model_instance_id=model_ids[0],
                violation_code="phase15d-grouped-resolution-coherency-break",
            ),
        ),
    )
    rollback = RulesUnitMovementRollbackRecord(
        unit_instance_id=before.rules_unit_instance_id,
        displacement_kind=ModelDisplacementKind.PILE_IN,
        before_rules_unit_placement=before,
        attempted_rules_unit_placement=attempted,
        coherency_result=broken_coherency,
    )
    moved_ids = resolution.endpoint_witness["moved_model_instance_ids"]
    endpoint_without_moved_model = dict(resolution.endpoint_witness)
    endpoint_without_moved_model["moved_model_instance_ids"] = moved_ids[:-1]
    malformed_endpoint = dict(resolution.endpoint_witness)
    malformed_endpoint.pop("objective_id")
    unsorted_targets = dict(resolution.endpoint_witness)
    unsorted_targets["target_unit_instance_ids"] = ["target-z", "target-a"]
    duplicate_engagements = dict(resolution.endpoint_witness)
    duplicate_engagements["engaged_after_unit_ids"] = ["target-a", "target-a"]
    invalid_objective = dict(resolution.endpoint_witness)
    invalid_objective["objective_id"] = 42
    assert resolution.witness is not None
    witness_paths = resolution.witness.model_paths
    first_witness_model_id, first_witness_poses = witness_paths[0]
    partial_witness = PathWitness.for_paths(witness_paths[:-1])
    start_drift_witness = PathWitness.for_paths(
        (
            (first_witness_model_id, (first_witness_poses[-1], *first_witness_poses[1:])),
            *witness_paths[1:],
        )
    )
    endpoint_drift_witness = PathWitness.for_paths(
        (
            (first_witness_model_id, (*first_witness_poses[:-1], first_witness_poses[0])),
            *witness_paths[1:],
        )
    )
    coherency_identity_drift = replace(
        resolution.coherency_result,
        unit_instance_id="attached-unit:drifted",
    )
    coherency_model_drift = replace(
        resolution.coherency_result,
        model_instance_ids=model_ids[:-1],
    )
    mismatched_rollback = replace(
        rollback,
        displacement_kind=ModelDisplacementKind.CONSOLIDATE,
    )

    malformed_resolutions = (
        ({"movement_phase_action": cast(str, 42)}, "action must be a string"),
        ({"movement_phase_action": ""}, "action must be a string"),
        ({"movement_mode": cast(MovementMode, "pile_in")}, "mode must be typed"),
        ({"movement_phase_action": CONSOLIDATE_ACTION}, "action/mode context drift"),
        ({"movement_mode": MovementMode.CONSOLIDATE}, "action/mode context drift"),
        ({"maximum_distance_inches": cast(float, "three")}, "distance must be numeric"),
        ({"maximum_distance_inches": 0.0}, "distance must be positive"),
        (
            {"before_rules_unit_placement": cast(FightRulesUnitPlacement, object())},
            "placements must be grouped",
        ),
        (
            {"attempted_rules_unit_placement": cast(FightRulesUnitPlacement, object())},
            "placements must be grouped",
        ),
        ({"attempted_rules_unit_placement": drifted_identity}, "placement identity drift"),
        ({"attempted_rules_unit_placement": one_component}, "component identity drift"),
        ({"attempted_rules_unit_placement": model_drift}, "model identity drift"),
        (
            {"endpoint_witness": cast(FightMovementEndpointPayload, malformed_endpoint)},
            "endpoint witness shape drifted",
        ),
        (
            {"endpoint_witness": cast(FightMovementEndpointPayload, endpoint_without_moved_model)},
            "endpoint witness model identity drift",
        ),
        (
            {"endpoint_witness": cast(FightMovementEndpointPayload, unsorted_targets)},
            "must be sorted and unique",
        ),
        (
            {"endpoint_witness": cast(FightMovementEndpointPayload, duplicate_engagements)},
            "must be sorted and unique",
        ),
        (
            {"endpoint_witness": cast(FightMovementEndpointPayload, invalid_objective)},
            "objective_id",
        ),
        ({"witness": cast(PathWitness, object())}, "witness must be typed"),
        ({"witness": partial_witness}, "witness model inventory drifted"),
        ({"witness": start_drift_witness}, "witness start pose drifted"),
        ({"witness": endpoint_drift_witness}, "witness endpoint pose drifted"),
        (
            {"path_validation_results": cast(tuple[PathValidationResult, ...], [])},
            "path results must be typed",
        ),
        (
            {"path_validation_results": (cast(PathValidationResult, object()),)},
            "path results must be typed",
        ),
        (
            {"terrain_path_legality_results": cast(tuple[TerrainPathLegalityResult, ...], [])},
            "terrain results must be typed",
        ),
        (
            {"terrain_path_legality_results": (cast(TerrainPathLegalityResult, object()),)},
            "terrain results must be typed",
        ),
        (
            {"coherency_result": cast(UnitCoherencyResult, object())},
            "coherency result must be typed",
        ),
        ({"coherency_result": None}, "requires coherency evidence"),
        ({"coherency_result": coherency_identity_drift}, "coherency identity drifted"),
        ({"coherency_result": coherency_model_drift}, "coherency model identity drifted"),
        (
            {"coherency_result": broken_coherency},
            "coherency requires a rollback record",
        ),
        ({"rollback_record": rollback}, "must not include a rollback record"),
        (
            {
                "coherency_result": broken_coherency,
                "rollback_record": mismatched_rollback,
            },
            "rollback evidence drifted",
        ),
        (
            {"rollback_record": cast(RulesUnitMovementRollbackRecord, object())},
            "rollback record must be typed",
        ),
    )
    for changes, message in malformed_resolutions:
        with pytest.raises(GameLifecycleError, match=message):
            replace(resolution, **changes)

    invalid_path_resolution = replace(resolution, path_validation_results=(invalid_path,))
    invalid_terrain_resolution = replace(
        resolution,
        terrain_path_legality_results=(invalid_terrain,),
    )
    rollback_resolution = replace(
        resolution,
        coherency_result=broken_coherency,
        rollback_record=rollback,
    )
    assert not invalid_path_resolution.is_valid
    assert not invalid_terrain_resolution.is_valid
    assert not rollback_resolution.is_valid
    for invalid_resolution in (
        invalid_path_resolution,
        invalid_terrain_resolution,
        rollback_resolution,
    ):
        with pytest.raises(GameLifecycleError, match="has no transition"):
            invalid_resolution.transition_batch()
    with pytest.raises(GameLifecycleError, match="requires a witness"):
        replace(resolution, witness=None)


def test_phase15d_grouped_fight_resolution_payload_round_trips_and_rejects_tampering() -> None:
    ruleset, scenario, state, rules_unit, _request, _proposal, resolution = (
        _resolved_attached_pile_in_fixture()
    )
    payload = resolution.to_payload()
    assert RulesUnitFightMovementResolution.from_payload(payload) == resolution

    broken_coherency = UnitCoherencyResult(
        status=UnitCoherencyStatus.BROKEN,
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        unit_instance_id=resolution.unit_instance_id,
        coherency_policy=ruleset.coherency_policy,
        model_instance_ids=tuple(
            model.model_instance_id
            for model in resolution.before_rules_unit_placement.model_placements
        ),
        violations=(
            UnitCoherencyViolation(
                model_instance_id=resolution.before_rules_unit_placement.model_placements[
                    0
                ].model_instance_id,
                violation_code="phase15d-grouped-payload-coherency-break",
            ),
        ),
    )
    rollback = RulesUnitMovementRollbackRecord(
        unit_instance_id=resolution.unit_instance_id,
        displacement_kind=ModelDisplacementKind.PILE_IN,
        before_rules_unit_placement=resolution.before_rules_unit_placement,
        attempted_rules_unit_placement=resolution.attempted_rules_unit_placement,
        coherency_result=broken_coherency,
    )
    rollback_resolution = replace(
        resolution,
        coherency_result=broken_coherency,
        rollback_record=rollback,
    )
    assert (
        RulesUnitFightMovementResolution.from_payload(rollback_resolution.to_payload())
        == rollback_resolution
    )

    consolidate_request = _rules_unit_fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        rules_unit=rules_unit,
    )
    consolidate_proposal = FightMovementProposal(
        proposal_request_id=consolidate_request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=rules_unit.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
    )
    no_move = resolve_rules_unit_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=consolidate_proposal,
        maximum_distance_inches=3.0,
        state=state,
    )
    assert isinstance(no_move, RulesUnitFightMovementResolution)
    assert RulesUnitFightMovementResolution.from_payload(no_move.to_payload()) == no_move
    with pytest.raises(GameLifecycleError, match="no-move resolution must not include a witness"):
        replace(no_move, witness=resolution.witness)
    with pytest.raises(
        GameLifecycleError,
        match="no-move resolution must not include coherency evidence",
    ):
        replace(no_move, coherency_result=resolution.coherency_result)
    with pytest.raises(
        GameLifecycleError,
        match="no-move resolution must not include a rollback record",
    ):
        replace(no_move, rollback_record=rollback)

    malformed_payloads: list[tuple[dict[str, object], str]] = []
    missing_key = dict(payload)
    missing_key.pop("endpoint_witness")
    malformed_payloads.append((missing_key, "shape drifted"))
    payload_tampers: tuple[tuple[str, object, str], ...] = (
        ("witness", [], "witness payload must be an object"),
        ("component_unit_instance_ids", (), "component payload must be a list"),
        ("path_validation_results", (), "path results payload must be a list"),
        ("terrain_path_legality_results", (), "terrain results payload must be a list"),
        ("coherency_result", [], "coherency payload must be an object"),
        ("rollback_record", [], "rollback payload must be an object"),
    )
    for key, value, message in payload_tampers:
        tampered = dict(payload)
        tampered[key] = value
        malformed_payloads.append((tampered, message))
    component_drift = dict(payload)
    component_drift["component_unit_instance_ids"] = [
        *payload["component_unit_instance_ids"],
        "army-alpha:extra",
    ]
    malformed_payloads.append((component_drift, "component payload drift"))
    unsupported_mode = dict(payload)
    unsupported_mode["movement_mode"] = MovementMode.NORMAL.value
    malformed_payloads.append((unsupported_mode, "payload mode is unsupported"))
    assert resolution.witness is not None
    witness_payload = resolution.witness.to_payload()
    partial_witness = dict(payload)
    partial_witness["witness"] = {
        "model_paths": witness_payload["model_paths"][:-1],
    }
    malformed_payloads.append((partial_witness, "witness model inventory drifted"))
    first_witness_path = witness_payload["model_paths"][0]
    start_drift_witness = dict(payload)
    start_drift_witness["witness"] = {
        "model_paths": [
            {
                "model_id": first_witness_path["model_id"],
                "poses": [first_witness_path["poses"][-1], *first_witness_path["poses"][1:]],
            },
            *witness_payload["model_paths"][1:],
        ]
    }
    malformed_payloads.append((start_drift_witness, "witness start pose drifted"))
    endpoint_drift_witness = dict(payload)
    endpoint_drift_witness["witness"] = {
        "model_paths": [
            {
                "model_id": first_witness_path["model_id"],
                "poses": [*first_witness_path["poses"][:-1], first_witness_path["poses"][0]],
            },
            *witness_payload["model_paths"][1:],
        ]
    }
    malformed_payloads.append((endpoint_drift_witness, "witness endpoint pose drifted"))
    missing_coherency = dict(payload)
    missing_coherency["coherency_result"] = None
    malformed_payloads.append((missing_coherency, "requires coherency evidence"))
    assert resolution.coherency_result is not None
    coherency_identity_drift = dict(payload)
    coherency_identity_drift["coherency_result"] = replace(
        resolution.coherency_result,
        unit_instance_id="attached-unit:drifted",
    ).to_payload()
    malformed_payloads.append((coherency_identity_drift, "coherency identity drifted"))
    no_move_witness = dict(no_move.to_payload())
    no_move_witness["witness"] = witness_payload
    malformed_payloads.append((no_move_witness, "no-move resolution must not include a witness"))

    for tampered, message in malformed_payloads:
        with pytest.raises(GameLifecycleError, match=message):
            RulesUnitFightMovementResolution.from_payload(
                cast(RulesUnitFightMovementResolutionPayload, tampered)
            )


def test_phase15d_grouped_fight_completed_event_requires_exact_transition_evidence() -> None:
    ruleset, _scenario, _state, _rules_unit, _request, proposal, resolution = (
        _resolved_attached_pile_in_fixture()
    )
    component_ids = resolution.before_rules_unit_placement.component_unit_instance_ids
    event_payload: dict[str, object] = {
        "unit_instance_id": resolution.unit_instance_id,
        "proposal_kind": proposal.proposal_kind.value,
        "resolution": resolution.to_payload(),
        "transition_batch": resolution.transition_batch().to_payload(),
    }
    assert (
        fight_rules_unit_movement_endpoint_from_completed_event(
            payload=cast(dict[str, JsonValue], event_payload),
            component_unit_instance_ids=component_ids,
        )
        == resolution.attempted_rules_unit_placement
    )

    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        fight_rules_unit_movement_endpoint_from_completed_event(
            payload=cast(dict[str, JsonValue], event_payload),
            component_unit_instance_ids=cast(tuple[str, ...], list(component_ids)),
        )
    for malformed_ids in ((), (component_ids[0], component_ids[0])):
        with pytest.raises(GameLifecycleError, match="non-empty and unique"):
            fight_rules_unit_movement_endpoint_from_completed_event(
                payload=cast(dict[str, JsonValue], event_payload),
                component_unit_instance_ids=malformed_ids,
            )

    invalid_path = PathValidationResult.invalid(
        PathConstraintViolation(
            violation_code="phase15d-completed-path-invalid",
            message="phase15d-completed-path-invalid",
        ),
        sampled_pose_count=1,
        model_collision_check_count=0,
        terrain_collision_check_count=0,
        engagement_check_count=0,
    )
    invalid_resolution = replace(resolution, path_validation_results=(invalid_path,))
    malformed_events: list[tuple[dict[str, object], tuple[str, ...], str]] = []
    not_an_object = dict(event_payload)
    not_an_object["resolution"] = []
    malformed_events.append((not_an_object, component_ids, "resolution must be an object"))
    legacy_endpoint = dict(event_payload)
    legacy_endpoint["movement_endpoint_placement"] = (
        resolution.attempted_rules_unit_placement.component_unit_placements[0].to_payload()
    )
    malformed_events.append((legacy_endpoint, component_ids, "evidence shape drifted"))
    invalid_inner = dict(event_payload)
    invalid_inner["resolution"] = invalid_resolution.to_payload()
    malformed_events.append((invalid_inner, component_ids, "resolution must be valid"))
    outer_identity_drift = dict(event_payload)
    outer_identity_drift["unit_instance_id"] = "attached-unit:drifted"
    malformed_events.append((outer_identity_drift, component_ids, "rules-unit identity drift"))
    malformed_events.append((event_payload, component_ids[:1], "component identity drift"))
    context_drift = dict(event_payload)
    context_drift["proposal_kind"] = ProposalKind.CONSOLIDATE.value
    malformed_events.append((context_drift, component_ids, "resolution context drifted"))
    transition_not_object = dict(event_payload)
    transition_not_object["transition_batch"] = []
    malformed_events.append((transition_not_object, component_ids, "must be an object"))
    transition_drift = dict(event_payload)
    transition_drift["transition_batch"] = BattlefieldTransitionBatch().to_payload()
    malformed_events.append((transition_drift, component_ids, "transition evidence drift"))
    first_component = resolution.attempted_rules_unit_placement.component_unit_placements[0]
    first_model = first_component.model_placements[0]
    tampered_pose = Pose.at(
        first_model.pose.position.x + 0.125,
        first_model.pose.position.y,
        first_model.pose.position.z,
        first_model.pose.facing.degrees,
    )
    tampered_attempted = FightRulesUnitPlacement(
        rules_unit_instance_id=resolution.unit_instance_id,
        component_unit_placements=(
            first_component.with_model_placements(
                (
                    first_model.with_pose(tampered_pose),
                    *first_component.model_placements[1:],
                )
            ),
            *resolution.attempted_rules_unit_placement.component_unit_placements[1:],
        ),
    )
    tampered_resolution = dict(resolution.to_payload())
    tampered_resolution["attempted_rules_unit_placement"] = tampered_attempted.to_payload()
    transition = resolution.transition_batch()
    consistently_tampered = dict(event_payload)
    consistently_tampered["resolution"] = tampered_resolution
    consistently_tampered["transition_batch"] = BattlefieldTransitionBatch(
        displacements=tuple(
            replace(displacement, end_pose=tampered_pose)
            if displacement.model_instance_id == first_model.model_instance_id
            else displacement
            for displacement in transition.displacements
        )
    ).to_payload()
    malformed_events.append(
        (
            consistently_tampered,
            component_ids,
            "witness endpoint pose drifted",
        )
    )

    for tampered, selected_components, message in malformed_events:
        with pytest.raises(GameLifecycleError, match=message):
            fight_rules_unit_movement_endpoint_from_completed_event(
                payload=cast(dict[str, JsonValue], tampered),
                component_unit_instance_ids=selected_components,
            )

    broken_coherency = UnitCoherencyResult(
        status=UnitCoherencyStatus.BROKEN,
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        unit_instance_id=resolution.unit_instance_id,
        coherency_policy=ruleset.coherency_policy,
        model_instance_ids=tuple(
            model.model_instance_id
            for model in resolution.before_rules_unit_placement.model_placements
        ),
        violations=(
            UnitCoherencyViolation(
                model_instance_id=resolution.before_rules_unit_placement.model_placements[
                    0
                ].model_instance_id,
                violation_code="phase15d-completed-coherency-break",
            ),
        ),
    )
    rollback = RulesUnitMovementRollbackRecord(
        unit_instance_id=resolution.unit_instance_id,
        displacement_kind=ModelDisplacementKind.PILE_IN,
        before_rules_unit_placement=resolution.before_rules_unit_placement,
        attempted_rules_unit_placement=resolution.attempted_rules_unit_placement,
        coherency_result=broken_coherency,
    )
    rollback_event = dict(event_payload)
    rollback_event["resolution"] = replace(
        resolution,
        coherency_result=broken_coherency,
        rollback_record=rollback,
    ).to_payload()
    with pytest.raises(GameLifecycleError, match="resolution must be valid"):
        fight_rules_unit_movement_endpoint_from_completed_event(
            payload=cast(dict[str, JsonValue], rollback_event),
            component_unit_instance_ids=component_ids,
        )


def test_phase15d_standalone_fight_completed_event_rejects_tampered_audit_evidence() -> None:
    _catalog, ruleset, scenario, attacker, target, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    proposal = FightMovementProposal(
        proposal_request_id="phase15d-completed-standalone-request",
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target.unit_instance_id,),
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
        proposal=proposal,
    )
    before = scenario.battlefield_state.unit_placement_by_id(attacker.unit_instance_id)
    transition = resolution.transition_batch(before=before)
    event_payload: dict[str, object] = {
        "unit_instance_id": attacker.unit_instance_id,
        "proposal_kind": proposal.proposal_kind.value,
        "resolution": resolution.to_payload(),
        "movement_endpoint_placement": resolution.attempted_placement.to_payload(),
        "transition_batch": transition.to_payload(),
    }
    assert (
        fight_rules_unit_movement_endpoint_from_completed_event(
            payload=cast(dict[str, JsonValue], event_payload),
            component_unit_instance_ids=(attacker.unit_instance_id,),
        )
        == resolution.attempted_placement
    )

    malformed_events: list[tuple[dict[str, object], str]] = []
    extra_resolution_key = dict(event_payload)
    extra_resolution = dict(resolution.to_payload())
    extra_resolution["unexpected"] = True
    extra_resolution_key["resolution"] = extra_resolution
    malformed_events.append((extra_resolution_key, "resolution shape drifted"))
    missing_endpoint = dict(event_payload)
    missing_endpoint.pop("movement_endpoint_placement")
    malformed_events.append((missing_endpoint, "endpoint evidence"))
    endpoint_not_object = dict(event_payload)
    endpoint_not_object["movement_endpoint_placement"] = []
    malformed_events.append((endpoint_not_object, "endpoint evidence"))
    endpoint_identity = dict(event_payload)
    endpoint_identity["movement_endpoint_placement"] = (
        scenario.battlefield_state.unit_placement_by_id(target.unit_instance_id).to_payload()
    )
    malformed_events.append((endpoint_identity, "endpoint identity drifted"))
    outer_context = dict(event_payload)
    outer_context["proposal_kind"] = ProposalKind.CONSOLIDATE.value
    malformed_events.append((outer_context, "resolution context drifted"))
    resolution_tampers: tuple[tuple[str, object, str], ...] = (
        ("movement_mode", MovementMode.CONSOLIDATE.value, "resolution context drifted"),
        ("movement_phase_action", CONSOLIDATE_ACTION, "resolution context drifted"),
        ("maximum_distance_inches", "three", "distance evidence is invalid"),
        ("maximum_distance_inches", 0.0, "distance evidence is invalid"),
        ("rollback_record", {}, "resolution must be valid"),
        ("path_validation_results", (), "path results must be a list"),
        ("terrain_path_legality_results", (), "terrain results must be a list"),
        ("coherency_result", [], "coherency result must be an object"),
    )
    for key, value, message in resolution_tampers:
        tampered_event = dict(event_payload)
        tampered_resolution = dict(resolution.to_payload())
        tampered_resolution[key] = value
        tampered_event["resolution"] = tampered_resolution
        malformed_events.append((tampered_event, message))

    invalid_path = PathValidationResult.invalid(
        PathConstraintViolation(
            violation_code="phase15d-completed-standalone-path",
            message="phase15d-completed-standalone-path",
        ),
        sampled_pose_count=1,
        model_collision_check_count=0,
        terrain_collision_check_count=0,
        engagement_check_count=0,
    )
    invalid_terrain = TerrainPathLegalityResult.invalid(
        TerrainTraversalViolation(
            violation_code="phase15d-completed-standalone-terrain",
            message="phase15d-completed-standalone-terrain",
        ),
        segments=(),
        sampled_pose_count=1,
    )
    for invalid_resolution in (
        replace(resolution, path_validation_results=(invalid_path,)),
        replace(resolution, terrain_path_legality_results=(invalid_terrain,)),
    ):
        tampered = dict(event_payload)
        tampered["resolution"] = invalid_resolution.to_payload()
        malformed_events.append((tampered, "resolution must be valid"))

    malformed_endpoint_witnesses: tuple[tuple[object, str], ...] = (
        ([], "endpoint witness shape drifted"),
        (
            {
                key: value
                for key, value in resolution.endpoint_witness.items()
                if key != "objective_id"
            },
            "endpoint witness shape drifted",
        ),
        (
            {**resolution.endpoint_witness, "moved_model_instance_ids": "not-a-list"},
            "moved model IDs must be a list",
        ),
        (
            {
                **resolution.endpoint_witness,
                "target_unit_instance_ids": ["target-z", "target-a"],
            },
            "must be sorted and unique",
        ),
        (
            {
                **resolution.endpoint_witness,
                "engaged_before_unit_ids": ["target-a", "target-a"],
            },
            "must be sorted and unique",
        ),
        ({**resolution.endpoint_witness, "objective_id": 42}, "objective_id"),
    )
    for endpoint_witness, message in malformed_endpoint_witnesses:
        tampered = dict(event_payload)
        tampered_resolution = dict(resolution.to_payload())
        tampered_resolution["endpoint_witness"] = endpoint_witness
        tampered["resolution"] = tampered_resolution
        malformed_events.append((tampered, message))

    transition_not_object = dict(event_payload)
    transition_not_object["transition_batch"] = []
    malformed_events.append((transition_not_object, "transition batch must be an object"))
    missing_displacement = dict(event_payload)
    missing_displacement["transition_batch"] = BattlefieldTransitionBatch().to_payload()
    malformed_events.append((missing_displacement, "transition model identity drifted"))
    drifted_endpoint = dict(event_payload)
    endpoint_model = resolution.attempted_placement.model_placements[0]
    drifted_endpoint["movement_endpoint_placement"] = (
        resolution.attempted_placement.with_model_placements(
            (endpoint_model.with_pose(Pose.at(20.0, 20.0)),)
        ).to_payload()
    )
    malformed_events.append((drifted_endpoint, "transition endpoint drifted"))

    displacement = transition.displacements[0]
    assert displacement.path_witness is not None
    drifted_path = PathWitness.for_paths(
        (
            (
                displacement.model_instance_id,
                (
                    displacement.end_pose,
                    displacement.end_pose,
                    displacement.end_pose,
                ),
            ),
        )
    )
    displacement_tampers = (
        replace(displacement, displacement_kind=ModelDisplacementKind.CONSOLIDATE),
        replace(displacement, source_phase=BattlePhase.SHOOTING.value),
        replace(displacement, source_step=CONSOLIDATE_ACTION),
        replace(displacement, source_rule_id="phase15d-tampered-rule"),
        replace(displacement, source_event_id="phase15d-tampered-event"),
        replace(displacement, path_witness=None),
        replace(displacement, path_witness=drifted_path),
    )
    for tampered_displacement in displacement_tampers:
        tampered = dict(event_payload)
        tampered["transition_batch"] = BattlefieldTransitionBatch(
            displacements=(tampered_displacement,)
        ).to_payload()
        message = (
            "displacement path drifted"
            if tampered_displacement.path_witness == drifted_path
            else "displacement context drifted"
        )
        malformed_events.append((tampered, message))

    for tampered, message in malformed_events:
        with pytest.raises(GameLifecycleError, match=message):
            fight_rules_unit_movement_endpoint_from_completed_event(
                payload=cast(dict[str, JsonValue], tampered),
                component_unit_instance_ids=(attacker.unit_instance_id,),
            )


def test_phase15d_attached_fight_movement_validates_each_pile_in_and_consolidation_mode() -> None:
    (
        _catalog,
        ruleset,
        engaged_scenario,
        engaged_state,
        rules_unit,
        _bodyguard,
        _leader,
        target,
    ) = _attached_melee_fixture()
    pile_request = _rules_unit_fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        rules_unit=rules_unit,
    )
    pile_proposal = FightMovementProposal(
        proposal_request_id=pile_request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=rules_unit.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target.unit_instance_id,),
        witness=_movement_witness_for_rules_unit(
            scenario=engaged_scenario,
            rules_unit=rules_unit,
            dx=0.25,
        ),
    )
    assert legal_rules_unit_consolidation_modes(
        scenario=engaged_scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=rules_unit.unit_instance_id,
        objective_markers=(),
        state=engaged_state,
    ) == (ConsolidationModeKind.ONGOING,)
    assert fight_rules_unit_movement_rule_validation(
        scenario=engaged_scenario,
        ruleset_descriptor=ruleset,
        proposal_request=pile_request,
        proposal=pile_proposal,
        eligible_unit_ids=(rules_unit.unit_instance_id,),
        state=engaged_state,
    ).is_valid

    pile_cases = (
        (
            replace(
                pile_proposal,
                pile_in_target_unit_instance_ids=(
                    target.unit_instance_id,
                    target.unit_instance_id,
                ),
            ),
            (rules_unit.unit_instance_id,),
            "fight_movement_target_ids_duplicated",
        ),
        (pile_proposal, (), "fight_movement_unit_not_eligible"),
        (
            replace(
                pile_proposal,
                pile_in_target_unit_instance_ids=("army-beta:missing-target",),
            ),
            (rules_unit.unit_instance_id,),
            "pile_in_engaged_targets_must_be_complete",
        ),
    )
    for selected_proposal, eligible_ids, expected_code in pile_cases:
        validation = fight_rules_unit_movement_rule_validation(
            scenario=engaged_scenario,
            ruleset_descriptor=ruleset,
            proposal_request=pile_request,
            proposal=selected_proposal,
            eligible_unit_ids=eligible_ids,
            state=engaged_state,
        )
        assert not validation.is_valid, expected_code
        assert validation.violations[0].violation_code == expected_code

    consolidate_request = _rules_unit_fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        rules_unit=rules_unit,
    )
    ongoing = FightMovementProposal(
        proposal_request_id=consolidate_request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=rules_unit.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
        consolidation_mode=ConsolidationModeKind.ONGOING,
        consolidate_target_unit_instance_ids=(target.unit_instance_id,),
        witness=_movement_witness_for_rules_unit(
            scenario=engaged_scenario,
            rules_unit=rules_unit,
            dx=0.25,
        ),
    )
    for selected_proposal, expected_code in (
        (
            replace(ongoing, consolidation_mode=ConsolidationModeKind.ENGAGING),
            "consolidation_mode_not_legal",
        ),
    ):
        validation = fight_rules_unit_movement_rule_validation(
            scenario=engaged_scenario,
            ruleset_descriptor=ruleset,
            proposal_request=consolidate_request,
            proposal=selected_proposal,
            eligible_unit_ids=(rules_unit.unit_instance_id,),
            state=engaged_state,
        )
        assert not validation.is_valid, expected_code
        assert validation.violations[0].violation_code == expected_code
    assert fight_rules_unit_movement_rule_validation(
        scenario=engaged_scenario,
        ruleset_descriptor=ruleset,
        proposal_request=consolidate_request,
        proposal=ongoing,
        eligible_unit_ids=(rules_unit.unit_instance_id,),
        state=engaged_state,
    ).is_valid

    target_placement = engaged_scenario.battlefield_state.unit_placement_by_id(
        target.unit_instance_id
    )
    near_battlefield = engaged_scenario.battlefield_state.with_unit_placement(
        target_placement.with_model_placements(
            tuple(
                model.with_pose(Pose.at(14.0, 10.0)) for model in target_placement.model_placements
            )
        )
    )
    near_scenario = replace(engaged_scenario, battlefield_state=near_battlefield)
    engaged_state.replace_battlefield_state(near_battlefield)
    engaging = replace(
        ongoing,
        consolidation_mode=ConsolidationModeKind.ENGAGING,
    )
    assert legal_rules_unit_consolidation_modes(
        scenario=near_scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=rules_unit.unit_instance_id,
        objective_markers=(),
        state=engaged_state,
    ) == (ConsolidationModeKind.ENGAGING,)
    for selected_proposal, expected_code in (
        (
            replace(engaging, consolidation_mode=ConsolidationModeKind.ONGOING),
            "consolidation_mode_not_legal",
        ),
        (
            replace(
                engaging,
                consolidate_target_unit_instance_ids=("army-beta:missing-target",),
            ),
            "engaging_consolidation_target_not_legal",
        ),
    ):
        validation = fight_rules_unit_movement_rule_validation(
            scenario=near_scenario,
            ruleset_descriptor=ruleset,
            proposal_request=consolidate_request,
            proposal=selected_proposal,
            eligible_unit_ids=(rules_unit.unit_instance_id,),
            state=engaged_state,
        )
        assert validation.violations[0].violation_code == expected_code
    assert fight_rules_unit_movement_rule_validation(
        scenario=near_scenario,
        ruleset_descriptor=ruleset,
        proposal_request=consolidate_request,
        proposal=engaging,
        eligible_unit_ids=(rules_unit.unit_instance_id,),
        state=engaged_state,
    ).is_valid

    far_battlefield = near_battlefield.with_unit_placement(
        target_placement.with_model_placements(
            tuple(
                model.with_pose(Pose.at(30.0, 30.0)) for model in target_placement.model_placements
            )
        )
    )
    far_scenario = replace(engaged_scenario, battlefield_state=far_battlefield)
    engaged_state.replace_battlefield_state(far_battlefield)
    no_target_validation = fight_rules_unit_movement_rule_validation(
        scenario=far_scenario,
        ruleset_descriptor=ruleset,
        proposal_request=pile_request,
        proposal=pile_proposal,
        eligible_unit_ids=(rules_unit.unit_instance_id,),
        state=engaged_state,
    )
    assert no_target_validation.violations[0].violation_code == "pile_in_no_legal_targets"

    objective = ObjectiveMarker(
        objective_marker_id="phase15d-grouped-objective",
        name="phase15d-grouped-objective",
        x_inches=12.0,
        y_inches=10.0,
    )
    objective_request = replace(
        consolidate_request,
        context=_validated_json_object(
            {
                "movement_mode": MovementMode.CONSOLIDATE.value,
                "objective_markers": [objective.to_payload()],
            }
        ),
    )
    objective_proposal = replace(
        ongoing,
        proposal_request_id=objective_request.request_id,
        consolidation_mode=ConsolidationModeKind.OBJECTIVE,
        consolidate_target_unit_instance_ids=(),
        objective_id=objective.objective_marker_id,
    )
    assert legal_rules_unit_consolidation_modes(
        scenario=far_scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=rules_unit.unit_instance_id,
        objective_markers=(objective,),
        state=engaged_state,
    ) == (ConsolidationModeKind.OBJECTIVE,)
    assert fight_rules_unit_movement_rule_validation(
        scenario=far_scenario,
        ruleset_descriptor=ruleset,
        proposal_request=objective_request,
        proposal=objective_proposal,
        eligible_unit_ids=(rules_unit.unit_instance_id,),
        state=engaged_state,
    ).is_valid
    for selected_proposal, expected_code in (
        (
            replace(objective_proposal, consolidation_mode=ConsolidationModeKind.ENGAGING),
            "consolidation_mode_not_legal",
        ),
        (
            replace(objective_proposal, objective_id="phase15d-missing-objective"),
            "objective_consolidation_target_not_legal",
        ),
    ):
        validation = fight_rules_unit_movement_rule_validation(
            scenario=far_scenario,
            ruleset_descriptor=ruleset,
            proposal_request=objective_request,
            proposal=selected_proposal,
            eligible_unit_ids=(rules_unit.unit_instance_id,),
            state=engaged_state,
        )
        assert validation.violations[0].violation_code == expected_code

    empty_request = replace(
        consolidate_request,
        context={"movement_mode": MovementMode.CONSOLIDATE.value, "objective_markers": []},
    )
    no_mode = replace(objective_proposal, proposal_request_id=empty_request.request_id)
    no_mode_validation = fight_rules_unit_movement_rule_validation(
        scenario=far_scenario,
        ruleset_descriptor=ruleset,
        proposal_request=empty_request,
        proposal=no_mode,
        eligible_unit_ids=(rules_unit.unit_instance_id,),
        state=engaged_state,
    )
    assert no_mode_validation.violations[0].violation_code == "consolidation_no_legal_mode"

    malformed_contexts: tuple[tuple[dict[str, JsonValue], str], ...] = (
        (
            _validated_json_object({"movement_mode": MovementMode.CONSOLIDATE.value}),
            "objective_markers must be a list",
        ),
        (
            _validated_json_object(
                {
                    "movement_mode": MovementMode.CONSOLIDATE.value,
                    "objective_markers": ["not-an-object"],
                }
            ),
            "marker must be an object",
        ),
    )
    for context, message in malformed_contexts:
        malformed_request = replace(consolidate_request, context=context)
        with pytest.raises(GameLifecycleError, match=message):
            fight_rules_unit_movement_rule_validation(
                scenario=far_scenario,
                ruleset_descriptor=ruleset,
                proposal_request=malformed_request,
                proposal=replace(
                    objective_proposal,
                    proposal_request_id=malformed_request.request_id,
                ),
                eligible_unit_ids=(rules_unit.unit_instance_id,),
                state=engaged_state,
            )


def test_phase15d_attached_fight_movement_rejects_alias_and_partial_witness() -> None:
    (
        _catalog,
        ruleset,
        scenario,
        state,
        rules_unit,
        bodyguard,
        _leader,
        target_bodyguard,
    ) = _attached_melee_fixture(target_attached=True)
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_bodyguard.unit_instance_id,
    )
    request = _rules_unit_fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        rules_unit=rules_unit,
    )
    full_witness = _movement_witness_for_rules_unit(
        scenario=scenario,
        rules_unit=rules_unit,
        dx=0.25,
    )
    alias_proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=rules_unit.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target_bodyguard.unit_instance_id,),
        witness=full_witness,
    )
    partial_proposal = replace(
        alias_proposal,
        pile_in_target_unit_instance_ids=(target_rules_unit.unit_instance_id,),
        witness=PathWitness.for_paths(
            tuple(
                path
                for path in full_witness.model_paths
                if path[0] == bodyguard.own_models[0].model_instance_id
            )
        ),
    )

    assert legal_rules_unit_pile_in_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=rules_unit.unit_instance_id,
        state=state,
    ) == (target_rules_unit.unit_instance_id,)
    alias_validation = fight_rules_unit_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=alias_proposal,
        eligible_unit_ids=(rules_unit.unit_instance_id,),
        state=state,
    )
    witness_validation = fight_rules_unit_movement_witness_matches_current_status(
        state=state,
        scenario=scenario,
        proposal_request=request,
        proposal=partial_proposal,
    )

    assert not alias_validation.is_valid
    assert (
        alias_validation.violations[0].violation_code
        == "fight_movement_target_identity_not_canonical"
    )
    assert witness_validation is not None
    assert witness_validation.violations[0].violation_code == ("fight_movement_witness_model_drift")


def test_phase15d_standalone_fight_movement_canonicalizes_attached_targets() -> None:
    (
        _catalog,
        ruleset,
        scenario,
        _attached_state,
        _moving_rules_unit,
        moving_bodyguard,
        moving_leader,
        target_bodyguard,
    ) = _attached_melee_fixture(target_attached=True)
    standalone_army = replace(scenario.armies[0], attached_units=())
    standalone_scenario = replace(
        scenario,
        armies=(standalone_army, scenario.armies[1]),
        battlefield_state=scenario.battlefield_state.without_unit_placement(
            moving_leader.unit_instance_id
        ),
    )
    state = _attack_sequence_state(
        game_id="phase15d-standalone-mover-attached-target",
        ruleset=ruleset,
        scenario=standalone_scenario,
    )
    attacker = standalone_army.unit_by_id(moving_bodyguard.unit_instance_id)
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_bodyguard.unit_instance_id,
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        attacker=attacker,
    )
    canonical_proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target_rules_unit.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=standalone_scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )

    assert legal_rules_unit_pile_in_target_unit_ids(
        scenario=standalone_scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=attacker.unit_instance_id,
        state=state,
    ) == (target_rules_unit.unit_instance_id,)
    for component_id in target_rules_unit.component_unit_instance_ids:
        alias_validation = fight_rules_unit_movement_rule_validation(
            scenario=standalone_scenario,
            ruleset_descriptor=ruleset,
            proposal_request=request,
            proposal=replace(
                canonical_proposal,
                pile_in_target_unit_instance_ids=(component_id,),
            ),
            eligible_unit_ids=(attacker.unit_instance_id,),
            state=state,
        )
        assert not alias_validation.is_valid
        assert (
            alias_validation.violations[0].violation_code
            == "fight_movement_target_identity_not_canonical"
        )

    assert fight_rules_unit_movement_rule_validation(
        scenario=standalone_scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=canonical_proposal,
        eligible_unit_ids=(attacker.unit_instance_id,),
        state=state,
    ).is_valid
    resolution = resolve_rules_unit_fight_movement(
        scenario=standalone_scenario,
        ruleset_descriptor=ruleset,
        proposal=canonical_proposal,
        maximum_distance_inches=3.0,
        state=state,
    )

    assert isinstance(resolution, FightMovementResolution)
    assert resolution.endpoint_witness["target_unit_instance_ids"] == [
        target_rules_unit.unit_instance_id
    ]
    assert resolution.endpoint_witness["engaged_before_unit_ids"] == [
        target_rules_unit.unit_instance_id
    ]
    assert (
        fight_rules_unit_movement_resolution_violation(
            proposal_request=request,
            proposal=canonical_proposal,
            resolution=resolution,
            scenario=standalone_scenario,
            ruleset_descriptor=ruleset,
            state=state,
        )
        is None
    )


def test_phase15d_attached_no_move_is_atomic_and_distance_effect_is_lineage_aware() -> None:
    (
        _catalog,
        ruleset,
        scenario,
        state,
        rules_unit,
        _bodyguard,
        leader,
        _target,
    ) = _attached_melee_fixture()
    request = _rules_unit_fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        rules_unit=rules_unit,
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=rules_unit.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
    )
    source_rule_id = "test:phase15d:attached-movement-distance"
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="phase15d-attached-movement-distance",
            source_rule_id=source_rule_id,
            owner_player_id="player-a",
            target_unit_instance_ids=(leader.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id="player-a",
            ),
            effect_payload={
                "effect_kind": FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
                "source_id": source_rule_id,
                "pile_in_distance_inches": 6.0,
                "consolidate_distance_inches": 5.0,
            },
        )
    )

    assert fight_rules_unit_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=proposal,
        eligible_unit_ids=(rules_unit.unit_instance_id,),
        state=state,
    ).is_valid
    resolution = resolve_rules_unit_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        maximum_distance_inches=5.0,
        state=state,
    )
    assert isinstance(resolution, RulesUnitFightMovementResolution)
    assert (
        apply_fight_rules_unit_movement_resolution(
            battlefield_state=scenario.battlefield_state,
            resolution=resolution,
        )
        is scenario.battlefield_state
    )
    assert (
        fight_rules_unit_movement_transition_batch(
            scenario=scenario,
            resolution=resolution,
        ).displacements
        == ()
    )
    assert (
        rules_unit_fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=rules_unit.unit_instance_id,
            proposal_kind=ProposalKind.PILE_IN,
        )
        == 6.0
    )


def test_phase15d_rules_unit_movement_delegates_standalone_payloads_exactly() -> None:
    _catalog, ruleset, scenario, attacker, target, _target_b = _melee_fixture(
        target_b_pose=Pose.at(30.0, 30.0),
    )
    state = _attack_sequence_state(
        game_id="phase15d-standalone-rules-unit-movement",
        ruleset=ruleset,
        scenario=scenario,
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
        pile_in_target_unit_instance_ids=(target.unit_instance_id,),
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=0.25,
            endpoint_only=False,
        ),
    )
    maximum_distance = fight_movement_maximum_distance_inches(
        state=state,
        unit_instance_id=attacker.unit_instance_id,
        proposal_kind=ProposalKind.PILE_IN,
    )
    direct_validation = fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=proposal,
        eligible_unit_ids=(attacker.unit_instance_id,),
        state=state,
    )
    wrapped_validation = fight_rules_unit_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=proposal,
        eligible_unit_ids=(attacker.unit_instance_id,),
        state=state,
    )
    direct_resolution = resolve_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        maximum_distance_inches=maximum_distance,
        state=state,
    )
    wrapped_resolution = resolve_rules_unit_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        maximum_distance_inches=maximum_distance,
        state=state,
    )

    assert (
        rules_unit_fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=attacker.unit_instance_id,
            proposal_kind=ProposalKind.PILE_IN,
        )
        == maximum_distance
    )
    assert legal_rules_unit_pile_in_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=attacker.unit_instance_id,
        state=state,
    ) == legal_pile_in_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        unit_instance_id=attacker.unit_instance_id,
        state=state,
    )
    assert wrapped_validation == direct_validation
    assert wrapped_resolution == direct_resolution
    assert wrapped_resolution.to_payload() == direct_resolution.to_payload()
    assert fight_rules_unit_movement_resolution_violation(
        proposal_request=request,
        proposal=proposal,
        resolution=wrapped_resolution,
        scenario=scenario,
        ruleset_descriptor=ruleset,
        state=state,
    ) == fight_movement_resolution_violation(
        proposal_request=request,
        proposal=proposal,
        resolution=direct_resolution,
        scenario=scenario,
        ruleset_descriptor=ruleset,
        state=state,
    )
    assert fight_rules_unit_movement_transition_batch(
        scenario=scenario,
        resolution=wrapped_resolution,
    ) == direct_resolution.transition_batch(
        before=scenario.battlefield_state.unit_placement_by_id(attacker.unit_instance_id)
    )
    assert apply_fight_rules_unit_movement_resolution(
        battlefield_state=scenario.battlefield_state,
        resolution=wrapped_resolution,
    ) == scenario.battlefield_state.with_unit_placement(direct_resolution.attempted_placement)


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


def test_phase15d_fight_movement_no_move_and_source_linked_distance_effects() -> None:
    _catalog, ruleset, scenario, attacker, target_a, _target_b = _melee_fixture(
        target_a_pose=Pose.at(30.0, 30.0),
        target_b_pose=Pose.at(34.0, 30.0),
    )
    state = _attack_sequence_state(
        game_id="phase15d-movement-distance",
        ruleset=ruleset,
        scenario=scenario,
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        attacker=attacker,
    )
    no_move = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
        unit_instance_id=attacker.unit_instance_id,
        movement_phase_action=CONSOLIDATE_ACTION,
        movement_mode=MovementMode.CONSOLIDATE,
    )

    assert fight_movement_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal_request=request,
        proposal=no_move,
        eligible_unit_ids=(attacker.unit_instance_id,),
        state=state,
    ).is_valid
    assert (
        legal_consolidation_modes(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            unit_instance_id=attacker.unit_instance_id,
            objective_markers=(),
            state=state,
        )
        == ()
    )
    assert (
        fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=attacker.unit_instance_id,
            proposal_kind=ProposalKind.PILE_IN,
        )
        == 3.0
    )

    expiration = EffectExpiration.end_turn(
        battle_round=state.battle_round,
        player_id="player-a",
    )
    source_rule_id = "test:phase15d:movement-distance"
    for effect in (
        PersistingEffect(
            effect_id="phase15d-movement-distance-unrelated-target",
            source_rule_id="test:phase15d:movement-distance-unrelated",
            owner_player_id="player-a",
            target_unit_instance_ids=(target_a.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload={
                "effect_kind": FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
                "source_id": "test:phase15d:movement-distance-unrelated",
                "pile_in_distance_inches": 12.0,
                "consolidate_distance_inches": 12.0,
            },
        ),
        PersistingEffect(
            effect_id="phase15d-movement-distance-non-object",
            source_rule_id="test:phase15d:movement-distance-non-object",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload="not-an-object",
        ),
        PersistingEffect(
            effect_id="phase15d-movement-distance-wrong-kind",
            source_rule_id="test:phase15d:movement-distance-wrong-kind",
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload={"effect_kind": "not-fight-movement-distance"},
        ),
        PersistingEffect(
            effect_id="phase15d-movement-distance-valid",
            source_rule_id=source_rule_id,
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=expiration,
            effect_payload={
                "effect_kind": FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
                "source_id": source_rule_id,
                "pile_in_distance_inches": 6,
                "consolidate_distance_inches": 5.0,
            },
        ),
    ):
        state.record_persisting_effect(effect)

    assert (
        fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=attacker.unit_instance_id,
            proposal_kind=ProposalKind.PILE_IN,
        )
        == 6.0
    )
    assert (
        fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=attacker.unit_instance_id,
            proposal_kind=ProposalKind.CONSOLIDATE,
        )
        == 5.0
    )

    drift_state = _attack_sequence_state(
        game_id="phase15d-movement-distance-drift",
        ruleset=ruleset,
        scenario=scenario,
    )
    drift_state.record_persisting_effect(
        PersistingEffect(
            effect_id="phase15d-movement-distance-drift",
            source_rule_id=source_rule_id,
            owner_player_id="player-a",
            target_unit_instance_ids=(attacker.unit_instance_id,),
            started_battle_round=drift_state.battle_round,
            expiration=expiration,
            effect_payload={
                "effect_kind": FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
                "source_id": "test:phase15d:wrong-source",
                "pile_in_distance_inches": 6.0,
                "consolidate_distance_inches": 5.0,
            },
        )
    )
    with pytest.raises(GameLifecycleError, match="movement distance source_id drift"):
        fight_movement_maximum_distance_inches(
            state=drift_state,
            unit_instance_id=attacker.unit_instance_id,
            proposal_kind=ProposalKind.PILE_IN,
        )


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

    _catalog, ruleset, scenario, attacker, _target_a, _target_b = _melee_fixture(
        target_a_pose=Pose.at(15.5, 10.0),
        target_b_pose=Pose.at(34.0, 30.0),
    )
    request = _fight_movement_request(
        proposal_kind=ProposalKind.CONSOLIDATE,
        attacker=attacker,
        context={"objective_markers": [objective_marker.to_payload()]},
    )
    engaged_after_objective = replace(
        objective,
        proposal_request_id=request.request_id,
        witness=_movement_witness_for_unit(
            scenario=scenario,
            unit_instance_id=attacker.unit_instance_id,
            dx=3.0,
            endpoint_only=False,
        ),
    )
    engaged_after_resolution = resolve_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=engaged_after_objective,
    )
    engaged_after_violation = fight_movement_resolution_violation(
        proposal_request=request,
        proposal=engaged_after_objective,
        resolution=engaged_after_resolution,
        scenario=scenario,
        ruleset_descriptor=ruleset,
    )

    assert engaged_after_resolution.is_valid
    assert engaged_after_violation is not None
    assert (
        engaged_after_violation.violations[0].violation_code
        == "objective_consolidation_unit_engaged_after"
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
    leader_keywords: tuple[WeaponKeyword, ...] = (),
    leader_abilities: tuple[AbilityDescriptor, ...] = (),
    target_a_pose: Pose | None = None,
    target_b_pose: Pose | None = None,
    target_a_datasheet_id: str = "core-character-leader",
    target_a_model_profile_id: str = "core-character-leader",
    target_a_model_count: int = 1,
    attacker_datasheet_id: str = "core-character-leader",
    attacker_model_profile_id: str = "core-character-leader",
    attacker_model_count: int = 1,
    attacker_wargear_ids: tuple[str, ...] | None = None,
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
    catalog = _catalog(
        include_extra_attacks=include_extra_attacks,
        leader_keywords=leader_keywords,
        leader_abilities=leader_abilities,
    )
    ruleset = RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase15d-test")
    armies = _armies(
        catalog,
        target_a_datasheet_id=target_a_datasheet_id,
        target_a_model_profile_id=target_a_model_profile_id,
        target_a_model_count=target_a_model_count,
        attacker_datasheet_id=attacker_datasheet_id,
        attacker_model_profile_id=attacker_model_profile_id,
        attacker_model_count=attacker_model_count,
    )
    attacker = armies[0].unit_by_id("army-alpha:attacker")
    if include_extra_attacks or attacker_wargear_ids is not None:
        selected_wargear_ids = (
            ("core-leader-blade", "core-extra-blade")
            if attacker_wargear_ids is None
            else attacker_wargear_ids
        )
        attacker = replace(
            attacker,
            own_models=tuple(
                replace(model, wargear_ids=selected_wargear_ids)
                if model.model_profile_id == attacker_model_profile_id
                else model
                for model in attacker.own_models
            ),
            wargear_selections=(
                WargearSelection(
                    option_id="phase15d-attacker-wargear",
                    model_profile_id=attacker_model_profile_id,
                    wargear_ids=selected_wargear_ids,
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


def _attached_melee_fixture(
    *,
    leader_keywords: tuple[WeaponKeyword, ...] = (),
    leader_abilities: tuple[AbilityDescriptor, ...] = (),
    leader_alive: bool = True,
    target_attached: bool = False,
    target_bodyguard_model_count: int = 1,
) -> tuple[
    ArmyCatalog,
    RulesetDescriptor,
    BattlefieldScenario,
    GameState,
    RulesUnitView,
    UnitInstance,
    UnitInstance,
    UnitInstance,
]:
    catalog = _catalog(
        include_extra_attacks=False,
        leader_keywords=leader_keywords,
        leader_abilities=leader_abilities,
    )
    ruleset = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase15d-attached-test"
    )
    alpha = muster_army(
        catalog=catalog,
        request=_army_request(
            catalog=catalog,
            army_id="army-alpha",
            player_id="player-a",
            unit_ids=("bodyguard", "leader"),
        ),
    )
    bodyguard = alpha.unit_by_id("army-alpha:bodyguard")
    leader = alpha.unit_by_id("army-alpha:leader")
    if not leader_alive:
        leader = replace(
            leader,
            own_models=tuple(replace(model, wounds_remaining=0) for model in leader.own_models),
        )
        alpha = replace(
            alpha,
            units=tuple(
                leader if unit.unit_instance_id == leader.unit_instance_id else unit
                for unit in alpha.units
            ),
        )
    formation = AttachedUnitFormation(
        attached_unit_instance_id="attached-unit:army-alpha:bodyguard-and-leader",
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
        ),
        source_id="test:phase15d:attached-melee",
        attachment_source_ids=("test:phase15d:attached-melee:eligibility",),
    )
    alpha = replace(alpha, attached_units=(formation,))
    beta = muster_army(
        catalog=catalog,
        request=(
            _attached_target_army_request(
                catalog=catalog,
                bodyguard_model_count=target_bodyguard_model_count,
            )
            if target_attached
            else _army_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                unit_ids=("target",),
            )
        ),
    )
    target = beta.unit_by_id(
        "army-beta:target-bodyguard" if target_attached else "army-beta:target"
    )
    target_leader: UnitInstance | None = None
    if target_attached:
        target_leader = beta.unit_by_id("army-beta:target-leader")
        target_formation = AttachedUnitFormation(
            attached_unit_instance_id="attached-unit:army-beta:target-bodyguard-and-leader",
            bodyguard_unit_instance_id=target.unit_instance_id,
            leader_unit_instance_ids=(target_leader.unit_instance_id,),
            component_unit_instance_ids=tuple(
                sorted((target.unit_instance_id, target_leader.unit_instance_id))
            ),
            source_id="test:phase15d:attached-melee-target",
            attachment_source_ids=("test:phase15d:attached-melee-target:eligibility",),
        )
        beta = replace(beta, attached_units=(target_formation,))
    armies = (alpha, beta)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase15d-attached-battlefield",
        armies=armies,
    )
    battlefield = scenario.battlefield_state
    placements: tuple[tuple[UnitInstance, str, str, Pose], ...] = (
        (bodyguard, "army-alpha", "player-a", Pose.at(10.0, 9.6)),
        (target, "army-beta", "player-b", Pose.at(12.0, 10.0)),
    )
    if leader_alive:
        placements = (
            *placements,
            (leader, "army-alpha", "player-a", Pose.at(10.0, 10.4)),
        )
    if target_leader is not None:
        placements = (
            *placements,
            (target_leader, "army-beta", "player-b", Pose.at(12.0, 10.8)),
        )
    for unit, army_id, player_id, pose in placements:
        battlefield = battlefield.with_unit_placement(
            _unit_placement(
                unit,
                army_id=army_id,
                player_id=player_id,
                pose=pose,
            )
        )
    scenario = BattlefieldScenario(armies=armies, battlefield_state=battlefield)
    state = _attack_sequence_state(
        game_id="phase15d-attached-rules-unit",
        ruleset=ruleset,
        scenario=scenario,
    )
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=formation.attached_unit_instance_id,
    )
    return catalog, ruleset, scenario, state, rules_unit, bodyguard, leader, target


def _rules_unit_melee_request(
    *,
    ruleset: RulesetDescriptor,
    rules_unit: RulesUnitView,
    available: tuple[JsonValue, ...],
    target_ids: tuple[str, ...],
) -> MeleeDeclarationProposalRequest:
    return MeleeDeclarationProposalRequest(
        request_id="phase15d-rules-unit-melee-request",
        actor_id=rules_unit.owner_player_id,
        game_id="phase15d-rules-unit-melee",
        battle_round=1,
        active_player_id=rules_unit.owner_player_id,
        unit_instance_id=rules_unit.unit_instance_id,
        source_decision_request_id="phase15d-rules-unit-source-request",
        source_decision_result_id="phase15d-attached-source-result",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        available_weapons=available,
        target_unit_instance_ids=target_ids,
    )


def _attached_rules_unit_melee_request_and_proposal(
    *,
    catalog: ArmyCatalog,
    ruleset: RulesetDescriptor,
    scenario: BattlefieldScenario,
    state: GameState,
    rules_unit: RulesUnitView,
    components: tuple[UnitInstance, ...],
    target_unit_instance_id: str,
) -> tuple[MeleeDeclarationProposalRequest, MeleeDeclarationProposal]:
    available = rules_unit_available_melee_weapons_payloads(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        rules_unit=rules_unit,
        army_catalog=catalog,
        state=state,
        source_decision_result_id="phase15d-attached-source-result",
    )
    request = _rules_unit_melee_request(
        ruleset=ruleset,
        rules_unit=rules_unit,
        available=available,
        target_ids=(target_unit_instance_id,),
    )
    return request, MeleeDeclarationProposal(
        proposal_request_id=request.request_id,
        proposal_kind=request.proposal_kind,
        player_id=request.actor_id,
        battle_round=request.battle_round,
        unit_instance_id=rules_unit.unit_instance_id,
        source_decision_request_id=request.source_decision_request_id,
        source_decision_result_id=request.source_decision_result_id,
        declarations=tuple(
            MeleeWeaponDeclaration(
                attacker_model_instance_id=component.own_models[0].model_instance_id,
                wargear_id="core-leader-blade",
                weapon_profile_id="core-leader-blade:standard",
                target_allocations=(MeleeTargetAllocation(target_unit_instance_id),),
            )
            for component in components
        ),
    )


def _validated_json_object(value: object) -> dict[str, JsonValue]:
    payload = validate_json_value(value)
    assert isinstance(payload, dict)
    return payload


def _resolved_attached_pile_in_fixture() -> tuple[
    RulesetDescriptor,
    BattlefieldScenario,
    GameState,
    RulesUnitView,
    MovementProposalRequest,
    FightMovementProposal,
    RulesUnitFightMovementResolution,
]:
    (
        _catalog,
        ruleset,
        scenario,
        state,
        rules_unit,
        _bodyguard,
        leader,
        target,
    ) = _attached_melee_fixture()
    leader_placement = scenario.battlefield_state.unit_placement_by_id(leader.unit_instance_id)
    spaced_battlefield = scenario.battlefield_state.with_unit_placement(
        leader_placement.with_model_placements(
            tuple(
                model.with_pose(Pose.at(10.0, 11.4)) for model in leader_placement.model_placements
            )
        )
    )
    scenario = replace(scenario, battlefield_state=spaced_battlefield)
    state.replace_battlefield_state(spaced_battlefield)
    request = _rules_unit_fight_movement_request(
        proposal_kind=ProposalKind.PILE_IN,
        rules_unit=rules_unit,
    )
    proposal = FightMovementProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=rules_unit.unit_instance_id,
        movement_phase_action=PILE_IN_ACTION,
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=(target.unit_instance_id,),
        witness=_movement_witness_for_rules_unit(
            scenario=scenario,
            rules_unit=rules_unit,
            dx=0.25,
        ),
    )
    resolution = resolve_rules_unit_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset,
        proposal=proposal,
        maximum_distance_inches=3.0,
        state=state,
    )
    assert isinstance(resolution, RulesUnitFightMovementResolution)
    assert resolution.is_valid
    return ruleset, scenario, state, rules_unit, request, proposal, resolution


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
        spatial_context_hash="0" * 64,
        context=request_context,
    )
    return MovementProposalRequest.from_decision_request_payload(request.payload)


def _rules_unit_fight_movement_request(
    *,
    proposal_kind: ProposalKind,
    rules_unit: RulesUnitView,
) -> MovementProposalRequest:
    request = build_fight_movement_request(
        state_game_id="phase15d-rules-unit-fight-movement",
        battle_round=1,
        active_player_id=rules_unit.owner_player_id,
        request_id=f"phase15d-rules-unit-{proposal_kind.value}-request",
        actor_id=rules_unit.owner_player_id,
        unit_instance_id=rules_unit.unit_instance_id,
        proposal_kind=proposal_kind,
        source_decision_request_id="phase15d-rules-unit-fight-activation-request",
        source_decision_result_id="phase15d-rules-unit-fight-activation-result",
        spatial_context_hash="0" * 64,
        context={"movement_mode": proposal_kind.value},
    )
    return MovementProposalRequest.from_decision_request_payload(request.payload)


def _movement_witness_for_rules_unit(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
    dx: float,
) -> PathWitness:
    paths: list[tuple[str, tuple[Pose, ...]]] = []
    for component_id in rules_unit.component_unit_instance_ids:
        placement = scenario.battlefield_state.unit_placement_or_none(component_id)
        if placement is None:
            continue
        for model in placement.model_placements:
            start = model.pose
            middle = Pose.at(
                start.position.x + dx / 2.0,
                start.position.y,
                start.position.z,
                facing_degrees=start.facing.degrees,
            )
            end = Pose.at(
                start.position.x + dx,
                start.position.y,
                start.position.z,
                facing_degrees=start.facing.degrees,
            )
            paths.append((model.model_instance_id, (start, middle, end)))
    return PathWitness.for_paths(tuple(paths))


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
            model_paths.append((placement.model_instance_id, (start, end, end)))
            continue
        midpoint = Pose.at(
            start.position.x + (dx / 2.0),
            start.position.y,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _catalog(
    *,
    include_extra_attacks: bool,
    leader_keywords: tuple[WeaponKeyword, ...] = (),
    leader_abilities: tuple[AbilityDescriptor, ...] = (),
) -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    if leader_keywords or leader_abilities:
        leader_blade = next(
            wargear for wargear in catalog.wargear if wargear.wargear_id == "core-leader-blade"
        )
        leader_profile = leader_blade.weapon_profiles[0]
        updated_leader_blade = replace(
            leader_blade,
            weapon_profiles=(
                replace(
                    leader_profile,
                    keywords=tuple(sorted(leader_keywords)),
                    abilities=leader_abilities,
                ),
            ),
        )
        catalog = replace(
            catalog,
            wargear=tuple(
                updated_leader_blade
                if wargear.wargear_id == updated_leader_blade.wargear_id
                else wargear
                for wargear in catalog.wargear
            ),
        )
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


def _armies(
    catalog: ArmyCatalog,
    *,
    target_a_datasheet_id: str = "core-character-leader",
    target_a_model_profile_id: str = "core-character-leader",
    target_a_model_count: int = 1,
    attacker_datasheet_id: str = "core-character-leader",
    attacker_model_profile_id: str = "core-character-leader",
    attacker_model_count: int = 1,
) -> tuple[ArmyDefinition, ArmyDefinition]:
    return (
        muster_army(
            catalog=catalog,
            request=_army_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                unit_ids=("attacker",),
                datasheet_id=attacker_datasheet_id,
                model_profile_id=attacker_model_profile_id,
                model_count=attacker_model_count,
            ),
        ),
        muster_army(
            catalog=catalog,
            request=ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=(
                    _unit_muster_selection(
                        unit_selection_id="target-a",
                        datasheet_id=target_a_datasheet_id,
                        model_profile_id=target_a_model_profile_id,
                        model_count=target_a_model_count,
                    ),
                    _unit_muster_selection(
                        unit_selection_id="target-b",
                        datasheet_id="core-character-leader",
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
        ),
    )


def _army_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    unit_ids: tuple[str, ...],
    datasheet_id: str = "core-character-leader",
    model_profile_id: str = "core-character-leader",
    model_count: int = 1,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=tuple(
            _unit_muster_selection(
                unit_selection_id=unit_id,
                datasheet_id=datasheet_id,
                model_profile_id=model_profile_id,
                model_count=model_count,
            )
            for unit_id in unit_ids
        ),
    )


def _attached_target_army_request(
    *,
    catalog: ArmyCatalog,
    bodyguard_model_count: int,
) -> ArmyMusterRequest:
    bodyguard_datasheet_id = (
        "core-character-leader" if bodyguard_model_count == 1 else "core-intercessor-like-infantry"
    )
    bodyguard_model_profile_id = (
        "core-character-leader" if bodyguard_model_count == 1 else "core-intercessor-like"
    )
    return ArmyMusterRequest(
        army_id="army-beta",
        player_id="player-b",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=(
            _unit_muster_selection(
                unit_selection_id="target-bodyguard",
                datasheet_id=bodyguard_datasheet_id,
                model_profile_id=bodyguard_model_profile_id,
                model_count=bodyguard_model_count,
            ),
            _unit_muster_selection(
                unit_selection_id="target-leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
    )


def _unit_muster_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
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
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(
                    pose.position.x,
                    pose.position.y + (index * 2.0),
                    pose.position.z,
                    facing_degrees=pose.facing.degrees,
                ),
            )
            for index, model in enumerate(unit.own_models)
        ),
    )


def _attack_sequence_state(
    *,
    game_id: str,
    ruleset: RulesetDescriptor,
    scenario: BattlefieldScenario,
) -> GameState:
    state = GameState(
        game_id=game_id,
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=tuple(ruleset.battle_phase_sequence.phases),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=tuple(ruleset.battle_phase_sequence.phases).index(BattlePhaseKind.FIGHT),
        battle_round=1,
        active_player_id="player-a",
    )
    for army in scenario.armies:
        state.record_army_definition(army)
    state.record_battlefield_state(scenario.battlefield_state)
    return state


def _record_charge_move_effect(*, state: GameState, unit: UnitInstance) -> None:
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"{unit.unit_instance_id}:phase14e-charge",
            source_rule_id="core-rules:charge:fights-first",
            owner_player_id="player-a",
            target_unit_instance_ids=(unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.CHARGE,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id="player-a",
            ),
            effect_payload={"effect_kind": "charge_grants_fights_first"},
        )
    )


def _fixed_roll_result(
    *,
    roll_id: str,
    spec: DiceRollSpec,
    value: int,
) -> DiceRollResult:
    return DiceRollResult.from_values(
        roll_id=roll_id,
        spec=spec,
        values=(value,),
        source="fixed",
    )


def _attack_step_payload(
    decisions: DecisionController,
    step: AttackSequenceStep,
) -> dict[str, object]:
    for event in decisions.event_log.records:
        if event.event_type != "attack_sequence_step":
            continue
        payload = cast(dict[str, object], event.payload)
        if payload["step"] == step.value:
            return cast(dict[str, object], payload["payload"])
    raise AssertionError(f"Missing attack sequence step {step.value}.")


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
