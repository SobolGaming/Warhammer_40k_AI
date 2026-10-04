"""Source authority and the single executable Select Model boundary stay shared."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_allocation_trigger_retains_selected_core_and_real_example_authority() -> None:
    audit = json.loads((ROOT / "data/source_audits/order117/source.audit.json").read_bytes())
    raw = (ROOT / audit["source"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == audit["source_sha256"]
    rows = {row["row_id"]: row for row in json.loads(raw)}
    assert audit["requirement"] == "faq-e58d31bc-b6eb-4db1-b319-dc27dd60154f-obligation-01"
    for row in audit["selected_rows"]:
        assert row == rows[row["row_id"]]
    example = audit["official_exemplar"]
    assert hashlib.sha256((ROOT / example["path"]).read_bytes()).hexdigest() == example["sha256"]
    assert (
        hashlib.sha256((ROOT / example["retained_profile"]).read_bytes()).hexdigest()
        == (example["retained_profile_sha256"])
    )


def test_every_mortal_select_model_owner_uses_the_shared_executable_boundary() -> None:
    callers: list[str] = []
    for path in ENGINE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "record_mortal_wound_allocation_occurrence"
            ):
                callers.append(path.name)
    assert sorted(callers) == [
        "direct_mortal_wound_application.py",
        "mortal_wound_model_allocation.py",
    ]
    boundary = (ENGINE / "mortal_wound_allocation_triggers.py").read_text(encoding="utf-8")
    assert "executed_sources.append(binding.source)" in boundary
    assert "return occurrence, resolved_sources, decline_allowed" in boundary
    assert "TimingTriggerKind.MORTAL_WOUND_ALLOCATED.value" in boundary
    assert ".lose_wounds(" not in boundary
    for name in ("mortal_wound_allocation_triggers.py", "mortal_wound_allocation_permissions.py"):
        text = (ENGINE / name).read_text(encoding="utf-8")
        assert "Arcane Genetic Alchemy" not in text
        assert "adeptus-custodes" not in text
    redaction = (ROOT / "src/warhammer40k_core/adapters/redaction.py").read_text(encoding="utf-8")
    assert "MORTAL_WOUND_ALLOCATION_RULE_APPLIED_EVENT_TYPE," in redaction
    decision = ast.parse((ENGINE / "decision.py").read_text(encoding="utf-8"))
    neutral = next(
        node.value
        for node in decision.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_RNG_HISTORY_NEUTRAL_EVENT_TYPES"
            for target in node.targets
        )
    )
    neutral_events = {
        node.value
        for node in ast.walk(neutral)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert {
        "mortal_wound_model_allocated",
        "mortal_wound_allocation_rule_applied",
    } <= neutral_events
