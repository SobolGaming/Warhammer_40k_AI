from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_action_and_movement_proposal,
)
from tests.phase10o_fall_back_helpers import (
    advance_to_movement_unit_selection,
    decision_request,
    fall_back_state,
)
from tests.phase11c_command_phase_helpers import (
    center_marker_definition,
    complete_setup_through_gate,
    with_model_offsets,
)

from warhammer40k_core.adapters.contracts import ParameterizedSubmission
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_formation_hooks import BattleFormationRequestContext
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.runtime import build_runtime_content_bundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.blood_legion import (  # noqa: E501
    rule,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    LifecycleStatus,
    LifecycleStatusKind,
    PlaceholderPhaseHandler,
    SetupStep,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.triggered_movement import (
    SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
)

_BLOOD_LEGION_DATASHEET_ID = "phase17g-blood-legion-khorne-daemon"
_BLOOD_LEGION_NON_KHORNE_DATASHEET_ID = "phase17g-blood-legion-non-khorne-daemon"
_BLOOD_UNIT_ID = "army-alpha:blood-daemon-unit"
_OTHER_FRIENDLY_UNIT_ID = "army-alpha:non-khorne-daemon-unit"
_ENEMY_UNIT_ID = "army-beta:enemy-unit"
_OTHER_DAEMON_DETACHMENT_ID = "warptide"


def test_blood_legion_runtime_hooks_materialize_only_for_selected_detachment() -> None:
    blood_summary = build_runtime_content_bundle(_blood_legion_config()).to_summary_payload()

    assert rule.MURDERCALL_HOOK_ID in blood_summary["movement_end_surge_hook_ids"]
    assert rule.BLOOD_TAINTED_HOOK_ID in blood_summary["phase_end_objective_control_hook_ids"]
    assert rule.SOURCE_RULE_ID in blood_summary["selected_execution_record_ids"]
    assert any(
        path.endswith(".chaos_daemons.detachments.blood_legion.manifest")
        for path in blood_summary["selected_module_paths"]
    )

    other_summary = build_runtime_content_bundle(
        _blood_legion_config(
            daemon_detachment_id=_OTHER_DAEMON_DETACHMENT_ID,
            game_id="phase17g-blood-legion-not-selected",
        )
    ).to_summary_payload()

    assert rule.MURDERCALL_HOOK_ID not in other_summary["movement_end_surge_hook_ids"]
    assert rule.BLOOD_TAINTED_HOOK_ID not in other_summary["phase_end_objective_control_hook_ids"]


def test_murdercall_triggers_after_enemy_move_and_resolves_surge_proposal() -> None:
    config = _blood_legion_config(
        game_id="phase17g-murdercall-game",
        turn_order=("player-b", "player-a"),
    )
    lifecycle, movement_status = advance_to_movement_unit_selection(config)
    state = fall_back_state(lifecycle)
    _place_murdercall_units(state)
    summary = _runtime_content_bundle(lifecycle).to_summary_payload()

    assert rule.MURDERCALL_HOOK_ID in summary["movement_end_surge_hook_ids"]

    selection_request = decision_request(movement_status)
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-murdercall-select-enemy",
            request=selection_request,
            selected_option_id=_ENEMY_UNIT_ID,
        )
    )
    action_request = decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE

    surge_status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        action_result_id="phase17g-murdercall-normal-move-action",
        proposal_result_id="phase17g-murdercall-normal-move-proposal",
        unit_instance_id=_ENEMY_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_ENEMY_UNIT_ID,
            dx=4.0,
        ),
    )
    surge_request = decision_request(surge_status)
    assert surge_request.decision_type == SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE
    assert surge_request.actor_id == "player-a"
    surge_option_id = f"surge:{_BLOOD_UNIT_ID}"
    assert surge_option_id in {option.option_id for option in surge_request.options}

    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-murdercall-select-surge-unit",
            request=surge_request,
            selected_option_id=surge_option_id,
        )
    )
    proposal_request = decision_request(proposal_status)
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert proposal.proposal_kind is ProposalKind.SURGE_MOVE
    assert proposal.unit_instance_id == _BLOOD_UNIT_ID

    resolved_status = _submit_surge_proposal(
        lifecycle=lifecycle,
        request=proposal_request,
        result_id="phase17g-murdercall-surge-proposal",
        unit_instance_id=_BLOOD_UNIT_ID,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_BLOOD_UNIT_ID,
            dx=-1.0,
        ),
    )

    assert resolved_status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    trigger_payload = _event_payload(lifecycle.decision_controller, "movement_end_surge_triggered")
    grants = cast(list[JsonValue], trigger_payload["grants"])
    first_grant = cast(dict[str, JsonValue], grants[0])
    assert first_grant["hook_id"] == rule.MURDERCALL_HOOK_ID
    assert first_grant["source_id"] == rule.SOURCE_RULE_ID
    resolved_payload = _event_payload(lifecycle.decision_controller, "triggered_movement_resolved")
    assert resolved_payload["source_rule_id"] == rule.SOURCE_RULE_ID
    assert resolved_payload["unit_instance_id"] == _BLOOD_UNIT_ID
    assert len(state.normal_move_states) == 2
    surge_states = tuple(
        move_state
        for move_state in state.normal_move_states
        if move_state.source_rule_id == rule.SOURCE_RULE_ID
    )
    assert len(surge_states) == 1


def test_blood_tainted_records_sticky_control_at_phase_end_boundary() -> None:
    config = _blood_legion_config(game_id="phase17g-blood-tainted-game")
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _battle_ready_state(lifecycle=lifecycle, config=config)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    _place_blood_tainted_units_on_center_objective(state)
    decisions = DecisionController()
    snapshot_payload = _emit_objective_proximity_snapshot(
        state=state,
        decisions=decisions,
        phase=BattlePhase.SHOOTING,
        ruleset_descriptor=config.ruleset_descriptor,
    )
    objective_id = _single_objective_id_for_unit(snapshot_payload, _ENEMY_UNIT_ID)
    _destroy_enemy_unit_for_blood_tainted(state=state, decisions=decisions)
    flow = BattleRoundFlow(
        phase_handlers={
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
        },
        phase_end_objective_control_hooks=(
            _runtime_content_bundle(lifecycle).phase_end_objective_control_hook_registry
        ),
    )

    status = flow.advance(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert len(state.sticky_objective_control_states) == 1
    sticky_state = state.sticky_objective_control_states[0]
    assert sticky_state.source_rule_id == rule.SOURCE_RULE_ID
    assert sticky_state.objective_id == objective_id
    sticky_event = _event_payload(decisions, "sticky_objective_control_state_recorded")
    sticky_payload = cast(dict[str, JsonValue], sticky_event["sticky_objective_control_state"])
    assert sticky_payload["source_rule_id"] == rule.SOURCE_RULE_ID
    phase_end_record = state.objective_control_records[-1]
    retained_result = phase_end_record.result_by_objective_id(objective_id)
    assert retained_result.controlled_by_player_id == "player-a"
    assert retained_result.retained_control_source_id is None
    event_types = tuple(event.event_type for event in decisions.event_log.records)
    assert event_types.index("end_boundary_objective_control_determined") < event_types.index(
        "sticky_objective_control_state_recorded"
    )


def test_blood_tainted_credits_only_unit_destruction_completion_attacker() -> None:
    config = _blood_legion_config(
        game_id="phase17g-blood-tainted-completion-attribution-game",
        include_other_friendly_unit=True,
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _battle_ready_state(lifecycle=lifecycle, config=config)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    _place_blood_tainted_units_on_center_objective(state)
    decisions = DecisionController()
    snapshot_payload = _emit_objective_proximity_snapshot(
        state=state,
        decisions=decisions,
        phase=BattlePhase.SHOOTING,
        ruleset_descriptor=config.ruleset_descriptor,
    )
    objective_id = _single_objective_id_for_unit(snapshot_payload, _ENEMY_UNIT_ID)
    _destroy_enemy_unit_with_split_attackers_for_blood_tainted(
        state=state,
        decisions=decisions,
    )
    flow = BattleRoundFlow(
        phase_handlers={
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
        },
        phase_end_objective_control_hooks=(
            _runtime_content_bundle(lifecycle).phase_end_objective_control_hook_registry
        ),
    )

    status = flow.advance(state=state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert state.sticky_objective_control_states == []
    assert all(
        event.event_type != "sticky_objective_control_state_recorded"
        for event in decisions.event_log.records
    )
    phase_end_record = state.objective_control_records[-1]
    result = phase_end_record.result_by_objective_id(objective_id)
    assert result.controlled_by_player_id == "player-a"
    assert result.retained_control_source_id is None


def test_blood_legion_rule_hooks_use_phase17f_execution_source_id() -> None:
    record = _blood_legion_rule_execution_record()
    bundle = build_runtime_content_bundle(_blood_legion_config(game_id="phase17g-blood-source-id"))
    surge_binding = next(
        binding
        for binding in bundle.movement_end_surge_hook_registry.all_bindings()
        if binding.hook_id == rule.MURDERCALL_HOOK_ID
    )
    sticky_binding = next(
        binding
        for binding in bundle.phase_end_objective_control_hook_registry.all_bindings()
        if binding.hook_id == rule.BLOOD_TAINTED_HOOK_ID
    )

    assert record.execution_id == rule.SOURCE_RULE_ID
    assert surge_binding.source_id == record.execution_id
    assert sticky_binding.source_id == record.execution_id


def _blood_legion_rule_execution_record() -> Phase17FExecutionRecord:
    records = tuple(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.faction_id == rule.CHAOS_DAEMONS_FACTION_ID
        and record.detachment_id == rule.BLOOD_LEGION_DETACHMENT_ID
        and record.coverage_kind is Phase17ECoverageKind.DETACHMENT_RULE
    )
    if len(records) != 1:
        raise AssertionError("expected one Blood Legion detachment-rule execution record")
    return records[0]


def _blood_legion_config(
    *,
    game_id: str = "phase17g-blood-legion-game",
    daemon_detachment_id: str = rule.BLOOD_LEGION_DETACHMENT_ID,
    turn_order: tuple[str, str] = ("player-a", "player-b"),
    include_other_friendly_unit: bool = False,
) -> GameConfig:
    catalog = _blood_legion_catalog()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase17g-blood-legion-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_id=daemon_detachment_id,
                unit_selection_id="blood-daemon-unit",
                datasheet_id=_BLOOD_LEGION_DATASHEET_ID,
                extra_unit_selections=(
                    (
                        "non-khorne-daemon-unit",
                        _BLOOD_LEGION_NON_KHORNE_DATASHEET_ID,
                    ),
                )
                if include_other_friendly_unit
                else (),
            ),
            _army_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                faction_id="core-marine-force",
                detachment_id="core-combined-arms",
                unit_selection_id="enemy-unit",
                datasheet_id="core-intercessor-like-infantry",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=turn_order,
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _blood_legion_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    daemon_datasheet = _blood_legion_datasheet(base_datasheet)
    non_khorne_daemon_datasheet = _blood_legion_non_khorne_datasheet(base_datasheet)
    return replace(
        base_catalog,
        datasheets=(
            *base_catalog.datasheets,
            daemon_datasheet,
            non_khorne_daemon_datasheet,
        ),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                name="Chaos Daemons",
                faction_keywords=("Legiones Daemonica",),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:chaos-daemons",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id=rule.BLOOD_LEGION_DETACHMENT_ID,
                name="Blood Legion",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=2,
                unit_datasheet_ids=(
                    _BLOOD_LEGION_DATASHEET_ID,
                    _BLOOD_LEGION_NON_KHORNE_DATASHEET_ID,
                ),
                force_disposition_ids=("phase17g-force",),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:chaos-daemons:blood-legion",
                ),
            ),
            DetachmentDefinition(
                detachment_id=_OTHER_DAEMON_DETACHMENT_ID,
                name="Warptide",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(_BLOOD_LEGION_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:chaos-daemons:warptide",
                ),
            ),
        ),
    )


def _blood_legion_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_BLOOD_LEGION_DATASHEET_ID,
        name="Blood Legion Khorne Daemon",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry", "Khorne"),
            faction_keywords=("Legiones Daemonica",),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:chaos-daemons:blood-legion-khorne-daemon",),
    )


def _blood_legion_non_khorne_datasheet(
    base_datasheet: DatasheetDefinition,
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_BLOOD_LEGION_NON_KHORNE_DATASHEET_ID,
        name="Blood Legion Non-Khorne Daemon",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry", "Tzeentch"),
            faction_keywords=("Legiones Daemonica",),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:chaos-daemons:blood-legion-non-khorne-daemon",),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    faction_id: str,
    detachment_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    extra_unit_selections: tuple[tuple[str, str], ...] = (),
) -> ArmyMusterRequest:
    unit_selections = [
        _unit_muster_selection(
            unit_selection_id=unit_selection_id,
            datasheet_id=datasheet_id,
        )
    ]
    unit_selections.extend(
        _unit_muster_selection(
            unit_selection_id=extra_unit_selection_id,
            datasheet_id=extra_datasheet_id,
        )
        for extra_unit_selection_id, extra_datasheet_id in extra_unit_selections
    )
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
        ),
        force_disposition_id=(
            "purge-the-foe" if faction_id == "core-marine-force" else "phase17g-force"
        ),
        unit_selections=tuple(unit_selections),
    )


def _unit_muster_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _battle_ready_state(
    *,
    lifecycle: GameLifecycle,
    config: GameConfig,
) -> GameState:
    state = lifecycle.state
    if state is None:
        raise AssertionError("lifecycle must be started")
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17g-blood-legion-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-a"))
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-b"))
    while state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        state.complete_current_setup_step()
    request = _runtime_content_bundle(lifecycle).battle_formation_hook_registry.next_request_for(
        BattleFormationRequestContext(
            state=state,
            decisions=DecisionController(),
            config=config,
        )
    )
    if request is not None:
        raise AssertionError("Blood Legion test fixture should not require battle formation input")
    complete_setup_through_gate(state=state, config=config)
    return state


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _fixed_secondary_choice(*, player_id: str) -> SecondaryMissionChoice:
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=SecondaryMissionMode.FIXED,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()


def _place_murdercall_units(state: GameState) -> None:
    _place_unit_poses(
        state,
        unit_instance_id=_ENEMY_UNIT_ID,
        poses=_unit_line_poses(x=20.0, y=20.0),
    )
    _place_unit_poses(
        state,
        unit_instance_id=_BLOOD_UNIT_ID,
        poses=_unit_line_poses(x=30.0, y=20.0),
    )


def _place_blood_tainted_units_on_center_objective(state: GameState) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    marker = center_marker_definition(state)
    blood = state.battlefield_state.unit_placement_by_id(_BLOOD_UNIT_ID)
    enemy = state.battlefield_state.unit_placement_by_id(_ENEMY_UNIT_ID)
    battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            blood,
            marker,
            offsets=((0.0, 0.0), (1.5, 0.0), (0.0, 1.5), (1.5, 1.5), (-1.5, 0.0)),
        )
    )
    battlefield_state = battlefield_state.with_unit_placement(
        with_model_offsets(
            enemy,
            marker,
            offsets=((2.5, 0.0), (2.5, 1.5), (2.5, -1.5), (4.0, 0.0), (4.0, 1.5)),
        )
    )
    state.replace_battlefield_state(battlefield_state)


def _place_unit_poses(
    state: GameState,
    *,
    unit_instance_id: str,
    poses: tuple[Pose, ...],
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(_with_model_poses(placement, poses=poses))
    )


def _unit_line_poses(*, x: float, y: float) -> tuple[Pose, ...]:
    return tuple(Pose.at(x, y + index * 1.8) for index in range(5))


def _with_model_poses(
    unit_placement: UnitPlacement,
    *,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    if len(poses) != len(unit_placement.model_placements):
        raise AssertionError("test pose fixture must match unit model count")
    return UnitPlacement(
        army_id=unit_placement.army_id,
        player_id=unit_placement.player_id,
        unit_instance_id=unit_placement.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=placement.army_id,
                player_id=placement.player_id,
                unit_instance_id=placement.unit_instance_id,
                model_instance_id=placement.model_instance_id,
                pose=pose,
            )
            for placement, pose in zip(unit_placement.model_placements, poses, strict=True)
        ),
    )


def _submit_surge_proposal(
    *,
    lifecycle: GameLifecycle,
    request: DecisionRequest,
    result_id: str,
    unit_instance_id: str,
    witness: PathWitness,
) -> LifecycleStatus:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    return lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            result_id=result_id,
            payload=validate_json_value(
                MovementProposalPayload(
                    proposal_request_id=proposal_request.request_id,
                    proposal_kind=proposal_request.proposal_kind,
                    unit_instance_id=unit_instance_id,
                    movement_phase_action="surge_move",
                    witness=witness,
                ).to_payload()
            ),
        ).to_result(request)
    )


def _emit_objective_proximity_snapshot(
    *,
    state: GameState,
    decisions: DecisionController,
    phase: BattlePhase,
    ruleset_descriptor: RulesetDescriptor,
) -> dict[str, JsonValue]:
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise AssertionError("test state requires active_player_id")
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=phase,
            ruleset_descriptor=ruleset_descriptor,
        )
    )
    objective_ids_by_unit: dict[str, set[str]] = {}
    for result in record.results:
        for contribution in result.contributors:
            objective_ids_by_unit.setdefault(contribution.unit_instance_id, set()).add(
                result.objective_id
            )
    payload = {
        "snapshot_id": (
            f"objective-proximity:{state.game_id}:round-{state.battle_round:02d}:"
            f"turn:{active_player_id}:phase:{phase.value}:start"
        ),
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": active_player_id,
        "phase": phase.value,
        "objective_ids_by_unit_instance_id": {
            unit_id: sorted(objective_ids)
            for unit_id, objective_ids in sorted(objective_ids_by_unit.items())
        },
        "removed_model_ids": sorted(state.battlefield_state.removed_model_ids),
        "source_objective_control_record": record.to_payload(),
    }
    decisions.event_log.append("objective_marker_phase_start_proximity_snapshot", payload)
    return cast(dict[str, JsonValue], validate_json_value(payload))


def _single_objective_id_for_unit(
    snapshot_payload: dict[str, JsonValue],
    unit_instance_id: str,
) -> str:
    mapping = cast(dict[str, JsonValue], snapshot_payload["objective_ids_by_unit_instance_id"])
    raw_objective_ids = mapping[unit_instance_id]
    if not isinstance(raw_objective_ids, list) or len(raw_objective_ids) != 1:
        raise AssertionError("expected one objective in range for unit")
    objective_id = raw_objective_ids[0]
    if type(objective_id) is not str:
        raise AssertionError("objective id must be a string")
    return objective_id


def _destroy_enemy_unit_for_blood_tainted(
    *,
    state: GameState,
    decisions: DecisionController,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    phase = state.current_battle_phase
    if phase is None:
        raise AssertionError("test state requires current battle phase")
    enemy_army = state.army_definition_for_player("player-b")
    if enemy_army is None:
        raise AssertionError("test state requires player-b army")
    enemy_unit = enemy_army.unit_by_id(_ENEMY_UNIT_ID)
    destroyed_model_ids = tuple(model.model_instance_id for model in enemy_unit.own_models)
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(destroyed_model_ids)
    )
    for index, model_id in enumerate(destroyed_model_ids, start=1):
        decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": phase.value,
                "destroying_player_id": "player-a",
                "attacking_unit_instance_id": _BLOOD_UNIT_ID,
                "target_unit_instance_id": _ENEMY_UNIT_ID,
                "model_instance_id": model_id,
                "damage_kind": "normal",
                "damage_event_id": f"phase17g-blood-tainted-damage-{index:02d}",
                "destroyed_model_rules_triggered": True,
            },
        )


def _destroy_enemy_unit_with_split_attackers_for_blood_tainted(
    *,
    state: GameState,
    decisions: DecisionController,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    phase = state.current_battle_phase
    if phase is None:
        raise AssertionError("test state requires current battle phase")
    enemy_army = state.army_definition_for_player("player-b")
    if enemy_army is None:
        raise AssertionError("test state requires player-b army")
    enemy_unit = enemy_army.unit_by_id(_ENEMY_UNIT_ID)
    destroyed_model_ids = tuple(model.model_instance_id for model in enemy_unit.own_models)
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(destroyed_model_ids)
    )
    for index, model_id in enumerate(destroyed_model_ids, start=1):
        attacker_id = _BLOOD_UNIT_ID if index == 1 else _OTHER_FRIENDLY_UNIT_ID
        decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": phase.value,
                "destroying_player_id": "player-a",
                "attacking_unit_instance_id": attacker_id,
                "target_unit_instance_id": _ENEMY_UNIT_ID,
                "model_instance_id": model_id,
                "damage_kind": "normal",
                "damage_event_id": f"phase17g-blood-tainted-split-damage-{index:02d}",
                "destroyed_model_rules_triggered": True,
            },
        )


def _event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, JsonValue]:
    for event in decisions.event_log.records:
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")
