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
    WeaponProfileModifierContext,
    apply_stratagem_decision,
    court_ir,
    create_deterministic_battlefield_scenario,
    emperors_children_july,
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


def _court_lifecycle_config() -> GameConfig:
    catalog = emperors_children_july.current_army_catalog(_court_catalog())
    return GameConfig(
        game_id="ws14-court-of-the-phoenician-generic-ir-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            _court_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                unit_selection_ids=(
                    "fulgrim-1",
                    "daemon-prince-1",
                    "lord-exultant-1",
                    "tears-1",
                    "soulstain-1",
                ),
                enhancement_assignments=(
                    ("000010654002", "tears-1"),
                    ("000010654003", "lord-exultant-1"),
                    ("000010654004", "soulstain-1"),
                    ("000010654005", "daemon-prince-1"),
                ),
            ),
            _court_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                unit_selection_ids=("enemy-character-1",),
                enhancement_assignments=(),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
        mission_setup=_mission_setup(),
    )


def _court_battle_lifecycle() -> GameLifecycle:
    config = _court_lifecycle_config()
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="ws14-court-battlefield",
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


def _court_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-boyz-like-infantry")
    core_weapons = tuple(
        wargear
        for wargear in base_catalog.wargear
        if wargear.wargear_id in {"core-leader-blade", "core-mob-shoota"}
    )
    return ArmyCatalog(
        catalog_id="ws14-court-of-the-phoenician-demo",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="data-package:core-v2:ws14-court-of-the-phoenician-demo:0.1.0",
        datasheets=(
            replace(
                base_datasheet,
                datasheet_id="ws14-court-fulgrim",
                name="WS14 Fulgrim",
                keywords=DatasheetKeywordSet(
                    keywords=(
                        court_ir.FULGRIM_KEYWORD,
                        court_ir.DAEMON_KEYWORD,
                        court_ir.CHARACTER_KEYWORD,
                        "MONSTER",
                    ),
                    faction_keywords=(court_ir.EMPERORS_CHILDREN_KEYWORD,),
                ),
                source_ids=("datasheet:ws14-court-fulgrim",),
            ),
            replace(
                base_datasheet,
                datasheet_id="ws14-court-daemon-prince",
                name="WS14 Emperor's Children Daemon Prince",
                keywords=DatasheetKeywordSet(
                    keywords=(
                        court_ir.DAEMON_PRINCE_KEYWORD,
                        court_ir.DAEMON_KEYWORD,
                        court_ir.CHARACTER_KEYWORD,
                        "MONSTER",
                    ),
                    faction_keywords=(court_ir.EMPERORS_CHILDREN_KEYWORD,),
                ),
                source_ids=("datasheet:ws14-court-daemon-prince",),
            ),
            replace(
                base_datasheet,
                datasheet_id="ws14-court-lord-exultant",
                name="WS14 Lord Exultant",
                keywords=DatasheetKeywordSet(
                    keywords=(court_ir.LORD_EXULTANT_KEYWORD, court_ir.CHARACTER_KEYWORD),
                    faction_keywords=(court_ir.EMPERORS_CHILDREN_KEYWORD,),
                ),
                source_ids=("datasheet:ws14-court-lord-exultant",),
            ),
            replace(
                base_datasheet,
                datasheet_id="ws14-court-infantry",
                name="WS14 Emperor's Children Infantry",
                keywords=DatasheetKeywordSet(
                    keywords=("INFANTRY",),
                    faction_keywords=(court_ir.EMPERORS_CHILDREN_KEYWORD,),
                ),
                source_ids=("datasheet:ws14-court-infantry",),
            ),
            replace(
                base_datasheet,
                datasheet_id="ws14-court-enemy-character",
                name="WS14 Enemy Character",
                keywords=DatasheetKeywordSet(
                    keywords=(court_ir.CHARACTER_KEYWORD, "INFANTRY"),
                    faction_keywords=("ENEMY", court_ir.EMPERORS_CHILDREN_KEYWORD),
                ),
                source_ids=("datasheet:ws14-court-enemy-character",),
            ),
        ),
        wargear=core_weapons,
        factions=(
            FactionDefinition(
                faction_id="emperors-children",
                name="Emperor's Children",
                faction_keywords=(court_ir.EMPERORS_CHILDREN_KEYWORD,),
                source_ids=("faction:emperors-children",),
            ),
            FactionDefinition(
                faction_id="ws14-opponent",
                name="WS14 Opponent",
                faction_keywords=("ENEMY",),
                source_ids=("faction:ws14-opponent",),
            ),
        ),
        detachments=(
            DetachmentDefinition(
                canonical_detachment_id="court-of-the-phoenician",
                detachment_id="court-of-the-phoenician",
                name="Court of the Phoenician",
                faction_id="emperors-children",
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    "ws14-court-fulgrim",
                    "ws14-court-daemon-prince",
                    "ws14-court-lord-exultant",
                    "ws14-court-infantry",
                    "ws14-court-enemy-character",
                ),
                force_disposition_ids=("purge-the-foe", "take-and-hold"),
                rule_source_ids=("phase17e:emperors-children:court-of-the-phoenician:rule",),
                enhancement_ids=(
                    "000010654002",
                    "000010654003",
                    "000010654004",
                    "000010654005",
                ),
                stratagem_ids=(
                    "000010655002",
                    "000010655003",
                    "000010655004",
                    "000010655005",
                    "000010655006",
                    "000010655007",
                ),
                source_ids=("detachment:court-of-the-phoenician",),
            ),
        ),
        enhancements=(
            EnhancementDefinition(
                enhancement_id="000010654002",
                name="Tears of the Phoenix",
                source_id=(
                    "phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654002"
                ),
                points=15,
            ),
            EnhancementDefinition(
                enhancement_id="000010654003",
                name="Exalted Patron",
                source_id=(
                    "phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654003"
                ),
                points=20,
            ),
            EnhancementDefinition(
                enhancement_id="000010654004",
                name="Soulstain Made Manifest",
                source_id=(
                    "phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654004"
                ),
                points=20,
            ),
            EnhancementDefinition(
                enhancement_id="000010654005",
                name="Spiritsliver",
                source_id=(
                    "phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654005"
                ),
                points=25,
            ),
        ),
        stratagems=(
            _court_stratagem("000010655002", "Contemptuous Disregard"),
            _court_stratagem("000010655003", "Prideful Superiority"),
            _court_stratagem("000010655004", "Sinuous Breach"),
            _court_stratagem("000010655005", "Close-Quarters Excruciation"),
            _court_stratagem("000010655006", "Euphoric Inspiration"),
            _court_stratagem("000010655007", "Catalytic Stimulus"),
        ),
        source_ids=("catalog:ws14-court-of-the-phoenician-demo",),
    )


def _court_stratagem(stratagem_id: str, name: str) -> StratagemDefinition:
    return StratagemDefinition(
        stratagem_id=stratagem_id,
        name=name,
        source_id=f"phase17e:stratagem:emperors-children:court-of-the-phoenician:{stratagem_id}",
        command_point_cost=1,
        timing_tags=("shooting", "fight", "movement", "charge"),
    )


def _court_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    unit_selection_ids: tuple[str, ...],
    enhancement_assignments: tuple[tuple[str, str], ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="emperors-children",
            detachment_ids=("court-of-the-phoenician",),
            enhancement_ids=(
                "000010654002",
                "000010654003",
                "000010654004",
                "000010654005",
            ),
        ),
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id=_court_datasheet_id_for_selection(unit_selection_id),
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-boyz-like",
                        model_count=10,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
        enhancement_assignments=tuple(
            EnhancementAssignment(
                model_profile_id="core-boyz-like",
                model_index=1,
                enhancement_id=enhancement_id,
                target_unit_selection_id=target_unit_selection_id,
                source_id=f"ws14-court:assignment:{target_unit_selection_id}:{enhancement_id}",
            )
            for enhancement_id, target_unit_selection_id in enhancement_assignments
        ),
        roster_legality_required=False,
    )


def _court_datasheet_id_for_selection(unit_selection_id: str) -> str:
    if unit_selection_id == "fulgrim-1":
        return "ws14-court-fulgrim"
    if unit_selection_id == "daemon-prince-1":
        return "ws14-court-daemon-prince"
    if unit_selection_id == "lord-exultant-1":
        return "ws14-court-lord-exultant"
    if unit_selection_id in {"tears-1", "soulstain-1"}:
        return "ws14-court-infantry"
    if unit_selection_id == "enemy-character-1":
        return "ws14-court-enemy-character"
    raise AssertionError(f"Missing Court datasheet mapping for {unit_selection_id}.")


def _use_court_stratagem(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int = 1,
    active_player_id: str = "player-a",
    trigger_kind: TimingTriggerKind = TimingTriggerKind.DURING_PHASE,
    trigger_payload: JsonValue = None,
) -> StratagemUseRecord:
    state = _state(lifecycle)
    result = _court_stratagem_decision_result(
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


def _use_court_stratagem_through_lifecycle(
    lifecycle: GameLifecycle,
    *,
    stratagem_id: str,
    target_unit_id: str,
    phase: BattlePhase,
    command_points: int = 1,
    active_player_id: str = "player-a",
    trigger_kind: TimingTriggerKind = TimingTriggerKind.DURING_PHASE,
    trigger_payload: JsonValue = None,
) -> tuple[StratagemUseRecord, LifecycleStatus]:
    state = _state(lifecycle)
    result = _court_stratagem_decision_result(
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


def _court_stratagem_decision_result(
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
    if command_points > 0:
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
        stratagem_cost_modifier_registry=(
            _runtime_content_bundle(lifecycle).stratagem_cost_modifier_registry
        ),
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
        result_id=f"ws14-court-{stratagem_id}-result",
        request=request,
        selected_option_id=selected_option.option_id,
    )


def _court_blade_profile() -> WeaponProfile:
    return next(
        wargear for wargear in _court_catalog().wargear if wargear.wargear_id == "core-leader-blade"
    ).weapon_profiles[0]


def _court_shoota_profile() -> WeaponProfile:
    return next(
        wargear for wargear in _court_catalog().wargear if wargear.wargear_id == "core-mob-shoota"
    ).weapon_profiles[0]


def _court_weapon_profile_context(
    *,
    state: GameState,
    weapon_profile: WeaponProfile,
    attacker_model_id: str,
    attacking_unit_id: str,
    target_unit_id: str,
    source_phase: BattlePhase,
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=state,
        source_phase=source_phase,
        attacking_unit_instance_id=attacking_unit_id,
        attacker_model_instance_id=attacker_model_id,
        target_unit_instance_id=target_unit_id,
        weapon_profile=weapon_profile,
    )


def _place_units_for_court_within_12(state: GameState) -> None:
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:fulgrim-1",
        poses=tuple(
            Pose.at(x=10.0 + (index % 5) * 1.5, y=10.0 + (index // 5) * 1.5) for index in range(10)
        ),
    )
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-character-1",
        poses=tuple(
            Pose.at(x=16.0 + (index % 5) * 1.5, y=10.0 + (index // 5) * 1.5) for index in range(10)
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
__all__ += ["WeaponProfileModifierContext", "_apply_battle_formation_hooks_from_bundle"]
__all__ += ["_clear_terrain", "_court_battle_lifecycle", "_court_blade_profile", "_court_catalog"]
__all__ += ["_court_datasheet_id_for_selection", "_court_lifecycle_config"]
__all__ += ["_court_muster_request", "_court_shoota_profile", "_court_stratagem"]
__all__ += ["_court_stratagem_decision_result", "_court_weapon_profile_context", "_grant_cp"]
__all__ += ["_mission_setup", "_option_stratagem_id", "_option_target_unit_id"]
__all__ += ["_place_units_for_court_within_12", "_prepare_battle_phase"]
__all__ += ["_record_fixed_secondary_choices_for_fixture", "_replace_unit_poses"]
__all__ += ["_runtime_content_bundle", "_state", "_use_court_stratagem"]
__all__ += ["_use_court_stratagem_through_lifecycle", "apply_stratagem_decision", "court_ir"]
__all__ += ["create_deterministic_battlefield_scenario", "emperors_children_july"]
__all__ += ["enter_battle_for_fixture", "muster_army", "replace"]
__all__ += ["request_stratagem_use_from_index"]
