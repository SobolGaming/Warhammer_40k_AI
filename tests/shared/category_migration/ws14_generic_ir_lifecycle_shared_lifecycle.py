from __future__ import annotations

from tests.shared.category_migration.ws14_generic_ir_lifecycle_bindings import (
    CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    AbilityKind,
    BattleFormationRequestContext,
    BattlePhase,
    BattlePhaseKind,
    CommandPointGainStatus,
    CommandPointSourceKind,
    EffectExpiration,
    FightPhaseState,
    FightsFirstRegistry,
    GameConfig,
    GameLifecycle,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    JsonValue,
    MissionSetup,
    PersistingEffect,
    Pose,
    RulesetDescriptor,
    RuntimeContentBundle,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    SetupStep,
    ShootingPhaseState,
    WeaponProfile,
    WeaponProfileModifierContext,
    chapter_approved_2026_27_mission_pack,
    replace,
)


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    bundle = object.__getattribute__(lifecycle, "_runtime_content_bundle")
    if type(bundle) is not RuntimeContentBundle:
        raise AssertionError("Runtime content bundle was not rebuilt.")
    return bundle


def _apply_battle_formation_hooks_from_bundle(lifecycle: GameLifecycle) -> None:
    state = _state(lifecycle)
    config = object.__getattribute__(lifecycle, "_config")
    if type(config) is not GameConfig:
        raise AssertionError("Lifecycle config was not loaded.")
    original_stage = state.stage
    original_setup_step_index = state.setup_step_index
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = state.setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS)
    try:
        request = _runtime_content_bundle(
            lifecycle
        ).battle_formation_hook_registry.next_request_for(
            BattleFormationRequestContext(
                state=state,
                decisions=lifecycle.decision_controller,
                config=config,
            )
        )
    finally:
        state.stage = original_stage
        state.setup_step_index = original_setup_step_index
    assert request is None


def _state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    assert state is not None
    return state


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _prepare_battle_phase(
    state: GameState,
    *,
    phase: BattlePhase,
    active_player_id: str,
) -> None:
    state.command_step_state = None
    state.movement_phase_state = None
    state.shooting_phase_state = None
    state.charge_phase_state = None
    state.fight_phase_state = None
    _set_current_battle_phase(state, phase)
    state.active_player_id = active_player_id
    if phase is BattlePhase.SHOOTING:
        state.shooting_phase_state = ShootingPhaseState(
            battle_round=state.battle_round,
            active_player_id=active_player_id,
        )
    if phase is BattlePhase.FIGHT:
        state.fight_phase_state = FightPhaseState.start(
            battle_round=state.battle_round,
            active_player_id=active_player_id,
            policy=RulesetDescriptor.warhammer_40000_eleventh().fight_policy,
            engaged_at_fight_step_start_unit_ids=(),
            fights_first_registry=FightsFirstRegistry.from_state(state),
        )


def _grant_cp(state: GameState, *, player_id: str, amount: int) -> None:
    result = state.gain_command_points(
        player_id=player_id,
        amount=amount,
        source_id=f"ws14-more-dakka-grant:{player_id}:{amount}",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    assert result.status is CommandPointGainStatus.APPLIED


def _record_fixed_secondary_choices_for_fixture(
    state: GameState,
    *,
    config: GameConfig,
) -> None:
    for player_id in config.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=config.fixed_secondary_mission_ids,
            )
        )


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Expected a JSON object.")
    return value


def _option_stratagem_id(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Stratagem option payload must be an object.")
    catalog_record = payload.get("catalog_record")
    if not isinstance(catalog_record, dict):
        raise GameLifecycleError("Stratagem option payload is missing catalog_record.")
    definition = catalog_record.get("definition")
    if not isinstance(definition, dict):
        raise GameLifecycleError("Stratagem option payload is missing definition.")
    stratagem_id = definition.get("stratagem_id")
    if stratagem_id is None:
        return None
    if type(stratagem_id) is not str:
        raise GameLifecycleError("Stratagem option stratagem_id must be a string.")
    return stratagem_id


def _option_target_unit_id(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Stratagem option payload must be an object.")
    target_binding = payload.get("target_binding")
    if not isinstance(target_binding, dict):
        raise GameLifecycleError("Stratagem option payload is missing target_binding.")
    target_unit_id = target_binding.get("target_unit_instance_id")
    if target_unit_id is None:
        return None
    if type(target_unit_id) is not str:
        raise GameLifecycleError("Stratagem option target_unit_instance_id must be a string.")
    return target_unit_id


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            return _json_object(event.payload)
    raise AssertionError(f"Missing event type: {event_type}")


def _weapon_profile_context(
    *,
    state: GameState,
    weapon_profile: WeaponProfile,
    attacker_model_id: str,
    attacking_unit_id: str = "army-alpha:boyz-1",
    target_unit_id: str = "army-beta:boyz-2",
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=attacking_unit_id,
        attacker_model_instance_id=attacker_model_id,
        target_unit_instance_id=target_unit_id,
        weapon_profile=weapon_profile,
    )


def _profile_has_ability(profile: WeaponProfile, ability_kind: AbilityKind) -> bool:
    return any(ability.ability_kind is ability_kind for ability in profile.abilities)


def _first_model_id(state: GameState, *, unit_instance_id: str) -> str:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit.own_models[0].model_instance_id
    raise AssertionError(f"Missing unit: {unit_instance_id}")


def _record_charge_move_effect(state: GameState, *, unit_instance_id: str) -> None:
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"ws14-court:charge-move:{unit_instance_id}:{state.battle_round}",
            source_rule_id="core-rules:charge-move",
            owner_player_id="player-a",
            target_unit_instance_ids=(unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.CHARGE,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id="player-a",
            ),
            effect_payload={"effect_kind": CHARGE_FIGHTS_FIRST_EFFECT_KIND},
        )
    )


def _replace_unit_poses(
    state: GameState,
    *,
    unit_instance_id: str,
    poses: tuple[Pose, ...],
) -> None:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    assert len(placement.model_placements) == len(poses)
    state.replace_battlefield_state(
        battlefield_state.with_unit_placement(
            placement.with_model_placements(
                tuple(
                    model_placement.with_pose(pose)
                    for model_placement, pose in zip(placement.model_placements, poses, strict=True)
                )
            )
        )
    )


def _clear_terrain(state: GameState) -> None:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    state.battlefield_state = replace(battlefield_state, terrain_features=())


def _effect_parameter(effect_payload: dict[str, JsonValue], key: str) -> JsonValue:
    parameters = effect_payload.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Expected RuleIR effect parameters.")
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise GameLifecycleError("Expected RuleIR effect parameter object.")
        if parameter.get("key") == key:
            return parameter.get("value")
    return None


__all__: list[str] = []
__all__ += ["AbilityKind", "BattleFormationRequestContext", "BattlePhase", "BattlePhaseKind"]
__all__ += ["CHARGE_FIGHTS_FIRST_EFFECT_KIND", "CommandPointGainStatus", "CommandPointSourceKind"]
__all__ += ["EffectExpiration", "FightPhaseState", "FightsFirstRegistry", "GameConfig"]
__all__ += ["GameLifecycle", "GameLifecycleError", "GameLifecycleStage", "GameState", "JsonValue"]
__all__ += ["MissionSetup", "PersistingEffect", "Pose", "RulesetDescriptor"]
__all__ += ["RuntimeContentBundle", "SecondaryMissionChoice", "SecondaryMissionMode", "SetupStep"]
__all__ += ["ShootingPhaseState", "WeaponProfile", "WeaponProfileModifierContext"]
__all__ += ["_apply_battle_formation_hooks_from_bundle", "_clear_terrain", "_effect_parameter"]
__all__ += ["_first_model_id", "_grant_cp", "_json_object", "_last_event_payload"]
__all__ += ["_mission_setup", "_option_stratagem_id", "_option_target_unit_id"]
__all__ += ["_prepare_battle_phase", "_profile_has_ability", "_record_charge_move_effect"]
__all__ += ["_record_fixed_secondary_choices_for_fixture", "_replace_unit_poses"]
__all__ += ["_runtime_content_bundle", "_set_current_battle_phase", "_state"]
__all__ += ["_weapon_profile_context", "chapter_approved_2026_27_mission_pack", "replace"]
