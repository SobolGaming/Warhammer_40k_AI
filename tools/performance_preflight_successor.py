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
INVENTORY = "data/source_audits/order135/current-inventory-category-migration.json"
FREEZE_COMMIT: str | None = None
# Filled from exact reviewed implementation bytes before the immutable freeze.
_PIN_ROWS = (
    (
        "data/source_audits/order135/current-inventory-category-migration.json",
        "c0460f930be48c49dcbef7568ea1af5e2319ca374d658b6abdb8eadd38869c16",
    ),
    (
        "scripts/check_performance_policy.py",
        "211658e8b50b0bb1f443b5389d815a221e1e218c1d475f909b32fa2959cb4d75",
    ),
    (
        "tests/code_quality/test_d07_geometry_containment.py",
        "241b0a96741494bb06ef77613a2cf4a1fcc4c60d12cb41bde1589efb491a91b0",
    ),
    (
        "tests/code_quality/test_performance_preflight.py",
        "5618fbac9cfbefae31c8ddeda8a6d5646026a01d48debc4c89379a6140e34e9f",
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
        "fb1bf3b9b983df3301edd047f5855efd1352507934f37bd88005e4b4eafe5a2e",
    ),
    (
        "tools/performance_preflight.py",
        "68231d01c2be7c1a1c1951dd0a178acaf97738ddfc937e5aac88a921fd7048a8",
    ),
    (
        "tools/performance_qualification_successor.py",
        "8306fec5f45dbddee62d899ff500a2d9d94799ad8ca2e6f09a23487b4c8f161c",
    ),
    (
        "tools/thousand_sons_perils_preservation.py",
        "2e9ef0110809dde8b380e04a7b608095672c10ea39b8cfc9aff8318002320894",
    ),
)
PINS: dict[str, str] = dict(_PIN_ROWS)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git(root: Path, *args: str, payload: bytes | None = None) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root, input=payload, timeout=60)


def _blobs(root: Path, revision: str, names: list[str]) -> dict[str, bytes]:
    """Read exact immutable members afresh; never cache Git or filesystem results."""
    if len(revision) != 40 or set(revision) - set("0123456789abcdef"):
        raise ValueError("Preflight Git revision must be an exact SHA1 selector.")
    if not names or len(set(names)) != len(names):
        raise ValueError("Preflight Git selection must contain unique members.")
    for name in names:
        if any(part in {"", ".", ".."} for part in name.split("/")) or any(
            character in name for character in "\\\x00\r\n"
        ):
            raise ValueError("Preflight Git member must be a canonical literal path.")
    tree = _git(root, "--literal-pathspecs", "ls-tree", "-r", "-z", revision, "--", *names)
    if not tree.endswith(b"\0"):
        raise ValueError("Preflight Git tree membership is incomplete.")
    objects: dict[str, str] = {}
    for row in tree[:-1].split(b"\0"):
        metadata, separator, encoded_name = row.partition(b"\t")
        fields = metadata.split(b" ")
        if not separator or len(fields) != 3:
            raise ValueError("Preflight Git tree row is malformed.")
        mode, kind, encoded_oid = fields
        name, oid = encoded_name.decode(), encoded_oid.decode("ascii")
        if (
            mode not in {b"100644", b"100755"}
            or kind != b"blob"
            or len(oid) != 40
            or set(oid) - set("0123456789abcdef")
            or name not in names
            or name in objects
        ):
            raise ValueError("Preflight Git member identity or type changed.")
        objects[name] = oid
    if objects.keys() != set(names):
        raise ValueError("Preflight Git tree membership is incomplete.")
    raw = _git(
        root,
        "cat-file",
        "--batch",
        payload="".join(objects[name] + "\n" for name in names).encode(),
    )
    result: dict[str, bytes] = {}
    offset = 0
    for name in names:
        boundary = raw.find(b"\n", offset)
        if boundary == -1:
            raise ValueError("Preflight Git blob header is incomplete.")
        fields = raw[offset:boundary].split(b" ")
        if len(fields) != 3:
            raise ValueError("Preflight Git blob header is malformed.")
        encoded_oid, kind, size = fields
        if encoded_oid != objects[name].encode() or kind != b"blob":
            raise ValueError("Preflight Git blob identity or type changed.")
        if not size.isdigit() or (len(size) > 1 and size.startswith(b"0")):
            raise ValueError("Preflight Git blob size is not canonical.")
        start = boundary + 1
        end = start + int(size)
        if end >= len(raw) or raw[end : end + 1] != b"\n":
            raise ValueError("Preflight Git blob payload is incomplete.")
        content = raw[start:end]
        object_hash = hashlib.sha1(b"blob " + size + b"\0", usedforsecurity=False)
        object_hash.update(content)
        if object_hash.hexdigest() != objects[name]:
            raise ValueError("Preflight Git blob bytes differ from the selected object.")
        result[name] = content
        offset = end + 1
    if offset != len(raw):
        raise ValueError("Preflight Git blob payload has trailing data.")
    return result


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
    frozen_members = _blobs(root, freeze, [SELF, *PINS])
    frozen = frozen_members[SELF]
    marker = b"\nFREEZE_COMMIT: str | None = None"
    if frozen.count(marker) != 1 or _read(root, SELF) != frozen.replace(
        marker, f'\nFREEZE_COMMIT: str | None = "{freeze}"'.encode(), 1
    ):
        raise ValueError("Preflight successor activation changed.")
    for name, pin in PINS.items():
        if _sha(_read(root, name)) != pin or _sha(frozen_members[name]) != pin:
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
    # This exact derived audit is outside runtime_inputs; its bytes and freeze
    # remain authenticated by _freeze and the complete live source scan.
    controls = (PINS.keys() - {INVENTORY}) | {SELF}
    if not controls <= current.keys():
        raise ValueError("Preflight actual input collector omitted current inputs.")
    actual = {name: _sha(_read(root, name)) for name in controls}
    projected = dict(current)
    prior_names = set(_git(root, "ls-tree", "-r", "--name-only", BASE).decode().splitlines())
    for name in controls:
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
