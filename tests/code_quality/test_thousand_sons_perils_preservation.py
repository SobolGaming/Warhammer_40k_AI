"""Exact perils continuation admission cannot discard preceding assertions or controls."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from tools import cumulative_preservation as cumulative
from tools import thousand_sons_perils_preservation as perils

ROOT = Path(__file__).resolve().parents[2]


def test_perils_successor_preserves_complete_source_and_original_test_bytes() -> None:
    assert len(cumulative.verify_live(ROOT)) == 64
    original = subprocess.check_output(["git", "show", perils.BASE + ":" + perils.TEST], cwd=ROOT)
    current = (ROOT / perils.TEST).read_bytes()
    assert perils.preceding_test(ROOT, perils.TEST, current) == original
    for name in (perils.STAGE, perils.CUMULATIVE):
        assert perils.preceding_control(ROOT, name, (ROOT / name).read_bytes()) == (
            subprocess.check_output(["git", "show", perils.BASE + ":" + name], cwd=ROOT)
        )


@pytest.fixture(scope="module")
def source_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("perils-exact-successor")
    shutil.copytree(
        ROOT,
        root,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(".git", "reports", "__pycache__", ".pytest_cache"),
    )
    git_dir = (
        subprocess.check_output(["git", "rev-parse", "--absolute-git-dir"], cwd=ROOT)
        .decode()
        .strip()
    )
    (root / ".git").write_text("gitdir: " + git_dir + "\n")
    return root


@pytest.mark.parametrize("kind", ["assertion", "rng", "continuation", "control", "blind_repin"])
def test_perils_successor_rejects_source_drift_and_blind_repins(
    source_copy: Path, kind: str
) -> None:
    name = (
        perils.STAGE if kind == "control" else perils.SELF if kind == "blind_repin" else perils.TEST
    )
    path = source_copy / name
    before = path.read_bytes()
    if kind == "assertion":
        changed = before.replace(b"final in {-1, -2}", b"final in {0, -1, -2}", 1)
    elif kind == "rng":
        changed = before.replace(b"twist-a:d07:324", b"twist-a:d07:325", 1)
    elif kind == "continuation":
        changed = before.replace(
            b'remaining_mortal_wounds"] == 2', b'remaining_mortal_wounds"] == 0', 1
        )
    elif kind == "blind_repin":
        changed = before.replace(perils.AFTER.encode(), b"0" * 64, 1)
    else:
        changed = before + b"\n# unreviewed control mutation\n"
    assert changed != before
    try:
        path.write_bytes(changed)
        with pytest.raises(ValueError, match="Perils successor"):
            cumulative.verify_live(source_copy)
    finally:
        path.write_bytes(before)
