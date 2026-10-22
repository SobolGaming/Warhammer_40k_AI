"""Exact tooling-only successor; all prior source and measurement anchors remain fixed."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

BASE = "fc1f186aeb0d143983e22382778177f4648438fd"
BASE_SOURCE = "36ab649ef5a6ab747587dc25d05336252db5a4eb148dc24619e6881c38efec42"
SELF = "tools/performance_preflight_successor.py"
ASSESSMENT = "docs/performance/change-assessment.json"
FREEZE_COMMIT: str | None = None
# Filled from exact reviewed implementation bytes before the immutable freeze.
_PIN_ROWS = (
    (
        "scripts/check_performance_policy.py",
        "211658e8b50b0bb1f443b5389d815a221e1e218c1d475f909b32fa2959cb4d75",
    ),
    (
        "tests/code_quality/test_performance_preflight.py",
        "1270d35ded44b9120f5cc0a53dad9ea3f938ca47a40902d61e6b5febca4c5f9d",
    ),
    (
        "tests/code_quality/test_qualification40_successor.py",
        "5a1f745da1d751f9c0be22ade0500831862381687c5de23d248e7269b64561d3",
    ),
    (
        "tools/cumulative_preservation.py",
        "b3e21ddadefb08e1a26c2a0f0d702252bd2ef23ebb2f2593b821cc000fc13e5a",
    ),
    (
        "tools/performance_policy.py",
        "b22bb94f8505558e82a8df3c3ea23c699f4c19e215b44465911f0313261aff41",
    ),
    (
        "tools/performance_preflight.py",
        "e69e8c25e8c922bf81ed3aec337e43e907de209eaf4f39d9180a59ac083d21be",
    ),
    (
        "tools/performance_qualification_successor.py",
        "f02faa899f7091553407a2d782ff0f16209f9db3fe23480112491bea1a794890",
    ),
    (
        "tools/thousand_sons_perils_preservation.py",
        "2e9ef0110809dde8b380e04a7b608095672c10ea39b8cfc9aff8318002320894",
    ),
)
PINS: dict[str, str] = dict(_PIN_ROWS)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root, timeout=60)


def _read(root: Path, name: str) -> bytes:
    from tests.d07_geometry_containment import read_owned_geometry_member

    if root.absolute() != root.resolve(strict=True):
        raise ValueError("Aliased preflight successor root.")
    return read_owned_geometry_member(root, name)


def preceding_control(root: Path, name: str, raw: bytes) -> bytes:
    """Exact byte projection; the complete successor freeze is admitted separately."""
    if name not in PINS and name != ASSESSMENT:
        return raw
    actual = _read(root, name)
    if name == ASSESSMENT:
        _assessment(root, _freeze(root))
    elif _sha(actual) != PINS[name]:
        raise ValueError(
            "Reviewed migration source/data changed: "
            "Qualification / Perils successor / Preflight source: " + name
        )
    old = _git(root, "show", BASE + ":" + name)
    if raw not in (actual, old):
        raise ValueError("Preflight control caller supplied unrelated bytes.")
    return old


def _freeze(root: Path) -> str:
    freeze = FREEZE_COMMIT
    if freeze is None or len(freeze) != 40 or set(freeze) - set("0123456789abcdef"):
        raise ValueError("Preflight successor awaits its exact source freeze.")
    _git(root, "merge-base", "--is-ancestor", BASE, freeze)
    _git(root, "merge-base", "--is-ancestor", freeze, "HEAD")
    names = _git(root, "diff", "--name-only", BASE, freeze).decode().splitlines()
    if set(names) != PINS.keys() | {SELF, ASSESSMENT} or len(names) != len(PINS) + 2:
        raise ValueError("Preflight successor finite membership changed.")
    frozen = _git(root, "show", freeze + ":" + SELF)
    marker = b"\nFREEZE_COMMIT: str | None = None"
    if frozen.count(marker) != 1 or _read(root, SELF) != frozen.replace(
        marker, f'\nFREEZE_COMMIT: str | None = "{freeze}"'.encode(), 1
    ):
        raise ValueError("Preflight successor activation changed.")
    for name, pin in PINS.items():
        if _sha(_read(root, name)) != pin or _sha(_git(root, "show", freeze + ":" + name)) != pin:
            raise ValueError(
                "Reviewed migration source/data changed: "
                "Qualification / Perils successor / Preflight source: " + name
            )
    return freeze


def _assessment(root: Path, freeze: str) -> bytes:
    from tools.performance_policy import owner_hashes

    assessment = json.loads(_git(root, "show", freeze + ":" + ASSESSMENT))
    current = _read(root, SELF)
    change = assessment["changes"][SELF]
    change["after_sha256"] = _sha(current)
    change["owners"]["@module"]["after"] = owner_hashes(SELF, current)["@module"]
    raw_assessment = _read(root, ASSESSMENT)
    if json.loads(raw_assessment) != assessment:
        raise ValueError("Preflight assessment changed outside exact anchor derivation.")
    return raw_assessment


def current_source(root: Path, previous: dict[str, str]) -> dict[str, str]:
    if _sha(json.dumps(previous, sort_keys=True, separators=(",", ":")).encode()) != BASE_SOURCE:
        raise ValueError("Preflight successor preceding complete source changed.")
    freeze = _freeze(root)
    return (
        previous
        | PINS
        | {SELF: _sha(_read(root, SELF)), ASSESSMENT: _sha(_assessment(root, freeze))}
    )


def measurement_inputs(root: Path, current: dict[str, str]) -> dict[str, str]:
    """Admit only exact tooling changes and the prior proven Perils test insertion.

    All runtime, measured drivers, shared fixture helpers, imports, dependencies,
    schemas and workload bytes must equal their preceding measured inventory.
    The existing qualification producing-input proof still runs on that inventory.
    """
    from tools import thousand_sons_perils_preservation as perils

    _freeze(root)
    controls = PINS.keys() | {SELF}
    if not controls <= current.keys():
        raise ValueError("Preflight actual input collector omitted current inputs.")
    actual = {name: _sha(_read(root, name)) for name in controls}
    projected = dict(current)
    prior_names = set(_git(root, "ls-tree", "-r", "--name-only", BASE).decode().splitlines())
    for name in PINS.keys() | {SELF}:
        if name not in current:
            continue
        if current[name] != actual[name]:
            raise ValueError("Preflight actual input collector omitted current control bytes.")
        if name in prior_names:
            projected[name] = _sha(_git(root, "show", BASE + ":" + name))
        else:
            del projected[name]
    # These five exact paths are already authenticated by the native Perils
    # admission. Its added test is not a measured driver or imported fixture.
    perils._freeze(root)
    for name in perils.CHANGED:
        raw = _git(root, "show", BASE + ":" + name)
        if projected.get(name) != _sha(raw):
            raise ValueError("Preflight Perils producing projection changed.")
        if name in {perils.SELF, perils.GUARD}:
            del projected[name]
        elif name == perils.TEST:
            projected[name] = _sha(perils.preceding_test(root, name, _read(root, name)))
        else:
            projected[name] = _sha(perils.preceding_control(root, name, _read(root, name)))
    return projected
