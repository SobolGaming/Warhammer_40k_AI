from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = ROOT / "src" / "warhammer40k_core" / "engine"
GAME_STATE_PATH = ENGINE_ROOT / "game_state.py"

# Defense-in-depth audit for the production pattern used today: functions that name
# `state: GameState` and directly assign `state.field = ...`. It does not attempt
# full type resolution for unannotated values, aliases, or dynamic writes.


def test_engine_game_state_mutations_go_through_game_state_methods() -> None:
    violations: list[str] = []

    for path in sorted(ENGINE_ROOT.rglob("*.py")):
        if path == GAME_STATE_PATH:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _GameStateAssignmentVisitor(path.relative_to(ROOT).as_posix())
        visitor.visit(tree)
        violations.extend(visitor.violations)

    assert not violations, (
        "Engine modules outside game_state.py must mutate GameState through narrow "
        "GameState mutator methods:\n" + "\n".join(violations)
    )


class _GameStateAssignmentVisitor(ast.NodeVisitor):
    def __init__(self, relative_path: str) -> None:
        self._relative_path = relative_path
        self._game_state_names_by_scope: list[set[str]] = [set()]
        self.violations: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function_scope(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function_scope(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and _annotation_mentions_game_state(node.annotation):
            self._game_state_names_by_scope[-1].add(node.target.id)
        self._record_assignment_target(node.target)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._record_assignment_target(target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._record_assignment_target(node.target)
        self.generic_visit(node)

    def _visit_function_scope(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        game_state_names = set(self._game_state_names_by_scope[-1])
        for arg in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        ):
            if arg.annotation is not None and _annotation_mentions_game_state(arg.annotation):
                game_state_names.add(arg.arg)
        if node.args.vararg is not None and _annotation_mentions_game_state(
            node.args.vararg.annotation
        ):
            game_state_names.add(node.args.vararg.arg)
        if node.args.kwarg is not None and _annotation_mentions_game_state(
            node.args.kwarg.annotation
        ):
            game_state_names.add(node.args.kwarg.arg)

        self._game_state_names_by_scope.append(game_state_names)
        for statement in node.body:
            self.visit(statement)
        self._game_state_names_by_scope.pop()

    def _record_assignment_target(self, target: ast.AST) -> None:
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            if target.value.id in self._game_state_names_by_scope[-1]:
                self.violations.append(f"{self._relative_path}:{target.lineno}:{target.attr}")
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._record_assignment_target(element)


def _annotation_mentions_game_state(annotation: ast.AST | None) -> bool:
    if annotation is None:
        return False
    if isinstance(annotation, ast.Name):
        return annotation.id == "GameState"
    if isinstance(annotation, ast.Attribute):
        return annotation.attr == "GameState"
    if isinstance(annotation, ast.Constant):
        return isinstance(annotation.value, str) and "GameState" in annotation.value
    return any(_annotation_mentions_game_state(child) for child in ast.iter_child_nodes(annotation))
