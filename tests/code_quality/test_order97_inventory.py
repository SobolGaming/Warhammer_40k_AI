"""An assertion inventory must reject missing source spans and invented evidence."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from tools import core_rules_order97_inventory as audit
from tools.core_rules_order84_capture import fingerprint
from tools.core_rules_order97_history import (
    ISSUE535_MAPPING,
    MAPPING,
    ORDER102_MAPPING,
    ORDER103_MAPPING,
    historical_evidence_path,
)


def repin(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> None:
    """Exercise structural guards independently of the reviewed identity guard."""
    monkeypatch.setattr(audit, "REVIEW_SHA256", fingerprint(payload))


def test_order97_inventory_covers_every_selected_clause_and_runtime_row() -> None:
    inventory = audit.load_inventory()
    assert set(inventory.categories) == {f"{number:02d}" for number in range(1, 26)}
    assert inventory.runtime_input is False
    assert inventory.caudit_01_closed is False
    assert inventory.outcome == "clause_evidence_inventory"
    assert len(inventory.sources) == 345
    assert len(inventory.changelog) == 91
    assert len(inventory.runtime_packages) == 52
    scheduled = {rid for finding in inventory.followups for rid in finding.requirement_ids}
    assert all(
        clause.evidence or clause.requirement_id in scheduled for clause in inventory.requirements
    )
    assert audit.REPORT.read_text() == audit.markdown(inventory)


@pytest.mark.parametrize(
    "field", ["sources", "requirements", "assertions", "changelog", "runtime_packages"]
)
def test_order97_rejects_omitted_or_duplicated_inventory(field: str) -> None:
    original = audit.load_inventory().model_dump()
    for duplicate in (False, True):
        payload = deepcopy(original)
        if duplicate:
            payload[field].append(payload[field][0])
        else:
            payload[field].pop()
        with pytest.raises(audit.InventoryError, match="identity changed"):
            audit.load_inventory(payload=payload)


def test_order97_rejects_false_certification_and_unknown_fields() -> None:
    for changes in ({"caudit_01_closed": True}, {"outcome": "certified"}, {"unknown": None}):
        with pytest.raises(audit.InventoryError, match="malformed or incomplete"):
            audit.load_inventory(payload={**audit.load_inventory().model_dump(), **changes})


def test_order97_rejects_source_block_omissions_after_repin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = audit.load_inventory().model_dump()
    row = payload["sources"][0]["row_id"]
    payload["requirements"] = [r for r in payload["requirements"] if r["row_id"] != row]
    payload["nonoperative"] = [r for r in payload["nonoperative"] if r["row_id"] != row]
    repin(monkeypatch, payload)
    with pytest.raises(audit.InventoryError, match="Unclassified or invented source block"):
        audit.load_inventory(payload=payload)


@pytest.mark.parametrize("change", ["assertion", "setup"])
def test_order97_rejects_forged_assertions_and_changed_test_setup(
    monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    payload = audit.load_inventory().model_dump()
    receipt = payload["assertions"][0]
    if change == "setup":
        receipt["test_ast_sha256"] = "0" * 64
    else:
        old = receipt["assertion"]
        receipt["assertion"] = "assert invented_core_rules_certificate is True"
        receipt["sha256"] = fingerprint(receipt["assertion"])
        for requirement in payload["requirements"]:
            for evidence in requirement["evidence"]:
                if evidence["nodeid"] == receipt["nodeid"] and evidence["assertion"] == old:
                    evidence["assertion"] = receipt["assertion"]
    repin(monkeypatch, payload)
    with pytest.raises(audit.InventoryError, match="Cited assertion is absent or changed"):
        audit.load_inventory(payload=payload)


def test_order97_rejects_unowned_evidence_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = audit.load_inventory().model_dump()
    payload["followups"] = []
    repin(monkeypatch, payload)
    with pytest.raises(audit.InventoryError, match="owned prerequisite"):
        audit.load_inventory(payload=payload)


def test_order97_rejects_unscheduled_prerequisite(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = audit.load_inventory().model_dump()
    payload["followups"][0]["pr_id"] = "INVENTED-PREREQUISITE"
    repin(monkeypatch, payload)
    with pytest.raises(audit.InventoryError, match="not a PFINAL prerequisite"):
        audit.load_inventory(payload=payload)


def test_order97_rejects_runtime_transcription_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = audit.load_inventory().model_dump()
    payload["runtime_packages"][0]["rules"][0]["source_text"] += " Invented permission."
    repin(monkeypatch, payload)
    with pytest.raises(audit.InventoryError, match="Runtime source receipt drifted"):
        audit.load_inventory(payload=payload)


def test_order97_rejects_retired_consumer_without_successor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = audit.load_inventory().model_dump()
    rule = next(
        rule
        for package in payload["runtime_packages"]
        for rule in package["rules"]
        if rule["runtime_consumer_ids"]
    )
    rule["retired_consumer_successors"] = {rule["runtime_consumer_ids"][0]: []}
    repin(monkeypatch, payload)
    with pytest.raises(audit.InventoryError, match="Retired consumers require"):
        audit.load_inventory(payload=payload)


@pytest.mark.parametrize("kind", ["helper", "test_module", "conftest"])
def test_order97_rejects_unpinned_assertion_fixture(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    inventory = audit.load_inventory()
    payload = inventory.model_dump()
    paths = sorted(audit.helper_source_paths(inventory))
    if kind == "test_module":
        helper = inventory.assertions[0].nodeid.split("::", 1)[0]
    elif kind == "conftest":
        helper = next(path for path in paths if path.endswith("conftest.py"))
    else:
        helper = next(path for path in paths if path.endswith("_helpers.py"))
    payload["files"] = [item for item in payload["files"] if item["path"] != helper]
    repin(monkeypatch, payload)
    with pytest.raises(audit.InventoryError, match="fixture dependencies must be pinned"):
        audit.load_inventory(payload=payload)


@pytest.mark.parametrize(("field", "value"), [("version", "invented"), ("kind", "invented")])
def test_order97_rejects_changelog_metadata_drift(
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    payload = audit.load_inventory().model_dump()
    payload["changelog"][0][field] = value
    repin(monkeypatch, payload)
    with pytest.raises(audit.InventoryError, match="Changelog transcription differs"):
        audit.load_inventory(payload=payload)


def test_order97_rejects_duplicated_nonoperative_disposition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = audit.load_inventory().model_dump()
    payload["nonoperative"].append(deepcopy(payload["nonoperative"][0]))
    repin(monkeypatch, payload)
    with pytest.raises(audit.InventoryError, match="Duplicated nonoperative disposition"):
        audit.load_inventory(payload=payload)


def test_issue535_original_scout_assertions_remain_exact_and_fail_closed(tmp_path: Path) -> None:
    reference = "tests/unit/test_phase16b_prebattle.py"
    for name in (MAPPING, ORDER102_MAPPING, ORDER103_MAPPING):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((audit.ROOT / name).read_bytes())
    with pytest.raises(FileNotFoundError):
        historical_evidence_path(reference, root=tmp_path)
    map_path = tmp_path / ISSUE535_MAPPING
    map_path.parent.mkdir(parents=True, exist_ok=True)
    map_path.write_bytes((audit.ROOT / ISSUE535_MAPPING).read_bytes())
    mapping = json.loads(map_path.read_bytes())
    assert mapping["reviewed_commit"] == "8007555ef23e85c11d39b294acec02bd83fc3271"
    assert mapping["also_present_at_base"] == "ff0b2db17106e7e0493929d6ab9ddb15c44aa476"
    assert len(mapping["files"]) == 1
    row = mapping["files"][0]
    assert row["path"] == row["git_path"] == reference
    assert row["git_revision"] == mapping["reviewed_commit"]
    assert (
        row["sha256"]
        == row["order97_file_pin"]
        == ("c1fcf7728167c259abfd08e08565aa2c1f637837751afd8d40b29f6f258959fb")
    )
    assert row["bytes"] == 104510
    with pytest.raises(FileNotFoundError):
        historical_evidence_path(reference, root=tmp_path)
    archive = tmp_path / row["historical_path"]
    archive.parent.mkdir(parents=True, exist_ok=True)
    retained = (audit.ROOT / row["historical_path"]).read_bytes()
    assert len(retained) == row["bytes"]
    assert hashlib.sha256(retained).hexdigest() == row["sha256"]
    archive.write_bytes(retained)
    assert historical_evidence_path(reference, root=tmp_path) == archive
    archive.write_bytes(retained + b"\n")
    with pytest.raises(ValueError, match="immutable historical input drifted"):
        historical_evidence_path(reference, root=tmp_path)
    archive.write_bytes(retained)
    map_path.write_bytes(map_path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="historical-input mapping drifted"):
        historical_evidence_path(reference, root=tmp_path)
