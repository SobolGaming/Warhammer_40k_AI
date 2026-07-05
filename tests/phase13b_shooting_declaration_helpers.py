from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
)
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import (
    WeaponProfile,
    WeaponProfilePayload,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import (
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.shooting_types import (
    ShootingType,
)
from warhammer40k_core.engine.transports import (
    FiringDeckSelection,
    FiringDeckWeaponSelection,
    TransportCapacityProfile,
    TransportCargoState,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_declaration import (
    ShootingDeclarationProposal,
    WeaponDeclaration,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def shooting_lifecycle(
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
    config = shooting_config(
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
    armies = mustered_armies(config)
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
            poses = compact_test_unit_poses(
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
            poses = compact_test_unit_poses(
                origin=Pose.at(10.0, friendly_y),
                model_count=len(unit.own_models),
            )
        battlefield = battlefield.with_unit_placement(
            unit_placement_at(unit, army_id=army_id, player_id=player_id, poses=poses)
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


def compact_test_unit_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
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


def catalog_with_replaced_bolt_profiles(
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


def shooting_config(
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
            alpha_unit_spec(
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
        ruleset_descriptor=ruleset(),
        army_catalog=resolved_catalog,
        army_muster_requests=(
            army_muster_request(
                catalog=resolved_catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_specs=resolved_alpha_unit_specs,
                attachment_declarations=alpha_attachment_declarations,
            ),
            army_muster_request(
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
        mission_setup=mission_setup(),
    )


def alpha_unit_spec(
    *,
    unit_id: str,
    alpha_datasheets: dict[str, tuple[str, str, int]] | None,
) -> tuple[str, str, str, int]:
    if alpha_datasheets is not None and unit_id in alpha_datasheets:
        datasheet_id, model_profile_id, model_count = alpha_datasheets[unit_id]
        return (unit_id, datasheet_id, model_profile_id, model_count)
    return (unit_id, "core-intercessor-like-infantry", "core-intercessor-like", 5)


def mission_setup() -> MissionSetup:
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


def mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def army_muster_request(
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


def proposal_from_request(
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
            shooting_type=first_shooting_type(target_candidate),
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
                shooting_type=first_shooting_type(target_candidate),
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


def first_shooting_type(target_candidate: dict[str, object]) -> ShootingType:
    shooting_types = cast(list[str], target_candidate["shooting_types"])
    if not shooting_types:
        raise AssertionError("Target candidate has no shooting types.")
    return ShootingType(shooting_types[0])


def ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase13b-test")


def unit_placement_at(
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


def weapon_profile_by_wargear(
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
