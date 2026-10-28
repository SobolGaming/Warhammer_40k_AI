from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
repository_root_path = str(REPOSITORY_ROOT)
if repository_root_path not in sys.path:
    sys.path.insert(0, repository_root_path)

if TYPE_CHECKING:
    from scripts.build_test_shards import BehavioralSelection


def _read_selection() -> BehavioralSelection:
    from scripts.build_test_shards import behavioral_selection

    return behavioral_selection(REPOSITORY_ROOT)


_selection = _read_selection()
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


@pytest.fixture(scope="session")
def selected_army_source_index(pytestconfig: pytest.Config) -> Path | None:
    value = pytestconfig.getoption("selected_army_source_index")
    if value is not None and not isinstance(value, Path):
        raise TypeError("Selected-army source index option must be a path.")
    return value


def _configured_selection(config: pytest.Config) -> BehavioralSelection:
    if config.getini("python_files") != ["test_*.py"]:
        raise SystemExit("Effective pytest python_files must equal ['test_*.py'].")
    selection = _read_selection()
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
