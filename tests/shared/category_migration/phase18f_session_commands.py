from __future__ import annotations

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from http.client import HTTPResponse
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Barrier, Thread
from typing import Protocol, cast
from urllib.request import Request, urlopen

import pytest
from jsonschema import Draft202012Validator
from referencing import Resource
from referencing.jsonschema import DRAFT202012, EMPTY_REGISTRY, Schema, SchemaRegistry

from tests.phase18f_command_helpers import (
    pre_record_unsupported_session,
    recorded_unsupported_session,
)
from tests.shared.repository_root import REPOSITORY_ROOT
from warhammer40k_core.adapters.access_control import (
    DEV_ADMIN_TOKEN,
    DEV_PLAYER_A_TOKEN,
    DEV_PLAYER_B_TOKEN,
    bearer_authorization,
)
from warhammer40k_core.adapters.external_contract import (
    SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
    SESSION_CREATE_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.projection import project_game_view
from warhammer40k_core.adapters.server import AdapterGameServer
from warhammer40k_core.adapters.server_types import ServerResponse
from warhammer40k_core.adapters.session_persistence import (
    SessionPersistenceError,
    SessionPersistenceStore,
    SQLiteSessionPersistenceStore,
)
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    BattlePhaseSequenceDescriptor,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
)
from warhammer40k_core.engine.replay import (
    ReplayArtifactPayload,
    ReplayProjectionCheckpoint,
    ReplayProjectionSnapshot,
    ReplayRunner,
    ReplayRunStatus,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import tacoma_open_2026

REPO_ROOT = REPOSITORY_ROOT
PLAYER_A = "player-a"
PLAYER_B = "player-b"
PARTICIPANT_A = "participant-a"
PARTICIPANT_B = "participant-b"
FIXED_SECONDARY_OPTION_ID = "fixed:assassination:bring_it_down"
NORMAL_MOVE_ACTION_OPTION_ID = "normal_move"
SELECT_DEPLOYMENT_UNIT = "select_deployment_unit"
SUBMIT_DEPLOYMENT_PLACEMENT = "submit_deployment_placement"
HTTP_REQUEST_TIMEOUT_SECONDS = 30.0


class _PayloadValidator(Protocol):
    def validate(self, instance: object) -> None: ...

    def iter_errors(self, instance: object) -> Iterator[object]: ...


def _create_session(server: AdapterGameServer, *, game_id: str) -> str:
    created = _request(
        server,
        "POST",
        "/sessions",
        body=_session_create_body(game_id),
        expected_status=201,
    )
    return _field_string(created, "session_id")


def _start_command(server: AdapterGameServer, session_id: str, command_id: str) -> None:
    _submit_command(
        server,
        participant_id=PARTICIPANT_A,
        envelope=_command_envelope(
            session_id=session_id,
            command_id=command_id,
            expected_revision=0,
            submission_kind="start_session",
        ),
    )


def _session_create_body(game_id: str) -> dict[str, JsonValue]:
    config = canonical_setup_prebattle_smoke_config(game_id=game_id)
    return _session_create_body_from_config(config)


def _session_create_body_from_config(config: GameConfig) -> dict[str, JsonValue]:
    return {
        "schema_version": SESSION_CREATE_SCHEMA_VERSION,
        "config": validate_json_value(config.to_payload()),
    }


def _compact_terminal_config(*, game_id: str) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    descriptor = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase18f-terminal"
    )
    compact_descriptor = replace(
        descriptor,
        descriptor_hash="",
        battle_phase_sequence=BattlePhaseSequenceDescriptor(
            phases=(BattlePhaseKind.COMMAND, BattlePhaseKind.FIGHT)
        ),
    )
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=compact_descriptor,
        army_catalog=catalog,
        army_muster_requests=(
            _compact_army_muster_request(
                catalog=catalog,
                player_id=PLAYER_A,
                army_id="army-alpha",
                unit_selection_id="terminal-unit-a",
            ),
            _compact_army_muster_request(
                catalog=catalog,
                player_id=PLAYER_B,
                army_id="army-beta",
                unit_selection_id="terminal-unit-b",
            ),
        ),
        player_ids=(PLAYER_A, PLAYER_B),
        turn_order=(PLAYER_A, PLAYER_B),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id=PLAYER_A,
            attacker_force_disposition_id="take-and-hold",
            defender_player_id=PLAYER_B,
            defender_force_disposition_id="purge-the-foe",
        ),
    )


def _compact_army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
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
            ),
        ),
    )


def _command_envelope(
    *,
    session_id: str,
    command_id: str,
    expected_revision: int,
    submission_kind: str,
    request_id: str | None = None,
    result_id: str | None = None,
    option_id: str | None = None,
    payload: JsonValue = None,
) -> dict[str, JsonValue]:
    submission: dict[str, JsonValue] = {"submission_kind": submission_kind}
    if option_id is not None:
        submission["option_id"] = option_id
    if submission_kind == "parameterized_payload":
        submission["payload"] = payload
    return {
        "schema_version": SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
        "command_id": command_id,
        "session_id": session_id,
        "expected_session_revision": expected_revision,
        "request_id": request_id,
        "result_id": result_id,
        "submission": submission,
    }


def _submit_command(
    server: AdapterGameServer,
    *,
    participant_id: str,
    envelope: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    response = _request_raw(
        server,
        session_id=_field_string(envelope, "session_id"),
        participant_id=participant_id,
        envelope=envelope,
    )
    assert response.status_code == 200, response.payload
    return _json_object(response.payload)


def _request_raw(
    server: AdapterGameServer,
    *,
    session_id: str,
    participant_id: str | None,
    envelope: dict[str, JsonValue],
) -> ServerResponse:
    submission = _field_object(envelope, "submission")
    lifecycle_command = _field_string(submission, "submission_kind") in {
        "start_session",
        "advance_session",
        "close_session",
    }
    if participant_id == PARTICIPANT_A and lifecycle_command:
        token = DEV_ADMIN_TOKEN
    elif participant_id == PARTICIPANT_A:
        token = DEV_PLAYER_A_TOKEN
    elif participant_id == PARTICIPANT_B:
        token = DEV_PLAYER_B_TOKEN
    else:
        token = "invalid-principal-token"
    return server.handle(
        method="POST",
        path=f"/sessions/{session_id}/commands",
        authorization=bearer_authorization(token),
        body=envelope,
    )


def _request(
    server: AdapterGameServer,
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: JsonValue = None,
    expected_status: int = 200,
) -> dict[str, JsonValue]:
    response = server.handle(
        method=method,
        path=path,
        query=query,
        body=body,
        authorization=bearer_authorization(_request_token(path=path, query=query, body=body)),
    )
    assert response.status_code == expected_status, response.payload
    payload = _json_object(response.payload)
    if path.endswith("/projection") and "projection" in payload:
        return _field_object(payload, "projection")
    return payload


def _pending_decision(
    server: AdapterGameServer,
    *,
    session_id: str,
    player_id: str,
) -> dict[str, JsonValue]:
    projection = _request(
        server,
        "GET",
        f"/sessions/{session_id}/projection",
        query={"viewer_player_id": player_id},
    )
    return _field_object(projection, "pending_decision")


def _pending_decision_for_any_player(
    server: AdapterGameServer,
    *,
    session_id: str,
) -> dict[str, JsonValue]:
    for player_id in (PLAYER_A, PLAYER_B):
        pending = _pending_decision(server, session_id=session_id, player_id=player_id)
        if pending["decision_type"] != "hidden_decision":
            return pending
    raise AssertionError("No actor-visible protocol decision found.")


def _request_token(
    *,
    path: str,
    query: dict[str, str] | None,
    body: JsonValue,
) -> str:
    if query is not None:
        viewer = query.get("viewer_player_id")
        if viewer == PLAYER_A:
            return DEV_PLAYER_A_TOKEN
        if viewer == PLAYER_B:
            return DEV_PLAYER_B_TOKEN
    if isinstance(body, dict):
        actor = body.get("actor_id")
        if actor == PLAYER_A:
            return DEV_PLAYER_A_TOKEN
        if actor == PLAYER_B:
            return DEV_PLAYER_B_TOKEN
    return DEV_ADMIN_TOKEN


def _advance_to_deployment_placement(
    server: AdapterGameServer,
    *,
    session_id: str,
) -> dict[str, JsonValue]:
    while True:
        pending = _pending_decision_for_any_player(server, session_id=session_id)
        decision_type = _field_string(pending, "decision_type")
        if decision_type == SUBMIT_DEPLOYMENT_PLACEMENT:
            return pending
        if decision_type == SECONDARY_MISSION_DECISION_TYPE:
            option_id = FIXED_SECONDARY_OPTION_ID
        else:
            assert decision_type in {"select_reserve_declaration", SELECT_DEPLOYMENT_UNIT}
            option_id = _first_option_id(pending)
        revision = _session_revision(server, session_id=session_id)
        _submit_command(
            server,
            participant_id=_participant_for_player(_field_string(pending, "actor_id")),
            envelope=_command_envelope(
                session_id=session_id,
                command_id=f"phase18f-setup-{_field_string(pending, 'request_id')}",
                expected_revision=revision,
                submission_kind="finite_option",
                request_id=_field_string(pending, "request_id"),
                result_id=f"phase18f-result-{_field_string(pending, 'request_id')}",
                option_id=option_id,
            ),
        )


def _advance_to_movement_selection(
    server: AdapterGameServer,
    *,
    session_id: str,
) -> dict[str, JsonValue]:
    while True:
        pending = _pending_decision_for_any_player(server, session_id=session_id)
        decision_type = _field_string(pending, "decision_type")
        if decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE:
            return pending
        if decision_type == SUBMIT_DEPLOYMENT_PLACEMENT:
            player_id = _field_string(pending, "actor_id")
            projection = _request(
                server,
                "GET",
                f"/sessions/{session_id}/projection",
                query={"viewer_player_id": player_id},
            )
            _submit_command(
                server,
                participant_id=_participant_for_player(player_id),
                envelope=_command_envelope(
                    session_id=session_id,
                    command_id=f"phase18f-movement-{_field_string(pending, 'request_id')}",
                    expected_revision=_session_revision(server, session_id=session_id),
                    submission_kind="parameterized_payload",
                    request_id=_field_string(pending, "request_id"),
                    result_id=f"phase18f-movement-result-{_field_string(pending, 'request_id')}",
                    payload=_deployment_payload_from_proposal(
                        _field_object(projection, "pending_proposal")
                    ),
                ),
            )
            continue
        if decision_type == SECONDARY_MISSION_DECISION_TYPE:
            option_id = FIXED_SECONDARY_OPTION_ID
        else:
            assert decision_type == SELECT_DEPLOYMENT_UNIT
            option_id = _first_option_id(pending)
        _submit_visible_option_command(
            server,
            session_id=session_id,
            request=pending,
            option_id=option_id,
            command_id=f"phase18f-movement-{_field_string(pending, 'request_id')}",
        )


def _submit_visible_option_command(
    server: AdapterGameServer,
    *,
    session_id: str,
    request: dict[str, JsonValue],
    option_id: str,
    command_id: str,
) -> dict[str, JsonValue]:
    player_id = _field_string(request, "actor_id")
    return _submit_command(
        server,
        participant_id=_participant_for_player(player_id),
        envelope=_command_envelope(
            session_id=session_id,
            command_id=command_id,
            expected_revision=_session_revision(server, session_id=session_id),
            submission_kind="finite_option",
            request_id=_field_string(request, "request_id"),
            result_id=f"{command_id}-result",
            option_id=option_id,
        ),
    )


def _deployment_payload_from_proposal(value: JsonValue) -> dict[str, JsonValue]:
    proposal = _json_object(value)
    player_id = _field_string(proposal, "player_id")
    unit_instance_id = _field_string(proposal, "unit_instance_id")
    army_id = unit_instance_id.split(":", maxsplit=1)[0]
    zone = _json_object(_field_list(proposal, "legal_deployment_zones")[0])
    polygon = _json_object(_field_list(_field_object(zone, "shape"), "polygons")[0])
    vertices = [_json_object(vertex) for vertex in _field_list(polygon, "vertices")]
    min_x = min(_field_float(vertex, "x") for vertex in vertices)
    min_y = min(_field_float(vertex, "y") for vertex in vertices)
    facing = 180.0 if player_id == PLAYER_B else 0.0
    placements: list[JsonValue] = []
    for index, model_id in enumerate(_field_list(proposal, "model_instance_ids")):
        placements.append(
            {
                "army_id": army_id,
                "player_id": player_id,
                "unit_instance_id": unit_instance_id,
                "model_instance_id": _json_string(model_id),
                "pose": {
                    "position": {
                        "x": min_x + 3.0 + ((index // 3) * 1.8),
                        "y": min_y + 3.0 + ((index % 3) * 1.8),
                        "z": 0.0,
                    },
                    "facing": {"degrees": facing},
                },
            }
        )
    return {
        "proposal_request_id": _field_string(proposal, "request_id"),
        "proposal_kind": _field_string(proposal, "proposal_kind"),
        "game_id": _field_string(proposal, "game_id"),
        "ruleset_descriptor_hash": _field_string(proposal, "ruleset_descriptor_hash"),
        "setup_step": _field_string(proposal, "setup_step"),
        "player_id": player_id,
        "unit_instance_id": unit_instance_id,
        "placement_kind": _field_string(proposal, "placement_kind"),
        "model_placements": placements,
        "context": proposal["context"],
    }


def _invalid_distance_witness(
    *,
    projection: dict[str, JsonValue],
    unit_instance_id: str,
) -> dict[str, JsonValue]:
    battlefield = _field_object(projection, "battlefield_state")
    for army_value in _field_list(battlefield, "placed_armies"):
        army = _json_object(army_value)
        for unit_value in _field_list(army, "unit_placements"):
            unit = _json_object(unit_value)
            if unit["unit_instance_id"] != unit_instance_id:
                continue
            model_paths: list[JsonValue] = []
            for model_value in _field_list(unit, "model_placements"):
                model = _json_object(model_value)
                pose = _field_object(model, "pose")
                position = _field_object(pose, "position")
                facing = _field_object(pose, "facing")
                x = _field_float(position, "x")
                y = _field_float(position, "y")
                z = _field_float(position, "z")
                degrees = _field_float(facing, "degrees")
                model_paths.append(
                    {
                        "model_id": _field_string(model, "model_instance_id"),
                        "poses": [
                            _pose_payload(x=x, y=y, z=z, degrees=degrees),
                            _pose_payload(x=x + 500.0, y=y, z=z, degrees=degrees),
                            _pose_payload(x=x + 1000.0, y=y, z=z, degrees=degrees),
                        ],
                    }
                )
            return {"model_paths": model_paths}
    raise AssertionError("Movement proposal unit placement was not visible.")


def _pose_payload(*, x: float, y: float, z: float, degrees: float) -> dict[str, JsonValue]:
    return {
        "position": {"x": x, "y": y, "z": z},
        "facing": {"degrees": degrees},
    }


def _authoritative_snapshot(
    server: AdapterGameServer,
    *,
    session_id: str,
) -> tuple[int, str | None, str, int, int]:
    metadata = _request(
        server,
        "GET",
        f"/sessions/{session_id}",
        query={"viewer_player_id": PLAYER_A},
    )
    replay = _request(server, "GET", f"/sessions/{session_id}/replay")
    projection_hash = metadata["projection_state_hash"]
    assert projection_hash is None or type(projection_hash) is str
    return (
        _field_int(metadata, "session_revision"),
        projection_hash,
        _field_string(metadata, "event_cursor"),
        len(_field_list(replay, "decision_records")),
        len(_field_list(replay, "event_records")),
    )


def _cursor_offset(server: AdapterGameServer, token: str) -> int:
    return server.cursor_codec.decode(token).offset


def _session_revision(server: AdapterGameServer, *, session_id: str) -> int:
    metadata = _request(server, "GET", f"/sessions/{session_id}")
    return _field_int(metadata, "session_revision")


def _participant_for_player(player_id: str) -> str:
    if player_id == PLAYER_A:
        return PARTICIPANT_A
    assert player_id == PLAYER_B
    return PARTICIPANT_B


def _replay_projection(
    lifecycle: GameLifecycle,
    checkpoint: ReplayProjectionCheckpoint,
) -> ReplayProjectionSnapshot:
    projection = project_game_view(
        lifecycle=lifecycle,
        viewer_player_id=checkpoint.viewer_player_id,
    )
    return ReplayProjectionSnapshot(
        viewer_player_id=checkpoint.viewer_player_id,
        projection_schema=projection["projection_schema"],
        projection_state_hash=projection["projection_state_hash"],
    )


def _http_server(server: AdapterGameServer) -> ThreadingHTTPServer:
    from warhammer40k_core.adapters.server import create_local_dev_http_server

    return create_local_dev_http_server(api=server)


def _http_json(request: Request) -> dict[str, JsonValue]:
    response = cast(
        HTTPResponse,
        urlopen(request, timeout=HTTP_REQUEST_TIMEOUT_SECONDS),
    )
    try:
        return _json_object(validate_json_value(json.loads(response.read().decode("utf-8"))))
    finally:
        response.close()


def _http_command_bytes(
    base_url: str,
    session_id: str,
    envelope: dict[str, JsonValue],
) -> tuple[int, bytes]:
    request = Request(
        f"{base_url}/sessions/{session_id}/commands",
        data=json.dumps(envelope, sort_keys=True).encode("utf-8"),
        headers={
            "Authorization": bearer_authorization(DEV_ADMIN_TOKEN),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    response = cast(
        HTTPResponse,
        urlopen(request, timeout=HTTP_REQUEST_TIMEOUT_SECONDS),
    )
    try:
        return response.status, response.read()
    finally:
        response.close()


def _schema_validator(schema_name: str) -> _PayloadValidator:
    schemas = _schema_payloads()
    return cast(
        _PayloadValidator,
        Draft202012Validator(schemas[schema_name], registry=_schema_registry(schemas)),
    )


def _schema_payloads() -> dict[str, Schema]:
    names = (
        "lifecycle-status.schema.json",
        "proposal-payload.schema.json",
        "session-command-envelope.schema.json",
        "session-command-outcome.schema.json",
        "session-metadata.schema.json",
    )
    return {
        name: cast(Schema, _read_json(REPO_ROOT / "contracts" / "schemas" / name)) for name in names
    }


def _schema_registry(schemas: dict[str, Schema]) -> SchemaRegistry:
    registry = EMPTY_REGISTRY
    for schema in schemas.values():
        if not isinstance(schema, dict):
            raise TypeError("Contract schemas must be JSON objects.")
        schema_id = schema.get("$id")
        assert type(schema_id) is str
        registry = registry.with_resource(
            schema_id,
            cast(
                Resource[Schema],
                Resource.from_contents(schema, default_specification=DRAFT202012),
            ),
        )
    return registry


def _read_json(path: Path) -> dict[str, JsonValue]:
    return _json_object(validate_json_value(json.loads(path.read_text(encoding="utf-8"))))


def _error_code(response: ServerResponse) -> str:
    return _field_string(_field_object(_json_object(response.payload), "error"), "code")


def _first_option_id(request: dict[str, JsonValue]) -> str:
    return _field_string(_json_object(_field_list(request, "options")[0]), "option_id")


def _terminal_progress_option_id(request: dict[str, JsonValue]) -> str:
    option_ids = tuple(
        _field_string(_json_object(option), "option_id")
        for option in _field_list(request, "options")
    )
    if request["decision_type"] == SECONDARY_MISSION_DECISION_TYPE:
        assert FIXED_SECONDARY_OPTION_ID in option_ids
        return FIXED_SECONDARY_OPTION_ID
    for preferred in ("complete_prebattle_actions", "declare_no_reserves"):
        if preferred in option_ids:
            return preferred
    for option_id in option_ids:
        if any(token in option_id for token in ("decline", "complete", "none", "skip")):
            return option_id
    return option_ids[0]


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _field_object(value: dict[str, JsonValue], key: str) -> dict[str, JsonValue]:
    return _json_object(value[key])


def _field_list(value: dict[str, JsonValue], key: str) -> list[JsonValue]:
    result = value[key]
    assert isinstance(result, list)
    return result


def _field_string(value: dict[str, JsonValue], key: str) -> str:
    return _json_string(value[key])


def _json_string(value: JsonValue) -> str:
    assert type(value) is str
    return value


def _field_int(value: dict[str, JsonValue], key: str) -> int:
    result = value[key]
    assert type(result) is int
    return result


def _field_float(value: dict[str, JsonValue], key: str) -> float:
    result = value[key]
    if type(result) is int:
        return float(result)
    assert type(result) is float
    return result


__all__: list[str] = []
__all__ += ["AdapterGameServer", "ArmyCatalog", "ArmyMusterRequest", "Barrier", "BattlePhaseKind"]
__all__ += ["DEV_ADMIN_TOKEN", "DEV_PLAYER_A_TOKEN", "BattlePhaseSequenceDescriptor"]
__all__ += ["DEV_PLAYER_B_TOKEN", "DRAFT202012", "DetachmentSelection", "Draft202012Validator"]
__all__ += ["EMPTY_REGISTRY", "FIXED_SECONDARY_OPTION_ID", "GameConfig", "GameLifecycle"]
__all__ += ["HTTP_REQUEST_TIMEOUT_SECONDS", "HTTPResponse", "Iterator", "JsonValue"]
__all__ += ["MissionSetup", "ModelProfileSelection", "MovementMode"]
__all__ += ["NORMAL_MOVE_ACTION_OPTION_ID", "PARTICIPANT_A", "PARTICIPANT_B", "PLAYER_A"]
__all__ += ["PLAYER_B", "REPOSITORY_ROOT", "REPO_ROOT", "Path", "Protocol"]
__all__ += ["ReplayArtifactPayload", "ReplayProjectionCheckpoint", "ReplayProjectionSnapshot"]
__all__ += ["ReplayRunStatus", "ReplayRunner", "Request", "Resource", "RulesetDescriptor"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "SELECT_DEPLOYMENT_UNIT"]
__all__ += ["SELECT_MOVEMENT_ACTION_DECISION_TYPE", "SELECT_MOVEMENT_UNIT_DECISION_TYPE"]
__all__ += ["SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION", "SESSION_CREATE_SCHEMA_VERSION"]
__all__ += ["SUBMIT_DEPLOYMENT_PLACEMENT", "SQLiteSessionPersistenceStore", "Schema"]
__all__ += ["SchemaRegistry", "ServerResponse", "SessionPersistenceError"]
__all__ += ["SessionPersistenceStore", "Thread", "ThreadPoolExecutor", "ThreadingHTTPServer"]
__all__ += ["UTC", "UnitMusterSelection", "_PayloadValidator", "_advance_to_deployment_placement"]
__all__ += ["_advance_to_movement_selection", "_authoritative_snapshot", "_command_envelope"]
__all__ += ["_compact_army_muster_request", "_compact_terminal_config", "_create_session"]
__all__ += ["_cursor_offset", "_deployment_payload_from_proposal", "_error_code", "_field_float"]
__all__ += ["_field_int", "_field_list", "_field_object", "_field_string", "_first_option_id"]
__all__ += ["_http_command_bytes", "_http_json", "_http_server", "_invalid_distance_witness"]
__all__ += ["_json_object", "_json_string", "_participant_for_player", "_pending_decision"]
__all__ += ["_pending_decision_for_any_player", "_pose_payload", "_read_json"]
__all__ += ["_replay_projection", "_request", "_request_raw", "_request_token"]
__all__ += ["_schema_payloads", "_schema_registry", "_schema_validator", "_session_create_body"]
__all__ += ["_session_create_body_from_config", "_session_revision", "_start_command"]
__all__ += ["_submit_command", "_submit_visible_option_command", "_terminal_progress_option_id"]
__all__ += ["bearer_authorization", "canonical_setup_prebattle_smoke_config", "cast"]
__all__ += ["chapter_approved_2026_27_mission_pack", "datetime", "json"]
__all__ += ["pre_record_unsupported_session", "project_game_view", "pytest"]
__all__ += ["recorded_unsupported_session", "replace", "tacoma_open_2026", "urlopen"]
__all__ += ["validate_json_value"]
