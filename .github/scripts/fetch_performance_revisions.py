"""Fetch exact measured commits needed by the current performance assessment."""

import json
import re
import subprocess
from pathlib import PurePosixPath

ASSESSMENT = "docs/performance/change-assessment.json"
CURRENT = PurePosixPath("docs/performance/current")


def main() -> None:
    assessment = json.loads(subprocess.check_output(["git", "show", f"HEAD:{ASSESSMENT}"]))
    revisions: set[str] = set()
    for path in assessment["comparisons"].values():
        member = PurePosixPath(path)
        if CURRENT not in member.parents or ".." in member.parts:
            raise ValueError(f"Invalid current comparison path: {path!r}")
        report = json.loads(subprocess.check_output(["git", "show", f"HEAD:{path}"]))
        binding = report.get("input_binding")
        if binding is None or binding["schema"] != "tool-input-roles-v4":
            continue
        revision = binding["sides"]["head"]["revision"]
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError(f"Expected a full measured commit ID in {path}.")
        revisions.add(revision)

    for revision in sorted(revisions):
        command = ["git", "cat-file", "-t", revision]
        local = subprocess.run(command, capture_output=True, check=False)
        kind = local.stdout
        if local.returncode != 0:
            # GitHub retains the source history under the PR head after squash.
            subprocess.run(
                [
                    "git",
                    "fetch",
                    "--no-tags",
                    "--no-recurse-submodules",
                    "origin",
                    revision,
                ],
                check=True,
            )
            kind = subprocess.check_output(command)
        if kind.strip() != b"commit":
            raise ValueError(f"Measured revision {revision} must be a Git commit.")


if __name__ == "__main__":
    main()
