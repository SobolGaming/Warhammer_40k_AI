"""Source context and mutation ownership audits for no-movement embark."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_embark_uses_shared_types_geometry_and_mutation_without_name_gates() -> None:
    types = (ENGINE / "transport_embark_types.py").read_text(encoding="utf-8")
    source = (ENGINE / "transport_source_embark.py").read_text(encoding="utf-8")
    movement = (ENGINE / "phases/movement_fall_back_embark.py").read_text(encoding="utf-8")
    history = (ENGINE / "transport_source_embark_history.py").read_text(encoding="utf-8")
    assert "class EmbarkSelection:" in types
    assert "TransportMovementStatus.NOT_MOVED" in types
    assert "source_context" in types
    assert "apply_embark_mutation(" in source
    assert "apply_embark_mutation(" in movement
    assert "_post_move_embark_options(" in source
    assert "selection != submitted" in history
    assert "Aerialists" not in source
    assert "normal_move" not in source
    for text in (source, movement):
        assert "state.replace_transport_cargo_state(embark.updated_cargo_state)" not in text
    mutation = (ENGINE / "transport_embark_mutation.py").read_text(encoding="utf-8")
    assert "state.replace_transport_cargo_state(embark.updated_cargo_state)" in mutation
    assert "apply_embark_to_battlefield(" in mutation


def test_source_embark_dispatch_is_registered_with_validator_and_applier() -> None:
    owner = ast.parse((ENGINE / "lifecycle.py").read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(owner)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "source_embark_dispatch_handler"
    ]
    assert len(calls) == 1
    assert {arg.arg for arg in calls[0].keywords} == {
        "state_provider",
        "decisions",
        "advance",
        "ordinary_validator",
        "ordinary_applier",
    }
    history = (ENGINE / "movement_decision_authority.py").read_text(encoding="utf-8")
    assert "validate_source_embark_request(request)" in history
    assert "validate_source_embark_event(record, payload)" in history
    selection_history = (ENGINE / "movement_selection_history.py").read_text(encoding="utf-8")
    assert "validate_source_embark_event(record, payload)" in selection_history
    assert 'event.event_type == "unit_embarked"' in selection_history


def test_order114_retains_original_order97_assertion_bytes_and_source_obligation() -> None:
    mapping = json.loads((ROOT / "data/source_audits/order114/historical-inputs.json").read_bytes())
    assert mapping["reviewed_commit"] == "6653b86daf7d1bc51e1d0158691fe640bb3a2a4d"
    for row in mapping["files"]:
        raw = (ROOT / row["historical_path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]
        assert len(raw) == row["bytes"]
        assert row["sha256"] == row["order97_file_pin"]
    source_rows = cast(
        list[dict[str, Any]],
        json.loads((ROOT / "data/source_audits/order97/selected-sources.json").read_bytes()),
    )
    faq = next(
        row for row in source_rows if row["row_id"] == "faq:c2df3e97-f21e-4fc9-943e-37072c08c10e"
    )
    assert faq["blocks"][1]["sha256"] == (
        "3331d006616a0da2fffb9f7111862c71f5498f9385943973130d3dafc08d7a36"
    )
