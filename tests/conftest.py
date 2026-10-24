from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
repository_root_path = str(REPOSITORY_ROOT)
if repository_root_path not in sys.path:
    sys.path.insert(0, repository_root_path)

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
