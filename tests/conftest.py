from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
repository_root_path = str(REPOSITORY_ROOT)
if repository_root_path not in sys.path:
    sys.path.insert(0, repository_root_path)

if TYPE_CHECKING:
    from scripts.build_test_shards import BehavioralSelection


def _tree_stat_fingerprint(selection: BehavioralSelection) -> tuple[tuple[str, int, int], ...]:
    from scripts.build_test_shards import CUTOVER_PATH

    tracked_paths = (
        CUTOVER_PATH,
        *selection.active_files,
        *(name for name in selection.inactive_files if (REPOSITORY_ROOT / name).exists()),
        *selection.quality_files,
        *selection.benchmark_files,
    )
    entries: list[tuple[str, int, int]] = []
    for relative in tracked_paths:
        stat_result = (REPOSITORY_ROOT / relative).lstat()
        entries.append((relative, stat_result.st_mtime_ns, stat_result.st_size))
    return tuple(entries)


def _read_selection() -> BehavioralSelection:
    from scripts.build_test_shards import behavioral_selection

    return behavioral_selection(REPOSITORY_ROOT)


_selection = _read_selection()
_selection_stat = _tree_stat_fingerprint(_selection)
collect_ignore = [name.removeprefix("tests/") for name in _selection.inactive_files]
_selection_key: pytest.StashKey[BehavioralSelection] = pytest.StashKey()

pytest_plugins = ("tests.timing_plugin",)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--selected-army-source-index",
        type=Path,
        default=None,
        help="Reuse an explicitly built source index in opted-in selected-army kernels.",
    )


def _auto_local_source_index(pytestconfig: pytest.Config) -> Path:
    from filelock import FileLock
    from tools.ability_support_sources import (
        ability_support_index_inputs,
        load_ability_support_sources,
    )
    from tools.generate_ability_support_matrix import DEFAULT_SOURCE_JSON_DIR

    from warhammer40k_core.rules.selected_source_index import (
        build_selected_source_index,
        source_input_hashes,
    )

    source = REPOSITORY_ROOT / DEFAULT_SOURCE_JSON_DIR
    input_files = ability_support_index_inputs(source)
    identity = {"python": sys.version, "inputs": source_input_hashes(input_files)}
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cache_base = Path(pytestconfig.cache._cachedir) / "selected-source-index"  # pyright: ignore[reportPrivateUsage]
    cache_base.mkdir(parents=True, exist_ok=True)
    target = cache_base / f"selected-source-index-v1-{digest}"
    marker = target / ".complete-v1"
    lock = cache_base / f"selected-source-index-v1-{digest}.lock"
    with FileLock(str(lock), timeout=600):
        if marker.is_file():
            return target
        staging = cache_base / f"staging-{os.getpid()}-{uuid.uuid4().hex}"
        build_selected_source_index(
            staging,
            input_files=input_files,
            load_sources=lambda: load_ability_support_sources(source),
        )
        (staging / ".complete-v1").write_text(digest + "\n", encoding="utf-8")
        if target.exists():
            shutil.rmtree(target)
        staging.replace(target)
    return target


@pytest.fixture(scope="session")
def selected_army_source_index(pytestconfig: pytest.Config) -> Path | None:
    value = pytestconfig.getoption("selected_army_source_index")
    if value is not None:
        if not isinstance(value, Path):
            raise TypeError("Selected-army source index option must be a path.")
        return value
    if os.environ.get("WH40K_DISABLE_AUTO_SOURCE_INDEX") == "1":
        return None
    return _auto_local_source_index(pytestconfig)


def _configured_selection(config: pytest.Config) -> BehavioralSelection:
    if config.getini("python_files") != ["test_*.py"]:
        raise SystemExit("Effective pytest python_files must equal ['test_*.py'].")
    try:
        unchanged = _tree_stat_fingerprint(_selection) == _selection_stat
    except OSError:
        unchanged = False
    selection = _selection if unchanged else _read_selection()
    if selection != _selection:
        raise SystemExit("Selection changed between conftest import and configuration.")
    selection.check_explicit(REPOSITORY_ROOT, tuple(config.args))
    return selection


def pytest_configure(config: pytest.Config) -> None:
    try:
        config.stash[_selection_key] = _configured_selection(config)
    except (SystemExit, OSError, ValueError) as error:
        raise pytest.UsageError("Finite test cutover admission failed: " + str(error)) from error


def _explicit_benchmark(config: pytest.Config) -> bool:
    for argument in config.args:
        path = Path(argument.split("::", 1)[0])
        path = path if path.is_absolute() else REPOSITORY_ROOT / path
        if path.is_relative_to(REPOSITORY_ROOT / "tests/benchmarks"):
            return True
    return False


class SchedulerWorker(Protocol):
    config: pytest.Config
    workerinput: dict[str, object]


@pytest.hookimpl(optionalhook=True)
def pytest_configure_node(node: SchedulerWorker) -> None:
    # xdist resets worker config.option.dist to "no" before collection.
    node.workerinput["s25_scheduler"] = node.config.getoption("dist")


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # Built-in -k/-m/--deselect filtering must finish before sizing worker chunks.
    worker_input = cast(dict[str, object], getattr(config, "workerinput", {}))
    if worker_input.get("s25_scheduler") != "worksteal":
        return
    raw_workers = os.environ.get("PYTEST_XDIST_WORKER_COUNT", "")
    if not raw_workers.isdecimal():
        return
    workers = int(raw_workers)
    if workers < 2:
        return
    shard_id = os.environ.get("SHARD_ID")
    explicit_profile = os.environ.get("BEHAVIORAL_DISPATCH_PROFILE")
    default_profile = REPOSITORY_ROOT / "ci/test_shards/durations.json"
    if not shard_id and explicit_profile is None and not default_profile.is_file():
        return

    from scripts.build_test_shards import (
        dispatch_case_seconds,
        duration_worksteal_order,
        summary_case_seconds,
        worksteal_relevance_order,
    )

    order = worksteal_relevance_order(tuple(item.nodeid for item in items), workers=workers)
    if shard_id or explicit_profile is not None:
        if explicit_profile is not None:
            profile_path = Path(explicit_profile)
            summary = json.loads(profile_path.read_text(encoding="utf-8"))
            selector_seconds = dispatch_case_seconds(summary, profile_path)
            weighted = duration_worksteal_order(
                tuple(items[index].nodeid for index in order),
                workers=workers,
                selector_seconds=selector_seconds,
            )
            order = tuple(order[index] for index in weighted)
    elif len(items) >= 2 * workers and default_profile.is_file():
        default_summary: object = json.loads(default_profile.read_text(encoding="utf-8"))
        if isinstance(default_summary, dict) and "case_seconds" in default_summary:
            selector_seconds = summary_case_seconds(cast(object, default_summary))
            ordered_nodes = tuple(items[index].nodeid for index in order)
            if all(
                node in selector_seconds or node.split("::", 1)[0] in selector_seconds
                for node in ordered_nodes
            ):
                weighted = duration_worksteal_order(
                    ordered_nodes,
                    workers=workers,
                    selector_seconds=selector_seconds,
                )
                order = tuple(order[index] for index in weighted)
    items[:] = [items[index] for index in order]


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    if collection_path.is_relative_to(
        REPOSITORY_ROOT / "tests/benchmarks"
    ) and not _explicit_benchmark(config):
        return True
    return None


def pytest_collect_file(file_path: Path, parent: pytest.Collector) -> None:
    if file_path.name.startswith("test_") and file_path.suffix == ".py":
        try:
            parent.config.stash[_selection_key].check_explicit(REPOSITORY_ROOT, (str(file_path),))
        except (SystemExit, OSError, ValueError) as error:
            raise pytest.UsageError(str(error)) from error
