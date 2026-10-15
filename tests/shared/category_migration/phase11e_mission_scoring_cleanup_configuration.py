from __future__ import annotations

from tests.shared.category_migration.phase11e_mission_scoring_cleanup_bindings import (
    SCORING_TERRAIN_FEATURE_ID,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    AttachmentDeclaration,
    BattlePhase,
    DecisionController,
    DetachmentSelection,
    GameConfig,
    GameLifecycleStage,
    GameState,
    MissionSetup,
    ModelProfileSelection,
    PlayerPrimaryMissionAssignment,
    ReserveKind,
    ReserveState,
    RulesetDescriptor,
    SecondaryMissionMode,
    UnitMusterSelection,
    chapter_approved_2026_27_mission_pack,
    create_deterministic_battlefield_scenario,
    enter_battle_for_fixture,
    mission_scoring_policies_from_setup,
    muster_army,
    replace,
    reserve_destruction_policy_from_scoring_policy,
    warhammer_event_companion_2026_07_mission_pack,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_state_primitives import (
    _place_unit_near_point,
    _record_active_tactical_secondary,
    _secondary_choice,
)


def _battle_state(
    *,
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_b_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_a_fixed_mission_ids: tuple[str, str] = ("assassination", "bring-it-down"),
    mission_setup: MissionSetup | None = None,
    decisions: DecisionController | None = None,
) -> GameState:
    config = _config(mission_setup=mission_setup)
    return _battle_state_from_config(
        config,
        player_a_secondary=player_a_secondary,
        player_b_secondary=player_b_secondary,
        player_a_fixed_mission_ids=player_a_fixed_mission_ids,
        decisions=decisions,
    )


def _battle_state_for_primary(primary_mission_id: str) -> GameState:
    return _battle_state_from_config(_config_for_primary(primary_mission_id))


def _battle_state_from_config(
    config: GameConfig,
    *,
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_b_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_a_fixed_mission_ids: tuple[str, str] = ("assassination", "bring-it-down"),
    turn_start_unit_positions: tuple[tuple[str, float, float], ...] = (),
    turn_start_unplaced_unit_ids: tuple[str, ...] = (),
    decisions: DecisionController | None = None,
) -> GameState:
    state = GameState.from_config(config)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    assert config.mission_setup is not None
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11e-battlefield",
        armies=tuple(state.army_definitions),
        battlefield_width_inches=config.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=config.mission_setup.battlefield_depth_inches,
        terrain_features=config.mission_setup.terrain_features,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    for unit_instance_id, x_inches, y_inches in turn_start_unit_positions:
        _place_unit_near_point(
            state,
            unit_instance_id=unit_instance_id,
            x_inches=x_inches,
            y_inches=y_inches,
        )
    for unit_instance_id in turn_start_unplaced_unit_ids:
        assert state.battlefield_state is not None
        state.replace_battlefield_state(
            state.battlefield_state.without_unit_placement(unit_instance_id)
        )
        owner = next(
            army.player_id
            for army in state.army_definitions
            if any(unit.unit_instance_id == unit_instance_id for unit in army.units)
        )
        state.record_reserve_state(
            ReserveState.declared_before_battle(
                player_id=owner,
                unit_instance_id=unit_instance_id,
                reserve_kind=ReserveKind.STRATEGIC_RESERVES,
                destruction_deadline_policy=reserve_destruction_policy_from_scoring_policy(
                    mission_scoring_policies_from_setup(config.mission_setup).policy_for_player(
                        owner
                    )
                ),
            )
        )
    seed_tactical_mission_ids: tuple[str, ...] = ()
    if player_a_secondary is SecondaryMissionMode.FIXED and "cleanse" in player_a_fixed_mission_ids:
        player_a_secondary = SecondaryMissionMode.TACTICAL
        seed_tactical_mission_ids = player_a_fixed_mission_ids
    state.record_secondary_mission_choice(
        _secondary_choice(
            player_id="player-a",
            mode=player_a_secondary,
            fixed_mission_ids=player_a_fixed_mission_ids,
        )
    )
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-b", mode=player_b_secondary)
    )
    enter_battle_for_fixture(state, decisions=decisions)
    for mission_id in seed_tactical_mission_ids:
        _record_active_tactical_secondary(state, secondary_mission_id=mission_id)
    assert state.stage is GameLifecycleStage.BATTLE
    assert state.current_battle_phase is BattlePhase.COMMAND
    return state


def _config(*, mission_setup: MissionSetup | None = None) -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    resolved_mission_setup = _mission_setup() if mission_setup is None else mission_setup
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-a"
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-b"
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=resolved_mission_setup,
    )


def _config_for_primary(
    primary_mission_id: str,
    *,
    objective_terrain_feature_id: str | None = None,
) -> GameConfig:
    return _config(
        mission_setup=_mission_setup_for_primary(
            primary_mission_id,
            objective_terrain_feature_id=objective_terrain_feature_id,
        ),
    )


def _config_with_player_a_vehicle() -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
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
                        unit_selection_id="intercessor-unit-1",
                        datasheet_id="core-intercessor-like-infantry",
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                    _unit_muster_selection(
                        unit_selection_id="vehicle-unit-2",
                        datasheet_id="core-vehicle-monster",
                        model_profile_id="core-vehicle-monster",
                        model_count=1,
                    ),
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _config_with_two_player_a_infantry_units() -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1", "intercessor-unit-2"),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _config_with_player_a_attached_unit(
    *,
    include_independent_unit: bool = False,
    mission_setup: MissionSetup | None = None,
) -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    resolved_mission_setup = _mission_setup() if mission_setup is None else mission_setup
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-a"
                ),
                unit_selections=(
                    _unit_muster_selection(
                        unit_selection_id="bodyguard-unit",
                        datasheet_id="core-intercessor-like-infantry",
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                    _unit_muster_selection(
                        unit_selection_id="leader-unit",
                        datasheet_id="core-character-leader",
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                    *(
                        (
                            _unit_muster_selection(
                                unit_selection_id="intercessor-unit-2",
                                datasheet_id="core-intercessor-like-infantry",
                                model_profile_id="core-intercessor-like",
                                model_count=5,
                            ),
                        )
                        if include_independent_unit
                        else ()
                    ),
                ),
                attachment_declarations=(
                    AttachmentDeclaration(
                        source_unit_selection_id="leader-unit",
                        bodyguard_unit_selection_id="bodyguard-unit",
                    ),
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-b"
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=resolved_mission_setup,
    )


def _config_with_player_a_transport() -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
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
                        unit_selection_id="intercessor-unit-1",
                        datasheet_id="core-intercessor-like-infantry",
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                    _unit_muster_selection(
                        unit_selection_id="transport-unit-2",
                        datasheet_id="core-transport",
                        model_profile_id="core-transport",
                        model_count=1,
                    ),
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _config_with_player_b_character(*, mission_setup: MissionSetup) -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
                force_disposition_id=mission_setup.force_disposition_id_for_player("player-a"),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id=mission_setup.force_disposition_id_for_player("player-b"),
                unit_selections=(
                    _unit_muster_selection(
                        unit_selection_id="character-unit-3",
                        datasheet_id="core-character-leader",
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=mission_setup,
    )


def _config_with_player_b_vehicles(
    vehicle_unit_ids: tuple[str, ...],
    *,
    mission_setup: MissionSetup | None = None,
) -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    resolved_mission_setup = _mission_setup() if mission_setup is None else mission_setup
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-a"
                ),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-b"
                ),
                unit_selections=tuple(
                    _unit_muster_selection(
                        unit_selection_id=unit_id,
                        datasheet_id="core-vehicle-monster",
                        model_profile_id="core-vehicle-monster",
                        model_count=1,
                    )
                    for unit_id in vehicle_unit_ids
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=resolved_mission_setup,
    )


def _config_with_player_b_horde_units(unit_ids: tuple[str, ...]) -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="take-and-hold",
                unit_selections=tuple(
                    _unit_muster_selection(
                        unit_selection_id=unit_id,
                        datasheet_id="core-boyz-like-infantry",
                        model_profile_id="core-boyz-like",
                        model_count=13,
                    )
                    for unit_id in unit_ids
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="take-and-hold",
    )


def _event_companion_mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="take-and-hold",
    )


def _event_companion_meatgrinder_mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        terrain_layout_id="purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _event_companion_purge_and_secure_mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-reconnaissance-layout-1",
        terrain_layout_id="take-and-hold-vs-reconnaissance-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="reconnaissance",
    )


def _event_companion_death_trap_mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-disruption-layout-1",
        terrain_layout_id="take-and-hold-vs-disruption-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="disruption",
        defender_player_id="player-b",
        defender_force_disposition_id="take-and-hold",
    )


def _chapter_approved_immovable_object_mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _mission_setup_for_primary(
    primary_mission_id: str,
    *,
    objective_terrain_feature_id: str | None = None,
) -> MissionSetup:
    if primary_mission_id == "primary-death-trap":
        return _event_companion_death_trap_mission_setup()
    if objective_terrain_feature_id is not None:
        raise AssertionError("Only Death Trap accepts a terrain target fixture.")
    if primary_mission_id == "primary-immovable-object":
        return _chapter_approved_immovable_object_mission_setup()
    if primary_mission_id == "primary-meatgrinder":
        return _event_companion_meatgrinder_mission_setup()
    if primary_mission_id == "primary-unstoppable-force":
        return _mission_setup()
    raise AssertionError("Primary mission fixture requires an engine-implemented mission.")


def _event_companion_mission_setup_with_scoring_terrain_feature(
    *,
    feature_id: str = SCORING_TERRAIN_FEATURE_ID,
) -> MissionSetup:
    del feature_id
    return _event_companion_mission_setup()


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="core-v2-phase11e-test"
    )


def _catalog_with_directional_force_dispositions() -> ArmyCatalog:
    source_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return replace(
        source_catalog,
        detachments=tuple(
            replace(
                detachment,
                force_disposition_ids=(
                    "disruption",
                    "purge-the-foe",
                    "reconnaissance",
                    "take-and-hold",
                ),
            )
            if detachment.detachment_id == "core-combined-arms"
            else detachment
            for detachment in source_catalog.detachments
        ),
    )


def _with_player_primary_mission(
    mission_setup: MissionSetup,
    *,
    player_id: str,
    primary_mission_id: str,
) -> MissionSetup:
    return replace(
        mission_setup,
        primary_mission_assignments=tuple(
            (
                PlayerPrimaryMissionAssignment(
                    player_id=assignment.player_id,
                    force_disposition_id=assignment.force_disposition_id,
                    primary_mission_id=primary_mission_id,
                )
                if assignment.player_id == player_id
                else assignment
            )
            for assignment in mission_setup.primary_mission_assignments
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
    force_disposition_id: str | None = None,
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
        force_disposition_id=(
            ("purge-the-foe" if player_id == "player-a" else "take-and-hold")
            if force_disposition_id is None
            else force_disposition_id
        ),
        unit_selections=tuple(
            _unit_muster_selection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_id="core-intercessor-like",
                model_count=5,
            )
            for unit_selection_id in unit_selection_ids
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


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest", "AttachmentDeclaration"]
__all__ += ["BattlePhase", "DecisionController", "DetachmentSelection", "GameConfig"]
__all__ += ["GameLifecycleStage", "GameState", "MissionSetup", "ModelProfileSelection"]
__all__ += ["PlayerPrimaryMissionAssignment", "ReserveKind", "ReserveState", "RulesetDescriptor"]
__all__ += ["SCORING_TERRAIN_FEATURE_ID", "SecondaryMissionMode", "UnitMusterSelection"]
__all__ += ["_army_muster_request", "_battle_state", "_battle_state_for_primary"]
__all__ += ["_battle_state_from_config", "_catalog_with_directional_force_dispositions"]
__all__ += ["_chapter_approved_immovable_object_mission_setup", "_config", "_config_for_primary"]
__all__ += ["_config_with_player_a_attached_unit", "_config_with_player_a_transport"]
__all__ += ["_config_with_player_a_vehicle", "_config_with_player_b_character"]
__all__ += ["_config_with_player_b_horde_units", "_config_with_player_b_vehicles"]
__all__ += ["_config_with_two_player_a_infantry_units"]
__all__ += ["_event_companion_death_trap_mission_setup"]
__all__ += ["_event_companion_meatgrinder_mission_setup", "_event_companion_mission_setup"]
__all__ += ["_event_companion_mission_setup_with_scoring_terrain_feature"]
__all__ += ["_event_companion_purge_and_secure_mission_setup", "_mission_setup"]
__all__ += ["_mission_setup_for_primary", "_mustered_armies", "_place_unit_near_point"]
__all__ += ["_record_active_tactical_secondary", "_ruleset", "_secondary_choice"]
__all__ += ["_unit_muster_selection", "_with_player_primary_mission"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_deterministic_battlefield_scenario"]
__all__ += ["enter_battle_for_fixture", "mission_scoring_policies_from_setup", "muster_army"]
__all__ += ["replace", "reserve_destruction_policy_from_scoring_policy"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack"]
