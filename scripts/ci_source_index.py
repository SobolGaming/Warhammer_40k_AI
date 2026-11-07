"""Overlap cold index construction with pytest startup, never with test execution."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import pytest

SCHEMA = "selected-source-index-completion-v1"
_KEY_PREFIX = "selected-source-index-v1-"


def validate_input_key(value: str) -> None:
    digest = value.removeprefix(_KEY_PREFIX)
    if (
        not value.startswith(_KEY_PREFIX)
        or len(digest) != 64
        or set(digest) - set("0123456789abcdef")
    ):
        raise pytest.UsageError("Invalid selected-source input identity.")


@dataclass(frozen=True, slots=True)
class BuildGate:
    result: Path
    index: Path
    input_key: str
    deadline: float

    def wait(self) -> None:
        validate_input_key(self.input_key)
        if not math.isfinite(self.deadline):
            raise pytest.UsageError("Source-index completion deadline must be finite.")
        remaining = self.deadline - time.time()
        stop = time.monotonic() + max(0.0, remaining)
        while not self.result.is_file():
            if time.monotonic() >= stop:
                raise pytest.UsageError(
                    "Source-index construction did not complete before deadline."
                )
            time.sleep(min(0.05, max(0.0, stop - time.monotonic())))
        try:
            payload: object = json.loads(self.result.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise pytest.UsageError("Cannot read source-index completion: " + str(error)) from error
        if not isinstance(payload, dict):
            raise pytest.UsageError("Malformed source-index completion record.")
        record = cast(dict[str, object], payload)
        if set(record) != {
            "schema",
            "index",
            "input_key",
            "exit_code",
        }:
            raise pytest.UsageError("Malformed source-index completion record.")
        if (
            record["schema"] != SCHEMA
            or record["index"] != str(self.index.resolve())
            or record["input_key"] != self.input_key
            or type(record["exit_code"]) is not int
        ):
            raise pytest.UsageError("Stale or invalid source-index completion record.")
        if record["exit_code"] != 0:
            raise pytest.UsageError(
                f"Source-index construction failed with exit code {record['exit_code']}."
            )
        if time.monotonic() >= stop:
            raise pytest.UsageError("Source-index completion exceeded the setup/test deadline.")


def build(source: Path, index: Path, result: Path, input_key: str) -> int:
    validate_input_key(input_key)
    if result.exists() or result.with_suffix(".tmp").exists():
        raise ValueError("Source-index completion requires a fresh result path.")
    command = [sys.executable, "-B", "-m", "tools.ability_support_sources", str(source), str(index)]
    status = subprocess.run(command, check=False).returncode
    payload = {
        "schema": SCHEMA,
        "index": str(index.resolve()),
        "input_key": input_key,
        "exit_code": status,
    }
    temporary = result.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    temporary.replace(result)
    if status == 0 and "GITHUB_OUTPUT" in os.environ:
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write("source_index_built=true\n")
    return status


_GATE: pytest.StashKey[BuildGate] = pytest.StashKey()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("source-index construction barrier")
    group.addoption("--ci-source-index-result", type=Path)
    group.addoption("--ci-source-index-target", type=Path)
    group.addoption("--ci-source-index-key")
    group.addoption("--ci-source-index-deadline", type=float)


def pytest_configure(config: pytest.Config) -> None:
    values = tuple(
        config.getoption("ci_source_index_" + name)
        for name in ("result", "target", "key", "deadline")
    )
    if all(value is None for value in values):
        return  # The plugin is optional for warm-cache and ordinary local invocations.
    if any(value is None for value in values):
        raise pytest.UsageError("All four source-index barrier options are required together.")
    result, index, input_key, deadline = values
    if (
        not isinstance(result, Path)
        or not isinstance(index, Path)
        or not isinstance(input_key, str)
    ):
        raise pytest.UsageError("Invalid source-index barrier configuration.")
    validate_input_key(input_key)
    if type(deadline) is not float or not math.isfinite(deadline):
        raise pytest.UsageError("Source-index completion deadline must be finite.")
    config.stash[_GATE] = BuildGate(result, index, input_key, deadline)


class CollectionNode(Protocol):
    config: pytest.Config


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node: CollectionNode) -> None:
    # xdist invokes this before admitting the collection to its scheduler.
    if _GATE in node.config.stash:
        node.config.stash[_GATE].wait()


def pytest_collection_finish(session: pytest.Session) -> None:
    # Workers report collection to the controller; only the controller owns the gate.
    if not hasattr(session.config, "workerinput") and _GATE in session.config.stash:
        session.config.stash[_GATE].wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("index", type=Path)
    parser.add_argument("result", type=Path)
    parser.add_argument("input_key")
    args = parser.parse_args()
    raise SystemExit(
        build(
            cast(Path, args.source),
            cast(Path, args.index),
            cast(Path, args.result),
            cast(str, args.input_key),
        )
    )


if __name__ == "__main__":
    main()
