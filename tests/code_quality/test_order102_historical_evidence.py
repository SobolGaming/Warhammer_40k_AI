"""The original Order97 assertions stay pinned while current tests still execute."""

import hashlib
import json
from pathlib import Path

import pytest
from tools.core_rules_order97_history import (
    MAPPING,
    ORDER102_MAPPING,
    historical_evidence_path,
)

ROOT = Path(__file__).resolve().parents[2]


def test_order102_original_assertions_are_immutable_and_fail_closed(tmp_path: Path) -> None:
    for name in (MAPPING, ORDER102_MAPPING):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    mapping = json.loads((ROOT / ORDER102_MAPPING).read_bytes())
    assert mapping["reviewed_commit"] == "8007555ef23e85c11d39b294acec02bd83fc3271"
    expected = {
        "tests/unit/test_phase15c_fight_order.py": (
            "0f3d5232ae42bb718ff0da4e6a1cb50017acbed5d317c6d468c1cd938c312f4b",
            305916,
        ),
        "tests/completed_attack_fixture_helpers.py": (
            "b6bf51193ee90beb5a08af3df8943848c47f2c90aeec8cd8ee82674c10a741ca",
            19339,
        ),
    }
    assert {row["path"] for row in mapping["files"]} == set(expected)
    assert len(mapping["files"]) == len(expected)
    for row in mapping["files"]:
        assert (row["sha256"], row["bytes"]) == expected[row["path"]]
        assert row["order97_file_pin"] == row["sha256"]
        with pytest.raises(FileNotFoundError):
            historical_evidence_path(row["path"], root=tmp_path)
        archived = tmp_path / row["historical_path"]
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_bytes((ROOT / row["historical_path"]).read_bytes())
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == row["sha256"]
        assert historical_evidence_path(row["path"], root=tmp_path) == archived
        archived.write_bytes(archived.read_bytes() + b"\n")
        with pytest.raises(ValueError, match="immutable historical input drifted"):
            historical_evidence_path(row["path"], root=tmp_path)
    map_path = tmp_path / ORDER102_MAPPING
    map_path.write_bytes(map_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="historical-input mapping drifted"):
        historical_evidence_path("tests/unit/test_phase15c_fight_order.py", root=tmp_path)
