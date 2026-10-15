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
    create_deterministic_battlefield_scenario,
    enter_battle_for_fixture,
    muster_army,
    replace,
    request_stratagem_use_from_index,
)
from tests.shared.category_migration.ws14_generic_ir_lifecycle_shared_lifecycle import (
    _apply_battle_formation_hooks_from_bundle,
    _grant_cp,
    _mission_setup,
    _option_stratagem_id,
    _option_target_unit_id,
    _prepare_battle_phase,
    _record_fixed_secondary_choices_for_fixture,
    _runtime_content_bundle,
    _state,
)


def _spectacle_lifecycle_config() -> GameConfig:
    catalog = _spectacle_catalog()
    return GameConfig(
        game_id="ws14-spectacle-of-slaughter-generic-ir-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        army_muster_requests=(
            _spectacle_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                unit_selection_ids=("blades-1", "blades-2"),
                enhancement_assignments=(
                    ("000010900002", "blades-1"),
                    ("000010900003", "blades-2"),
                ),
            ),
            _spectacle_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                unit_selection_ids=("blades-3",),
                enhancement_assignments=(),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
        mission_setup=_mission_setup(),
    )


def _spectacle_battle_lifecycle() -> GameLifecycle:
    config = _spectacle_lifecycle_config()
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="ws14-spectacle-battlefield",
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


def _spectacle_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-boyz-like-infantry")
    flawless_blades_datasheet = replace(
        base_datasheet,
        datasheet_id="ws14-emperors-children-flawless-blades",
        name="WS14 Emperor's Children Flawless Blades",
        keywords=DatasheetKeywordSet(
            keywords=("Character", "Infantry"),
            faction_keywords=("Emperor's Children", "Flawless Blades"),
        ),
        source_ids=("datasheet:ws14-emperors-children-flawless-blades",),
    )
    core_weapons = tuple(
        wargear
        for wargear in base_catalog.wargear
        if wargear.wargear_id in {"core-leader-blade", "core-mob-shoota"}
    )
    return ArmyCatalog(
        catalog_id="ws14-spectacle-of-slaughter-demo",
        ruleset_id=base_catalog.ruleset_id,
        source_package_id="data-package:core-v2:ws14-spectacle-of-slaughter-demo:0.1.0",
        datasheets=(flawless_blades_datasheet,),
        wargear=core_weapons,
        factions=(
            FactionDefinition(
                faction_id="emperors-children",
                name="Emperor's Children",
                faction_keywords=("Emperor's Children",),
                source_ids=("faction:emperors-children",),
            ),
        ),
        detachments=(
            DetachmentDefinition(
                canonical_detachment_id="spectacle-of-slaughter",
                detachment_id="spectacle-of-slaughter",
                name="Spectacle of Slaughter",
                faction_id="emperors-children",
                detachment_point_cost=1,
                unit_datasheet_ids=("ws14-emperors-children-flawless-blades",),
                force_disposition_ids=("purge-the-foe", "take-and-hold"),
                rule_source_ids=("phase17e:emperors-children:spectacle-of-slaughter:rule",),
                enhancement_ids=("000010900002", "000010900003"),
                stratagem_ids=("000010901002", "000010901003", "000010901004"),
                source_ids=("detachment:spectacle-of-slaughter",),
            ),
        ),
        enhancements=(
            EnhancementDefinition(
                enhancement_id="000010900002",
                name="Beguiling Grotesquerie Upgrade",
                source_id=(
                    "phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900002"
                ),
                points=15,
            ),
            EnhancementDefinition(
                enhancement_id="000010900003",
                name="Eager Patrons Upgrade",
                source_id=(
                    "phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900003"
                ),
                points=20,
            ),
        ),
        stratagems=(
            _spectacle_stratagem("000010901002", "Honour Is For Fools"),
            _spectacle_stratagem("000010901003", "Single-Minded Strike"),
            _spectacle_stratagem("000010901004", "Intoxicated By Triumph"),
        ),
        source_ids=("catalog:ws14-spectacle-of-slaughter-demo",),
    )


def _spectacle_stratagem(stratagem_id: str, name: str) -> StratagemDefinition:
    return StratagemDefinition(
        stratagem_id=stratagem_id,
        name=name,
        source_id=f"phase17e:stratagem:emperors-children:spectacle-of-slaughter:{stratagem_id}",
        command_point_cost=1,
        timing_tags=("fight", "charge", "movement"),
    )


def _spectacle_muster_request(
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
            detachment_ids=("spectacle-of-slaughter",),
            enhancement_ids=("000010900002", "000010900003"),
        ),
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="ws14-emperors-children-flawless-blades",
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
                source_id=(
                    f"ws14-spectacle:assignment:{target_unit_selection_id}:{enhancement_id}"
                ),
            )
            for enhancement_id, target_unit_selection_id in enhancement_assignments
        ),
        roster_legality_required=False,
    )


def _use_spectacle_stratagem(
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
    result = _spectacle_stratagem_decision_result(
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


def _use_spectacle_stratagem_through_lifecycle(
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
    result = _spectacle_stratagem_decision_result(
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


def _spectacle_stratagem_decision_result(
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
        result_id=f"ws14-spectacle-{stratagem_id}-result",
        request=request,
        selected_option_id=selected_option.option_id,
    )


def _leader_blade_profile() -> WeaponProfile:
    return next(
        wargear
        for wargear in _spectacle_catalog().wargear
        if wargear.wargear_id == "core-leader-blade"
    ).weapon_profiles[0]


def _spectacle_weapon_profile_context(
    *,
    state: GameState,
    weapon_profile: WeaponProfile,
    attacker_model_id: str,
    source_phase: BattlePhase,
    attacking_unit_id: str = "army-alpha:blades-1",
    target_unit_id: str = "army-beta:blades-3",
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=state,
        source_phase=source_phase,
        attacking_unit_instance_id=attacking_unit_id,
        attacker_model_instance_id=attacker_model_id,
        target_unit_instance_id=target_unit_id,
        weapon_profile=weapon_profile,
    )


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "BattlePhase", "DatasheetKeywordSet"]
__all__ += ["DecisionResult", "DetachmentDefinition", "DetachmentSelection"]
__all__ += ["EnhancementAssignment", "EnhancementDefinition", "FactionDefinition", "GameConfig"]
__all__ += ["GameLifecycle", "GameState", "JsonValue", "LifecycleStatus", "LifecycleStatusKind"]
__all__ += ["ModelProfileSelection", "ReactionQueue", "RulesetDescriptor", "StratagemDefinition"]
__all__ += ["StratagemEligibilityContext", "StratagemUseRecord", "TimingTriggerKind"]
__all__ += ["UnitMusterSelection", "WeaponProfile", "WeaponProfileModifierContext"]
__all__ += ["_apply_battle_formation_hooks_from_bundle", "_grant_cp", "_leader_blade_profile"]
__all__ += ["_mission_setup", "_option_stratagem_id", "_option_target_unit_id"]
__all__ += ["_prepare_battle_phase", "_record_fixed_secondary_choices_for_fixture"]
__all__ += ["_runtime_content_bundle", "_spectacle_battle_lifecycle", "_spectacle_catalog"]
__all__ += ["_spectacle_lifecycle_config", "_spectacle_muster_request", "_spectacle_stratagem"]
__all__ += ["_spectacle_stratagem_decision_result", "_spectacle_weapon_profile_context", "_state"]
__all__ += ["_use_spectacle_stratagem", "_use_spectacle_stratagem_through_lifecycle"]
__all__ += ["apply_stratagem_decision", "create_deterministic_battlefield_scenario"]
__all__ += ["enter_battle_for_fixture", "muster_army", "replace"]
__all__ += ["request_stratagem_use_from_index"]
