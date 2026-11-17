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
    if descriptor.get("schema") in {
        "historical-snapshot-linux-authority-profile-v1",
        "historical-snapshot-milli-inch-foundation-v1",
        "historical-snapshot-precision-profile-binding-v1",
        "historical-snapshot-milli-inch-symbolic-v1",
        "historical-snapshot-canonical-polygon-v1",
    }:
        current = json.loads((directory / "linux-authority-covered-baseline.json").read_bytes())
        values.update((current["source_head"], "e2d7a899d162cc1972d8a158fc02978e54301cc2"))
    if descriptor.get("schema") in {
        "historical-snapshot-milli-inch-foundation-v1",
        "historical-snapshot-precision-profile-binding-v1",
        "historical-snapshot-milli-inch-symbolic-v1",
        "historical-snapshot-canonical-polygon-v1",
    }:
        current = json.loads((directory / "milli-inch-covered-baseline.json").read_bytes())
        values.update((current["source_head"], "22f3fde616758008100bdf37d87edd671ed90d9a"))
    if descriptor.get("schema") in {
        "historical-snapshot-precision-profile-binding-v1",
        "historical-snapshot-milli-inch-symbolic-v1",
        "historical-snapshot-canonical-polygon-v1",
    }:
        current = json.loads((directory / "precision-profile-covered-baseline.json").read_bytes())
        values.update((current["source_head"], "13a8cad365b00fd9a96157dd029ee4db8121210f"))
    if descriptor.get("schema") in {
        "historical-snapshot-milli-inch-symbolic-v1",
        "historical-snapshot-canonical-polygon-v1",
    }:
        current = json.loads((directory / "symbolic-milli-inch-covered-baseline.json").read_bytes())
        values.update((current["source_head"], "fc52e9166ff6380b606269ce362f4f1cbc6a2835"))
    if descriptor.get("schema") == "historical-snapshot-canonical-polygon-v1":
        current = json.loads((directory / "canonical-polygon-covered-baseline.json").read_bytes())
        values.update((current["source_head"], "99dcf4adb983a0f968c536b16e9d960182e63afe"))
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
