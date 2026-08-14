from __future__ import annotations

# pyright: reportPrivateUsage=false
import hashlib
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
from warhammer40k_core.engine.attached_unit_reconciliation import (
    split_attached_rules_unit_if_required,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_model_materialization_runtime import (
    CATALOG_MODELS_MATERIALIZED_EVENT,
)
from warhammer40k_core.engine.decision_record import DecisionRecord, DecisionRecordPayload
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
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
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import (
    MissionSetup,
    PlayerPrimaryMissionAssignment,
)
from warhammer40k_core.engine.missions import (
    mission_scoring_policies_from_setup,
    reserve_destruction_policy_from_scoring_policy,
)
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
from warhammer40k_core.engine.primary_battlefield_departure import (
    primary_battlefield_departure_id,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
    RulesUnitObjectiveProximityWitness,
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_battlefield_departure_events,
    record_new_primary_turn_start_evidence_events,
    record_new_primary_unit_destruction_events,
    record_primary_unit_destruction_event,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    record_primary_turn_start_evidence,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    primary_unit_destruction_id,
    record_primary_destroyed_model_departures,
    record_primary_unit_destructions_for_destroyed_models,
)
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
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState
from warhammer40k_core.engine.setup_flow import (
    SECONDARY_MISSION_DECISION_TYPE,
    army_mustered_event_payload,
)
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
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.terrain_factory import TerrainFactory
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
    warhammer_event_companion_2026_07_mission_pack,
)
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
    assert REPLAY_ARTIFACT_SCHEMA_VERSION == "replay-artifact-v6-phase17n-step3"


def test_replay_source_identity_binds_canonical_mission_package_hash() -> None:
    artifact = _setup_to_battle_artifact()
    payload = _artifact_payload_copy(artifact)
    mission_pack = chapter_approved_2026_27_mission_pack()
    source_identity = payload["source_identity"]

    assert source_identity["mission_pack_id"] == mission_pack.mission_pack_id
    assert (
        source_identity["mission_source_package_hash"]
        == mission_pack.source_package.source_commit_or_import_hash
    )

    source_identity["mission_source_package_hash"] = "f" * 64
    if mission_pack.source_package.source_commit_or_import_hash == "f" * 64:
        source_identity["mission_source_package_hash"] = "e" * 64
    with pytest.raises(ReplayArtifactError, match="source identity drifted from snapshot"):
        ReplayArtifact.from_payload(payload)


def test_replay_source_identity_binds_late_bound_layoutless_mission_package() -> None:
    config = replace(
        _combat_config(game_id="phase18b-late-bound-replay-source"), mission_setup=None
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _state(lifecycle)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    state.record_mission_setup(_open_mission_setup())
    artifact = ReplayArtifact.capture(
        artifact_id="phase18b-late-bound-replay-source",
        initial_lifecycle_payload=_lifecycle_payload_copy(lifecycle),
        final_lifecycle=lifecycle,
    )
    mission_pack = warhammer_event_companion_2026_07_mission_pack()

    assert artifact.source_identity.mission_pack_id == mission_pack.mission_pack_id
    assert (
        artifact.source_identity.mission_source_package_hash
        == mission_pack.source_package.source_commit_or_import_hash
    )
    assert ReplayArtifact.from_payload(_artifact_payload_copy(artifact)) == artifact


def test_legacy_replay_versions_are_rejected_without_shape_inference() -> None:
    for legacy_schema_version in (
        "replay-artifact-v2-phase18i",
        "replay-artifact-v3-phase17n",
        "replay-artifact-v4-phase17n",
        "replay-artifact-v5-phase17n",
    ):
        legacy_payload = _artifact_payload_copy(_setup_to_battle_artifact())
        legacy_payload["schema_version"] = legacy_schema_version
        legacy_lifecycle = cast(dict[str, JsonValue], legacy_payload["initial_lifecycle"])
        legacy_lifecycle["state"] = None

        with pytest.raises(ReplayArtifactError, match="schema_version is unsupported"):
            ReplayArtifact.from_payload(legacy_payload)


def test_replay_v6_missing_phase17n_rules_unit_snapshot_fails_with_typed_error() -> None:
    payload = _artifact_payload_copy(_setup_to_battle_artifact())
    state = cast(dict[str, JsonValue], payload["initial_lifecycle"]["state"])
    state.pop("primary_rules_unit_turn_start_snapshots")

    with pytest.raises(
        ReplayArtifactError,
        match="missing required field: primary_rules_unit_turn_start_snapshots",
    ):
        ReplayArtifact.from_payload(payload)


def test_replay_v6_rejects_invented_primary_destruction_event_reference() -> None:
    payload = _populated_primary_destruction_replay_payload()
    destruction = _primary_destruction_payload(payload)
    destruction["source_model_destroyed_event_id"] = "event-999999"

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "no authoritative model_destroyed event" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_primary_destruction_source_witness_drift() -> None:
    payload = _populated_primary_destruction_replay_payload()
    destruction = _primary_destruction_payload(payload)
    attribution = cast(dict[str, JsonValue], destruction["destruction_attribution"])
    source_model_id = cast(str, attribution["source_model_instance_id"])
    source_witness = cast(
        dict[str, JsonValue],
        destruction["source_rules_unit_objective_proximity_witness"],
    )
    source_witness["objective_marker_witnesses"] = [
        {
            "objective_marker_id": "phase18b-remote-objective",
            "model_instance_ids": [source_model_id],
        }
    ]

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "source witness drifted" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_known_turn_start_objective_control_drift() -> None:
    payload = _populated_primary_destruction_replay_payload()
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    turn_start_states = cast(list[JsonValue], state_payload["primary_objective_turn_start_states"])
    assert len(turn_start_states) == 1
    turn_start_state = cast(dict[str, JsonValue], turn_start_states[0])
    mission_setup = cast(dict[str, JsonValue], state_payload["mission_setup"])
    objective_markers = cast(list[JsonValue], mission_setup["objective_markers"])
    known_objective_id = cast(
        str, cast(dict[str, JsonValue], objective_markers[0])["objective_marker_id"]
    )
    turn_start_state["controlled_objective_ids"] = [known_objective_id]

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "controlled objectives drifted" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_known_turn_start_position_witness_drift() -> None:
    payload = _populated_primary_destruction_replay_payload()
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    snapshots = cast(list[JsonValue], state_payload["primary_rules_unit_turn_start_snapshots"])
    assert len(snapshots) == 1
    snapshot = cast(dict[str, JsonValue], snapshots[0])
    memberships = cast(list[JsonValue], snapshot["rules_unit_memberships"])
    membership = cast(dict[str, JsonValue], memberships[0])
    components = cast(list[JsonValue], membership["component_memberships"])
    component = cast(dict[str, JsonValue], components[0])
    evaluated_model_ids = cast(list[JsonValue], component["evaluated_model_instance_ids"])
    assert evaluated_model_ids
    mission_setup = cast(dict[str, JsonValue], state_payload["mission_setup"])
    objective_markers = cast(list[JsonValue], mission_setup["objective_markers"])
    known_objective_id = cast(
        str, cast(dict[str, JsonValue], objective_markers[0])["objective_marker_id"]
    )
    component["objective_marker_witnesses"] = [
        {
            "objective_marker_id": known_objective_id,
            "model_instance_ids": [cast(str, evaluated_model_ids[0])],
        }
    ]

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "turn-start recorded-event payload drift" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_missing_destroyed_battlefield_departure() -> None:
    payload = _populated_primary_destruction_replay_payload()
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    departures = cast(list[JsonValue], state_payload["primary_battlefield_departure_states"])
    assert len(departures) == 5
    removed_departure = cast(dict[str, JsonValue], departures.pop(0))
    decisions_payload = cast(dict[str, JsonValue], lifecycle_payload["decisions"])
    events = cast(list[JsonValue], decisions_payload["event_log"])
    departure_event = next(
        cast(dict[str, JsonValue], event)
        for event in events
        if cast(dict[str, JsonValue], event)["event_type"]
        == "primary_battlefield_departure_recorded"
        and cast(
            dict[str, JsonValue],
            cast(dict[str, JsonValue], event)["payload"],
        )["primary_battlefield_departure_state"]
        == removed_departure
    )
    departure_event["event_type"] = "phase18b_removed_departure_audit_placeholder"

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "lacks its exact battlefield departure" in str(exc_info.value.__cause__)


@pytest.mark.parametrize(
    "forged_removal_kind",
    [
        BattlefieldRemovalKind.EMBARK,
        BattlefieldRemovalKind.INTO_RESERVES,
        BattlefieldRemovalKind.TEMPORARILY_REMOVED,
    ],
)
def test_replay_v6_rejects_cloned_non_destruction_departure_and_derived_event(
    forged_removal_kind: BattlefieldRemovalKind,
) -> None:
    lifecycle, units = _movement_phase_lifecycle(
        game_id=f"phase18b-invented-{forged_removal_kind.value}-departure"
    )
    state = _state(lifecycle)
    state.reposition_unit_to_strategic_reserves(
        event_log=lifecycle.decision_controller.event_log,
        player_id="player-b",
        unit_instance_id=units["target"].unit_instance_id,
    )
    payload = _lifecycle_payload_copy(lifecycle)
    assert (
        GameLifecycle.from_payload(
            cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
        ).to_payload()
        == lifecycle.to_payload()
    )
    state_payload = cast(dict[str, JsonValue], payload["state"])
    departures = cast(list[JsonValue], state_payload["primary_battlefield_departure_states"])
    assert len(departures) == 1
    forged = cast(dict[str, JsonValue], json.loads(json.dumps(departures[0])))
    forged_source_id = f"phase18b:invented:{forged_removal_kind.value}"
    forged["source_id"] = forged_source_id
    forged["removal_kind"] = forged_removal_kind.value
    forged["departure_id"] = primary_battlefield_departure_id(
        game_id=cast(str, forged["game_id"]),
        rules_unit_instance_id=cast(str, forged["rules_unit_instance_id"]),
        affected_component_unit_instance_ids=tuple(
            cast(list[str], forged["affected_component_unit_instance_ids"])
        ),
        departed_component_unit_instance_ids=tuple(
            cast(list[str], forged["departed_component_unit_instance_ids"])
        ),
        removed_model_instance_ids=tuple(cast(list[str], forged["removed_model_instance_ids"])),
        battle_round=cast(int, forged["battle_round"]),
        active_player_id=cast(str, forged["active_player_id"]),
        phase=cast(str, forged["phase"]),
        removal_kind=forged_removal_kind,
        occurrence_id=cast(str, forged["occurrence_id"]),
        source_id=forged_source_id,
    )
    departures.append(forged)
    decisions_payload = cast(dict[str, JsonValue], payload["decisions"])
    events = cast(list[JsonValue], decisions_payload["event_log"])
    original_derived_event = next(
        cast(dict[str, JsonValue], event)
        for event in events
        if cast(dict[str, JsonValue], event)["event_type"]
        == "primary_battlefield_departure_recorded"
    )
    cloned_derived_event = cast(
        dict[str, JsonValue],
        json.loads(json.dumps(original_derived_event, sort_keys=True)),
    )
    cloned_derived_event["event_id"] = f"event-{len(events) + 1:06d}"
    cloned_derived_payload = cast(dict[str, JsonValue], cloned_derived_event["payload"])
    cloned_derived_payload["primary_battlefield_departure_state"] = json.loads(
        json.dumps(forged, sort_keys=True)
    )
    events.append(cloned_derived_event)

    with pytest.raises(
        GameLifecycleError,
        match=r"authoritative .* mutation event|no authoritative mutation provider",
    ):
        GameLifecycle.from_payload(payload)


def test_replay_v6_rejects_invented_reserve_deadline_destruction() -> None:
    payload = _populated_primary_destruction_replay_payload()
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    destructions = cast(list[JsonValue], state_payload["primary_unit_destruction_states"])
    assert len(destructions) == 1
    forged = cast(dict[str, JsonValue], json.loads(json.dumps(destructions[0])))
    forged_source_id = "phase18b:invented:reserve-deadline"
    forged["destroying_player_id"] = None
    forged["destruction_attribution"] = None
    forged["source_model_destroyed_event_id"] = None
    forged["source_rules_unit_objective_proximity_witness"] = None
    forged["source_battlefield_departure_ids"] = []
    forged["unattributed_cause"] = PrimaryUnattributedDestructionCause.RESERVE_DEADLINE.value
    forged["source_id"] = forged_source_id
    forged["source_mutation_id"] = forged_source_id
    forged["destruction_id"] = primary_unit_destruction_id(
        game_id=cast(str, forged["game_id"]),
        source_id=forged_source_id,
        destroyed_unit_instance_id=cast(str, forged["destroyed_unit_instance_id"]),
    )
    destructions.append(forged)

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "authoritative recorded event" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_duplicate_destruction_completion_without_restore() -> None:
    payload = _populated_primary_destruction_replay_payload()
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    decisions_payload = cast(dict[str, JsonValue], lifecycle_payload["decisions"])
    events = cast(list[JsonValue], decisions_payload["event_log"])
    model_destroyed_events = tuple(
        cast(
            dict[str, JsonValue],
            json.loads(json.dumps(event, sort_keys=True)),
        )
        for event in events
        if cast(dict[str, JsonValue], event)["event_type"] == "model_destroyed"
    )
    departures = cast(list[JsonValue], state_payload["primary_battlefield_departure_states"])
    new_departure_ids: list[str] = []
    new_model_destroyed_event_ids: list[str] = []

    for original_event in model_destroyed_events:
        original_event_id = cast(str, original_event["event_id"])
        new_event_id = f"event-{len(events) + 1:06d}"
        new_model_destroyed_event_ids.append(new_event_id)
        events.append(
            {
                "event_id": new_event_id,
                "event_type": "model_destroyed",
                "payload": json.loads(json.dumps(original_event["payload"], sort_keys=True)),
            }
        )
        original_departure = next(
            cast(dict[str, JsonValue], departure)
            for departure in departures
            if cast(str, cast(dict[str, JsonValue], departure)["occurrence_id"]).startswith(
                f"{original_event_id}:"
            )
        )
        duplicated_departure = cast(
            dict[str, JsonValue],
            json.loads(json.dumps(original_departure, sort_keys=True)),
        )
        component_id = cast(
            str,
            cast(list[JsonValue], duplicated_departure["affected_component_unit_instance_ids"])[0],
        )
        duplicated_occurrence_id = f"{new_event_id}:{component_id}"
        duplicated_source_id = (
            f"core-rules:primary-unit-destruction-tracking:{new_event_id}:{component_id}"
        )
        duplicated_departure["occurrence_id"] = duplicated_occurrence_id
        duplicated_departure["source_id"] = duplicated_source_id
        duplicated_departure_id = primary_battlefield_departure_id(
            game_id=cast(str, duplicated_departure["game_id"]),
            rules_unit_instance_id=cast(str, duplicated_departure["rules_unit_instance_id"]),
            affected_component_unit_instance_ids=tuple(
                cast(list[str], duplicated_departure["affected_component_unit_instance_ids"])
            ),
            departed_component_unit_instance_ids=tuple(
                cast(list[str], duplicated_departure["departed_component_unit_instance_ids"])
            ),
            removed_model_instance_ids=tuple(
                cast(list[str], duplicated_departure["removed_model_instance_ids"])
            ),
            battle_round=cast(int, duplicated_departure["battle_round"]),
            active_player_id=cast(str, duplicated_departure["active_player_id"]),
            phase=cast(str, duplicated_departure["phase"]),
            removal_kind=BattlefieldRemovalKind.DESTROYED,
            occurrence_id=duplicated_occurrence_id,
            source_id=duplicated_source_id,
        )
        duplicated_departure["departure_id"] = duplicated_departure_id
        departures.append(duplicated_departure)
        new_departure_ids.append(duplicated_departure_id)
        events.append(
            {
                "event_id": f"event-{len(events) + 1:06d}",
                "event_type": "primary_battlefield_departure_recorded",
                "payload": {
                    "game_id": duplicated_departure["game_id"],
                    "battle_round": duplicated_departure["battle_round"],
                    "active_player_id": duplicated_departure["active_player_id"],
                    "phase": duplicated_departure["phase"],
                    "primary_battlefield_departure_state": json.loads(
                        json.dumps(duplicated_departure, sort_keys=True)
                    ),
                },
            }
        )

    destructions = cast(list[JsonValue], state_payload["primary_unit_destruction_states"])
    assert len(destructions) == 1
    duplicated_destruction = cast(
        dict[str, JsonValue],
        json.loads(json.dumps(destructions[0], sort_keys=True)),
    )
    final_model_destroyed_event_id = new_model_destroyed_event_ids[-1]
    destroyed_unit_id = cast(str, duplicated_destruction["destroyed_unit_instance_id"])
    duplicated_destruction["source_model_destroyed_event_id"] = final_model_destroyed_event_id
    duplicated_destruction["source_battlefield_departure_ids"] = cast(
        JsonValue, sorted(new_departure_ids)
    )
    duplicated_destruction_source_id = (
        "core-rules:primary-unit-destruction-tracking:"
        f"{final_model_destroyed_event_id}:{destroyed_unit_id}"
    )
    duplicated_destruction["source_id"] = duplicated_destruction_source_id
    duplicated_destruction["destruction_id"] = primary_unit_destruction_id(
        game_id=cast(str, duplicated_destruction["game_id"]),
        source_id=duplicated_destruction_source_id,
        destroyed_unit_instance_id=destroyed_unit_id,
    )
    destructions.append(duplicated_destruction)
    events.append(
        {
            "event_id": f"event-{len(events) + 1:06d}",
            "event_type": "primary_unit_destruction_recorded",
            "payload": {
                "game_id": duplicated_destruction["game_id"],
                "battle_round": duplicated_destruction["battle_round"],
                "active_player_id": duplicated_destruction["active_player_id"],
                "phase": duplicated_destruction["phase"],
                "source_model_destroyed_event_id": final_model_destroyed_event_id,
                "primary_unit_destruction_state": json.loads(
                    json.dumps(duplicated_destruction, sort_keys=True)
                ),
            },
        }
    )

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "requires a living model transition" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_unbacked_destroyed_departure_for_already_dead_model() -> None:
    payload = _populated_primary_destruction_replay_payload()
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    departures = cast(list[JsonValue], state_payload["primary_battlefield_departure_states"])
    assert departures
    forged_departure = cast(
        dict[str, JsonValue],
        json.loads(json.dumps(departures[0], sort_keys=True)),
    )
    component_id = cast(
        str,
        cast(list[JsonValue], forged_departure["affected_component_unit_instance_ids"])[0],
    )
    forged_source = "phase18b:forged:unbacked-destroyed"
    forged_departure_source_id = f"{forged_source}:{component_id}"
    forged_departure["occurrence_id"] = forged_departure_source_id
    forged_departure["source_id"] = forged_departure_source_id
    forged_departure["departure_id"] = primary_battlefield_departure_id(
        game_id=cast(str, forged_departure["game_id"]),
        rules_unit_instance_id=cast(str, forged_departure["rules_unit_instance_id"]),
        affected_component_unit_instance_ids=tuple(
            cast(list[str], forged_departure["affected_component_unit_instance_ids"])
        ),
        departed_component_unit_instance_ids=tuple(
            cast(list[str], forged_departure["departed_component_unit_instance_ids"])
        ),
        removed_model_instance_ids=tuple(
            cast(list[str], forged_departure["removed_model_instance_ids"])
        ),
        battle_round=cast(int, forged_departure["battle_round"]),
        active_player_id=cast(str, forged_departure["active_player_id"]),
        phase=cast(str, forged_departure["phase"]),
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        occurrence_id=forged_departure_source_id,
        source_id=forged_departure_source_id,
    )
    departures.append(forged_departure)
    decisions_payload = cast(dict[str, JsonValue], lifecycle_payload["decisions"])
    events = cast(list[JsonValue], decisions_payload["event_log"])
    events.append(
        {
            "event_id": f"event-{len(events) + 1:06d}",
            "event_type": "primary_battlefield_departure_recorded",
            "payload": {
                "game_id": forged_departure["game_id"],
                "battle_round": forged_departure["battle_round"],
                "active_player_id": forged_departure["active_player_id"],
                "phase": forged_departure["phase"],
                "primary_battlefield_departure_state": json.loads(
                    json.dumps(forged_departure, sort_keys=True)
                ),
            },
        }
    )

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "no authoritative mutation provider" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_attributed_destruction_relabelled_as_coherency_cleanup() -> None:
    payload = _populated_primary_destruction_replay_payload()
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    decisions_payload = cast(dict[str, JsonValue], lifecycle_payload["decisions"])
    events = cast(list[JsonValue], decisions_payload["event_log"])
    departures = cast(list[JsonValue], state_payload["primary_battlefield_departure_states"])
    destructions = cast(list[JsonValue], state_payload["primary_unit_destruction_states"])
    assert departures
    assert len(destructions) == 1
    original_destruction = cast(dict[str, JsonValue], destructions[0])
    destroyed_unit_id = cast(str, original_destruction["destroyed_unit_instance_id"])
    destroyed_model_ids = sorted(
        cast(str, model_id)
        for departure_value in departures
        for departure in (cast(dict[str, JsonValue], departure_value),)
        for model_id in cast(list[JsonValue], departure["removed_model_instance_ids"])
    )
    cleanup_id = f"end-turn-cleanup:{cast(str, state_payload['game_id'])}:round-01:player-a"

    for event_value in events:
        event = cast(dict[str, JsonValue], event_value)
        if event["event_type"] in {
            "primary_battlefield_departure_recorded",
            "primary_unit_destruction_recorded",
        }:
            event["event_type"] = "phase18b_relabelled_derived_placeholder"

    combined_departure = cast(
        dict[str, JsonValue],
        json.loads(json.dumps(departures[0], sort_keys=True)),
    )
    combined_departure["departed_component_unit_instance_ids"] = [destroyed_unit_id]
    combined_departure["removed_model_instance_ids"] = cast(JsonValue, destroyed_model_ids)
    combined_departure_source_id = f"{cleanup_id}:{destroyed_unit_id}"
    combined_departure["occurrence_id"] = combined_departure_source_id
    combined_departure["source_id"] = combined_departure_source_id
    combined_departure["departure_id"] = primary_battlefield_departure_id(
        game_id=cast(str, combined_departure["game_id"]),
        rules_unit_instance_id=cast(str, combined_departure["rules_unit_instance_id"]),
        affected_component_unit_instance_ids=tuple(
            cast(list[str], combined_departure["affected_component_unit_instance_ids"])
        ),
        departed_component_unit_instance_ids=tuple(
            cast(list[str], combined_departure["departed_component_unit_instance_ids"])
        ),
        removed_model_instance_ids=tuple(
            cast(list[str], combined_departure["removed_model_instance_ids"])
        ),
        battle_round=cast(int, combined_departure["battle_round"]),
        active_player_id=cast(str, combined_departure["active_player_id"]),
        phase=cast(str, combined_departure["phase"]),
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        occurrence_id=combined_departure_source_id,
        source_id=combined_departure_source_id,
    )
    departures[:] = [combined_departure]

    cleanup_states = cast(list[JsonValue], state_payload["end_turn_cleanup_states"])
    cleanup_states.append(
        {
            "cleanup_id": cleanup_id,
            "game_id": state_payload["game_id"],
            "battle_round": 1,
            "active_player_id": "player-a",
            "phase": BattlePhase.MOVEMENT.value,
            "removals": [
                {
                    "player_id": "player-b",
                    "unit_instance_id": destroyed_unit_id,
                    "model_instance_id": model_id,
                    "removal_kind": BattlefieldRemovalKind.DESTROYED.value,
                    "source_rule_id": "core_rules_unit_coherency_cleanup",
                    "destroyed_model_rules_triggered": False,
                }
                for model_id in destroyed_model_ids
            ],
            "coherency_results": [],
            "transition_batch": {
                "placements": [],
                "removals": [
                    {
                        "model_instance_id": model_id,
                        "removal_kind": BattlefieldRemovalKind.DESTROYED.value,
                        "source_phase": BattlePhase.MOVEMENT.value,
                        "source_step": "end_turn_cleanup",
                        "source_rule_id": "core_rules_unit_coherency_cleanup",
                        "source_event_id": None,
                        "destination_id": None,
                    }
                    for model_id in destroyed_model_ids
                ],
                "displacements": [],
            },
        }
    )

    relabelled_destruction = cast(
        dict[str, JsonValue],
        json.loads(json.dumps(original_destruction, sort_keys=True)),
    )
    relabelled_destruction["destroying_player_id"] = None
    relabelled_destruction["destruction_attribution"] = None
    relabelled_destruction["source_model_destroyed_event_id"] = None
    relabelled_destruction["source_rules_unit_objective_proximity_witness"] = None
    relabelled_destruction["source_battlefield_departure_ids"] = [
        combined_departure["departure_id"]
    ]
    relabelled_destruction["unattributed_cause"] = (
        PrimaryUnattributedDestructionCause.UNIT_COHERENCY.value
    )
    relabelled_destruction["source_mutation_id"] = cleanup_id
    relabelled_destruction_source_id = f"{cleanup_id}:{destroyed_unit_id}"
    relabelled_destruction["source_id"] = relabelled_destruction_source_id
    relabelled_destruction["destruction_id"] = primary_unit_destruction_id(
        game_id=cast(str, relabelled_destruction["game_id"]),
        source_id=relabelled_destruction_source_id,
        destroyed_unit_instance_id=destroyed_unit_id,
    )
    destructions[:] = [relabelled_destruction]
    events.extend(
        (
            {
                "event_id": f"event-{len(events) + 1:06d}",
                "event_type": "primary_battlefield_departure_recorded",
                "payload": {
                    "game_id": combined_departure["game_id"],
                    "battle_round": combined_departure["battle_round"],
                    "active_player_id": combined_departure["active_player_id"],
                    "phase": combined_departure["phase"],
                    "primary_battlefield_departure_state": json.loads(
                        json.dumps(combined_departure, sort_keys=True)
                    ),
                },
            },
            {
                "event_id": f"event-{len(events) + 2:06d}",
                "event_type": "battle_phase_completed",
                "payload": {},
            },
            {
                "event_id": f"event-{len(events) + 3:06d}",
                "event_type": "primary_unit_destruction_recorded",
                "payload": {
                    "game_id": relabelled_destruction["game_id"],
                    "battle_round": relabelled_destruction["battle_round"],
                    "active_player_id": relabelled_destruction["active_player_id"],
                    "phase": relabelled_destruction["phase"],
                    "source_model_destroyed_event_id": None,
                    "primary_unit_destruction_state": json.loads(
                        json.dumps(relabelled_destruction, sort_keys=True)
                    ),
                },
            },
        )
    )

    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, lifecycle_payload))


def test_replay_v6_rejects_attributed_destruction_relabelled_as_reserve_deadline() -> None:
    payload = _populated_primary_destruction_replay_payload()
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    decisions_payload = cast(dict[str, JsonValue], lifecycle_payload["decisions"])
    events = cast(list[JsonValue], decisions_payload["event_log"])
    destructions = cast(list[JsonValue], state_payload["primary_unit_destruction_states"])
    assert len(destructions) == 1
    destruction = cast(dict[str, JsonValue], destructions[0])
    destroyed_unit_id = cast(str, destruction["destroyed_unit_instance_id"])

    cast(list[JsonValue], state_payload["primary_battlefield_departure_states"]).clear()
    for event_value in events:
        event = cast(dict[str, JsonValue], event_value)
        if event["event_type"] == "primary_battlefield_departure_recorded":
            event["event_type"] = "phase18b_relabelled_departure_placeholder"

    policy_source_id = "phase18b:forged:reserve-policy"
    reserve_states = cast(list[JsonValue], state_payload["reserve_states"])
    reserve_states.append(
        {
            "player_id": "player-b",
            "unit_instance_id": destroyed_unit_id,
            "reserve_origin": "declare_battle_formations",
            "reserve_kind": "strategic_reserves",
            "source_rule_ids": ["strategic_reserves"],
            "points_contribution": 0,
            "declared_during_step": "declare_battle_formations",
            "entered_reserves_battle_round": None,
            "entered_reserves_phase": None,
            "required_arrival_battle_round": None,
            "required_arrival_phase": None,
            "required_arrival_source_rule_id": None,
            "required_arrival_placement_kind": None,
            "destruction_deadline_policy": {
                "timing_kind": "end_of_battle_round_n",
                "battle_round": 1,
                "exclude_during_battle_strategic_reserves": True,
                "only_declare_battle_formations": True,
                "source_id": policy_source_id,
            },
            "status": "destroyed",
            "embarked_unit_instance_ids": [],
            "arrived_battle_round": None,
            "arrived_phase": None,
            "destroyed_battle_round": 1,
            "large_model_exception_used": False,
            "post_arrival_restrictions": [],
            "restriction_battle_round": None,
        }
    )
    mutation_id = f"{policy_source_id}:round-01:round-boundary"
    destruction["destroying_player_id"] = None
    destruction["destruction_attribution"] = None
    destruction["source_model_destroyed_event_id"] = None
    destruction["source_rules_unit_objective_proximity_witness"] = None
    destruction["source_battlefield_departure_ids"] = []
    destruction["unattributed_cause"] = PrimaryUnattributedDestructionCause.RESERVE_DEADLINE.value
    destruction["source_mutation_id"] = mutation_id
    destruction_source_id = f"{mutation_id}:{destroyed_unit_id}"
    destruction["source_id"] = destruction_source_id
    destruction["destruction_id"] = primary_unit_destruction_id(
        game_id=cast(str, destruction["game_id"]),
        source_id=destruction_source_id,
        destroyed_unit_instance_id=destroyed_unit_id,
    )
    recorded_event = next(
        cast(dict[str, JsonValue], event)
        for event in events
        if cast(dict[str, JsonValue], event)["event_type"] == "primary_unit_destruction_recorded"
    )
    recorded_event["payload"] = {
        "game_id": destruction["game_id"],
        "battle_round": destruction["battle_round"],
        "active_player_id": destruction["active_player_id"],
        "phase": destruction["phase"],
        "source_model_destroyed_event_id": None,
        "primary_unit_destruction_state": json.loads(json.dumps(destruction, sort_keys=True)),
    }

    with pytest.raises(GameLifecycleError, match="exact battlefield departure"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, lifecycle_payload))


def test_replay_v6_rejects_primary_destruction_recorded_event_payload_drift() -> None:
    payload = _populated_primary_destruction_replay_payload()
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    decisions_payload = cast(dict[str, JsonValue], lifecycle_payload["decisions"])
    events = cast(list[JsonValue], decisions_payload["event_log"])
    recorded_event = next(
        cast(dict[str, JsonValue], event)
        for event in events
        if cast(dict[str, JsonValue], event)["event_type"] == "primary_unit_destruction_recorded"
    )
    recorded_payload = cast(dict[str, JsonValue], recorded_event["payload"])
    recorded_payload["source_rule_id"] = "phase18b-invented-tracking-rule"

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "recorded-event payload drift" in str(exc_info.value.__cause__)


def test_replay_v6_accepts_attached_target_historical_rules_unit_destruction() -> None:
    payload = _populated_primary_destruction_replay_payload(attached_target=True)
    destruction = _primary_destruction_payload(payload)
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    decisions_payload = cast(dict[str, JsonValue], lifecycle_payload["decisions"])
    model_destroyed_events = [
        cast(dict[str, JsonValue], event)
        for event in cast(list[JsonValue], decisions_payload["event_log"])
        if cast(dict[str, JsonValue], event)["event_type"] == "model_destroyed"
    ]
    final_event_payload = cast(dict[str, JsonValue], model_destroyed_events[-1]["payload"])

    assert destruction["destroyed_unit_instance_id"] == "attached-unit:army-beta:target"
    assert final_event_payload["target_unit_instance_id"] == "army-beta:target-leader"
    assert len(cast(list[JsonValue], destruction["source_battlefield_departure_ids"])) == 6
    assert ReplayArtifact.from_payload(payload).to_payload() == payload


def test_replay_v6_rejects_frozen_attached_mapping_replaced_by_materialized_model() -> None:
    lifecycle = _populated_primary_destruction_lifecycle(
        attached_target=True,
        complete_attached_target=True,
        added_attached_model=True,
    )
    lifecycle_payload = cast(dict[str, JsonValue], json.loads(json.dumps(lifecycle.to_payload())))
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    records = cast(list[JsonValue], state_payload["starting_attached_unit_records"])
    assert len(records) == 1
    record = cast(dict[str, JsonValue], records[0])
    frozen_by_component = cast(
        dict[str, JsonValue], record["starting_model_instance_ids_by_component"]
    )
    leader_id = "army-beta:target-leader"
    frozen_leader_ids = cast(list[JsonValue], frozen_by_component[leader_id])
    assert len(frozen_leader_ids) == 1
    frozen_leader_ids[0] = "army-beta:target-leader:phase18b-added-model"
    decisions_payload = cast(dict[str, JsonValue], lifecycle_payload["decisions"])
    event_log = cast(list[JsonValue], decisions_payload["event_log"])
    mustered = next(
        cast(dict[str, JsonValue], event["payload"])
        for raw_event in event_log
        for event in (cast(dict[str, JsonValue], raw_event),)
        if event["event_type"] == "army_mustered"
        and cast(dict[str, JsonValue], event["payload"])["player_id"] == "player-b"
    )
    mustered_records = cast(list[JsonValue], mustered["starting_attached_unit_records"])
    mustered_record = cast(dict[str, JsonValue], mustered_records[0])
    mustered_mapping = cast(
        dict[str, JsonValue], mustered_record["starting_model_instance_ids_by_component"]
    )
    cast(list[JsonValue], mustered_mapping[leader_id])[0] = (
        "army-beta:target-leader:phase18b-added-model"
    )

    with pytest.raises(GameLifecycleError, match="muster mapping drift"):
        GameLifecycle.from_payload(cast(GameLifecyclePayload, lifecycle_payload))


def test_replay_v6_rejects_forged_catalog_materialization_evidence() -> None:
    lifecycle = _populated_primary_destruction_lifecycle(
        attached_target=True,
        complete_attached_target=True,
        added_attached_model=True,
    )

    with pytest.raises(GameLifecycleError, match="active runtime provider binding"):
        GameLifecycle.from_payload(_lifecycle_payload_copy(lifecycle))


def test_replay_v6_accepts_unpaired_intermediate_attached_component_departure() -> None:
    lifecycle = _populated_primary_destruction_lifecycle(
        attached_target=True,
        complete_attached_target=False,
    )
    state = _state(lifecycle)

    assert state.primary_unit_destruction_states == []
    assert len(state.primary_battlefield_departure_states) == 5
    restored = GameLifecycle.from_payload(_lifecycle_payload_copy(lifecycle))
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()


def test_replay_v6_rejects_attached_destruction_with_omitted_component_edge() -> None:
    payload = _populated_primary_destruction_replay_payload(attached_target=True)
    destruction = _primary_destruction_payload(payload)
    departure_ids = cast(list[JsonValue], destruction["source_battlefield_departure_ids"])
    assert len(departure_ids) == 6
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    departures = cast(list[JsonValue], state_payload["primary_battlefield_departure_states"])
    bodyguard_departure_id = next(
        cast(str, departure["departure_id"])
        for value in departures
        for departure in (cast(dict[str, JsonValue], value),)
        if departure["departed_component_unit_instance_ids"] == ["army-beta:target"]
    )
    departure_ids.remove(bodyguard_departure_id)
    decisions_payload = cast(dict[str, JsonValue], lifecycle_payload["decisions"])
    recorded_event = next(
        cast(dict[str, JsonValue], event)
        for event in cast(list[JsonValue], decisions_payload["event_log"])
        if cast(dict[str, JsonValue], event)["event_type"] == "primary_unit_destruction_recorded"
    )
    recorded_payload = cast(dict[str, JsonValue], recorded_event["payload"])
    recorded_state = cast(dict[str, JsonValue], recorded_payload["primary_unit_destruction_state"])
    recorded_departure_ids = cast(
        list[JsonValue], recorded_state["source_battlefield_departure_ids"]
    )
    recorded_departure_ids.remove(bodyguard_departure_id)

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "starting rules unit" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_nonfinal_attached_model_event_as_completion() -> None:
    payload = _populated_primary_destruction_replay_payload(attached_target=True)
    destruction = _primary_destruction_payload(payload)
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    decisions_payload = cast(dict[str, JsonValue], lifecycle_payload["decisions"])
    events = cast(list[JsonValue], decisions_payload["event_log"])
    model_destroyed_events = [
        cast(dict[str, JsonValue], event)
        for event in events
        if cast(dict[str, JsonValue], event)["event_type"] == "model_destroyed"
    ]
    first_event_id = cast(str, model_destroyed_events[0]["event_id"])
    logical_unit_id = cast(str, destruction["destroyed_unit_instance_id"])
    source_id = f"core-rules:primary-unit-destruction-tracking:{first_event_id}:{logical_unit_id}"
    destruction["source_model_destroyed_event_id"] = first_event_id
    destruction["source_id"] = source_id
    destruction["destruction_id"] = primary_unit_destruction_id(
        game_id=cast(str, destruction["game_id"]),
        source_id=source_id,
        destroyed_unit_instance_id=logical_unit_id,
    )
    recorded_event = next(
        cast(dict[str, JsonValue], event)
        for event in events
        if cast(dict[str, JsonValue], event)["event_type"] == "primary_unit_destruction_recorded"
    )
    recorded_payload = cast(dict[str, JsonValue], recorded_event["payload"])
    recorded_payload["source_model_destroyed_event_id"] = first_event_id
    recorded_payload["primary_unit_destruction_state"] = json.loads(
        json.dumps(destruction, sort_keys=True)
    )

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "event-backed departure edges" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_destroyed_rules_unit_witness_identity_drift() -> None:
    payload = _populated_primary_destruction_replay_payload(attached_target=True)
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    decisions_payload = cast(dict[str, JsonValue], lifecycle_payload["decisions"])
    model_destroyed_events = [
        cast(dict[str, JsonValue], event)
        for event in cast(list[JsonValue], decisions_payload["event_log"])
        if cast(dict[str, JsonValue], event)["event_type"] == "model_destroyed"
    ]
    event_payload = cast(dict[str, JsonValue], model_destroyed_events[-1]["payload"])
    destroyed_witness = cast(
        dict[str, JsonValue],
        event_payload["destroyed_rules_unit_objective_proximity_witness"],
    )
    destroyed_witness["component_unit_instance_ids"] = ["army-beta:target"]

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "destroyed witness component identity drift" in str(exc_info.value.__cause__)


def test_replay_v6_accepts_reserve_deadline_destruction_without_departure() -> None:
    lifecycle, units = _movement_phase_lifecycle(game_id="phase18b-reserve-deadline-integrity")
    state = _state(lifecycle)
    target = units["target"]
    battlefield = state.battlefield_state
    mission_setup = state.mission_setup
    assert battlefield is not None
    assert mission_setup is not None
    state.battlefield_state = battlefield.without_unit_placement(target.unit_instance_id)
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-b",
            unit_instance_id=target.unit_instance_id,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            destruction_deadline_policy=reserve_destruction_policy_from_scoring_policy(
                mission_scoring_policies_from_setup(mission_setup).common_policy
            ),
        )
    )
    state.battle_round = 3
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    objective_state_ids_before = tuple(
        value.state_id for value in state.primary_objective_turn_start_states
    )
    snapshot_ids_before = tuple(
        value.snapshot_id for value in state.primary_rules_unit_turn_start_snapshots
    )
    record_primary_turn_start_evidence(state=state)
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=lifecycle.decision_controller.event_log,
        objective_state_ids_before=objective_state_ids_before,
        snapshot_ids_before=snapshot_ids_before,
    )
    destruction_ids_before = tuple(
        value.destruction_id for value in state.primary_unit_destruction_states
    )
    state._resolve_unarrived_reserve_destruction_boundary(end_of_battle=False)
    record_new_primary_unit_destruction_events(
        state=state,
        event_log=lifecycle.decision_controller.event_log,
        destruction_ids_before=destruction_ids_before,
    )

    assert len(state.primary_unit_destruction_states) == 1
    assert state.primary_unit_destruction_states[0].source_battlefield_departure_ids == ()
    assert state.primary_battlefield_departure_states == []
    restored = GameLifecycle.from_payload(_lifecycle_payload_copy(lifecycle))
    assert restored.to_payload() == lifecycle.to_payload()


@pytest.mark.parametrize("remove_and_relabel_member", [False, True])
@pytest.mark.parametrize("mutation_target", ["config", "state"])
def test_replay_v6_rejects_partial_logical_objective_bindings(
    remove_and_relabel_member: bool,
    mutation_target: str,
) -> None:
    payload, _event_setup = _event_layout_replay_payload()
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    config_payload = cast(dict[str, JsonValue], lifecycle_payload["config"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    mission_setup_payload = cast(
        dict[str, JsonValue],
        (config_payload if mutation_target == "config" else state_payload)["mission_setup"],
    )
    bindings = cast(list[JsonValue], mission_setup_payload["objective_terrain_areas"])
    binding = cast(dict[str, JsonValue], bindings[0])
    terrain_areas = cast(list[JsonValue], mission_setup_payload["terrain_areas"])
    area_ids_by_logical_id: dict[str, list[JsonValue]] = {}
    for candidate in terrain_areas:
        area = cast(dict[str, JsonValue], candidate)
        logical_id = cast(str, area["logical_terrain_area_id"])
        area_ids_by_logical_id.setdefault(logical_id, []).append(area["terrain_area_id"])
    complete_ids = next(
        area_ids for area_ids in area_ids_by_logical_id.values() if len(area_ids) > 1
    )
    retained_id = cast(str, complete_ids[-1])
    binding["terrain_area_ids"] = [retained_id]
    if remove_and_relabel_member:
        terrain_areas[:] = [
            candidate
            for candidate in terrain_areas
            if cast(dict[str, JsonValue], candidate)["terrain_area_id"] == retained_id
            or cast(dict[str, JsonValue], candidate)["terrain_area_id"] not in complete_ids
        ]
        retained_area = next(
            cast(dict[str, JsonValue], candidate)
            for candidate in terrain_areas
            if cast(dict[str, JsonValue], candidate)["terrain_area_id"] == retained_id
        )
        retained_area["logical_terrain_area_id"] = retained_id

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid"):
        ReplayArtifact.from_payload(payload)


@pytest.mark.parametrize("terrain_mutation", ["injected", "removed", "relocated"])
def test_replay_v6_rejects_runtime_battlefield_drift_from_source_layout(
    terrain_mutation: str,
) -> None:
    payload, event_setup = _event_layout_replay_payload()
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    battlefield_payload = cast(dict[str, JsonValue], state_payload["battlefield_state"])
    terrain_features = cast(list[JsonValue], battlefield_payload["terrain_features"])
    if terrain_mutation == "injected":
        terrain_features.append(
            validate_json_value(
                TerrainFactory.ruins_fixture(
                    feature_id="phase18b-injected-runtime-wall",
                    center_x_inches=22.0,
                    center_y_inches=30.0,
                )[0].to_payload()
            )
        )
    elif terrain_mutation == "removed":
        terrain_features.pop()
    else:
        source_feature = event_setup.terrain_features[0]
        terrain_features[0] = validate_json_value(
            _translated_terrain_feature(
                source_feature,
                x_delta=0.05,
                y_delta=0.0,
            ).to_payload()
        )

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "battlefield runtime geometry drifted" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_canonical_layoutless_mission_setup_source_drift() -> None:
    payload = _artifact_payload_copy(_setup_to_battle_artifact())
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    config_payload = cast(dict[str, JsonValue], lifecycle_payload["config"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    for owner_payload in (config_payload, state_payload):
        mission_setup_payload = cast(dict[str, JsonValue], owner_payload["mission_setup"])
        assert mission_setup_payload["battlefield_layout_id"] is None
        mission_setup_payload["source_id"] = "substituted-source"
        mission_setup_payload["source_version"] = "substituted-version"
        assignments = cast(
            list[JsonValue],
            mission_setup_payload["primary_mission_assignments"],
        )
        cast(dict[str, JsonValue], assignments[0])["primary_mission_id"] = "primary-meatgrinder"
        objective_markers = cast(list[JsonValue], mission_setup_payload["objective_markers"])
        central_marker = next(
            cast(dict[str, JsonValue], marker)
            for marker in objective_markers
            if cast(dict[str, JsonValue], marker)["objective_marker_id"]
            == "take-and-hold-vs-purge-the-foe-layout-3-center-central"
        )
        central_marker["x_inches"] = 35.0
    source_identity_payload = cast(dict[str, JsonValue], payload["source_identity"])
    source_identity_payload["game_config_hash"] = hashlib.sha256(
        canonical_json(validate_json_value(config_payload)).encode("utf-8")
    ).hexdigest()

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "source package identity drifted" in str(exc_info.value.__cause__)


@pytest.mark.parametrize("runtime_mutation", ["dimensions", "injected_terrain"])
def test_replay_v6_rejects_canonical_layoutless_runtime_battlefield_drift(
    runtime_mutation: str,
) -> None:
    payload = _artifact_payload_copy(_setup_to_battle_artifact())
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    config_payload = cast(dict[str, JsonValue], lifecycle_payload["config"])
    mission_setup_payload = cast(dict[str, JsonValue], config_payload["mission_setup"])
    assert mission_setup_payload["battlefield_layout_id"] is None
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    battlefield_payload = cast(dict[str, JsonValue], state_payload["battlefield_state"])
    if runtime_mutation == "dimensions":
        battlefield_payload["battlefield_width_inches"] = 99.0
    else:
        terrain_features = cast(list[JsonValue], battlefield_payload["terrain_features"])
        assert terrain_features == []
        terrain_features.append(
            validate_json_value(
                TerrainFactory.ruins_fixture(
                    feature_id="phase18b-layoutless-injected-runtime-wall",
                    center_x_inches=30.0,
                    center_y_inches=22.0,
                )[0].to_payload()
            )
        )

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "battlefield runtime geometry drifted" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_custom_layoutless_runtime_battlefield_dimension_drift() -> None:
    payload = _artifact_payload_copy(_setup_to_battle_artifact())
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    config_payload = cast(dict[str, JsonValue], lifecycle_payload["config"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    for owner_payload in (config_payload, state_payload):
        mission_setup_payload = cast(dict[str, JsonValue], owner_payload["mission_setup"])
        assert mission_setup_payload["battlefield_layout_id"] is None
        mission_setup_payload["deployment_map_id"] = "phase18b-custom-layoutless-deployment-map"
        mission_setup_payload["terrain_layout_id"] = "phase18b-custom-layoutless-terrain-layout"
        mission_setup_payload["battlefield_width_inches"] = 60.0
        mission_setup_payload["battlefield_depth_inches"] = 44.0
        mission_setup_payload["objective_markers"] = []
        mission_setup_payload["deployment_zones"] = []
        mission_setup_payload["battlefield_regions"] = []
        mission_setup_payload["terrain_areas"] = []
        mission_setup_payload["objective_terrain_areas"] = []
        mission_setup_payload["terrain_features"] = []
    battlefield_payload = cast(dict[str, JsonValue], state_payload["battlefield_state"])
    battlefield_payload["battlefield_width_inches"] = 99.0
    battlefield_payload["battlefield_depth_inches"] = 77.0
    source_identity_payload = cast(dict[str, JsonValue], payload["source_identity"])
    source_identity_payload["game_config_hash"] = hashlib.sha256(
        canonical_json(validate_json_value(config_payload)).encode("utf-8")
    ).hexdigest()

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "battlefield runtime geometry drifted" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_state_mission_setup_drift_from_config() -> None:
    payload = _artifact_payload_copy(_setup_to_battle_artifact())
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    state_payload["mission_setup"] = cast(
        JsonValue,
        MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-b",
            attacker_force_disposition_id="purge-the-foe",
            defender_player_id="player-a",
            defender_force_disposition_id="take-and-hold",
        ).to_payload(),
    )

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "state mission_setup does not match config" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_missing_state_mission_setup_with_config() -> None:
    payload = _artifact_payload_copy(_setup_to_battle_artifact())
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    state_payload = cast(dict[str, JsonValue], lifecycle_payload["state"])
    state_payload["mission_setup"] = None

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "state mission_setup does not match config" in str(exc_info.value.__cause__)


def test_replay_v6_rejects_source_linked_state_setup_missing_from_config() -> None:
    payload, _event_setup = _event_layout_replay_payload()
    lifecycle_payload = cast(dict[str, JsonValue], payload["initial_lifecycle"])
    config_payload = cast(dict[str, JsonValue], lifecycle_payload["config"])
    config_payload["mission_setup"] = None

    with pytest.raises(ReplayArtifactError, match="lifecycle payload is invalid") as exc_info:
        ReplayArtifact.from_payload(payload)

    assert isinstance(exc_info.value.__cause__, GameLifecycleError)
    assert "state mission_setup does not match config" in str(exc_info.value.__cause__)


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
    attached_target: bool = False,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    config = _combat_config(game_id=game_id, attached_target=attached_target)
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
    if attached_target:
        battlefield = battlefield.with_unit_placement(
            _unit_placement_at(
                units["target-leader"],
                army_id="army-beta",
                player_id="player-b",
                poses=(Pose.at(22.0, 20.0, facing_degrees=180.0),),
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
    seed_lifecycle = GameLifecycle()
    for army in armies:
        seed_lifecycle.decision_controller.event_log.append(
            "army_mustered",
            army_mustered_event_payload(
                state=state,
                army_definition=army,
            ),
        )
    payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": seed_lifecycle.decision_controller.to_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    return GameLifecycle.from_payload(payload), units


def _populated_primary_destruction_replay_payload(
    *,
    attached_target: bool = False,
) -> ReplayArtifactPayload:
    lifecycle = _populated_primary_destruction_lifecycle(
        attached_target=attached_target,
        complete_attached_target=True,
    )
    initial_payload = _lifecycle_payload_copy(lifecycle)
    artifact = ReplayArtifact.capture(
        artifact_id="phase18b-primary-destruction-integrity",
        initial_lifecycle_payload=initial_payload,
        final_lifecycle=lifecycle,
    )
    payload = _artifact_payload_copy(artifact)
    assert ReplayArtifact.from_payload(payload).to_payload() == payload
    return payload


def _populated_primary_destruction_lifecycle(
    *,
    attached_target: bool,
    complete_attached_target: bool,
    added_attached_model: bool = False,
) -> GameLifecycle:
    lifecycle, units = _movement_phase_lifecycle(
        game_id="phase18b-primary-destruction-integrity",
        attached_target=attached_target,
    )
    state = _state(lifecycle)
    attacker = units["attacker"]
    target = units["target"]
    added_model_id: str | None = None
    if added_attached_model:
        if not attached_target:
            raise AssertionError("Added attached-model fixture requires an attached target.")
        leader = units["target-leader"]
        original_leader_model = leader.own_models[0]
        added_model_id = f"{leader.unit_instance_id}:phase18b-added-model"
        added_model = replace(
            original_leader_model,
            model_instance_id=added_model_id,
            source_ids=tuple(
                sorted((*original_leader_model.source_ids, "test:phase18b:added-model"))
            ),
        )
        replacement_leader = replace(leader, own_models=(*leader.own_models, added_model))
        _replace_test_unit(state=state, replacement=replacement_leader)
        battlefield = state.battlefield_state
        assert battlefield is not None
        leader_placement = battlefield.unit_placement_by_id(leader.unit_instance_id)
        state.battlefield_state = battlefield.with_unit_placement(
            leader_placement.with_model_placements(
                (
                    *leader_placement.model_placements,
                    ModelPlacement(
                        army_id="army-beta",
                        player_id="player-b",
                        unit_instance_id=leader.unit_instance_id,
                        model_instance_id=added_model_id,
                        pose=Pose.at(24.0, 20.0, facing_degrees=180.0),
                    ),
                )
            )
        )
        lifecycle.decision_controller.event_log.append(
            CATALOG_MODELS_MATERIALIZED_EVENT,
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "attack_sequence_id": "phase18b-materialization-sequence",
                "source_phase": BattlePhase.MOVEMENT.value,
                "action_phase": BattlePhase.MOVEMENT.value,
                "parent_battle_phase": BattlePhase.MOVEMENT.value,
                "source_rule_id": "test:phase18b:materialization",
                "source_unit_instance_id": leader.unit_instance_id,
                "request_id": "phase18b-materialization-request",
                "result_id": "phase18b-materialization-result",
                "model_instance_ids": [added_model.model_instance_id],
                "models": [added_model.to_payload()],
                "transition_batch": {"placements": [], "removals": []},
            },
        )
        units["target-leader"] = replacement_leader
    objective_state_ids_before = tuple(
        value.state_id for value in state.primary_objective_turn_start_states
    )
    snapshot_ids_before = tuple(
        value.snapshot_id for value in state.primary_rules_unit_turn_start_snapshots
    )
    record_primary_turn_start_evidence(state=state)
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=lifecycle.decision_controller.event_log,
        objective_state_ids_before=objective_state_ids_before,
        snapshot_ids_before=snapshot_ids_before,
    )
    source_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=attacker.unit_instance_id,
    )
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=attacker.unit_instance_id,
        source_model_instance_id=attacker.own_models[0].model_instance_id,
    )
    tracking_rule_id = "core-rules:primary-unit-destruction-tracking"
    if attached_target:
        attached_unit_id = "attached-unit:army-beta:target"
        bodyguard_destructions = _record_primary_destruction_test_step(
            lifecycle=lifecycle,
            unit=target,
            target_rules_unit_id=attached_unit_id,
            attribution=attribution,
            source_witness=source_witness,
            tracking_rule_id=tracking_rule_id,
        )
        assert bodyguard_destructions == ()
        assert len(state.primary_battlefield_departure_states) == len(target.own_model_ids())
        surviving_ids = split_attached_rules_unit_if_required(
            state=state,
            event_log=lifecycle.decision_controller.event_log,
            rules_unit_instance_id=attached_unit_id,
        )
        leader = units["target-leader"]
        assert surviving_ids == (leader.unit_instance_id,)
        if not complete_attached_target:
            return lifecycle
        destructions = _record_primary_destruction_test_step(
            lifecycle=lifecycle,
            unit=leader,
            target_rules_unit_id=leader.unit_instance_id,
            attribution=attribution,
            source_witness=source_witness,
            tracking_rule_id=tracking_rule_id,
            destroyed_model_ids=tuple(
                model_id for model_id in leader.own_model_ids() if model_id != added_model_id
            ),
        )
    else:
        destructions = _record_primary_destruction_test_step(
            lifecycle=lifecycle,
            unit=target,
            target_rules_unit_id=target.unit_instance_id,
            attribution=attribution,
            source_witness=source_witness,
            tracking_rule_id=tracking_rule_id,
        )
    assert len(destructions) == 1
    destruction = destructions[0]
    record_primary_unit_destruction_event(
        event_log=lifecycle.decision_controller.event_log,
        destruction=destruction,
    )
    return lifecycle


def _record_primary_destruction_test_step(
    *,
    lifecycle: GameLifecycle,
    unit: UnitInstance,
    target_rules_unit_id: str,
    attribution: ModelDestructionAttribution,
    source_witness: RulesUnitObjectiveProximityWitness,
    tracking_rule_id: str,
    destroyed_model_ids: tuple[str, ...] | None = None,
) -> tuple[PrimaryUnitDestructionState, ...]:
    state = _state(lifecycle)
    requested_destroyed_model_ids = (
        unit.own_model_ids() if destroyed_model_ids is None else destroyed_model_ids
    )
    destructions: list[PrimaryUnitDestructionState] = []
    for model_id in requested_destroyed_model_ids:
        destroyed_witness = rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=target_rules_unit_id,
        )
        battlefield = state.battlefield_state
        assert battlefield is not None
        _set_test_model_wounds_remaining(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            model_instance_ids=(model_id,),
            wounds_remaining=0,
        )
        state.battlefield_state = battlefield.with_removed_models((model_id,))
        model_destroyed_event = lifecycle.decision_controller.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                **attribution.to_payload(),
                "source_rules_unit_objective_proximity_witness": source_witness.to_payload(),
                "destroyed_rules_unit_objective_proximity_witness": (
                    destroyed_witness.to_payload()
                ),
                "target_unit_instance_id": target_rules_unit_id,
                "model_instance_id": model_id,
            },
        )
        departure_ids_before = tuple(
            value.departure_id for value in state.primary_battlefield_departure_states
        )
        record_primary_destroyed_model_departures(
            state=state,
            destroyed_model_instance_ids=(model_id,),
            source_id=f"{tracking_rule_id}:{model_destroyed_event.event_id}",
            occurrence_id=model_destroyed_event.event_id,
        )
        occurrence_destructions = record_primary_unit_destructions_for_destroyed_models(
            state=state,
            destroyed_model_instance_ids=(model_id,),
            destruction_attribution=attribution,
            source_model_destroyed_event_id=model_destroyed_event.event_id,
            source_rules_unit_objective_proximity_witness=source_witness,
            destroyed_rules_unit_objective_proximity_witness=destroyed_witness,
            unattributed_cause=None,
            source_mutation_id=None,
            left_battlefield=False,
            source_id=f"{tracking_rule_id}:{model_destroyed_event.event_id}",
        )
        record_new_primary_battlefield_departure_events(
            state=state,
            event_log=lifecycle.decision_controller.event_log,
            departure_ids_before=departure_ids_before,
        )
        destructions.extend(occurrence_destructions)
    assert all(type(destruction) is PrimaryUnitDestructionState for destruction in destructions)
    return tuple(destructions)


def _set_test_model_wounds_remaining(
    *,
    state: GameState,
    unit_instance_id: str,
    model_instance_ids: tuple[str, ...],
    wounds_remaining: int,
) -> None:
    requested_model_ids = set(model_instance_ids)
    unit = next(
        candidate
        for army in state.army_definitions
        for candidate in army.units
        if candidate.unit_instance_id == unit_instance_id
    )
    _replace_test_unit(
        state=state,
        replacement=replace(
            unit,
            own_models=tuple(
                replace(model, wounds_remaining=wounds_remaining)
                if model.model_instance_id in requested_model_ids
                else model
                for model in unit.own_models
            ),
        ),
    )


def _replace_test_unit(*, state: GameState, replacement: UnitInstance) -> None:
    state.replace_army_definitions(
        [
            replace(
                army,
                units=tuple(
                    replacement
                    if candidate.unit_instance_id == replacement.unit_instance_id
                    else candidate
                    for candidate in army.units
                ),
            )
            for army in state.army_definitions
        ]
    )


def _primary_destruction_payload(
    replay_payload: ReplayArtifactPayload,
) -> dict[str, JsonValue]:
    state_payload = cast(dict[str, JsonValue], replay_payload["initial_lifecycle"]["state"])
    destructions = cast(list[JsonValue], state_payload["primary_unit_destruction_states"])
    assert len(destructions) == 1
    return cast(dict[str, JsonValue], destructions[0])


def _setup_config(*, game_id: str) -> GameConfig:
    source_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        source_catalog,
        detachments=tuple(
            replace(
                detachment,
                force_disposition_ids=("purge-the-foe", "take-and-hold"),
            )
            if detachment.detachment_id == "core-combined-arms"
            else detachment
            for detachment in source_catalog.detachments
        ),
    )
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
                force_disposition_id="take-and-hold",
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-2",),
                force_disposition_id="purge-the-foe",
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
            attacker_force_disposition_id="take-and-hold",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
        ),
    )


def _combat_config(*, game_id: str, attached_target: bool = False) -> GameConfig:
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
                force_disposition_id="purge-the-foe",
            ),
            (
                _attached_target_muster_request(catalog=catalog)
                if attached_target
                else _army_muster_request(
                    catalog=catalog,
                    player_id="player-b",
                    army_id="army-beta",
                    unit_selection_ids=("target",),
                    force_disposition_id="purge-the-foe",
                )
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_open_mission_setup(),
    )


def _open_mission_setup() -> MissionSetup:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    return MissionSetup(
        mission_pack_id=mission_pack.mission_pack_id,
        source_version=mission_pack.source_version,
        source_id=mission_pack.source_id,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-3",
        primary_mission_assignments=(
            PlayerPrimaryMissionAssignment(
                player_id="player-a",
                force_disposition_id="purge-the-foe",
                primary_mission_id="primary-meatgrinder",
            ),
            PlayerPrimaryMissionAssignment(
                player_id="player-b",
                force_disposition_id="purge-the-foe",
                primary_mission_id="primary-meatgrinder",
            ),
        ),
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
    force_disposition_id: str,
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
        force_disposition_id=force_disposition_id,
        unit_selections=tuple(_unit_selection(unit_id) for unit_id in unit_selection_ids),
    )


def _attached_target_muster_request(*, catalog: ArmyCatalog) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id="army-beta",
        player_id="player-b",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=(
            _unit_selection("target"),
            UnitMusterSelection(
                unit_selection_id="target-leader",
                datasheet_id="core-character-leader",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="target-leader",
                bodyguard_unit_selection_id="target",
            ),
        ),
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


def _event_layout_replay_payload() -> tuple[ReplayArtifactPayload, MissionSetup]:
    layout_id = "purge-the-foe-vs-purge-the-foe-layout-2"
    event_setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id=f"mission-{layout_id}",
        terrain_layout_id=layout_id,
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    base_config = _setup_config(game_id="phase18b-event-layout-drift")
    config = replace(
        base_config,
        ruleset_descriptor=(
            RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
                descriptor_version="core-v2-phase18b-event-layout-test"
            )
        ),
        army_muster_requests=tuple(
            replace(request, force_disposition_id="purge-the-foe")
            for request in base_config.army_muster_requests
        ),
        mission_setup=event_setup,
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.advance_until_decision_or_terminal()
    artifact = ReplayArtifact.capture(
        artifact_id="phase18b-event-layout-drift",
        initial_lifecycle_payload=_lifecycle_payload_copy(lifecycle),
        final_lifecycle=lifecycle,
    )
    payload = _artifact_payload_copy(artifact)
    assert ReplayArtifact.from_payload(payload).to_payload() == payload
    return payload, event_setup


def _translated_terrain_feature(
    feature: TerrainFeatureDefinition,
    *,
    x_delta: float,
    y_delta: float,
) -> TerrainFeatureDefinition:
    return replace(
        feature,
        footprint_center_x_inches=feature.footprint_center_x_inches + x_delta,
        footprint_center_y_inches=feature.footprint_center_y_inches + y_delta,
        rules_footprint_polygon=tuple(
            replace(
                point,
                x_inches=point.x_inches + x_delta,
                y_inches=point.y_inches + y_delta,
            )
            for point in feature.rules_footprint_polygon
        ),
        display_geometry=replace(
            feature.display_geometry,
            footprint_polygon=tuple(
                replace(
                    point,
                    x_inches=point.x_inches + x_delta,
                    y_inches=point.y_inches + y_delta,
                )
                for point in feature.display_geometry.footprint_polygon
            ),
        ),
        walls=tuple(
            replace(
                wall,
                center_x_inches=wall.center_x_inches + x_delta,
                center_y_inches=wall.center_y_inches + y_delta,
            )
            for wall in feature.walls
        ),
        floors=tuple(
            replace(
                floor,
                center_x_inches=floor.center_x_inches + x_delta,
                center_y_inches=floor.center_y_inches + y_delta,
            )
            for floor in feature.floors
        ),
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
