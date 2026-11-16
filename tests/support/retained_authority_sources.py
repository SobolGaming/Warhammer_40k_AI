"""Materialize reviewed source bytes as data for retained scheduling controls.

The snapshot is never added to sys.path. All Python validators and executable
entry points remain the current implementation; historical Python is not run.
"""

from __future__ import annotations

import io
import re
import subprocess
import tarfile
from pathlib import Path

from scripts.linux_authority_shard_admission import PREDECESSOR


def materialize_retained_sources(
    repository: Path, destination: Path, *, revision: str = PREDECESSOR
) -> None:
    if re.fullmatch("[0-9a-f]{40}", revision) is None:
        raise ValueError("A source snapshot requires an exact full Git commit ID.")
    if any(destination.iterdir()):
        raise ValueError("Retained source destination must be a new empty test directory.")
    git = ["git", "-c", f"safe.directory={repository.as_posix()}"]
    common = subprocess.check_output(
        [*git, "rev-parse", "--git-common-dir"], cwd=repository, text=True
    ).strip()
    objects = (repository / common).resolve() / "objects"
    subprocess.run(["git", "init", "--quiet", str(destination)], check=True, timeout=30)
    subprocess.run(
        ["git", "config", "core.autocrlf", "false"], cwd=destination, check=True, timeout=30
    )
    subprocess.run(
        ["git", "config", "core.longpaths", "true"], cwd=destination, check=True, timeout=30
    )
    metadata = destination / ".git"
    (metadata / "objects/info/alternates").write_text(
        objects.as_posix() + "\n", encoding="utf-8", newline="\n"
    )
    (metadata / "HEAD").write_text(revision + "\n", encoding="ascii", newline="\n")
    subprocess.run(["git", "read-tree", revision], cwd=destination, check=True, timeout=30)
    archive = subprocess.check_output(
        [
            *git,
            "archive",
            revision,
            "src",
            "tests",
            "scripts",
            "tools",
            "contracts/schemas",
            "pyproject.toml",
            "uv.lock",
            "docs/performance/policy-v3/operation-map.json",
            "ci/test_shards",
            ".gitignore",
            ".gitattributes",
            ".github/workflows/ci.yml",
            "data/source_snapshots/wahapedia/10th-edition/2026-06-14/json",
            "data/source_overlays",
            "data/source_audits/ci64_provenance_v1",
            "docs/performance/policy-v3/acts-provenance-20261031",
            "data/army_lists/cavalcade-shadow-bloodthirster.json",
        ],
        cwd=repository,
        timeout=60,
    )
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        stream.extractall(destination, filter="data")
