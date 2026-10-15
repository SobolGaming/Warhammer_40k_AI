from __future__ import annotations

from tests.shared.category_migration.ws14_generic_ir_lifecycle_bindings import (
    ArmyCatalog,
    ArmyMusterRequest,
    BattlePhase,
    DatasheetKeywordSet,
    DecisionResult,
    DetachmentDefinition,
    DetachmentSelection,
    EnhancementAssignment,
    EnhancementDefinition,
    FactionDefinition,
    GameConfig,
    GameLifecycle,
    GameState,
    JsonValue,
    LifecycleStatus,
    LifecycleStatusKind,
    ModelProfileSelection,
    Pose,
    ReactionQueue,
    RulesetDescriptor,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemUseRecord,
    TimingTriggerKind,
    UnitMusterSelection,
    WeaponProfile,
    apply_stratagem_decision,
    create_deterministic_battlefield_scenario,
    enter_battle_for_fixture,
    muster_army,
    replace,
    request_stratagem_use_from_index,
)
from tests.shared.category_migration.ws14_generic_ir_lifecycle_shared_lifecycle import (
    _apply_battle_formation_hooks_from_bundle,
    _clear_terrain,
    _grant_cp,
    _mission_setup,
    _option_stratagem_id,
    _option_target_unit_id,
    _prepare_battle_phase,
    _record_fixed_secondary_choices_for_fixture,
    _replace_unit_poses,
    _runtime_content_bundle,
    _state,
)


def _more_dakka_lifecycle_config() -> GameConfig:
    catalog = _more_dakka_catalog()
    return GameConfig(
        game_id="ws14-more-dakka-generic-ir-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            _more_dakka_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                unit_selection_id="boyz-1",
                walker_unit_selection_id="walker-1",
            ),
            _more_dakka_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                unit_selection_id="boyz-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
        mission_setup=_mission_setup(),
    )


def _more_dakka_battle_lifecycle() -> GameLifecycle:
    config = _more_dakka_lifecycle_config()
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="ws14-more-dakka-battlefield",
        armies=armies,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    _record_fixed_secondary_choices_for_fixture(state, config=config)
    decisions = enter_battle_for_fixture(state)
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )
    _apply_battle_formation_hooks_from_bundle(lifecycle)
    return lifecycle


def _more_dakka_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-boyz-like-infantry")
    boyz_datasheet = replace(
        base_datasheet,
        datasheet_id="ws14-orks-boyz",
        name="WS14 Orks Boyz",
        keywords=DatasheetKeywordSet(
            keywords=("Character", "Infantry"),
            faction_keywords=("Orks",),
        ),
        source_ids=("datasheet:ws14-orks-boyz",),
    )
    walker_datasheet = replace(
        base_datasheet,
        datasheet_id="ws14-orks-walker",
        name="WS14 Orks Walker",
        keywords=DatasheetKeywordSet(
            keywords=("Vehicle", "Walker"),
            faction_keywords=("Orks",),
        ),
        source_ids=("datasheet:ws14-orks-walker",),
    )
    mob_shoota = next(
        wargear for wargear in base_catalog.wargear if wargear.wargear_id == "core-mob-shoota"
    )
    return ArmyCatalog(
        catalog_id="ws14-more-dakka-demo",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="data-package:core-v2:ws14-more-dakka-demo:0.1.0",
        datasheets=(boyz_datasheet, walker_datasheet),
        wargear=(mob_shoota,),
        factions=(
            FactionDefinition(
                faction_id="orks",
                name="Orks",
                faction_keywords=("Orks",),
                source_ids=("faction:orks",),
            ),
        ),
        detachments=(
            DetachmentDefinition(
                canonical_detachment_id="more-dakka",
                detachment_id="more-dakka",
                name="More Dakka",
                faction_id="orks",
                detachment_point_cost=1,
                unit_datasheet_ids=("ws14-orks-boyz", "ws14-orks-walker"),
                force_disposition_ids=("purge-the-foe", "take-and-hold"),
                rule_source_ids=("phase17e:orks:more-dakka:rule",),
                enhancement_ids=(
                    "000009991002",
                    "000009991003",
                    "000009991004",
                    "000009991005",
                ),
                stratagem_ids=(
                    "000009992002",
                    "000009992003",
                    "000009992004",
                    "000009992005",
                    "000009992006",
                    "000009992007",
                ),
                source_ids=("detachment:more-dakka",),
            ),
        ),
        enhancements=(
            EnhancementDefinition(
                enhancement_id="000009991002",
                name="Da Gobshot Thunderbuss",
                source_id="phase17e:enhancement:orks:more-dakka:000009991002",
                points=15,
            ),
            EnhancementDefinition(
                enhancement_id="000009991003",
                name="Dead Shiny Shootas",
                source_id="phase17e:enhancement:orks:more-dakka:000009991003",
                points=35,
            ),
            EnhancementDefinition(
                enhancement_id="000009991004",
                name="Targetin Squigs",
                source_id="phase17e:enhancement:orks:more-dakka:000009991004",
                points=15,
            ),
            EnhancementDefinition(
                enhancement_id="000009991005",
                name="Zog Off and Eat Dakka",
                source_id="phase17e:enhancement:orks:more-dakka:000009991005",
                points=10,
            ),
        ),
        stratagems=(
            _more_dakka_stratagem("000009992002", "Orks Is Still Orks", 1),
            _more_dakka_stratagem("000009992003", "Get Stuck In Ladz", 2),
            _more_dakka_stratagem("000009992004", "Huge Show Offs", 1),
            _more_dakka_stratagem("000009992005", "Long Uncontrolled Bursts", 1),
            _more_dakka_stratagem("000009992006", "Speshul Shells", 1),
            _more_dakka_stratagem("000009992007", "Call Dat Dakka", 1),
        ),
        source_ids=("catalog:ws14-more-dakka-demo",),
    )


def _more_dakka_stratagem(
    stratagem_id: str,
    name: str,
    command_point_cost: int,
) -> StratagemDefinition:
    return StratagemDefinition(
        stratagem_id=stratagem_id,
        name=name,
        source_id=f"phase17e:stratagem:orks:more-dakka:{stratagem_id}",
        command_point_cost=command_point_cost,
        timing_tags=("shooting",),
    )


def _more_dakka_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    unit_selection_id: str,
    walker_unit_selection_id: str | None = None,
) -> ArmyMusterRequest:
    unit_selections = [
        UnitMusterSelection(
            unit_selection_id=unit_selection_id,
            datasheet_id="ws14-orks-boyz",
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="core-boyz-like",
                    model_count=10,
                ),
            ),
        )
    ]
    if walker_unit_selection_id is not None:
        unit_selections.append(
            UnitMusterSelection(
                unit_selection_id=walker_unit_selection_id,
                datasheet_id="ws14-orks-walker",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-boyz-like",
                        model_count=10,
                    ),
                ),
            )
        )
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="orks",
            detachment_ids=("more-dakka",),
            enhancement_ids=("000009991003", "000009991004", "000009991005"),
        ),
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
        unit_selections=tuple(unit_selections),
        enhancement_assignments=(
            EnhancementAssignment(
                model_profile_id="core-boyz-like",
                model_index=1,
                enhancement_id="000009991004",
                target_unit_selection_id=unit_selection_id,
                source_id=(f"ws14-more-dakka:assignment:{unit_selection_id}:000009991004"),
            ),
        ),
        roster_legality_required=False,
    )


def _use_more_dakka_stratagem(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int = 1,
    active_player_id: str = "player-a",
    trigger_kind: TimingTriggerKind = TimingTriggerKind.START_PHASE,
    trigger_payload: JsonValue = None,
) -> StratagemUseRecord:
    state = _state(lifecycle)
    result = _more_dakka_stratagem_decision_result(
        lifecycle,
        stratagem_id=stratagem_id,
        target_unit_id=target_unit_id,
        phase=phase,
        command_points=command_points,
        active_player_id=active_player_id,
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )
    lifecycle.decision_controller.submit_result(result)
    config = object.__getattribute__(lifecycle, "_config")
    if type(config) is not GameConfig:
        raise AssertionError("Lifecycle config was not loaded.")
    use_record = apply_stratagem_decision(
        state=state,
        result=result,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        stratagem_handler_registry=(_runtime_content_bundle(lifecycle).stratagem_handler_registry),
        stratagem_cost_modifier_registry=(
            _runtime_content_bundle(lifecycle).stratagem_cost_modifier_registry
        ),
        shooting_unit_selected_grant_hooks=(
            _runtime_content_bundle(lifecycle).shooting_unit_selected_grant_hook_registry
        ),
    )
    assert state.stratagem_use_records[-1] == use_record
    return use_record


def _use_more_dakka_stratagem_through_lifecycle(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int = 1,
    active_player_id: str = "player-a",
    trigger_kind: TimingTriggerKind = TimingTriggerKind.START_PHASE,
    trigger_payload: JsonValue = None,
) -> tuple[StratagemUseRecord, LifecycleStatus]:
    state = _state(lifecycle)
    result = _more_dakka_stratagem_decision_result(
        lifecycle,
        stratagem_id=stratagem_id,
        target_unit_id=target_unit_id,
        phase=phase,
        command_points=command_points,
        active_player_id=active_player_id,
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )
    status = lifecycle.submit_decision(result)
    use_record = state.stratagem_use_records[-1]
    assert use_record.stratagem_id == stratagem_id
    assert use_record.targeted_unit_instance_ids == (target_unit_id,)
    return use_record, status


def _more_dakka_stratagem_decision_result(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int,
    active_player_id: str,
    trigger_kind: TimingTriggerKind,
    trigger_payload: JsonValue,
) -> DecisionResult:
    state = _state(lifecycle)
    _prepare_battle_phase(state, phase=phase, active_player_id=active_player_id)
    _grant_cp(state, player_id="player-a", amount=command_points)
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-a",
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )
    status = request_stratagem_use_from_index(
        state=state,
        decisions=lifecycle.decision_controller,
        index=_runtime_content_bundle(lifecycle).stratagem_indexes_by_player_id["player-a"],
        context=context,
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = lifecycle.pending_decision_request()
    assert request is not None
    selected_option = next(
        option
        for option in request.options
        if _option_stratagem_id(option.payload) == stratagem_id
        and _option_target_unit_id(option.payload) == target_unit_id
    )
    return DecisionResult.for_request(
        result_id=f"ws14-more-dakka-{stratagem_id}-result",
        request=request,
        selected_option_id=selected_option.option_id,
    )


def _mob_shoota_profile() -> WeaponProfile:
    return next(
        wargear
        for wargear in _more_dakka_catalog().wargear
        if wargear.wargear_id == "core-mob-shoota"
    ).weapon_profiles[0]


def _place_units_for_more_dakka_shooting(state: GameState) -> None:
    # The target must not be engaged with the fixture's unrelated friendly Walker.
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:walker-1",
        poses=tuple(
            Pose.at(x=20.0 + (index % 5) * 1.5, y=30.0 + (index // 5) * 1.5) for index in range(10)
        ),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:boyz-1",
        poses=tuple(
            Pose.at(x=(index % 5) * 1.5, y=10.0 + (index // 5) * 1.5) for index in range(10)
        ),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:boyz-2",
        poses=tuple(
            Pose.at(x=10.0 + (index % 5) * 1.5, y=10.0 + (index // 5) * 1.5) for index in range(10)
        ),
    )
    _clear_terrain(state)


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "BattlePhase", "DatasheetKeywordSet"]
__all__ += ["DecisionResult", "DetachmentDefinition", "DetachmentSelection"]
__all__ += ["EnhancementAssignment", "EnhancementDefinition", "FactionDefinition", "GameConfig"]
__all__ += ["GameLifecycle", "GameState", "JsonValue", "LifecycleStatus", "LifecycleStatusKind"]
__all__ += ["ModelProfileSelection", "Pose", "ReactionQueue", "RulesetDescriptor"]
__all__ += ["StratagemDefinition", "StratagemEligibilityContext", "StratagemUseRecord"]
__all__ += ["TimingTriggerKind", "UnitMusterSelection", "WeaponProfile"]
__all__ += ["_apply_battle_formation_hooks_from_bundle", "_clear_terrain", "_grant_cp"]
__all__ += ["_mission_setup", "_mob_shoota_profile", "_more_dakka_battle_lifecycle"]
__all__ += ["_more_dakka_catalog", "_more_dakka_lifecycle_config", "_more_dakka_muster_request"]
__all__ += ["_more_dakka_stratagem", "_more_dakka_stratagem_decision_result"]
__all__ += ["_option_stratagem_id", "_option_target_unit_id"]
__all__ += ["_place_units_for_more_dakka_shooting", "_prepare_battle_phase"]
__all__ += ["_record_fixed_secondary_choices_for_fixture", "_replace_unit_poses"]
__all__ += ["_runtime_content_bundle", "_state", "_use_more_dakka_stratagem"]
__all__ += ["_use_more_dakka_stratagem_through_lifecycle", "apply_stratagem_decision"]
__all__ += ["create_deterministic_battlefield_scenario", "enter_battle_for_fixture"]
__all__ += ["muster_army", "replace", "request_stratagem_use_from_index"]
