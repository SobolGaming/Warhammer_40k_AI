"""Fetch only the exact Git objects named by retained scheduling evidence.

Stdlib-only bootstrap: usable before the job's Python environment is installed.
Missing objects stay errors in all validators; this step supplies their inputs.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def revisions(directory: Path) -> tuple[str, ...]:
    calibration = json.loads((directory / "hosted-calibration.json").read_bytes())
    scope = json.loads((directory / "allocation-scope.json").read_bytes())
    descriptor = json.loads((directory / "current-runtime-compatibility.json").read_bytes())
    baseline = json.loads((directory / "current-covered-baseline.json").read_bytes())
    native = json.loads((directory / "current-native-serial-role.json").read_bytes())
    sources = [row["source"] for row in calibration["reports"]] + [scope["source"]]
    values = {source[key] for source in sources for key in ("pr_head", "checkout")}
    values.update((descriptor["historical_revision"], baseline["source_head"]))
    values.update(
        native["observations"][context]["source_head"] for context in ("standalone", "with_mirror")
    )
    if any(
        not isinstance(value, str) or re.fullmatch("[0-9a-f]{40}", value) is None
        for value in values
    ):
        raise SystemExit("Scheduling sources must be exact full commit IDs.")
    return tuple(sorted(values))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    missing = [
        revision
        for revision in revisions(root / "ci/test_shards")
        if subprocess.run(
            ["git", "cat-file", "-e", revision + "^{commit}"],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        ).returncode
        != 0
    ]
    if missing:
        subprocess.run(
            [
                "git",
                "fetch",
                "--no-tags",
                "--no-recurse-submodules",
                "origin",
                *missing,
            ],
            cwd=root,
            check=True,
            timeout=120,
        )


if __name__ == "__main__":
    main()
