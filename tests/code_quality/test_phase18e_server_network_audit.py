from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "warhammer40k_core"
SERVER_NETWORK_MODULES = (
    SRC / "adapters" / "network.py",
    SRC / "adapters" / "server.py",
)
CLIENT_PRODUCER_MODULES = (
    SRC / "adapters" / "headless.py",
    SRC / "adapters" / "network.py",
    SRC / "adapters" / "server.py",
    SRC / "adapters" / "ui.py",
    SRC / "interfaces" / "cli.py",
)
FORBIDDEN_DICE_IMPORT_NAMES = frozenset(
    {
        "DiceRollManager",
        "RandomSource",
        "injected_results",
        "roll_d3_fixed",
        "roll_fixed",
    }
)
FORBIDDEN_DICE_MODULES = frozenset(
    {
        "random",
        "warhammer40k_core.core.rng",
        "warhammer40k_core.engine.dice",
    }
)
ENGINE_DICE_MODULES = frozenset(
    {
        "warhammer40k_core.engine.decision",
        "warhammer40k_core.engine.dice",
    }
)
REDACTION_CONSUMER_MODULES = (
    SRC / "adapters" / "projection.py",
    SRC / "adapters" / "event_stream.py",
    SRC / "adapters" / "server.py",
)
LOCAL_REDACTION_HELPER_NAMES = frozenset(
    {
        "_redacted_decision_type",
        "_redact_decision_type_for_hidden_viewer",
        "_secret_request_hidden_from_viewer",
    }
)
LEGACY_HIDDEN_DECISION_TYPES = frozenset(
    {
        "discard_tactical_secondary_mission",
        "draw_tactical_secondary_missions",
        "start_mission_action",
    }
)


def test_phase18e_server_network_modules_do_not_bypass_session_facade() -> None:
    violations: list[str] = []
    for path in SERVER_NETWORK_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "warhammer40k_core.engine.lifecycle":
                    for alias in node.names:
                        if alias.name == "GameLifecycle":
                            violations.append(f"{path}: imports GameLifecycle directly")
                if node.module in ENGINE_DICE_MODULES:
                    for alias in node.names:
                        if alias.name == "DiceRollManager":
                            violations.append(f"{path}: imports DiceRollManager")
            if isinstance(node, ast.Attribute):
                if node.attr == "decision_controller":
                    violations.append(f"{path}: accesses decision_controller directly")
                if node.attr == "submit_decision":
                    violations.append(f"{path}: calls submit_decision directly")
            if isinstance(node, ast.Name) and node.id == "DiceRollManager":
                violations.append(f"{path}: references DiceRollManager")
    assert not violations


def test_phase18e_client_network_headless_modules_do_not_own_dice_rng() -> None:
    violations: list[str] = []
    for path in CLIENT_PRODUCER_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_DICE_MODULES:
                        violations.append(f"{path}: imports forbidden RNG module {alias.name}")
            if isinstance(node, ast.ImportFrom):
                module = "" if node.module is None else node.module
                if module in FORBIDDEN_DICE_MODULES:
                    violations.append(f"{path}: imports forbidden RNG module {module}")
                for alias in node.names:
                    if alias.name in FORBIDDEN_DICE_IMPORT_NAMES:
                        violations.append(f"{path}: imports forbidden dice owner {alias.name}")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr in {
                    "roll_d3_fixed",
                    "roll_fixed",
                }:
                    violations.append(f"{path}: calls {node.func.attr}")
                if isinstance(node.func, ast.Name) and node.func.id in {
                    "roll_d3_fixed",
                    "roll_fixed",
                }:
                    violations.append(f"{path}: calls {node.func.id}")
            if isinstance(node, ast.Name) and node.id in {"DiceRollManager", "RandomSource"}:
                violations.append(f"{path}: references forbidden dice/RNG owner {node.id}")
    assert not violations


def test_adapter_hidden_decision_redaction_is_centralized() -> None:
    violations: list[str] = []
    for path in REDACTION_CONSUMER_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports_shared_redaction = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "warhammer40k_core.adapters.redaction"
            ):
                imports_shared_redaction = True
            if isinstance(node, ast.FunctionDef) and node.name in LOCAL_REDACTION_HELPER_NAMES:
                violations.append(f"{path}: defines local hidden-decision helper {node.name}")
            if isinstance(node, ast.Set):
                hidden_type_literals = {
                    element.value
                    for element in node.elts
                    if isinstance(element, ast.Constant) and type(element.value) is str
                } & LEGACY_HIDDEN_DECISION_TYPES
                if hidden_type_literals:
                    violations.append(
                        f"{path}: defines local hidden-decision type set "
                        f"{sorted(hidden_type_literals)}"
                    )
        if not imports_shared_redaction:
            violations.append(f"{path}: does not import adapters.redaction")
    assert not violations
