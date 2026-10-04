"""Bounded source and orchestration ownership for the selected Command body."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from warhammer40k_core.engine.command_abilities import COMMAND_ABILITIES_SOURCE_RULE_ID

ROOT = Path(__file__).resolve().parents[2]


def test_command_abilities_uses_the_immutable_selected_core_source() -> None:
    raw = (ROOT / "data/source_audits/order97/selected-sources.json").read_bytes()
    audit = json.loads((ROOT / "data/source_audits/order121/source.audit.json").read_bytes())
    assert audit["selected_sources_sha256"] == hashlib.sha256(raw).hexdigest()
    selected = {row["row_id"]: row for row in json.loads(raw)}
    assert audit["selected_core_rows"] == [
        selected["rule:08:08.00:1"],
        selected[COMMAND_ABILITIES_SOURCE_RULE_ID],
    ]
    assert set(audit["requirements"]) == {"08.00-step-6", "08.04-ability-window"}


def test_command_body_precedes_end_replacement_and_uses_shared_timing_owner() -> None:
    tree = ast.parse(
        (ROOT / "src/warhammer40k_core/engine/phases/command.py").read_text(encoding="utf-8")
    )
    handler = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CommandPhaseHandler"
    )
    begin = next(
        node
        for node in handler.body
        if isinstance(node, ast.FunctionDef) and node.name == "begin_phase"
    )
    calls = {
        node.func.id: node.lineno
        for node in ast.walk(begin)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert calls["_resolve_battle_shock_step"] < calls["resolve_command_abilities"]
    assert (
        calls["resolve_command_abilities"]
        < calls["_request_tactical_secondary_replacement_if_available"]
    )
    body = ast.parse(
        (ROOT / "src/warhammer40k_core/engine/command_abilities.py").read_text(encoding="utf-8")
    )
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve_runtime_timing_window"
        for node in ast.walk(body)
    )
