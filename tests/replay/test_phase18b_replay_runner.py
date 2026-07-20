from __future__ import annotations

# pyright: reportPrivateUsage=false
import json
import re
from dataclasses import replace
from typing import cast

import pytest
from tests.deployment_submission_helpers import submit_all_deployments_if_pending

from warhammer40k_core.adapters.contracts import FiniteOptionSubmission, ParameterizedSubmission
from warhammer40k_core.adapters.projection import (
    GameViewPayload,
    _projection_state_hash,
    project_game_view,
)
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.decision_record import DecisionRecord, DecisionRecordPayload
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.fight_resolution import PILE_IN_ACTION, FightMovementProposal
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.charge import (
    CHARGE_MOVE_ACTION,
    SELECT_CHARGING_UNIT_DECISION_TYPE,
    ChargeMoveProposal,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import (
    COMPLETE_SHOOTING_PHASE_OPTION_ID,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.replay import (
    REPLAY_ARTIFACT_SCHEMA_VERSION,
    ReplayArtifact,
    ReplayArtifactError,
    ReplayArtifactPayload,
    ReplayDiagnosticCode,
    ReplayProjectionCheckpoint,
    ReplayProjectionSnapshot,
    ReplayRunner,
    ReplayRunStatus,
    ReplayTraceExporter,
    decision_request_options_fingerprint,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import tacoma_open_2026

pytestmark = pytest.mark.replay

MEMORY_REPR_PATTERN = re.compile(r"<[^>\n]+ object at 0x[0-9a-fA-F]+>")
FORBIDDEN_UI_STATE_KEYS = frozenset(
    {
        "ui_state",
        "dom_state",
        "component_state",
        "render_state",
        "adapter_state",
    }
)


def test_setup_to_battle_replay_reproduces_exactly() -> None:
    artifact = _setup_to_battle_artifact()
    payload = _artifact_payload_copy(artifact)
    round_tripped = ReplayArtifact.from_payload(payload)

    result = ReplayRunner(
        artifact=round_tripped,
        projection_provider=_projection_provider,
    ).run()

    assert result.status is ReplayRunStatus.REPRODUCED
    assert result.reproduced_exactly
    assert result.reproduced_decision_count == len(artifact.decision_records)
    assert result.final_event_log_hash == artifact.projection_checkpoints[-1].event_log_hash
    assert payload["source_identity"]["game_id"] == "phase18b-setup-golden"
    assert payload["initial_rng_state"]["seed"] == "phase18b-setup-golden"
    assert payload["initial_lifecycle"]["state"] is not None
    assert payload["decision_records"]
    assert payload["event_records"]
    assert payload["projection_checkpoints"]
    assert payload["schema_version"] == REPLAY_ARTIFACT_SCHEMA_VERSION
    assert REPLAY_ARTIFACT_SCHEMA_VERSION == "replay-artifact-v2-phase18i"


def test_replay_source_identity_verifies_active_rules_overlay() -> None:
    config = _setup_config(game_id="phase18b-tacoma-overlay")
    descriptor = tacoma_open_2026.apply_rules_overlay(config.ruleset_descriptor)
    lifecycle = GameLifecycle()
    lifecycle.start(replace(config, ruleset_descriptor=descriptor))
    initial_payload = _lifecycle_payload_copy(lifecycle)
    artifact = ReplayArtifact.capture(
        artifact_id="phase18b-tacoma-overlay",
        initial_lifecycle_payload=initial_payload,
        final_lifecycle=lifecycle,
    )

    payload = _artifact_payload_copy(artifact)
    assert payload["source_identity"]["ruleset_descriptor_hash"] == descriptor.descriptor_hash
    assert payload["source_identity"]["rules_overlay_ids"] == [tacoma_open_2026.RULES_OVERLAY_ID]
    assert ReplayArtifact.from_payload(payload) == artifact

    payload["source_identity"]["rules_overlay_ids"] = []
    with pytest.raises(ReplayArtifactError, match="source identity drifted from snapshot"):
        ReplayArtifact.from_payload(payload)


@pytest.mark.parametrize("field_name", ["seed", "history", "draw_count"])
def test_replay_artifact_rejects_initial_rng_state_drift(field_name: str) -> None:
    artifact = _setup_to_battle_artifact()
    payload = _artifact_payload_copy(artifact)
    rng_state = payload["initial_rng_state"]
    if field_name == "seed":
        rng_state["seed"] = "phase18b-drifted-seed"
    elif field_name == "history":
        rng_state["history"].append("phase18b-drifted-history-token")
    elif field_name == "draw_count":
        rng_state["draw_count"] += 1
    else:
        raise AssertionError(f"Unhandled RNG drift field: {field_name}")

    with pytest.raises(ReplayArtifactError, match="initial_rng_state drifted from snapshot"):
        ReplayArtifact.from_payload(payload)


def test_movement_shooting_charge_fight_replay_reproduces_exactly() -> None:
    artifact = _movement_shooting_charge_fight_artifact()

    result = ReplayRunner(
        artifact=artifact,
        projection_provider=_projection_provider,
    ).run()

    assert result.status is ReplayRunStatus.REPRODUCED
    assert result.reproduced_decision_count == len(artifact.decision_records)
    assert any(event.event_type == "charge_move_completed" for event in artifact.event_records)
    assert any(event.event_type == "fight_movement_requested" for event in artifact.event_records)
    assert any(event.event_type == "fight_movement_completed" for event in artifact.event_records)


def test_replay_with_deliberately_stale_request_id_fails_with_typed_diagnostics() -> None:
    artifact = _setup_to_battle_artifact()
    payload = _artifact_payload_copy(artifact)
    first_record = payload["decision_records"][0]
    first_record["request"]["request_id"] = "phase18b-stale-request-id"
    first_record["result"]["request_id"] = "phase18b-stale-request-id"
    drifted_artifact = ReplayArtifact.from_payload(payload)

    result = ReplayRunner(
        artifact=drifted_artifact,
        projection_provider=_projection_provider,
    ).run()

    assert result.status is ReplayRunStatus.DRIFTED
    assert result.reproduced_decision_count == 0
    assert result.diagnostics[0].diagnostic_code is ReplayDiagnosticCode.REQUEST_ID_DRIFT
    assert result.diagnostics[0].expected == {"request_id": "phase18b-stale-request-id"}


def test_replay_with_changed_legal_option_fingerprint_fails_with_drift_diagnostics() -> None:
    artifact = _setup_to_battle_artifact()
    payload = _artifact_payload_copy(artifact)
    first_record = payload["decision_records"][0]
    selected_option_id = first_record["result"]["selected_option_id"]
    expected_fingerprint = decision_request_options_fingerprint(
        artifact.decision_records[0].request
    )
    _mutate_unselected_option_label(
        first_record,
        selected_option_id=selected_option_id,
    )
    drifted_artifact = ReplayArtifact.from_payload(payload)

    result = ReplayRunner(
        artifact=drifted_artifact,
        projection_provider=_projection_provider,
    ).run()

    assert result.status is ReplayRunStatus.DRIFTED
    assert result.reproduced_decision_count == 0
    assert (
        result.diagnostics[0].diagnostic_code is ReplayDiagnosticCode.LEGAL_OPTION_FINGERPRINT_DRIFT
    )
    assert result.diagnostics[0].actual == {"legal_option_fingerprint": expected_fingerprint}


def test_trace_exporter_exports_json_safe_decision_corpus_without_ui_state() -> None:
    artifact = _movement_shooting_charge_fight_artifact()
    result = ReplayRunner(
        artifact=artifact,
        projection_provider=_projection_provider,
    ).run()
    exporter = ReplayTraceExporter()

    timeline = exporter.human_readable_timeline(artifact)
    jsonl = exporter.decision_records_jsonl(artifact)
    triage_payload = exporter.failure_triage_payload(artifact=artifact, result=result)
    triage_text = canonical_json(triage_payload)

    assert "Decision " in timeline
    assert "Event " in timeline
    assert MEMORY_REPR_PATTERN.search(timeline) is None
    assert MEMORY_REPR_PATTERN.search(jsonl) is None
    assert MEMORY_REPR_PATTERN.search(triage_text) is None
    _assert_no_ui_owned_state(validate_json_value(artifact.to_payload()))
    _assert_no_ui_owned_state(triage_payload)

    lines = [line for line in jsonl.splitlines() if line]
    assert len(lines) == len(artifact.decision_records)
    for line in lines:
        payload = cast(DecisionRecordPayload, json.loads(line))
        assert DecisionRecord.from_payload(payload).to_payload() == payload
        _assert_no_ui_owned_state(validate_json_value(payload))


def _setup_to_battle_artifact() -> ReplayArtifact:
    game_id = "phase18b-setup-golden"
    lifecycle = GameLifecycle()
    lifecycle.start(_setup_config(game_id=game_id))
    status = lifecycle.advance_until_decision_or_terminal()
    initial_payload = _lifecycle_payload_copy(lifecycle)
    status = _drive_setup_to_battle(lifecycle=lifecycle, status=status, game_id=game_id)
    _assert_decision_request(status, SELECT_MOVEMENT_UNIT_DECISION_TYPE)
    return ReplayArtifact.capture(
        artifact_id="phase18b-setup-to-battle",
        initial_lifecycle_payload=initial_payload,
        final_lifecycle=lifecycle,
        projection_checkpoints=(
            _projection_checkpoint(
                lifecycle,
                checkpoint_id="phase18b-setup-battle-start",
                decision_record_index=len(lifecycle.decision_controller.records),
            ),
        ),
    )


def _movement_shooting_charge_fight_artifact() -> ReplayArtifact:
    game_id = "probe-fight"
    lifecycle, units = _movement_phase_lifecycle(game_id=game_id)
    status = lifecycle.advance_until_decision_or_terminal()
    initial_payload = _lifecycle_payload_copy(lifecycle)
    initial_checkpoint = _projection_checkpoint(
        lifecycle,
        checkpoint_id="phase18b-combat-movement-start",
        decision_record_index=0,
    )

    status = _drive_movement_shooting_charge_fight(
        lifecycle=lifecycle,
        status=status,
        units=units,
        game_id=game_id,
    )
    next_fight_request = _assert_decision_request(status, MOVEMENT_PROPOSAL_DECISION_TYPE)
    next_fight_proposal = MovementProposalRequest.from_decision_request_payload(
        next_fight_request.payload
    )
    state = _state(lifecycle)
    assert state.current_battle_phase is BattlePhase.FIGHT
    assert next_fight_proposal.proposal_kind is ProposalKind.PILE_IN
    assert next_fight_proposal.unit_instance_id == units["target"].unit_instance_id
    assert any(
        event.event_type == "fight_movement_completed"
        for event in lifecycle.decision_controller.event_log.records
    )
    return ReplayArtifact.capture(
        artifact_id="phase18b-movement-shooting-charge-fight",
        initial_lifecycle_payload=initial_payload,
        final_lifecycle=lifecycle,
        projection_checkpoints=(
            initial_checkpoint,
            _projection_checkpoint(
                lifecycle,
                checkpoint_id="phase18b-combat-pile-in-completed",
                decision_record_index=len(lifecycle.decision_controller.records),
            ),
        ),
    )


def _drive_setup_to_battle(
    *,
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    game_id: str,
) -> LifecycleStatus:
    first_request = _assert_decision_request(status, SECONDARY_MISSION_DECISION_TYPE)
    status = _submit_option(
        lifecycle=lifecycle,
        request=first_request,
        option_id="fixed:assassination:bring_it_down",
        result_id=f"{game_id}-secondary-a",
    )
    second_request = _assert_decision_request(status, SECONDARY_MISSION_DECISION_TYPE)
    status = _submit_option(
        lifecycle=lifecycle,
        request=second_request,
        option_id="fixed:assassination:bring_it_down",
        result_id=f"{game_id}-secondary-b",
    )
    return submit_all_deployments_if_pending(
        lifecycle,
        status,
        result_id_prefix=f"{game_id}-deploy",
    )


def _drive_movement_shooting_charge_fight(
    *,
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    units: dict[str, UnitInstance],
    game_id: str,
) -> LifecycleStatus:
    attacker_unit_id = units["attacker"].unit_instance_id
    target_unit_id = units["target"].unit_instance_id
    movement_request = _assert_decision_request(status, SELECT_MOVEMENT_UNIT_DECISION_TYPE)
    status = _submit_option(
        lifecycle=lifecycle,
        request=movement_request,
        option_id=attacker_unit_id,
        result_id=f"{game_id}-select-movement-unit",
    )
    action_request = _assert_decision_request(status, SELECT_MOVEMENT_ACTION_DECISION_TYPE)
    status = _submit_option(
        lifecycle=lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.REMAIN_STATIONARY.value,
        result_id=f"{game_id}-remain-stationary",
    )
    status = _decline_optional_stratagem_if_pending(
        lifecycle=lifecycle,
        status=status,
        result_id=f"{game_id}-decline-overwatch",
    )
    shooting_request = _assert_decision_request(status, SELECT_SHOOTING_UNIT_DECISION_TYPE)
    status = _submit_option(
        lifecycle=lifecycle,
        request=shooting_request,
        option_id=COMPLETE_SHOOTING_PHASE_OPTION_ID,
        result_id=f"{game_id}-complete-shooting",
    )
    charge_request = _assert_decision_request(status, SELECT_CHARGING_UNIT_DECISION_TYPE)
    status = _submit_option(
        lifecycle=lifecycle,
        request=charge_request,
        option_id=attacker_unit_id,
        result_id=f"{game_id}-select-charging-unit",
    )
    proposal_request = _assert_decision_request(status, MOVEMENT_PROPOSAL_DECISION_TYPE)
    charge_proposal = MovementProposalRequest.from_decision_request_payload(
        proposal_request.payload
    )
    assert charge_proposal.proposal_kind is ProposalKind.CHARGE_MOVE
    assert charge_proposal.unit_instance_id == attacker_unit_id
    status = _submit_parameterized(
        lifecycle=lifecycle,
        request=proposal_request,
        payload=validate_json_value(
            ChargeMoveProposal(
                proposal_request_id=charge_proposal.request_id,
                proposal_kind=charge_proposal.proposal_kind,
                unit_instance_id=charge_proposal.unit_instance_id,
                movement_phase_action=CHARGE_MOVE_ACTION,
                movement_mode=MovementMode.CHARGE,
                charge_target_unit_instance_ids=(target_unit_id,),
                witness=_straight_line_witness_for_unit(
                    lifecycle,
                    unit_instance_id=attacker_unit_id,
                    dx=2.0,
                ),
            ).to_payload()
        ),
        result_id=f"{game_id}-submit-charge-move",
    )
    pile_in_request = _assert_decision_request(status, MOVEMENT_PROPOSAL_DECISION_TYPE)
    pile_in_proposal = MovementProposalRequest.from_decision_request_payload(
        pile_in_request.payload
    )
    assert pile_in_proposal.proposal_kind is ProposalKind.PILE_IN
    assert pile_in_proposal.unit_instance_id == attacker_unit_id
    return _submit_parameterized(
        lifecycle=lifecycle,
        request=pile_in_request,
        payload=validate_json_value(
            FightMovementProposal(
                proposal_request_id=pile_in_proposal.request_id,
                proposal_kind=ProposalKind.PILE_IN,
                unit_instance_id=pile_in_proposal.unit_instance_id,
                movement_phase_action=PILE_IN_ACTION,
                movement_mode=MovementMode.PILE_IN,
                pile_in_target_unit_instance_ids=(target_unit_id,),
                witness=_straight_line_witness_for_unit(
                    lifecycle,
                    unit_instance_id=attacker_unit_id,
                    dx=0.1,
                ),
            ).to_payload()
        ),
        result_id=f"{game_id}-submit-pile-in",
    )


def _decline_optional_stratagem_if_pending(
    *,
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    result_id: str,
) -> LifecycleStatus:
    request = _decision_request(status)
    if request.decision_type != STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        return status
    return _submit_parameterized(
        lifecycle=lifecycle,
        request=request,
        payload=stratagem_decline_payload(),
        result_id=result_id,
    )


def _projection_checkpoint(
    lifecycle: GameLifecycle,
    *,
    checkpoint_id: str,
    decision_record_index: int,
) -> ReplayProjectionCheckpoint:
    view = _game_view(lifecycle, viewer_player_id="player-a")
    pending_decision = view["pending_decision"]
    assert pending_decision is not None
    assert pending_decision["interaction"] is not None
    assert _projection_state_hash(view) == view["projection_state_hash"]
    return ReplayProjectionCheckpoint.from_lifecycle(
        lifecycle=lifecycle,
        checkpoint_id=checkpoint_id,
        decision_record_index=decision_record_index,
        viewer_player_id="player-a",
        projection_schema=view["projection_schema"],
        projection_state_hash=view["projection_state_hash"],
    )


def _projection_provider(
    lifecycle: GameLifecycle,
    checkpoint: ReplayProjectionCheckpoint,
) -> ReplayProjectionSnapshot:
    view = _game_view(lifecycle, viewer_player_id=checkpoint.viewer_player_id)
    return ReplayProjectionSnapshot(
        viewer_player_id=checkpoint.viewer_player_id,
        projection_schema=view["projection_schema"],
        projection_state_hash=view["projection_state_hash"],
    )


def _game_view(lifecycle: GameLifecycle, *, viewer_player_id: str) -> GameViewPayload:
    return project_game_view(lifecycle=lifecycle, viewer_player_id=viewer_player_id)


def _movement_phase_lifecycle(
    *,
    game_id: str,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    config = _combat_config(game_id=game_id)
    armies = _mustered_armies(config)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=f"{game_id}-battlefield",
        battlefield_width_inches=100.0,
        battlefield_depth_inches=100.0,
        armies=armies,
    )
    units = {
        unit.unit_instance_id.split(":", maxsplit=1)[1]: unit
        for army in armies
        for unit in army.units
    }
    battlefield = scenario.battlefield_state
    battlefield = battlefield.with_unit_placement(
        _unit_placement_at(
            units["attacker"],
            army_id="army-alpha",
            player_id="player-a",
            poses=_compact_test_unit_poses(
                origin=Pose.at(10.0, 20.0, facing_degrees=0.0),
                model_count=len(units["attacker"].own_models),
            ),
        )
    )
    battlefield = battlefield.with_unit_placement(
        _unit_placement_at(
            units["target"],
            army_id="army-beta",
            player_id="player-b",
            poses=_compact_test_unit_poses(
                origin=Pose.at(19.0, 20.0, facing_degrees=180.0),
                model_count=len(units["target"].own_models),
            ),
        )
    )
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
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": GameLifecycle().decision_controller.to_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    return GameLifecycle.from_payload(payload), units


def _setup_config(*, game_id: str) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase18b-setup-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-2",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def _combat_config(*, game_id: str) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase18b-combat-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("attacker",),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("target",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_open_mission_setup(),
    )


def _open_mission_setup() -> MissionSetup:
    mission_pack = chapter_approved_2026_27_mission_pack()
    return MissionSetup(
        mission_pack_id=mission_pack.mission_pack_id,
        source_version=mission_pack.source_version,
        source_id=mission_pack.source_id,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        primary_mission_id="take-and-hold",
        battlefield_layout_id=None,
        deployment_map_id="phase18b-open-map",
        terrain_layout_id="phase18b-open-layout",
        attacker_player_id="player-a",
        defender_player_id="player-b",
        battlefield_width_inches=100.0,
        battlefield_depth_inches=100.0,
        objective_markers=(
            ObjectiveMarkerDefinition(
                objective_marker_id="phase18b-remote-objective",
                name="Phase 18B Remote Objective",
                objective_role=ObjectiveMarkerRole.CENTRAL,
                x_inches=95.0,
                y_inches=95.0,
                source_id="phase18b-test",
            ),
        ),
        deployment_zones=(),
        battlefield_regions=(),
        terrain_areas=(),
        terrain_features=(),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
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
        unit_selections=tuple(_unit_selection(unit_id) for unit_id in unit_selection_ids),
    )


def _unit_selection(unit_selection_id: str) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-intercessor-like-infantry",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _compact_test_unit_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
    return tuple(
        Pose.at(
            origin.position.x + ((index % 5) * 1.4),
            origin.position.y + ((index // 5) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(model_count)
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


def _straight_line_witness_for_unit(
    lifecycle: GameLifecycle,
    *,
    unit_instance_id: str,
    dx: float,
    dy: float = 0.0,
) -> PathWitness:
    state = _state(lifecycle)
    if state.battlefield_state is None:
        raise GameLifecycleError("Charge Move witness helper requires battlefield_state.")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        midpoint = Pose.at(
            start.position.x + (dx / 2.0),
            start.position.y + (dy / 2.0),
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        end = Pose.at(
            start.position.x + dx,
            start.position.y + dy,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _submit_option(
    *,
    lifecycle: GameLifecycle,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=request.request_id,
            selected_option_id=option_id,
            result_id=result_id,
        ).to_result(request)
    )


def _submit_parameterized(
    *,
    lifecycle: GameLifecycle,
    request: DecisionRequest,
    payload: JsonValue,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=request.request_id,
            payload=payload,
            result_id=result_id,
        ).to_result(request)
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _assert_decision_request(status: LifecycleStatus, decision_type: str) -> DecisionRequest:
    request = _decision_request(status)
    assert request.decision_type == decision_type
    return request


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    return lifecycle.state


def _lifecycle_payload_copy(lifecycle: GameLifecycle) -> GameLifecyclePayload:
    return cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )


def _artifact_payload_copy(artifact: ReplayArtifact) -> ReplayArtifactPayload:
    return cast(
        ReplayArtifactPayload,
        json.loads(json.dumps(artifact.to_payload(), sort_keys=True)),
    )


def _mutate_unselected_option_label(
    record_payload: DecisionRecordPayload,
    *,
    selected_option_id: str,
) -> None:
    for option_payload in record_payload["request"]["options"]:
        if option_payload["option_id"] == selected_option_id:
            continue
        option_payload["label"] = f"{option_payload['label']} drifted"
        return
    raise AssertionError("Expected at least one unselected option to mutate.")


def _assert_no_ui_owned_state(value: JsonValue) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_UI_STATE_KEYS.intersection(value.keys())
        assert not forbidden
        for nested in value.values():
            _assert_no_ui_owned_state(nested)
        return
    if isinstance(value, list):
        for nested in value:
            _assert_no_ui_owned_state(nested)
