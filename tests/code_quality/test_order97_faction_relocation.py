"""Historical faction evidence is usable only after exact live relocation checks."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest
from tools import core_rules_order97_inventory as audit
from tools.core_rules_order97_history import historical_evidence_path

from tests.support import faction_layout_preservation as preservation
from tests.support.faction_layout_preservation import MANIFEST, verify_layout_original

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = "tests/unit/test_phase17g_world_eaters_army_rule.py"
SUCCESSOR = "tests/factions/world_eaters/unit/test_world_eaters_army_rule.py"
HELPER = "tests/factions/world_eaters/world_eaters_helpers.py"


def test_order97_resolves_authenticated_faction_archive_before_historical_evidence() -> None:
    assert not (ROOT / ORIGINAL).exists()
    _, record = verify_layout_original(ROOT, ORIGINAL)
    historical = historical_evidence_path(ORIGINAL, root=ROOT)
    expected = ROOT / record["archive"] if historical is None else historical
    assert audit._path(ORIGINAL, ROOT) == expected  # pyright: ignore[reportPrivateUsage]
    symbol = "test_lifecycle_requests_world_eaters_blessings_and_records_effect"
    node = audit._symbol(  # pyright: ignore[reportPrivateUsage]
        ORIGINAL + "::" + symbol, {}, ROOT
    )
    assert isinstance(node, ast.FunctionDef)
    assert node.name == symbol


@pytest.mark.parametrize("corruption", ["manifest", "archive", "assertion", "helper", "missing"])
def test_order97_relocated_archive_rejects_live_or_historical_drift(
    tmp_path: Path, corruption: str
) -> None:
    manifest = json.loads((ROOT / MANIFEST).read_bytes())
    record = manifest["originals"][ORIGINAL]
    for relative in [MANIFEST, record["archive"], *record["successors"]]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    if corruption == "missing":
        (tmp_path / SUCCESSOR).unlink()
        with pytest.raises(FileNotFoundError):
            audit._path(ORIGINAL, tmp_path)  # pyright: ignore[reportPrivateUsage]
        return
    target = {
        "manifest": MANIFEST,
        "archive": record["archive"],
        "assertion": SUCCESSOR,
        "helper": HELPER,
    }[corruption]
    path = tmp_path / target
    if corruption == "assertion":
        raw = path.read_bytes()
        assert b"assert " in raw
        path.write_bytes(raw.replace(b"assert ", b"assert False and ", 1))
    else:
        path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match=r"Faction layout .* drifted"):
        audit._path(ORIGINAL, tmp_path)  # pyright: ignore[reportPrivateUsage]


def test_order97_unregistered_missing_evidence_still_fails(tmp_path: Path) -> None:
    with pytest.raises(audit.InventoryError, match="Evidence file is absent"):
        audit._path("tests/unit/test_unregistered_missing_evidence.py", tmp_path)  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b'match="unit_instance_id is unknown"', b'match="unreviewed lookup message"'),
        (
            b'pytest.raises(GameLifecycleError, match="unit_instance_id is unknown")',
            b'pytest.raises(ValueError, match="unit_instance_id is unknown")',
        ),
        (b'unit_instance_id="missing-unit"', b'unit_instance_id="different-unit"'),
    ],
)
def test_world_eaters_lookup_maintenance_preserves_every_other_archived_assertion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, old: bytes, new: bytes
) -> None:
    manifest = json.loads((ROOT / MANIFEST).read_bytes())
    record = manifest["originals"][ORIGINAL]
    for relative in [record["archive"], *record["successors"]]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    path = tmp_path / SUCCESSOR
    raw = path.read_bytes()
    assert raw.count(old) == 1
    changed = raw.replace(old, new, 1)
    path.write_bytes(changed)
    # Exercise the AST maintenance boundary after current-byte admission;
    # the immutable archived bytes and definition mappings remain untouched.
    record["successors"][SUCCESSOR] = hashlib.sha256(changed).hexdigest()
    manifest_raw = json.dumps(manifest).encode()
    manifest_path = tmp_path / MANIFEST
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(manifest_raw)
    monkeypatch.setattr(preservation, "MANIFEST_SHA256", hashlib.sha256(manifest_raw).hexdigest())
    with pytest.raises(ValueError, match=r"Faction layout .* drifted"):
        verify_layout_original(tmp_path, ORIGINAL)
