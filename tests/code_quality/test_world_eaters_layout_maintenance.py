"""The reviewed lookup diagnostic maintenance preserves archived assertions."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.support import faction_layout_preservation as preservation
from tests.support.faction_layout_preservation import MANIFEST, verify_layout_original

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = "tests/unit/test_phase17g_world_eaters_army_rule.py"
SUCCESSOR = "tests/factions/world_eaters/unit/test_world_eaters_army_rule.py"


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
