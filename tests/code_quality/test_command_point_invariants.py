from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = ROOT / "src" / "warhammer40k_core" / "engine"
COMMAND_POINT_OWNER = ENGINE_ROOT / "command_points.py"
GAME_STATE_OWNER = ENGINE_ROOT / "game_state.py"
COMMAND_PHASE_OWNER = ENGINE_ROOT / "phases" / "command.py"
APPROVED_EXPLICIT_CAP_EXEMPTION_CALLERS = {
    ENGINE_ROOT / "faction_content" / "warhammer_40000_11th" / "imperial_knights" / "army_rule.py",
}


def test_ability_paths_cannot_opt_out_of_the_non_core_cp_cap() -> None:
    offenders: list[str] = []
    approved_counts = dict.fromkeys(APPROVED_EXPLICIT_CAP_EXEMPTION_CALLERS, 0)
    for path in sorted(ENGINE_ROOT.rglob("*.py")):
        if path in {COMMAND_POINT_OWNER, GAME_STATE_OWNER}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "cap_exempt":
                    continue
                if (
                    path in APPROVED_EXPLICIT_CAP_EXEMPTION_CALLERS
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True
                ):
                    approved_counts[path] += 1
                    continue
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")

    assert offenders == []
    assert approved_counts == dict.fromkeys(APPROVED_EXPLICIT_CAP_EXEMPTION_CALLERS, 1)


def test_only_the_command_phase_owner_can_issue_core_cp() -> None:
    offenders: list[str] = []
    allowed_paths = {COMMAND_POINT_OWNER, COMMAND_PHASE_OWNER}
    for path in sorted(ENGINE_ROOT.rglob("*.py")):
        if path in allowed_paths:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr == "COMMAND_PHASE_START"
                and isinstance(node.value, ast.Name)
                and node.value.id == "CommandPointSourceKind"
            ):
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")

    assert offenders == []
