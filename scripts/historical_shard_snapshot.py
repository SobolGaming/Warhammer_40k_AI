"""Authenticate retained scheduling evidence in its original source snapshot.

Only data and test source are materialized. Historical Python is never imported
or executed. The current validators retain their strict runtime/inventory checks.
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from scripts.hosted_timing_calibration import load_planning_seconds, read_json
from scripts.scoped_shard_evidence import ScopedEvidence, load_declared_scope
from scripts.shard_execution_model import Cohort, load_cohorts

HISTORICAL_REVISION = "008be8a8cb0b50b232fe022452762b3906489b49"
MANIFEST = "src/warhammer40k_core/_engine_build_manifest.json"


def git_bytes(root: Path, revision: str, path: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "show", revision + ":" + path], cwd=root, stderr=subprocess.PIPE, timeout=30
        )
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            "Required scheduling source object is unavailable: "
            + revision
            + ":"
            + path
            + ". Fetch that exact revision; historical receipts must not be relabeled."
        ) from error


def fingerprint(root: Path, revision: str) -> str:
    return cast(str, json.loads(git_bytes(root, revision, MANIFEST))["fingerprint"])


def authenticate_producers(root: Path, directory: Path) -> None:
    calibration = cast(dict[str, object], read_json(directory / "hosted-calibration.json"))
    sources = [
        cast(dict[str, object], row["source"])
        for row in cast(list[dict[str, object]], calibration["reports"])
    ]
    scope = cast(dict[str, object], read_json(directory / "allocation-scope.json"))
    sources.append(cast(dict[str, object], scope["source"]))
    checked: dict[str, str] = {}
    for source in sources:
        for key in ("pr_head", "checkout"):
            revision = cast(str, source[key])
            if revision not in checked:
                checked[revision] = fingerprint(root, revision)
            if checked[revision] != source["runtime_fingerprint"]:
                raise SystemExit("Historical producer runtime fingerprint differs from Git.")
    extension = cast(dict[str, object], read_json(directory / "scoped-worker-extension.json"))
    binding = cast(dict[str, object], extension["merge_binding"])
    source = cast(dict[str, object], extension["source"])
    try:
        tree = (
            subprocess.check_output(
                ["git", "rev-parse", cast(str, source["checkout"]) + "^{tree}"], cwd=root
            )
            .decode()
            .strip()
        )
        commit = subprocess.check_output(
            ["git", "cat-file", "-p", cast(str, source["checkout"])], cwd=root
        ).decode()
        parents = [
            line.split()[1]
            for line in commit.split("\n\n", 1)[0].splitlines()
            if line.startswith("parent ")
        ]
    except subprocess.CalledProcessError as error:
        raise SystemExit("Historical tested merge object is unavailable.") from error
    if tree != binding["tested_tree"] or parents != binding["parents"]:
        raise SystemExit("Historical tested merge tree or parents differ from Git.")


@dataclass(frozen=True)
class HistoricalSnapshot:
    root: Path
    directory: Path
    baseline: dict[str, float]
    dispatch: dict[str, float]
    cohorts: tuple[Cohort, ...]
    scope: ScopedEvidence
    groups: tuple[tuple[str, ...], ...]


@contextmanager
def historical_snapshot(root: Path) -> Iterator[HistoricalSnapshot]:
    """Validate the pinned evidence with today's validators and original inputs."""
    from scripts.build_test_shards import summary_case_seconds

    try:
        archive = subprocess.check_output(
            ["git", "archive", HISTORICAL_REVISION, "ci/test_shards", "tests", MANIFEST],
            cwd=root,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as error:
        raise SystemExit("Exact historical scheduling snapshot is unavailable.") from error
    with TemporaryDirectory(prefix="historical-shard-data-") as scratch:
        snapshot = Path(scratch)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(snapshot, filter="data")
        directory = snapshot / "ci/test_shards"
        authenticate_producers(root, directory)
        summary = read_json(directory / "durations.json")
        baseline = summary_case_seconds(summary)
        dispatch, _ = load_planning_seconds(
            directory / "hosted-calibration.json", baseline=baseline, root=snapshot
        )
        cohorts = load_cohorts(directory, root=snapshot, nodes=set(baseline))
        scope = load_declared_scope(directory, root=snapshot, costs=dispatch)
        if scope is None or scope.extension is None:
            raise SystemExit("Historical scheduling snapshot lacks its reviewed scope.")
        groups = tuple(
            tuple((directory / f"shard-{index}.txt").read_text().splitlines())
            for index in range(1, 13)
        )
        yield HistoricalSnapshot(snapshot, directory, baseline, dispatch, cohorts, scope, groups)


def unchanged_historical_files(directory: Path, snapshot: HistoricalSnapshot) -> None:
    """Live receipts remain byte-identical; only derived manifests may change."""
    for path in snapshot.directory.iterdir():
        if path.name == "durations.json" or path.name.startswith("shard-"):
            continue
        live = directory / path.name
        if (
            not live.is_file()
            or hashlib.sha256(live.read_bytes()).digest()
            != hashlib.sha256(path.read_bytes()).digest()
        ):
            raise SystemExit("Retained historical scheduling evidence changed: " + path.name)
