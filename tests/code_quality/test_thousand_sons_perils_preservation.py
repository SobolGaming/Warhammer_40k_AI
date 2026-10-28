"""Exact perils continuation admission cannot discard preceding assertions or controls."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from tools import cumulative_preservation as cumulative
from tools import thousand_sons_perils_preservation as perils

ROOT = Path(__file__).resolve().parents[2]


def _copy_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = set(
        shutil.ignore_patterns(".git", "reports", "__pycache__", ".pytest_cache")(directory, names)
    )
    if Path(directory) == ROOT and ".venv" in names:
        if any(
            name in os.environ
            for name in (
                "GIT_DIR",
                "GIT_WORK_TREE",
                "GIT_COMMON_DIR",
                "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY",
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_NAMESPACE",
                "GIT_CONFIG",
                "GIT_CONFIG_COUNT",
                "GIT_CONFIG_PARAMETERS",
                "GIT_CONFIG_GLOBAL",
                "GIT_CONFIG_SYSTEM",
                "GIT_REPLACE_REF_BASE",
            )
        ):
            raise ValueError("Root environment ownership refuses redirected Git roles.")
        environment = ROOT / ".venv"
        first = environment.lstat()
        if (
            environment.is_symlink()
            or environment.is_junction()
            or environment.resolve(strict=True) != environment
        ):
            raise ValueError("Root environment must not be an alias.")
        command = [
            "git",
            "--literal-pathspecs",
            "--work-tree=" + str(ROOT),
            "ls-files",
            "--with-tree=HEAD",
            "--error-unmatch",
            "-z",
            "--",
            ".venv",
        ]
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.DEVNULL, timeout=30)
        if result.returncode == 0:
            raise ValueError("Tracked root environment must not be omitted.")
        if result.returncode != 1:
            raise subprocess.CalledProcessError(result.returncode, command)
        second = environment.lstat()
        if (
            (first.st_dev, first.st_ino, first.st_mode)
            != (second.st_dev, second.st_ino, second.st_mode)
            or environment.is_symlink()
            or environment.is_junction()
            or environment.resolve(strict=True) != environment
        ):
            raise ValueError("Root environment identity changed during ownership admission.")
        if environment.is_dir():
            ignored.add(".venv")
    return ignored


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
        ignore=_copy_ignore,
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


def test_root_environment_copy_filter_preserves_owned_and_nested_sources(tmp_path: Path) -> None:
    source, copied = tmp_path / "source", tmp_path / "copied"
    environment = source / ".venv" / "environment.py"
    nested = source / "data" / ".venv" / "owned.py"
    ordinary = source / "src" / "owned.py"
    for path, raw in (
        (environment, b"ENV = 1\n"),
        (nested, b"NESTED = 1\n"),
        (ordinary, b"OWNED = 1\n"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(
        ["git", "add", "-f", "data/.venv/owned.py", "src/owned.py"], cwd=source, check=True
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=quality-control",
            "-c",
            "user.email=quality-control@example.invalid",
            "commit",
            "-qm",
            "owned nested fixture",
        ],
        cwd=source,
        check=True,
    )
    with pytest.MonkeyPatch.context() as private:
        private.setitem(globals(), "ROOT", source)
        shutil.copytree(source, copied, ignore=_copy_ignore)
        assert not (copied / ".venv").exists()
        assert (copied / "data/.venv/owned.py").read_bytes() == nested.read_bytes()
        assert (copied / "src/owned.py").read_bytes() == ordinary.read_bytes()
        subprocess.run(["git", "add", "-f", ".venv/environment.py"], cwd=source, check=True)
        with pytest.raises(ValueError, match="Tracked root environment"):
            _copy_ignore(str(source), [".venv"])
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=quality-control",
                "-c",
                "user.email=quality-control@example.invalid",
                "commit",
                "-qm",
                "owned root fixture",
            ],
            cwd=source,
            check=True,
        )
        subprocess.run(["git", "rm", "--cached", "-qr", ".venv"], cwd=source, check=True)
        with pytest.raises(ValueError, match="Tracked root environment"):
            _copy_ignore(str(source), [".venv"])
        with pytest.MonkeyPatch.context() as redirected:
            redirected.setenv("GIT_INDEX_FILE", str(tmp_path / "unrelated-index"))
            with pytest.raises(ValueError, match="redirected Git roles"):
                _copy_ignore(str(source), [".venv"])
    alias_root = tmp_path / "alias-source"
    alias_root.mkdir()
    (alias_root / ".venv").symlink_to(environment.parent, target_is_directory=True)
    subprocess.run(["git", "init", "-q"], cwd=alias_root, check=True)
    subprocess.run(["git", "add", "-f", ".venv"], cwd=alias_root, check=True)
    assert subprocess.check_output(
        ["git", "ls-files", "--stage", "--", ".venv"], cwd=alias_root
    ).startswith(b"120000")
    with pytest.MonkeyPatch.context() as private:
        private.setitem(globals(), "ROOT", alias_root)
        with pytest.raises(ValueError, match="must not be an alias"):
            _copy_ignore(str(alias_root), [".venv"])
