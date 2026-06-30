from __future__ import annotations

import json
from dataclasses import replace
from http.client import HTTPResponse
from pathlib import Path
from threading import Thread
from typing import Protocol, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from jsonschema import Draft202012Validator
from referencing import Resource
from referencing.jsonschema import (
    DRAFT202012,
    EMPTY_REGISTRY,
    Schema,
    SchemaRegistry,
    SchemaResource,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.server import (
    AdapterGameServer,
    ServerApiError,
    ServerResponse,
    create_local_dev_http_server,
)
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.replay import ReplayArtifactPayload, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYER_A = "player-a"
PLAYER_B = "player-b"
FIXED_SECONDARY_OPTION_ID = "fixed:assassination:bring_it_down"
SELECT_DEPLOYMENT_UNIT = "select_deployment_unit"
SUBMIT_DEPLOYMENT_PLACEMENT = "submit_deployment_placement"
SELECT_MOVEMENT_UNIT = "select_movement_unit"
SELECT_MOVEMENT_ACTION = "select_movement_action"
ADVANCE_ACTION_OPTION_ID = "advance"


class _PayloadValidator(Protocol):
    def validate(self, instance: object) -> None: ...


def test_phase18e_server_api_smoke_exports_replay_and_schema_valid_payloads() -> None:
    server = AdapterGameServer()
    game_id = "phase18e-server-smoke"
    _create_game(server, game_id=game_id)

    rules_catalog = _request(server, "GET", "/rules-catalog")
    _schema_validator("rules_catalog_view.schema.json").validate(rules_catalog)

    status_payload = _request(server, "POST", f"/games/{game_id}/advance")
    first_request = _decision_from_status(server, game_id=game_id, payload=status_payload)
    assert first_request["decision_type"] == SECONDARY_MISSION_DECISION_TYPE

    player_a_view = _request(
        server,
        "GET",
        f"/games/{game_id}/view",
        query={"viewer_player_id": PLAYER_A},
    )
    player_b_view = _request(
        server,
        "GET",
        f"/games/{game_id}/view",
        query={"viewer_player_id": PLAYER_B},
    )
    _schema_validator("game_view.schema.json").validate(player_a_view)
    player_b_pending = _field_object(player_b_view, "pending_decision")
    assert _field_list(player_b_pending, "options") == []
    assert _field_object(player_b_pending, "payload") == {"hidden": True, "secret": True}

    initial_events = _request(
        server,
        "GET",
        f"/games/{game_id}/events",
        query={"viewer_player_id": PLAYER_B, "cursor": "0"},
    )
    _schema_validator("event_stream_delta.schema.json").validate(initial_events)

    status_payload = _submit_option(
        server,
        game_id=game_id,
        request=first_request,
        option_id=FIXED_SECONDARY_OPTION_ID,
        result_id=f"{game_id}-secondary-a",
    )
    second_request = _decision_from_status(server, game_id=game_id, payload=status_payload)
    status_payload = _submit_option(
        server,
        game_id=game_id,
        request=second_request,
        option_id=FIXED_SECONDARY_OPTION_ID,
        result_id=f"{game_id}-secondary-b",
    )
    deployment_request = _decision_from_status(server, game_id=game_id, payload=status_payload)
    status_payload = _submit_option(
        server,
        game_id=game_id,
        request=deployment_request,
        option_id=_first_option_id(deployment_request),
        result_id=f"{game_id}-deployment-unit",
    )
    placement_request = _decision_from_status(server, game_id=game_id, payload=status_payload)
    assert placement_request["decision_type"] == SUBMIT_DEPLOYMENT_PLACEMENT
    placement_view = _request(
        server,
        "GET",
        f"/games/{game_id}/view",
        query={"viewer_player_id": _actor(placement_request)},
    )
    placement_payload = _deployment_payload_from_proposal(
        _field_object(placement_view, "pending_proposal")
    )
    status_payload = _submit_payload(
        server,
        game_id=game_id,
        request=placement_request,
        payload=placement_payload,
        result_id=f"{game_id}-deployment-placement",
    )
    assert _status_kind(status_payload) == "waiting_for_decision"

    event_delta = _request(
        server,
        "GET",
        f"/games/{game_id}/events",
        query={
            "viewer_player_id": PLAYER_A,
            "cursor": str(_field_int(initial_events, "next_cursor")),
        },
    )
    assert _field_list(event_delta, "events")
    _schema_validator("event_stream_delta.schema.json").validate(event_delta)

    replay_payload = _request(server, "GET", f"/games/{game_id}/replay")
    replay_result = ReplayRunner.from_payload(cast(ReplayArtifactPayload, replay_payload)).run()
    assert replay_result.status is ReplayRunStatus.REPRODUCED
    assert replay_result.reproduced_decision_count == len(
        _field_list(replay_payload, "decision_records")
    )

    support_profile = _request(server, "GET", f"/games/{game_id}/support-profile")
    assert support_profile["overall_status"] == "playable"
    assert support_profile["eligible_for_headless_self_play_smoke"] is True
    assert _field_list(support_profile, "mustering_support_rows")
    assert _field_list(support_profile, "detachment_faction_support_rows")


def test_phase18e_mutation_response_does_not_expose_next_opponent_decision() -> None:
    server = AdapterGameServer()
    game_id = "phase18e-server-redacted-mutation"
    _create_game(server, game_id=game_id)
    status_payload = _request(server, "POST", f"/games/{game_id}/advance")
    first_request = _decision_from_status(server, game_id=game_id, payload=status_payload)
    assert _actor(first_request) == PLAYER_A

    mutation_response = _submit_option(
        server,
        game_id=game_id,
        request=first_request,
        option_id=FIXED_SECONDARY_OPTION_ID,
        result_id=f"{game_id}-secondary-a",
    )
    response_status = _field_object(mutation_response, "status")
    assert _field_string(response_status, "status_kind") == "waiting_for_decision"
    assert _field_string(response_status, "actor_id") == PLAYER_B
    assert _field_string(response_status, "decision_type") == SECONDARY_MISSION_DECISION_TYPE
    assert _field_string(response_status, "pending_request_id")
    assert "decision_request" not in response_status
    assert response_status["payload"] is None
    assert not _contains_key(mutation_response, "options")
    assert not _contains_key(mutation_response, "secret")

    player_a_view = _request(
        server,
        "GET",
        f"/games/{game_id}/view",
        query={"viewer_player_id": PLAYER_A},
    )
    player_a_pending = _field_object(player_a_view, "pending_decision")
    assert _field_list(player_a_pending, "options") == []
    assert _field_object(player_a_pending, "payload") == {"hidden": True, "secret": True}

    player_b_view = _request(
        server,
        "GET",
        f"/games/{game_id}/view",
        query={"viewer_player_id": PLAYER_B},
    )
    player_b_pending = _field_object(player_b_view, "pending_decision")
    assert _field_string(player_b_pending, "request_id") == _field_string(
        response_status, "pending_request_id"
    )
    assert _field_list(player_b_pending, "options")
    assert _field_object(player_b_pending, "payload") != {"hidden": True, "secret": True}


def test_phase18e_support_profile_generic_ir_datasheet_ability_is_playable() -> None:
    server = AdapterGameServer()
    game_id = "phase18e-server-generic-ir-support"
    catalog = _catalog_with_selected_generic_ir_ability()
    _create_game(server, game_id=game_id, catalog=catalog)

    support_profile = _request(server, "GET", f"/games/{game_id}/support-profile")
    rows = [
        _json_object(row)
        for row in _field_list(support_profile, "datasheet_support_rows")
        if _field_string(_json_object(row), "ability_id") == "phase18e-generic-ir-no-consumer"
    ]
    assert len(rows) == 1
    assert _field_string(rows[0], "catalog_support") == CatalogAbilitySupport.GENERIC_RULE_IR.value
    assert _field_string(rows[0], "status") == "playable"
    assert support_profile["overall_status"] == "playable"


def test_phase18e_server_submission_rejections_are_typed() -> None:
    server = AdapterGameServer()
    game_id = "phase18e-server-rejections"
    _create_game(server, game_id=game_id)
    first_status = _request(server, "POST", f"/games/{game_id}/advance")
    first_request = _decision_from_status(server, game_id=game_id, payload=first_status)

    stale = _request_raw(
        server,
        "POST",
        f"/games/{game_id}/decisions/stale-request/option",
        body={
            "actor_id": _actor(first_request),
            "option_id": FIXED_SECONDARY_OPTION_ID,
            "result_id": "phase18e-stale",
        },
    )
    assert stale.status_code == 409
    assert _error_code(stale) == "stale_request_id"

    wrong_actor = _request_raw(
        server,
        "POST",
        f"/games/{game_id}/decisions/{first_request['request_id']}/option",
        body={
            "actor_id": PLAYER_B,
            "option_id": FIXED_SECONDARY_OPTION_ID,
            "result_id": "phase18e-wrong-actor",
        },
    )
    assert wrong_actor.status_code == 403
    assert _error_code(wrong_actor) == "wrong_actor"

    wrong_option = _request_raw(
        server,
        "POST",
        f"/games/{game_id}/decisions/{first_request['request_id']}/option",
        body={
            "actor_id": _actor(first_request),
            "option_id": "client-invented-option",
            "result_id": "phase18e-wrong-option",
        },
    )
    assert wrong_option.status_code == 422
    assert _error_code(wrong_option) == "wrong_selected_option"

    malformed = _request_raw(
        server,
        "POST",
        f"/games/{game_id}/decisions/{first_request['request_id']}/payload",
        body={"actor_id": _actor(first_request), "result_id": "phase18e-malformed"},
    )
    assert malformed.status_code == 400
    assert _error_code(malformed) == "malformed_payload"

    raw_dice = _request_raw(
        server,
        "POST",
        f"/games/{game_id}/decisions/{first_request['request_id']}/payload",
        body={
            "actor_id": _actor(first_request),
            "payload": {
                "roll_id": "roll-000001",
                "spec": {},
                "values": [6],
                "total": 6,
                "source": "rng",
            },
            "result_id": "phase18e-raw-dice",
        },
    )
    assert raw_dice.status_code == 400
    assert _error_code(raw_dice) == "client_raw_dice_rejected"

    fresh = AdapterGameServer()
    _create_game(fresh, game_id=f"{game_id}-drift")
    placement_request = _advance_to_first_deployment_placement(fresh, game_id=f"{game_id}-drift")
    placement_view = _request(
        fresh,
        "GET",
        f"/games/{game_id}-drift/view",
        query={"viewer_player_id": _actor(placement_request)},
    )
    drifted_payload = _deployment_payload_from_proposal(
        _field_object(placement_view, "pending_proposal")
    )
    drifted_payload["proposal_request_id"] = "phase18e-drifted-request"
    drift = _request_raw(
        fresh,
        "POST",
        f"/games/{game_id}-drift/decisions/{placement_request['request_id']}/payload",
        body={
            "actor_id": _actor(placement_request),
            "payload": drifted_payload,
            "result_id": "phase18e-payload-drift",
        },
    )
    assert drift.status_code == 422
    assert _status_kind(_json_object(drift.payload)) == "invalid"

    no_pending = AdapterGameServer()
    _create_game(no_pending, game_id=f"{game_id}-not-advanced")
    closed = _request_raw(
        no_pending,
        "POST",
        f"/games/{game_id}-not-advanced/decisions/decision-request-000001/option",
        body={
            "actor_id": PLAYER_A,
            "option_id": FIXED_SECONDARY_OPTION_ID,
            "result_id": "phase18e-no-pending",
        },
    )
    assert closed.status_code == 409
    assert _error_code(closed) == "closed_or_terminal_session"


def test_phase18e_server_route_errors_are_typed() -> None:
    server = AdapterGameServer()
    game_id = "phase18e-server-route-errors"

    method_not_allowed = _request_raw(server, "PUT", "/rules-catalog")
    assert method_not_allowed.status_code == 405
    assert _error_code(method_not_allowed) == "method_not_allowed"

    not_found = _request_raw(server, "GET", "/missing-route")
    assert not_found.status_code == 404
    assert _error_code(not_found) == "route_not_found"

    missing_game = _request_raw(
        server,
        "GET",
        "/games/missing-game/view",
        query={"viewer_player_id": PLAYER_A},
    )
    assert missing_game.status_code == 404
    assert _error_code(missing_game) == "game_not_found"

    malformed_create = _request_raw(server, "POST", "/games", body=[])
    assert malformed_create.status_code == 400
    assert _error_code(malformed_create) == "malformed_payload"

    _create_game(server, game_id=game_id)

    duplicate = _request_raw(
        server,
        "POST",
        "/games",
        body=_game_config_body(game_id=game_id),
    )
    assert duplicate.status_code == 409
    assert _error_code(duplicate) == "game_already_exists"

    missing_viewer = _request_raw(server, "GET", f"/games/{game_id}/view")
    assert missing_viewer.status_code == 400
    assert _error_code(missing_viewer) == "missing_query_parameter"

    invalid_cursor = _request_raw(
        server,
        "GET",
        f"/games/{game_id}/events",
        query={"viewer_player_id": PLAYER_A, "cursor": "-1"},
    )
    assert invalid_cursor.status_code == 400
    assert _error_code(invalid_cursor) == "invalid_query_parameter"

    malformed_submission = _request_raw(
        server,
        "POST",
        "/games/phase18e-server-route-errors/decisions/decision-request-000001/option",
        body={
            "actor_id": PLAYER_A,
            "option_id": FIXED_SECONDARY_OPTION_ID,
            "result_id": "phase18e-extra",
            "extra": "client-field",
        },
    )
    assert malformed_submission.status_code == 400
    assert _error_code(malformed_submission) == "malformed_payload"

    with pytest.raises(ServerApiError):
        create_local_dev_http_server(api=cast(AdapterGameServer, object()))


def test_phase18e_local_dev_http_server_serves_json_and_rejects_bad_bodies() -> None:
    api = AdapterGameServer()
    http_server = create_local_dev_http_server(api=api)
    host, port = cast(tuple[str, int], http_server.server_address)
    thread = Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{host}:{port}"
    game_id = "phase18e-http-smoke"

    try:
        created = _http_json(
            "POST",
            f"{base_url}/games",
            body=_game_config_body(game_id=game_id),
        )
        assert created["game_id"] == game_id
        assert _status_kind(created) == "advanced"

        view = _http_json(
            "GET",
            f"{base_url}/games/{game_id}/view?viewer_player_id={PLAYER_A}",
        )
        _schema_validator("game_view.schema.json").validate(view)

        ambiguous_query = _http_error(
            Request(f"{base_url}/rules-catalog?viewer=one&viewer=two", method="GET")
        )
        assert ambiguous_query.code == 400
        assert _http_error_code(ambiguous_query) == "ambiguous_query_parameter"

        bad_json = _http_error(
            Request(
                f"{base_url}/games",
                data=b"{",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
        )
        assert bad_json.code == 400
        assert _http_error_code(bad_json) == "malformed_json_body"

        bad_utf8 = _http_error(
            Request(
                f"{base_url}/games",
                data=b"\xff",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
        )
        assert bad_utf8.code == 400
        assert _http_error_code(bad_utf8) == "malformed_json_body"
    finally:
        http_server.shutdown()
        thread.join(timeout=10.0)
        http_server.server_close()


def test_phase18e_network_client_observes_server_owned_dice_through_events_and_view() -> None:
    server = AdapterGameServer()
    game_id = "phase18e-server-dice-stream"
    _create_game(server, game_id=game_id)
    status_payload = _advance_to_movement_selection(server, game_id=game_id)
    movement_request = _decision_from_status(server, game_id=game_id, payload=status_payload)
    assert movement_request["decision_type"] == SELECT_MOVEMENT_UNIT

    status_payload = _submit_option(
        server,
        game_id=game_id,
        request=movement_request,
        option_id=_first_option_id(movement_request),
        result_id=f"{game_id}-movement-unit",
    )
    action_request = _decision_from_status(server, game_id=game_id, payload=status_payload)
    assert action_request["decision_type"] == SELECT_MOVEMENT_ACTION
    advance_body: dict[str, JsonValue] = {
        "actor_id": _actor(action_request),
        "option_id": ADVANCE_ACTION_OPTION_ID,
        "result_id": f"{game_id}-advance-action",
    }
    assert "values" not in advance_body
    assert "roll_id" not in advance_body
    status_payload = _request(
        server,
        "POST",
        f"/games/{game_id}/decisions/{action_request['request_id']}/option",
        body=advance_body,
    )
    assert _status_kind(status_payload) == "waiting_for_decision"

    event_delta = _request(
        server,
        "GET",
        f"/games/{game_id}/events",
        query={"viewer_player_id": PLAYER_A, "cursor": "0"},
    )
    dice_events: list[dict[str, JsonValue]] = []
    for event_value in _field_list(event_delta, "events"):
        event = _json_object(event_value)
        if _field_string(event, "event_type") == "dice_rolled":
            dice_events.append(event)
    assert dice_events
    assert _field_list(_field_object(dice_events[0], "payload"), "values")

    view = _request(
        server,
        "GET",
        f"/games/{game_id}/view",
        query={"viewer_player_id": PLAYER_A},
    )
    pending_proposal = _field_object(view, "pending_proposal")
    assert _contains_key(pending_proposal, "advance_roll")
    assert _contains_key(pending_proposal, "current_values")


def test_phase18e_legal_decision_choice_changes_next_rng_lineage_not_only_die_value() -> None:
    left = LocalGameSession()
    right = LocalGameSession()
    config = _config(game_id="phase18e-lineage")
    left.start(config)
    right.start(config)
    left_request = _decision_from_lifecycle_status(left.advance_until_decision_or_terminal())
    right_request = _decision_from_lifecycle_status(right.advance_until_decision_or_terminal())
    assert left_request.to_payload() == right_request.to_payload()

    left.submit_option(
        request_id=left_request.request_id,
        option_id=FIXED_SECONDARY_OPTION_ID,
        result_id="phase18e-left-fixed",
    )
    right.submit_option(
        request_id=right_request.request_id,
        option_id="tactical",
        result_id="phase18e-right-tactical",
    )

    left_manager = DiceRollManager(
        "phase18e-lineage",
        event_log=left.lifecycle.decision_controller.event_log,
    )
    right_manager = DiceRollManager(
        "phase18e-lineage",
        event_log=right.lifecycle.decision_controller.event_log,
    )
    left_pre_roll_digest = left_manager.rng.history_digest()
    right_pre_roll_digest = right_manager.rng.history_digest()
    assert left_pre_roll_digest != right_pre_roll_digest

    spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Phase 18E lineage regression probe",
        roll_type="phase18e_lineage_probe",
        actor_id=PLAYER_A,
    )
    left_roll = left_manager.roll(spec)
    right_roll = right_manager.roll(spec)

    assert left_roll.original_result.spec == right_roll.original_result.spec
    assert left_manager.rng.history_digest() != right_manager.rng.history_digest()
    assert left_manager.rng.to_payload()["history"] != right_manager.rng.to_payload()["history"]


def _create_game(
    server: AdapterGameServer,
    *,
    game_id: str,
    catalog: ArmyCatalog | None = None,
) -> None:
    payload = _request(
        server,
        "POST",
        "/games",
        body=_game_config_body(game_id=game_id, catalog=catalog),
        expected_status=201,
    )
    assert payload["game_id"] == game_id
    assert _status_kind(payload) == "advanced"


def _game_config_body(
    *,
    game_id: str,
    catalog: ArmyCatalog | None = None,
) -> dict[str, JsonValue]:
    return {
        "config": validate_json_value(
            cast(JsonValue, _config(game_id=game_id, catalog=catalog).to_payload())
        )
    }


def _http_json(
    method: str,
    url: str,
    *,
    body: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    encoded_body = None if body is None else json.dumps(body, sort_keys=True).encode("utf-8")
    headers = {} if body is None else {"Content-Type": "application/json"}
    request = Request(url, data=encoded_body, method=method, headers=headers)
    response = cast(HTTPResponse, urlopen(request, timeout=10.0))
    try:
        payload = validate_json_value(json.loads(response.read().decode("utf-8")))
    finally:
        response.close()
    return _json_object(payload)


def _http_error(request: Request) -> HTTPError:
    with pytest.raises(HTTPError) as exc_info:
        urlopen(request, timeout=10.0)
    return exc_info.value


def _http_error_code(error: HTTPError) -> str:
    payload = validate_json_value(json.loads(error.read().decode("utf-8")))
    return _field_string(_field_object(_json_object(payload), "error"), "code")


def _advance_to_first_deployment_placement(
    server: AdapterGameServer,
    *,
    game_id: str,
) -> dict[str, JsonValue]:
    status_payload = _request(server, "POST", f"/games/{game_id}/advance")
    first_request = _decision_from_status(server, game_id=game_id, payload=status_payload)
    status_payload = _submit_option(
        server,
        game_id=game_id,
        request=first_request,
        option_id=FIXED_SECONDARY_OPTION_ID,
        result_id=f"{game_id}-secondary-a",
    )
    second_request = _decision_from_status(server, game_id=game_id, payload=status_payload)
    status_payload = _submit_option(
        server,
        game_id=game_id,
        request=second_request,
        option_id=FIXED_SECONDARY_OPTION_ID,
        result_id=f"{game_id}-secondary-b",
    )
    selection_request = _decision_from_status(server, game_id=game_id, payload=status_payload)
    status_payload = _submit_option(
        server,
        game_id=game_id,
        request=selection_request,
        option_id=_first_option_id(selection_request),
        result_id=f"{game_id}-deployment-unit",
    )
    return _decision_from_status(server, game_id=game_id, payload=status_payload)


def _advance_to_movement_selection(
    server: AdapterGameServer,
    *,
    game_id: str,
) -> dict[str, JsonValue]:
    status_payload = _request(server, "POST", f"/games/{game_id}/advance")
    while True:
        request = _decision_from_status(server, game_id=game_id, payload=status_payload)
        decision_type = request["decision_type"]
        if decision_type == SECONDARY_MISSION_DECISION_TYPE:
            status_payload = _submit_option(
                server,
                game_id=game_id,
                request=request,
                option_id=FIXED_SECONDARY_OPTION_ID,
                result_id=f"{game_id}-{request['request_id']}-secondary",
            )
            continue
        if decision_type == SELECT_DEPLOYMENT_UNIT:
            status_payload = _submit_option(
                server,
                game_id=game_id,
                request=request,
                option_id=_first_option_id(request),
                result_id=f"{game_id}-{request['request_id']}-deployment-unit",
            )
            continue
        if decision_type == SUBMIT_DEPLOYMENT_PLACEMENT:
            view = _request(
                server,
                "GET",
                f"/games/{game_id}/view",
                query={"viewer_player_id": _actor(request)},
            )
            status_payload = _submit_payload(
                server,
                game_id=game_id,
                request=request,
                payload=_deployment_payload_from_proposal(_field_object(view, "pending_proposal")),
                result_id=f"{game_id}-{request['request_id']}-deployment-placement",
            )
            continue
        assert decision_type == SELECT_MOVEMENT_UNIT
        return status_payload


def _submit_option(
    server: AdapterGameServer,
    *,
    game_id: str,
    request: dict[str, JsonValue],
    option_id: str,
    result_id: str,
) -> dict[str, JsonValue]:
    body: dict[str, JsonValue] = {
        "actor_id": _actor(request),
        "option_id": option_id,
        "result_id": result_id,
    }
    return _request(
        server,
        "POST",
        f"/games/{game_id}/decisions/{_request_id(request)}/option",
        body=body,
    )


def _submit_payload(
    server: AdapterGameServer,
    *,
    game_id: str,
    request: dict[str, JsonValue],
    payload: JsonValue,
    result_id: str,
) -> dict[str, JsonValue]:
    body: dict[str, JsonValue] = {
        "actor_id": _actor(request),
        "payload": payload,
        "result_id": result_id,
    }
    return _request(
        server,
        "POST",
        f"/games/{game_id}/decisions/{_request_id(request)}/payload",
        body=body,
    )


def _deployment_payload_from_proposal(value: JsonValue) -> dict[str, JsonValue]:
    proposal = _json_object(value)
    player_id = _json_string(proposal["player_id"])
    unit_instance_id = _json_string(proposal["unit_instance_id"])
    army_id = unit_instance_id.split(":", maxsplit=1)[0]
    zone = _json_object(_json_list(proposal["legal_deployment_zones"])[0])
    first_polygon = _json_object(_json_list(_json_object(zone["shape"])["polygons"])[0])
    vertices = _json_list(first_polygon["vertices"])
    min_x = min(_json_float(_json_object(vertex)["x"]) for vertex in vertices)
    min_y = min(_json_float(_json_object(vertex)["y"]) for vertex in vertices)
    facing = 180.0 if player_id == PLAYER_B else 0.0
    model_placements: list[JsonValue] = []
    for index, model_instance_id_value in enumerate(_json_list(proposal["model_instance_ids"])):
        model_instance_id = _json_string(model_instance_id_value)
        row = index // 3
        column = index % 3
        model_placements.append(
            {
                "army_id": army_id,
                "player_id": player_id,
                "unit_instance_id": unit_instance_id,
                "model_instance_id": model_instance_id,
                "pose": {
                    "position": {
                        "x": min_x + 3.0 + (row * 1.8),
                        "y": min_y + 3.0 + (column * 1.8),
                        "z": 0.0,
                    },
                    "facing": {"degrees": facing},
                },
            }
        )
    return {
        "proposal_request_id": _json_string(proposal["request_id"]),
        "proposal_kind": _json_string(proposal["proposal_kind"]),
        "game_id": _json_string(proposal["game_id"]),
        "ruleset_descriptor_hash": _json_string(proposal["ruleset_descriptor_hash"]),
        "setup_step": _json_string(proposal["setup_step"]),
        "player_id": player_id,
        "unit_instance_id": unit_instance_id,
        "placement_kind": _json_string(proposal["placement_kind"]),
        "model_placements": model_placements,
        "context": proposal["context"],
    }


def _request(
    server: AdapterGameServer,
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: JsonValue = None,
    expected_status: int = 200,
) -> dict[str, JsonValue]:
    response = _request_raw(server, method, path, query=query, body=body)
    assert response.status_code == expected_status, response.payload
    return _json_object(response.payload)


def _request_raw(
    server: AdapterGameServer,
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: JsonValue = None,
) -> ServerResponse:
    return server.handle(method=method, path=path, query=query, body=body)


def _decision_from_status(
    server: AdapterGameServer,
    *,
    game_id: str,
    payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    status = _field_object(payload, "status")
    assert _field_string(status, "status_kind") == "waiting_for_decision"
    actor_id = _field_string(status, "actor_id")
    request_id = _field_string(status, "pending_request_id")
    view = _request(
        server,
        "GET",
        f"/games/{game_id}/view",
        query={"viewer_player_id": actor_id},
    )
    decision = _field_object(view, "pending_decision")
    assert _field_string(decision, "request_id") == request_id
    return decision


def _decision_from_lifecycle_status(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _first_option_id(request: dict[str, JsonValue]) -> str:
    options = _json_list(request["options"])
    assert options
    return _json_string(_json_object(options[0])["option_id"])


def _request_id(request: dict[str, JsonValue]) -> str:
    return _field_string(request, "request_id")


def _actor(request: dict[str, JsonValue]) -> str:
    return _field_string(request, "actor_id")


def _status_kind(payload: dict[str, JsonValue]) -> str:
    return _field_string(_field_object(payload, "status"), "status_kind")


def _error_code(response: ServerResponse) -> str:
    payload = _json_object(response.payload)
    return _field_string(_field_object(payload, "error"), "code")


def _contains_key(value: JsonValue, key: str) -> bool:
    if isinstance(value, dict):
        if key in value:
            return True
        return any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def _catalog_with_selected_generic_ir_ability() -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    added_ability = DatasheetAbilityDescriptor(
        ability_id="phase18e-generic-ir-no-consumer",
        name="Phase 18E Generic IR No Consumer",
        source_id="phase18e:test:generic-ir-no-consumer",
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.CORE,
        effect_description="Structured generic IR without a phase host consumer.",
        timing_tags=("command_phase",),
        parameter_tokens=(),
        rule_ir_payload={"kind": "phase18e_test_no_consumer"},
    )
    datasheets = tuple(
        replace(datasheet, abilities=(*datasheet.abilities, added_ability))
        if datasheet.datasheet_id == "core-intercessor-like-infantry"
        else datasheet
        for datasheet in catalog.datasheets
    )
    return replace(catalog, datasheets=datasheets)


def _config(*, game_id: str, catalog: ArmyCatalog | None = None) -> GameConfig:
    army_catalog = ArmyCatalog.phase9a_canonical_content_pack() if catalog is None else catalog
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase18e-server-test"
        ),
        army_catalog=army_catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=army_catalog,
                player_id=PLAYER_A,
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _army_muster_request(
                catalog=army_catalog,
                player_id=PLAYER_B,
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
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
            defender_player_id=PLAYER_B,
        ),
    )


def _army_muster_request(
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


def _schema_validator(schema_name: str) -> _PayloadValidator:
    schema = _schema_payloads()[schema_name]
    return cast(_PayloadValidator, Draft202012Validator(schema, registry=_schema_registry()))


def _schema_payloads() -> dict[str, Schema]:
    names = (
        "decision_request_view.schema.json",
        "event_stream_delta.schema.json",
        "game_view.schema.json",
        "rules_catalog_view.schema.json",
    )
    return {name: cast(Schema, _read_json(REPO_ROOT / "docs" / "api" / name)) for name in names}


def _schema_registry() -> SchemaRegistry:
    registry = EMPTY_REGISTRY
    for schema in _schema_payloads().values():
        if not isinstance(schema, dict):
            raise TypeError("API schemas must be JSON objects.")
        schema_id = schema.get("$id")
        assert type(schema_id) is str
        resource = cast(
            SchemaResource,
            Resource.from_contents(cast(Schema, schema), default_specification=DRAFT202012),
        )
        registry = registry.with_resource(schema_id, resource)
    return registry


def _read_json(path: Path) -> dict[str, JsonValue]:
    payload = validate_json_value(json.loads(path.read_text(encoding="utf-8")))
    assert isinstance(payload, dict)
    return payload


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _json_list(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _field_object(payload: dict[str, JsonValue], key: str) -> dict[str, JsonValue]:
    return _json_object(payload[key])


def _field_list(payload: dict[str, JsonValue], key: str) -> list[JsonValue]:
    return _json_list(payload[key])


def _field_string(payload: dict[str, JsonValue], key: str) -> str:
    return _json_string(payload[key])


def _field_int(payload: dict[str, JsonValue], key: str) -> int:
    return _json_int(payload[key])


def _json_string(value: JsonValue) -> str:
    assert type(value) is str
    return value


def _json_int(value: JsonValue) -> int:
    assert type(value) is int
    return value


def _json_float(value: JsonValue) -> float:
    if type(value) is int:
        return float(value)
    assert type(value) is float
    return value
