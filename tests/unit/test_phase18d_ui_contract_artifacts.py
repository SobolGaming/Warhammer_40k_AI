from __future__ import annotations

# pyright: reportPrivateUsage=false
import hashlib
import json
import re
import runpy
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import Protocol, cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Resource
from referencing.jsonschema import (
    DRAFT202012,
    EMPTY_REGISTRY,
    Schema,
    SchemaRegistry,
    SchemaResource,
)
from scripts.export_ui_contract_fixtures import (
    BATTLEFIELD_EXAMPLE_DIR,
    DECISION_EXAMPLE_DIR,
    MODEL_ALPHA_1,
    PLAYER_A,
    PLAYER_B,
    PROPOSAL_EXAMPLE_DIR,
    UI_FIXTURE_DIR,
    UNIT_ALPHA,
    UNIT_BETA,
    build_local_session_at_movement_request,
    export_ui_contract_files,
)

from warhammer40k_core.adapters.battlefield_projection import (
    BATTLEFIELD_COORDINATE_SPACE,
    BATTLEFIELD_COORDINATE_SPEC_VERSION,
    BATTLEFIELD_VIEW_SCHEMA_VERSION,
    BattlefieldViewPayload,
    _model_geometry,
    _model_state,
    _polygon_shape,
    _terrain_feature_entity,
    authoritative_geometry_hash,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.external_contract import (
    DECISION_REQUEST_VIEW_SCHEMA_VERSION,
    LIFECYCLE_STATUS_SCHEMA_VERSION,
    SESSION_COMMAND_OUTCOME_SCHEMA_VERSION,
    SESSION_COMMAND_RESULT_SCHEMA_VERSION,
    SESSION_METADATA_SCHEMA_VERSION,
    SESSION_PROJECTION_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.projection import (
    PROJECTION_SCHEMA_VERSION,
    GameViewPayload,
    _projection_state_hash,
    project_rules_catalog_view,
)
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.detachment import StratagemDefinition
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_areas import TerrainAreaClassification
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.interaction_metadata import (
    InteractionKind,
    registered_interaction_decision_types,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.reserves import ReserveStatus
from warhammer40k_core.geometry.model_geometry import (
    BaseFootprintKind,
    FootprintPart,
    GeometrySourceKind,
    HeightSourceKind,
    ModelGeometry,
)
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MEMORY_REPR_PATTERN = re.compile(r"<[^>\n]+ object at 0x[0-9a-fA-F]+>")
FORBIDDEN_UI_STATE_KEYS = frozenset(
    {
        "adapter_state",
        "component_state",
        "dom_state",
        "render_state",
        "ui_state",
    }
)
SCHEMA_FILES = (
    Path("contracts/schemas/battlefield-view.schema.json"),
    Path("contracts/schemas/create-session.schema.json"),
    Path("contracts/schemas/decision-family-coverage.schema.json"),
    Path("contracts/schemas/decision-family-live.schema.json"),
    Path("contracts/schemas/decision-request-view.schema.json"),
    Path("contracts/schemas/annotated-decision-request.schema.json"),
    Path("contracts/schemas/event-delta.schema.json"),
    Path("contracts/schemas/game-view.schema.json"),
    Path("contracts/schemas/interaction-descriptor.schema.json"),
    Path("contracts/schemas/lifecycle-status.schema.json"),
    Path("contracts/schemas/replay-metadata.schema.json"),
    Path("contracts/schemas/rules-catalog.schema.json"),
    Path("contracts/schemas/session-metadata.schema.json"),
)
FIXTURE_FILES = (
    "hidden_secondary_redaction_view.json",
    "initial_setup_view_player1.json",
    "initial_setup_view_player2.json",
    "pending_movement_request.json",
    "post_deployment_view.json",
    "rules_catalog_view.json",
    "terrain_snapshot_hidden_reserve_view_player_a.json",
    "terrain_snapshot_hidden_reserve_view_player_b.json",
    "visible_modifier_datacard_view.json",
)
GAME_VIEW_FIXTURE_FILES = (
    "hidden_secondary_redaction_view.json",
    "initial_setup_view_player1.json",
    "initial_setup_view_player2.json",
    "post_deployment_view.json",
    "terrain_snapshot_hidden_reserve_view_player_a.json",
    "terrain_snapshot_hidden_reserve_view_player_b.json",
    "visible_modifier_datacard_view.json",
)
PROPOSAL_EXAMPLE_FILES = (
    "charge_move.json",
    "deployment_placement.json",
    "melee_declaration.json",
    "movement_path_witness.json",
    "shooting_target_selection.json",
)
DECISION_FAMILY_COVERAGE_PATH = Path("contracts/examples/decisions/family-coverage.json")
BATTLEFIELD_GEOMETRY_CONFORMANCE_PATH = BATTLEFIELD_EXAMPLE_DIR / "geometry-conformance.json"


class _PayloadValidator(Protocol):
    def validate(self, instance: object) -> None: ...

    def iter_errors(self, instance: object) -> Iterable[object]: ...


class _ContractSnapshotVerifier(Protocol):
    def __call__(
        self,
        *,
        reference_label: str,
        reference_version: str,
        reference_schemas: dict[str, JsonValue],
        reference_operations: set[str],
        current_version: str,
        current_schemas: dict[str, Schema],
        current_operations: set[str],
        require_version_progress: bool,
    ) -> None: ...


def test_ui_contract_artifacts_are_json_safe_and_scrubbed() -> None:
    paths = (
        *SCHEMA_FILES,
        BATTLEFIELD_GEOMETRY_CONFORMANCE_PATH,
        *(_fixture_path(name) for name in FIXTURE_FILES),
        *(PROPOSAL_EXAMPLE_DIR / name for name in PROPOSAL_EXAMPLE_FILES),
        DECISION_EXAMPLE_DIR / "opportunity_window.json",
        DECISION_FAMILY_COVERAGE_PATH,
        *sorted((REPO_ROOT / DECISION_EXAMPLE_DIR / "families").glob("*.json")),
    )

    for path in paths:
        payload = _read_json(REPO_ROOT / path)
        round_trip = json.loads(json.dumps(payload, sort_keys=True))
        encoded = json.dumps(payload, sort_keys=True)

        assert validate_json_value(round_trip) == payload
        assert not MEMORY_REPR_PATTERN.search(encoded)
        assert "object at 0x" not in encoded
        _assert_no_ui_owned_state(payload)


def test_ui_contract_schemas_validate_generated_and_live_payloads() -> None:
    registry = _schema_registry()
    for schema_payload in _schema_payloads().values():
        Draft202012Validator.check_schema(schema_payload)

    game_view_validator = _schema_validator(
        "game-view.schema.json",
        registry=registry,
    )
    for fixture_name in GAME_VIEW_FIXTURE_FILES:
        game_view_validator.validate(_fixture(fixture_name))

    _schema_validator("battlefield-view.schema.json", registry=registry).validate(
        _read_json(REPO_ROOT / BATTLEFIELD_GEOMETRY_CONFORMANCE_PATH)
    )

    _schema_validator("decision-request-view.schema.json", registry=registry).validate(
        _fixture("pending_movement_request.json")
    )
    coverage = _read_json(REPO_ROOT / DECISION_FAMILY_COVERAGE_PATH)
    _schema_validator("decision-family-coverage.schema.json", registry=registry).validate(coverage)
    live_validator = _schema_validator("decision-family-live.schema.json", registry=registry)
    for path in sorted((REPO_ROOT / DECISION_EXAMPLE_DIR / "families").glob("*.json")):
        live_validator.validate(_read_json(path))

    session, _status = build_local_session_at_movement_request(
        game_id="ui-contract-schema-validation"
    )
    rules_catalog_validator = _schema_validator("rules-catalog.schema.json", registry=registry)
    rules_catalog_validator.validate(_fixture("rules_catalog_view.json"))
    rules_catalog_validator.validate(session.rules_catalog_view())
    assert (
        session.events_since(EventStreamCursor(0), viewer_player_id=PLAYER_A)["schema_version"]
        == "event-delta-v4-phase17n-step4"
    )


def test_phase17n_projection_family_versions_cover_the_new_closed_shapes() -> None:
    game_view_schema = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/game-view.schema.json"))
    )
    game_view_properties = _json_object(game_view_schema["properties"])
    game_view_required = {_json_string(value) for value in _json_list(game_view_schema["required"])}
    battlefield_schema = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/battlefield-view.schema.json"))
    )
    battlefield_properties = _json_object(battlefield_schema["properties"])
    battlefield_defs = _json_object(battlefield_schema["$defs"])
    terrain_feature = _json_object(battlefield_defs["terrain_feature"])
    terrain_area = _json_object(battlefield_defs["terrain_area"])

    assert (
        _json_object(game_view_properties["projection_schema"])["const"]
        == PROJECTION_SCHEMA_VERSION
        == "game-view-v11-phase17n-step4"
    )
    assert "primary_rules_unit_turn_start_snapshots" in game_view_required
    assert "primary_mission_progress_state" in game_view_required
    assert (
        _json_object(battlefield_properties["schema_version"])["const"]
        == BATTLEFIELD_VIEW_SCHEMA_VERSION
        == "battlefield-view-v4-phase17n-step3"
    )
    assert battlefield_schema["$id"] == (
        "https://warhammer40k-core.local/contracts/v6/battlefield-view.schema.json"
    )
    battlefield_view_schema = _json_object(game_view_properties["battlefield_view"])
    battlefield_view_options = _json_list(battlefield_view_schema["oneOf"])
    assert {
        _json_string(option["$ref"])
        for option in map(_json_object, battlefield_view_options)
        if "$ref" in option
    } == {"https://warhammer40k-core.local/contracts/v6/battlefield-view.schema.json"}
    assert "classification" in {
        _json_string(value) for value in _json_list(terrain_feature["required"])
    }
    assert "logical_terrain_area_id" in {
        _json_string(value) for value in _json_list(terrain_area["required"])
    }


def test_phase17n_unresolved_formation_redaction_versions_nested_payload_families() -> None:
    decision_request_schema = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/decision-request-view.schema.json"))
    )
    lifecycle_status_schema = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/lifecycle-status.schema.json"))
    )
    game_view_schema = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/game-view.schema.json"))
    )
    session_metadata_schema = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/session-metadata.schema.json"))
    )
    decision_family_schema = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/decision-family-live.schema.json"))
    )

    decision_request_uri = (
        "https://warhammer40k-core.local/contracts/v6/decision-request-view.schema.json"
    )
    lifecycle_status_uri = (
        "https://warhammer40k-core.local/contracts/v4/lifecycle-status.schema.json"
    )
    assert decision_request_schema["$id"] == decision_request_uri
    assert (
        _json_object(_json_object(decision_request_schema["properties"])["schema_version"])["const"]
        == DECISION_REQUEST_VIEW_SCHEMA_VERSION
        == "decision-request-view-v5-phase17n-step4"
    )
    assert lifecycle_status_schema["$id"] == lifecycle_status_uri
    assert (
        _json_object(_json_object(lifecycle_status_schema["properties"])["schema_version"])["const"]
        == LIFECYCLE_STATUS_SCHEMA_VERSION
        == "lifecycle-status-v4-phase17n-step4"
    )

    pending_decision_schema = _json_object(
        _json_object(game_view_schema["properties"])["pending_decision"]
    )
    assert {
        _json_string(option["$ref"])
        for option in map(_json_object, _json_list(pending_decision_schema["oneOf"]))
        if "$ref" in option
    } == {decision_request_uri}
    lifecycle_status_ref = _json_object(
        _json_object(session_metadata_schema["properties"])["lifecycle_status"]
    )
    assert lifecycle_status_ref["$ref"] == f"{lifecycle_status_uri}#/$defs/status"

    assert decision_family_schema["$id"] == (
        "https://warhammer40k-core.local/contracts/v7/decision-family-live.schema.json"
    )
    decision_family_defs = _json_object(decision_family_schema["$defs"])
    for family_name in (
        "select_secondary_missions",
        "select_movement_unit",
        "select_movement_action",
        "submit_movement_proposal",
    ):
        family = _json_object(decision_family_defs[family_name])
        inherited_request = _json_object(_json_list(family["allOf"])[0])
        assert inherited_request["$ref"] == decision_request_uri


def test_phase17n_post_reveal_reserve_and_snapshot_history_are_public() -> None:
    opponent_view = _fixture("terrain_snapshot_hidden_reserve_view_player_a.json")
    owner_view = _fixture("terrain_snapshot_hidden_reserve_view_player_b.json")
    opponent_snapshots = _json_list(opponent_view["primary_rules_unit_turn_start_snapshots"])
    owner_snapshots = _json_list(owner_view["primary_rules_unit_turn_start_snapshots"])

    assert len(opponent_snapshots) == len(owner_snapshots) == 1
    opponent_snapshot = _json_object(opponent_snapshots[0])
    owner_snapshot = _json_object(owner_snapshots[0])
    for metadata_key in (
        "snapshot_id",
        "game_id",
        "active_player_id",
        "battle_round",
        "source_id",
    ):
        assert opponent_snapshot[metadata_key] == owner_snapshot[metadata_key]

    opponent_membership_ids = {
        _json_string(_json_object(component)["unit_instance_id"])
        for membership in _json_list(opponent_snapshot["rules_unit_memberships"])
        for component in _json_list(_json_object(membership)["component_memberships"])
    }
    owner_membership_ids = {
        _json_string(_json_object(component)["unit_instance_id"])
        for membership in _json_list(owner_snapshot["rules_unit_memberships"])
        for component in _json_list(_json_object(membership)["component_memberships"])
    }
    assert opponent_membership_ids == set(_json_object(opponent_view["unit_display_by_id"]))
    assert owner_membership_ids == set(_json_object(owner_view["unit_display_by_id"]))
    assert opponent_membership_ids == owner_membership_ids
    assert UNIT_BETA in opponent_membership_ids
    assert UNIT_BETA in owner_membership_ids
    assert UNIT_BETA in _json_object(opponent_view["unit_display_by_id"])
    assert UNIT_BETA in _json_object(owner_view["unit_display_by_id"])
    assert UNIT_BETA in json.dumps(opponent_snapshots, sort_keys=True)
    assert UNIT_BETA in json.dumps(owner_snapshots, sort_keys=True)


def test_game_view_schema_requires_logical_terrain_area_identity() -> None:
    registry = _schema_registry()
    validator = _schema_validator("game-view.schema.json", registry=registry)
    view = _json_object(
        _read_json(REPO_ROOT / Path("contracts/examples/projections/post_deployment_view.json"))
    )
    validator.validate(view)
    mission_setup = _json_object(view["mission_setup"])
    terrain_areas = _json_list(mission_setup["terrain_areas"])
    terrain_areas.append({"terrain_area_id": "physical-area-without-logical-identity"})

    with pytest.raises(ValidationError):
        validator.validate(view)


def test_live_movement_proposal_schema_requires_spatial_context_hash() -> None:
    registry = _schema_registry()
    validator = _schema_validator("decision-family-live.schema.json", registry=registry)
    payload = _read_json(
        REPO_ROOT / DECISION_EXAMPLE_DIR / "families" / "submit_movement_proposal.json"
    )
    without_spatial_context = json.loads(json.dumps(payload))
    proposal_request = without_spatial_context["payload"]["proposal_request"]
    proposal_request.pop("spatial_context_hash")

    with pytest.raises(ValidationError):
        validator.validate(without_spatial_context)


def test_session_metadata_contract_version_accepts_compatible_major_ten_releases() -> None:
    registry = _schema_registry()
    validator = _schema_validator("session-metadata.schema.json", registry=registry)
    metadata = _read_json(
        REPO_ROOT / Path("contracts/examples/sessions/session-metadata-created.json")
    )
    compatible = {**_json_object(metadata), "server_contract_version": "10.1.0"}
    incompatible = {**_json_object(metadata), "server_contract_version": "9.3.0"}

    validator.validate(compatible)
    with pytest.raises(ValidationError):
        validator.validate(incompatible)


def test_contract_ten_advances_only_affected_session_wrapper_families() -> None:
    metadata = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/session-metadata.schema.json"))
    )
    result = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/session-command-result.schema.json"))
    )
    outcome = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/session-command-outcome.schema.json"))
    )
    projection = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/session-projection.schema.json"))
    )

    assert metadata["$id"] == (
        "https://warhammer40k-core.local/contracts/v10/session-metadata.schema.json"
    )
    assert result["$id"] == (
        "https://warhammer40k-core.local/contracts/v10/session-command-result.schema.json"
    )
    assert outcome["$id"] == (
        "https://warhammer40k-core.local/contracts/v10/session-command-outcome.schema.json"
    )
    assert (
        _json_object(_json_object(metadata["properties"])["schema_version"])["const"]
        == SESSION_METADATA_SCHEMA_VERSION
        == "session-metadata-v10-contract"
    )
    assert (
        _json_object(_json_object(result["properties"])["schema_version"])["const"]
        == SESSION_COMMAND_RESULT_SCHEMA_VERSION
        == "session-command-result-v10-contract"
    )
    assert (
        _json_object(_json_object(outcome["properties"])["schema_version"])["const"]
        == SESSION_COMMAND_OUTCOME_SCHEMA_VERSION
        == "session-command-outcome-v10-contract"
    )
    assert (
        _json_object(_json_object(projection["properties"])["schema_version"])["const"]
        == SESSION_PROJECTION_SCHEMA_VERSION
        == "session-projection-v7-phase17n-step4"
    )


@pytest.mark.parametrize("field_name", ["ruleset_descriptor_hash", "rules_overlay_ids"])
def test_session_metadata_schema_rejects_missing_rules_overlay_identity(field_name: str) -> None:
    validator = _schema_validator("session-metadata.schema.json", registry=_schema_registry())
    metadata = _json_object(
        _read_json(REPO_ROOT / Path("contracts/examples/sessions/session-metadata-created.json"))
    )
    metadata.pop(field_name)

    with pytest.raises(ValidationError):
        validator.validate(metadata)


def test_replay_metadata_schema_rejects_missing_rules_overlay_identity() -> None:
    replay_schema = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/replay-metadata.schema.json"))
    )
    assert replay_schema["$id"] == (
        "https://warhammer40k-core.local/contracts/v8/replay-metadata.schema.json"
    )
    validator = _schema_validator("replay-metadata.schema.json", registry=_schema_registry())
    replay = _json_object(_read_json(REPO_ROOT / Path("contracts/examples/replay-metadata.json")))
    source_identity = _json_object(replay["source_identity"])
    source_identity.pop("rules_overlay_ids")

    with pytest.raises(ValidationError):
        validator.validate(replay)


def test_replay_metadata_schema_requires_closed_step5a_scoring_state_evidence() -> None:
    replay_schema = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/replay-metadata.schema.json"))
    )
    initial_lifecycle = _json_object(_json_object(replay_schema["properties"])["initial_lifecycle"])
    state = _json_object(_json_object(initial_lifecycle["properties"])["state"])
    assert state["$ref"] == "#/$defs/step5a_replay_state"

    definitions = _json_object(replay_schema["$defs"])
    replay_state = _json_object(definitions["step5a_replay_state"])
    replay_state_required = {_json_string(value) for value in _json_list(replay_state["required"])}
    assert "objective_control_record_authorities" in replay_state_required
    assert "primary_scoring_state_evidence_records" in replay_state_required
    authority_collection = _json_object(
        _json_object(replay_state["properties"])["objective_control_record_authorities"]
    )
    assert _json_object(authority_collection["items"])["$ref"] == (
        "#/$defs/objective_control_record_authority"
    )
    evidence_collection = _json_object(
        _json_object(replay_state["properties"])["primary_scoring_state_evidence_records"]
    )
    assert _json_object(evidence_collection["items"])["$ref"] == (
        "#/$defs/primary_scoring_state_evidence"
    )

    evidence = _json_object(definitions["primary_scoring_state_evidence"])
    assert evidence["additionalProperties"] is False
    assert {_json_string(value) for value in _json_list(evidence["required"])} == set(
        _json_object(evidence["properties"])
    )
    destruction_ids = _json_object(
        _json_object(evidence["properties"])["primary_unit_destruction_state_ids"]
    )
    assert destruction_ids["uniqueItems"] is True
    assert _json_object(destruction_ids["items"])["type"] == "string"
    spatial_collection = _json_object(
        _json_object(evidence["properties"])["primary_scoring_spatial_evidence_by_player_id"]
    )
    assert _json_object(spatial_collection["items"])["$ref"] == (
        "#/$defs/primary_scoring_spatial_evidence"
    )
    witness = _json_object(definitions["primary_scoring_rules_unit_position_witness"])
    membership = _json_object(_json_object(witness["properties"])["rules_unit_membership"])
    assert membership["$ref"] == (
        "https://warhammer40k-core.local/contracts/v8/game-view.schema.json"
        "#/$defs/primary_rules_unit_turn_start_membership"
    )
    for definition_name in (
        "objective_control_record_authority",
        "primary_mission_boundary_checkpoint",
        "primary_mission_boundary_model_state",
        "primary_mission_objective_control_modifier_source",
        "sticky_objective_control_state",
        "primary_scoring_spatial_evidence",
        "primary_table_quarter_unit_witness",
        "primary_territory_unit_witness",
    ):
        definition = _json_object(definitions[definition_name])
        assert definition["additionalProperties"] is False
        assert {_json_string(value) for value in _json_list(definition["required"])} == set(
            _json_object(definition["properties"])
        )

    game_view_schema = _json_object(
        _read_json(REPO_ROOT / Path("contracts/schemas/game-view.schema.json"))
    )
    assert "primary_scoring_state_evidence_records" not in _json_object(
        game_view_schema["properties"]
    )


@pytest.mark.parametrize(
    "nulled_field",
    ["mission_pack_id", "mission_source_package_hash"],
)
def test_replay_metadata_schema_rejects_partial_mission_source_identity(
    nulled_field: str,
) -> None:
    validator = _schema_validator("replay-metadata.schema.json", registry=_schema_registry())
    replay = _json_object(_read_json(REPO_ROOT / Path("contracts/examples/replay-metadata.json")))
    source_identity = _json_object(replay["source_identity"])
    assert source_identity["mission_pack_id"] is not None
    assert source_identity["mission_source_package_hash"] is not None
    source_identity[nulled_field] = None

    with pytest.raises(ValidationError):
        validator.validate(replay)


def test_replay_metadata_schema_accepts_absent_mission_source_identity_pair() -> None:
    validator = _schema_validator("replay-metadata.schema.json", registry=_schema_registry())
    replay = _json_object(_read_json(REPO_ROOT / Path("contracts/examples/replay-metadata.json")))
    source_identity = _json_object(replay["source_identity"])
    source_identity["mission_pack_id"] = None
    source_identity["mission_source_package_hash"] = None

    validator.validate(replay)


def test_replay_metadata_schema_requires_logical_terrain_area_identity() -> None:
    registry = _schema_registry()
    validator = _schema_validator("replay-metadata.schema.json", registry=registry)
    replay = _json_object(_read_json(REPO_ROOT / Path("contracts/examples/replay-metadata.json")))
    initial_lifecycle = _json_object(replay["initial_lifecycle"])
    config = _json_object(initial_lifecycle["config"])
    mission_setup = _json_object(config["mission_setup"])
    terrain_areas = _json_list(mission_setup["terrain_areas"])
    assert terrain_areas
    first_area = _json_object(terrain_areas[0])
    assert first_area.pop("logical_terrain_area_id")

    with pytest.raises(ValidationError):
        validator.validate(replay)


@pytest.mark.parametrize(
    "state_field",
    [
        None,
        "primary_rules_unit_turn_start_snapshots",
        "primary_unit_destruction_states",
        "primary_battlefield_departure_states",
    ],
    ids=("state", "turn-start-snapshots", "destructions", "departures"),
)
def test_replay_v6_schema_requires_step3_state_slice(state_field: str | None) -> None:
    validator = _schema_validator("replay-metadata.schema.json", registry=_schema_registry())
    replay = _json_object(_read_json(REPO_ROOT / Path("contracts/examples/replay-metadata.json")))
    initial_lifecycle = _json_object(replay["initial_lifecycle"])
    if state_field is None:
        initial_lifecycle.pop("state")
    else:
        state = _json_object(initial_lifecycle["state"])
        state.pop(state_field)

    with pytest.raises(ValidationError):
        validator.validate(replay)


def test_replay_v6_schema_closes_step3_destruction_and_departure_rows() -> None:
    validator = _schema_validator("replay-metadata.schema.json", registry=_schema_registry())
    replay = _json_object(_read_json(REPO_ROOT / Path("contracts/examples/replay-metadata.json")))
    state = _json_object(_json_object(replay["initial_lifecycle"])["state"])
    destruction: dict[str, JsonValue] = {
        "destruction_id": "phase17n-destruction",
        "game_id": "phase18d-contract-session",
        "destroying_player_id": "player-a",
        "destruction_attribution": {
            "destroying_player_id": "player-a",
            "source_rules_unit_instance_id": "army-alpha:unit-a",
            "source_model_instance_id": "army-alpha:unit-a:model-001",
            "attacking_unit_instance_id": None,
            "attacking_model_instance_id": None,
            "destruction_provenance": {
                "destruction_source_kind": "ability",
                "attack_kind": "none",
                "source_weapon_profile": None,
                "attack_context_id": None,
            },
        },
        "source_model_destroyed_event_id": "event-000001",
        "source_rules_unit_objective_proximity_witness": {
            "rules_unit_instance_id": "army-alpha:unit-a",
            "component_unit_instance_ids": ["army-alpha:unit-a"],
            "objective_marker_witnesses": [],
        },
        "source_battlefield_departure_ids": ["phase17n-departure"],
        "unattributed_cause": None,
        "source_mutation_id": None,
        "destroyed_player_id": "player-b",
        "active_player_id": "player-a",
        "battle_round": 1,
        "phase": "shooting",
        "destroyed_unit_instance_id": "army-beta:unit-b",
        "started_turn_terrain_feature_ids": [],
        "started_turn_objective_marker_ids": [],
        "source_id": "core-rules:primary-unit-destruction-tracking:event-000001",
    }
    departure: dict[str, JsonValue] = {
        "departure_id": "phase17n-departure",
        "game_id": "phase18d-contract-session",
        "owner_player_id": "player-b",
        "rules_unit_instance_id": "army-beta:unit-b",
        "component_unit_instance_ids": ["army-beta:unit-b"],
        "affected_component_unit_instance_ids": ["army-beta:unit-b"],
        "departed_component_unit_instance_ids": ["army-beta:unit-b"],
        "removed_model_instance_ids": ["army-beta:unit-b:model-001"],
        "battle_round": 1,
        "active_player_id": "player-a",
        "phase": "shooting",
        "removal_kind": "destroyed",
        "occurrence_id": "event-000001",
        "source_id": "core-rules:primary-unit-destruction-tracking:event-000001",
    }
    state["primary_unit_destruction_states"] = [destruction]
    state["primary_battlefield_departure_states"] = [departure]
    validator.validate(replay)

    destruction["unexpected"] = True
    with pytest.raises(ValidationError):
        validator.validate(replay)
    destruction.pop("unexpected")
    departure["unexpected"] = True
    with pytest.raises(ValidationError):
        validator.validate(replay)


def test_contract_three_payloads_are_rejected_by_closed_contract_two_client_schemas() -> None:
    baseline = _read_json(REPO_ROOT / Path("contracts/compatibility/2.0.0-shape.json"))
    old_schemas = cast(dict[str, Schema], _json_object(baseline["schemas"]))
    old_registry = EMPTY_REGISTRY
    for schema in old_schemas.values():
        schema_id = _json_string(_json_object(cast(JsonValue, schema))["$id"])
        old_registry = old_registry.with_resource(
            schema_id,
            cast(
                SchemaResource,
                Resource.from_contents(schema, default_specification=DRAFT202012),
            ),
        )

    current_decision = _fixture("pending_movement_request.json")
    current_support = _read_json(REPO_ROOT / Path("contracts/examples/support-profile.json"))
    old_decision = cast(
        _PayloadValidator,
        Draft202012Validator(
            old_schemas["decision-request-view.schema.json"],
            registry=old_registry,
        ),
    )
    old_support = cast(
        _PayloadValidator,
        Draft202012Validator(
            old_schemas["support-profile.schema.json"],
            registry=old_registry,
        ),
    )

    assert list(old_decision.iter_errors(current_decision))
    assert list(old_support.iter_errors(current_support))


def test_rules_catalog_schema_requires_catalog_card_detail_maps() -> None:
    schema = _read_json(REPO_ROOT / Path("contracts/schemas/rules-catalog.schema.json"))
    properties = _json_object(schema["properties"])
    required = {_json_string(value) for value in _json_list(schema["required"])}

    assert {"army_rule_display_by_id", "stratagem_display_by_id"}.issubset(required)
    assert (
        _json_object(_json_object(properties["army_rule_display_by_id"])["additionalProperties"])[
            "$ref"
        ]
        == "#/$defs/army_rule_display"
    )
    assert (
        _json_object(_json_object(properties["stratagem_display_by_id"])["additionalProperties"])[
            "$ref"
        ]
        == "#/$defs/stratagem_display"
    )


def test_exporter_reproduces_committed_ui_contract_payloads(tmp_path: Path) -> None:
    export_ui_contract_files(output_root=tmp_path)

    paths = (
        *(_fixture_path(name) for name in FIXTURE_FILES),
        *(PROPOSAL_EXAMPLE_DIR / name for name in PROPOSAL_EXAMPLE_FILES),
        DECISION_EXAMPLE_DIR / "opportunity_window.json",
    )
    for path in paths:
        assert _read_json(tmp_path / path) == _read_json(REPO_ROOT / path)


def test_ui_contract_fixtures_expose_stable_joinable_viewer_payloads() -> None:
    post_deployment = _fixture("post_deployment_view.json")
    rules_catalog_ref = _json_object(post_deployment["rules_catalog"])
    battlefield = _json_object(post_deployment["battlefield_state"])

    assert rules_catalog_ref["catalog_id"] == "phase9a-canonical"
    assert rules_catalog_ref["source_package_id"] == "data-package:core-v2:phase9a-canonical:0.1.0"
    assert len(cast(str, rules_catalog_ref["source_hash"])) == 64
    assert post_deployment["viewer_player_id"] == PLAYER_A
    assert post_deployment["stage"] == "battle"
    assert post_deployment["current_battle_phase"] == "movement"

    unit_display_by_id = cast(dict[str, JsonValue], post_deployment["unit_display_by_id"])
    model_display_by_id = cast(dict[str, JsonValue], post_deployment["model_display_by_id"])
    for placed_army_value in _json_list(battlefield["placed_armies"]):
        placed_army = _json_object(placed_army_value)
        for unit_placement_value in _json_list(placed_army["unit_placements"]):
            unit_placement = _json_object(unit_placement_value)
            unit_id = _json_string(unit_placement["unit_instance_id"])
            assert unit_id in unit_display_by_id
            unit_display = _json_object(unit_display_by_id[unit_id])
            assert unit_display["unit_instance_id"] == unit_id
            for model_placement_value in _json_list(unit_placement["model_placements"]):
                model_placement = _json_object(model_placement_value)
                model_id = _json_string(model_placement["model_instance_id"])
                assert model_id in model_display_by_id
                model_display = _json_object(model_display_by_id[model_id])
                assert model_display["unit_instance_id"] == unit_id


def test_phase18j_battlefield_projection_is_typed_joinable_and_viewer_scoped() -> None:
    registry = _schema_registry()
    battlefield_validator = _schema_validator(
        "battlefield-view.schema.json",
        registry=registry,
    )
    owner_view = cast(GameViewPayload, _fixture("post_deployment_view.json"))
    battlefield = owner_view["battlefield_view"]
    assert battlefield is not None

    battlefield_validator.validate(battlefield)
    assert battlefield["schema_version"] == BATTLEFIELD_VIEW_SCHEMA_VERSION
    assert battlefield["coordinate_spec_version"] == BATTLEFIELD_COORDINATE_SPEC_VERSION
    assert battlefield["coordinate_space"] == BATTLEFIELD_COORDINATE_SPACE
    assert battlefield["bounds"] == {
        "min_x_inches": 0.0,
        "min_y_inches": 0.0,
        "min_z_inches": 0.0,
        "max_x_inches": 44.0,
        "max_y_inches": 60.0,
    }
    authoritative = battlefield["authoritative"]
    assert set(authoritative["models_by_id"]) == set(owner_view["model_display_by_id"])
    assert len(authoritative["objectives_by_id"]) == 6
    assert len(authoritative["deployment_zones_by_id"]) == 2
    assert all(
        "marker_diameter_inches" in objective and "marker_diameter_mm" not in objective
        for objective in authoritative["objectives_by_id"].values()
    )
    for zone in authoritative["deployment_zones_by_id"].values():
        for polygon in zone["shape"]["polygons"]:
            twice_area = sum(
                point["x_inches"] * polygon[(index + 1) % len(polygon)]["y_inches"]
                - polygon[(index + 1) % len(polygon)]["x_inches"] * point["y_inches"]
                for index, point in enumerate(polygon)
            )
            assert twice_area > 0.0
    assert all(
        model["pose"] is not None and 0.0 <= model["pose"]["facing_degrees"] < 360.0
        for model in authoritative["models_by_id"].values()
    )
    pending = owner_view["pending_decision"]
    assert pending is not None
    legal_candidate_refs = battlefield["interaction"]["legal_candidate_refs"]
    assert [candidate["reference_id"] for candidate in legal_candidate_refs] == [
        option["option_id"] for option in pending["options"]
    ]

    opponent_view = cast(GameViewPayload, _fixture("initial_setup_view_player2.json"))
    opponent_battlefield = opponent_view["battlefield_view"]
    assert opponent_battlefield is not None
    opponent_models = opponent_battlefield["authoritative"]["models_by_id"]
    assert set(opponent_models) == set(opponent_view["model_display_by_id"])

    # Roster identity is public. Until Declare Battle Formations resolves, the
    # opponent receives no placement, reserve-kind, or transport-cargo state.
    opponent_model = opponent_models[MODEL_ALPHA_1]
    assert opponent_model["model_instance_id"] == MODEL_ALPHA_1
    assert opponent_model["unit_instance_id"] == UNIT_ALPHA
    assert opponent_model["owner_player_id"] == PLAYER_A
    assert opponent_model["state"] == "undeployed"
    assert opponent_model["pose"] is None
    assert opponent_model["state_context"] == {
        "reserve_kind": None,
        "transport_unit_instance_id": None,
    }
    assert opponent_battlefield["interaction"]["legal_candidate_refs"] == []


def test_phase18j_geometry_maps_round_oval_hull_support_and_terrain() -> None:
    session, _status = build_local_session_at_movement_request(game_id="phase18j-geometry-kinds")
    state = session.lifecycle.state
    assert state is not None
    model = state.army_definitions[0].units[0].own_models[0]

    round_geometry = _model_geometry(model)
    assert round_geometry["measurement_basis"] == "base"
    assert round_geometry["measurement_shapes"][0]["kind"] == "circle"
    round_support = round_geometry["support_shape"]
    assert round_support is not None
    assert round_support["kind"] == "circle"

    oval_base = BaseSizeDefinition.oval(length_mm=75.0, width_mm=42.0)
    oval_model = replace(
        model,
        base_size=oval_base,
        geometry=ModelGeometry.from_base_size(
            oval_base,
            geometry_source_id="phase18j-oval-profile",
        ),
    )
    oval_geometry = _model_geometry(oval_model)
    assert oval_geometry["measurement_shapes"][0]["kind"] == "ellipse"
    oval_support = oval_geometry["support_shape"]
    assert oval_support is not None
    assert oval_support["kind"] == "ellipse"

    hull_geometry = ModelGeometry(
        footprint_kind=BaseFootprintKind.HULL,
        parts=(
            FootprintPart(
                part_id="accepted-hull",
                footprint_kind=BaseFootprintKind.HULL,
                radius_x_inches=2.5,
                radius_y_inches=1.25,
            ),
        ),
        height_inches=3.0,
        geometry_source_kind=GeometrySourceKind.MANUAL_OVERRIDE,
        geometry_source_id="phase18j-accepted-hull",
        height_source_kind=HeightSourceKind.MANUAL_OVERRIDE,
        height_source_id="phase18j-accepted-height",
    )
    hull_model = replace(model, geometry=hull_geometry)
    hull_payload = _model_geometry(hull_model)
    assert hull_payload["measurement_basis"] == "hull"
    assert hull_payload["measurement_shapes"][0]["kind"] == "rectangle"
    hull_support = hull_payload["support_shape"]
    assert hull_support is not None
    assert hull_support["kind"] == "circle"

    terrain_source = _phase18j_terrain_feature()
    terrain = _terrain_feature_entity(terrain_source)
    assert terrain["classification"] == "dense"
    assert terrain["footprint"]["kind"] == "polygon"
    assert terrain["footprint"]["vertices"] == [
        {"x_inches": 7.0, "y_inches": 10.0},
        {"x_inches": 13.0, "y_inches": 10.0},
        {"x_inches": 13.0, "y_inches": 14.0},
        {"x_inches": 7.0, "y_inches": 14.0},
    ]
    assert {volume["volume_kind"] for volume in terrain["volumes"]} == {"wall", "floor"}
    assert {volume["bottom_center"]["z_inches"] for volume in terrain["volumes"]} == {0.0}
    assert "display_geometry" not in terrain
    render_only_change = replace(
        terrain_source,
        display_geometry=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=10.0,
            center_y_inches=12.0,
            width_inches=6.0,
            depth_inches=4.0,
            display_template_id="phase18j-other-render-asset",
        ),
    )
    assert _terrain_feature_entity(render_only_change) == terrain

    polygon = _polygon_shape(((0.0, 0.0), (0.0, 1.0), (1.0, 0.0)))
    assert polygon["kind"] == "polygon"
    assert polygon["vertices"] == [
        {"x_inches": 1.0, "y_inches": 0.0},
        {"x_inches": 0.0, "y_inches": 1.0},
        {"x_inches": 0.0, "y_inches": 0.0},
    ]


def test_phase18j_published_geometry_conformance_fixture_covers_declared_union() -> None:
    battlefield = cast(
        BattlefieldViewPayload,
        _read_json(REPO_ROOT / BATTLEFIELD_GEOMETRY_CONFORMANCE_PATH),
    )
    models = tuple(battlefield["authoritative"]["models_by_id"].values())
    measurement_kinds = {
        shape["kind"] for model in models for shape in model["geometry"]["measurement_shapes"]
    }
    support_kinds = {model["geometry"]["support_shape"]["kind"] for model in models}
    measurement_bases = {model["geometry"]["measurement_basis"] for model in models}

    assert measurement_kinds == {"circle", "ellipse", "rectangle"}
    assert support_kinds == {"circle", "ellipse"}
    assert measurement_bases == {"base", "hull"}
    assert all(model["pose"] is not None for model in models)
    assert all(
        model["pose"] is not None and model["pose"]["facing_degrees"] != 0.0 for model in models
    )

    terrain = battlefield["authoritative"]["terrain_features_by_id"]["geometry-conformance-terrain"]
    assert terrain["classification"] == "unknown"
    assert terrain["footprint"]["kind"] == "rectangle"
    assert {volume["volume_kind"] for volume in terrain["volumes"]} == {"wall", "floor"}
    terrain_area = battlefield["authoritative"]["terrain_areas_by_id"]["geometry-conformance-area"]
    assert terrain_area["footprint"]["kind"] == "polygon"
    assert terrain_area["logical_terrain_area_id"] == "geometry-conformance-area"
    logical_group_change = cast(
        BattlefieldViewPayload,
        json.loads(json.dumps(battlefield, sort_keys=True)),
    )
    logical_group_change["authoritative"]["terrain_areas_by_id"]["geometry-conformance-area"][
        "logical_terrain_area_id"
    ] = "geometry-conformance-logical-group"
    assert (
        authoritative_geometry_hash(
            bounds=logical_group_change["bounds"],
            authoritative=logical_group_change["authoritative"],
        )
        != battlefield["authoritative_geometry_hash"]
    )
    assert battlefield["authoritative"]["objectives_by_id"]

    zone_shape = battlefield["authoritative"]["deployment_zones_by_id"][
        "geometry-conformance-zone"
    ]["shape"]
    assert len(zone_shape["circle_cutouts"]) == 1
    assert len(zone_shape["polygon_cutouts"]) == 1
    assert zone_shape["circle_cutouts"][0]["kind"] == "circle"
    assert zone_shape["polygon_cutouts"][0]["kind"] == "polygon"
    assert battlefield["interaction"]["measurement_overlays"]
    path = battlefield["interaction"]["path_overlays"][0]
    assert len(path["segments"]) == 2
    assert {segment["segment_kind"] for segment in path["segments"]} == {"line"}
    assert (
        battlefield["render"]["hit_regions_by_entity_id"]["geometry-conformance-terrain"]["shape"][
            "kind"
        ]
        == "polygon"
    )


def test_phase18j_shape_schema_rejects_missing_centers_and_unanchored_polygon_rotation() -> None:
    validator = _schema_validator(
        "battlefield-view.schema.json",
        registry=_schema_registry(),
    )
    battlefield = cast(
        BattlefieldViewPayload,
        _read_json(REPO_ROOT / BATTLEFIELD_GEOMETRY_CONFORMANCE_PATH),
    )
    missing_center = cast(
        BattlefieldViewPayload,
        json.loads(json.dumps(battlefield, sort_keys=True)),
    )
    circle = missing_center["authoritative"]["models_by_id"]["geometry-conformance-circle-model"][
        "geometry"
    ]["measurement_shapes"][0]
    circle["center"] = None
    with pytest.raises(ValidationError):
        validator.validate(missing_center)

    unanchored_rotation = cast(
        BattlefieldViewPayload,
        json.loads(json.dumps(battlefield, sort_keys=True)),
    )
    polygon = unanchored_rotation["render"]["hit_regions_by_entity_id"][
        "geometry-conformance-terrain"
    ]["shape"]
    polygon["rotation_degrees"] = 15.0
    with pytest.raises(ValidationError):
        validator.validate(unanchored_rotation)

    missing_logical_area_id = cast(
        BattlefieldViewPayload,
        json.loads(json.dumps(battlefield, sort_keys=True)),
    )
    raw_missing_logical_area = cast(
        dict[str, object],
        missing_logical_area_id["authoritative"]["terrain_areas_by_id"][
            "geometry-conformance-area"
        ],
    )
    raw_missing_logical_area.pop("logical_terrain_area_id")
    with pytest.raises(ValidationError):
        validator.validate(missing_logical_area_id)


def test_phase18j_model_state_projection_is_explicit_and_fail_closed() -> None:
    session, _status = build_local_session_at_movement_request(game_id="phase18j-model-states")
    state = session.lifecycle.state
    assert state is not None
    model = state.army_definitions[0].units[0].own_models[0]

    assert (
        _model_state(
            model=model,
            placement_exists=True,
            removed=False,
            transport_unit_id=None,
            reserve_status=None,
        )
        == "placed"
    )
    assert (
        _model_state(
            model=replace(model, wounds_remaining=0),
            placement_exists=True,
            removed=False,
            transport_unit_id=None,
            reserve_status=None,
        )
        == "destroyed"
    )
    assert (
        _model_state(
            model=model,
            placement_exists=False,
            removed=False,
            transport_unit_id="transport-unit",
            reserve_status=None,
        )
        == "embarked"
    )
    assert (
        _model_state(
            model=model,
            placement_exists=False,
            removed=False,
            transport_unit_id=None,
            reserve_status=ReserveStatus.IN_RESERVES,
        )
        == "reserves"
    )
    assert (
        _model_state(
            model=model,
            placement_exists=False,
            removed=True,
            transport_unit_id=None,
            reserve_status=None,
        )
        == "removed"
    )
    assert (
        _model_state(
            model=model,
            placement_exists=False,
            removed=False,
            transport_unit_id=None,
            reserve_status=None,
        )
        == "undeployed"
    )


def test_phase18j_interaction_and_render_geometry_do_not_change_authoritative_hash() -> None:
    session, _status = build_local_session_at_movement_request(game_id="phase18j-hash-boundary")
    view = session.view(viewer_player_id=PLAYER_A)
    battlefield = view["battlefield_view"]
    assert battlefield is not None
    original_hash = battlefield["authoritative_geometry_hash"]

    non_authoritative_change = cast(
        BattlefieldViewPayload,
        json.loads(json.dumps(battlefield, sort_keys=True)),
    )
    non_authoritative_change["interaction"]["measurement_overlays"] = [
        {
            "overlay_id": "phase18j-measurement",
            "start": {"x_inches": 3.0, "y_inches": 4.0, "z_inches": 0.0},
            "end": {"x_inches": 6.0, "y_inches": 8.0, "z_inches": 0.0},
            "distance_inches": 5.0,
        }
    ]
    non_authoritative_change["interaction"]["path_overlays"] = [
        {
            "overlay_id": "phase18j-path",
            "model_instance_id": MODEL_ALPHA_1,
            "segments": [
                {
                    "segment_kind": "line",
                    "start": {
                        "position": {"x_inches": 3.0, "y_inches": 4.0, "z_inches": 0.0},
                        "facing_degrees": 0.0,
                    },
                    "end": {
                        "position": {"x_inches": 6.0, "y_inches": 4.0, "z_inches": 0.0},
                        "facing_degrees": 90.0,
                    },
                }
            ],
        }
    ]
    non_authoritative_change["render"]["hints_by_entity_id"]["phase18j-render-only"] = {
        "entity_id": "phase18j-render-only",
        "asset_id": "changed-asset",
    }
    assert (
        authoritative_geometry_hash(
            bounds=non_authoritative_change["bounds"],
            authoritative=non_authoritative_change["authoritative"],
        )
        == original_hash
    )
    _schema_validator(
        "battlefield-view.schema.json",
        registry=_schema_registry(),
    ).validate(non_authoritative_change)

    authoritative_change = cast(
        BattlefieldViewPayload,
        json.loads(json.dumps(battlefield, sort_keys=True)),
    )
    first_model = next(iter(authoritative_change["authoritative"]["models_by_id"].values()))
    assert first_model["pose"] is not None
    first_model["pose"]["position"]["x_inches"] += 0.25
    assert (
        authoritative_geometry_hash(
            bounds=authoritative_change["bounds"],
            authoritative=authoritative_change["authoritative"],
        )
        != original_hash
    )
    refreshed = session.view(viewer_player_id=PLAYER_A)
    assert refreshed["battlefield_view"] == battlefield

    state = session.lifecycle.state
    assert state is not None
    army = state.army_definitions[0]
    unit = army.units[0]
    model = unit.own_models[0]
    drifted_model = replace(
        model,
        geometry=replace(
            model.geometry,
            geometry_source_kind=GeometrySourceKind.MANUAL_OVERRIDE,
            geometry_source_id="phase18j-source-identity-drift",
        ),
    )
    state.army_definitions = [
        replace(
            army,
            units=(
                replace(unit, own_models=(drifted_model, *unit.own_models[1:])),
                *army.units[1:],
            ),
        ),
        *state.army_definitions[1:],
    ]
    drifted_view = session.view(viewer_player_id=PLAYER_A)
    drifted_battlefield = drifted_view["battlefield_view"]
    assert drifted_battlefield is not None
    assert drifted_battlefield["authoritative_geometry_hash"] != original_hash
    assert drifted_view["projection_state_hash"] != view["projection_state_hash"]


def test_phase18j_physical_proposal_context_excludes_render_geometry() -> None:
    session, _status = build_local_session_at_movement_request(
        game_id="phase18j-physical-context-render-boundary"
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert state.mission_setup is not None
    feature = _phase18j_terrain_feature()
    state.battlefield_state = replace(state.battlefield_state, terrain_features=(feature,))
    state.mission_setup = replace(state.mission_setup, terrain_features=(feature,))
    authoritative_context_hash = state.physical_proposal_context_hash()

    render_changed = replace(
        feature,
        display_geometry=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=10.0,
            center_y_inches=12.0,
            width_inches=6.0,
            depth_inches=4.0,
            display_template_id="phase18j-render-only-context-change",
        ),
    )
    state.battlefield_state = replace(
        state.battlefield_state,
        terrain_features=(render_changed,),
    )
    state.mission_setup = replace(state.mission_setup, terrain_features=(render_changed,))

    assert state.physical_proposal_context_hash() == authoritative_context_hash

    rules_changed = replace(
        render_changed,
        walls=(replace(render_changed.walls[0], height_inches=4.0),),
    )
    state.battlefield_state = replace(
        state.battlefield_state,
        terrain_features=(rules_changed,),
    )
    state.mission_setup = replace(state.mission_setup, terrain_features=(rules_changed,))

    assert state.physical_proposal_context_hash() != authoritative_context_hash

    classification_changed = replace(
        render_changed,
        classification=TerrainAreaClassification.LIGHT,
    )
    state.battlefield_state = replace(
        state.battlefield_state,
        terrain_features=(classification_changed,),
    )
    state.mission_setup = replace(
        state.mission_setup,
        terrain_features=(classification_changed,),
    )

    assert state.physical_proposal_context_hash() != authoritative_context_hash


def _phase18j_terrain_feature() -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="phase18j-ruin",
        feature_kind=TerrainFeatureKind.RUINS,
        classification=TerrainAreaClassification.DENSE,
        footprint_center_x_inches=10.0,
        footprint_center_y_inches=12.0,
        footprint_width_inches=6.0,
        footprint_depth_inches=4.0,
        rules_footprint_polygon=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=10.0,
            center_y_inches=12.0,
            width_inches=6.0,
            depth_inches=4.0,
            display_template_id="phase18j-ruin-rules",
        ).footprint_polygon,
        display_geometry=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=10.0,
            center_y_inches=12.0,
            width_inches=6.0,
            depth_inches=4.0,
            display_template_id="phase18j-ruin-asset",
        ),
        walls=(
            TerrainWallDefinition(
                wall_id="phase18j-wall",
                center_x_inches=10.0,
                center_y_inches=13.5,
                bottom_z_inches=0.0,
                width_inches=5.0,
                depth_inches=0.25,
                height_inches=3.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="phase18j-floor",
                center_x_inches=10.0,
                center_y_inches=12.0,
                bottom_z_inches=0.0,
                width_inches=6.0,
                depth_inches=4.0,
                thickness_inches=0.1,
            ),
        ),
        source_id="phase18j-ruin-source",
    )


def test_rules_catalog_card_maps_are_joinable_by_static_ids() -> None:
    session, _status = build_local_session_at_movement_request(game_id="ui-contract-card-map-joins")
    catalog_view = session.rules_catalog_view()
    army_rule_display_by_id = catalog_view["army_rule_display_by_id"]
    stratagem_display_by_id = catalog_view["stratagem_display_by_id"]

    assert army_rule_display_by_id["core-discipline"] == {
        "army_rule_id": "core-discipline",
        "display_name": "Core Discipline",
        "source_id": "army-rule:core-discipline",
        "content_scope": "matched_play",
        "ability_descriptor_ids": [],
    }
    for faction in catalog_view["faction_display_by_id"].values():
        for rule_id in faction["army_rule_ids"]:
            assert rule_id in army_rule_display_by_id

    for detachment in catalog_view["detachment_display_by_id"].values():
        for stratagem_id in detachment["stratagem_ids"]:
            assert stratagem_id in stratagem_display_by_id


def test_rules_catalog_stratagem_card_records_expose_stage1_details() -> None:
    catalog_view = project_rules_catalog_view(catalog=_catalog_with_ui_contract_stratagem())
    _schema_validator("rules-catalog.schema.json", registry=_schema_registry()).validate(
        catalog_view
    )

    detachment = catalog_view["detachment_display_by_id"]["core-combined-arms"]
    stratagem = catalog_view["stratagem_display_by_id"]["ui-contract-stratagem"]

    assert detachment["stratagem_ids"] == ["ui-contract-stratagem"]
    assert stratagem == {
        "stratagem_id": "ui-contract-stratagem",
        "display_name": "UI Contract Stratagem",
        "source_id": "stratagem:ui-contract-stratagem",
        "content_scope": "matched_play",
        "command_point_cost": 1,
        "timing_tags": ["fight", "shooting"],
        "ability_descriptor_ids": ["ui-contract-stratagem-ability"],
    }
    for record in catalog_view["stratagem_display_by_id"].values():
        assert type(record["command_point_cost"]) is int
        assert record["timing_tags"]
        assert record["source_id"]
        assert record["display_name"]


def test_hidden_data_is_redacted_but_legal_options_remain_explicit() -> None:
    initial_player_b = _fixture("initial_setup_view_player2.json")
    initial_pending = _json_object(initial_player_b["pending_decision"])

    assert initial_pending["request_id"] == "hidden-request"
    assert initial_pending["actor_id"] is None
    assert initial_pending["decision_type"] == "hidden_decision"
    assert initial_pending["payload"] == {"hidden": True, "secret": True}
    assert initial_pending["options"] == []
    assert initial_pending["interaction"] is None

    hidden_redaction = _fixture("hidden_secondary_redaction_view.json")
    choices = _json_list(hidden_redaction["public_secondary_mission_choices"])
    pending = _json_object(hidden_redaction["pending_decision"])
    option_ids = {
        _json_string(_json_object(option)["option_id"]) for option in _json_list(pending["options"])
    }

    assert choices == [{"hidden": True, "player_id": PLAYER_A, "selected": True}]
    assert pending["actor_id"] == PLAYER_B
    assert pending["request_id"] == "decision-request-000002"
    assert _json_object(pending["interaction"])["interaction_kind"] == "finite_option_list"
    assert {"fixed:assassination:bring_it_down", "tactical"}.issubset(option_ids)


def test_pending_decision_and_modifier_datacard_fixtures_are_ui_ready() -> None:
    pending = _fixture("pending_movement_request.json")
    options = _json_list(pending["options"])

    assert pending["request_id"] == "decision-request-000007"
    assert pending["decision_type"] == "select_movement_unit"
    assert all(_json_string(_json_object(option)["option_id"]) for option in options)
    assert {_json_string(_json_object(option)["option_id"]) for option in options} == {UNIT_ALPHA}
    interaction = _json_object(pending["interaction"])
    constraints = _json_object(interaction["constraints"])
    assert interaction["interaction_kind"] == "entity_selection"
    assert interaction["required_inputs"] == ["selected_entities"]
    assert constraints["entity_kinds"] == ["unit"]
    assert constraints["candidate_option_ids"] == [UNIT_ALPHA]
    assert constraints["submission_schema_ref"] == "finite-submission.schema.json"
    assert constraints["proposal_schema_ref"] is None
    assert constraints["minimum_selections"] == 1
    assert constraints["maximum_selections"] == 1

    modifier_view = _fixture("visible_modifier_datacard_view.json")
    model_display_by_id = cast(dict[str, JsonValue], modifier_view["model_display_by_id"])
    model_display = _json_object(model_display_by_id[MODEL_ALPHA_1])
    base_movement = _json_object(_json_object(model_display["base_characteristics"])["M"])
    current_movement = _json_object(_json_object(model_display["current_characteristics"])["M"])
    visible_modifiers = _json_list(model_display["visible_modifiers"])

    assert base_movement["final"] == 6
    assert current_movement["final"] == 7
    assert current_movement["applied_modifier_ids"] == ["ui-contract-move-plus-one"]
    assert _json_object(visible_modifiers[0])["source_kind"] == ("engine_resolved_characteristic")


def test_parameterized_interaction_metadata_selects_renderer_and_typed_schema() -> None:
    request = _read_json(
        REPO_ROOT / DECISION_EXAMPLE_DIR / "families" / "submit_movement_proposal.json"
    )
    interaction = _json_object(request["interaction"])
    constraints = _json_object(interaction["constraints"])

    assert interaction["interaction_kind"] == "path_editor"
    assert interaction["proposal_kind"] == "normal_move"
    assert interaction["selected_entity_ids"] == [UNIT_ALPHA]
    assert interaction["required_inputs"] == ["model_paths", "final_poses"]
    assert constraints["must_preserve_coherency"] is True
    assert constraints["may_enter_engagement_range"] is False
    assert constraints["submission_schema_ref"] == "parameterized-submission.schema.json"
    assert constraints["proposal_schema_ref"] == "proposal-payload.schema.json#/$defs/movement"


def test_proposal_examples_cover_engine_facing_payload_families() -> None:
    deployment = _proposal_example("deployment_placement.json")
    movement = _proposal_example("movement_path_witness.json")
    charge = _proposal_example("charge_move.json")
    shooting = _proposal_example("shooting_target_selection.json")
    melee = _proposal_example("melee_declaration.json")
    cult_ambush_marker = _proposal_example("cult_ambush_marker_placement.json")
    cult_ambush_no_marker = _proposal_example("cult_ambush_no_marker.json")
    return_on_death = _proposal_example("submit_return_on_death_placement.json")
    opportunity = _read_json(REPO_ROOT / DECISION_EXAMPLE_DIR / "opportunity_window.json")

    assert deployment["proposal_kind"] == "deployment_placement"
    assert deployment["unit_instance_id"] == UNIT_BETA
    assert len(_json_list(deployment["model_placements"])) == 5

    assert movement["proposal_kind"] == "normal_move"
    assert movement["movement_mode"] == "normal"
    assert len(_json_list(_json_object(movement["witness"])["model_paths"])) == 5

    assert charge["proposal_kind"] == "charge_move"
    assert charge["charge_target_unit_instance_ids"] == [UNIT_BETA]
    assert _json_list(_json_object(charge["witness"])["model_paths"])

    assert shooting["proposal_kind"] == "shooting_declaration"
    shooting_declarations = _json_list(shooting["declarations"])
    assert _json_object(shooting_declarations[0])["target_unit_instance_id"] == UNIT_BETA

    assert melee["proposal_kind"] == "melee_declaration"
    melee_declarations = _json_list(melee["declarations"])
    assert _json_object(melee_declarations[0])["target_allocations"] == [
        {"target_unit_instance_id": UNIT_BETA}
    ]

    assert cult_ambush_marker["submission_kind"] == "cult_ambush_marker_placement"
    assert {"x_inches", "y_inches"}.issubset(cult_ambush_marker)
    assert cult_ambush_no_marker["submission_kind"] == "cult_ambush_no_marker"
    assert cult_ambush_no_marker["no_marker_reason"] == "no_legal_marker_position"
    assert return_on_death["submission_kind"] == "submit_return_on_death_placement"
    assert _json_object(return_on_death["attempted_placement"])["model_placements"]

    request = _json_object(opportunity["decision_request"])
    request_payload = _json_object(request["payload"])
    options = _json_list(request["options"])
    option_ids = {_json_string(_json_object(option)["option_id"]) for option in options}
    assert request_payload["submission_family"] == "opportunity_window"
    assert opportunity["selected_option_id"] in option_ids
    assert _json_object(opportunity["selected_option_payload"])["submission_kind"] == (
        "opportunity_action"
    )


def test_decision_family_coverage_uses_registry_metadata_and_real_scenarios() -> None:
    coverage = _read_json(REPO_ROOT / DECISION_FAMILY_COVERAGE_PATH)
    rows = [_json_object(row) for row in _json_list(coverage["families"])]
    rows_by_type = {_json_string(row["decision_type"]): row for row in rows}
    registered = {
        contract.decision_type: contract for contract in GameLifecycle().decision_dispatch_contracts
    }
    live_paths = {
        path.relative_to(REPO_ROOT / Path("contracts")).as_posix(): path
        for path in sorted((REPO_ROOT / DECISION_EXAMPLE_DIR / "families").glob("*.json"))
    }

    assert coverage["registered_decision_type_count"] == len(registered)
    assert coverage["known_external_token_count"] == len(registered) + 2
    assert coverage["live_scenario_count"] == len(live_paths)
    assert set(registered).issubset(rows_by_type)
    assert set(registered) == set(registered_interaction_decision_types())
    assert coverage["interaction_kind_count"] == len(InteractionKind)
    assert coverage["standard_interaction_kinds"] == sorted(kind.value for kind in InteractionKind)
    for decision_type, contract in registered.items():
        row = rows_by_type[decision_type]
        assert row["registry_scope"] == "registered"
        assert row["submission_kind"] == contract.submission_kind.value
        assert row["interaction_kinds"] == list(contract.interaction_kinds)

    for row in rows:
        status = row["coverage_status"]
        example_path = row["example_path"]
        if status == "live_scenario":
            assert type(example_path) is str
            example = _read_json(live_paths[example_path])
            assert example["decision_type"] == row["decision_type"]
            assert example["is_parameterized"] is (row["submission_kind"] == "parameterized")
            interaction = _json_object(example["interaction"])
            assert _json_string(interaction["interaction_kind"]) in _json_list(
                row["interaction_kinds"]
            )
            assert interaction["schema_version"] == "interaction-descriptor-v2-variants"
            assert '"contract_fixture"' not in json.dumps(example, sort_keys=True)
        else:
            assert example_path is None


def test_contract_manifest_hashes_baseline_with_canonical_line_endings() -> None:
    manifest = _read_json(REPO_ROOT / Path("contracts/manifest.json"))
    hashes = _json_object(manifest["file_sha256"])
    baseline_path = REPO_ROOT / Path("contracts/compatibility/1.0.0-shape.json")
    baseline = _read_json(baseline_path)
    baseline_schema_names = set(_json_object(baseline["schemas"]))
    canonical_schema_names = {
        path.name for path in (REPO_ROOT / Path("contracts/schemas")).glob("*.json")
    }
    canonical_hash = hashlib.sha256(
        baseline_path.read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()

    assert len(baseline_schema_names) == 15
    assert len(canonical_schema_names) == 26
    assert "capability-manifest.schema.json" in canonical_schema_names
    assert baseline_schema_names < canonical_schema_names
    assert hashes["compatibility/1.0.0-shape.json"] == canonical_hash


def test_projection_hash_covers_pending_request_and_interaction_metadata_after_redaction() -> None:
    session, _status = build_local_session_at_movement_request(game_id="phase18i-projection-hash")
    owner_view = session.view(viewer_player_id=PLAYER_A)
    owner_hash = _json_string(owner_view["projection_state_hash"])
    request_changed = cast(
        GameViewPayload,
        json.loads(json.dumps(owner_view, sort_keys=True)),
    )
    request_pending = cast(dict[str, JsonValue], request_changed["pending_decision"])
    request_pending["request_id"] = "changed-request-id"
    assert _projection_state_hash(request_changed) != owner_hash

    interaction_changed = cast(
        GameViewPayload,
        json.loads(json.dumps(owner_view, sort_keys=True)),
    )
    interaction_pending = cast(dict[str, JsonValue], interaction_changed["pending_decision"])
    interaction = cast(dict[str, JsonValue], interaction_pending["interaction"])
    display_hints = cast(dict[str, JsonValue], interaction["display_hints"])
    display_hints["confirm_label"] = "Changed Interaction Label"
    assert _projection_state_hash(interaction_changed) != owner_hash

    opponent_view = cast(GameViewPayload, _fixture("initial_setup_view_player2.json"))
    opponent_pending = cast(dict[str, JsonValue], opponent_view["pending_decision"])
    assert opponent_pending["interaction"] is None
    assert opponent_view["nested_interaction_requests"] == []
    assert _projection_state_hash(opponent_view) == opponent_view["projection_state_hash"]


def test_typescript_interaction_gate_has_no_decision_family_switches_or_engine_imports() -> None:
    for relative_path in (
        Path("conformance/typescript/src/interaction.ts"),
        Path("conformance/typescript/src/interaction-conformance.test.ts"),
    ):
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "decision_type" not in source
        assert "warhammer40k_core.engine" not in source


def test_pr_base_contract_comparison_preserves_cumulative_minor_additions() -> None:
    verify = _contract_snapshot_verifier()
    schema_with_minor_addition = cast(
        JsonValue,
        {
            "type": "object",
            "properties": {"added_in_1_1": {"type": "string"}},
        },
    )
    schema_without_minor_addition = cast(
        JsonValue,
        {"type": "object", "properties": {}},
    )

    with pytest.raises(ValueError, match="major version increment"):
        verify(
            reference_label="pull request base contract",
            reference_version="1.1.0",
            reference_schemas={"example.schema.json": schema_with_minor_addition},
            reference_operations={"GET /added-in-1-1"},
            current_version="1.2.0",
            current_schemas={"example.schema.json": cast(Schema, schema_without_minor_addition)},
            current_operations=set(),
            require_version_progress=True,
        )

    with pytest.raises(ValueError, match="openapi operation removed"):
        verify(
            reference_label="pull request base contract",
            reference_version="1.1.0",
            reference_schemas={"example.schema.json": schema_without_minor_addition},
            reference_operations={"GET /added-in-1-1"},
            current_version="1.2.0",
            current_schemas={"example.schema.json": cast(Schema, schema_without_minor_addition)},
            current_operations=set(),
            require_version_progress=True,
        )

    with pytest.raises(ValueError, match="contract version increment"):
        verify(
            reference_label="pull request base contract",
            reference_version="1.0.0",
            reference_schemas={"example.schema.json": schema_without_minor_addition},
            reference_operations=set(),
            current_version="1.0.0",
            current_schemas={"example.schema.json": cast(Schema, schema_with_minor_addition)},
            current_operations={"GET /added-in-1-1"},
            require_version_progress=True,
        )

    verify(
        reference_label="pull request base contract",
        reference_version="1.0.0",
        reference_schemas={"example.schema.json": schema_without_minor_addition},
        reference_operations=set(),
        current_version="1.1.0",
        current_schemas={"example.schema.json": cast(Schema, schema_with_minor_addition)},
        current_operations={"GET /added-in-1-1"},
        require_version_progress=True,
    )


def test_released_contract_baseline_is_fail_closed_and_pr_ci_compares_base() -> None:
    baseline_path = REPO_ROOT / Path("contracts/compatibility/1.0.0-shape.json")
    baseline_before = baseline_path.read_bytes()
    completed = subprocess.run(
        [sys.executable, "scripts/build_external_contract.py", "--write-baseline"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    workflow = (REPO_ROOT / Path(".github/workflows/ci.yml")).read_text(encoding="utf-8")

    assert completed.returncode != 0
    assert "requires a new contract major version" in completed.stderr
    assert baseline_path.read_bytes() == baseline_before
    assert "fetch-depth: 0" in workflow
    assert "--base-ref ${{ github.event.pull_request.base.sha }}" in workflow
    assert "scripts/smoke_installed_contract_wheel.py" in workflow


def test_local_session_dev_server_exposes_read_only_routes() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/run_local_session_dev_server.py", "--dump-routes"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["game_id"] == "ui-contract-dev-server"
    assert "/rules-catalog" in payload["routes"]
    assert "/view/player-a" in payload["routes"]
    assert "/events/player-b?cursor=0" in payload["routes"]
    assert payload["viewer_player_ids"] == [PLAYER_A, PLAYER_B]


def _fixture(name: str) -> dict[str, JsonValue]:
    return _read_json(REPO_ROOT / _fixture_path(name))


def _fixture_path(name: str) -> Path:
    if name == "pending_movement_request.json":
        return DECISION_EXAMPLE_DIR / name
    return UI_FIXTURE_DIR / name


def _proposal_example(name: str) -> dict[str, JsonValue]:
    return _read_json(REPO_ROOT / PROPOSAL_EXAMPLE_DIR / name)


def _read_json(path: Path) -> dict[str, JsonValue]:
    payload = validate_json_value(json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict), f"{path} must contain a JSON object."
    return payload


def _catalog_with_ui_contract_stratagem() -> ArmyCatalog:
    base = ArmyCatalog.phase9a_canonical_content_pack()
    stratagem = StratagemDefinition(
        stratagem_id="ui-contract-stratagem",
        name="UI Contract Stratagem",
        source_id="stratagem:ui-contract-stratagem",
        command_point_cost=1,
        timing_tags=("fight", "shooting"),
        ability_descriptor_ids=("ui-contract-stratagem-ability",),
    )
    detachment = replace(
        base.detachments[0],
        stratagem_ids=(stratagem.stratagem_id,),
    )
    return ArmyCatalog(
        catalog_id="ui-contract-stratagem-catalog",
        ruleset_id=base.ruleset_id,
        source_package_id=base.source_package_id,
        datasheets=base.datasheets,
        wargear=base.wargear,
        factions=base.factions,
        army_rules=base.army_rules,
        detachments=(detachment,),
        enhancements=base.enhancements,
        stratagems=(stratagem,),
        source_ids=base.source_ids,
    )


def _schema_payloads() -> dict[str, Schema]:
    payloads: dict[str, Schema] = {}
    for path in SCHEMA_FILES:
        payloads[path.name] = cast(Schema, _read_json(REPO_ROOT / path))
    return payloads


def _contract_snapshot_verifier() -> _ContractSnapshotVerifier:
    scripts_directory = REPO_ROOT / Path("scripts")
    sys.path.insert(0, str(scripts_directory))
    try:
        namespace = runpy.run_path(str(scripts_directory / "build_external_contract.py"))
    finally:
        sys.path.remove(str(scripts_directory))
    return cast(
        _ContractSnapshotVerifier,
        namespace["_verify_contract_snapshot_compatibility"],
    )


def _schema_registry() -> SchemaRegistry:
    registry = EMPTY_REGISTRY
    for schema in _schema_payloads().values():
        if not isinstance(schema, dict):
            raise TypeError("UI contract schemas must be JSON objects.")
        schema_id = schema.get("$id")
        assert type(schema_id) is str, "UI contract schemas must declare string $id values."
        resource = cast(
            SchemaResource,
            Resource.from_contents(cast(Schema, schema), default_specification=DRAFT202012),
        )
        registry = registry.with_resource(schema_id, resource)
    return registry


def _schema_validator(schema_name: str, *, registry: SchemaRegistry) -> _PayloadValidator:
    schema = _schema_payloads()[schema_name]
    return cast(_PayloadValidator, Draft202012Validator(schema, registry=registry))


def _assert_no_ui_owned_state(value: JsonValue) -> None:
    if isinstance(value, dict):
        forbidden = FORBIDDEN_UI_STATE_KEYS.intersection(value.keys())
        assert not forbidden
        for nested in value.values():
            _assert_no_ui_owned_state(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_ui_owned_state(nested)


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict), "Expected JSON object."
    return value


def _json_list(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list), "Expected JSON list."
    return value


def _json_string(value: JsonValue) -> str:
    assert type(value) is str, "Expected JSON string."
    return value
