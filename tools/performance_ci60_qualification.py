"""Finite CI60 qualification; historical engine bytes never become current inputs."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

from tools.performance_preflight import AdmissionOperands

BASE = "d7b7650fa1c76ee5830a9ffc78522eba3a6a3209"
PR_BASE = "5f509724da25a2f6ded0c2739a8e7c84bdf59c91"
SELF = "tools/performance_ci60_qualification.py"
NAMESPACE = "data/source_audits/ci60_qualification_v1"
ASSESSMENT = "docs/performance/change-assessment.json"
MAP = "docs/performance/policy-v3/operation-map.json"
FREEZE: str | None = "1cbbebf5e1a6a72d6e7a5c456ce24ff6770bd2b1"
SUPERSEDED_REPORTS: dict[str, str] = {
    "docs/performance/current/ci61-external_contract_source_reuse.json": (
        "a0fcf49e675f1d0ce978ea67ee93e08d44d2bcf475a45b904d28a6871a13fab2"
    ),
    "docs/performance/current/ci60-external_contract_source_reuse.json": (
        "71ed8f56225c81b161673685fa3010215601c6ad72bfa8b4552f7389d88a4c5b"
    ),
    "docs/performance/current/qualification40-dice.json": (
        "84ba455e20996cbd1fdeb246fc5410ab183d61da2ca6e4d760879168d2ddcd2e"
    ),
    "docs/performance/current/qualification40-dice_sustained.json": (
        "76fafa45cf162e140d07134e28e085c56d3b08dcd2947a3e32310bade0b89e5b"
    ),
    "docs/performance/current/qualification40-external_contract_source_reuse.json": (
        "fc87e9a27ca8ae10602db2524d3f8be1c1e3bf429b82bcae018ed9c860c3ed2c"
    ),
    "docs/performance/current/qualification40-fight.json": (
        "27fc3cba9c0da9b312eeb6cf980734f78f9b57f8bd3609d77a3405c511f8b86d"
    ),
    "docs/performance/current/qualification40-movement.json": (
        "bf5a007814b41cf78d1731677a86330eb3538c50c2ee1a95286d045a00b21d42"
    ),
    "docs/performance/current/qualification40-reconstruction.json": (
        "a3a5f2831eb81a2b9c016f5a2debb36157a4e9836eabe253afa8fa786159a7bc"
    ),
    "docs/performance/current/qualification40-setup.json": (
        "c845ab6764fef7f5ef1b91888fa4785cafa38383394d3433294da8632d942d8b"
    ),
    "docs/performance/current/qualification40-shock_reconstruction.json": (
        "18ce976b2063ab3f423574ccb460e0ad4f747e1842987178c78cd0260ee552d8"
    ),
    "docs/performance/current/qualification40-strength.json": (
        "89d57824df2b71b8459012b87f6f58fa5ec750e851fbfd071254da21e2143d70"
    ),
    "docs/performance/current/qualification40-visibility.json": (
        "b22afc0433f2ed9e3ab7078f0cbece7f6c637e1d4cab2139969bd54cab007aa5"
    ),
}
RETAINED = frozenset({"roster", "objective_control"})
CONTROLS = frozenset(
    {
        "ci/quality_shards/all.txt",
        "ci/quality_shards/shard-1.txt",
        "tools/core_rules_order97_inventory.py",
        "tests/category_migration_preservation.py",
        "tests/code_quality/test_category_migration_preservation.py",
        "tests/code_quality/test_cumulative_preservation.py",
        "tests/code_quality/test_performance_preflight.py",
        "tests/code_quality/test_performance_static_successor.py",
        "tools/quality_runtime_successor.py",
        "tools/cumulative_preservation.py",
        "tools/performance_policy.py",
        "tools/performance_history_snapshot.py",
        "scripts/check_performance_policy.py",
        "tests/code_quality/test_qualification40_successor.py",
        "tests/code_quality/test_qualification40_measurements.py",
        "tests/code_quality/test_quality_runtime.py",
        "tests/code_quality/test_performance_policy.py",
        "docs/CORE_RULES_REMEDIATION_ROADMAP.md",
        MAP,
        ASSESSMENT,
    }
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: object) -> str:
    return digest(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def owned(root: Path, name: str) -> bytes:
    from tests.d07_geometry_containment import read_owned_geometry_member

    return read_owned_geometry_member(root, name)


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root, timeout=60)


def history(root: Path, *args: str) -> bytes:
    from tools.performance_history_snapshot import historical

    return historical(root, "plain60", args, lambda: git(root, *args))


DERIVATION_BASE = "eda94d97a85eea11cea87451c39198d26767e64f"
DERIVATION_NAMESPACE = "data/source_audits/ci61_provenance_v1"
DERIVATION_FREEZE: str | None = "9e6d2cabbdbef9c7320a1c1f9a0fe0fc17ef61ab"
DERIVATION_TEST = "tests/code_quality/test_performance_provenance.py"
DERIVATION_CONTROLS = frozenset(
    {
        SELF,
        "tools/performance_preflight.py",
        "tools/performance_history_snapshot.py",
        "ci/quality_shards/all.txt",
        "ci/quality_shards/shard-1.txt",
        "ci/quality_shards/shard-1-modules.txt",
        "docs/CORE_RULES_REMEDIATION_ROADMAP.md",
        ASSESSMENT,
        MAP,
    }
)
DERIVATION_REPORT = "docs/performance/current/ci61-external_contract_source_reuse.json"
DERIVATION_MEMBERS = DERIVATION_CONTROLS | {
    DERIVATION_TEST,
    "docs/CI61_PROVENANCE_SCOPE.md",
    DERIVATION_REPORT,
    *(
        DERIVATION_NAMESPACE + "/" + name
        for name in (
            "changed-members.json",
            "control-transitions.json",
            "applicability.json",
            "producing-inputs.json",
            "source-token-roles.json",
            "source-token-inventories.json",
            "measurement-provenance.json",
            "measurements/source-base.json",
            "measurements/source-head.json",
            "receipts/source-base-0.json",
            "receipts/source-base-1.json",
            "receipts/source-base-2.json",
            "receipts/source-head-0.json",
            "receipts/source-head-1.json",
            "receipts/source-head-2.json",
        )
    ),
}
DERIVATION_INPUTS = frozenset(
    {
        SELF,
        "tools/performance_preflight.py",
        "tools/performance_history_snapshot.py",
        DERIVATION_TEST,
        MAP,
    }
)


PRELUDE_BASE = "620cbe91ae3ddd356eaf7effa7455b931882a39e"
PRELUDE_NAMESPACE = "data/source_audits/ci64_provenance_v1"
PRELUDE_FREEZE: str | None = None
PRELUDE_REPORT = "docs/performance/current/ci64-external_contract_source_reuse.json"
PRELUDE_CONTROLS = frozenset(
    {
        SELF,
        "tools/performance_policy.py",
        "tools/performance_preflight.py",
        "tests/code_quality/test_performance_policy.py",
        "tests/code_quality/test_performance_preflight.py",
        DERIVATION_TEST,
        "ci/quality_shards/all.txt",
        "ci/quality_shards/shard-1.txt",
        "docs/CORE_RULES_REMEDIATION_ROADMAP.md",
        ASSESSMENT,
        MAP,
    }
)
PRELUDE_NEW = frozenset(
    {
        "docs/CI64_PROVENANCE_SCOPE.md",
        PRELUDE_REPORT,
        *(
            PRELUDE_NAMESPACE + "/" + name
            for name in (
                "changed-members.json",
                "control-transitions.json",
                "applicability.json",
                "producing-inputs.json",
                "source-token-roles.json",
                "source-token-inventories.json",
                "measurement-provenance.json",
                "measurements/source-base.json",
                "measurements/source-head.json",
                "receipts/source-base-0.json",
                "receipts/source-base-1.json",
                "receipts/source-base-2.json",
                "receipts/source-head-0.json",
                "receipts/source-head-1.json",
                "receipts/source-head-2.json",
            )
        ),
    }
)
PRELUDE_MEMBERS = PRELUDE_CONTROLS | PRELUDE_NEW
PRELUDE_INPUTS = frozenset(
    {
        SELF,
        "tools/performance_policy.py",
        "tools/performance_preflight.py",
        "tests/code_quality/test_performance_policy.py",
        "tests/code_quality/test_performance_preflight.py",
        DERIVATION_TEST,
        MAP,
    }
)


def _prelude_transition(operands: AdmissionOperands) -> dict[str, bytes]:
    """One exact CI64 proof over already acquired bytes; no observation or cache."""
    from tools.performance_policy import owner_hashes

    values = {name: raw for name, _, raw in operands}
    freeze = values["next-freeze"].decode()
    names = json.loads(values["next-selection"])
    frozen = {name[12:]: raw for name, _, raw in operands if name.startswith("next-frozen/")}
    previous = {name[14:]: raw for name, _, raw in operands if name.startswith("next-previous/")}
    extra = {name[13:]: raw for name, _, raw in operands if name.startswith("next-current/")}
    observations = [
        (name.split("/", 1)[1], raw)
        for name, _, raw in operands
        if name.startswith(("current/", "observed/"))
    ]
    actual = dict(observations) | extra
    if (
        set(names) != PRELUDE_MEMBERS
        or len(names) != len(PRELUDE_MEMBERS)
        or set(frozen) != PRELUDE_MEMBERS
        or set(previous) != PRELUDE_CONTROLS
        or set(extra) != PRELUDE_NEW
        or json.loads(frozen[PRELUDE_NAMESPACE + "/changed-members.json"]) != sorted(names)
    ):
        raise ValueError("CI64 finite source membership changed.")
    record = json.loads(frozen[PRELUDE_NAMESPACE + "/control-transitions.json"])
    if (
        record.keys() != {"schema", "base", "changes"}
        or record["schema"] != "ci64-exact-provenance-v1"
        or record["base"] != PRELUDE_BASE
        or record["changes"].keys() != PRELUDE_CONTROLS - {ASSESSMENT}
    ):
        raise ValueError("CI64 exact transition membership changed.")
    for name, row in record["changes"].items():
        if (
            row.keys() != {"before_sha256", "after_sha256", "edits"}
            or digest(previous[name]) != row["before_sha256"]
            or digest(frozen[name]) != row["after_sha256"]
        ):
            raise ValueError("CI64 exact transition source changed.")
        projected = previous[name]
        for edit in row["edits"]:
            if edit.keys() != {"before", "after"} or not all(
                isinstance(value, str) and value for value in edit.values()
            ):
                raise ValueError("CI64 exact transition edit changed.")
            before, after = edit["before"].encode(), edit["after"].encode()
            if projected.count(before) != 1:
                raise ValueError("CI64 exact transition lacks one preimage.")
            projected = projected.replace(before, after, 1)
        if projected != frozen[name]:
            raise ValueError("CI64 source changed outside reviewed edits.")
    marker = b"\nPRELUDE_FREEZE: str | None = None"
    activated = f'\nPRELUDE_FREEZE: str | None = "{freeze}"'.encode()
    if frozen[SELF].count(marker) != 1:
        raise ValueError("CI64 original activation changed.")
    expected = frozen | {SELF: frozen[SELF].replace(marker, activated, 1)}
    assessment = json.loads(frozen[ASSESSMENT])
    row = assessment["changes"][SELF]
    row["after_sha256"] = digest(expected[SELF])
    row["owners"]["@module"]["after"] = owner_hashes(SELF, expected[SELF])["@module"]
    if (
        json.loads(actual[ASSESSMENT]) != assessment
        or json.loads(values["assessment-first"]) != assessment
        or values["assessment-second"] != actual[ASSESSMENT]
    ):
        raise ValueError("CI64 assessment changed outside exact activation.")
    expected[ASSESSMENT] = actual[ASSESSMENT]
    if {name: actual[name] for name in PRELUDE_MEMBERS} != expected:
        raise ValueError("CI64 Preflight source changed.")
    for name, raw in observations:
        if name in expected and raw != expected[name]:
            raise ValueError("CI64 Preflight source changed between observations: " + name)
    old_map, new_map = json.loads(previous[MAP]), json.loads(frozen[MAP])
    if {key: value for key, value in old_map.items() if key != "operations"} != {
        key: value for key, value in new_map.items() if key != "operations"
    } or any(
        new_map["operations"].get(key) != value for key, value in old_map["operations"].items()
    ):
        raise ValueError("CI64 changed an existing operation, family or budget.")
    for name in new_map["operations"].keys() - old_map["operations"].keys():
        operation = new_map["operations"][name]
        if (
            operation["mandatory"] is not True
            or len(operation["paths"]) != 1
            or operation["paths"][0] not in PRELUDE_INPUTS | PRELUDE_NEW
            or any(
                any(char in item for char in "*?[")
                for item in operation["paths"] + operation["owners"]
            )
        ):
            raise ValueError("CI64 new operation must be finite, literal and mandatory.")
    return previous


def _current_derivation_transition(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
    """Compose two finite pure proofs in the existing single admission entry."""
    previous = _prelude_transition(operands)
    projected = []
    for name, mode, raw in operands:
        if name.startswith(("current/", "observed/")):
            raw = previous.get(name.split("/", 1)[1], raw)
        elif name in {"assessment-first", "assessment-second"}:
            raw = previous[ASSESSMENT]
        if not name.startswith("next-"):
            projected.append((name, mode, raw))
    _derivation_transition(tuple(projected), identity)


def _prelude_preimage(actual: dict[str, bytes], name: str) -> bytes:
    """Reverse only an already authenticated exact control recipe to native E61."""
    if name not in PRELUDE_CONTROLS - {ASSESSMENT}:
        return actual[name]
    record = json.loads(actual[PRELUDE_NAMESPACE + "/control-transitions.json"])
    row = record["changes"][name]
    raw = actual[name]
    if name == SELF:
        activated = f'\nPRELUDE_FREEZE: str | None = "{PRELUDE_FREEZE}"'.encode()
        marker = b"\nPRELUDE_FREEZE: str | None = None"
        if raw.count(activated) != 1:
            raise ValueError("CI64 producing SELF is not the exact unactivated frozen source.")
        raw = raw.replace(activated, marker, 1)
    if digest(raw) != row["after_sha256"]:
        raise ValueError("CI64 authenticated control source changed.")
    for edit in reversed(row["edits"]):
        before, after = edit["before"].encode(), edit["after"].encode()
        if not before or not after or raw.count(after) != 1:
            raise ValueError("CI64 exact control transition changed.")
        raw = raw.replace(after, before, 1)
    if digest(raw) != row["before_sha256"]:
        raise ValueError("CI64 native predecessor changed.")
    return raw


def _derivation_transition(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
    """Authenticate the finite E-to-CI61 source; original CI60 objects stay original."""
    from tools.performance_policy import owner_hashes

    values = {name: raw for name, _, raw in operands}
    freeze = values["freeze"].decode()
    names = json.loads(values["selection"])
    frozen = {name[7:]: raw for name, _, raw in operands if name.startswith("frozen/")}
    previous = {name[9:]: raw for name, _, raw in operands if name.startswith("previous/")}
    current = {name[8:]: raw for name, _, raw in operands if name.startswith("current/")}
    observed = {name[9:]: raw for name, _, raw in operands if name.startswith("observed/")}
    if (
        set(names) != DERIVATION_MEMBERS
        or len(names) != len(DERIVATION_MEMBERS)
        or json.loads(frozen[DERIVATION_NAMESPACE + "/changed-members.json"]) != sorted(names)
        or set(previous) != DERIVATION_CONTROLS
        or set(current) != set(frozen)
    ):
        raise ValueError("CI61 finite source membership changed.")
    record = json.loads(frozen[DERIVATION_NAMESPACE + "/control-transitions.json"])
    if (
        record.keys() != {"schema", "base", "changes"}
        or record["schema"] != "ci61-exact-provenance-v1"
        or record["base"] != DERIVATION_BASE
        or record["changes"].keys() != DERIVATION_CONTROLS - {ASSESSMENT}
    ):
        raise ValueError("CI61 exact transition membership changed.")
    for name, row in record["changes"].items():
        if (
            row.keys() != {"before_sha256", "after_sha256", "edits"}
            or digest(previous[name]) != row["before_sha256"]
            or digest(frozen[name]) != row["after_sha256"]
        ):
            raise ValueError("CI61 exact transition source changed.")
        projected = previous[name]
        for edit in row["edits"]:
            if edit.keys() != {"before", "after"} or not all(
                isinstance(value, str) and value for value in edit.values()
            ):
                raise ValueError("CI61 exact transition edit changed.")
            before, after = edit["before"].encode(), edit["after"].encode()
            if projected.count(before) != 1:
                raise ValueError("CI61 exact transition lacks one preimage.")
            projected = projected.replace(before, after, 1)
        if projected != frozen[name]:
            raise ValueError("CI61 source changed outside reviewed edits.")
    marker = b"\nDERIVATION_FREEZE: str | None = None"
    activated = f'\nDERIVATION_FREEZE: str | None = "{freeze}"'.encode()
    if frozen[SELF].count(marker) != 1:
        raise ValueError("CI61 original activation changed.")
    expected = frozen | {SELF: frozen[SELF].replace(marker, activated, 1)}
    assessment = json.loads(frozen[ASSESSMENT])
    row = assessment["changes"][SELF]
    row["after_sha256"] = digest(expected[SELF])
    row["owners"]["@module"]["after"] = owner_hashes(SELF, expected[SELF])["@module"]
    if (
        json.loads(current[ASSESSMENT]) != assessment
        or json.loads(values["assessment-first"]) != assessment
        or values["assessment-second"] != current[ASSESSMENT]
    ):
        raise ValueError("CI61 assessment changed outside exact activation.")
    expected[ASSESSMENT] = current[ASSESSMENT]
    if current != expected:
        raise ValueError("CI61 Preflight source changed.")
    for name in observed.keys() & expected.keys():
        if observed[name] != expected[name]:
            raise ValueError("CI61 Preflight source changed between observations: " + name)
    old_map = json.loads(previous[MAP])
    new_map = json.loads(frozen[MAP])
    if {key: value for key, value in old_map.items() if key != "operations"} != {
        key: value for key, value in new_map.items() if key != "operations"
    } or any(
        new_map["operations"].get(key) != value for key, value in old_map["operations"].items()
    ):
        raise ValueError("CI61 changed an existing operation, family or budget.")
    additions = new_map["operations"].keys() - old_map["operations"].keys()
    for name in additions:
        operation = new_map["operations"][name]
        if (
            not operation["mandatory"]
            or len(operation["paths"]) != 1
            or operation["paths"][0]
            not in (
                DERIVATION_INPUTS
                | {
                    name
                    for name in DERIVATION_MEMBERS
                    if name.startswith(DERIVATION_NAMESPACE + "/")
                }
            )
            or any(
                any(char in item for char in "*?[")
                for item in operation["paths"] + operation["owners"]
            )
        ):
            raise ValueError("CI61 new operation must be finite, literal and mandatory.")


def _derivation_source(
    root: Path,
    observed: AdmissionOperands,
    first: tuple[str, int, bytes],
    second: tuple[str, int, bytes],
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    from tools.performance_history_snapshot import proof_identity
    from tools.performance_policy import owner_hashes
    from tools.performance_preflight import admission_proof, source_members
    from tools.performance_preflight_successor import read_frozen_blobs

    freeze = DERIVATION_FREEZE
    if freeze is None or len(freeze) != 40 or set(freeze) - set("0123456789abcdef"):
        raise ValueError("CI61 provenance source freeze is pending.")
    history(root, "merge-base", "--is-ancestor", DERIVATION_BASE, freeze)
    git(root, "merge-base", "--is-ancestor", freeze, "HEAD")
    names = history(root, "diff", "--name-only", DERIVATION_BASE, freeze).decode().splitlines()
    if set(names) != DERIVATION_MEMBERS or len(names) != len(DERIVATION_MEMBERS):
        raise ValueError("CI61 finite source membership changed.")
    frozen = read_frozen_blobs(root, freeze, names)
    previous = read_frozen_blobs(root, DERIVATION_BASE, sorted(DERIVATION_CONTROLS))
    current = source_members(root, list(frozen))
    # Preserve the complete original fourth scan, including its final directory
    # observations, before acquiring the seventeen genuinely new live members.
    next_freeze = PRELUDE_FREEZE
    if next_freeze is None or len(next_freeze) != 40 or set(next_freeze) - set("0123456789abcdef"):
        raise ValueError("CI64 provenance source freeze is pending.")
    history(root, "merge-base", "--is-ancestor", PRELUDE_BASE, next_freeze)
    git(root, "merge-base", "--is-ancestor", next_freeze, "HEAD")
    next_names = (
        history(root, "diff", "--name-only", PRELUDE_BASE, next_freeze).decode().splitlines()
    )
    if set(next_names) != PRELUDE_MEMBERS or len(next_names) != len(PRELUDE_MEMBERS):
        raise ValueError("CI64 finite source membership changed.")
    next_frozen = read_frozen_blobs(root, next_freeze, next_names)
    next_previous = read_frozen_blobs(root, PRELUDE_BASE, sorted(PRELUDE_CONTROLS))
    extra_names = [name for name in next_frozen if name in PRELUDE_NEW]
    extra = source_members(root, extra_names)
    operands = (
        ("next-freeze", 0, next_freeze.encode()),
        ("next-selection", 0, json.dumps(next_names, separators=(",", ":")).encode()),
        (
            "next-selectors",
            0,
            json.dumps(
                [
                    PRELUDE_BASE,
                    PRELUDE_NAMESPACE,
                    SELF,
                    ASSESSMENT,
                    MAP,
                    sorted(PRELUDE_CONTROLS),
                    sorted(PRELUDE_MEMBERS),
                    sorted(PRELUDE_NEW),
                    sorted(PRELUDE_INPUTS),
                ],
                separators=(",", ":"),
            ).encode(),
        ),
        *(("next-frozen/" + name, 0, raw) for name, raw in next_frozen.items()),
        *(("next-previous/" + name, 0, raw) for name, raw in next_previous.items()),
        *(("next-current/" + name, mode, raw) for name, mode, raw in extra),
        ("freeze", 0, freeze.encode()),
        ("selection", 0, json.dumps(names, separators=(",", ":")).encode()),
        (
            "selectors",
            0,
            json.dumps(
                [
                    DERIVATION_BASE,
                    DERIVATION_NAMESPACE,
                    SELF,
                    ASSESSMENT,
                    MAP,
                    sorted(DERIVATION_MEMBERS),
                    sorted(DERIVATION_CONTROLS),
                    sorted(DERIVATION_INPUTS),
                ],
                separators=(",", ":"),
            ).encode(),
        ),
        *(("frozen/" + name, 0, raw) for name, raw in frozen.items()),
        *(("previous/" + name, 0, raw) for name, raw in previous.items()),
        *(("current/" + name, mode, raw) for name, mode, raw in current),
        *(("observed/" + name, mode, raw) for name, mode, raw in observed),
        ("assessment-first", first[1], first[2]),
        ("assessment-second", second[1], second[2]),
    )
    admission_proof(
        _current_derivation_transition,
        operands,
        proof_identity(root),
        (
            digest,
            hashlib.sha256,
            json.loads,
            owner_hashes,
            _prelude_transition,
            _derivation_transition,
        ),
    )
    return (
        {name: raw for name, _, raw in current + extra},
        next_previous | previous,
    )


def _preceding_self(actual: dict[str, bytes], *, historical_ci61: bool = False) -> bytes:
    """Exact native E preimage already authenticated by the finite transition."""
    record = json.loads(actual[DERIVATION_NAMESPACE + "/control-transitions.json"])
    row = record["changes"][SELF]
    activated = f'\nDERIVATION_FREEZE: str | None = "{DERIVATION_FREEZE}"'.encode()
    marker = b"\nDERIVATION_FREEZE: str | None = None"
    raw = actual[SELF] if historical_ci61 else _prelude_preimage(actual, SELF)
    if raw.count(activated) != 1:
        raise ValueError("CI61 producing SELF is not the exact unactivated frozen source.")
    raw = raw.replace(activated, marker, 1)
    for edit in reversed(row["edits"]):
        before, after = edit["before"].encode(), edit["after"].encode()
        if not before or not after or raw.count(after) != 1:
            raise ValueError("CI61 exact SELF transition changed.")
        raw = raw.replace(after, before, 1)
    if digest(raw) != row["before_sha256"]:
        raise ValueError("CI61 original SELF preimage changed.")
    return raw


def _admitted_derivation(operands: AdmissionOperands, identity: tuple[str, ...]) -> None:
    """The complete original finite proof, with no filesystem or Git observation."""
    from tools.performance_policy import owner_hashes

    values = {name: raw for name, _, raw in operands}
    freeze = values["freeze"].decode()
    names = json.loads(values["selection"])
    frozen = {name[7:]: raw for name, _, raw in operands if name.startswith("frozen/")}
    old = {name[4:]: raw for name, _, raw in operands if name.startswith("old/")}
    current = {name[8:]: raw for name, _, raw in operands if name.startswith("current/")}
    declaration = NAMESPACE + "/changed-members.json"
    if json.loads(frozen[declaration]) != sorted(names) or len(names) != len(set(names)):
        raise ValueError("CI60 Qualification finite membership changed.")
    marker = b"\nFREEZE: str | None = None"
    if frozen[SELF].count(marker) != 1:
        raise ValueError("CI60 Qualification original activation changed.")
    actual = dict(frozen)
    actual[SELF] = frozen[SELF].replace(marker, f'\nFREEZE: str | None = "{freeze}"'.encode(), 1)
    assessment = json.loads(frozen[ASSESSMENT])
    row = assessment["changes"][SELF]
    row["after_sha256"] = digest(actual[SELF])
    row["owners"]["@module"]["after"] = owner_hashes(SELF, actual[SELF])["@module"]
    if json.loads(values["assessment-first"]) != assessment:
        raise ValueError("CI60 Qualification assessment changed outside exact activation.")
    actual[ASSESSMENT] = values["assessment-second"]
    if current.keys() != actual.keys():
        raise ValueError("CI60 Qualification finite membership changed.")
    for name, raw in actual.items():
        if current[name] != raw:
            raise ValueError("CI60 Qualification Preflight source changed: " + name)
    transitions = json.loads(frozen[NAMESPACE + "/control-transitions.json"])
    if set(transitions) != set(CONTROLS - {ASSESSMENT}):
        raise ValueError("CI60 Qualification control membership changed.")
    for name, row in transitions.items():
        if row.keys() != {"before_sha256", "after_sha256", "edits"}:
            raise ValueError("CI60 Qualification control recipe schema changed.")
        if digest(old[name]) != row["before_sha256"] or digest(frozen[name]) != row["after_sha256"]:
            raise ValueError("CI60 Qualification control recipe pin changed.")
        projected = old[name]
        for edit in row["edits"]:
            if edit.keys() != {"before", "after"} or not all(
                isinstance(value, str) for value in edit.values()
            ):
                raise ValueError("CI60 Qualification exact edit is malformed.")
            before, after = edit["before"].encode(), edit["after"].encode()
            if projected.count(before) != 1:
                raise ValueError("CI60 Qualification exact edit lacks one preimage.")
            projected = projected.replace(before, after, 1)
        if projected != frozen[name]:
            raise ValueError("CI60 Qualification control changed outside its exact recipe.")
    old_map, new_map = json.loads(old[MAP]), json.loads(frozen[MAP])
    additions = json.loads(frozen[NAMESPACE + "/added-operations.json"])
    if {k: v for k, v in old_map.items() if k != "operations"} != {
        k: v for k, v in new_map.items() if k != "operations"
    }:
        raise ValueError("CI60 Qualification historical families or budgets changed.")
    if new_map["operations"] != old_map["operations"] | additions:
        raise ValueError("CI60 Qualification historical operation changed.")
    for operation in additions.values():
        if (
            not operation["mandatory"]
            or len(operation["paths"]) != 1
            or any(
                any(c in literal for c in "*?[")
                for literal in operation["paths"] + operation["owners"]
            )
        ):
            raise ValueError("CI60 Qualification operation must remain literal and mandatory.")


def admitted(root: Path) -> dict[str, bytes]:
    """Fresh complete observations precede invocation-local pure proof reuse."""
    from tools.performance_history_snapshot import proof_identity
    from tools.performance_policy import owner_hashes
    from tools.performance_preflight import admission_proof, source_members
    from tools.performance_preflight_successor import read_frozen_blobs

    freeze = FREEZE
    if freeze is None or len(freeze) != 40 or set(freeze) - set("0123456789abcdef"):
        raise ValueError("CI60 Qualification source freeze is pending.")
    history(root, "merge-base", "--is-ancestor", BASE, freeze)
    git(root, "merge-base", "--is-ancestor", freeze, "HEAD")
    names = history(root, "diff", "--name-only", BASE, freeze).decode().splitlines()
    frozen = read_frozen_blobs(root, freeze, names)
    first = source_members(root, [ASSESSMENT])[0]
    second = source_members(root, [ASSESSMENT])[0]
    current = source_members(root, list(frozen))
    old = read_frozen_blobs(root, BASE, sorted(CONTROLS))
    derived, preceding = _derivation_source(root, current, first, second)
    projected = tuple((name, mode, preceding.get(name, raw)) for name, mode, raw in current)
    first = first[0], first[1], preceding[ASSESSMENT]
    second = second[0], second[1], preceding[ASSESSMENT]
    selectors = json.dumps(
        [BASE, SELF, NAMESPACE, ASSESSMENT, MAP, sorted(CONTROLS)], separators=(",", ":")
    ).encode()
    operands = (
        ("freeze", 0, freeze.encode()),
        ("selection", 0, json.dumps(names, separators=(",", ":")).encode()),
        ("selectors", 0, selectors),
        *((("frozen/" + name, 0, raw) for name, raw in frozen.items())),
        *((("old/" + name, 0, raw) for name, raw in old.items())),
        ("assessment-first", first[1], first[2]),
        ("assessment-second", second[1], second[2]),
        *((("current/" + name, mode, raw) for name, mode, raw in projected)),
    )
    identity = proof_identity(root)
    admission_proof(
        _admitted_derivation, operands, identity, (digest, hashlib.sha256, json.loads, owner_hashes)
    )
    return {name: raw for name, _, raw in current} | derived


def control_projection(root: Path) -> dict[str, bytes]:
    from tools.performance_preflight_successor import read_frozen_blobs

    admitted(root)
    return (
        read_frozen_blobs(root, PRELUDE_BASE, sorted(PRELUDE_CONTROLS - {SELF}))
        | read_frozen_blobs(root, BASE, sorted(CONTROLS))
        | read_frozen_blobs(root, DERIVATION_BASE, sorted(DERIVATION_CONTROLS - CONTROLS - {SELF}))
    )


def preceding_control(root: Path, name: str, supplied: bytes) -> bytes:
    if name == CURRENT_INVENTORY and (root / NAMESPACE).is_dir():
        return historical_inventory_preimage(root, supplied)
    if name not in CONTROLS:
        if name in (DERIVATION_CONTROLS | PRELUDE_CONTROLS) - {SELF}:
            actual = owned(root, name)
            if supplied != actual:
                raise ValueError("CI61 predecessor caller supplied unrelated bytes.")
            return control_projection(root)[name]
        return supplied
    actual = owned(root, name)
    if supplied != actual:
        raise ValueError("CI60 Qualification caller supplied unrelated bytes.")
    projection = control_projection(root)
    return projection[name]


CURRENT_INVENTORY = "data/source_audits/order135/current-inventory-category-migration.json"
CURRENT_INVENTORY_BEFORE = "c0460f930be48c49dcbef7568ea1af5e2319ca374d658b6abdb8eadd38869c16"
INVENTORY_TEST_CASES = {
    "tests/integration/test_fight_on_death_presence.py": (
        "test_order_30_other_destruction_triggers_wait_for_retained_model_completion",
        "test_order_30_retained_model_fights_from_original_base_then_is_removed",
    ),
    "tests/unit/test_phase12b_stratagem_framework.py": (
        "test_attached_unit_components_share_one_stratagem_affected_key",
        "test_different_stratagem_same_unit_same_phase_suppresses_options",
        "test_finite_stratagem_use_round_trips_through_lifecycle_and_spends_cp",
        "test_opponent_stratagem_targeting_unit_does_not_block_player_same_phase_stratagem",
        "test_parameterized_stratagem_target_proposals_validate_before_queue_pop",
        "test_same_phase_duplicate_and_battle_shocked_targeting_suppress_options",
        "test_same_stratagem_restriction_uses_active_player_phase_instance",
        "test_stratagem_spend_prevalidation_rejects_cp_drift_without_underflow",
    ),
}


def historical_inventory_preimage(root: Path, supplied: bytes) -> bytes:
    """Original DATA pin after exact current fourteen-field source refresh proof."""
    actual = admitted(root)
    if supplied != actual[CURRENT_INVENTORY]:
        raise ValueError("CI60 historical inventory caller supplied unrelated bytes.")
    before = history(root, "show", BASE + ":" + CURRENT_INVENTORY)
    if digest(before) != CURRENT_INVENTORY_BEFORE:
        raise ValueError("CI60 historical inventory native preimage changed.")
    expected = json.loads(before)
    for path, cases in INVENTORY_TEST_CASES.items():
        raw = actual[path]
        expected["current_files_observed"][path]["bytes"] = len(raw)
        expected["current_files_observed"][path]["sha256"] = digest(raw)
        for case in cases:
            expected["tests"][path + "::" + case]["file_sha256"] = digest(raw)
    if json.loads(supplied) != expected:
        raise ValueError("CI60 current inventory changed outside fourteen source fields.")
    return before


def current_source(root: Path, previous: dict[str, str]) -> dict[str, str]:
    from tools.performance_preflight_successor import read_frozen_blobs

    actual = admitted(root)
    prior_names = sorted(set(actual) & previous.keys())
    before = read_frozen_blobs(root, BASE, prior_names)
    if any(previous[name] != digest(before[name]) for name in prior_names):
        raise ValueError("CI60 Qualification predecessor source changed.")
    return previous | {name: digest(raw) for name, raw in actual.items()}


def measurement_controls(root: Path, current: dict[str, str]) -> dict[str, str]:
    """Only declared control bytes project; every current engine/fixture byte survives."""
    actual = admitted(root)
    projected = control_projection(root)
    result = dict(current)
    for name in ((DERIVATION_CONTROLS | PRELUDE_CONTROLS) - CONTROLS - {SELF}) & current.keys():
        if current[name] != digest(actual[name]):
            raise ValueError("CI61 actual input collector omitted current control bytes.")
        result[name] = digest(projected[name])
    for name in (CONTROLS | {SELF}) & current.keys():
        if current[name] != digest(actual[name]):
            raise ValueError("CI60 actual input collector omitted current control bytes.")
        if name == SELF:
            del result[name]
        else:
            result[name] = digest(projected[name])
    return result


def _cohort(actual: dict[str, bytes]) -> dict[str, Any]:
    value: dict[str, Any] = json.loads(actual[NAMESPACE + "/family-plan.json"])
    families: dict[str, Any] = value["families"]
    if (
        value["base"] != PR_BASE
        or len(families) != 12
        or {name for name, row in families.items() if row["disposition"] == "retained"}
        != set(RETAINED)
        or sum(len(row["cases"]) for row in families.values()) != 41
        or sum(len(row["cases"]) * row["samples_per_case"] for row in families.values()) != 247
    ):
        raise ValueError("CI60 Qualification family inventory changed.")
    families["external_contract_source_reuse"]["comparison"] = PRELUDE_REPORT
    return families


def comparison_paths(root: Path) -> dict[str, str]:
    return {family: row["comparison"] for family, row in _cohort(admitted(root)).items()}


def applies(root: Path, *, base: str, family: str, path: str) -> bool:
    return base == PR_BASE and comparison_paths(root).get(family) == path


def producing_inputs(root: Path, current: dict[str, str]) -> dict[str, str]:
    return _producing_inputs(admitted(root), current)


def _original_producing_inputs(
    actual: dict[str, bytes], *, historical_ci61: bool = False
) -> dict[str, str]:
    measured: dict[str, str] = json.loads(actual[NAMESPACE + "/producing-inputs.json"])
    activated = f'\nFREEZE: str | None = "{FREEZE}"'.encode()
    marker = b"\nFREEZE: str | None = None"
    original = _preceding_self(actual, historical_ci61=historical_ci61)
    if original.count(activated) != 1 or measured.get(SELF) != digest(
        original.replace(activated, marker, 1)
    ):
        raise ValueError("CI60 producing SELF is not the exact unactivated frozen source.")
    return measured


def _ci61_producing_inputs(actual: dict[str, bytes], current: dict[str, str]) -> dict[str, str]:
    _original_producing_inputs(actual, historical_ci61=True)
    measured: dict[str, str] = json.loads(actual[DERIVATION_NAMESPACE + "/producing-inputs.json"])
    activated = f'\nDERIVATION_FREEZE: str | None = "{DERIVATION_FREEZE}"'.encode()
    marker = b"\nDERIVATION_FREEZE: str | None = None"
    if actual[SELF].count(activated) != 1 or measured.get(SELF) != digest(
        actual[SELF].replace(activated, marker, 1)
    ):
        raise ValueError("CI61 producing SELF is not the exact unactivated frozen source.")
    if current != measured | {SELF: digest(actual[SELF])}:
        raise ValueError("CI61 complete producing inputs differ from the actual current collector.")
    return measured


def _ci61_view(actual: dict[str, bytes]) -> dict[str, bytes]:
    """Exact E61 control bytes for the original pure CI61 producing proof."""
    return actual | {
        name: _prelude_preimage(actual, name) for name in PRELUDE_CONTROLS - {ASSESSMENT}
    }


def _producing_inputs(actual: dict[str, bytes], current: dict[str, str]) -> dict[str, str]:
    historical = _ci61_view(actual)
    previous: dict[str, str] = json.loads(actual[DERIVATION_NAMESPACE + "/producing-inputs.json"])
    _ci61_producing_inputs(historical, previous | {SELF: digest(historical[SELF])})
    measured: dict[str, str] = json.loads(actual[PRELUDE_NAMESPACE + "/producing-inputs.json"])
    activated = f'\nPRELUDE_FREEZE: str | None = "{PRELUDE_FREEZE}"'.encode()
    marker = b"\nPRELUDE_FREEZE: str | None = None"
    if actual[SELF].count(activated) != 1 or measured.get(SELF) != digest(
        actual[SELF].replace(activated, marker, 1)
    ):
        raise ValueError("CI64 producing SELF is not the exact unactivated frozen source.")
    if current != measured | {SELF: digest(actual[SELF])}:
        raise ValueError("CI64 complete producing inputs differ from the actual current collector.")
    return measured


def _prelude_applicability(
    actual: dict[str, bytes], current: dict[str, str], family: str
) -> dict[str, Any]:
    """The seven current collector changes compose with authenticated CI61 applicability."""
    produced = _producing_inputs(actual, current)
    previous: dict[str, str] = json.loads(actual[DERIVATION_NAMESPACE + "/producing-inputs.json"])
    historical = _ci61_view(actual)
    old_proof = _current_applicability(
        historical, previous | {SELF: digest(historical[SELF])}, family
    )
    proof: dict[str, Any] = json.loads(actual[PRELUDE_NAMESPACE + "/applicability.json"])
    families = _cohort(actual)
    selected = set(families) - {"external_contract_source_reuse"}
    changed = {
        name: {"before": previous.get(name), "after": produced.get(name)}
        for name in previous.keys() | produced.keys()
        if previous.get(name) != produced.get(name)
    }
    unchanged = {name: pin for name, pin in previous.items() if produced.get(name) == pin}
    if (
        proof.keys()
        != {
            "schema",
            "original_input_digest",
            "current_producing_input_digest",
            "previous_applicability_sha256",
            "changes",
            "unchanged_inputs",
            "families",
        }
        or proof["schema"] != "ci64-finite-current-applicability-v1"
        or proof["original_input_digest"] != canonical(previous)
        or proof["current_producing_input_digest"] != canonical(produced)
        or proof["previous_applicability_sha256"] != canonical(old_proof)
        or proof["changes"] != changed
        or changed.keys() != PRELUDE_INPUTS
        or previous.keys() != produced.keys()
        or proof["unchanged_inputs"] != unchanged
        or set(proof["families"]) != selected
        or family not in selected
    ):
        raise ValueError("CI64 complete current applicability changed.")
    for name, row in proof["families"].items():
        required = {
            families[name]["driver"],
            "tests/conftest.py",
            "tests/__init__.py",
            "tests/timing_plugin.py",
            "pyproject.toml",
            "uv.lock",
        }
        if (
            row.keys() != {"driver", "unchanged_startup", "call_path"}
            or row["driver"] != families[name]["driver"]
            or row["unchanged_startup"] != {path: unchanged[path] for path in sorted(required)}
            or not isinstance(row["call_path"], str)
            or not row["call_path"]
        ):
            raise ValueError("CI64 timed consumer/startup proof changed.")
    return proof


def _current_applicability(
    actual: dict[str, bytes], current: dict[str, str], family: str
) -> dict[str, Any]:
    """Complete current inputs differ only in the finite uncalled provenance controls."""
    produced = _ci61_producing_inputs(actual, current)
    previous = _original_producing_inputs(actual, historical_ci61=True)
    proof: dict[str, Any] = json.loads(actual[DERIVATION_NAMESPACE + "/applicability.json"])
    families = _cohort(actual)
    selected = set(families) - {"external_contract_source_reuse"}
    changed = {
        name: {"before": previous.get(name), "after": produced.get(name)}
        for name in previous.keys() | produced.keys()
        if previous.get(name) != produced.get(name)
    }
    unchanged = {name: pin for name, pin in previous.items() if produced.get(name) == pin}
    if (
        proof.keys()
        != {
            "schema",
            "original_input_digest",
            "current_producing_input_digest",
            "changes",
            "unchanged_inputs",
            "families",
        }
        or proof["schema"] != "ci61-finite-current-applicability-v1"
        or proof["original_input_digest"] != canonical(previous)
        or proof["current_producing_input_digest"] != canonical(produced)
        or proof["changes"] != changed
        or not changed.keys() <= DERIVATION_INPUTS
        or proof["unchanged_inputs"] != unchanged
        or set(proof["families"]) != selected
        or family not in selected
    ):
        raise ValueError("CI61 complete current applicability changed.")
    for name, row in proof["families"].items():
        required = {
            families[name]["driver"],
            "tests/conftest.py",
            "tests/__init__.py",
            "tests/timing_plugin.py",
            "pyproject.toml",
            "uv.lock",
        }
        if (
            row.keys() != {"driver", "unchanged_startup", "call_path"}
            or row["driver"] != families[name]["driver"]
            or row["unchanged_startup"] != {path: unchanged[path] for path in sorted(required)}
            or not isinstance(row["call_path"], str)
            or not row["call_path"]
        ):
            raise ValueError("CI61 timed consumer/startup proof changed.")
    return proof


def extend_catalog(builder: Any) -> None:
    """Append the finite CI60 native objects after the unchanged historical catalog."""
    freeze = FREEZE
    if freeze is None:
        raise ValueError("CI60 Qualification catalog freeze is pending.")
    builder.fact("plain60", ("merge-base", "--is-ancestor", BASE, freeze), "ci60.ancestry")
    raw = builder.fact("plain60", ("diff", "--name-only", BASE, freeze), "ci60.membership")
    names = raw.decode().splitlines()
    frozen = builder.add("plain60", freeze, dict.fromkeys(names), "ci60.freeze")
    if json.loads(frozen[NAMESPACE + "/changed-members.json"]) != sorted(names):
        raise ValueError("CI60 Qualification native membership changed.")
    builder.add("plain60", BASE, dict.fromkeys(CONTROLS), "ci60.control-preimages")
    # current_source verifies the exact original predecessor for every existing member.
    existing = set(builder.all_paths("plain60", BASE)) & set(names)
    builder.add("plain60", BASE, dict.fromkeys(existing), "ci60.source-preimages")
    derivation = DERIVATION_FREEZE
    if derivation is None:
        raise ValueError("CI61 provenance catalog freeze is pending.")
    builder.fact(
        "plain60",
        ("merge-base", "--is-ancestor", DERIVATION_BASE, derivation),
        "ci61.ancestry",
    )
    changed = (
        builder.fact(
            "plain60", ("diff", "--name-only", DERIVATION_BASE, derivation), "ci61.membership"
        )
        .decode()
        .splitlines()
    )
    if set(changed) != DERIVATION_MEMBERS or len(changed) != len(DERIVATION_MEMBERS):
        raise ValueError("CI61 native catalog membership changed.")
    builder.add("plain60", derivation, dict.fromkeys(changed), "ci61.freeze")
    builder.add("plain60", DERIVATION_BASE, dict.fromkeys(DERIVATION_CONTROLS), "ci61.preimages")
    earlier = set(builder.all_paths("plain60", BASE)) & set(changed)
    builder.add("plain60", BASE, dict.fromkeys(earlier), "ci61.source-preimages")

    prelude = PRELUDE_FREEZE
    if prelude is None:
        raise ValueError("CI64 provenance catalog freeze is pending.")
    builder.fact("plain60", ("merge-base", "--is-ancestor", PRELUDE_BASE, prelude), "ci64.ancestry")
    changed = (
        builder.fact("plain60", ("diff", "--name-only", PRELUDE_BASE, prelude), "ci64.membership")
        .decode()
        .splitlines()
    )
    if set(changed) != PRELUDE_MEMBERS or len(changed) != len(PRELUDE_MEMBERS):
        raise ValueError("CI64 native catalog membership changed.")
    builder.add("plain60", prelude, dict.fromkeys(changed), "ci64.freeze")
    builder.add("plain60", PRELUDE_BASE, dict.fromkeys(PRELUDE_CONTROLS), "ci64.preimages")
    earlier = set(builder.all_paths("plain60", BASE)) & set(changed)
    builder.add("plain60", BASE, dict.fromkeys(earlier), "ci64.source-preimages")


def source_binding(
    actual: dict[str, bytes], input_digest: str, *, namespace: str = PRELUDE_NAMESPACE
) -> dict[str, Any]:
    if namespace not in {DERIVATION_NAMESPACE, PRELUDE_NAMESPACE}:
        raise ValueError("Source-token namespace is not an admitted finite cohort.")
    spec = json.loads(actual[namespace + "/source-token-roles.json"])
    inventories = json.loads(actual[spec["inventories_path"]])
    before, after = inventories["base"], inventories["head"]
    common = {name: pin for name, pin in before.items() if after.get(name) == pin}
    changed = (before.keys() | after.keys()) - common.keys()
    if (
        spec["schema"] != "tool-input-roles-v3"
        or spec["base_revision"] != PR_BASE
        or canonical(inventories) != spec["inventories_sha256"]
        or canonical(common) != spec["common_sha256"]
        or spec["roles"].keys() != changed
        or any(
            role
            not in {"runtime-or-generator-treatment", "side-derived-output", "untimed-governance"}
            for role in spec["roles"].values()
        )
    ):
        raise ValueError("CI60 complete source-token input roles changed.")
    return {
        "schema": spec["schema"],
        "family": "external_contract_source_reuse",
        "base_revision": PR_BASE,
        "head_input_digest": input_digest,
        "role_spec_sha256": canonical(spec),
        "complete_inventories_sha256": canonical(inventories),
        "common_sha256": canonical(common),
        "contract_trees": spec["contract_trees"],
        "runtime_identities": spec["runtime_identities"],
        "shared_dependencies_sha256": spec["shared_dependencies_sha256"],
        "shared_workload_sha256": spec["shared_workload_sha256"],
    }


def retained_role_proof(
    root: Path,
    family: str,
    actual: dict[str, bytes],
    current: dict[str, str],
    measured: dict[str, str],
) -> dict[str, Any]:
    from tools.performance_policy import owner_hashes

    proofs = json.loads(actual[NAMESPACE + "/retained-role-proofs.json"])
    if proofs.keys() != set(RETAINED) or family not in RETAINED:
        raise ValueError("CI60 retained applicability is limited to two exact families.")
    proof: dict[str, Any] = proofs[family]
    changed = {
        name for name in current.keys() | measured.keys() if current.get(name) != measured.get(name)
    }
    if (
        proof["current_input_digest"] != canonical(current)
        or proof["producing_input_digest"] != canonical(measured)
        or proof["changed_inputs"].keys() != changed
    ):
        raise ValueError("CI60 retained family roles omit or invent current inputs.")
    for name, row in proof["changed_inputs"].items():
        if (
            row["before"] != measured.get(name)
            or row["after"] != current.get(name)
            or row["role"]
            not in {
                "uncalled-owner",
                "identity-only",
                "untimed-governance",
                "unchanged-called-owner-in-changed-module",
            }
            or len(row["reason"].strip()) < 30
        ):
            raise ValueError("CI60 retained family changed-input role changed.")
    for name, owners in proof["called_owners"].items():
        current_owners = owner_hashes(name, owned(root, name))
        if any(current_owners.get(owner) != pin for owner, pin in owners.items()):
            raise ValueError("CI60 retained family called owner changed: " + name)
    if not proof["called_owners"] or len(proof["call_path"].strip()) < 100:
        raise ValueError("CI60 retained family call proof is incomplete.")
    return proof


def measurement(
    root: Path,
    *,
    current: dict[str, str],
    report: dict[str, Any],
    family: str,
) -> tuple[dict[str, str], dict[str, object] | None, str, str]:
    """Original runtimes stay original; current applicability is a separate receipt."""
    from tools import cumulative_preservation as cumulative
    from tools import performance_qualification_measurements as measurements
    from tools import performance_qualification_successor as old
    from tools import performance_tool_inputs_v3 as roles
    from warhammer40k_core.build_identity import verified_engine_build_identity

    live = cumulative.verify_live(root)
    actual = admitted(root)
    inputs = _producing_inputs(actual, current)
    families = _cohort(actual)
    plan = families[family]
    applicability = None
    if family != "external_contract_source_reuse":
        applicability = _prelude_applicability(actual, current, family)
        inputs = _original_producing_inputs(actual)
    qualified_inputs = inputs
    binding = None
    proof: dict[str, Any] | None = None
    if family in RETAINED:
        historical_stage = cast(_HistoricalStage, old)
        freeze = _HistoricalStage.freeze(historical_stage, root)
        inputs = json.loads(
            _HistoricalStage.member(
                historical_stage, root, old.NAMESPACE + "/producing-inputs.json", freeze
            )
        )
        if canonical(inputs) != old.PRODUCING_INPUT_DIGEST:
            raise ValueError("CI60 original producing input authority changed.")
        proof = retained_role_proof(root, family, actual, qualified_inputs, inputs)
        provenance = json.loads(
            _HistoricalStage.member(
                historical_stage, root, old.NAMESPACE + "/measurement-provenance.json", freeze
            )
        )
        row = provenance[family]
        original = json.loads(
            _HistoricalStage.member(historical_stage, root, plan["comparison"], freeze)
        )
        if report != original:
            raise ValueError("CI60 retained report changed its original samples or identities.")
        runtime = row["head"]["runtime_build_id"]

        def member(name: str) -> bytes:
            return _HistoricalStage.member(historical_stage, root, name, freeze)
    else:
        provenance = json.loads(actual[NAMESPACE + "/measurement-provenance.json"])
        if set(provenance) != set(families) - RETAINED:
            raise ValueError("CI60 fresh family provenance membership changed.")
        if family == "external_contract_source_reuse":
            provenance = json.loads(actual[PRELUDE_NAMESPACE + "/measurement-provenance.json"])
            if set(provenance) != {"external_contract_source_reuse"}:
                raise ValueError("CI61 fresh source-token provenance membership changed.")
        row = provenance[family]
        runtime = verified_engine_build_identity().build_id

        def member(name: str) -> bytes:
            return actual[name]

    if (
        row["base_revision"] != PR_BASE
        or row["head_input_digest"] != canonical(inputs)
        or report["family"] != family
        or report["base_revision"] != PR_BASE
        or report["head_runtime_build_id"] != runtime
    ):
        raise ValueError("CI60 comparison has another producing cohort.")
    for side in ("base", "head"):
        arm = row[side]
        raw = json.loads(member(arm["path"]))
        samples = measurements.samples_from_raw(family, raw)
        if (
            canonical(raw) != arm["canonical_sha256"]
            or samples != arm["samples"]
            or samples != report[side]["samples"]
            or set(samples) != set(plan["cases"])
            or any(len(values) != plan["samples_per_case"] for values in samples.values())
            or report[side]["runtime_build_id"] != arm["runtime_build_id"]
            or arm["completed"] is not True
        ):
            raise ValueError("CI60 raw report lost a sample, case, completion or identity.")
        if not arm["receipt_paths"]:
            raise ValueError("CI60 measured arm lacks a whole-process receipt.")
        for path in arm["receipt_paths"]:
            receipt = json.loads(member(path))
            if receipt["exit_code"] != 0 or receipt["timeout"] or receipt["source_drift"]:
                raise ValueError("CI60 measured arm failed or changed source.")
    if family == "external_contract_source_reuse":
        binding = source_binding(actual, canonical(inputs), namespace=PRELUDE_NAMESPACE)
        if report["input_binding"] != binding:
            raise ValueError("CI60 source-token report has unrelated complete roles.")
        roles.validate_generated_evidence(report["generated_output_binding"], binding)
    if cumulative.verify_live(root) != live:
        raise ValueError("CI60 source changed during evidence admission.")
    receipt = canonical(
        {
            "current_source": live,
            "current_inputs": canonical(current),
            "current_runtime": verified_engine_build_identity().build_id,
            "family": family,
            "disposition": plan["disposition"],
            "producing_inputs": canonical(inputs),
            "producing_runtime": runtime,
            "raw_provenance": row,
            "retained_role_proof": proof,
            "current_applicability": applicability,
        }
    )
    return inputs, binding, receipt, runtime


def retained_historical_report(*, base: str, path: str, change: dict[str, object]) -> bool:
    """Exact immutable former-current records remain historical obligations."""
    return (
        base == PR_BASE
        and path in SUPERSEDED_REPORTS
        and change["before_sha256"] is None
        and change["after_sha256"] == SUPERSEDED_REPORTS[path]
    )


class _HistoricalStage(Protocol):
    def _freeze(self, root: Path) -> str: ...
    def _member(self, root: Path, name: str, freeze: str) -> bytes: ...
    def _read(self, root: Path, name: str) -> bytes: ...

    def freeze(self, root: Path) -> str:
        return self._freeze(root)

    def member(self, root: Path, name: str, freeze: str) -> bytes:
        return self._member(root, name, freeze)

    def read(self, root: Path, name: str) -> bytes:
        return self._read(root, name)


def historical_inputs(root: Path, *, original_controls: bool = False) -> dict[str, str]:
    """Authenticated old dictionary for historical assertions; never current credit."""
    from tools import performance_qualification_successor as old

    stage = cast(_HistoricalStage, old)
    freeze = _HistoricalStage.freeze(stage, root)
    result: dict[str, str] = json.loads(
        _HistoricalStage.member(stage, root, old.NAMESPACE + "/producing-inputs.json", freeze)
    )
    if canonical(result) != old.PRODUCING_INPUT_DIGEST:
        raise ValueError("CI60 original producing input authority changed.")
    if original_controls:
        allowed = {old.SELF, MAP, "tests/code_quality/test_qualification40_successor.py"}
        result |= {name: digest(_HistoricalStage.read(stage, root, name)) for name in allowed}
    return result


def historical_ledger_owners(root: Path, path: str, current: dict[str, str]) -> dict[str, str]:
    """One historical module-import assertion; never a measurement-input projection."""
    name = "src/warhammer40k_core/engine/retained_demise_removal.py"
    if path != name:
        return current
    from tools.performance_policy import owner_hashes

    before = "482b60427ede07c2ef519a7633aa53e463c05dc353290f26e34cfe62594ced83"
    after = "fde9ffe9f023bf0d1fcbfed6c10bdf62481d0915bbaeda34462525a28e51ec79"
    actual = admitted(root)
    if current.get("@module") != after or owner_hashes(name, actual[name]) != current:
        raise ValueError("CI60 current retained-demise owner source changed.")
    raw = actual[name].replace(b"\r\n", b"\n")
    import_line = (
        b"    from warhammer40k_core.engine.retained_destruction_state "
        b"import RetainedModelDestruction\n"
    )
    if (
        raw.count(import_line) != 1
        or owner_hashes(name, raw.replace(import_line, b"", 1)).get("@module") != before
    ):
        raise ValueError("CI60 ledger successor is not the sole reviewed type-only import.")
    original = owner_hashes(name, history(root, "show", BASE + ":" + name))
    if original.get("@module") != before:
        raise ValueError("CI60 original retained-demise ledger owner changed.")
    return current | {"@module": before}


HISTORICAL_TEST_PINS: dict[str, str] = {
    "tests/shared/category_migration/phase11e_mission_scoring_cleanup_configuration.py": (
        "dcf42d1f5991ab5ced6061152472bc00e415117709c4c30846f8f709069a8553"
    ),
    "tests/shared/category_migration/phase11e_mission_scoring_cleanup_history_and_reserves.py": (
        "3f579830b668704ccbfd4b94da524df1c74e297ab52614ae0168ef298e6144da"
    ),
    "tests/integration/test_fight_on_death_presence.py": (
        "c63c3b334a69aa742e86da70d61f602a4eaf5144a51da88c1837bbc228917123"
    ),
    "tests/setup_completion_helpers.py": (
        "928c24e7775f97890720fee9619432029bed4821ff1a5c72871148af02c12c15"
    ),
    "tests/unit/test_phase12b_stratagem_framework.py": (
        "4aace3168598f0a8f8d02f23ece82e611dfb73657629941be99fc5dc0e4c0a64"
    ),
    "tests/unit/test_phase17g_runtime_content.py": (
        "e30343a5fceafc63e3c31f0228d3d3a555882920ea0260623123e9c9bf5fe5fd"
    ),
}
HISTORICAL_CATEGORY_TESTS = frozenset(
    {
        "tests/unit/test_phase17g_runtime_content.py",
        "tests/shared/category_migration/phase11e_mission_scoring_cleanup_configuration.py",
        "tests/shared/category_migration/phase11e_mission_scoring_cleanup_history_and_reserves.py",
    }
)
HISTORICAL_DIRECT_TESTS = frozenset(HISTORICAL_TEST_PINS) - HISTORICAL_CATEGORY_TESTS


def historical_test_preimage(root: Path, path: str, current: bytes) -> bytes:
    """Exact historical assertion view; never a physical pytest or measured input."""
    if path not in HISTORICAL_TEST_PINS:
        return current
    actual = admitted(root)
    if current != actual[path]:
        raise ValueError("CI60 historical test caller supplied unrelated current bytes.")
    before = history(root, "show", BASE + ":" + path)
    if digest(before) != HISTORICAL_TEST_PINS[path]:
        raise ValueError("CI60 historical test native preimage changed.")

    def assertions(raw: bytes) -> Counter[str]:
        return Counter(
            ast.dump(node, include_attributes=False)
            for node in ast.walk(ast.parse(raw))
            if isinstance(node, ast.Assert)
        )

    if assertions(before) - assertions(current):
        raise ValueError("CI60 historical test lost an original assertion.")
    return before


class _HistoricalPrevious(Protocol):
    def __call__(
        self, root: Path, name: str, supplied: bytes, *, predecessor: bytes | None = None
    ) -> bytes: ...


def _historical_ci54_functions(root: Path) -> dict[str, Any]:
    """Original native CI54 function for its explicitly sparse historical test fixture."""
    from tools import quality_runtime_successor as original

    projection = control_projection(root)
    source = ast.parse(projection[original.SELF])
    functions: list[ast.stmt] = [
        node
        for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name in {"admit", "previous"}
    ]
    if {node.name for node in functions if isinstance(node, ast.FunctionDef)} != {
        "admit",
        "previous",
    } or len(functions) != 2:
        raise ValueError("CI60 original CI54 admission owner changed.")
    physical = original.owned

    def historical_read(selected: Path, name: str) -> bytes:
        if selected == root and name in projection:
            return projection[name]
        return physical(selected, name)

    namespace = dict(vars(original)) | {"owned": historical_read}
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), "authenticated-ci54-admit", "exec"),
        namespace,
    )
    return namespace


def historical_ci54_admission(root: Path) -> Callable[[Path], None]:
    return cast(Callable[[Path], None], _historical_ci54_functions(root)["admit"])


def historical_ci54_previous(root: Path) -> _HistoricalPrevious:
    return cast(_HistoricalPrevious, _historical_ci54_functions(root)["previous"])
