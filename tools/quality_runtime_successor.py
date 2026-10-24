"""Finite CI54 source transition; every prior assertion and historical pin remains intact."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

BASE = "5396b557fd90a67e0c097da1020959b58724a7ec"
SELF = "tools/quality_runtime_successor.py"
RECORD = "docs/performance/ci-quality-runtime54.json"
ASSESSMENT = "docs/performance/change-assessment.json"
FREEZE: str | None = "6fb2b40a42ca64802ac593ca73889d41583b9ffe"
PINS: dict[str, str] = {
    ".github/workflows/ci.yml": (
        "91d7b64dbed61e5fd959ef2db8d9dfff0d967ae0b0bfc4d22aabaccfb27f18f7"
    ),
    "ci/quality_shards/all.txt": (
        "8df91b5d75cc914289c8f590597ac295a67b18ba728fc9365b0c6eb9f30c7dd0"
    ),
    "ci/quality_shards/baseline-ci53.txt": (
        "308870fb4095de8e263def2e75ac71687bc65c3b32f06f591fed848fc34b4ef3"
    ),
    "ci/quality_shards/shard-1-modules.txt": (
        "6134b0b35c0072935aa1c215507f3877ca26911ef5b35df75089644685b5d2ab"
    ),
    "ci/quality_shards/shard-1.txt": (
        "a0e8077184b1a65546791f4b2cdeb66a472968a2ce2af0e5907668f5a10f9c32"
    ),
    "ci/quality_shards/shard-2-modules.txt": (
        "47cef6512f7f708a0303d903bb31865de214f7cc91a4889498e809bb4af7f74f"
    ),
    "ci/quality_shards/shard-2.txt": (
        "0d1792bce29af2037ebc23a2736baa3a695f9dcc5e5d054f241d9e77e0cea007"
    ),
    "ci/quality_shards/shard-3-modules.txt": (
        "1677cbafcc8257c3803cd4bfa65f12a2d4293e622840bfb47c657893b0315344"
    ),
    "ci/quality_shards/shard-3.txt": (
        "d2a169aea7729bbb173304ee53e095a08f0a98e1400afe82502d87c83a10ecee"
    ),
    "ci/quality_shards/shard-4-modules.txt": (
        "e5ab009fc440840dac9717a0f05b64cd47f371664a9f838e5ca17fe1d210e7bd"
    ),
    "ci/quality_shards/shard-4.txt": (
        "53ea730de39ce522a62461daec9ccf353c0b0fe04534aadb7800f53705ef8341"
    ),
    "docs/CORE_RULES_REMEDIATION_ROADMAP.md": (
        "b627e0688559b1fc46307c8449d17095307dd1fdc7a969c20cf5378a34887a0a"
    ),
    "docs/performance/ci-quality-runtime54.json": (
        "a837c4caaab81880e6e4bd5c93943954647bcaa62cd750c85f2596191516aeb4"
    ),
    "docs/performance/history-phase-snapshot.md": (
        "eff5ac4c71a42a547507bbba0713b33f89330fecaa1a931032395629f063e72a"
    ),
    "scripts/check_performance_policy.py": (
        "a662c87aff61d5e49b7edbec93ac5109b2713f3269e4aff14db5a939aedd704a"
    ),
    "scripts/quality_evidence.py": (
        "923b8da16949a54a2d8e1b984aecce34e1e9d6de08bc698b54469dd920418808"
    ),
    "scripts/quality_reporter.py": (
        "3e0fdae7fabd9342a5350cde41cc5f678966851733d029e6ca36051174ccc014"
    ),
    "scripts/quality_runner.py": (
        "51dfd0d535c0c3d8227653a50e7f1755b2181e717e12e71594e9f31f3d337517"
    ),
    "tests/code_quality/test_ci_history_input.py": (
        "204350bb9b037839d42c60975a35055d54aefbb0222f718b8937860464c18833"
    ),
    "tests/code_quality/test_ci_performance_gates.py": (
        "843d9f8b18851ee99d34779b994714286d7e70f482a35e593b2f7ef1976730c3"
    ),
    "tests/code_quality/test_ci_runtime_successor.py": (
        "e90ce2f38ae81cf82a7de6648d1482e0d6d23a81c449506fa2f3326633399f79"
    ),
    "tests/code_quality/test_performance_policy.py": (
        "8494642f66f70ce0cc71d330e164eba067e90e9ebea3eb1f0c11fbb4dbc25c69"
    ),
    "tests/code_quality/test_performance_preflight.py": (
        "68c001826e8d063d840ddf704d81fbd720b69e8f72a57a188e920f5e76982e76"
    ),
    "tests/code_quality/test_quality_runtime.py": (
        "0203134e35a15f7862bd51107684251d8ef741788eac47658e1e5b3d85070221"
    ),
    "tests/code_quality/test_quality_runtime_process.py": (
        "8c19b977eefd4d587b8116f9af0c0ced4c2a1040cec9a1d5fe619014ac03e45d"
    ),
    "tools/cumulative_preservation.py": (
        "8f3a7a87d29bd4fe49a04321fc83070b396e930d25e7c3fe97f656c625609d64"
    ),
    "tools/performance_history_snapshot.py": (
        "108f451110eac2162ca25bb68aa0e2610222a306db5ac04f5eb002f4e81c19c1"
    ),
    "tools/performance_policy.py": (
        "c110135e06b3ded99c69adc23d2571e610824a562ce0a7acc84dcb6955e2708d"
    ),
    "tools/performance_preflight_successor.py": (
        "60e1e493fe3aaaf98e88c28c85b781c52c5355ece3be556ea33681819817df59"
    ),
    "tools/performance_qualification_successor.py": (
        "d5fccbb82ccce15700443eba27130f3e859d60f7b6b5b64294cd9619c9f1923b"
    ),
    "tools/thousand_sons_perils_preservation.py": (
        "3dbedc63406bf2088320d62d4571981457f130453e52f4ba7643433cdd878e3b"
    ),
}
BEFORE: dict[str, str] = {
    ".github/workflows/ci.yml": (
        "ee0d1a9d331a06195836847d291184b82b94a5d9cfc36bb7485cfabb6bd1c0fe"
    ),
    "docs/CORE_RULES_REMEDIATION_ROADMAP.md": (
        "630b8a18ca865d40b0b0d31dcff2a9d6f551f6a62c62a3c1ec9e02dea514de4a"
    ),
    "docs/performance/change-assessment.json": (
        "ffc4c16a77d50c889a2e7edf668f350d24dea67d4ffe8b99b14a491bed33c5f3"
    ),
    "tests/code_quality/test_ci_history_input.py": (
        "762bfc9bd8d6094dc53205da38ecbbf11058dd8948a583d725e5b79b6fad4fcb"
    ),
    "tests/code_quality/test_ci_performance_gates.py": (
        "23dc913cc9d2def5a1a0625f4acd95881fb06fa3561d54feb21c158446a25267"
    ),
    "tests/code_quality/test_ci_runtime_successor.py": (
        "f0a91c3093e954287cbebb8e05b2c03bf03f9d827c69b6e1bc6906da60bd7c89"
    ),
    "tests/code_quality/test_performance_policy.py": (
        "f21c4726c30d75d7f8ddc534d0172d5a4485b98bdece6bac06bd2f64e349c6a3"
    ),
    "tools/performance_policy.py": (
        "fb1bf3b9b983df3301edd047f5855efd1352507934f37bd88005e4b4eafe5a2e"
    ),
    "tools/performance_preflight_successor.py": (
        "d5eb85fb360283515f99beb3b01dd7f6351750f4b72c43e68bbf686981796dba"
    ),
    "tests/code_quality/test_performance_preflight.py": (
        "b6924bdca684374749f2a86d7e086192de3ace2b6eac595aa558deb8117c57e6"
    ),
}

# Additional snapshot owner preimages; the original borrowed-role map stays exact.
SNAPSHOT_BEFORE: dict[str, str] = {
    "scripts/check_performance_policy.py": (
        "ce2c1e27152f0eb030b867078f543bb94472a7b3b0cf3cd0d5e2cc1102111209"
    ),
    "tools/cumulative_preservation.py": (
        "0aed6e5a524e891710bc85c2eda40565ca1f5cfc5c07f268acdb6ec727c060f3"
    ),
    "tools/performance_qualification_successor.py": (
        "45ba0c6dd10afb1f49f42e1cfe8ae77dab08b66436f2e9b4d8517415db28ed2a"
    ),
    "tools/thousand_sons_perils_preservation.py": (
        "2e9ef0110809dde8b380e04a7b608095672c10ea39b8cfc9aff8318002320894"
    ),
}

BORROWED_PREDECESSORS = frozenset(
    {
        ".github/workflows/ci.yml",
        "docs/CORE_RULES_REMEDIATION_ROADMAP.md",
        "tests/code_quality/test_ci_history_input.py",
        "tests/code_quality/test_ci_runtime_successor.py",
        "tools/performance_policy.py",
    }
)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root, timeout=30)


def _history(root: Path, *args: str) -> bytes:
    from tools.performance_history_snapshot import historical

    return historical(root, "plain30", args, lambda: git(root, *args))


def owned(root: Path, name: str) -> bytes:
    from tests.d07_geometry_containment import read_owned_geometry_member

    value: bytes = read_owned_geometry_member(root, name)
    return value


def previous(root: Path, name: str, supplied: bytes, *, predecessor: bytes | None = None) -> bytes:
    """Fresh member admission; a caller may lend only five exact historical payloads."""
    if predecessor is not None:
        from tools.performance_preflight_successor import PINS as preflight_pins

        if name not in BORROWED_PREDECESSORS or preflight_pins.get(name) != BEFORE.get(name):
            raise ValueError("CI54 predecessor borrowing is not admitted for this path.")
    before_pins = BEFORE | SNAPSHOT_BEFORE
    if name not in before_pins:
        return supplied
    actual = owned(root, name)
    if name == ASSESSMENT:
        admit(root)
    elif digest(actual) != PINS[name]:
        raise ValueError("CI54 Preflight source changed: " + name)
    if supplied != actual:
        raise ValueError("CI54 predecessor caller supplied unrelated bytes.")
    old = _history(root, "show", BASE + ":" + name) if predecessor is None else predecessor
    if digest(old) != before_pins[name]:
        raise ValueError("CI54 immutable predecessor changed.")
    return old


def admit(root: Path) -> None:
    """Read the one bounded successor inventory afresh; no mutable admission cache."""
    from tools.performance_policy import owner_hashes
    from tools.performance_preflight_successor import read_frozen_blobs

    freeze = FREEZE
    if freeze is None or len(freeze) != 40:
        raise ValueError("CI54 source freeze is pending.")
    _history(root, "merge-base", "--is-ancestor", BASE, freeze)
    git(root, "merge-base", "--is-ancestor", freeze, "HEAD")
    names = _history(root, "diff", "--name-only", BASE, freeze).decode().splitlines()
    if set(names) != PINS.keys() | {SELF, ASSESSMENT}:
        raise ValueError("CI54 finite source membership changed.")
    frozen = read_frozen_blobs(root, freeze, [SELF, ASSESSMENT, *PINS])
    marker = b"\nFREEZE: str | None = None"
    activated = frozen[SELF].replace(marker, f'\nFREEZE: str | None = "{freeze}"'.encode(), 1)
    if frozen[SELF].count(marker) != 1 or owned(root, SELF) != activated:
        raise ValueError("CI54 source activation changed.")
    for name, pin in PINS.items():
        if digest(frozen[name]) != pin or digest(owned(root, name)) != pin:
            raise ValueError("CI54 Preflight source changed: " + name)
    record: dict[str, Any] = json.loads(frozen[RECORD])
    if record.keys() != {"schema", "base", "changes"} or record["schema"] != "exact-ci-quality-v1":
        raise ValueError("CI54 transition schema changed.")
    before_pins = BEFORE | SNAPSHOT_BEFORE
    if BEFORE.keys() & SNAPSHOT_BEFORE.keys():
        raise ValueError("CI54 snapshot predecessor maps overlap.")
    if record["base"] != BASE or record["changes"].keys() != before_pins.keys() - {ASSESSMENT}:
        raise ValueError("CI54 transition membership changed.")
    originals = read_frozen_blobs(root, BASE, list(before_pins.keys() - {ASSESSMENT}))
    for name, row in record["changes"].items():
        before = originals[name]
        if (
            digest(before) != before_pins[name]
            or row["before_sha256"] != before_pins[name]
            or row["after_sha256"] != PINS[name]
            or row.keys() != {"before_sha256", "after_sha256", "edits"}
        ):
            raise ValueError("CI54 transition identity changed.")
        projected = before
        for edit in row["edits"]:
            if edit.keys() != {"before", "after"} or not all(
                isinstance(v, str) for v in edit.values()
            ):
                raise ValueError("CI54 transition edit is malformed.")
            old, new = edit["before"].encode(), edit["after"].encode()
            if projected.count(old) != 1:
                raise ValueError("CI54 transition lacks one exact preimage.")
            projected = projected.replace(old, new, 1)
        if projected != frozen[name]:
            raise ValueError("CI54 transition changed outside reviewed edits.")
    assessment: dict[str, Any] = json.loads(frozen[ASSESSMENT])
    row = assessment["changes"][SELF]
    row["after_sha256"] = digest(activated)
    row["owners"]["@module"]["after"] = owner_hashes(SELF, activated)["@module"]
    if json.loads(owned(root, ASSESSMENT)) != assessment:
        raise ValueError("CI54 assessment changed outside exact activation.")


def current_source(root: Path, previous_source: dict[str, str]) -> dict[str, str]:
    admit(root)
    return (
        previous_source
        | PINS
        | {
            SELF: digest(owned(root, SELF)),
            ASSESSMENT: digest(owned(root, ASSESSMENT)),
        }
    )


def measurement_inputs(root: Path, current: dict[str, str]) -> dict[str, str]:
    """Project only exact reviewed development controls, never engine/workload inputs."""
    admit(root)
    result = dict(current)
    for name in PINS.keys() | {SELF}:
        if name not in result:
            continue
        if result[name] != digest(owned(root, name)):
            raise ValueError("CI54 actual input collector omitted current control bytes.")
        if name in BEFORE | SNAPSHOT_BEFORE:
            result[name] = (BEFORE | SNAPSHOT_BEFORE)[name]
        else:
            del result[name]
    return result
