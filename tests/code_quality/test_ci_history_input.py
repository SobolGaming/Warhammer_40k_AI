"""Provision original historical inputs without changing any validation gate."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest
from tools import performance_category_migration as legacy
from tools import performance_policy as policy
from tools import performance_preflight_successor as stage
from tools import performance_reconstruction_campaign as reconstruction
from tools import performance_tool_inputs as original_inputs

from tests import d07_geometry_containment as geometry
from tests.code_quality.tool_input_history import REVISION as ARCHIVAL_REVISION

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ".github/workflows/ci.yml"
PREDECESSOR = "f69b0702882cfe055044dd002890e7e94383adcc"
WORKFLOW_BEFORE_SHA256 = "8e49742d623a6f595dc5190c98258143fe5260d59a7e7662f323f4b5c8349660"
ANCHOR = "4a8fb3c10cbf9c6ce1766f048508b8a16f8f24e8"
SCRIPT = "scripts/check_performance_policy.py"
SCRIPT_SHA256 = "520da31556b55271ce74af77e553281d5974e6faf9b8baf23bcd8b5a76605b12"
SNAPSHOTS = (
    (
        "4a8fb3c10cbf9c6ce1766f048508b8a16f8f24e8",
        "fd5cd25b37a4f10ef32090a4552e6fbe11afa0446c91e9f29fdb7a320bc37667",
        "10c18ec612cc281238d2a996ab7c889e30950aaf",
    ),
    (
        "1009fd82e077239abf854e9179d87b0affe8186e",
        "f412c78c01877e55343ff1c095f4af82d4334c8e1a67cce4cf1d3e020376c651",
        "835e7db740719dc7a6d0feeea8106f00bc286cc8",
    ),
    (
        "1e70b261b30223f3a1b2e64ffd81593414eda2af",
        "6fd8dfb04597677cf93ccb0a58def06838e2aedd52d4d6c1a80e63e4c3e171b3",
        "a96ee54373b24bc78642fa8987e7bd94aadb980b",
    ),
    (
        "241f413ce9b83586d0aff4fd87ce50f8157c0163",
        "46312b4f7025d9c161ac8299d28e5e62d770148d9dc7c767b8dac877d25c2021",
        "c5c4ebc8a211888e6ed76594bd4cd48907368240",
    ),
    (
        "40a727563355ecd29cc981ad141dd194a5690a99",
        "ca21c51399093290f6887914c7a943872ca2df38dd4bc053bfde2d2b915bba8c",
        "e32ab69ddefbf59f317d7af648195624a98589f8",
    ),
)

FETCH_STEP = (
    "      - name: Fetch original historical validation inputs\n"
    "        run: git fetch --no-tags --no-recurse-submodules origin " + ANCHOR + "\n\n"
)


def test_history_fetch_is_the_only_workflow_change_before_validation() -> None:
    before = subprocess.check_output(["git", "show", PREDECESSOR + ":" + WORKFLOW], cwd=ROOT)
    assert hashlib.sha256(before).hexdigest() == WORKFLOW_BEFORE_SHA256
    assert legacy.SOURCE_COMMIT == ANCHOR
    start, quality = before.decode().split("  code-quality:\n", 1)
    checkout = "          fetch-depth: 0\n\n"
    assert quality.count(checkout) == 1
    expected = start + "  code-quality:\n" + quality.replace(checkout, checkout + FETCH_STEP, 1)
    quality_step = "      - name: Code-quality tests\n        env:"
    assert expected.count(quality_step) == 1
    expected = expected.replace(
        quality_step,
        "      - name: Code-quality tests\n        timeout-minutes: 10\n        env:",
        1,
    )
    current = (ROOT / WORKFLOW).read_text()
    assert current == expected
    lane = current.split("  code-quality:\n", 1)[1].split("  semantic-audit-macos:\n", 1)[0]
    assert lane.index(FETCH_STEP) < lane.index("scripts.check_performance_policy")
    assert lane.index("scripts.check_performance_policy") < lane.index("pytest tests/code_quality")


def test_workflow_is_a_live_pinned_source_even_though_not_a_measured_runtime_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = (ROOT / WORKFLOW).read_bytes()
    assert stage.PINS[WORKFLOW] == hashlib.sha256(current).hexdigest()
    assert WORKFLOW not in policy.runtime_inputs(ROOT)
    before = subprocess.check_output(["git", "show", stage.BASE + ":" + WORKFLOW], cwd=ROOT)
    assert stage.preceding_control(ROOT, WORKFLOW, current) == before
    original = geometry.read_owned_geometry_member

    def changed_read(root: Path, name: str) -> bytes:
        raw = original(root, name)
        return raw + b"# unreviewed workflow change\n" if name == WORKFLOW else raw

    monkeypatch.setattr(geometry, "read_owned_geometry_member", changed_read)
    with pytest.raises(ValueError, match="Preflight source"):
        stage.preceding_control(ROOT, WORKFLOW, current)


def test_missing_original_commit_fails_and_exact_original_object_restores_lookup(
    tmp_path: Path,
) -> None:
    def original(*args: str) -> bytes:
        return subprocess.check_output(["git", *args], cwd=ROOT, timeout=10)

    def local(*args: str, payload: bytes | None = None) -> bytes:
        return subprocess.check_output(["git", *args], cwd=tmp_path, input=payload, timeout=10)

    local("init", "--bare", "--quiet")
    for expression, kind in (
        (ANCHOR + "^{tree}", "tree"),
        (ANCHOR + ":scripts", "tree"),
        (ANCHOR + ":" + SCRIPT, "blob"),
    ):
        oid = original("rev-parse", expression).decode().strip()
        raw = original("cat-file", kind, oid)
        assert (
            local("hash-object", "-w", "-t", kind, "--stdin", payload=raw).decode().strip() == oid
        )
    missing = subprocess.run(
        ["git", "show", ANCHOR + ":" + SCRIPT],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert missing.returncode == 128
    assert missing.stdout == b""
    origin = tmp_path / "unavailable-origin.git"
    origin.mkdir()
    subprocess.run(["git", "init", "--bare", "--quiet"], cwd=origin, check=True)
    local("remote", "add", "origin", str(origin))
    unavailable_fetch = subprocess.run(
        ["git", "fetch", "--no-tags", "--no-recurse-submodules", "origin", ANCHOR],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert unavailable_fetch.returncode != 0
    still_missing = subprocess.run(
        ["git", "cat-file", "-e", ANCHOR],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert still_missing.returncode != 0
    other_revision = "1009fd82e077239abf854e9179d87b0affe8186e"
    other_commit = original("cat-file", "commit", other_revision)
    stored = local("hash-object", "-w", "-t", "commit", "--stdin", payload=other_commit)
    assert stored.decode().strip() == other_revision
    assert other_revision != ANCHOR
    mismatched = subprocess.run(
        ["git", "show", ANCHOR + ":" + SCRIPT],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert mismatched.returncode == 128
    assert mismatched.stdout == b""
    commit = original("cat-file", "commit", ANCHOR)
    assert (
        local("hash-object", "-w", "-t", "commit", "--stdin", payload=commit).decode().strip()
        == ANCHOR
    )
    assert local("cat-file", "commit", ANCHOR) == commit
    restored = local("show", ANCHOR + ":" + SCRIPT)
    assert restored == original("show", ANCHOR + ":" + SCRIPT)
    assert hashlib.sha256(restored).hexdigest() == SCRIPT_SHA256


def test_all_five_original_snapshot_identities_and_ancestry_are_available() -> None:
    assert {revision for revision, _, _ in SNAPSHOTS} == {
        legacy.SOURCE_COMMIT,
        original_inputs.MEASURED_HEAD,
        reconstruction.MEASURED,
        legacy.MEASURED,
        ARCHIVAL_REVISION,
    }
    for revision, expected_digest, expected_tree in SNAPSHOTS:
        raw = subprocess.check_output(["git", "cat-file", "commit", revision], cwd=ROOT)
        assert hashlib.sha256(raw).hexdigest() == expected_digest
        oid = (
            subprocess.check_output(
                ["git", "hash-object", "-t", "commit", "--stdin"], cwd=ROOT, input=raw
            )
            .decode()
            .strip()
        )
        assert oid == revision
        tree = (
            subprocess.check_output(["git", "rev-parse", revision + "^{tree}"], cwd=ROOT)
            .decode()
            .strip()
        )
        assert tree == expected_tree
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, ANCHOR], cwd=ROOT, check=True
        )
