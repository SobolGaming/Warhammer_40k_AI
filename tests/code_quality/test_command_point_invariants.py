from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = ROOT / "src" / "warhammer40k_core" / "engine"
COMMAND_POINT_OWNER = ENGINE_ROOT / "command_points.py"
CORE_CP_HISTORY_AUTHORITY_OWNER = ENGINE_ROOT / "command_core_cp_history.py"
GAME_STATE_OWNER = ENGINE_ROOT / "game_state.py"
COMMAND_PHASE_OWNER = ENGINE_ROOT / "phases" / "command.py"
COMMAND_PHASE_START_AUTHORITY_OWNER = ENGINE_ROOT / "command_phase_start_authority.py"
APPROVED_EXPLICIT_CAP_EXEMPTION_CALLERS = {
    ENGINE_ROOT / "faction_content" / "warhammer_40000_11th" / "imperial_knights" / "army_rule.py",
}
COMMAND_PHASE_START_REGISTRY_RECEIVER_NAMES = {
    "command_phase_start_hooks",
    "command_phase_start_hook_registry",
}
COMMAND_PHASE_START_PRE_CP_METHODS = {
    "resolve_with_provider_dispositions",
    "resolve_effects_with_provider_dispositions",
    "next_request_with_provider",
}


def _receiver_identifies_command_phase_start_registry(node: ast.expr) -> bool:
    current = node
    while True:
        if isinstance(current, ast.Name):
            return current.id in COMMAND_PHASE_START_REGISTRY_RECEIVER_NAMES
        if isinstance(current, ast.Attribute):
            if current.attr in COMMAND_PHASE_START_REGISTRY_RECEIVER_NAMES:
                return True
            current = current.value
            continue
        if isinstance(current, ast.Subscript):
            current = current.value
            continue
        return False


def _parse_expression(source: str) -> ast.expr:
    tree = ast.parse(source, mode="eval")
    assert isinstance(tree, ast.Expression)
    return tree.body


class _CommandPhaseStartRegistryCallVisitor(ast.NodeVisitor):
    def __init__(self, *, owner_path: str) -> None:
        self.owner_path = owner_path
        self.scope: list[str] = []
        self.owners_by_method: dict[str, list[str]] = {
            method: [] for method in COMMAND_PHASE_START_PRE_CP_METHODS
        }

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in COMMAND_PHASE_START_PRE_CP_METHODS
            and _receiver_identifies_command_phase_start_registry(node.func.value)
        ):
            owner = ".".join(self.scope) if self.scope else "<module>"
            self.owners_by_method[node.func.attr].append(f"{self.owner_path}:{owner}")
        self.generic_visit(node)


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
    allowed_paths = {
        COMMAND_POINT_OWNER,
        COMMAND_PHASE_OWNER,
        CORE_CP_HISTORY_AUTHORITY_OWNER,
    }
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


def test_command_phase_start_registry_routes_through_one_pre_cp_boundary() -> None:
    for receiver_source in (
        "command_phase_start_hooks",
        "self.command_phase_start_hooks",
        "bundle.runtime.command_phase_start_hook_registry",
        "registries['command'].command_phase_start_hook_registry",
    ):
        assert _receiver_identifies_command_phase_start_registry(_parse_expression(receiver_source))
    for receiver_source in (
        "other_registry",
        "self.shooting_phase_start_hooks",
        "command_phase_start_hooks_factory",
    ):
        assert not _receiver_identifies_command_phase_start_registry(
            _parse_expression(receiver_source)
        )

    tree = ast.parse(
        COMMAND_PHASE_OWNER.read_text(encoding="utf-8"),
        filename=COMMAND_PHASE_OWNER.as_posix(),
    )
    command_handler_classes = tuple(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CommandPhaseHandler"
    )
    assert len(command_handler_classes) == 1
    begin_phase_methods = tuple(
        node
        for node in command_handler_classes[0].body
        if isinstance(node, ast.FunctionDef) and node.name == "begin_phase"
    )
    assert len(begin_phase_methods) == 1
    begin_phase = begin_phase_methods[0]

    begin_phase_direct_calls = tuple(
        node.func.id
        for node in ast.walk(begin_phase)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    )
    assert begin_phase_direct_calls.count("resolve_command_phase_start_boundary") == 1
    assert begin_phase_direct_calls.count("_resolve_gain_core_command_points_step") == 1
    assert "_request_command_phase_start_faction_rule_if_available" not in (
        begin_phase_direct_calls
    )

    registry_call_owners: dict[str, list[str]] = {
        method: [] for method in COMMAND_PHASE_START_PRE_CP_METHODS
    }
    for path in sorted(ENGINE_ROOT.rglob("*.py")):
        engine_tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
        visitor = _CommandPhaseStartRegistryCallVisitor(
            owner_path=path.relative_to(ROOT).as_posix()
        )
        visitor.visit(engine_tree)
        for method, owners in visitor.owners_by_method.items():
            registry_call_owners[method].extend(owners)

    authority_owner = COMMAND_PHASE_START_AUTHORITY_OWNER.relative_to(ROOT).as_posix()
    assert registry_call_owners == {
        "resolve_with_provider_dispositions": [
            f"{authority_owner}:resolve_command_phase_start_boundary"
        ],
        "resolve_effects_with_provider_dispositions": [
            f"{authority_owner}:resolve_command_phase_start_boundary"
        ],
        "next_request_with_provider": [f"{authority_owner}:resolve_command_phase_start_boundary"],
    }

    authority_tree = ast.parse(
        COMMAND_PHASE_START_AUTHORITY_OWNER.read_text(encoding="utf-8"),
        filename=COMMAND_PHASE_START_AUTHORITY_OWNER.as_posix(),
    )
    boundary_functions = tuple(
        function
        for function in ast.walk(authority_tree)
        if isinstance(function, ast.FunctionDef)
        and function.name == "resolve_command_phase_start_boundary"
    )
    assert len(boundary_functions) == 1
    ordered_lines: dict[str, int] = {}
    for node in ast.walk(boundary_functions[0]):
        if not isinstance(node, ast.Call):
            continue
        if (
            isinstance(node.func, ast.Attribute)
            and _receiver_identifies_command_phase_start_registry(node.func.value)
            and node.func.attr in COMMAND_PHASE_START_PRE_CP_METHODS
        ):
            ordered_lines[node.func.attr] = node.lineno

    assert set(ordered_lines) == {
        "resolve_with_provider_dispositions",
        "resolve_effects_with_provider_dispositions",
        "next_request_with_provider",
    }
    assert (
        ordered_lines["resolve_with_provider_dispositions"]
        < ordered_lines["resolve_effects_with_provider_dispositions"]
    )
    assert (
        ordered_lines["resolve_effects_with_provider_dispositions"]
        < ordered_lines["next_request_with_provider"]
    )
    begin_call_lines = {
        node.func.id: node.lineno
        for node in ast.walk(begin_phase)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id
        in {"resolve_command_phase_start_boundary", "_resolve_gain_core_command_points_step"}
    }
    assert (
        begin_call_lines["resolve_command_phase_start_boundary"]
        < begin_call_lines["_resolve_gain_core_command_points_step"]
    )
