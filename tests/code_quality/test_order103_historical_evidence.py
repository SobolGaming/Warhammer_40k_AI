"""Current API changes cannot rewrite the original Order97 assertion evidence."""

import hashlib
import json
from pathlib import Path

import pytest
from tools.core_rules_order97_history import (
    MAPPING,
    ORDER102_MAPPING,
    ORDER103_MAPPING,
    historical_evidence_path,
)

ROOT = Path(__file__).resolve().parents[2]


def test_order103_original_assertions_remain_exact_and_fail_closed(tmp_path: Path) -> None:
    for name in (MAPPING, ORDER102_MAPPING, ORDER103_MAPPING):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    mapping = json.loads((ROOT / ORDER103_MAPPING).read_bytes())
    expected = {
        "tests/unit/test_phase13b_shooting_declarations.py": (
            "fbe5dff1543e140d933880844a52a8d63e4b0eaad2e7fdd309438abc5c1e3d69",
            815634,
        ),
        "tests/unit/test_target_replacement.py": (
            "85334dd19d82ec8f113eba0cd7c6999fe961cd530d2192ed268a78a34db363a8",
            48608,
        ),
        "tests/unit/test_order97_attack_evidence.py": (
            "12a4057e5de809b5d048acf4df983333694e8f8df013cb3c356fb96d6ea95538",
            13758,
        ),
        "tests/order97_gap_probes_04_06.py": (
            "86c4fa69223ac2bff187cbc4f8655f80ea2af1e81b0d17e50aa53445d861023c",
            8734,
        ),
        "tests/unit/test_lethal_hits.py": (
            "e1420132cd93943381e99b7f3ffd789ac834ba3a78e1ebbc61f4c1193b3b2ca5",
            22456,
        ),
        "tests/unit/test_order96_twin_linked.py": (
            "4cd357c8cdc4f217cb17fe20c7015c1e65f7df89c49a4ef0b0ed9935463e2c16",
            24575,
        ),
        "tests/unit/test_phase11e_mission_scoring_cleanup.py": (
            "0bb56db81c16794d86833ec8fe5a1a976fcbbcd4895fb31e3ee14052a546aaa3",
            511731,
        ),
        "tests/order101_failed_setup_helpers.py": (
            "6c387f7d7c5975fbb9960c862b62b33fd75b6349e3fe5f39d3e0cdff39d36211",
            43050,
        ),
        "tests/twin_linked_helpers.py": (
            "0333b151949c7761cde49283709e8edad5586725c75ee71611267b1bb600c8d5",
            11947,
        ),
    }
    assert {row["path"] for row in mapping["files"]} == set(expected)
    assert len(mapping["files"]) == len(expected)
    for row in mapping["files"]:
        assert (row["sha256"], row["bytes"]) == expected[row["path"]]
        assert row["order97_file_pin"] == row["sha256"]
        assert row["git_path"] == row["path"]
        assert row["git_revision"] == (
            "38ce2265b81f2c0b2c9c668dae7536c239095193"
            if row["path"] == "tests/order101_failed_setup_helpers.py"
            else "19f1c507541321b7c1ed04f80e2c1110a1fa786d"
            if "order97" in row["path"]
            else "8007555ef23e85c11d39b294acec02bd83fc3271"
        )
        with pytest.raises(FileNotFoundError):
            historical_evidence_path(row["path"], root=tmp_path)
        archive = tmp_path / row["historical_path"]
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes((ROOT / row["historical_path"]).read_bytes())
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == row["sha256"]
        assert historical_evidence_path(row["path"], root=tmp_path) == archive
        archive.write_bytes(archive.read_bytes() + b"\n")
        with pytest.raises(ValueError, match="immutable historical input drifted"):
            historical_evidence_path(row["path"], root=tmp_path)
    map_path = tmp_path / ORDER103_MAPPING
    map_path.write_bytes(map_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="historical-input mapping drifted"):
        historical_evidence_path("tests/unit/test_target_replacement.py", root=tmp_path)
