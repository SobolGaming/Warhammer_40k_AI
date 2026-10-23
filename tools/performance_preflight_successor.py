"""Exact preflight and static successor; historical measurement anchors remain fixed."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

BASE = "fc1f186aeb0d143983e22382778177f4648438fd"
BASE_SOURCE = "36ab649ef5a6ab747587dc25d05336252db5a4eb148dc24619e6881c38efec42"
SELF = "tools/performance_preflight_successor.py"
ASSESSMENT = "docs/performance/change-assessment.json"
INVENTORY = "data/source_audits/order135/current-inventory-category-migration.json"
FREEZE_COMMIT: str | None = "f765523d188b8526465804ff7eb0042791e54954"
# Filled from exact reviewed implementation bytes before the immutable freeze.
_PIN_ROWS = (
    (
        "data/source_audits/order135/current-inventory-category-migration.json",
        "c0460f930be48c49dcbef7568ea1af5e2319ca374d658b6abdb8eadd38869c16",
    ),
    (
        "docs/CORE_RULES_REMEDIATION_ROADMAP.md",
        "59d0624883ffa435a267416718d508a30994b175b7bf239ddce2ec235b07f7c5",
    ),
    (
        "docs/performance/ci-successor49.json",
        "ea9fd6be7ca6371b78461291d95c85ba2371838b82e4e2f3a7a391212f9d879c",
    ),
    (
        "docs/performance/policy-v3/operation-map.json",
        "5323c1736433605c84d150bb43371a85db5ee8d726b57fbe1ec1df600a1012a0",
    ),
    (
        "docs/performance/static-successor48.json",
        "b834787bc3f8bcf503ea3ae985d1a6f46e598a6350e8f1b5621e3d41d25f3c33",
    ),
    (
        "scripts/__init__.py",
        "8d5e4e6f7bebd9df2e7c317a68f93d634913012d661987474a65739976b9b4ec",
    ),
    (
        "scripts/check_performance_policy.py",
        "211658e8b50b0bb1f443b5389d815a221e1e218c1d475f909b32fa2959cb4d75",
    ),
    (
        "tests/__init__.py",
        "8d5e4e6f7bebd9df2e7c317a68f93d634913012d661987474a65739976b9b4ec",
    ),
    (
        "tests/code_quality/test_cumulative_preservation.py",
        "b27516e78bf1a911aa5f814b8f6bda1cc76ba404558715be843a47caa66b6629",
    ),
    (
        "tests/code_quality/test_d07_geometry_containment.py",
        "7de3292b5ac379ece05285fc4e94eab943af5dfc55f6961b5a0e42644384fdd4",
    ),
    (
        "tests/code_quality/test_order34_action_restrictions.py",
        "47d450c66f0b0c801c5963d71fc182bb0eced3354dda416228c60038209da1c4",
    ),
    (
        "tests/code_quality/test_order97_faction_relocation.py",
        "0ee571c76b471dd9940f2a716c0c1f71ebc8a766f90ce2ae94c8239d47feda22",
    ),
    (
        "tests/code_quality/test_performance_preflight.py",
        "d313ad37d9836bd55d0e40026aca88445727b462f0e1b367781ffd4222114e31",
    ),
    (
        "tests/code_quality/test_performance_static_successor.py",
        "cf46f4112a762e6c2fa87b67b982115867b40413bf53e9c45b63fda9fe3e2ba8",
    ),
    (
        "tests/code_quality/test_qualification40_successor.py",
        "dbc224be55ff45ba4d86eef3648ba641f4e6c350f84a58c0e5a6751229c550bc",
    ),
    (
        "tests/support/section08_native_mission.py",
        "c5cd5422243cc6a2b849b30c03743afc52a8535245b739ae00bde656c9e9feec",
    ),
    (
        "tools/core_rules_order97_inventory.py",
        "a2244c13bb62a966807801bd21929b60004d4f89260c3e1a7fde852d0721f0b5",
    ),
    (
        "tools/cumulative_preservation.py",
        "fd56f9037e9b5c1ae1466eed49195ee40be44ba32772a729c9ff724bc0c734e0",
    ),
    (
        "tools/generate_aeldari_datasheet_semantic_coverage.py",
        "1e49fd40cf7f9841054315e1db8eb4e6ba4c92c94db9080a9efab375b254b3bc",
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

STATIC_BASE = "b150e426c70d4705da100bc75f1d253483e021c7"
STATIC_RECORD = "docs/performance/static-successor48.json"
STATIC_TEST = "tests/code_quality/test_order34_action_restrictions.py"
STATIC_FIXTURE = "tests/support/section08_native_mission.py"
_STATIC_BEFORE_ROWS = (
    (
        "tests/code_quality/test_cumulative_preservation.py",
        "a761f02992373d610f0df01b3c2b419c4825b61f86b4222f73560542e8d379da",
    ),
    (
        "tests/code_quality/test_d07_geometry_containment.py",
        "241b0a96741494bb06ef77613a2cf4a1fcc4c60d12cb41bde1589efb491a91b0",
    ),
    (
        "tests/code_quality/test_order34_action_restrictions.py",
        "42b011550184e5377296d5a325381a30f3912728846e61f8a6fab86244430124",
    ),
    (
        "tests/code_quality/test_order97_faction_relocation.py",
        "39833a0fb545a8121c4aa9d1ce74bcedae3c8790ea0f7624c25ed543b4547e7f",
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
        "tests/support/section08_native_mission.py",
        "a4282eba8e4bfccb18ad17417e43ef9b9cd9063285777c155e13b0955be2ccc9",
    ),
    (
        "tools/core_rules_order97_inventory.py",
        "a9fcf75cffde412df9bd0aea2bfa99fcb2b9deb2c1a1e88cd870c00a459a39e6",
    ),
    (
        "tools/cumulative_preservation.py",
        "b3e21ddadefb08e1a26c2a0f0d702252bd2ef23ebb2f2593b821cc000fc13e5a",
    ),
)
STATIC_BEFORE: dict[str, str] = dict(_STATIC_BEFORE_ROWS)


CI_BASE = "d1d37f45c17e7ecc4d60b990b011d4c725ac4d1c"
CI_RECORD = "docs/performance/ci-successor49.json"
CI_NEW = "scripts/__init__.py"
CI_ROADMAP = "docs/CORE_RULES_REMEDIATION_ROADMAP.md"
_CI_BEFORE_ROWS = (
    (
        "tests/__init__.py",
        "01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b",
    ),
    (
        "tools/generate_aeldari_datasheet_semantic_coverage.py",
        "59c535dbeac16d8aad6d413558fb20269ebb020d1cf5ec0927ff372ca44a220d",
    ),
    (
        "docs/performance/policy-v3/operation-map.json",
        "f330487a339f4e3d58f4301afd6a6c21f64d9ed47e1f46742ebcbdf3e3b867b9",
    ),
    (
        "docs/CORE_RULES_REMEDIATION_ROADMAP.md",
        "df1b90a433e4f38aa0e2cd0974a9428f9d230c6bbce1d9079a0276ee16dc7442",
    ),
)
CI_BEFORE: dict[str, str] = dict(_CI_BEFORE_ROWS)


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


def assert_static_transition(name: str, before: bytes, current: bytes, row: dict[str, Any]) -> None:
    """Check one finite static edit against its independent immutable preimage."""
    from tools.cumulative_preservation import assert_recipe

    if (
        name not in STATIC_BEFORE
        or row.keys() != {"before_sha256", "after_sha256", "recipe"}
        or row["before_sha256"] != STATIC_BEFORE[name]
        or _sha(before) != STATIC_BEFORE[name]
        or row["after_sha256"] != _sha(current)
    ):
        raise ValueError("Static transition identity or bytes changed.")
    recipe: dict[str, Any] = row["recipe"]
    if (
        not isinstance(recipe, dict)
        or recipe.keys() != {"edits"}
        or not isinstance(recipe["edits"], list)
    ):
        raise ValueError("Static transition recipe is malformed.")
    for edit in cast(list[dict[str, Any]], recipe["edits"]):
        if not isinstance(edit, dict) or "kind" not in edit:
            raise ValueError("Static transition edit is malformed.")
        kind = edit.get("kind")
        keys = {"kind", "at", "before", "after"}
        if kind == "splice":
            keys |= {"start", "end"}
        if (
            kind not in {"replace", "splice"}
            or edit.keys() != keys
            or not isinstance(edit["at"], list)
            or not edit["at"]
            or any(type(part) not in {str, int} for part in edit["at"])
        ):
            raise ValueError("Static transition edit is malformed.")
        if kind == "splice" and (
            type(edit["start"]) is not int
            or type(edit["end"]) is not int
            or not 0 <= edit["start"] <= edit["end"]
            or not isinstance(edit["before"], list)
            or not isinstance(edit["after"], list)
        ):
            raise ValueError("Static transition splice is malformed.")
    assert_recipe(before, current, recipe)


def _static_transitions(root: Path, frozen_members: dict[str, bytes]) -> None:
    record: dict[str, Any] = json.loads(frozen_members[STATIC_RECORD])
    if (
        record.keys() != {"schema", "base", "changes"}
        or record["schema"] != "exact-static-successor-v1"
        or record["base"] != STATIC_BASE
        or record["changes"].keys() != STATIC_BEFORE.keys()
    ):
        raise ValueError("Static transition membership or base changed.")
    previous = _blobs(root, STATIC_BASE, list(STATIC_BEFORE))
    for name in STATIC_BEFORE:
        assert_static_transition(
            name, previous[name], frozen_members[name], record["changes"][name]
        )


def assert_ci_transition(
    name: str, before: bytes | None, current: bytes, row: dict[str, Any]
) -> None:
    """Admit only the frozen CI import/bootstrap edits and exact map additions."""
    expected = CI_BEFORE.get(name)
    if (
        (name not in CI_BEFORE and name != CI_NEW)
        or row.keys() != {"before_sha256", "after_sha256", "edits"}
        or row["before_sha256"] != expected
        or (before is None) != (name == CI_NEW)
        or (before is not None and _sha(before) != expected)
        or row["after_sha256"] != _sha(current)
        or not isinstance(row["edits"], list)
        or not row["edits"]
    ):
        raise ValueError("CI transition identity or bytes changed.")
    projected = b"" if before is None else before
    for edit in cast(list[dict[str, Any]], row["edits"]):
        if (
            not isinstance(edit, dict)
            or edit.keys() != {"before", "after"}
            or not isinstance(edit["before"], str)
            or not isinstance(edit["after"], str)
        ):
            raise ValueError("CI transition edit is malformed.")
        old, new = edit["before"].encode(), edit["after"].encode()
        if projected.count(old) != 1:
            raise ValueError("CI transition edit does not have one exact occurrence.")
        projected = projected.replace(old, new, 1)
    if projected != current:
        raise ValueError("CI transition changed outside the exact reviewed edits.")


def _ci_transitions(root: Path, frozen_members: dict[str, bytes]) -> None:
    record: dict[str, Any] = json.loads(frozen_members[CI_RECORD])
    if (
        record.keys() != {"schema", "base", "changes"}
        or record["schema"] != "exact-ci-successor-v1"
        or record["base"] != CI_BASE
        or record["changes"].keys() != CI_BEFORE.keys() | {CI_NEW}
    ):
        raise ValueError("CI transition membership or base changed.")
    if _git(root, "--literal-pathspecs", "ls-tree", "-r", "-z", CI_BASE, "--", CI_NEW):
        raise ValueError("CI bootstrap predecessor was not absent.")
    previous = _blobs(root, CI_BASE, list(CI_BEFORE))
    for name in record["changes"]:
        assert_ci_transition(
            name, previous.get(name), frozen_members[name], record["changes"][name]
        )


def static_predecessor(root: Path, name: str, raw: bytes) -> bytes:
    """Only the reviewed Order34 annotation may expose its prior historical stage."""
    if name != STATIC_TEST:
        return raw
    _freeze(root)
    live = _read(root, name)
    if raw not in (live, live.replace(b"\r\n", b"\n")):
        raise ValueError("Static predecessor caller supplied unrelated bytes.")
    before = _git(root, "show", STATIC_BASE + ":" + name)
    if _sha(before) != STATIC_BEFORE[name]:
        raise ValueError("Static predecessor immutable bytes changed.")
    return before.replace(b"\r\n", b"\n") if raw != live else before


def _freeze(root: Path) -> str:
    freeze = FREEZE_COMMIT
    if freeze is None or len(freeze) != 40 or set(freeze) - set("0123456789abcdef"):
        raise ValueError("Preflight successor awaits its exact source freeze.")
    _git(root, "merge-base", "--is-ancestor", BASE, freeze)
    _git(root, "merge-base", "--is-ancestor", freeze, "HEAD")
    _git(root, "merge-base", "--is-ancestor", STATIC_BASE, freeze)
    _git(root, "merge-base", "--is-ancestor", CI_BASE, freeze)
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
    _static_transitions(root, frozen_members)
    _ci_transitions(root, frozen_members)
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
    """Expose exact historical comparison inputs after current-source admission.

    The finite static recipes also admit the Command-end fixture's explicit
    export list; its functions, source-ID import and initializers remain exact.
    This is a changed recorded fixture input, not a byte-identical measurement.
    The CI successor also changes package bootstrap to prevent generated bytecode
    and imports the same generator function from its canonical owner. Its three
    exact module mappings add no detailed families or altered workload semantics.
    Current collectors and a fresh smoke receipt still bind the actual source.
    """
    from tools import thousand_sons_perils_preservation as perils

    _freeze(root)
    # The derived audit and proof records are outside runtime_inputs; their
    # bytes remain authenticated by _freeze and the complete live source scan.
    controls = (PINS.keys() - {INVENTORY, STATIC_RECORD, CI_RECORD, CI_ROADMAP}) | {SELF}
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
