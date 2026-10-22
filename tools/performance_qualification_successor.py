"""Finite fixture/performance successor; prior stages keep their original identities."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ACCEPTED = "ee3ecc1de30a799811f6cbdf04a05d56e02f6ae5"
SOURCE_SHA256 = "3d3c08cfd731fd56494716aa64570ba656300abf4ffaf105131a65693dfd6244"
NAMESPACE = "data/source_audits/qualification40_v1"
SELF = "tools/performance_qualification_successor.py"
MAP = "docs/performance/policy-v3/operation-map.json"
# Activated only after the genuine local implementation/measurement freeze.
FREEZE_COMMIT: str | None = None


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _digest(value: object) -> str:
    return _sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def _git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root, timeout=60)


def _read(root: Path, name: str) -> bytes:
    from tests.d07_geometry_containment import read_owned_geometry_member

    if root.is_symlink() or root.is_junction() or root.absolute() != root.resolve(strict=True):
        raise ValueError("Aliased qualification successor root.")
    return read_owned_geometry_member(root, name)


def enabled(root: Path) -> bool:
    return (root / NAMESPACE).exists()


def _freeze(root: Path) -> str:
    if FREEZE_COMMIT is None:
        raise ValueError("Qualification successor awaits its exact implementation freeze.")
    if len(FREEZE_COMMIT) != 40 or any(c not in "0123456789abcdef" for c in FREEZE_COMMIT):
        raise ValueError("Invalid qualification successor freeze.")
    _git(root, "merge-base", "--is-ancestor", ACCEPTED, FREEZE_COMMIT)
    _git(root, "merge-base", "--is-ancestor", FREEZE_COMMIT, "HEAD")
    frozen = _git(root, "show", FREEZE_COMMIT + ":" + SELF)
    marker = b"\nFREEZE_COMMIT: str | None = None"
    activated = f'\nFREEZE_COMMIT: str | None = "{FREEZE_COMMIT}"'.encode()
    if frozen.count(marker) != 1 or _read(root, SELF) != frozen.replace(marker, activated, 1):
        raise ValueError("Qualification successor control bytes changed.")
    return FREEZE_COMMIT


def _member(root: Path, name: str, freeze: str) -> bytes:
    raw = _read(root, name)
    if raw != _git(root, "show", freeze + ":" + name):
        raise ValueError("Qualification reviewed evidence/control bytes changed: " + name)
    return raw


def expected_source(root: Path, previous: dict[str, str]) -> dict[str, str]:
    freeze = _freeze(root)
    accepted = json.loads(_member(root, NAMESPACE + "/accepted-source.json", freeze))
    if _digest(accepted) != SOURCE_SHA256:
        raise ValueError("Qualification accepted predecessor source changed.")
    names = _git(root, "diff", "--name-only", ACCEPTED, freeze).decode().splitlines()
    declared = json.loads(_member(root, NAMESPACE + "/changed-members.json", freeze))
    if sorted(names) != declared or len(set(declared)) != len(declared):
        raise ValueError("Qualification finite changed membership changed.")
    for name, pin in previous.items():
        if name not in declared and accepted.get(name) != pin:
            raise ValueError("Qualification prior-source projection changed: " + name)
    result = dict(accepted)
    for name in names:
        raw = _git(root, "show", freeze + ":" + name)
        if name == SELF:
            raw = raw.replace(
                b"\nFREEZE_COMMIT: str | None = None",
                f'\nFREEZE_COMMIT: str | None = "{freeze}"'.encode(),
                1,
            )
        result[name] = _sha(raw)
    assessment = "docs/performance/change-assessment.json"
    frozen_assessment = json.loads(_git(root, "show", freeze + ":" + assessment))
    actual_control = _read(root, SELF)
    from tools.performance_policy import owner_hashes

    change = frozen_assessment["changes"][SELF]
    change["after_sha256"] = _sha(actual_control)
    change["owners"]["@module"]["after"] = owner_hashes(SELF, actual_control)["@module"]
    current_assessment = _read(root, assessment)
    if json.loads(current_assessment) != frozen_assessment:
        raise ValueError("Qualification assessment changed outside exact anchor derivation.")
    result[assessment] = _sha(current_assessment)
    return result


def control_projection(root: Path) -> dict[str, bytes]:
    """Authenticate the new controls before exposing the preceding exact stage."""
    from tools.cumulative_preservation import assert_recipe

    freeze = _freeze(root)
    rows = json.loads(_member(root, NAMESPACE + "/control-transitions.json", freeze))
    projected = {}
    for row in rows:
        name = row["path"]
        old = _git(root, "show", ACCEPTED + ":" + name)
        new = _member(root, name, freeze)
        if _sha(old) != row["before_sha256"] or _sha(new) != row["after_sha256"]:
            raise ValueError("Qualification exact control transition changed: " + name)
        assert_recipe(old, new, row["recipe"])
        projected[name] = old
    return projected


def preceding_control(root: Path, name: str, current: bytes) -> bytes:
    projection = control_projection(root)
    return projection.get(name, current)


def prior_operation_map_bytes(root: Path) -> bytes:
    freeze = _freeze(root)
    old_raw = _git(root, "show", ACCEPTED + ":" + MAP)
    old = json.loads(old_raw)
    new = json.loads(_member(root, MAP, freeze))
    metadata = {k: v for k, v in new.items() if k != "operations"}
    old_metadata = {k: v for k, v in old.items() if k != "operations"}
    expected_capability = {
        "schema": "tool-input-roles-v3",
        "role_specification": NAMESPACE + "/tool-input-roles-v3.json",
    }
    if (
        metadata["families"]["external_contract_source_reuse"]["input_binding"]
        != expected_capability
    ):
        raise ValueError("Qualification current source-token capability changed.")
    metadata["families"]["external_contract_source_reuse"]["input_binding"] = old_metadata[
        "families"
    ]["external_contract_source_reuse"]["input_binding"]
    if metadata != old_metadata:
        raise ValueError("Qualification historical families/budgets changed.")
    if any(new["operations"].get(k) != v for k, v in old["operations"].items()):
        raise ValueError("Qualification prior operation or mandatory obligation changed.")
    additions = json.loads(_member(root, NAMESPACE + "/added-operations.json", freeze))
    if new["operations"].keys() - old["operations"].keys() != additions.keys():
        raise ValueError("Qualification operation addition membership changed.")
    for name, operation in additions.items():
        if new["operations"][name] != operation or not operation["mandatory"]:
            raise ValueError("Qualification exact mandatory owner mapping changed.")
        if len(operation["paths"]) != 1 or any(
            any(c in value for c in "*?[") for value in operation["paths"] + operation["owners"]
        ):
            raise ValueError("Qualification owner mapping must remain literal.")
    return old_raw


def accepted_operation_map(root: Path) -> dict[str, Any]:
    """Original 52-operation assertions, after authenticating the full extension."""
    value: dict[str, Any] = json.loads(prior_operation_map_bytes(root))
    return value


def producing_inputs(root: Path, current: dict[str, str]) -> dict[str, str]:
    """Only the declared post-measurement anchor literal can differ from producing code."""
    freeze = _freeze(root)
    frozen = _git(root, "show", freeze + ":" + SELF)
    if current.get(SELF) != _sha(_read(root, SELF)):
        raise ValueError("Qualification actual input collector omitted its successor control.")
    return current | {SELF: _sha(frozen)}
