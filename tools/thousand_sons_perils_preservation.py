"""Finite native-perils test successor; retain all preceding source and assertion pins."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

BASE = "9167053e3659e1efa95652aaef1fcc847d3e902d"
BASE_SOURCE = "78ec04dd674e95dc99a53945a4be8681359bc98622e744a6a052e02a347086be"
SELF = "tools/thousand_sons_perils_preservation.py"
STAGE = "tools/performance_qualification_successor.py"
CUMULATIVE = "tools/cumulative_preservation.py"
TEST = "tests/unit/test_phase17g_thousand_sons_army_rule.py"
GUARD = "tests/code_quality/test_thousand_sons_perils_preservation.py"
CHANGED = frozenset({SELF, STAGE, CUMULATIVE, TEST, GUARD})
BEFORE = "164b74babdb28ec0b67c821951c32821402e7caf9181e55669fcbccde44d9373"
AFTER = "75105d6dc3eba760dce048c4a158b574bec2e9dd414ecc610349109d5d60914b"
BLOCK = "99277c8bc089d9f4ea9e2c2c54e8f3e9560e8ec84c740dee5625a9b72e3d2f32"
OFFSET, LENGTH = 7812, 1510
# Activation changes only this literal after the genuine local five-path freeze.
FREEZE_COMMIT: str | None = "c48ed1a67780f22772a229788117ad5ed89d84c6"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(root: Path, name: str) -> bytes:
    from tests.d07_geometry_containment import read_owned_geometry_member

    if root.absolute() != root.resolve(strict=True):
        raise ValueError("Aliased perils successor root.")
    from tools.performance_preflight_successor import preceding_control as preflight_control

    return preflight_control(root, name, read_owned_geometry_member(root, name))


def _git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root, timeout=60)


def _history(root: Path, *args: str) -> bytes:
    from tools.performance_history_snapshot import historical

    return historical(root, "plain60", args, lambda: _git(root, *args))


def _freeze(root: Path) -> str:
    freeze = FREEZE_COMMIT
    if freeze is None or len(freeze) != 40 or set(freeze) - set("0123456789abcdef"):
        raise ValueError("Perils successor awaits its exact source freeze.")
    _history(root, "merge-base", "--is-ancestor", BASE, freeze)
    _git(root, "merge-base", "--is-ancestor", freeze, "HEAD")
    names = _history(root, "diff", "--name-only", BASE, freeze).decode().splitlines()
    if set(names) != CHANGED or len(names) != len(CHANGED):
        raise ValueError("Perils successor finite changed membership drift.")
    for name in CHANGED:
        expected = _history(root, "show", freeze + ":" + name)
        if name == SELF:
            marker = b"\nFREEZE_COMMIT: str | None = None"
            if expected.count(marker) != 1:
                raise ValueError("Perils successor freeze must be unactivated.")
            expected = expected.replace(
                marker, f'\nFREEZE_COMMIT: str | None = "{freeze}"'.encode(), 1
            )
        if _read(root, name) != expected:
            raise ValueError("Perils successor frozen source changed: " + name)
    return freeze


def preceding_control(root: Path, name: str, raw: bytes) -> bytes:
    from tools.performance_preflight_successor import preceding_control as preflight_control

    raw = preflight_control(root, name, raw)
    if name not in {STAGE, CUMULATIVE}:
        return raw
    _freeze(root)
    replacements = (
        (
            (
                b"    from tools.thousand_sons_perils_preservation import preceding_control\n\n"
                b"    return preceding_control(root, name, "
                b"read_owned_geometry_member(root, name))\n",
                b"    return read_owned_geometry_member(root, name)\n",
            ),
            (
                b"    from tools.thousand_sons_perils_preservation import current_source\n\n"
                b"    return current_source(root, result)\n",
                b"    return result\n",
            ),
        )
        if name == STAGE
        else (
            (b"    from tools.thousand_sons_perils_preservation import preceding_test\n\n", b""),
            (b"        live = preceding_test(root, path, live)\n", b""),
        )
    )
    for added, original in replacements:
        if raw.count(added) != 1:
            raise ValueError("Perils successor exact control insertion drift.")
        raw = raw.replace(added, original, 1)
    if raw != _history(root, "show", BASE + ":" + name):
        raise ValueError("Perils successor changed a preceding control owner.")
    return raw


def preceding_test(root: Path, name: str, raw: bytes) -> bytes:
    if name != TEST:
        return raw
    _freeze(root)
    # Historical migration consumers normalize CRLF, but the live raw pin stays exact.
    live = _read(root, TEST)
    if _sha(live) != AFTER or _sha(live[OFFSET : OFFSET + LENGTH]) != BLOCK:
        raise ValueError("Perils successor exact native test/block drift.")
    if raw not in (live, live.replace(b"\r\n", b"\n")):
        raise ValueError("Perils successor caller omitted the actual test bytes.")
    original = live[:OFFSET] + live[OFFSET + LENGTH :]
    if _sha(original) != BEFORE or original != _history(root, "show", BASE + ":" + TEST):
        raise ValueError("Perils successor original assertion/branch/identity drift.")
    return original.replace(b"\r\n", b"\n") if raw != live else original


def current_source(root: Path, previous: dict[str, str]) -> dict[str, str]:
    if _sha(json.dumps(previous, sort_keys=True, separators=(",", ":")).encode()) != BASE_SOURCE:
        raise ValueError("Perils successor preceding complete source changed.")
    _freeze(root)
    for name in (STAGE, CUMULATIVE):
        preceding_control(root, name, _read(root, name))
    preceding_test(root, TEST, _read(root, TEST))
    from tools.performance_preflight_successor import current_source as preflight_source

    return preflight_source(root, previous | {name: _sha(_read(root, name)) for name in CHANGED})
