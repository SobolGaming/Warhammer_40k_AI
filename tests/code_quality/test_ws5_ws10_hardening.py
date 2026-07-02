from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src" / "warhammer40k_core"
CLI_PATH = SRC_ROOT / "interfaces" / "cli.py"
DECISIONS_PATH = SRC_ROOT / "adapters" / "decisions.py"
PROJECTION_PATH = SRC_ROOT / "adapters" / "projection.py"
UI_FIXTURE_EXPORTER_PATH = ROOT / "scripts" / "export_ui_contract_fixtures.py"
MOVEMENT_ENVELOPE_PATH = SRC_ROOT / "geometry" / "movement_envelope.py"
PATHING_PATH = SRC_ROOT / "geometry" / "pathing.py"
VOLUME_PATH = SRC_ROOT / "geometry" / "volume.py"


def test_local_validate_identifier_functions_are_not_reintroduced() -> None:
    violations: list[str] = []

    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_validate_identifier":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert not violations, (
        "Identifier validation must use warhammer40k_core.core.validation instead of "
        "local _validate_identifier functions:\n" + "\n".join(violations)
    )


def test_adapter_pending_decision_readers_use_lifecycle_accessor() -> None:
    violations = [
        path.relative_to(ROOT).as_posix()
        for path in (DECISIONS_PATH, PROJECTION_PATH)
        if "pending_requests" in path.read_text(encoding="utf-8")
    ]

    assert not violations, (
        "Adapter pending-decision readers must use GameLifecycle.pending_decision_request():\n"
        + "\n".join(violations)
    )


def test_cli_prompt_rendering_uses_viewer_scoped_projection() -> None:
    tree = ast.parse(CLI_PATH.read_text(encoding="utf-8"), filename=str(CLI_PATH))
    forbidden = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "render_decision_request_for_cli"
    ]
    assert not forbidden

    render_function = _function_node(tree=tree, name="render_pending_decision_for_cli")
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "view"
        for node in ast.walk(render_function)
    )


def test_ui_fixture_authoring_state_access_remains_explicitly_exempted() -> None:
    text = UI_FIXTURE_EXPORTER_PATH.read_text(encoding="utf-8")
    assert "session.lifecycle.state" in text
    assert "WS5 fixture-authoring exemption" in text
    assert "synthesize stable UI projection fixtures" in text


def test_geometry_engagement_and_coherency_thresholds_have_no_numeric_defaults() -> None:
    movement_envelope = _class_node(
        path=MOVEMENT_ENVELOPE_PATH,
        class_name="MovementEnvelope",
    )
    for field_name in (
        "coherency_horizontal_inches",
        "coherency_vertical_inches",
        "engagement_horizontal_inches",
        "engagement_vertical_inches",
    ):
        assert _class_field_default(class_node=movement_envelope, field_name=field_name) is None

    path_context = _class_node(path=PATHING_PATH, class_name="PathValidationContext")
    for field_name in (
        "enemy_engagement_horizontal_inches",
        "enemy_engagement_vertical_inches",
    ):
        assert _class_field_default(class_node=path_context, field_name=field_name) is None

    model = _class_node(path=VOLUME_PATH, class_name="Model")
    method = _method_node(class_node=model, name="is_within_engagement_range")
    assert method.args.defaults == []


def _class_node(*, path: Path, class_name: str) -> ast.ClassDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(f"Expected {class_name} in {path.relative_to(ROOT)}.")


def _function_node(*, tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Expected function {name}.")


def _method_node(*, class_node: ast.ClassDef, name: str) -> ast.FunctionDef:
    for node in class_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Expected method {name}.")


def _class_field_default(*, class_node: ast.ClassDef, field_name: str) -> ast.expr | None:
    for node in class_node.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == field_name
        ):
            return node.value
    raise AssertionError(f"Expected field {field_name}.")
