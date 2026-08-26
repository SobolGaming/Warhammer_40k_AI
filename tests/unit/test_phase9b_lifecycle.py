from __future__ import annotations

import inspect
import json
from dataclasses import replace
from typing import cast

import pytest
from tests.deployment_submission_helpers import submit_all_deployments_if_pending
from tests.model_geometry_helpers import accepted_model_geometry
from tests.phase17n_secondary_mission_helpers import drain_pending_secondary_mission_setup
from tests.setup_completion_helpers import ensure_army_mustered_events_for_fixture

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.model_geometry_catalog import (
    ModelGeometryCatalogRecord,
    ModelGeometryCatalogRecordPayload,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    BattlePhaseSequenceDescriptor,
    RulesetDescriptor,
    SetupSequenceDescriptor,
    SetupStepKind,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.charge_declaration import (
    ChargeRollRequest,
    ChargeRollResult,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.game_state import (
    DEFAULT_MAX_LIFECYCLE_TRANSITIONS,
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.game_state_payloads import GameConfigPayload
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    PlaceholderPhaseHandler,
    SetupStep,
    game_lifecycle_stage_from_token,
    lifecycle_status_kind_from_token,
)
from warhammer40k_core.engine.phases.charge import (
    ChargePhaseState,
    ChargingUnitSelection,
)
from warhammer40k_core.engine.phases.command import (
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    CommandPhaseHandler,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseState,
)
from warhammer40k_core.engine.phases.shooting import ShootingPhaseState
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    STRATAGEM_DECISION_TYPE,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.geometry.model_geometry import GeometrySourceKind, HeightSourceKind
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def _config(
    *,
    ruleset_descriptor: RulesetDescriptor | None = None,
    army_catalog: ArmyCatalog | None = None,
    army_muster_requests: tuple[ArmyMusterRequest, ...] | None = None,
    max_lifecycle_transitions: int = DEFAULT_MAX_LIFECYCLE_TRANSITIONS,
    model_geometries: tuple[ModelGeometryCatalogRecord, ...] | None = None,
) -> GameConfig:
    descriptor = ruleset_descriptor
    if descriptor is None:
        descriptor = RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase9b-test"
        )
    catalog = ArmyCatalog.phase9a_canonical_content_pack() if army_catalog is None else army_catalog
    return GameConfig(
        game_id="phase9b-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=descriptor,
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_requests(catalog) if army_muster_requests is None else army_muster_requests
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
        ),
        max_lifecycle_transitions=max_lifecycle_transitions,
        mission_setup=_mission_setup(),
        model_geometries=model_geometries,
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


def _army_muster_requests(catalog: ArmyCatalog) -> tuple[ArmyMusterRequest, ...]:
    return (
        _army_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selection_id="intercessor-unit-1",
        ),
        _army_muster_request(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            unit_selection_id="intercessor-unit-2",
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
    wargear_selections: tuple[WargearSelection, ...] = (),
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
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
                wargear_selections=wargear_selections,
            ),
        ),
    )


def _descriptor_with_sequences(
    *,
    setup_steps: tuple[SetupStepKind, ...] | None = None,
    battle_phases: tuple[BattlePhaseKind, ...] | None = None,
) -> RulesetDescriptor:
    base = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase9b-sequence-test"
    )
    return RulesetDescriptor(
        ruleset_id=base.ruleset_id,
        source_date=base.source_date,
        descriptor_version=base.descriptor_version,
        engagement_policy=base.engagement_policy,
        movement_policy=base.movement_policy,
        charge_policy=base.charge_policy,
        fight_policy=base.fight_policy,
        terrain_movement_policy=base.terrain_movement_policy,
        terrain_visibility_policy=base.terrain_visibility_policy,
        objective_policy=base.objective_policy,
        coherency_policy=base.coherency_policy,
        fly_policy=base.fly_policy,
        mission_policy=base.mission_policy,
        setup_sequence=SetupSequenceDescriptor(
            steps=setup_steps
            if setup_steps is not None
            else SetupSequenceDescriptor.warhammer_40000_eleventh_default().steps
        ),
        battle_phase_sequence=BattlePhaseSequenceDescriptor(
            phases=battle_phases
            if battle_phases is not None
            else BattlePhaseSequenceDescriptor.warhammer_40000_eleventh_default().phases
        ),
    )


def _start_lifecycle(config: GameConfig | None = None) -> GameLifecycle:
    lifecycle = GameLifecycle()
    lifecycle.start(_config() if config is None else config)
    return lifecycle


def _state(lifecycle: GameLifecycle) -> GameStatePayload:
    payload = lifecycle.to_payload()
    return payload["state"]


def _pending_request(lifecycle: GameLifecycle) -> DecisionRequest:
    return lifecycle.decision_controller.queue.peek_next()


def _request_payload(request: DecisionRequest) -> dict[str, JsonValue]:
    assert isinstance(request.payload, dict)
    return request.payload


def _public_secondary_choices(payload: dict[str, JsonValue]) -> list[JsonValue]:
    choices = payload["secondary_mission_choices"]
    assert isinstance(choices, list)
    return choices


def _state_battle_phase(state: GameState) -> BattlePhaseKind | None:
    return state.current_battle_phase


def _submit_pending(
    lifecycle: GameLifecycle,
    *,
    option_id: str,
    result_number: int,
) -> LifecycleStatus:
    request = _pending_request(lifecycle)
    result = DecisionResult.for_request(
        result_id=f"decision-result-{result_number:06d}",
        request=request,
        selected_option_id=option_id,
    )
    return lifecycle.submit_decision(result)


def _decline_stratagem_window_if_pending(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_number: int,
) -> LifecycleStatus:
    current = drain_pending_secondary_mission_setup(
        lifecycle,
        status,
        result_id_prefix=f"decision-result-{result_number:06d}-secondary-setup",
    )
    request = current.decision_request
    if request is None or request.decision_type != STRATAGEM_DECISION_TYPE:
        return current
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=f"decision-result-{result_number:06d}",
            request=request,
            selected_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        )
    )


def _advance_to_secondary_mission_step(lifecycle: GameLifecycle) -> None:
    while lifecycle.state is not None and (
        lifecycle.state.current_setup_step is not SetupStep.SELECT_SECONDARY_MISSIONS
    ):
        lifecycle.advance_until_decision_or_terminal()


def _choose_secondaries(
    lifecycle: GameLifecycle,
    *,
    player_a_option: str = "tactical",
    player_b_option: str = "fixed:assassination:bring_it_down",
) -> None:
    _advance_to_secondary_mission_step(lifecycle)
    status = lifecycle.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.actor_id == "player-a"
    assert status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    _submit_pending(lifecycle, option_id=player_a_option, result_number=1)

    status = lifecycle.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.actor_id == "player-b"
    assert status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    _submit_pending(lifecycle, option_id=player_b_option, result_number=2)


def _advance_to_battle(lifecycle: GameLifecycle) -> None:
    _choose_secondaries(lifecycle)
    status = lifecycle.advance_until_decision_or_terminal()
    while lifecycle.state is not None and lifecycle.state.stage is not GameLifecycleStage.BATTLE:
        status = submit_all_deployments_if_pending(
            lifecycle,
            status,
            result_id_prefix="phase9b-deploy",
        )
        if _lifecycle_is_in_battle(lifecycle):
            return
        status = lifecycle.advance_until_decision_or_terminal()


def _lifecycle_is_in_battle(lifecycle: GameLifecycle) -> bool:
    return lifecycle.state is not None and lifecycle.state.stage is GameLifecycleStage.BATTLE


def _battle_flow() -> BattleRoundFlow:
    return BattleRoundFlow(
        phase_handlers={
            BattlePhase.COMMAND: CommandPhaseHandler(),
            BattlePhase.MOVEMENT: PlaceholderPhaseHandler(BattlePhase.MOVEMENT),
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
            BattlePhase.CHARGE: PlaceholderPhaseHandler(BattlePhase.CHARGE),
            BattlePhase.FIGHT: PlaceholderPhaseHandler(BattlePhase.FIGHT),
        }
    )


def _battle_state(
    config: GameConfig | None = None,
    *,
    decisions: DecisionController | None = None,
) -> GameState:
    resolved_config = _config() if config is None else config
    state = GameState.from_config(resolved_config)
    for request in resolved_config.army_muster_requests:
        state.record_army_definition(
            muster_army(catalog=resolved_config.army_catalog, request=request)
        )
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id="phase9b-battlefield",
            armies=tuple(state.army_definitions),
        ).battlefield_state
    )
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    resolved_decisions = DecisionController() if decisions is None else decisions
    _complete_setup_through_gate(
        state=state,
        decisions=resolved_decisions,
        config=resolved_config,
    )
    return state


def _battle_lifecycle_for_consistency() -> GameLifecycle:
    config = _config()
    decisions = DecisionController()
    state = _battle_state(config, decisions=decisions)
    return GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": {"frames": []},
            },
        )
    )


def _phase_state_consistency_payload(
    *,
    phase: BattlePhase,
) -> tuple[GameLifecyclePayload, str, str]:
    lifecycle = _battle_lifecycle_for_consistency()
    state = lifecycle.state
    assert state is not None
    alpha_unit_id = state.army_definitions[0].units[0].unit_instance_id
    beta_unit_id = state.army_definitions[1].units[0].unit_instance_id
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    state.replace_command_step_state(None)
    state.replace_movement_phase_state(None)
    state.replace_shooting_phase_state(None)
    state.replace_charge_phase_state(None)
    state.replace_fight_phase_state(None)
    if phase is BattlePhase.MOVEMENT:
        state.replace_movement_phase_state(
            MovementPhaseState(
                battle_round=state.battle_round,
                active_player_id="player-a",
                selected_unit_ids=(alpha_unit_id,),
            )
        )
    elif phase is BattlePhase.SHOOTING:
        state.replace_shooting_phase_state(
            ShootingPhaseState(
                battle_round=state.battle_round,
                active_player_id="player-a",
                selected_unit_ids=(alpha_unit_id,),
            )
        )
    elif phase is BattlePhase.CHARGE:
        selection = ChargingUnitSelection(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=alpha_unit_id,
            request_id="phase9b-charge-selection-request",
            result_id="phase9b-charge-selection-result",
        )
        roll_request = ChargeRollRequest(
            request_id="phase9b-charge-roll-request",
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id="player-a",
            unit_instance_id=alpha_unit_id,
            source_decision_request_id=selection.request_id,
            source_decision_result_id=selection.result_id,
        )
        roll_state = DiceRollManager("phase9b-charge-consistency").roll_fixed(
            roll_request.spec,
            [3, 4],
        )
        roll_result = ChargeRollResult.from_roll_state(
            request=roll_request,
            roll_state=roll_state,
            reachable_target_distances_inches={beta_unit_id: 3.0},
        )
        state.replace_charge_phase_state(
            ChargePhaseState(
                battle_round=state.battle_round,
                active_player_id="player-a",
            )
            .with_unit_selection(selection)
            .with_charge_roll_result(roll_result)
        )
    elif phase is BattlePhase.FIGHT:
        state.replace_fight_phase_state(
            FightPhaseState.start(
                battle_round=state.battle_round,
                active_player_id="player-a",
                policy=lifecycle.config.ruleset_descriptor.fight_policy,
                engaged_at_fight_step_start_unit_ids=(alpha_unit_id, beta_unit_id),
                fights_first_registry=FightsFirstRegistry(),
            )
        )
    else:
        raise AssertionError("Phase consistency fixture requires a non-Command battle phase.")
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(payload).to_payload() == payload
    return payload, alpha_unit_id, beta_unit_id


def _complete_setup_through_gate(
    *,
    state: GameState,
    decisions: DecisionController,
    config: GameConfig,
) -> None:
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    SetupCompletionGate().complete_setup_and_enter_battle(
        state=state,
        decisions=decisions,
        config=config,
    )


def test_game_state_replace_army_definitions_sorts_and_validates() -> None:
    config = _config()
    state = GameState.from_config(config)
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )

    state.replace_army_definitions([armies[1], armies[0]])

    assert [army.player_id for army in state.army_definitions] == ["player-a", "player-b"]
    with pytest.raises(GameLifecycleError, match="ArmyDefinition values"):
        state.replace_army_definitions(cast(list[ArmyDefinition], [object()]))


def test_game_state_phase_state_mutators_clear_validated_state_fields() -> None:
    state = GameState.from_config(_config())

    state.replace_command_step_state(None)
    state.replace_movement_phase_state(None)
    state.replace_shooting_phase_state(None)
    state.replace_out_of_phase_shooting_state(None)
    state.replace_charge_phase_state(None)
    state.replace_fight_phase_state(None)

    assert state.command_step_state is None
    assert state.movement_phase_state is None
    assert state.shooting_phase_state is None
    assert state.out_of_phase_shooting_state is None
    assert state.charge_phase_state is None
    assert state.fight_phase_state is None


def test_new_game_starts_at_muster_armies_and_records_descriptor_hash() -> None:
    config = _config()
    lifecycle = GameLifecycle()
    status = lifecycle.start(config)

    assert status.status_kind is LifecycleStatusKind.ADVANCED
    assert lifecycle.state is not None
    assert lifecycle.state.stage is GameLifecycleStage.SETUP
    assert lifecycle.state.current_setup_step is SetupStep.MUSTER_ARMIES
    assert lifecycle.state.ruleset_descriptor_hash == config.ruleset_descriptor.descriptor_hash
    assert _state(lifecycle)["ruleset_descriptor_hash"] == config.ruleset_descriptor.descriptor_hash


def test_setup_steps_advance_in_ruleset_descriptor_order() -> None:
    lifecycle = _start_lifecycle()
    assert lifecycle.state is not None
    status = lifecycle.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    _submit_pending(lifecycle, option_id="tactical", result_number=1)
    status = _submit_pending(
        lifecycle,
        option_id="fixed:assassination:bring_it_down",
        result_number=2,
    )
    submit_all_deployments_if_pending(
        lifecycle,
        status,
        result_id_prefix="phase9b-setup-order-deploy",
    )

    observed_steps = [
        event.payload["step"]
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "setup_step_completed" and isinstance(event.payload, dict)
    ]

    assert observed_steps == [
        step.value for step in RulesetDescriptor.warhammer_40000_eleventh().setup_sequence.steps
    ]


def test_lifecycle_muster_armies_consumes_requests_and_records_runtime_armies() -> None:
    lifecycle = _start_lifecycle()

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.state is not None
    assert lifecycle.state.current_setup_step is SetupStep.SELECT_SECONDARY_MISSIONS
    assert lifecycle.state.missing_army_player_ids() == ()
    assert tuple(army.player_id for army in lifecycle.state.army_definitions) == (
        "player-a",
        "player-b",
    )
    assert tuple(army.army_id for army in lifecycle.state.army_definitions) == (
        "army-alpha",
        "army-beta",
    )
    assert [
        event.payload["player_id"]
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "army_mustered" and isinstance(event.payload, dict)
    ] == ["player-a", "player-b"]


def test_game_config_model_geometries_round_trip_only_when_present() -> None:
    config_without_reviewed_geometry = _config()
    payload_without_reviewed_geometry = config_without_reviewed_geometry.to_payload()

    assert "model_geometries" not in payload_without_reviewed_geometry
    assert GameConfig.from_payload(payload_without_reviewed_geometry).model_geometries is None

    geometry = accepted_model_geometry()
    config_with_reviewed_geometry = _config(model_geometries=(geometry,))
    payload_with_reviewed_geometry = config_with_reviewed_geometry.to_payload()

    assert payload_with_reviewed_geometry.get("model_geometries") == [geometry.to_payload()]
    assert GameConfig.from_payload(payload_with_reviewed_geometry).to_payload() == (
        payload_with_reviewed_geometry
    )


def test_lifecycle_mustering_uses_game_config_reviewed_model_geometry() -> None:
    geometry = accepted_model_geometry()
    lifecycle = _start_lifecycle(_config(model_geometries=(geometry,)))

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.state is not None
    for army in lifecycle.state.army_definitions:
        model_geometry = army.units[0].own_models[0].geometry
        assert model_geometry.geometry_source_kind is GeometrySourceKind.CATALOG_GEOMETRY_RECORD
        assert model_geometry.height_source_kind is HeightSourceKind.CATALOG_GEOMETRY_RECORD
        assert model_geometry.height_inches == 1.55
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)
    assert restored.config.model_geometries == (geometry,)
    assert restored.to_payload() == lifecycle.to_payload()


def test_lifecycle_mustering_preserves_partial_reviewed_model_geometry() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    reviewed_geometry = accepted_model_geometry()
    player_a_request = _army_muster_request(
        catalog=catalog,
        player_id="player-a",
        army_id="army-alpha",
        unit_selection_id="intercessor-unit-1",
    )
    player_b_request = replace(
        _army_muster_request(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            unit_selection_id="boyz-unit-1",
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="boyz-unit-1",
                datasheet_id="core-boyz-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-boyz-like",
                        model_count=10,
                    ),
                ),
                wargear_selections=(),
            ),
        ),
    )
    config = _config(
        army_catalog=catalog,
        army_muster_requests=(player_a_request, player_b_request),
        model_geometries=(reviewed_geometry,),
    )
    lifecycle = _start_lifecycle(config)

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.state is not None
    armies_by_player_id = {army.player_id: army for army in lifecycle.state.army_definitions}
    accepted_model = armies_by_player_id["player-a"].units[0].own_models[0]
    unresolved_model = armies_by_player_id["player-b"].units[0].own_models[0]
    assert accepted_model.geometry.geometry_source_kind is (
        GeometrySourceKind.CATALOG_GEOMETRY_RECORD
    )
    assert accepted_model.geometry.height_source_kind is (HeightSourceKind.CATALOG_GEOMETRY_RECORD)
    assert unresolved_model.geometry.geometry_source_kind is GeometrySourceKind.CATALOG_BASE_SIZE
    assert unresolved_model.geometry.height_source_kind is HeightSourceKind.KEYWORD_HEURISTIC
    assert GameConfig.from_payload(config.to_payload()).model_geometries == (reviewed_geometry,)


def test_game_config_rejects_model_geometry_for_unknown_catalog_profile() -> None:
    with pytest.raises(GameLifecycleError, match="unknown catalog model profile"):
        _config(model_geometries=(accepted_model_geometry("unknown-model-profile"),))


def test_game_config_rejects_duplicate_model_geometry_profiles() -> None:
    geometry = accepted_model_geometry()

    with pytest.raises(GameLifecycleError, match="unique by model_profile_id"):
        _config(model_geometries=(geometry, geometry))


def test_game_config_payload_rejects_structurally_incomplete_model_geometry() -> None:
    payload = cast(
        GameConfigPayload,
        json.loads(
            json.dumps(
                _config(model_geometries=(accepted_model_geometry(),)).to_payload(),
                sort_keys=True,
            )
        ),
    )
    assert "model_geometries" in payload
    geometry_payload = cast(
        dict[str, object],
        cast(object, payload["model_geometries"][0]),
    )
    del geometry_payload["support_base"]

    with pytest.raises(GameLifecycleError, match="model_geometries payload is invalid"):
        GameConfig.from_payload(payload)


def test_game_config_payload_rejects_non_record_model_geometry() -> None:
    payload = _config().to_payload()
    payload["model_geometries"] = cast(list[ModelGeometryCatalogRecordPayload], [1])

    with pytest.raises(GameLifecycleError, match="model_geometries payload is invalid"):
        GameConfig.from_payload(payload)


def test_lifecycle_replay_payload_preserves_mustered_army_definitions() -> None:
    lifecycle = _start_lifecycle()
    lifecycle.advance_until_decision_or_terminal()
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    blob = json.dumps(payload, sort_keys=True)

    assert len(payload["state"]["army_definitions"]) == 2
    assert "army-alpha:intercessor-unit-1" in blob
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


def test_lifecycle_muster_armies_fails_before_setup_advancement_on_invalid_request() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    bad_wargear = WargearSelection(
        option_id="core-intercessor-like-infantry:default-wargear",
        model_profile_id="core-intercessor-like",
        wargear_ids=("core-heavy-cannon",),
    )
    config = _config(
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
                wargear_selections=(bad_wargear,),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
    )
    lifecycle = _start_lifecycle(config)

    with pytest.raises(GameLifecycleError, match="MUSTER_ARMIES"):
        lifecycle.advance_until_decision_or_terminal()

    assert lifecycle.state is not None
    assert lifecycle.state.current_setup_step is SetupStep.MUSTER_ARMIES
    assert lifecycle.state.army_definitions == []


def test_game_config_requires_muster_requests_for_every_player() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()

    with pytest.raises(GameLifecycleError, match="every player"):
        _config(
            army_catalog=catalog,
            army_muster_requests=(
                _army_muster_request(
                    catalog=catalog,
                    player_id="player-a",
                    army_id="army-alpha",
                    unit_selection_id="intercessor-unit-1",
                ),
            ),
        )


def test_lifecycle_reads_setup_order_from_ruleset_descriptor() -> None:
    setup_steps = (
        SetupStepKind.MUSTER_ARMIES,
        SetupStepKind.SELECT_SECONDARY_MISSIONS,
        SetupStepKind.SELECT_MISSION,
        SetupStepKind.CREATE_BATTLEFIELD,
        SetupStepKind.DETERMINE_ATTACKER_DEFENDER,
        SetupStepKind.DECLARE_BATTLE_FORMATIONS,
        SetupStepKind.DEPLOY_ARMIES,
        SetupStepKind.REDEPLOY_UNITS,
        SetupStepKind.DETERMINE_FIRST_TURN,
        SetupStepKind.RESOLVE_PREBATTLE_ACTIONS,
    )
    lifecycle = _start_lifecycle(
        _config(ruleset_descriptor=_descriptor_with_sequences(setup_steps=setup_steps))
    )

    lifecycle.advance_until_decision_or_terminal()

    assert lifecycle.state is not None
    assert lifecycle.state.current_setup_step is SetupStep.SELECT_SECONDARY_MISSIONS


def test_setup_completion_enters_battle_round_one_command_phase() -> None:
    lifecycle = _start_lifecycle()

    _advance_to_battle(lifecycle)

    assert lifecycle.state is not None
    assert lifecycle.state.stage is GameLifecycleStage.BATTLE
    assert lifecycle.state.battle_round == 1
    assert lifecycle.state.active_player_id == "player-a"
    assert lifecycle.state.current_battle_phase is BattlePhase.COMMAND


def test_battle_phases_advance_command_movement_shooting_charge_fight() -> None:
    state = _battle_state()
    flow = _battle_flow()

    assert _state_battle_phase(state) is BattlePhase.COMMAND
    flow.advance(state=state, decisions=GameLifecycle().decision_controller)
    assert _state_battle_phase(state) is BattlePhase.MOVEMENT
    flow.advance(state=state, decisions=GameLifecycle().decision_controller)
    assert _state_battle_phase(state) is BattlePhase.SHOOTING
    flow.advance(state=state, decisions=GameLifecycle().decision_controller)
    assert _state_battle_phase(state) is BattlePhase.CHARGE
    flow.advance(state=state, decisions=GameLifecycle().decision_controller)
    assert _state_battle_phase(state) is BattlePhase.FIGHT


def test_lifecycle_reads_battle_phase_order_from_ruleset_descriptor() -> None:
    descriptor = _descriptor_with_sequences(
        battle_phases=(
            BattlePhaseKind.COMMAND,
            BattlePhaseKind.SHOOTING,
            BattlePhaseKind.MOVEMENT,
            BattlePhaseKind.CHARGE,
            BattlePhaseKind.FIGHT,
        )
    )
    state = _battle_state(_config(ruleset_descriptor=descriptor))
    _battle_flow().advance(state=state, decisions=GameLifecycle().decision_controller)

    assert state.current_battle_phase is BattlePhase.SHOOTING


def test_missing_battle_phase_handler_is_not_silently_skipped() -> None:
    state = _battle_state()
    decisions = GameLifecycle().decision_controller
    flow = BattleRoundFlow(phase_handlers={})

    with pytest.raises(GameLifecycleError, match="missing handler"):
        flow.advance(state=state, decisions=decisions)

    assert state.current_battle_phase is BattlePhase.COMMAND


def test_placeholder_phase_handler_emits_explicit_noop_and_advances_boundary() -> None:
    state = _battle_state()
    flow = _battle_flow()
    decisions = GameLifecycle().decision_controller
    flow.advance(state=state, decisions=decisions)

    status = flow.advance(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert status.payload == {
        "completed_phase": BattlePhase.MOVEMENT.value,
        "phase_body_status": "placeholder_noop",
        "battle_round": 1,
        "active_player_id": "player-a",
        "current_phase": BattlePhase.SHOOTING.value,
    }
    assert tuple(event.event_type for event in decisions.event_log.records) == (
        "timing_window_opened",
        "timing_window_resolved",
        "timing_window_opened",
        "timing_window_resolved",
        "timing_window_opened",
        "timing_window_resolved",
        "command_points_gained",
        "command_points_gained",
        "command_step_started",
        "command_phase_scoring_hooks_resolved",
        "battle_shock_step_completed",
        "end_boundary_objective_control_determined",
        "timing_window_opened",
        "timing_window_resolved",
        "primary_scoring_commit_checkpoint_recorded",
        "battle_phase_completed",
        "timing_window_opened",
        "timing_window_resolved",
        "phase_body_placeholder_noop",
        "end_boundary_objective_control_determined",
        "timing_window_opened",
        "timing_window_resolved",
        "battle_phase_completed",
    )


def test_phase_wrap_switches_active_player() -> None:
    state = _battle_state()
    flow = _battle_flow()

    for _ in range(5):
        flow.advance(state=state, decisions=GameLifecycle().decision_controller)

    assert state.battle_round == 1
    assert state.active_player_id == "player-b"
    assert state.current_battle_phase is BattlePhase.COMMAND


def test_turn_end_objective_control_audit_follows_post_cleanup_capture() -> None:
    state = _battle_state()
    flow = _battle_flow()
    decisions = DecisionController()

    for _ in range(5):
        flow.advance(state=state, decisions=decisions)

    fight_boundary_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "end_boundary_objective_control_determined"
        and isinstance(event.payload, dict)
        and event.payload.get("phase") == BattlePhase.FIGHT.value
    )
    assert len(fight_boundary_events) == 2
    phase_end_record = next(
        record
        for record in state.objective_control_records
        if record.phase == BattlePhase.FIGHT.value
        and record.timing is ObjectiveControlTiming.PHASE_END
    )
    turn_end_record = next(
        record
        for record in state.objective_control_records
        if record.phase == BattlePhase.FIGHT.value
        and record.timing is ObjectiveControlTiming.TURN_END
    )
    fight_boundary_payloads = tuple(
        cast(dict[str, JsonValue], event.payload) for event in fight_boundary_events
    )
    assert [payload["record_ids"] for payload in fight_boundary_payloads] == [
        [phase_end_record.record_id],
        [turn_end_record.record_id],
    ]
    event_types = tuple(event.event_type for event in decisions.event_log.records)
    turn_end_audit_index = decisions.event_log.records.index(fight_boundary_events[-1])
    phase_completed_index = next(
        index
        for index in range(turn_end_audit_index + 1, len(event_types))
        if event_types[index] == "battle_phase_completed"
    )
    turn_start_evidence_indexes = tuple(
        index
        for index in range(turn_end_audit_index + 1, len(event_types))
        if event_types[index] == "primary_turn_start_evidence_recorded"
    )
    assert turn_end_audit_index < phase_completed_index
    assert all(
        turn_end_audit_index < index < phase_completed_index
        for index in turn_start_evidence_indexes
    )


def test_battle_round_increments_after_all_players_complete_fight_phase() -> None:
    state = _battle_state()
    flow = _battle_flow()

    for _ in range(10):
        flow.advance(state=state, decisions=GameLifecycle().decision_controller)

    assert state.battle_round == 2
    assert state.active_player_id == "player-a"
    assert state.current_battle_phase is BattlePhase.COMMAND


def test_lifecycle_stops_at_decision_request() -> None:
    lifecycle = _start_lifecycle()

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.actor_id == "player-a"
    assert status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    assert lifecycle.state is not None
    assert lifecycle.state.current_setup_step is SetupStep.SELECT_SECONDARY_MISSIONS


def test_advance_until_reaches_first_decision_from_initial_state_in_one_call() -> None:
    lifecycle = _start_lifecycle()

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    assert status.decision_request.actor_id == "player-a"
    assert lifecycle.state is not None
    assert lifecycle.state.current_setup_step is SetupStep.SELECT_SECONDARY_MISSIONS


def test_select_secondary_missions_emits_secret_requests_for_both_players() -> None:
    lifecycle = _start_lifecycle()
    _advance_to_secondary_mission_step(lifecycle)

    first_status = lifecycle.advance_until_decision_or_terminal()
    assert first_status.decision_request is not None
    assert _request_payload(first_status.decision_request)["secret"] is True
    assert first_status.decision_request.actor_id == "player-a"
    _submit_pending(lifecycle, option_id="tactical", result_number=1)

    second_status = lifecycle.advance_until_decision_or_terminal()
    assert second_status.decision_request is not None
    assert _request_payload(second_status.decision_request)["secret"] is True
    assert second_status.decision_request.actor_id == "player-b"
    _submit_pending(lifecycle, option_id="fixed:assassination:bring_it_down", result_number=2)

    assert lifecycle.state is not None
    assert lifecycle.state.missing_secondary_mission_player_ids() == ()


def test_secondary_mission_public_payload_reveals_after_all_choices() -> None:
    lifecycle = _start_lifecycle()
    _choose_secondaries(
        lifecycle,
        player_a_option="tactical",
        player_b_option="fixed:bring_it_down:cleanse",
    )
    assert lifecycle.state is not None

    player_a_payload = lifecycle.state.to_public_payload(viewer_player_id="player-a")
    player_b_payload = lifecycle.state.to_public_payload(viewer_player_id="player-b")
    assert {
        "player_id": "player-b",
        "selected": True,
        "hidden": False,
        "mode": "fixed",
        "fixed_mission_ids": ["bring_it_down", "cleanse"],
    } in _public_secondary_choices(player_a_payload)
    assert {
        "player_id": "player-a",
        "selected": True,
        "hidden": False,
        "mode": "tactical",
        "fixed_mission_ids": [],
    } in _public_secondary_choices(player_b_payload)
    assert "bring_it_down" in json.dumps(player_b_payload, sort_keys=True)
    assert "cleanse" in json.dumps(player_b_payload, sort_keys=True)


def test_tactical_secondary_draws_occur_in_command_phase_not_setup() -> None:
    lifecycle = _start_lifecycle()
    _choose_secondaries(
        lifecycle,
        player_a_option="tactical",
        player_b_option="fixed:assassination:bring_it_down",
    )
    setup_decision_types = [
        record.request.decision_type for record in lifecycle.decision_controller.records
    ]

    status = lifecycle.advance_until_decision_or_terminal()
    while lifecycle.state is not None and lifecycle.state.stage is not GameLifecycleStage.BATTLE:
        status = submit_all_deployments_if_pending(
            lifecycle,
            status,
            result_id_prefix="phase9b-tactical-setup-deploy",
        )
        if _lifecycle_is_in_battle(lifecycle):
            break
        status = lifecycle.advance_until_decision_or_terminal()

    status = lifecycle.advance_until_decision_or_terminal()

    assert setup_decision_types == [
        SECONDARY_MISSION_DECISION_TYPE,
        SECONDARY_MISSION_DECISION_TYPE,
    ]
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE
    assert status.decision_request.actor_id == "player-a"
    assert _request_payload(status.decision_request)["phase"] == BattlePhase.COMMAND.value


def test_tactical_secondary_draw_decision_records_command_draw_and_enters_movement() -> None:
    lifecycle = _start_lifecycle()
    _choose_secondaries(
        lifecycle,
        player_a_option="tactical",
        player_b_option="fixed:assassination:bring_it_down",
    )
    status = lifecycle.advance_until_decision_or_terminal()
    while lifecycle.state is not None and lifecycle.state.stage is not GameLifecycleStage.BATTLE:
        status = submit_all_deployments_if_pending(
            lifecycle,
            status,
            result_id_prefix="phase9b-tactical-draw-deploy",
        )
        if _lifecycle_is_in_battle(lifecycle):
            break
        status = lifecycle.advance_until_decision_or_terminal()

    status = lifecycle.advance_until_decision_or_terminal()
    assert status.decision_request is not None
    draw_result = DecisionResult.for_request(
        result_id="decision-result-000003",
        request=status.decision_request,
        selected_option_id="draw",
    )
    follow_up_status = lifecycle.submit_decision(draw_result)
    follow_up_status = _decline_stratagem_window_if_pending(
        lifecycle,
        follow_up_status,
        result_number=4,
    )

    assert lifecycle.state is not None
    assert follow_up_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert follow_up_status.decision_request is not None
    assert follow_up_status.decision_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert follow_up_status.decision_request.actor_id == "player-a"
    assert lifecycle.state.current_battle_phase is BattlePhase.MOVEMENT
    assert lifecycle.state.battlefield_state is not None
    assert len(lifecycle.state.tactical_secondary_draws) == 1
    draw = lifecycle.state.tactical_secondary_draws[0]
    assert draw.player_id == "player-a"
    assert draw.battle_round == 1
    assert draw.draw_count == 2
    assert len(lifecycle.decision_controller.queue.pending_requests) == 1
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


def test_descriptor_hash_is_recorded_in_lifecycle_replay_payloads() -> None:
    config = _config()
    lifecycle = _start_lifecycle(config)
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    assert payload["config"] is not None
    assert payload["config"]["ruleset_descriptor"]["descriptor_hash"] == (
        config.ruleset_descriptor.descriptor_hash
    )
    assert payload["state"]["ruleset_descriptor_hash"] == config.ruleset_descriptor.descriptor_hash
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


def test_lifecycle_transition_guard_is_recorded_in_config_provenance() -> None:
    config = _config(max_lifecycle_transitions=127)
    lifecycle = _start_lifecycle(config)
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    assert payload["config"] is not None
    assert payload["config"]["max_lifecycle_transitions"] == 127
    assert GameConfig.from_payload(payload["config"]).max_lifecycle_transitions == 127
    assert GameLifecycle.from_payload(payload).config.max_lifecycle_transitions == 127


def test_lifecycle_transition_guard_returns_typed_boundary_when_config_limit_is_too_low() -> None:
    lifecycle = _start_lifecycle(_config(max_lifecycle_transitions=1))

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert status.message == "Lifecycle reached its deterministic transition safety boundary."
    assert status.payload == {
        "unsupported_reason": "transition_budget_exhausted",
        "transition_budget": 1,
    }


def test_game_config_rejects_lifecycle_sequence_prerequisite_gaps() -> None:
    missing_secondary = _descriptor_with_sequences(
        setup_steps=(
            SetupStepKind.MUSTER_ARMIES,
            SetupStepKind.SELECT_MISSION,
            SetupStepKind.CREATE_BATTLEFIELD,
            SetupStepKind.DETERMINE_ATTACKER_DEFENDER,
            SetupStepKind.DECLARE_BATTLE_FORMATIONS,
            SetupStepKind.DEPLOY_ARMIES,
            SetupStepKind.REDEPLOY_UNITS,
            SetupStepKind.DETERMINE_FIRST_TURN,
            SetupStepKind.RESOLVE_PREBATTLE_ACTIONS,
        )
    )
    with pytest.raises(GameLifecycleError, match="SELECT_SECONDARY_MISSIONS"):
        _config(ruleset_descriptor=missing_secondary)

    not_command_first = _descriptor_with_sequences(
        battle_phases=(
            BattlePhaseKind.MOVEMENT,
            BattlePhaseKind.COMMAND,
            BattlePhaseKind.FIGHT,
        )
    )
    with pytest.raises(GameLifecycleError, match="start with COMMAND"):
        _config(ruleset_descriptor=not_command_first)


def test_lifecycle_from_payload_rejects_config_state_ruleset_drift() -> None:
    lifecycle = _start_lifecycle()
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    hash_mismatch = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    hash_mismatch["state"]["ruleset_descriptor_hash"] = "0" * 64
    with pytest.raises(GameLifecycleError, match="ruleset hash"):
        GameLifecycle.from_payload(hash_mismatch)

    setup_mismatch = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    setup_mismatch["state"]["setup_sequence"] = list(reversed(payload["state"]["setup_sequence"]))
    with pytest.raises(GameLifecycleError, match="setup sequence"):
        GameLifecycle.from_payload(setup_mismatch)

    battle_mismatch = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    battle_mismatch["state"]["battle_phase_sequence"] = [
        BattlePhaseKind.COMMAND.value,
        BattlePhaseKind.SHOOTING.value,
        BattlePhaseKind.MOVEMENT.value,
        BattlePhaseKind.CHARGE.value,
        BattlePhaseKind.FIGHT.value,
    ]
    with pytest.raises(GameLifecycleError, match="battle phase sequence"):
        GameLifecycle.from_payload(battle_mismatch)


def test_lifecycle_from_payload_rejects_config_state_identity_drift() -> None:
    lifecycle = _start_lifecycle()
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    game_id_mismatch = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    game_id_mismatch["state"]["game_id"] = "other-game"
    with pytest.raises(GameLifecycleError, match="game_id"):
        GameLifecycle.from_payload(game_id_mismatch)

    player_mismatch = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    player_mismatch["state"]["player_ids"] = ["player-a", "player-c"]
    with pytest.raises(GameLifecycleError, match="player_ids"):
        GameLifecycle.from_payload(player_mismatch)

    turn_order_mismatch = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(payload, sort_keys=True)),
    )
    turn_order_mismatch["state"]["turn_order"] = ["player-b", "player-a"]
    with pytest.raises(GameLifecycleError, match="turn_order"):
        GameLifecycle.from_payload(turn_order_mismatch)

    tactical_count_mismatch = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(payload, sort_keys=True)),
    )
    tactical_count_mismatch["state"]["tactical_secondary_draw_count"] = 3
    with pytest.raises(GameLifecycleError, match="tactical secondary draw count"):
        GameLifecycle.from_payload(tactical_count_mismatch)


@pytest.mark.parametrize(
    ("corruption", "expected_message"),
    [
        ("wrong_phase", "charge_phase_state requires CHARGE phase"),
        ("active_player_drift", "charge_phase_state active player drift"),
        ("battle_round_drift", "charge_phase_state battle round drift"),
        ("selected_enemy", "selected unit is not active player's unit"),
        ("roll_unit_not_selected", "roll unit was not selected"),
        ("unknown_target", "target unit is unknown"),
        ("friendly_target", "target unit is not an enemy"),
    ],
)
def test_lifecycle_restore_rejects_corrupt_charge_phase_authority(
    corruption: str,
    expected_message: str,
) -> None:
    payload, alpha_unit_id, beta_unit_id = _phase_state_consistency_payload(
        phase=BattlePhase.CHARGE
    )
    state_payload = payload["state"]
    charge_payload = cast(dict[str, object], state_payload["charge_phase_state"])
    selection = cast(dict[str, object], charge_payload["active_selection"])
    distance_states = cast(list[dict[str, object]], charge_payload["distance_states"])
    roll_result = cast(dict[str, object], distance_states[0]["roll_result"])

    if corruption == "wrong_phase":
        state_payload["battle_phase_index"] = state_payload["battle_phase_sequence"].index(
            BattlePhase.MOVEMENT.value
        )
    elif corruption == "active_player_drift":
        charge_payload["active_player_id"] = "player-b"
        selection["player_id"] = "player-b"
    elif corruption == "battle_round_drift":
        charge_payload["battle_round"] = 2
        selection["battle_round"] = 2
    elif corruption == "selected_enemy":
        charge_payload["selected_unit_ids"] = [alpha_unit_id, beta_unit_id]
    elif corruption == "roll_unit_not_selected":
        charge_payload["selected_unit_ids"] = []
        charge_payload["active_selection"] = None
    elif corruption == "unknown_target":
        roll_result["reachable_target_distances_inches"] = {"unknown-target": 3.0}
    elif corruption == "friendly_target":
        roll_result["reachable_target_distances_inches"] = {alpha_unit_id: 3.0}

    with pytest.raises(GameLifecycleError, match=expected_message):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_message"),
    [
        ("wrong_phase", "movement_phase_state requires MOVEMENT phase"),
        ("active_player_drift", "movement_phase_state active player drift"),
        ("battle_round_drift", "movement_phase_state battle round drift"),
        ("selected_enemy", "selected unit is not active player's unit"),
    ],
)
def test_lifecycle_restore_rejects_corrupt_movement_phase_authority(
    corruption: str,
    expected_message: str,
) -> None:
    payload, _alpha_unit_id, beta_unit_id = _phase_state_consistency_payload(
        phase=BattlePhase.MOVEMENT
    )
    state_payload = payload["state"]
    movement_payload = cast(dict[str, object], state_payload["movement_phase_state"])

    if corruption == "wrong_phase":
        state_payload["battle_phase_index"] = state_payload["battle_phase_sequence"].index(
            BattlePhase.SHOOTING.value
        )
    elif corruption == "active_player_drift":
        movement_payload["active_player_id"] = "player-b"
    elif corruption == "battle_round_drift":
        movement_payload["battle_round"] = 2
    elif corruption == "selected_enemy":
        movement_payload["selected_unit_ids"] = [beta_unit_id]

    with pytest.raises(GameLifecycleError, match=expected_message):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_message"),
    [
        ("wrong_phase", "shooting_phase_state requires SHOOTING phase"),
        ("active_player_drift", "shooting_phase_state active player drift"),
        ("battle_round_drift", "shooting_phase_state battle round drift"),
        ("selected_enemy", "selected unit is not active player's unit"),
    ],
)
def test_lifecycle_restore_rejects_corrupt_shooting_phase_authority(
    corruption: str,
    expected_message: str,
) -> None:
    payload, _alpha_unit_id, beta_unit_id = _phase_state_consistency_payload(
        phase=BattlePhase.SHOOTING
    )
    state_payload = payload["state"]
    shooting_payload = cast(dict[str, object], state_payload["shooting_phase_state"])

    if corruption == "wrong_phase":
        state_payload["battle_phase_index"] = state_payload["battle_phase_sequence"].index(
            BattlePhase.MOVEMENT.value
        )
    elif corruption == "active_player_drift":
        shooting_payload["active_player_id"] = "player-b"
    elif corruption == "battle_round_drift":
        shooting_payload["battle_round"] = 2
    elif corruption == "selected_enemy":
        shooting_payload["selected_unit_ids"] = [beta_unit_id]

    with pytest.raises(GameLifecycleError, match=expected_message):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_message"),
    [
        ("wrong_phase", "fight_phase_state requires FIGHT phase"),
        ("active_player_drift", "fight_phase_state active player drift"),
        ("battle_round_drift", "fight_phase_state battle round drift"),
        ("next_player_unknown", "next player is not in this game"),
        ("unit_unknown", "fight_phase_state unit is unknown"),
        ("passed_player_unknown", "passed player is not in this game"),
        ("activation_unit_unknown", "activation unit is unknown"),
        ("activation_player_drift", "activation player drift"),
    ],
)
def test_lifecycle_restore_rejects_corrupt_fight_phase_authority(
    corruption: str,
    expected_message: str,
) -> None:
    payload, alpha_unit_id, _beta_unit_id = _phase_state_consistency_payload(
        phase=BattlePhase.FIGHT
    )
    state_payload = payload["state"]
    fight_payload = cast(dict[str, object], state_payload["fight_phase_state"])
    fight_order = cast(dict[str, object], fight_payload["fight_order_state"])

    if corruption == "wrong_phase":
        state_payload["battle_phase_index"] = state_payload["battle_phase_sequence"].index(
            BattlePhase.CHARGE.value
        )
    elif corruption == "active_player_drift":
        fight_payload["active_player_id"] = "player-b"
    elif corruption == "battle_round_drift":
        fight_payload["battle_round"] = 2
    elif corruption == "next_player_unknown":
        fight_order["next_player_id"] = "player-c"
    elif corruption == "unit_unknown":
        fight_order["engaged_at_fight_step_start_unit_ids"] = ["unknown-fight-unit"]
    elif corruption == "passed_player_unknown":
        fight_order["passed_player_ids"] = ["player-c"]
    elif corruption in {"activation_unit_unknown", "activation_player_drift"}:
        fight_order["activation_selections"] = [
            {
                "player_id": (
                    "player-b" if corruption == "activation_player_drift" else "player-a"
                ),
                "battle_round": 1,
                "unit_instance_id": (
                    alpha_unit_id
                    if corruption == "activation_player_drift"
                    else "unknown-fight-unit"
                ),
                "ordering_band": "remaining_combats",
                "fight_type": "normal",
                "eligibility_reasons": ["currently_engaged"],
                "request_id": "phase9b-fight-activation-request",
                "result_id": "phase9b-fight-activation-result",
                "interrupt_id": None,
            }
        ]

    with pytest.raises(GameLifecycleError, match=expected_message):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_message"),
    [
        ("selection_missing_history", "selection is missing from selected history"),
        ("active_missing_selection", "must match exactly one selection"),
        ("active_selection_drift", "Active Fight activation selection drift"),
        ("duplicate_result_id", "selection result IDs must be unique"),
    ],
)
def test_lifecycle_restore_rejects_corrupt_fight_activation_history(
    corruption: str,
    expected_message: str,
) -> None:
    payload, alpha_unit_id, beta_unit_id = _phase_state_consistency_payload(phase=BattlePhase.FIGHT)
    fight_payload = cast(dict[str, object], payload["state"]["fight_phase_state"])
    fight_order = cast(dict[str, object], fight_payload["fight_order_state"])
    selection = {
        "player_id": "player-a",
        "battle_round": 1,
        "unit_instance_id": alpha_unit_id,
        "ordering_band": "remaining_combats",
        "fight_type": "normal",
        "eligibility_reasons": ["currently_engaged"],
        "request_id": "phase9b-fight-history-request",
        "result_id": "phase9b-fight-history-result",
        "interrupt_id": None,
    }
    if corruption == "selection_missing_history":
        fight_order["activation_selections"] = [selection]
    elif corruption == "active_missing_selection":
        fight_payload["active_activation"] = selection
    elif corruption == "active_selection_drift":
        fight_order["selected_to_fight_unit_ids"] = [alpha_unit_id]
        fight_order["activation_selections"] = [selection]
        fight_payload["active_activation"] = {
            **selection,
            "request_id": "phase9b-fight-history-drift",
        }
    elif corruption == "duplicate_result_id":
        fight_order["selected_to_fight_unit_ids"] = [alpha_unit_id, beta_unit_id]
        fight_order["activation_selections"] = [
            selection,
            {
                **selection,
                "player_id": "player-b",
                "unit_instance_id": beta_unit_id,
                "request_id": "phase9b-fight-history-request-beta",
            },
        ]

    with pytest.raises(GameLifecycleError, match=expected_message):
        GameLifecycle.from_payload(payload)


def test_lifecycle_from_payload_rejects_mustered_army_state_drift() -> None:
    lifecycle = _start_lifecycle()
    lifecycle.advance_until_decision_or_terminal()
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    missing_armies = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    missing_armies["state"]["army_definitions"] = []
    missing_armies["state"]["starting_strength_records"] = []
    with pytest.raises(GameLifecycleError, match=r"mustered army definitions|battlefield_state"):
        GameLifecycle.from_payload(missing_armies)

    army_mismatch = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    army_mismatch["state"]["army_definitions"][0]["units"][0]["name"] = "Different Name"
    with pytest.raises(GameLifecycleError, match="army definitions"):
        GameLifecycle.from_payload(army_mismatch)


def test_no_ui_or_headless_specific_phase_path_exists() -> None:
    public_methods = {
        name
        for name, _member in inspect.getmembers(GameLifecycle, inspect.isfunction)
        if not name.startswith("_")
    }

    assert public_methods == {
        "advance_until_decision_or_terminal",
        "pending_decision_request",
        "start",
        "submit_decision",
        "to_payload",
    }
    assert callable(GameLifecycle.from_payload)


def test_lifecycle_and_command_handler_fail_fast_on_invalid_entry_points() -> None:
    lifecycle = GameLifecycle()
    with pytest.raises(GameLifecycleError, match="has not started"):
        lifecycle.advance_until_decision_or_terminal()

    config = _config()
    lifecycle.start(config)
    with pytest.raises(GameLifecycleError, match="already started"):
        lifecycle.start(config)

    _advance_to_battle(lifecycle)
    assert CommandPhaseHandler().phase is BattlePhase.COMMAND
    draw_status = _submit_pending(lifecycle, option_id="draw", result_number=3)
    draw_status = drain_pending_secondary_mission_setup(
        lifecycle,
        draw_status,
        result_id_prefix="decision-result-secondary-setup",
    )
    if (
        draw_status.decision_request is not None
        and draw_status.decision_request.decision_type == STRATAGEM_DECISION_TYPE
    ):
        _submit_pending(
            lifecycle,
            option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
            result_number=4,
        )
    assert lifecycle.state is not None
    assert lifecycle.state.current_battle_phase is BattlePhase.MOVEMENT
    with pytest.raises(GameLifecycleError, match="only in the COMMAND phase"):
        CommandPhaseHandler().begin_phase(
            state=lifecycle.state,
            decisions=lifecycle.decision_controller,
        )


def test_lifecycle_status_payloads_are_serializable_and_fail_fast() -> None:
    advanced = LifecycleStatus.advanced(
        stage=GameLifecycleStage.SETUP,
        payload={"step": SetupStep.MUSTER_ARMIES.value},
    )
    terminal = LifecycleStatus.terminal(
        stage=GameLifecycleStage.COMPLETE,
        message="complete",
    )
    unsupported = LifecycleStatus.unsupported(
        stage=GameLifecycleStage.BATTLE,
        message="phase body unsupported",
    )

    for status in (advanced, terminal, unsupported):
        payload = json.loads(json.dumps(status.to_payload(), sort_keys=True))
        assert LifecycleStatus.from_payload(payload).to_payload() == status.to_payload()

    with pytest.raises(GameLifecycleError, match="requires a decision_request"):
        LifecycleStatus(
            stage=GameLifecycleStage.SETUP,
            status_kind=LifecycleStatusKind.WAITING_FOR_DECISION,
        )
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        LifecycleStatus.terminal(stage=GameLifecycleStage.COMPLETE, message=" ")
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        game_lifecycle_stage_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported GameLifecycleStage"):
        game_lifecycle_stage_from_token("unsupported")
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        lifecycle_status_kind_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported LifecycleStatusKind"):
        lifecycle_status_kind_from_token("bad_kind")
