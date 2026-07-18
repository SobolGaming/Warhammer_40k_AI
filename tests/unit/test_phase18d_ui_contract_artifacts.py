from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Protocol, cast

from jsonschema import Draft202012Validator
from referencing import Resource
from referencing.jsonschema import (
    DRAFT202012,
    EMPTY_REGISTRY,
    Schema,
    SchemaRegistry,
    SchemaResource,
)
from scripts.export_ui_contract_fixtures import (
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

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.projection import project_rules_catalog_view
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.detachment import StratagemDefinition
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle

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
    Path("contracts/schemas/decision-family-coverage.schema.json"),
    Path("contracts/schemas/decision-family-live.schema.json"),
    Path("contracts/schemas/decision-request-view.schema.json"),
    Path("contracts/schemas/event-delta.schema.json"),
    Path("contracts/schemas/game-view.schema.json"),
    Path("contracts/schemas/rules-catalog.schema.json"),
)
FIXTURE_FILES = (
    "hidden_secondary_redaction_view.json",
    "initial_setup_view_player1.json",
    "initial_setup_view_player2.json",
    "pending_movement_request.json",
    "post_deployment_view.json",
    "rules_catalog_view.json",
    "visible_modifier_datacard_view.json",
)
GAME_VIEW_FIXTURE_FILES = (
    "hidden_secondary_redaction_view.json",
    "initial_setup_view_player1.json",
    "initial_setup_view_player2.json",
    "post_deployment_view.json",
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


class _PayloadValidator(Protocol):
    def validate(self, instance: object) -> None: ...


def test_ui_contract_artifacts_are_json_safe_and_scrubbed() -> None:
    paths = (
        *SCHEMA_FILES,
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
    _schema_validator("event-delta.schema.json", registry=registry).validate(
        session.events_since(EventStreamCursor(0), viewer_player_id=PLAYER_A)
    )


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

    assert initial_pending["request_id"] == "decision-request-000001"
    assert initial_pending["decision_type"] == "hidden_decision"
    assert initial_pending["payload"] == {"hidden": True, "secret": True}
    assert initial_pending["options"] == []

    hidden_redaction = _fixture("hidden_secondary_redaction_view.json")
    choices = _json_list(hidden_redaction["public_secondary_mission_choices"])
    pending = _json_object(hidden_redaction["pending_decision"])
    option_ids = {
        _json_string(_json_object(option)["option_id"]) for option in _json_list(pending["options"])
    }

    assert choices == [{"hidden": True, "player_id": PLAYER_A, "selected": True}]
    assert pending["actor_id"] == PLAYER_B
    assert pending["request_id"] == "decision-request-000002"
    assert {"fixed:assassination:bring_it_down", "tactical"}.issubset(option_ids)


def test_pending_decision_and_modifier_datacard_fixtures_are_ui_ready() -> None:
    pending = _fixture("pending_movement_request.json")
    options = _json_list(pending["options"])

    assert pending["request_id"] == "decision-request-000007"
    assert pending["decision_type"] == "select_movement_unit"
    assert all(_json_string(_json_object(option)["option_id"]) for option in options)
    assert {_json_string(_json_object(option)["option_id"]) for option in options} == {UNIT_ALPHA}

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


def test_proposal_examples_cover_engine_facing_payload_families() -> None:
    deployment = _proposal_example("deployment_placement.json")
    movement = _proposal_example("movement_path_witness.json")
    charge = _proposal_example("charge_move.json")
    shooting = _proposal_example("shooting_target_selection.json")
    melee = _proposal_example("melee_declaration.json")
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
        contract.decision_type: contract.submission_kind.value
        for contract in GameLifecycle().decision_dispatch_contracts
    }
    live_paths = {
        path.relative_to(REPO_ROOT / Path("contracts")).as_posix(): path
        for path in sorted((REPO_ROOT / DECISION_EXAMPLE_DIR / "families").glob("*.json"))
    }

    assert coverage["registered_decision_type_count"] == len(registered)
    assert coverage["known_external_token_count"] == len(registered) + 2
    assert coverage["live_scenario_count"] == len(live_paths)
    assert set(registered).issubset(rows_by_type)
    for decision_type, submission_kind in registered.items():
        row = rows_by_type[decision_type]
        assert row["registry_scope"] == "registered"
        assert row["submission_kind"] == submission_kind

    for row in rows:
        status = row["coverage_status"]
        example_path = row["example_path"]
        if status == "live_scenario":
            assert type(example_path) is str
            example = _read_json(live_paths[example_path])
            assert example["decision_type"] == row["decision_type"]
            assert example["is_parameterized"] is (row["submission_kind"] == "parameterized")
            assert '"contract_fixture"' not in json.dumps(example, sort_keys=True)
        else:
            assert example_path is None


def test_contract_manifest_hashes_baseline_with_canonical_line_endings() -> None:
    manifest = _read_json(REPO_ROOT / Path("contracts/manifest.json"))
    hashes = _json_object(manifest["file_sha256"])
    baseline_path = REPO_ROOT / Path("contracts/compatibility/1.0.0-shape.json")
    canonical_hash = hashlib.sha256(
        baseline_path.read_text(encoding="utf-8").encode("utf-8")
    ).hexdigest()

    assert hashes["compatibility/1.0.0-shape.json"] == canonical_hash


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
