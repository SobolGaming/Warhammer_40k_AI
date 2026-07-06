from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import warhammer40k_core.engine.attack_sequence as attack_sequence_module
import warhammer40k_core.engine.phases.shooting as shooting_phase_module
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
    DatasheetWargearOption,
)
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollResult,
    DiceRollSpec,
)
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.core.ruleset_descriptor import (
    CoverEffect,
    LineOfSightPolicy,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfilePayload,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    AttachedUnitFormation,
    muster_army,
)
from warhammer40k_core.engine.attack_sequence import (
    SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
    AttackResolutionContextPayload,
    AttackSequence,
    AttackSequenceStep,
    HitRoll,
    PendingDestroyedTransportDisembark,
    WoundRoll,
    apply_damage_allocation_model_decision,
    attack_sequence_hit_roll_spec,
    resolve_attack_sequence_until_blocked,
    wound_roll_target_number,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_POST_SHOOT_HIT_TARGET_STATUS_EFFECT_KIND,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.core_stratagem_effects import GO_TO_GROUND_EFFECT_KIND
from warhammer40k_core.engine.damage_allocation import (
    SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
    DamageApplication,
    DamageKind,
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainResolution,
    FeelNoPainSource,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.hazard import hazard_roll_spec
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    MovementDiceRecord,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import (
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingPhaseState,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.saves import (
    SaveKind,
    saving_throw_roll_spec,
)
from warhammer40k_core.engine.shooting_types import (
    ShootingType,
)
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    FiringDeckSelection,
    FiringDeckWeaponSelection,
    TransportCapacityProfile,
    TransportCargoState,
    TransportMovementStatus,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.weapon_declaration import (
    RangedAttackPool,
    ShootingDeclarationProposal,
    WeaponDeclaration,
    WeaponDeclarationPayload,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.visibility import (
    BenefitOfCoverResult,
    CoverSourceReason,
    CoverSourceRecord,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

__all__ = (
    "_advanced_unit_state",
    "_alpha_unit_spec",
    "_army_muster_request",
    "_assert_command_reroll_request",
    "_assert_invalid_proposal_status",
    "_assert_stale_damage_model_choice_rejected_before_queue_pop",
    "_assert_waiting_for_movement_unit",
    "_attached_enemy_declarations",
    "_attached_enemy_unit_specs",
    "_attached_formation_for_player",
    "_attack_pool_for_test",
    "_attack_sequence_private",
    "_attack_step_payload",
    "_attack_step_payloads",
    "_benefit_of_cover_result",
    "_blocking_ruin",
    "_catalog_with_core_datasheet_ability",
    "_catalog_with_core_feel_no_pain_datasheet",
    "_catalog_with_deadly_demise_datasheet",
    "_catalog_with_extra_bolt_profile",
    "_catalog_with_lone_operative_datasheet",
    "_catalog_with_replaced_bolt_profiles",
    "_catalog_with_same_profile_id_target_cache_collision_weapons",
    "_catalog_with_stealth_datasheet",
    "_command_reroll_use_option_id",
    "_compact_test_unit_poses",
    "_config",
    "_continue_damage_model_choices",
    "_damage_model_choice_lifecycle",
    "_decision_request",
    "_dense_solid_woods",
    "_destroyed_transport_attack_context_for_test",
    "_destroyed_transport_hazard_roll_results_for_test",
    "_destroyed_transport_pending_for_test",
    "_destroyed_transport_placement_payload_for_test",
    "_destroyed_transport_proposal_request_for_test",
    "_dice_rolled_payloads_for_spec",
    "_display_geometry",
    "_drain_damage_model_choices_with_manager",
    "_event_payloads",
    "_first_shooting_type",
    "_first_weapon_profile",
    "_fixed_roll_result",
    "_gone_to_ground_detection_context",
    "_grant_command_reroll_cp",
    "_last_event_payload",
    "_mission_setup",
    "_model_with_attached_role",
    "_model_with_characteristic",
    "_mustered_armies",
    "_non_solid_hill_with_wall",
    "_paused_optional_fnp_lifecycle",
    "_phase13f_cover_effect",
    "_phase13f_gate_weapon_profile",
    "_phase14l_multi_group_lifecycle",
    "_phase14l_multi_target_declarations",
    "_phase14l_submit_multi_group_declaration",
    "_phase14l_test1_dice_results",
    "_phase14l_test1_hit_spec",
    "_phase14l_test1_target_model",
    "_phase14l_test1_wound_spec",
    "_phase17_post_shoot_cover_denial_effect",
    "_phase18b_shooting_hit_command_reroll_status",
    "_precision_request_for_fixture",
    "_proposal_decision_result",
    "_proposal_from_declarations",
    "_proposal_from_request",
    "_record_parameterized_result_for_apply",
    "_replace_enemy_with_attached_character_fixture",
    "_replace_unit_instance_in_state",
    "_replace_unit_toughness",
    "_ruleset",
    "_save_and_damage_step_payloads",
    "_save_payload_has_cover",
    "_scenario_with_replaced_unit",
    "_scenario_with_unit_pose",
    "_select_shooting_unit_and_type",
    "_shooting_lifecycle",
    "_shooting_phase_private",
    "_single_deadly_demise_source",
    "_state",
    "_store_shooting_attack_sequence",
    "_stored_shooting_attack_sequence",
    "_submit_all_pending_fnp_declines",
    "_submit_payload",
    "_submit_phase13f_pending_attack_choices",
    "_submit_result",
    "_unit_placement_at",
    "_weapon_payload_to_declaration_payload",
    "_weapon_profile_by_wargear",
    "catalog_with_replaced_bolt_profiles",
    "lifecycle_decisions_payload",
    "proposal_from_request",
    "shooting_lifecycle",
    "weapon_profile_by_wargear",
)


def _phase13f_gate_weapon_profile() -> WeaponProfile:
    base = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    return replace(
        base,
        profile_id="phase13f-gate-rifle",
        name="Phase 13F gate rifle",
        attack_profile=AttackProfile.fixed(4),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -3),
        damage_profile=DamageProfile.fixed(3),
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(),
    )


def _phase13f_cover_effect(target_unit_instance_id: str) -> PersistingEffect:
    return PersistingEffect(
        effect_id="phase13f-go-to-ground-cover",
        source_rule_id="core-stratagem:go-to-ground",
        owner_player_id="player-b",
        target_unit_instance_ids=(target_unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            player_id="player-a",
        ),
        effect_payload={
            "effect_kind": GO_TO_GROUND_EFFECT_KIND,
            "benefit_of_cover": True,
        },
    )


def _phase17_post_shoot_cover_denial_effect(target_unit_instance_id: str) -> PersistingEffect:
    return PersistingEffect(
        effect_id="phase17-post-shoot-cover-denial",
        source_rule_id="phase17:test:post-shoot-cover-denial",
        owner_player_id="player-a",
        target_unit_instance_ids=(target_unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            player_id="player-a",
        ),
        effect_payload={
            "effect_kind": CATALOG_POST_SHOOT_HIT_TARGET_STATUS_EFFECT_KIND,
            "benefit_of_cover_denied": True,
            "status": "benefit_of_cover",
            "operation": "deny",
        },
    )


def _submit_phase13f_pending_attack_choices(
    lifecycle: GameLifecycle,
    *,
    status: LifecycleStatus,
    result_id_prefix: str,
) -> LifecycleStatus:
    attack_decision_types = {
        SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    }
    attack_sequence_choice_types = {
        SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
        SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    }
    current = status
    for index in range(128):
        if current.status_kind is LifecycleStatusKind.UNSUPPORTED:
            return current
        request = _decision_request(current)
        if (
            request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
            or request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
            or request.decision_type in attack_sequence_choice_types
        ):
            return current
        if request.decision_type not in attack_decision_types:
            raise AssertionError(f"Unexpected Phase 13F decision type {request.decision_type}.")
        option = request.options[0]
        current = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"{result_id_prefix}-{index:03d}",
                request=request,
                selected_option_id=option.option_id,
            )
        )
    raise AssertionError("Phase 13F attack sequence did not drain.")


def _attack_step_payloads(
    lifecycle: GameLifecycle,
    step: AttackSequenceStep,
) -> tuple[dict[str, object], ...]:
    return tuple(
        event
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == step.value
    )


def _save_payload_has_cover(event: dict[str, object]) -> bool:
    payload = cast(dict[str, object], event["payload"])
    option = cast(dict[str, object], payload["option"])
    cover_result = option.get("cover_result")
    if option["cover_applied"] is not True or not isinstance(cover_result, dict):
        return False
    cover_payload = cast(dict[str, object], cover_result)
    return cover_payload.get("has_benefit") is True


def _attached_enemy_unit_specs() -> tuple[tuple[str, str, str, int], ...]:
    return (
        (
            "bodyguard-unit",
            "core-intercessor-like-infantry",
            "core-intercessor-like",
            5,
        ),
        ("leader-unit", "core-character-leader", "core-character-leader", 1),
        ("support-unit", "core-character-support", "core-character-support", 1),
    )


def _attached_enemy_declarations() -> tuple[AttachmentDeclaration, ...]:
    return (
        AttachmentDeclaration(
            source_unit_selection_id="leader-unit",
            bodyguard_unit_selection_id="bodyguard-unit",
        ),
        AttachmentDeclaration(
            source_unit_selection_id="support-unit",
            bodyguard_unit_selection_id="bodyguard-unit",
        ),
    )


def _attached_formation_for_player(
    *,
    state: GameState,
    player_id: str,
) -> AttachedUnitFormation:
    for army in state.army_definitions:
        if army.player_id == player_id:
            if not army.attached_units:
                raise AssertionError(f"missing attached formation for {player_id}")
            return army.attached_units[0]
    raise AssertionError(f"missing army for {player_id}")


def _replace_unit_toughness(
    *,
    state: GameState,
    unit: UnitInstance,
    toughness: int,
) -> UnitInstance:
    replacement = replace(
        unit,
        own_models=tuple(
            _model_with_characteristic(
                model,
                characteristic=Characteristic.TOUGHNESS,
                raw_value=toughness,
            )
            for model in unit.own_models
        ),
    )
    _replace_unit_instance_in_state(state=state, replacement=replacement)
    return replacement


def _shooting_lifecycle(
    *,
    alpha_unit_ids: tuple[str, ...],
    game_id: str = "phase13b-game",
    alpha_datasheets: dict[str, tuple[str, str, int]] | None = None,
    alpha_unit_specs: tuple[tuple[str, str, str, int], ...] | None = None,
    alpha_attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
    enemy_datasheet: tuple[str, str, int] | None = None,
    enemy_unit_specs: tuple[tuple[str, str, str, int], ...] | None = None,
    enemy_attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
    embarked_unit_ids: tuple[str, ...] = (),
    enemy_pose: Pose | None = None,
    catalog: ArmyCatalog | None = None,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    resolved_enemy_pose = Pose.at(35.0, 35.0) if enemy_pose is None else enemy_pose
    config = _config(
        game_id=game_id,
        alpha_unit_ids=alpha_unit_ids,
        alpha_datasheets=alpha_datasheets,
        alpha_unit_specs=alpha_unit_specs,
        alpha_attachment_declarations=alpha_attachment_declarations,
        enemy_datasheet=enemy_datasheet,
        enemy_unit_specs=enemy_unit_specs,
        enemy_attachment_declarations=enemy_attachment_declarations,
        catalog=catalog,
    )
    armies = _mustered_armies(config)
    mission_setup = config.mission_setup
    assert mission_setup is not None
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase13b-battlefield",
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        armies=armies,
    )
    units = {
        unit.unit_instance_id.split(":", maxsplit=1)[1]: unit
        for army in armies
        for unit in army.units
    }
    battlefield = scenario.battlefield_state
    friendly_unit_index = 0
    enemy_unit_index = 0
    for unit_key, unit in units.items():
        if unit_key in embarked_unit_ids:
            battlefield = battlefield.without_unit_placement(unit.unit_instance_id)
            continue
        army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
        player_id = "player-a" if army_id == "army-alpha" else "player-b"
        if army_id == "army-beta":
            poses = _compact_test_unit_poses(
                origin=Pose.at(
                    resolved_enemy_pose.position.x,
                    resolved_enemy_pose.position.y + (enemy_unit_index * 10.0),
                    resolved_enemy_pose.position.z,
                    facing_degrees=180.0,
                ),
                model_count=len(unit.own_models),
            )
            enemy_unit_index += 1
        elif unit.datasheet_id == "core-transport":
            poses = (Pose.at(10.0, 35.0 + (friendly_unit_index * 10.0)),)
        else:
            friendly_y = 35.0 + (friendly_unit_index * 10.0)
            poses = _compact_test_unit_poses(
                origin=Pose.at(10.0, friendly_y),
                model_count=len(unit.own_models),
            )
        battlefield = battlefield.with_unit_placement(
            _unit_placement_at(unit, army_id=army_id, player_id=player_id, poses=poses)
        )
        if army_id == "army-alpha":
            friendly_unit_index += 1
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.battle_round = 1
    state.active_player_id = "player-a"
    if embarked_unit_ids:
        transport = units["transport-1"]
        state.record_transport_cargo_state(
            TransportCargoState(
                player_id="player-a",
                transport_unit_instance_id=transport.unit_instance_id,
                capacity_profile=TransportCapacityProfile(
                    transport_datasheet_id=transport.datasheet_id,
                    max_model_count=10,
                    allowed_keywords=("INFANTRY",),
                ),
                embarked_unit_instance_ids=tuple(
                    units[unit_key].unit_instance_id for unit_key in embarked_unit_ids
                ),
                phase_battle_round=1,
                started_phase_embarked_unit_instance_ids=tuple(
                    units[unit_key].unit_instance_id for unit_key in embarked_unit_ids
                ),
            )
        )
    payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": lifecycle_decisions_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    return GameLifecycle.from_payload(payload), units


def _compact_test_unit_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
    if type(model_count) is not int or model_count < 1:
        raise AssertionError("Test unit poses require at least one model.")
    return tuple(
        Pose.at(
            origin.position.x + ((index % 5) * 1.4),
            origin.position.y + ((index // 5) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(model_count)
    )


def lifecycle_decisions_payload() -> dict[str, object]:
    lifecycle = GameLifecycle()
    return cast(dict[str, object], lifecycle.decision_controller.to_payload())


def _catalog_with_extra_bolt_profile(extra_profile: WeaponProfile) -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    updated_wargear: list[Wargear] = []
    for wargear in catalog.wargear:
        if wargear.wargear_id == "core-bolt-rifle":
            updated_wargear.append(
                replace(
                    wargear,
                    weapon_profiles=(*wargear.weapon_profiles, extra_profile),
                )
            )
            continue
        updated_wargear.append(wargear)
    return replace(catalog, wargear=tuple(updated_wargear))


def _catalog_with_replaced_bolt_profiles(
    weapon_profiles: tuple[WeaponProfile, ...],
) -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    updated_wargear: list[Wargear] = []
    for wargear in catalog.wargear:
        if wargear.wargear_id == "core-bolt-rifle":
            updated_wargear.append(replace(wargear, weapon_profiles=weapon_profiles))
            continue
        updated_wargear.append(wargear)
    return replace(catalog, wargear=tuple(updated_wargear))


def _catalog_with_same_profile_id_target_cache_collision_weapons() -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    long_profile = replace(
        base_profile,
        profile_id="default",
        name="Phase 14 cache long rifle",
        range_profile=RangeProfile.distance(36),
        keywords=(),
        abilities=(),
    )
    short_profile = replace(
        base_profile,
        profile_id="default",
        name="Phase 14 cache short mortar",
        range_profile=RangeProfile.distance(6),
        keywords=(WeaponKeyword.INDIRECT_FIRE,),
        abilities=(),
    )
    long_wargear = Wargear(
        wargear_id="phase14-cache-long-rifle",
        name="Phase 14 cache long rifle",
        weapon_profiles=(long_profile,),
    )
    short_wargear = Wargear(
        wargear_id="phase14-cache-short-mortar",
        name="Phase 14 cache short mortar",
        weapon_profiles=(short_profile,),
    )
    updated_datasheets: list[DatasheetDefinition] = []
    for datasheet in catalog.datasheets:
        if datasheet.datasheet_id != "core-intercessor-like-infantry":
            updated_datasheets.append(datasheet)
            continue
        updated_datasheets.append(
            replace(
                datasheet,
                wargear_options=(
                    DatasheetWargearOption(
                        option_id="phase14-cache-profile-id-collision-weapons",
                        model_profile_id="core-intercessor-like",
                        default_wargear_ids=(
                            long_wargear.wargear_id,
                            short_wargear.wargear_id,
                        ),
                        allowed_wargear_ids=(
                            long_wargear.wargear_id,
                            short_wargear.wargear_id,
                        ),
                        min_selections=2,
                        max_selections=2,
                    ),
                ),
            )
        )
    return replace(
        catalog,
        datasheets=tuple(updated_datasheets),
        wargear=(*catalog.wargear, long_wargear, short_wargear),
    )


def _catalog_with_deadly_demise_datasheet(*, token: str) -> ArmyCatalog:
    return _catalog_with_core_datasheet_ability(
        DatasheetAbilityDescriptor(
            ability_id="core-deadly-demise",
            name=f"Deadly Demise {token}",
            source_id="datasheet:core-intercessor-like-infantry:ability:deadly-demise",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.CORE,
            effect_description="CORE Deadly Demise descriptor.",
            timing_tags=("after_destroyed", "deadly_demise"),
            parameter_tokens=(token,),
        )
    )


def _catalog_with_core_feel_no_pain_datasheet(*, token: str) -> ArmyCatalog:
    return _catalog_with_core_datasheet_ability(
        DatasheetAbilityDescriptor(
            ability_id="core-feel-no-pain",
            name=f"Feel No Pain {token}",
            source_id="datasheet:core-intercessor-like-infantry:ability:feel-no-pain",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.CORE,
            effect_description="CORE Feel No Pain descriptor.",
            timing_tags=("lost_wound", "feel_no_pain"),
            parameter_tokens=(token,),
        )
    )


def _catalog_with_lone_operative_datasheet() -> ArmyCatalog:
    return _catalog_with_core_datasheet_ability(
        DatasheetAbilityDescriptor(
            ability_id="core-lone-operative",
            name="Lone Operative",
            source_id="datasheet:core-intercessor-like-infantry:ability:lone-operative",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.CORE,
            effect_description="CORE Lone Operative descriptor.",
            timing_tags=("target_selection", "lone_operative"),
        )
    )


def _catalog_with_stealth_datasheet() -> ArmyCatalog:
    return _catalog_with_core_datasheet_ability(
        DatasheetAbilityDescriptor(
            ability_id="core-stealth",
            name="Stealth",
            source_id="datasheet:core-intercessor-like-infantry:ability:stealth",
            support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
            source_kind=CatalogAbilitySourceKind.CORE,
            effect_description="CORE Stealth descriptor.",
            timing_tags=("ranged_attack", "stealth"),
        )
    )


def _catalog_with_core_datasheet_ability(
    ability: DatasheetAbilityDescriptor,
) -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    if type(ability) is not DatasheetAbilityDescriptor:
        raise AssertionError("Test catalog core ability requires a descriptor.")
    updated_datasheets: list[DatasheetDefinition] = []
    for datasheet in catalog.datasheets:
        if datasheet.datasheet_id != "core-intercessor-like-infantry":
            updated_datasheets.append(datasheet)
            continue
        updated_datasheets.append(
            replace(
                datasheet,
                abilities=tuple(
                    sorted(
                        (*datasheet.abilities, ability),
                        key=lambda stored: stored.ability_id,
                    )
                ),
            )
        )
    return replace(catalog, datasheets=tuple(updated_datasheets))


def _single_deadly_demise_source(
    *,
    state: GameState,
    model_instance_id: str,
) -> DestructionReactionSource:
    sources = tuple(
        source
        for source in state.destruction_reaction_sources_for_model(
            model_instance_id=model_instance_id
        )
        if source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE
    )
    if len(sources) != 1:
        raise AssertionError(f"expected one Deadly Demise source, found {len(sources)}")
    return sources[0]


def _config(
    *,
    game_id: str = "phase13b-game",
    alpha_unit_ids: tuple[str, ...],
    alpha_datasheets: dict[str, tuple[str, str, int]] | None,
    alpha_unit_specs: tuple[tuple[str, str, str, int], ...] | None = None,
    alpha_attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
    enemy_datasheet: tuple[str, str, int] | None,
    enemy_unit_specs: tuple[tuple[str, str, str, int], ...] | None = None,
    enemy_attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
    catalog: ArmyCatalog | None = None,
) -> GameConfig:
    resolved_catalog = ArmyCatalog.phase9a_canonical_content_pack() if catalog is None else catalog
    enemy_datasheet_id, enemy_model_profile_id, enemy_model_count = (
        ("core-intercessor-like-infantry", "core-intercessor-like", 5)
        if enemy_datasheet is None
        else enemy_datasheet
    )
    beta_unit_specs = (
        (("enemy", enemy_datasheet_id, enemy_model_profile_id, enemy_model_count),)
        if enemy_unit_specs is None
        else enemy_unit_specs
    )
    resolved_alpha_unit_specs = (
        tuple(
            _alpha_unit_spec(
                unit_id=unit_id,
                alpha_datasheets=alpha_datasheets,
            )
            for unit_id in alpha_unit_ids
        )
        if alpha_unit_specs is None
        else alpha_unit_specs
    )
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=resolved_catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=resolved_catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_specs=resolved_alpha_unit_specs,
                attachment_declarations=alpha_attachment_declarations,
            ),
            _army_muster_request(
                catalog=resolved_catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_specs=beta_unit_specs,
                attachment_declarations=enemy_attachment_declarations,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _alpha_unit_spec(
    *,
    unit_id: str,
    alpha_datasheets: dict[str, tuple[str, str, int]] | None,
) -> tuple[str, str, str, int]:
    if alpha_datasheets is not None and unit_id in alpha_datasheets:
        datasheet_id, model_profile_id, model_count = alpha_datasheets[unit_id]
        return (unit_id, datasheet_id, model_profile_id, model_count)
    return (unit_id, "core-intercessor-like-infantry", "core-intercessor-like", 5)


def _mission_setup() -> MissionSetup:
    mission_pack = chapter_approved_2026_27_mission_pack()
    return MissionSetup(
        mission_pack_id=mission_pack.mission_pack_id,
        source_version=mission_pack.source_version,
        source_id=mission_pack.source_id,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        primary_mission_id="take-and-hold",
        battlefield_layout_id=None,
        deployment_map_id="phase13b-open-map",
        terrain_layout_id="phase13b-open-layout",
        attacker_player_id="player-a",
        defender_player_id="player-b",
        battlefield_width_inches=100.0,
        battlefield_depth_inches=60.0,
        objective_markers=(
            ObjectiveMarkerDefinition(
                objective_marker_id="phase13b-remote-objective",
                name="Phase 13B Remote Objective",
                objective_role=ObjectiveMarkerRole.CENTRAL,
                x_inches=95.0,
                y_inches=55.0,
                source_id="phase13b-test",
            ),
        ),
        deployment_zones=(),
        battlefield_regions=(),
        terrain_areas=(),
        terrain_features=(),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_specs: tuple[tuple[str, str, str, int], ...],
    attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
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
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_id,
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id=model_profile_id,
                        model_count=model_count,
                    ),
                ),
            )
            for unit_id, datasheet_id, model_profile_id, model_count in unit_specs
        ),
        attachment_declarations=attachment_declarations,
    )


def _proposal_from_request(
    *,
    request: DecisionRequest,
    target_unit_id: str,
    firing_deck_unit: UnitInstance | None = None,
    weapon_profile_id: str | None = None,
    selected_weapon_ability_ids: tuple[str, ...] = (),
) -> ShootingDeclarationProposal:
    payload = cast(dict[str, object], request.payload)
    proposal_request = cast(dict[str, object], payload["proposal_request"])
    weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
    target_candidates = cast(list[dict[str, object]], proposal_request["target_candidates"])
    target_candidate = next(
        candidate
        for candidate in target_candidates
        if candidate["target_unit_instance_id"] == target_unit_id and candidate["is_legal"] is True
    )
    selected_weapon = (
        weapons[0]
        if weapon_profile_id is None
        else next(weapon for weapon in weapons if weapon["weapon_profile_id"] == weapon_profile_id)
    )
    declarations = [
        WeaponDeclaration(
            attacker_model_instance_id=cast(str, selected_weapon["model_instance_id"]),
            wargear_id=cast(str, selected_weapon["wargear_id"]),
            weapon_profile_id=cast(str, selected_weapon["weapon_profile_id"]),
            target_unit_instance_id=target_unit_id,
            shooting_type=_first_shooting_type(target_candidate),
            selected_weapon_ability_ids=selected_weapon_ability_ids,
        )
    ]
    firing_deck_selection = None
    if firing_deck_unit is not None:
        passenger_model = firing_deck_unit.own_models[0]
        passenger_wargear_id = firing_deck_unit.wargear_selections[0].wargear_ids[0]
        passenger_profile = next(
            weapon
            for weapon in weapons
            if weapon.get("firing_deck_source_model_instance_id")
            == passenger_model.model_instance_id
        )
        declarations.append(
            WeaponDeclaration(
                attacker_model_instance_id=cast(str, passenger_profile["model_instance_id"]),
                wargear_id=passenger_wargear_id,
                weapon_profile_id=cast(str, passenger_profile["weapon_profile_id"]),
                target_unit_instance_id=target_unit_id,
                shooting_type=_first_shooting_type(target_candidate),
                firing_deck_source_unit_instance_id=firing_deck_unit.unit_instance_id,
                firing_deck_source_model_instance_id=passenger_model.model_instance_id,
            )
        )
        firing_deck_selection = FiringDeckSelection(
            player_id="player-a",
            battle_round=1,
            transport_unit_instance_id=cast(str, proposal_request["unit_instance_id"]),
            firing_deck_value=cast(int, proposal_request["firing_deck_value"]),
            weapon_selections=(
                FiringDeckWeaponSelection(
                    embarked_unit_instance_id=firing_deck_unit.unit_instance_id,
                    model_instance_id=passenger_model.model_instance_id,
                    wargear_id=passenger_wargear_id,
                    weapon_profile=WeaponProfile.from_payload(
                        cast(WeaponProfilePayload, passenger_profile["weapon_profile"])
                    ),
                ),
            ),
            already_shot_unit_instance_ids=(),
        )
    return ShootingDeclarationProposal(
        proposal_request_id=cast(str, proposal_request["request_id"]),
        proposal_kind="shooting_declaration",
        player_id=cast(str, proposal_request["active_player_id"]),
        battle_round=cast(int, proposal_request["battle_round"]),
        unit_instance_id=cast(str, proposal_request["unit_instance_id"]),
        source_decision_request_id=cast(str, proposal_request["source_decision_request_id"]),
        source_decision_result_id=cast(str, proposal_request["source_decision_result_id"]),
        declarations=tuple(declarations),
        firing_deck_selection=firing_deck_selection,
        visibility_cache_key=cast(str, target_candidate["visibility_cache_key"]),
    )


def _proposal_from_declarations(
    *,
    request: DecisionRequest,
    declarations: tuple[WeaponDeclaration, ...],
) -> ShootingDeclarationProposal:
    payload = cast(dict[str, object], request.payload)
    proposal_request = cast(dict[str, object], payload["proposal_request"])
    return ShootingDeclarationProposal(
        proposal_request_id=cast(str, proposal_request["request_id"]),
        proposal_kind="shooting_declaration",
        player_id=cast(str, proposal_request["active_player_id"]),
        battle_round=cast(int, proposal_request["battle_round"]),
        unit_instance_id=cast(str, proposal_request["unit_instance_id"]),
        source_decision_request_id=cast(str, proposal_request["source_decision_request_id"]),
        source_decision_result_id=cast(str, proposal_request["source_decision_result_id"]),
        declarations=declarations,
        firing_deck_selection=None,
        visibility_cache_key=cast(str, proposal_request["visibility_cache_key"]),
    )


def _phase14l_multi_group_lifecycle(
    *,
    game_id: str,
) -> tuple[GameLifecycle, dict[str, UnitInstance], WeaponProfile]:
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id=None,
    )
    heavy_profile = replace(
        base_profile,
        profile_id=f"{game_id}-heavy-bolt",
        strength=CharacteristicValue.from_raw(
            Characteristic.STRENGTH,
            base_profile.strength.final + 1,
        ),
    )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_specs=(
            ("enemy-a", "core-intercessor-like-infantry", "core-intercessor-like", 5),
            ("enemy-b", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
        catalog=_catalog_with_extra_bolt_profile(heavy_profile),
        game_id=game_id,
    )
    return lifecycle, units, heavy_profile


def _phase14l_submit_multi_group_declaration(
    *,
    lifecycle: GameLifecycle,
    units: dict[str, UnitInstance],
    heavy_profile: WeaponProfile,
    result_prefix: str,
) -> DecisionRequest:
    first_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=first_request,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id=f"{result_prefix}-select-shooter",
    )
    declarations = _phase14l_multi_target_declarations(
        declaration_request=declaration_request,
        first_target_id=units["enemy-a"].unit_instance_id,
        second_target_id=units["enemy-b"].unit_instance_id,
        extra_profile_id=heavy_profile.profile_id,
    )
    proposal = _proposal_from_declarations(
        request=declaration_request,
        declarations=declarations,
    )
    return _decision_request(
        _submit_payload(
            lifecycle,
            request=declaration_request,
            payload=proposal.to_payload(),
            result_id=f"{result_prefix}-declaration",
        )
    )


def _phase14l_multi_target_declarations(
    *,
    declaration_request: DecisionRequest,
    first_target_id: str,
    second_target_id: str,
    extra_profile_id: str,
) -> tuple[WeaponDeclaration, ...]:
    payload = cast(dict[str, object], declaration_request.payload)
    proposal_request = cast(dict[str, object], payload["proposal_request"])
    weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
    base_weapons = [weapon for weapon in weapons if weapon["weapon_profile_id"] != extra_profile_id]
    extra_weapons = [
        weapon for weapon in weapons if weapon["weapon_profile_id"] == extra_profile_id
    ]
    first_base_weapon = base_weapons[0]
    extra_weapon = next(
        weapon
        for weapon in extra_weapons
        if weapon["model_instance_id"] != first_base_weapon["model_instance_id"]
    )
    used_model_ids = {
        cast(str, first_base_weapon["model_instance_id"]),
        cast(str, extra_weapon["model_instance_id"]),
    }
    second_base_weapon = next(
        weapon for weapon in base_weapons if weapon["model_instance_id"] not in used_model_ids
    )
    return (
        WeaponDeclaration.from_payload(
            _weapon_payload_to_declaration_payload(
                weapon=first_base_weapon,
                target_unit_id=first_target_id,
            )
        ),
        WeaponDeclaration.from_payload(
            _weapon_payload_to_declaration_payload(
                weapon=extra_weapon,
                target_unit_id=first_target_id,
            )
        ),
        WeaponDeclaration.from_payload(
            _weapon_payload_to_declaration_payload(
                weapon=second_base_weapon,
                target_unit_id=second_target_id,
            )
        ),
    )


def _weapon_payload_to_declaration_payload(
    *,
    weapon: dict[str, object],
    target_unit_id: str,
    shooting_type: ShootingType = ShootingType.NORMAL,
) -> WeaponDeclarationPayload:
    payload: WeaponDeclarationPayload = {
        "attacker_model_instance_id": cast(str, weapon["model_instance_id"]),
        "wargear_id": cast(str, weapon["wargear_id"]),
        "weapon_profile_id": cast(str, weapon["weapon_profile_id"]),
        "target_unit_instance_id": target_unit_id,
        "shooting_type": shooting_type.value,
        "selected_weapon_ability_ids": [],
        "firing_deck_source_unit_instance_id": None,
        "firing_deck_source_model_instance_id": None,
    }
    if "firing_deck_source_unit_instance_id" in weapon:
        payload["firing_deck_source_unit_instance_id"] = cast(
            str,
            weapon["firing_deck_source_unit_instance_id"],
        )
        payload["firing_deck_source_model_instance_id"] = cast(
            str,
            weapon["firing_deck_source_model_instance_id"],
        )
    return payload


def _first_shooting_type(target_candidate: dict[str, object]) -> ShootingType:
    shooting_types = cast(list[str], target_candidate["shooting_types"])
    if not shooting_types:
        raise AssertionError("Target candidate has no shooting types.")
    return ShootingType(shooting_types[0])


def _submit_result(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option_id,
        )
    )


def _select_shooting_unit_and_type(
    lifecycle: GameLifecycle,
    *,
    selection_request: DecisionRequest,
    unit_instance_id: str,
    selection_result_id: str,
    shooting_type: ShootingType = ShootingType.NORMAL,
    type_result_id: str | None = None,
) -> DecisionRequest:
    type_request = _decision_request(
        _submit_result(
            lifecycle,
            request=selection_request,
            option_id=unit_instance_id,
            result_id=selection_result_id,
        )
    )
    assert type_request.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE
    type_payload = cast(dict[str, object], type_request.payload)
    assert type_payload["unit_instance_id"] == unit_instance_id
    assert shooting_type.value in {option.option_id for option in type_request.options}

    declaration_request = _decision_request(
        _submit_result(
            lifecycle,
            request=type_request,
            option_id=shooting_type.value,
            result_id=type_result_id or f"{selection_result_id}-type",
        )
    )
    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
    return declaration_request


def _submit_payload(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    payload: object,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id="submit_parameterized_payload",
            payload=validate_json_value(payload),
        )
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _assert_waiting_for_movement_unit(status: LifecycleStatus) -> DecisionRequest:
    request = _decision_request(status)
    assert request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return request


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    return lifecycle.state


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase13b-test")


def _attack_sequence_private(name: str) -> Any:
    return getattr(attack_sequence_module, name)


def _shooting_phase_private(name: str) -> Any:
    return getattr(shooting_phase_module, name)


def _benefit_of_cover_result() -> BenefitOfCoverResult:
    source_record = CoverSourceRecord(
        feature_id="phase13c-cover-ruin",
        feature_kind=TerrainFeatureKind.RUINS,
        policy_kind=LineOfSightPolicy.TRUE_LINE_OF_SIGHT,
        reason=CoverSourceReason.NOT_FULLY_VISIBLE_BECAUSE_OF_FEATURE,
    )
    return BenefitOfCoverResult(
        has_benefit=True,
        cover_effect=CoverEffect.ATTACKER_BS_MODIFIER,
        source_feature_ids=("phase13c-cover-ruin",),
        source_policy_kinds=(LineOfSightPolicy.TRUE_LINE_OF_SIGHT,),
        source_records=(source_record,),
        los_cache_key="phase13c-cover-cache",
        target_unit_visible=True,
        target_unit_fully_visible=False,
        non_stacking=True,
        ap_zero_save_bonus_excluded_for_save_3_plus_or_better=True,
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


def _phase18b_shooting_hit_command_reroll_status() -> tuple[
    GameLifecycle,
    UnitInstance,
    AttackSequence | None,
    tuple[str, ...],
    LifecycleStatus | None,
]:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    _grant_command_reroll_cp(state, player_id="player-a")
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase18b-command-reroll-hit",
    )
    sequence_id = "phase18b-command-reroll-hit"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )
    sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )

    remaining, allocated, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id=f"{sequence_id}:hit", spec=hit_spec, value=2),
            ),
        ),
        stratagem_index=eleventh_edition_stratagem_index(),
    )
    return lifecycle, attacker, remaining, allocated, status


def _grant_command_reroll_cp(state: GameState, *, player_id: str) -> None:
    state.gain_command_points(
        player_id=player_id,
        amount=1,
        source_id=f"phase18b-command-reroll-cp-{player_id}",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )


def _assert_command_reroll_request(
    status: LifecycleStatus | None,
    *,
    actor_id: str,
    phase_body_status: str,
    roll_type: str,
    affected_unit_instance_id: str,
) -> DecisionRequest:
    assert status is not None
    request = _decision_request(status)
    assert request.decision_type == "use_stratagem"
    assert request.actor_id == actor_id
    status_payload = cast(dict[str, object], status.payload)
    assert status_payload["phase_body_status"] == phase_body_status
    option_ids = {option.option_id for option in request.options}
    assert any(option_id.startswith("use-stratagem:command-reroll:") for option_id in option_ids)
    assert "decline_stratagem_window" in option_ids
    payload = cast(dict[str, object], request.payload)
    assert payload["submission_family"] == "opportunity_window"
    opportunity = cast(dict[str, object], payload["opportunity_window"])
    assert payload["opportunity_window_id"] == opportunity["window_id"]
    assert opportunity["state_hash"]
    assert isinstance(opportunity["sequence_number"], int)
    assert cast(list[object], opportunity["anchor_event_ids"])
    context = cast(dict[str, object], payload["stratagem_context"])
    trigger_payload = cast(dict[str, object], context["trigger_payload"])
    assert context["trigger_kind"] == "after_dice_roll"
    assert trigger_payload["roll_type"] == roll_type
    assert trigger_payload["affected_unit_instance_id"] == affected_unit_instance_id
    use_option = request.option_by_id(_command_reroll_use_option_id(request))
    use_payload = cast(dict[str, object], use_option.payload)
    opportunity_submission = cast(dict[str, object], use_payload["opportunity_submission"])
    assert opportunity_submission["window_id"] == payload["opportunity_window_id"]
    assert opportunity_submission["state_hash"] == opportunity["state_hash"]
    action = cast(dict[str, object], opportunity_submission["action"])
    assert action["action_id"] == use_option.option_id
    assert action["source_id"] == "core:command-reroll"
    return request


def _command_reroll_use_option_id(request: DecisionRequest) -> str:
    for option in request.options:
        if option.option_id.startswith("use-stratagem:command-reroll:"):
            return option.option_id
    raise AssertionError("Command Re-roll use option was not emitted.")


def _model_with_characteristic(
    model: ModelInstance,
    *,
    characteristic: Characteristic,
    raw_value: int,
) -> ModelInstance:
    replacement = CharacteristicValue.from_raw(characteristic, raw_value)
    characteristics = tuple(
        replacement if value.characteristic is characteristic else value
        for value in model.characteristics
    )
    if replacement not in characteristics:
        characteristics = (*characteristics, replacement)
    return replace(model, characteristics=characteristics)


def _model_with_attached_role(model: ModelInstance, *, role: str) -> ModelInstance:
    if role not in {"bodyguard", "leader", "support"}:
        raise AssertionError(f"Unsupported attached role in test fixture: {role}.")
    source_ids = {
        source_id
        for source_id in model.source_ids
        if not source_id.startswith(("attached-role:", "runtime-attached-unit:"))
        and source_id != "datasheet:core-character-leader"
    }
    source_ids.add(f"runtime-attached-unit:{role}")
    if role in {"leader", "support"}:
        source_ids.add(f"attached-role:{role}")
    return replace(model, source_ids=tuple(sorted(source_ids)))


def _attack_pool_for_test(
    *,
    attacker: UnitInstance,
    defender: UnitInstance,
    weapon_profile: WeaponProfile,
    attacks: int,
    target_unit_instance_id: str | None = None,
) -> RangedAttackPool:
    defender_model_ids = tuple(model.model_instance_id for model in defender.own_models)
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id=attacker.wargear_selections[0].wargear_ids[0],
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=(
            defender.unit_instance_id
            if target_unit_instance_id is None
            else target_unit_instance_id
        ),
        shooting_type=ShootingType.NORMAL,
        attacks=attacks,
        target_visible_model_ids=defender_model_ids,
        target_in_range_model_ids=defender_model_ids,
    )


def _destroyed_transport_pending_for_test(
    *,
    sequence_id: str,
    attacker: UnitInstance,
    transport: UnitInstance,
    passenger: UnitInstance,
) -> PendingDestroyedTransportDisembark:
    transport_model = transport.own_models[0]
    return PendingDestroyedTransportDisembark(
        attack_context=_destroyed_transport_attack_context_for_test(
            sequence_id=sequence_id,
            attacker=attacker,
            transport=transport,
        ),
        damage_application=DamageApplication(
            target_unit_instance_id=transport.unit_instance_id,
            model_instance_id=transport_model.model_instance_id,
            damage_kind=DamageKind.NORMAL,
            requested_damage=transport_model.wounds_remaining,
            wounds_lost=transport_model.wounds_remaining,
            excess_damage_lost=0,
            starting_wounds_remaining=transport_model.wounds_remaining,
            final_wounds_remaining=0,
            destroyed=True,
        ),
        saving_throw_payload={
            "save_kind": SaveKind.ARMOUR.value,
            "successful": False,
        },
        feel_no_pain=FeelNoPainResolution.declined(
            requested_wounds=transport_model.wounds_remaining
        ),
        destroyed_model_controller_player_id="player-b",
        transport_unit_instance_id=transport.unit_instance_id,
        pending_unit_instance_ids=(passenger.unit_instance_id,),
        pending_sources=(
            DestructionReactionSource(
                source_id=f"{sequence_id}-deadly-demise",
                reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
                source_rule_id=f"{sequence_id}-deadly-demise-rule",
                payload={
                    "trigger_roll_threshold": 6,
                    "range_inches": 0.1,
                    "mortal_wounds": {"kind": "fixed", "value": 1},
                },
                optional=False,
            ),
        ),
    )


def _destroyed_transport_attack_context_for_test(
    *,
    sequence_id: str,
    attacker: UnitInstance,
    transport: UnitInstance,
) -> AttackResolutionContextPayload:
    weapon_profile = _weapon_profile_by_wargear(
        wargear_id=attacker.wargear_selections[0].wargear_ids[0],
        weapon_profile_id=None,
    )
    strength = 10
    toughness = 5
    return {
        "sequence_id": sequence_id,
        "source_phase": BattlePhase.SHOOTING.value,
        "attack_context_id": f"{sequence_id}:pool-001:attack-001",
        "pool_index": 0,
        "attack_index": 0,
        "generated_hit_index": 0,
        "attacker_player_id": "player-a",
        "defender_player_id": "player-b",
        "attacking_unit_instance_id": attacker.unit_instance_id,
        "attacker_model_instance_id": attacker.own_models[0].model_instance_id,
        "target_unit_instance_id": transport.unit_instance_id,
        "weapon_profile_id": weapon_profile.profile_id,
        "selected_weapon_ability_ids": [],
        "is_psychic_attack": False,
        "damage_profile": DamageProfile.fixed(
            transport.own_models[0].wounds_remaining
        ).to_payload(),
        "hit_roll": HitRoll.auto_hit(target_number=3).to_payload(),
        "wound_roll": WoundRoll.auto_wound(
            strength=strength,
            toughness=toughness,
            target_number=wound_roll_target_number(strength=strength, toughness=toughness),
        ).to_payload(),
        "allocation": None,
        "save_options": [],
    }


def _destroyed_transport_proposal_request_for_test(
    *,
    state: GameState,
    pending: PendingDestroyedTransportDisembark,
    sequence: AttackSequence,
    unit_instance_id: str,
    request_id: str,
) -> DecisionRequest:
    attack_context_id = pending.attack_context["attack_context_id"]
    return MovementProposalRequest(
        request_id=request_id,
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=pending.destroyed_model_controller_player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=sequence.source_phase.value,
        unit_instance_id=unit_instance_id,
        proposal_kind=ProposalKind.DISEMBARK,
        source_decision_request_id=f"{attack_context_id}:destroyed-transport",
        source_decision_result_id=f"{attack_context_id}:destroyed-transport",
        placement_kinds=(BattlefieldPlacementKind.DISEMBARK,),
        context={
            "destruction_timing": "destroyed_transport",
            "transport_unit_instance_id": pending.transport_unit_instance_id,
            "disembark_mode": DisembarkModeKind.EMERGENCY_DISEMBARK.value,
            "transport_movement_status": TransportMovementStatus.NOT_MOVED.value,
            "attack_sequence_id": sequence.sequence_id,
            "attack_context_id": attack_context_id,
            "destroyed_model_instance_id": pending.damage_application.model_instance_id,
        },
    ).to_decision_request()


def _destroyed_transport_placement_payload_for_test(
    *,
    proposal_request: MovementProposalRequest,
    unit: UnitInstance,
    transport: UnitInstance,
) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        PlacementProposalPayload(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            unit_instance_id=unit.unit_instance_id,
            placement_kind=BattlefieldPlacementKind.DISEMBARK,
            attempted_placement=_unit_placement_at(
                unit,
                army_id="army-beta",
                player_id="player-b",
                poses=tuple(
                    Pose.at(38.0 + (0.7 * index), 34.0 + (0.5 * index))
                    for index, _model in enumerate(unit.own_models)
                ),
            ),
            transport_unit_instance_id=transport.unit_instance_id,
            disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ).to_payload(),
    )


def _destroyed_transport_hazard_roll_results_for_test(
    attempted_placement: UnitPlacement,
    *,
    values: tuple[int, ...],
    roll_id_prefix: str,
) -> tuple[DiceRollResult, ...]:
    if len(values) != len(attempted_placement.model_placements):
        raise AssertionError("Destroyed Transport hazard roll values must match placed models.")
    return tuple(
        DiceRollResult.from_values(
            roll_id=f"{roll_id_prefix}-{index:03d}",
            spec=hazard_roll_spec(
                reason=(
                    f"Destroyed Transport disembark roll for {model_placement.model_instance_id}"
                ),
                roll_type="destroyed_transport_disembark",
                actor_id=model_placement.model_instance_id,
            ),
            values=(roll_value,),
            source="injected",
        )
        for index, (model_placement, roll_value) in enumerate(
            zip(attempted_placement.model_placements, values, strict=True),
            start=1,
        )
    )


def _proposal_decision_result(
    *,
    request: DecisionRequest,
    payload: object,
    result_id: str,
) -> DecisionResult:
    return DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="submit_parameterized_payload",
        payload=validate_json_value(payload),
    )


def _record_parameterized_result_for_apply(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    payload: object,
    result_id: str,
) -> DecisionResult:
    lifecycle.decision_controller.request_decision(request)
    result = _proposal_decision_result(
        request=request,
        payload=payload,
        result_id=result_id,
    )
    lifecycle.decision_controller.submit_result(result)
    return result


def _assert_invalid_proposal_status(
    status: LifecycleStatus | None,
    *,
    expected_code: str,
    expected_field: str | None,
) -> None:
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    payload = cast(dict[str, object], status.payload)
    validation = cast(dict[str, object], payload["proposal_validation"])
    violations = cast(list[dict[str, object]], validation["violations"])
    assert validation["is_valid"] is False
    assert violations[0]["violation_code"] == expected_code
    assert violations[0]["field"] == expected_field


def _replace_enemy_with_attached_character_fixture(
    *,
    state: GameState,
    defender: UnitInstance,
) -> UnitInstance:
    bodyguard_model = defender.own_models[0]
    character_model = replace(
        defender.own_models[1],
        source_ids=tuple(
            sorted(
                {
                    *defender.own_models[1].source_ids,
                    "attached-role:character",
                    "datasheet:core-character-leader",
                }
            )
        ),
    )
    attached_defender = replace(
        defender,
        keywords=tuple(sorted({*defender.keywords, "ATTACHED_UNIT"})),
        own_models=(bodyguard_model, character_model),
    )
    _replace_unit_instance_in_state(state=state, replacement=attached_defender)
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(defender.unit_instance_id)
    kept_model_ids = {model.model_instance_id for model in attached_defender.own_models}
    state.replace_battlefield_state(
        battlefield.with_unit_placement(
            placement.with_model_placements(
                tuple(
                    model_placement
                    for model_placement in placement.model_placements
                    if model_placement.model_instance_id in kept_model_ids
                )
            )
        )
    )
    return attached_defender


def _replace_unit_instance_in_state(
    *,
    state: GameState,
    replacement: UnitInstance,
) -> None:
    for army_index, army in enumerate(state.army_definitions):
        units = tuple(
            replacement if unit.unit_instance_id == replacement.unit_instance_id else unit
            for unit in army.units
        )
        if units != army.units:
            state.army_definitions[army_index] = replace(army, units=units)
            return
    raise AssertionError(f"Missing unit {replacement.unit_instance_id}.")


def _damage_model_choice_lifecycle(
    *,
    sequence_id: str,
) -> tuple[GameLifecycle, DecisionRequest, AttackSequence, tuple[str, ...], UnitInstance]:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",), game_id=sequence_id)
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id=f"{sequence_id}-profile",
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id=f"{sequence_id}-hit",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}-wound",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}-save",
                    spec=saving_throw_roll_spec(
                        save_kind=SaveKind.ARMOUR,
                        player_id="player-b",
                        allocated_model_id=defender.own_models[0].model_instance_id,
                        attack_context_id=attack_context_id,
                    ),
                    value=1,
                ),
            ),
        ),
    )
    if remaining_sequence is None:
        raise AssertionError("Damage model choice fixture unexpectedly completed.")
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        state.shooting_phase_state = ShootingPhaseState(
            battle_round=state.battle_round,
            active_player_id="player-a",
            selected_unit_ids=(attacker.unit_instance_id,),
            shot_unit_ids=(attacker.unit_instance_id,),
            attack_pools=remaining_sequence.attack_pools,
            attack_sequence=remaining_sequence,
            allocated_model_ids_this_phase=allocated_ids,
        )
    else:
        state.shooting_phase_state = shooting_state.with_attack_sequence_update(
            attack_sequence=remaining_sequence,
            allocated_model_ids_this_phase=allocated_ids,
        )
    return (
        lifecycle,
        _decision_request(cast(LifecycleStatus, status)),
        remaining_sequence,
        allocated_ids,
        defender,
    )


def _assert_stale_damage_model_choice_rejected_before_queue_pop(
    *,
    lifecycle: GameLifecycle,
    request: DecisionRequest,
    selected_model_id: str,
    result_id: str,
) -> None:
    before_attack_events = _save_and_damage_step_payloads(lifecycle)
    before_records = lifecycle.decision_controller.records
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=selected_model_id,
    )

    status = lifecycle.submit_decision(result)

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, object], status.payload)["invalid_reason"] == (
        "invalid_damage_allocation_model_result"
    )
    assert cast(dict[str, object], status.payload)["field"] == "selected_model_id"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert lifecycle.decision_controller.records == before_records
    assert _save_and_damage_step_payloads(lifecycle) == before_attack_events


def _save_and_damage_step_payloads(
    lifecycle: GameLifecycle,
) -> tuple[dict[str, object], ...]:
    return tuple(
        event
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] in {AttackSequenceStep.SAVE.value, AttackSequenceStep.DAMAGE.value}
    )


def _continue_damage_model_choices(
    lifecycle: GameLifecycle,
    *,
    attack_sequence: AttackSequence | None,
    allocated_ids: tuple[str, ...],
    status: LifecycleStatus | None,
    result_id_prefix: str,
) -> tuple[AttackSequence | None, LifecycleStatus | None]:
    if attack_sequence is not None:
        _store_shooting_attack_sequence(
            lifecycle=lifecycle,
            attack_sequence=attack_sequence,
            allocated_ids=allocated_ids,
        )
    current_status = status
    result_index = 1
    while current_status is not None:
        if current_status.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION:
            return _stored_shooting_attack_sequence(lifecycle), current_status
        request = _decision_request(current_status)
        if request.decision_type != SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE:
            return _stored_shooting_attack_sequence(lifecycle), current_status
        current_status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"{result_id_prefix}-{result_index:03d}",
                request=request,
                selected_option_id=request.options[0].option_id,
            )
        )
        result_index += 1
    return _stored_shooting_attack_sequence(lifecycle), None


def _drain_damage_model_choices_with_manager(
    *,
    lifecycle: GameLifecycle,
    attack_sequence: AttackSequence | None,
    allocated_ids: tuple[str, ...],
    status: LifecycleStatus | None,
    dice_manager: DiceRollManager,
    result_id_prefix: str,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    state = _state(lifecycle)
    current_sequence = attack_sequence
    current_allocated_ids = allocated_ids
    current_status = status
    for index in range(128):
        if current_status is None:
            if current_sequence is None:
                return None, current_allocated_ids, None
            current_sequence, current_allocated_ids, current_status = (
                resolve_attack_sequence_until_blocked(
                    state=state,
                    decisions=lifecycle.decision_controller,
                    ruleset_descriptor=_ruleset(),
                    attack_sequence=current_sequence,
                    already_allocated_model_ids=current_allocated_ids,
                    dice_manager=dice_manager,
                )
            )
            continue
        if current_status.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION:
            return current_sequence, current_allocated_ids, current_status
        request = _decision_request(current_status)
        if request.decision_type != SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE:
            return current_sequence, current_allocated_ids, current_status
        if current_sequence is None:
            raise AssertionError("Damage allocation decision requires an attack sequence.")
        result = DecisionResult.for_request(
            result_id=f"{result_id_prefix}-{index:03d}",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
        lifecycle.decision_controller.submit_result(result)
        current_sequence, current_allocated_ids, current_status = (
            apply_damage_allocation_model_decision(
                state=state,
                decisions=lifecycle.decision_controller,
                ruleset_descriptor=_ruleset(),
                attack_sequence=current_sequence,
                result=result,
                already_allocated_model_ids=current_allocated_ids,
                dice_manager=dice_manager,
            )
        )
    raise AssertionError("Attack sequence damage allocation choices did not drain.")


def _phase14l_test1_target_model(model: ModelInstance) -> ModelInstance:
    overrides = (
        (Characteristic.TOUGHNESS, 3),
        (Characteristic.WOUNDS, 1),
        (Characteristic.SAVE, 3),
        (Characteristic.INVULNERABLE_SAVE, 5),
    )
    override_values = dict(overrides)
    seen: set[Characteristic] = set()
    characteristics: list[CharacteristicValue] = []
    for value in model.characteristics:
        if value.characteristic in override_values:
            characteristics.append(
                CharacteristicValue.from_raw(
                    value.characteristic,
                    override_values[value.characteristic],
                )
            )
            seen.add(value.characteristic)
            continue
        characteristics.append(value)
    for characteristic, raw_value in overrides:
        if characteristic not in seen:
            characteristics.append(CharacteristicValue.from_raw(characteristic, raw_value))
    return replace(
        model,
        characteristics=tuple(characteristics),
        starting_wounds=1,
        wounds_remaining=1,
    )


def _phase14l_test1_dice_results(
    *,
    bolt_profile: WeaponProfile,
    heavy_profile: WeaponProfile,
    first_save_model_id: str,
    second_save_model_id: str,
) -> tuple[DiceRollResult, ...]:
    results: list[DiceRollResult] = []
    bolt_wound_rolls = iter((6, 3, 5, 1))
    for attack_number, hit_roll in enumerate((2, 4, 6, 4, 3), start=1):
        attack_context_id = f"phase14l-shooting-test1:pool-001:attack-{attack_number:03d}"
        results.append(
            _fixed_roll_result(
                roll_id=f"phase14l-test1-bolt-hit-{attack_number}",
                spec=_phase14l_test1_hit_spec(
                    profile=bolt_profile,
                    attack_context_id=attack_context_id,
                ),
                value=hit_roll,
            )
        )
        if hit_roll >= 3:
            results.append(
                _fixed_roll_result(
                    roll_id=f"phase14l-test1-bolt-wound-{attack_number}",
                    spec=_phase14l_test1_wound_spec(
                        profile=bolt_profile,
                        attack_context_id=attack_context_id,
                    ),
                    value=next(bolt_wound_rolls),
                )
            )
    for attack_number, save_roll in ((2, 6), (3, 4), (4, 2)):
        attack_context_id = f"phase14l-shooting-test1:pool-001:attack-{attack_number:03d}"
        results.append(
            _fixed_roll_result(
                roll_id=f"phase14l-test1-bolt-save-{attack_number}",
                spec=saving_throw_roll_spec(
                    save_kind=SaveKind.INVULNERABLE,
                    player_id="player-b",
                    allocated_model_id=first_save_model_id,
                    attack_context_id=attack_context_id,
                ),
                value=save_roll,
            )
        )

    heavy_wound_rolls = iter((3, 6))
    for attack_number, hit_roll in enumerate((4, 4, 2), start=1):
        attack_context_id = f"phase14l-shooting-test1:pool-004:attack-{attack_number:03d}"
        results.append(
            _fixed_roll_result(
                roll_id=f"phase14l-test1-heavy-hit-{attack_number}",
                spec=_phase14l_test1_hit_spec(
                    profile=heavy_profile,
                    attack_context_id=attack_context_id,
                ),
                value=hit_roll,
            )
        )
        if hit_roll >= 4:
            results.append(
                _fixed_roll_result(
                    roll_id=f"phase14l-test1-heavy-wound-{attack_number}",
                    spec=_phase14l_test1_wound_spec(
                        profile=heavy_profile,
                        attack_context_id=attack_context_id,
                    ),
                    value=next(heavy_wound_rolls),
                )
            )
    for attack_number, save_roll in ((1, 5), (2, 3)):
        attack_context_id = f"phase14l-shooting-test1:pool-004:attack-{attack_number:03d}"
        results.append(
            _fixed_roll_result(
                roll_id=f"phase14l-test1-heavy-save-{attack_number}",
                spec=saving_throw_roll_spec(
                    save_kind=SaveKind.INVULNERABLE,
                    player_id="player-b",
                    allocated_model_id=second_save_model_id,
                    attack_context_id=attack_context_id,
                ),
                value=save_roll,
            )
        )
    return tuple(results)


def _phase14l_test1_hit_spec(
    *,
    profile: WeaponProfile,
    attack_context_id: str,
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )


def _phase14l_test1_wound_spec(
    *,
    profile: WeaponProfile,
    attack_context_id: str,
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )


def _store_shooting_attack_sequence(
    *,
    lifecycle: GameLifecycle,
    attack_sequence: AttackSequence,
    allocated_ids: tuple[str, ...],
) -> None:
    state = _state(lifecycle)
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        state.shooting_phase_state = ShootingPhaseState(
            battle_round=state.battle_round,
            active_player_id=attack_sequence.attacker_player_id,
            selected_unit_ids=(attack_sequence.attacking_unit_instance_id,),
            shot_unit_ids=(attack_sequence.attacking_unit_instance_id,),
            attack_pools=attack_sequence.attack_pools,
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=allocated_ids,
        )
        return
    state.shooting_phase_state = shooting_state.with_attack_sequence_update(
        attack_sequence=attack_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )


def _stored_shooting_attack_sequence(lifecycle: GameLifecycle) -> AttackSequence | None:
    state = _state(lifecycle)
    out_of_phase_state = state.out_of_phase_shooting_state
    if out_of_phase_state is not None:
        return out_of_phase_state.attack_sequence
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        return None
    return shooting_state.attack_sequence


def _paused_optional_fnp_lifecycle() -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    source_a = FeelNoPainSource(source_id="phase14h-fnp-a", threshold=5)
    source_b = FeelNoPainSource(source_id="phase14h-fnp-b", threshold=6)
    state.record_model_feel_no_pain_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(source_a, source_b),
        decline_allowed=True,
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14h-fnp-round-trip",
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    sequence = AttackSequence.start(
        sequence_id="phase14h-fnp-round-trip",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=2,
            ),
        ),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=sequence.attack_pools,
        attack_sequence=sequence,
    )
    injected_results: list[DiceRollResult] = []
    for attack_number in range(1, 3):
        attack_context_id = f"phase14h-fnp-round-trip:pool-001:attack-{attack_number:03d}"
        injected_results.extend(
            (
                _fixed_roll_result(
                    roll_id=f"phase14h-fnp-hit-{attack_number}",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"phase14h-fnp-wound-{attack_number}",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
            )
        )
    for attack_number in range(1, 3):
        attack_context_id = f"phase14h-fnp-round-trip:pool-001:attack-{attack_number:03d}"
        injected_results.append(
            _fixed_roll_result(
                roll_id=f"phase14h-fnp-save-{attack_number}",
                spec=saving_throw_roll_spec(
                    save_kind=SaveKind.ARMOUR,
                    player_id="player-b",
                    allocated_model_id=defender_model.model_instance_id,
                    attack_context_id=attack_context_id,
                ),
                value=1,
            )
        )
    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14h-fnp-round-trip",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=tuple(injected_results),
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))
    assert remaining_sequence is not None
    assert remaining_sequence.pending_grouped_damage is not None
    shooting_state = state.shooting_phase_state
    assert shooting_state is not None
    state.shooting_phase_state = shooting_state.with_attack_sequence_update(
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )
    return lifecycle, request


def _submit_all_pending_fnp_declines(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
) -> None:
    current_request = request
    result_index = 1
    while True:
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"phase14h-fnp-decline-{result_index}",
                request=current_request,
                selected_option_id="decline",
            )
        )
        if status.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION:
            return
        current_request = _decision_request(status)
        if current_request.decision_type != SELECT_FEEL_NO_PAIN_DECISION_TYPE:
            return
        result_index += 1


def _precision_request_for_fixture(
    *,
    lifecycle: GameLifecycle,
    attacker: UnitInstance,
    defender: UnitInstance,
    weapon_profile: WeaponProfile,
    sequence_id: str,
) -> tuple[DecisionRequest, AttackSequence, tuple[str, ...]]:
    state = _state(lifecycle)
    sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id=f"{sequence_id}:hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id=f"{sequence_id}:wound", spec=wound_spec, value=6),
            ),
        ),
    )
    if remaining_sequence is None:
        raise AssertionError("Precision fixture unexpectedly completed.")
    return _decision_request(cast(LifecycleStatus, status)), remaining_sequence, allocated_ids


def _display_geometry(
    *,
    center_x_inches: float,
    center_y_inches: float,
    width_inches: float,
    depth_inches: float,
) -> TerrainDisplayGeometry:
    return TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=center_x_inches,
        center_y_inches=center_y_inches,
        width_inches=width_inches,
        depth_inches=depth_inches,
        display_template_id="test_axis_aligned_terrain",
    )


def _gone_to_ground_detection_context() -> tuple[
    BattlefieldScenario,
    UnitInstance,
    UnitInstance,
    WeaponProfile,
]:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    attacker = units["intercessor-1"]
    target = units["enemy"]
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=target,
        army_id="army-beta",
        player_id="player-b",
        poses=tuple(Pose.at(25.5 + (index * 1.4), 35.0) for index in range(5)),
    )
    return scenario, attacker, target, _first_weapon_profile(lifecycle, attacker)


def _dense_solid_woods() -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="phase13b-dense-solid-woods",
        feature_kind=TerrainFeatureKind.WOODS,
        footprint_center_x_inches=29.5,
        footprint_center_y_inches=35.0,
        footprint_width_inches=12.0,
        footprint_depth_inches=6.0,
        display_geometry=_display_geometry(
            center_x_inches=29.5,
            center_y_inches=35.0,
            width_inches=12.0,
            depth_inches=6.0,
        ),
    )


def _non_solid_hill_with_wall() -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="phase13b-non-solid-hill-with-wall",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=25.5,
        footprint_center_y_inches=35.0,
        footprint_width_inches=12.0,
        footprint_depth_inches=6.0,
        display_geometry=_display_geometry(
            center_x_inches=25.5,
            center_y_inches=35.0,
            width_inches=12.0,
            depth_inches=6.0,
        ),
        walls=(
            TerrainWallDefinition(
                wall_id="partial-wall",
                center_x_inches=22.0,
                center_y_inches=35.0,
                bottom_z_inches=0.0,
                width_inches=0.2,
                depth_inches=1.0,
                height_inches=4.0,
            ),
        ),
    )


def _blocking_ruin() -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="phase13b-blocking-ruin",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=20.0,
        footprint_center_y_inches=35.0,
        footprint_width_inches=4.0,
        footprint_depth_inches=4.0,
        display_geometry=_display_geometry(
            center_x_inches=20.0,
            center_y_inches=35.0,
            width_inches=4.0,
            depth_inches=4.0,
        ),
        walls=(
            TerrainWallDefinition(
                wall_id="wall",
                center_x_inches=20.0,
                center_y_inches=35.0,
                bottom_z_inches=0.0,
                width_inches=0.2,
                depth_inches=4.0,
                height_inches=4.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground-floor",
                center_x_inches=20.0,
                center_y_inches=35.0,
                bottom_z_inches=0.0,
                width_inches=4.0,
                depth_inches=4.0,
                thickness_inches=0.1,
            ),
        ),
    )


def _unit_placement_at(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
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
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )


def _first_weapon_profile(lifecycle: GameLifecycle, unit: UnitInstance) -> WeaponProfile:
    _state(lifecycle)
    wargear_id = unit.wargear_selections[0].wargear_ids[0]
    return _weapon_profile_by_wargear(
        wargear_id=wargear_id,
        weapon_profile_id=None,
    )


def _weapon_profile_by_wargear(
    *,
    wargear_id: str,
    weapon_profile_id: str | None,
) -> WeaponProfile:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    for wargear in catalog.wargear:
        if wargear.wargear_id == wargear_id:
            if weapon_profile_id is None:
                return wargear.weapon_profiles[0]
            for profile in wargear.weapon_profiles:
                if profile.profile_id == weapon_profile_id:
                    return profile
    raise AssertionError(f"Missing wargear {wargear_id}.")


def _advanced_unit_state(unit_instance_id: str, *, can_shoot: bool) -> AdvancedUnitState:
    request = AdvanceRollRequest.for_unit(
        request_id=f"{unit_instance_id}:advance-roll",
        game_id="phase13b-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
    )
    roll_state = DiceRollManager("phase13b-advanced-state").roll_fixed(request.spec, [3])
    return AdvancedUnitState(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=unit_instance_id,
        movement_dice_record=MovementDiceRecord(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=AdvanceRollResult.from_roll_state(
                request=request,
                roll_state=roll_state,
            ),
        ),
        can_shoot=can_shoot,
    )


def _scenario_with_unit_pose(
    *,
    scenario: BattlefieldScenario,
    unit: UnitInstance,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
) -> BattlefieldScenario:
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.with_unit_placement(
            _unit_placement_at(unit, army_id=army_id, player_id=player_id, poses=poses)
        ),
    )


def _scenario_with_replaced_unit(
    *,
    scenario: BattlefieldScenario,
    replacement: UnitInstance,
) -> BattlefieldScenario:
    updated_armies: list[ArmyDefinition] = []
    for army in scenario.armies:
        updated_armies.append(
            replace(
                army,
                units=tuple(
                    replacement if unit.unit_instance_id == replacement.unit_instance_id else unit
                    for unit in army.units
                ),
            )
        )
    return BattlefieldScenario(
        armies=tuple(updated_armies),
        battlefield_state=scenario.battlefield_state,
    )


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, object]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, object], event.payload)
    raise AssertionError(f"Missing event type {event_type}.")


def _event_payloads(lifecycle: GameLifecycle, event_type: str) -> tuple[dict[str, object], ...]:
    return tuple(
        cast(dict[str, object], event.payload)
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == event_type
    )


def _dice_rolled_payloads_for_spec(
    lifecycle: GameLifecycle,
    spec_payload: dict[str, object],
) -> tuple[dict[str, object], ...]:
    return tuple(
        payload
        for payload in _event_payloads(lifecycle, "dice_rolled")
        if cast(dict[str, object], payload["spec"]) == spec_payload
    )


def _attack_step_payload(
    events: tuple[dict[str, object], ...],
    step: AttackSequenceStep,
) -> dict[str, object]:
    for event in events:
        if event["step"] == step.value:
            return event
    raise AssertionError(f"Missing attack sequence step {step.value}.")


shooting_lifecycle = _shooting_lifecycle
catalog_with_replaced_bolt_profiles = _catalog_with_replaced_bolt_profiles
proposal_from_request = _proposal_from_request
weapon_profile_by_wargear = _weapon_profile_by_wargear
