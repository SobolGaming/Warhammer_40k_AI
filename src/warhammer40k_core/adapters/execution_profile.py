"""Explicit Linux execution identities and opaque, profile-bound checkpoints.

This envelope does not change or migrate the inner LocalGameSession format.
The registered executor, rather than the client's operating system, owns all
numerical work throughout a session's lifetime.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import sys
import sysconfig
from pathlib import Path

from warhammer40k_core.adapters.numerical_policy import (
    NumericalPolicyConfiguration,
    NumericalPolicyError,
)
from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.base import CircularBase, OvalBase
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.shapely_backend import footprint_for_base

PROFILE_SCHEMA = "linux-execution-profile-v2-numerical-policy"
CHECKPOINT_SCHEMA = "profiled-session-checkpoint-v1"
_RUNTIME_DISTRIBUTIONS = (
    "orjson",
    "msgspec",
    "pydantic",
    "pydantic-core",
    "shapely",
    "numpy",
    "jsonschema",
    "referencing",
    "z3-solver",
    "attrs",
    "rpds-py",
    "jsonschema-specifications",
    "typing-extensions",
    "annotated-types",
    "typing-inspection",
)


class ExecutionProfileError(GameLifecycleError):
    """An explicit executor or its checkpoint binding is unavailable or drifted."""


def object_payload(value: JsonValue, *, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ExecutionProfileError(f"{label} must be a JSON object.")
    return value


def string_field(value: dict[str, JsonValue], key: str) -> str:
    field = value[key]
    if not isinstance(field, str) or not field:
        raise ExecutionProfileError(f"{key} must be a nonempty string.")
    return field


def content_hash(value: JsonValue) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_executor_profile(
    profile: JsonValue, *, expected: JsonValue, engine_build_id: str
) -> None:
    if profile != expected:
        raise ExecutionProfileError("The installed Linux execution profile has drifted.")
    value = object_payload(profile, label="Linux execution profile")
    if value.get("schema_version") != PROFILE_SCHEMA:
        raise ExecutionProfileError("Unsupported Linux execution profile schema.")
    if value.get("engine_build_id") != engine_build_id:
        raise ExecutionProfileError("Client and Linux authority require the same engine build.")
    numerical_policy_for_profile(profile)


def numerical_policy_for_profile(profile: JsonValue) -> NumericalPolicyConfiguration:
    """Require an explicit supported policy; old profiles require their old executor."""
    value = object_payload(profile, label="Linux execution profile")
    if value.get("schema_version") != PROFILE_SCHEMA:
        raise ExecutionProfileError("Unsupported Linux execution profile schema.")
    policy_id = value.get("numerical_policy_id")
    if not isinstance(policy_id, str):
        raise ExecutionProfileError("Linux execution profile requires a numerical policy.")
    try:
        return NumericalPolicyConfiguration(policy_id)
    except NumericalPolicyError as exc:
        raise ExecutionProfileError(str(exc)) from exc


def linux_execution_profile() -> dict[str, JsonValue]:
    """Identify this installed executor; never infer a profile from a save file.

    Source, native binaries and loaded system libraries are bound, in addition
    to version labels and numerical canaries. This identifies an installation;
    it does not certify that distinct Linux installations are interchangeable.
    Bytecode is disabled at both lookup and write boundaries by the launcher.
    """
    if (
        platform.system() != "Linux"
        or sys.pycache_prefix != "/dev/null"
        or not sys.dont_write_bytecode
    ):
        raise ExecutionProfileError(
            "The authority requires Linux Python -B -X pycache_prefix=/dev/null."
        )
    resources: dict[str, str] = {}
    stdlib = Path(sysconfig.get_path("stdlib"))
    for path in sorted(stdlib.rglob("*")):
        relative = path.relative_to(stdlib)
        if "site-packages" in relative.parts or "__pycache__" in relative.parts:
            continue
        if path.is_file() and path.suffix in {".py", ".so"}:
            resources[f"stdlib/{relative.as_posix()}"] = _file_hash(path)
    resources["python-executable"] = _file_hash(Path(sys.executable).resolve())
    versions: dict[str, JsonValue] = {}
    for name in _RUNTIME_DISTRIBUTIONS:
        distribution = importlib.metadata.distribution(name)
        versions[name] = distribution.version
        if distribution.files is None:
            raise ExecutionProfileError(f"Runtime distribution inventory unavailable: {name}.")
        for package_file in distribution.files:
            if package_file.suffix in {".py", ".so", ".json"} or package_file.name in {
                "METADATA",
                "WHEEL",
            }:
                path = Path(str(distribution.locate_file(package_file)))
                resources[f"distribution/{name}/{package_file.as_posix()}"] = _file_hash(path)
    # Imported extension modules and their numerical system dependencies must
    # already be mapped before this inventory is captured.
    numpy = importlib.import_module("numpy")
    z3 = importlib.import_module("z3")
    numpy.sqrt(2.0)
    z3.get_version_string()
    circle = footprint_for_base(CircularBase(100.0 / 25.4 / 2.0), Pose.at(18.0, 40.0))
    oval = footprint_for_base(OvalBase(90.0, 52.5), Pose.at(-100.0, -200.0, facing_degrees=137.0))
    for line in Path("/proc/self/maps").read_text(encoding="utf-8").splitlines():
        columns = line.split(maxsplit=5)
        if len(columns) == 6 and columns[5].startswith("/"):
            path = Path(columns[5])
            if ".so" in path.name:
                resources[f"loaded-library/{path.name}"] = _file_hash(path)
    canaries: dict[str, JsonValue] = {
        "circle_area": circle.area.hex(),
        "circle_bounds": [value.hex() for value in circle.bounds],
        "rotated_oval_area": oval.area.hex(),
        "rotated_oval_bounds": [value.hex() for value in oval.bounds],
        "circle_to_rotated_oval_distance": circle.distance(oval).hex(),
        "sin_137": math.sin(math.radians(137.0)).hex(),
        "cos_37_96875": math.cos(math.radians(37.96875)).hex(),
    }
    return {
        "schema_version": PROFILE_SCHEMA,
        "numerical_policy_id": NumericalPolicyConfiguration().numerical_policy_id,
        "engine_build_id": verified_engine_build_identity().build_id,
        "platform": platform.system(),
        "machine": platform.machine(),
        "kernel_release": platform.release(),
        "cpu": _cpu_identity(),
        "numeric_environment": {
            name: os.environ.get(name)
            for name in (
                "NPY_DISABLE_CPU_FEATURES",
                "OPENBLAS_CORETYPE",
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "MKL_CBWR",
                "MKL_NUM_THREADS",
                "PYTHONHASHSEED",
            )
        },
        "python": sys.version,
        "distributions": versions,
        "resources": dict(sorted(resources.items())),
        "numerical_canaries": canaries,
    }


def _cpu_identity() -> JsonValue:
    # Exclude dynamic clocks, utilization and per-core ordinals. A different
    # numerical CPU capability set requires explicit executor requalification.
    fields = {"vendor_id", "cpu family", "model", "model name", "stepping", "microcode", "flags"}
    values: dict[str, set[str]] = {name: set() for name in fields}
    for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition(":")
        if separator and name.strip() in values:
            values[name.strip()].add(value.strip())
    return validate_json_value({name: sorted(values[name]) for name in sorted(values)})


def checkpoint_envelope(
    *,
    payload_bytes: bytes,
    profile: JsonValue,
    provenance: JsonValue,
    payload_schema: str = "local-game-session-persistence-v2-private-rng",
) -> dict[str, JsonValue]:
    """Preserve exact original bytes with an explicit enrollment/producer receipt."""
    if not isinstance(provenance, dict) or not provenance:
        raise ExecutionProfileError("An explicit nonempty provenance receipt is required.")
    content: dict[str, JsonValue] = {
        "schema_version": CHECKPOINT_SCHEMA,
        "execution_profile": profile,
        "profile_hash": content_hash(profile),
        "payload_schema": payload_schema,
        "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
        "payload_base64": base64.b64encode(payload_bytes).decode("ascii"),
        "provenance": provenance,
    }
    return {**content, "content_hash": content_hash(content)}


def checkpoint_bytes(envelope: JsonValue, *, profile: JsonValue) -> bytes:
    value = object_payload(envelope, label="Profiled checkpoint")
    if (
        set(value)
        != {
            "schema_version",
            "execution_profile",
            "profile_hash",
            "payload_sha256",
            "payload_base64",
            "payload_schema",
            "provenance",
            "content_hash",
        }
        or value["schema_version"] != CHECKPOINT_SCHEMA
    ):
        raise ExecutionProfileError("Unsupported profiled checkpoint schema.")
    content = {key: field for key, field in value.items() if key != "content_hash"}
    if value["content_hash"] != content_hash(content):
        raise ExecutionProfileError("Profiled checkpoint content hash drift.")
    if value["execution_profile"] != profile or value["profile_hash"] != content_hash(profile):
        raise ExecutionProfileError("The checkpoint requires a different execution profile.")
    if not isinstance(value["provenance"], dict) or not value["provenance"]:
        raise ExecutionProfileError("Profiled checkpoint has no provenance receipt.")
    try:
        raw = base64.b64decode(string_field(value, "payload_base64"), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ExecutionProfileError("Invalid checkpoint byte encoding.") from exc
    if hashlib.sha256(raw).hexdigest() != value["payload_sha256"]:
        raise ExecutionProfileError("Inner checkpoint byte hash drift.")
    return raw


def decode_json(raw: bytes) -> JsonValue:
    try:
        return validate_json_value(json.loads(raw))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExecutionProfileError("Authority payload must be UTF-8 JSON.") from exc


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
