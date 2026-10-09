"""Only the approved Core grant path opts out of normal fight-band selection."""

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "src/warhammer40k_core/engine"


def test_pre_grant_query_scope_is_explicit_and_confined_to_core_counter() -> None:
    actual: set[tuple[str, str, str]] = set()
    defaults: set[tuple[str, str]] = set()
    for path in ENGINE.rglob("*.py"):
        for owner in ast.walk(ast.parse(path.read_bytes())):
            if not isinstance(owner, ast.FunctionDef):
                continue
            for argument, value in zip(owner.args.kwonlyargs, owner.args.kw_defaults, strict=True):
                if argument.arg == "respect_ordering_band":
                    assert isinstance(value, ast.Constant)
                    assert value.value is True
                    defaults.add((path.relative_to(ENGINE).as_posix(), owner.name))
            for call in ast.walk(owner):
                if not isinstance(call, ast.Call):
                    continue
                for keyword in call.keywords:
                    if keyword.arg == "respect_ordering_band":
                        actual.add(
                            (
                                path.relative_to(ENGINE).as_posix(),
                                owner.name,
                                ast.unparse(keyword.value),
                            )
                        )
    assert defaults == {
        ("fight_order.py", "eligible_fight_contexts_for_player"),
        ("stratagems_geometry.py", "_counteroffensive_target_context_error"),
    }
    assert actual == {
        ("phases/fight.py", "request_counteroffensive_if_available", "False"),
        ("stratagems_eligibility.py", "_handler_unavailable_reason", "False"),
        ("stratagems_effect_handlers.py", "_apply_counteroffensive_handler", "False"),
        (
            "stratagems_geometry.py",
            "_counteroffensive_target_context_error",
            "respect_ordering_band",
        ),
    }
