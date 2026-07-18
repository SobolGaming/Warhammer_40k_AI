from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import cast

from export_ui_contract_fixtures import export_ui_contract_files
from jsonschema import Draft202012Validator
from referencing import Resource
from referencing.jsonschema import DRAFT202012, EMPTY_REGISTRY, Schema, SchemaRegistry

from warhammer40k_core.adapters.external_contract import (
    CREATE_SESSION_SCHEMA_VERSION,
    DECISION_REQUEST_VIEW_SCHEMA_VERSION,
    ERROR_ENVELOPE_SCHEMA_VERSION,
    EVENT_STREAM_DELTA_SCHEMA_VERSION,
    EXTERNAL_CONTRACT_VERSION,
    FINITE_SUBMISSION_SCHEMA_VERSION,
    LIFECYCLE_STATUS_SCHEMA_VERSION,
    PARAMETERIZED_SUBMISSION_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.projection import (
    PROJECTION_SCHEMA_VERSION,
    RULES_CATALOG_VIEW_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.server import AdapterGameServer, ServerResponse
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.adapters.support_profile import SUPPORT_PROFILE_SCHEMA_VERSION
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.replay import REPLAY_ARTIFACT_SCHEMA_VERSION
from warhammer40k_core.engine.stratagems import (
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemTargetKind,
    StratagemTargetProposal,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "contracts"
SCHEMA_DIR = CONTRACT_ROOT / "schemas"
EXAMPLE_DIR = CONTRACT_ROOT / "examples"
PROJECTION_EXAMPLE_DIR = EXAMPLE_DIR / "projections"
DECISION_EXAMPLE_DIR = EXAMPLE_DIR / "decisions"
PROPOSAL_EXAMPLE_DIR = DECISION_EXAMPLE_DIR / "proposals"
PARAMETERIZED_EXAMPLE_DIR = DECISION_EXAMPLE_DIR / "parameterized"
DECISION_FAMILY_EXAMPLE_DIR = DECISION_EXAMPLE_DIR / "families"
EVENT_EXAMPLE_DIR = EXAMPLE_DIR / "events"
ERROR_EXAMPLE_DIR = EXAMPLE_DIR / "errors"
STATUS_EXAMPLE_DIR = EXAMPLE_DIR / "statuses"
SESSION_EXAMPLE_DIR = EXAMPLE_DIR / "sessions"
BASELINE_PATH = CONTRACT_ROOT / "compatibility" / "1.0.0-shape.json"
MANIFEST_PATH = CONTRACT_ROOT / "manifest.json"
OPENAPI_PATH = CONTRACT_ROOT / "openapi.yaml"
SRC_ROOT = ROOT / "src" / "warhammer40k_core"

PRIMARY_SCHEMA_NAMES = frozenset(
    {
        "create-session.schema.json",
        "decision-request-view.schema.json",
        "error-envelope.schema.json",
        "event-delta.schema.json",
        "finite-submission.schema.json",
        "game-view.schema.json",
        "lifecycle-status.schema.json",
        "parameterized-submission.schema.json",
        "proposal-payload.schema.json",
        "replay-metadata.schema.json",
        "rules-catalog.schema.json",
        "support-profile.schema.json",
    }
)
PAYLOAD_SCHEMA_VERSION_BY_NAME = {
    "create-session.schema.json": ("schema_version", CREATE_SESSION_SCHEMA_VERSION),
    "decision-request-view.schema.json": (
        "schema_version",
        DECISION_REQUEST_VIEW_SCHEMA_VERSION,
    ),
    "error-envelope.schema.json": ("schema_version", ERROR_ENVELOPE_SCHEMA_VERSION),
    "event-delta.schema.json": ("schema_version", EVENT_STREAM_DELTA_SCHEMA_VERSION),
    "finite-submission.schema.json": ("schema_version", FINITE_SUBMISSION_SCHEMA_VERSION),
    "game-view.schema.json": ("projection_schema", PROJECTION_SCHEMA_VERSION),
    "lifecycle-status.schema.json": ("schema_version", LIFECYCLE_STATUS_SCHEMA_VERSION),
    "parameterized-submission.schema.json": (
        "schema_version",
        PARAMETERIZED_SUBMISSION_SCHEMA_VERSION,
    ),
    "replay-metadata.schema.json": ("schema_version", REPLAY_ARTIFACT_SCHEMA_VERSION),
    "rules-catalog.schema.json": (
        "projection_schema",
        RULES_CATALOG_VIEW_SCHEMA_VERSION,
    ),
    "support-profile.schema.json": ("schema_version", SUPPORT_PROFILE_SCHEMA_VERSION),
}


class ExternalContractError(ValueError):
    """Raised when the committed external contract bundle is invalid or drifted."""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify the versioned Phase 18D external contract bundle."
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()
    if args.check and args.write_baseline:
        raise ExternalContractError("--check and --write-baseline are mutually exclusive.")
    if args.check:
        verify_contract_bundle()
        return 0
    write_contract_examples()
    if args.write_baseline:
        _write_json(BASELINE_PATH, _compatibility_baseline())
    _write_json(MANIFEST_PATH, _contract_manifest())
    verify_contract_bundle()
    return 0


def write_contract_examples() -> None:
    export_ui_contract_files(output_root=ROOT)
    _write_missing_proposal_examples()

    config = canonical_setup_prebattle_smoke_config(game_id="phase18d-contract-session")
    create_payload: JsonValue = {
        "schema_version": CREATE_SESSION_SCHEMA_VERSION,
        "config": config.to_payload(),
    }
    _write_json(SESSION_EXAMPLE_DIR / "create-session.json", create_payload)

    server = AdapterGameServer()
    created = _successful_response(
        server.handle(method="POST", path="/games", body=create_payload),
        expected_status=201,
    )
    _write_json(STATUS_EXAMPLE_DIR / "advanced.json", created)
    waiting = _successful_response(
        server.handle(method="POST", path=f"/games/{config.game_id}/advance"),
        expected_status=200,
    )
    _write_json(STATUS_EXAMPLE_DIR / "waiting-for-decision.json", waiting)

    player_a_view = _successful_response(
        server.handle(
            method="GET",
            path=f"/games/{config.game_id}/view",
            query={"viewer_player_id": "player-a"},
        ),
        expected_status=200,
    )
    pending = _json_object(player_a_view["pending_decision"], "pending decision")
    options = _json_list(pending["options"], "pending decision options")
    first_option = _json_object(options[0], "pending decision option")
    finite_submission: JsonValue = {
        "schema_version": FINITE_SUBMISSION_SCHEMA_VERSION,
        "actor_id": _required_string(pending, "actor_id"),
        "option_id": _required_string(first_option, "option_id"),
        "result_id": "phase18d-finite-result-000001",
    }
    _write_json(DECISION_EXAMPLE_DIR / "finite-submission.json", finite_submission)

    _write_server_read_examples(server=server, game_id=config.game_id)
    _write_decision_family_examples()
    _write_parameterized_submission_examples()
    _write_status_examples(game_id=config.game_id)
    _write_error_examples()


def verify_contract_bundle() -> None:
    schemas = _schema_payloads()
    if set(schemas) != set(_schema_file_names()):
        raise ExternalContractError("External contract schema discovery drifted.")
    missing_primary = PRIMARY_SCHEMA_NAMES - set(schemas)
    if missing_primary:
        raise ExternalContractError(
            "External contract is missing primary schemas: " + ", ".join(sorted(missing_primary))
        )
    registry = _schema_registry(schemas)
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    _verify_python_schema_versions(schemas)

    manifest = _json_object(_read_json(MANIFEST_PATH), "contract manifest")
    if manifest["contract_version"] != EXTERNAL_CONTRACT_VERSION:
        raise ExternalContractError("External contract manifest version drifted.")
    expected_manifest = _contract_manifest()
    if manifest != expected_manifest:
        raise ExternalContractError(
            "External contract manifest drifted; run scripts/build_external_contract.py."
        )

    example_bindings = _json_object(manifest["example_schema_by_path"], "example bindings")
    for relative_path, schema_name_value in sorted(example_bindings.items()):
        if type(schema_name_value) is not str:
            raise ExternalContractError("Example schema binding must be a string.")
        schema = schemas[schema_name_value]
        Draft202012Validator(schema, registry=registry).validate(
            _read_json(CONTRACT_ROOT / relative_path)
        )

    _verify_decision_and_proposal_coverage()
    _verify_openapi(schemas)
    _verify_compatibility(schemas)


def _verify_python_schema_versions(schemas: dict[str, Schema]) -> None:
    for schema_name, (property_name, expected) in PAYLOAD_SCHEMA_VERSION_BY_NAME.items():
        schema = _json_object(schemas[schema_name], schema_name)
        properties = _json_object(schema["properties"], f"{schema_name} properties")
        property_schema = _json_object(
            properties[property_name],
            f"{schema_name} {property_name}",
        )
        if property_schema.get("const") != expected:
            raise ExternalContractError(
                f"{schema_name} {property_name} drifted from Python payload version {expected}."
            )


def _write_server_read_examples(*, server: AdapterGameServer, game_id: str) -> None:
    for viewer in ("player-a", "player-b"):
        event_payload = _successful_response(
            server.handle(
                method="GET",
                path=f"/games/{game_id}/events",
                query={"viewer_player_id": viewer, "cursor": "0"},
            ),
            expected_status=200,
        )
        _write_json(EVENT_EXAMPLE_DIR / f"initial-{viewer}.json", event_payload)
    _write_json(
        EXAMPLE_DIR / "support-profile.json",
        _successful_response(
            server.handle(method="GET", path=f"/games/{game_id}/support-profile"),
            expected_status=200,
        ),
    )
    _write_json(
        EXAMPLE_DIR / "replay-metadata.json",
        _successful_response(
            server.handle(method="GET", path=f"/games/{game_id}/replay"),
            expected_status=200,
        ),
    )


def _write_decision_family_examples() -> None:
    for index, decision_type in enumerate(_decision_type_tokens(), start=1):
        is_parameterized = decision_type.startswith("submit_")
        option_id = "submit_parameterized_payload" if is_parameterized else "example-option"
        payload: JsonValue = {
            "schema_version": DECISION_REQUEST_VIEW_SCHEMA_VERSION,
            "request_id": f"contract-decision-request-{index:06d}",
            "decision_type": decision_type,
            "actor_id": "player-a",
            "payload": {
                "contract_fixture": True,
                "decision_type": decision_type,
            },
            "options": [
                {
                    "option_id": option_id,
                    "label": "Submit parameterized payload" if is_parameterized else "Example",
                    "payload": {"contract_fixture": True},
                }
            ],
            "is_parameterized": is_parameterized,
        }
        _write_json(DECISION_FAMILY_EXAMPLE_DIR / f"{decision_type}.json", payload)


def _write_parameterized_submission_examples() -> None:
    proposal_paths = {
        _proposal_kind(_read_json(path)): path
        for path in sorted(PROPOSAL_EXAMPLE_DIR.glob("*.json"))
    }
    expected_kinds = set(_proposal_kind_tokens())
    if set(proposal_paths) != expected_kinds:
        missing = sorted(expected_kinds - set(proposal_paths))
        extra = sorted(set(proposal_paths) - expected_kinds)
        raise ExternalContractError(
            f"Proposal example coverage drifted; missing={missing}, extra={extra}."
        )
    for proposal_kind, path in sorted(proposal_paths.items()):
        wrapper: JsonValue = {
            "schema_version": PARAMETERIZED_SUBMISSION_SCHEMA_VERSION,
            "actor_id": "player-a",
            "payload": _read_json(path),
            "result_id": f"phase18d-{proposal_kind}-result-000001",
        }
        _write_json(PARAMETERIZED_EXAMPLE_DIR / f"{proposal_kind}.json", wrapper)


def _write_missing_proposal_examples() -> None:
    examples = _supplemental_proposal_examples()
    for proposal_kind, payload in sorted(examples.items()):
        _write_json(PROPOSAL_EXAMPLE_DIR / f"{proposal_kind}.json", payload)


def _supplemental_proposal_examples() -> dict[str, JsonValue]:
    pose = {
        "position": {"x": 12.0, "y": 18.0, "z": 0.0},
        "facing": {"degrees": 0.0},
    }
    model_placement = {
        "army_id": "army-alpha",
        "player_id": "player-a",
        "unit_instance_id": "army-alpha:unit-1",
        "model_instance_id": "army-alpha:unit-1:model-1",
        "pose": pose,
    }
    placement = {
        "army_id": "army-alpha",
        "player_id": "player-a",
        "unit_instance_id": "army-alpha:unit-1",
        "model_placements": [model_placement],
    }
    empty_witness = {"model_paths": []}
    source_hash = "0" * 64
    return {
        "advance": {
            "proposal_request_id": "contract-advance-request-000001",
            "proposal_kind": "advance",
            "unit_instance_id": "army-alpha:unit-1",
            "movement_phase_action": "advance",
            "movement_mode": "advance",
            "witness": empty_witness,
        },
        "consolidate": {
            "proposal_request_id": "contract-consolidate-request-000001",
            "proposal_kind": "consolidate",
            "unit_instance_id": "army-alpha:unit-1",
            "movement_phase_action": "consolidate",
            "movement_mode": "consolidate",
            "consolidate_target_unit_instance_ids": [],
        },
        "cult_ambush_placement": {
            "proposal_request_id": "contract-cult-ambush-request-000001",
            "proposal_kind": "cult_ambush_placement",
            "unit_instance_id": "army-alpha:unit-1",
            "placement_kind": "cult_ambush",
            "attempted_placement": placement,
        },
        "deep_strike_placement": {
            "proposal_request_id": "contract-deep-strike-request-000001",
            "proposal_kind": "deep_strike_placement",
            "unit_instance_id": "army-alpha:unit-1",
            "placement_kind": "deep_strike",
            "attempted_placement": placement,
        },
        "disembark_placement": {
            "proposal_request_id": "contract-disembark-request-000001",
            "proposal_kind": "disembark_placement",
            "unit_instance_id": "army-alpha:unit-1",
            "placement_kind": "disembark",
            "transport_unit_instance_id": "army-alpha:transport-1",
            "disembark_mode": "tactical_disembark",
            "attempted_placement": placement,
        },
        "fall_back": {
            "proposal_request_id": "contract-fall-back-request-000001",
            "proposal_kind": "fall_back",
            "unit_instance_id": "army-alpha:unit-1",
            "movement_phase_action": "fall_back",
            "movement_mode": "ordered_retreat",
            "witness": empty_witness,
        },
        "pile_in": {
            "proposal_request_id": "contract-pile-in-request-000001",
            "proposal_kind": "pile_in",
            "unit_instance_id": "army-alpha:unit-1",
            "movement_phase_action": "pile_in",
            "movement_mode": "pile_in",
            "pile_in_target_unit_instance_ids": [],
        },
        "redeploy_placement": {
            "proposal_request_id": "contract-redeploy-request-000001",
            "proposal_kind": "redeploy_placement",
            "game_id": "phase18d-contract-session",
            "ruleset_descriptor_hash": source_hash,
            "setup_step": "redeploy_units",
            "player_id": "player-a",
            "unit_instance_id": "army-alpha:unit-1",
            "action_kind": "redeploy",
            "source_rule_id": "source-rule:redeploy",
            "placement_kind": "redeploy",
            "model_placements": [model_placement],
            "context": {"contract_fixture": True},
        },
        "reinforcement_placement": {
            "proposal_request_id": "contract-reinforcement-request-000001",
            "proposal_kind": "reinforcement_placement",
            "unit_instance_id": "army-alpha:unit-1",
            "placement_kind": "strategic_reserves",
            "attempted_placement": placement,
        },
        "scout_move": {
            "proposal_request_id": "contract-scout-move-request-000001",
            "proposal_kind": "scout_move",
            "game_id": "phase18d-contract-session",
            "ruleset_descriptor_hash": source_hash,
            "setup_step": "resolve_prebattle_actions",
            "player_id": "player-a",
            "unit_instance_id": "army-alpha:unit-1",
            "action_kind": "scout_move",
            "source_rule_id": "source-rule:scouts",
            "scout_distance_inches": 6,
            "witness": empty_witness,
            "context": {"contract_fixture": True},
        },
        "scout_reserve_setup": {
            "proposal_request_id": "contract-scout-reserve-request-000001",
            "proposal_kind": "scout_reserve_setup",
            "game_id": "phase18d-contract-session",
            "ruleset_descriptor_hash": source_hash,
            "setup_step": "resolve_prebattle_actions",
            "player_id": "player-a",
            "unit_instance_id": "army-alpha:unit-1",
            "action_kind": "scout_reserve_setup",
            "source_rule_id": "source-rule:scouts",
            "placement_kind": "strategic_reserves",
            "model_placements": [model_placement],
            "context": {"contract_fixture": True},
        },
        "stratagem_target_binding": _stratagem_proposal_example(),
        "strategic_reserves_placement": {
            "proposal_request_id": "contract-strategic-reserves-request-000001",
            "proposal_kind": "strategic_reserves_placement",
            "unit_instance_id": "army-alpha:unit-1",
            "placement_kind": "strategic_reserves",
            "attempted_placement": placement,
        },
        "surge_move": {
            "proposal_request_id": "contract-surge-request-000001",
            "proposal_kind": "surge_move",
            "unit_instance_id": "army-alpha:unit-1",
            "movement_phase_action": "surge_move",
            "movement_mode": "surge_move",
            "witness": empty_witness,
        },
    }


def _stratagem_proposal_example() -> JsonValue:
    context = StratagemEligibilityContext(
        game_id="phase18d-contract-session",
        player_id="player-a",
        battle_round=1,
        phase=BattlePhaseKind.MOVEMENT,
        active_player_id="player-a",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    record = StratagemCatalogRecord(
        record_id="phase18d-contract-parameterized-stratagem",
        definition=StratagemDefinition(
            stratagem_id="phase18d-parameterized-target",
            name="Phase 18D Parameterized Target",
            source_id="source:phase18d-parameterized-target",
            command_point_cost=1,
            category=StratagemCategory.BATTLE_TACTIC,
            when_descriptor="Start of Movement phase",
            target_descriptor="One friendly unit",
            effect_descriptor="Contract fixture effect",
            restrictions_descriptor="Contract fixture restriction",
            timing=StratagemTimingDescriptor(
                trigger_kind=TimingTriggerKind.START_PHASE,
                phase=BattlePhaseKind.MOVEMENT,
            ),
            target_spec=StratagemTargetSpec(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                enumerable=False,
                target_policy_id="contract-friendly-unit",
            ),
        ),
    )
    return cast(
        JsonValue,
        StratagemTargetProposal.for_request(
            context=context,
            catalog_record=record,
        ).to_payload(),
    )


def _write_status_examples(*, game_id: str) -> None:
    statuses: dict[str, JsonValue] = {
        "invalid": _status_example(game_id=game_id, status_kind="invalid", message="Invalid."),
        "terminal": _status_example(
            game_id=game_id,
            status_kind="terminal",
            message="Game complete.",
        ),
        "unsupported": _status_example(
            game_id=game_id,
            status_kind="unsupported",
            message="Unsupported rule path.",
        ),
    }
    for name, payload in statuses.items():
        _write_json(STATUS_EXAMPLE_DIR / f"{name}.json", payload)


def _status_example(*, game_id: str, status_kind: str, message: str) -> JsonValue:
    return {
        "schema_version": LIFECYCLE_STATUS_SCHEMA_VERSION,
        "game_id": game_id,
        "status": {
            "stage": "complete" if status_kind == "terminal" else "setup",
            "status_kind": status_kind,
            "message": message,
            "payload": {"contract_fixture": True},
            "pending_request_id": None,
            "decision_type": None,
            "actor_id": None,
        },
    }


def _write_error_examples() -> None:
    errors = {
        "conflict": ("session_revision_conflict", "Session revision conflicted."),
        "corruption": ("session_corruption", "Session recovery verification failed."),
        "forbidden": ("actor_not_authorized", "Actor is not authorized."),
        "invalid": ("proposal_invalid", "Proposal is invalid."),
        "malformed": ("malformed_payload", "Payload is malformed."),
        "stale": ("stale_decision_request", "Decision request is stale."),
        "terminal": ("session_terminal", "Session is terminal."),
        "unsupported": ("rule_path_unsupported", "Rule path is unsupported."),
    }
    for name, (code, message) in errors.items():
        _write_json(
            ERROR_EXAMPLE_DIR / f"{name}.json",
            {
                "schema_version": ERROR_ENVELOPE_SCHEMA_VERSION,
                "error": {"code": code, "message": message},
            },
        )


def _contract_manifest() -> JsonValue:
    schemas = _schema_payloads()
    example_bindings = _example_schema_bindings()
    hashes: dict[str, str] = {}
    for path in sorted(
        (
            *(SCHEMA_DIR.glob("*.json")),
            *(CONTRACT_ROOT.rglob("*.md")),
            OPENAPI_PATH,
            *(CONTRACT_ROOT.glob("*.json")),
            *(EXAMPLE_DIR.rglob("*.json")),
        )
    ):
        if path in {MANIFEST_PATH, BASELINE_PATH} or not path.is_file():
            continue
        hashes[path.relative_to(CONTRACT_ROOT).as_posix()] = _file_hash(path)
    return {
        "contract_version": EXTERNAL_CONTRACT_VERSION,
        "decision_type_count": len(_decision_type_tokens()),
        "example_schema_by_path": example_bindings,
        "file_sha256": hashes,
        "proposal_kind_count": len(_proposal_kind_tokens()),
        "schema_ids": {
            name: _required_string(_json_object(schema, name), "$id")
            for name, schema in sorted(schemas.items())
        },
    }


def _example_schema_bindings() -> dict[str, JsonValue]:
    bindings: dict[str, JsonValue] = {}
    for path in sorted(PROJECTION_EXAMPLE_DIR.glob("*.json")):
        schema = (
            "rules-catalog.schema.json"
            if path.name == "rules_catalog_view.json"
            else ("game-view.schema.json")
        )
        bindings[path.relative_to(CONTRACT_ROOT).as_posix()] = schema
    bindings[
        (DECISION_EXAMPLE_DIR / "pending_movement_request.json")
        .relative_to(CONTRACT_ROOT)
        .as_posix()
    ] = "decision-request-view.schema.json"
    bindings[
        (DECISION_EXAMPLE_DIR / "finite-submission.json").relative_to(CONTRACT_ROOT).as_posix()
    ] = "finite-submission.schema.json"
    for path in sorted(DECISION_FAMILY_EXAMPLE_DIR.glob("*.json")):
        bindings[path.relative_to(CONTRACT_ROOT).as_posix()] = "decision-request-view.schema.json"
    for path in sorted(PARAMETERIZED_EXAMPLE_DIR.glob("*.json")):
        bindings[path.relative_to(CONTRACT_ROOT).as_posix()] = (
            "parameterized-submission.schema.json"
        )
    for path in sorted(PROPOSAL_EXAMPLE_DIR.glob("*.json")):
        bindings[path.relative_to(CONTRACT_ROOT).as_posix()] = "proposal-payload.schema.json"
    bindings["examples/decisions/opportunity_window.json"] = (
        "opportunity-window-example.schema.json"
    )
    for path in sorted(EVENT_EXAMPLE_DIR.glob("*.json")):
        bindings[path.relative_to(CONTRACT_ROOT).as_posix()] = "event-delta.schema.json"
    for path in sorted(ERROR_EXAMPLE_DIR.glob("*.json")):
        bindings[path.relative_to(CONTRACT_ROOT).as_posix()] = "error-envelope.schema.json"
    for path in sorted(STATUS_EXAMPLE_DIR.glob("*.json")):
        bindings[path.relative_to(CONTRACT_ROOT).as_posix()] = "lifecycle-status.schema.json"
    bindings["examples/sessions/create-session.json"] = "create-session.schema.json"
    bindings["examples/support-profile.json"] = "support-profile.schema.json"
    bindings["examples/replay-metadata.json"] = "replay-metadata.schema.json"
    return bindings


def _verify_decision_and_proposal_coverage() -> None:
    expected_decisions = set(_decision_type_tokens())
    actual_decisions = {path.stem for path in DECISION_FAMILY_EXAMPLE_DIR.glob("*.json")}
    if actual_decisions != expected_decisions:
        raise ExternalContractError("Decision-family example coverage drifted.")
    expected_proposals = set(_proposal_kind_tokens())
    actual_proposals = {path.stem for path in PARAMETERIZED_EXAMPLE_DIR.glob("*.json")}
    if actual_proposals != expected_proposals:
        raise ExternalContractError("Parameterized proposal example coverage drifted.")


def _verify_openapi(schemas: dict[str, Schema]) -> None:
    openapi = _json_object(_read_json(OPENAPI_PATH), "OpenAPI document")
    if openapi.get("openapi") != "3.1.0":
        raise ExternalContractError("OpenAPI document must use version 3.1.0.")
    info = _json_object(openapi["info"], "OpenAPI info")
    if info.get("version") != EXTERNAL_CONTRACT_VERSION:
        raise ExternalContractError("OpenAPI contract version drifted.")
    refs = _schema_refs(openapi)
    missing = sorted(
        ref for ref in refs if ref.startswith("./schemas/") and Path(ref).name not in schemas
    )
    if missing:
        raise ExternalContractError("OpenAPI references missing schemas: " + ", ".join(missing))
    referenced_names = {Path(ref).name for ref in refs if ref.startswith("./schemas/")}
    if not referenced_names >= PRIMARY_SCHEMA_NAMES:
        raise ExternalContractError("OpenAPI does not reference every primary contract schema.")


def _verify_compatibility(schemas: dict[str, Schema]) -> None:
    baseline = _json_object(_read_json(BASELINE_PATH), "compatibility baseline")
    baseline_version = _required_string(baseline, "contract_version")
    baseline_schemas = _json_object(baseline["schemas"], "baseline schemas")
    breaking: list[str] = []
    baseline_operations = _string_set(baseline.get("openapi_operations"))
    current_operations = set(_openapi_operations())
    for operation in sorted(baseline_operations - current_operations):
        breaking.append(f"openapi operation removed: {operation}")
    for name, baseline_schema in sorted(baseline_schemas.items()):
        current = schemas.get(name)
        if current is None:
            breaking.append(f"schemas.{name}: removed")
            continue
        breaking.extend(
            _breaking_changes(
                _json_object(baseline_schema, f"baseline {name}"),
                cast(dict[str, JsonValue], current),
                path=f"schemas.{name}",
            )
        )
    if breaking and _major_version(EXTERNAL_CONTRACT_VERSION) <= _major_version(baseline_version):
        raise ExternalContractError(
            "Breaking external contract change requires a major version increment:\n"
            + "\n".join(breaking)
        )


def _breaking_changes(
    baseline: dict[str, JsonValue],
    current: dict[str, JsonValue],
    *,
    path: str,
) -> list[str]:
    changes: list[str] = []
    if "$ref" in baseline and current.get("$ref") != baseline["$ref"]:
        changes.append(f"{path}.$ref changed")
    if "const" in baseline and current.get("const") != baseline["const"]:
        changes.append(f"{path}.const changed")
    baseline_types = _type_tokens(baseline.get("type"))
    current_types = _type_tokens(current.get("type"))
    if baseline_types and not baseline_types <= current_types:
        changes.append(f"{path}.type narrowed")
    baseline_enum = _json_scalar_set(baseline.get("enum"))
    current_enum = _json_scalar_set(current.get("enum"))
    if baseline_enum and not baseline_enum <= current_enum:
        changes.append(f"{path}.enum narrowed")
    _compare_numeric_bound(
        baseline, current, path=path, key="minimum", higher_breaks=True, out=changes
    )
    _compare_numeric_bound(
        baseline, current, path=path, key="minLength", higher_breaks=True, out=changes
    )
    _compare_numeric_bound(
        baseline, current, path=path, key="minItems", higher_breaks=True, out=changes
    )
    _compare_numeric_bound(
        baseline, current, path=path, key="maximum", higher_breaks=False, out=changes
    )
    _compare_numeric_bound(
        baseline, current, path=path, key="maxLength", higher_breaks=False, out=changes
    )
    _compare_numeric_bound(
        baseline, current, path=path, key="maxItems", higher_breaks=False, out=changes
    )

    baseline_required = _string_set(baseline.get("required"))
    current_required = _string_set(current.get("required"))
    for key in sorted(current_required - baseline_required):
        changes.append(f"{path}.required added {key}")

    baseline_properties = _object_or_empty(baseline.get("properties"))
    current_properties = _object_or_empty(current.get("properties"))
    for key, baseline_property in sorted(baseline_properties.items()):
        current_property = current_properties.get(key)
        if current_property is None:
            changes.append(f"{path}.properties.{key} removed")
            continue
        if isinstance(baseline_property, dict) and isinstance(current_property, dict):
            changes.extend(
                _breaking_changes(
                    baseline_property,
                    current_property,
                    path=f"{path}.properties.{key}",
                )
            )

    for key in ("items", "additionalProperties"):
        baseline_value = baseline.get(key)
        current_value = current.get(key)
        if baseline_value is True and current_value is False:
            changes.append(f"{path}.{key} became restrictive")
        if isinstance(baseline_value, dict):
            if not isinstance(current_value, dict):
                if current_value is False:
                    changes.append(f"{path}.{key} removed allowed values")
            else:
                changes.extend(
                    _breaking_changes(
                        baseline_value,
                        current_value,
                        path=f"{path}.{key}",
                    )
                )
    baseline_definitions = _object_or_empty(baseline.get("$defs"))
    current_definitions = _object_or_empty(current.get("$defs"))
    for key, baseline_definition in sorted(baseline_definitions.items()):
        current_definition = current_definitions.get(key)
        if current_definition is None:
            changes.append(f"{path}.$defs.{key} removed")
            continue
        if isinstance(baseline_definition, dict) and isinstance(current_definition, dict):
            changes.extend(
                _breaking_changes(
                    baseline_definition,
                    current_definition,
                    path=f"{path}.$defs.{key}",
                )
            )
    for key in ("oneOf", "anyOf"):
        baseline_options = _object_list(baseline.get(key))
        current_options = _object_list(current.get(key))
        for index, baseline_option in enumerate(baseline_options):
            if not any(
                _schema_accepts_baseline(option, baseline_option) for option in current_options
            ):
                changes.append(f"{path}.{key}[{index}] removed or narrowed")
    return changes


def _schema_accepts_baseline(current: dict[str, JsonValue], baseline: dict[str, JsonValue]) -> bool:
    return not _breaking_changes(baseline, current, path="option")


def _compare_numeric_bound(
    baseline: dict[str, JsonValue],
    current: dict[str, JsonValue],
    *,
    path: str,
    key: str,
    higher_breaks: bool,
    out: list[str],
) -> None:
    baseline_value = baseline.get(key)
    current_value = current.get(key)
    if not isinstance(baseline_value, int | float):
        if isinstance(current_value, int | float):
            out.append(f"{path}.{key} added")
        return
    if not isinstance(current_value, int | float):
        return
    if (higher_breaks and current_value > baseline_value) or (
        not higher_breaks and current_value < baseline_value
    ):
        out.append(f"{path}.{key} narrowed")


def _compatibility_baseline() -> JsonValue:
    return {
        "contract_version": EXTERNAL_CONTRACT_VERSION,
        "openapi_operations": list(_openapi_operations()),
        "schemas": {
            name: cast(JsonValue, schema) for name, schema in sorted(_schema_payloads().items())
        },
    }


def _openapi_operations() -> tuple[str, ...]:
    openapi = _json_object(_read_json(OPENAPI_PATH), "OpenAPI document")
    paths = _json_object(openapi["paths"], "OpenAPI paths")
    operations: list[str] = []
    for path, path_item_value in sorted(paths.items()):
        path_item = _json_object(path_item_value, f"OpenAPI path {path}")
        for method in sorted(path_item):
            if method in {"delete", "get", "head", "options", "patch", "post", "put"}:
                operations.append(f"{method.upper()} {path}")
    return tuple(operations)


def _schema_payloads() -> dict[str, Schema]:
    return {path.name: cast(Schema, _read_json(path)) for path in sorted(SCHEMA_DIR.glob("*.json"))}


def _schema_registry(schemas: dict[str, Schema]) -> SchemaRegistry:
    registry = EMPTY_REGISTRY
    for schema in schemas.values():
        schema_id = schema.get("$id")
        if type(schema_id) is not str:
            raise ExternalContractError("External contract schemas require string $id values.")
        registry = registry.with_resource(
            schema_id,
            Resource.from_contents(schema, default_specification=DRAFT202012),
        )
    return registry


def _decision_type_tokens() -> tuple[str, ...]:
    values: set[str] = set()
    for path in _source_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                value = _string_constant(node.value)
                if value is None:
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.endswith("DECISION_TYPE"):
                        values.add(value)
            if isinstance(node, ast.AnnAssign):
                value = _string_constant(node.value)
                if (
                    value is not None
                    and isinstance(node.target, ast.Name)
                    and node.target.id.endswith("DECISION_TYPE")
                ):
                    values.add(value)
    return tuple(sorted(values))


def _proposal_kind_tokens() -> tuple[str, ...]:
    values: set[str] = set()
    for path in _source_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                value = _string_constant(node.value)
                if value is None:
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.endswith(
                        ("_PROPOSAL_KIND", "_PROPOSAL_PAYLOAD_KIND")
                    ):
                        values.add(value)
            if isinstance(node, ast.ClassDef) and node.name == "ProposalKind":
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        value = _string_constant(item.value)
                        if value is not None:
                            values.add(value)
    return tuple(sorted(values))


def _source_paths() -> tuple[Path, ...]:
    return tuple(sorted(path for path in SRC_ROOT.rglob("*.py") if path.is_file()))


def _schema_refs(value: JsonValue) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "$ref" and type(nested) is str:
                refs.add(nested)
            else:
                refs.update(_schema_refs(nested))
    elif isinstance(value, list):
        for nested in value:
            refs.update(_schema_refs(nested))
    return refs


def _schema_file_names() -> tuple[str, ...]:
    return tuple(path.name for path in sorted(SCHEMA_DIR.glob("*.json")))


def _proposal_kind(payload: JsonValue) -> str:
    return _required_string(_json_object(payload, "proposal example"), "proposal_kind")


def _successful_response(response: ServerResponse, *, expected_status: int) -> dict[str, JsonValue]:
    if response.status_code != expected_status:
        raise ExternalContractError(
            f"Contract fixture server expected {expected_status}, got {response.status_code}."
        )
    return _json_object(response.payload, "server response")


def _read_json(path: Path) -> JsonValue:
    return validate_json_value(json.loads(path.read_text(encoding="utf-8")))


def _write_json(path: Path, payload: JsonValue) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(validate_json_value(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _json_object(value: JsonValue, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ExternalContractError(f"{field_name} must be a JSON object.")
    return value


def _json_list(value: JsonValue, field_name: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ExternalContractError(f"{field_name} must be a JSON list.")
    return value


def _required_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload[key]
    if type(value) is not str or not value:
        raise ExternalContractError(f"{key} must be a non-empty string.")
    return value


def _string_constant(node: ast.expr | None) -> str | None:
    if not isinstance(node, ast.Constant) or type(node.value) is not str:
        return None
    return node.value


def _type_tokens(value: JsonValue | None) -> set[str]:
    if type(value) is str:
        return {value}
    if isinstance(value, list):
        return {item for item in value if type(item) is str}
    return set()


def _string_set(value: JsonValue | None) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if type(item) is str}


def _json_scalar_set(value: JsonValue | None) -> set[str | int | float | bool | None]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if not isinstance(item, dict | list)}


def _object_or_empty(value: JsonValue | None) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    return {}


def _object_list(value: JsonValue | None) -> list[dict[str, JsonValue]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _major_version(value: str) -> int:
    major, _separator, _rest = value.partition(".")
    if not major.isdigit():
        raise ExternalContractError("Contract version must use semantic versioning.")
    return int(major)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
