from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SCHEMA_NAMES = frozenset(
    {
        "create-session.schema.json",
        "decision-family-coverage.schema.json",
        "decision-family-live.schema.json",
        "decision-request-view.schema.json",
        "error-envelope.schema.json",
        "event-delta.schema.json",
        "finite-submission.schema.json",
        "game-view.schema.json",
        "lifecycle-status.schema.json",
        "opportunity-window-example.schema.json",
        "parameterized-submission.schema.json",
        "proposal-payload.schema.json",
        "replay-metadata.schema.json",
        "rules-catalog.schema.json",
        "session-command-result.schema.json",
        "session-create.schema.json",
        "session-metadata.schema.json",
        "support-profile.schema.json",
    }
)
SMOKE_PROGRAM = r"""
import json
from importlib.resources import files
from pathlib import Path

import warhammer40k_core.adapters.external_contract as external_contract
from warhammer40k_core.adapters.external_contract import (
    CREATE_SESSION_SCHEMA_NAME,
    CREATE_SESSION_SCHEMA_VERSION,
    FINITE_SUBMISSION_SCHEMA_NAME,
    FINITE_SUBMISSION_SCHEMA_VERSION,
    PARAMETERIZED_SUBMISSION_SCHEMA_NAME,
    PARAMETERIZED_SUBMISSION_SCHEMA_VERSION,
    SESSION_CREATE_SCHEMA_NAME,
    SESSION_CREATE_SCHEMA_VERSION,
    validate_external_request_payload,
)
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.engine.event_log import validate_json_value

expected_schema_names = {
    "create-session.schema.json",
    "decision-family-coverage.schema.json",
    "decision-family-live.schema.json",
    "decision-request-view.schema.json",
    "error-envelope.schema.json",
    "event-delta.schema.json",
    "finite-submission.schema.json",
    "game-view.schema.json",
    "lifecycle-status.schema.json",
    "opportunity-window-example.schema.json",
    "parameterized-submission.schema.json",
    "proposal-payload.schema.json",
    "replay-metadata.schema.json",
    "rules-catalog.schema.json",
    "session-command-result.schema.json",
    "session-create.schema.json",
    "session-metadata.schema.json",
    "support-profile.schema.json",
}
module_path = Path(external_contract.__file__).resolve()
repository_candidate = module_path.parents[3] / "contracts" / "schemas"
if repository_candidate.is_dir():
    raise RuntimeError("Installed-wheel smoke unexpectedly found a repository schema copy.")

schema_directory = files("warhammer40k_core").joinpath("contracts", "schemas")
schema_names = {
    entry.name
    for entry in schema_directory.iterdir()
    if entry.is_file() and entry.name.endswith(".json")
}
if schema_names != expected_schema_names:
    raise RuntimeError("Installed wheel does not contain the complete canonical schema bundle.")

create_payload = validate_json_value(
    {
        "schema_version": CREATE_SESSION_SCHEMA_VERSION,
        "config": canonical_setup_prebattle_smoke_config(
            game_id="installed-wheel-contract-smoke"
        ).to_payload(),
    }
)
finite_payload = validate_json_value(
    {
        "schema_version": FINITE_SUBMISSION_SCHEMA_VERSION,
        "actor_id": "player-a",
        "option_id": "finite-option",
        "result_id": "installed-wheel-finite-result",
    }
)
parameterized_payload = validate_json_value(
    {
        "schema_version": PARAMETERIZED_SUBMISSION_SCHEMA_VERSION,
        "actor_id": "player-a",
        "payload": {
            "proposal_request_id": "installed-wheel-proposal-request",
            "proposal_kind": "normal_move",
            "unit_instance_id": "army-alpha:unit-1",
            "movement_phase_action": "normal_move",
            "witness": {"model_paths": []},
        },
        "result_id": "installed-wheel-parameterized-result",
    }
)
session_create_payload = validate_json_value(
    {
        "schema_version": SESSION_CREATE_SCHEMA_VERSION,
        "config": create_payload["config"],
        "participant_assignments": [
            {"participant_id": "player-a", "role": "player", "player_id": "player-a"},
            {"participant_id": "player-b", "role": "player", "player_id": "player-b"},
        ],
    }
)
for schema_name, payload, payload_name in (
    (CREATE_SESSION_SCHEMA_NAME, create_payload, "installed create session"),
    (FINITE_SUBMISSION_SCHEMA_NAME, finite_payload, "installed finite submission"),
    (
        PARAMETERIZED_SUBMISSION_SCHEMA_NAME,
        parameterized_payload,
        "installed parameterized submission",
    ),
    (SESSION_CREATE_SCHEMA_NAME, session_create_payload, "installed session create"),
):
    validate_external_request_payload(
        schema_name=schema_name,
        payload=payload,
        payload_name=payload_name,
    )

print(
    json.dumps(
        {
            "package_path": module_path.as_posix(),
            "schema_count": len(schema_names),
            "validated_request_families": [
                "create",
                "finite",
                "parameterized",
                "session_create",
            ],
        },
        sort_keys=True,
    )
)
"""


def main() -> int:
    with TemporaryDirectory(prefix="phase18d-installed-wheel-") as temporary_directory:
        temporary_root = Path(temporary_directory).resolve()
        wheel_directory = temporary_root / "wheel"
        environment_directory = temporary_root / "environment"
        outside_repository = temporary_root / "outside-repository"
        wheel_directory.mkdir()
        outside_repository.mkdir()

        _run(
            ("uv", "build", "--wheel", "--out-dir", str(wheel_directory)),
            cwd=ROOT,
        )
        wheels = tuple(wheel_directory.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("Installed contract smoke requires exactly one built wheel.")

        _run(
            ("uv", "venv", "--python", sys.executable, str(environment_directory)),
            cwd=outside_repository,
        )
        installed_python = _environment_python(environment_directory)
        _run(
            (
                "uv",
                "pip",
                "install",
                "--python",
                str(installed_python),
                str(wheels[0]),
            ),
            cwd=outside_repository,
        )
        environment = os.environ.copy()
        if "PYTHONPATH" in environment:
            del environment["PYTHONPATH"]
        completed = subprocess.run(
            (str(installed_python), "-I", "-c", SMOKE_PROGRAM),
            cwd=outside_repository,
            env=environment,
            check=True,
            capture_output=True,
            encoding="utf-8",
        )
        result = json.loads(completed.stdout)
        if result.get("schema_count") != len(EXPECTED_SCHEMA_NAMES):
            raise RuntimeError("Installed contract smoke returned an invalid schema count.")
        print(completed.stdout.strip())
    return 0


def _run(command: tuple[str, ...], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _environment_python(environment_directory: Path) -> Path:
    relative_path = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    executable = environment_directory / relative_path
    if not executable.is_file():
        raise RuntimeError("Installed contract smoke environment has no Python executable.")
    return executable


if __name__ == "__main__":
    raise SystemExit(main())
