from __future__ import annotations

import ast
from pathlib import Path
from typing import cast

import pytest

from warhammer40k_core.engine.decision_dispatch import (
    DecisionDispatchHandler,
    DecisionDispatchRegistry,
    DecisionSubmissionKind,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import (
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.weapon_abilities import WEAPON_ABILITY_SELECTION_DECISION_TYPE

ROOT = Path(__file__).resolve().parents[2]
ENGINE_ROOT = ROOT / "src" / "warhammer40k_core" / "engine"
ADAPTER_CONTRACT = ROOT / "docs" / "ADAPTER_DECISION_CONTRACT.md"

_NESTED_DECISION_TYPE_ALLOWLIST = {
    WEAPON_ABILITY_SELECTION_DECISION_TYPE: (
        "Nested allowlist entry for duplicate weapon-ability descriptor disambiguation in "
        "shooting declarations. Tesseract Vault C'tan Power weapon selection is emitted "
        "inside submit_shooting_declaration using "
        "DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT."
    ),
}


def test_engine_decision_type_constants_are_registered_or_documented_nested() -> None:
    decision_types = _engine_decision_type_constants()
    registered = set(
        GameLifecycle()._decision_dispatch_registry.registered_decision_types()  # pyright: ignore[reportPrivateUsage]
    )
    nested = set(_NESTED_DECISION_TYPE_ALLOWLIST)

    assert nested == {WEAPON_ABILITY_SELECTION_DECISION_TYPE}
    assert nested <= decision_types
    assert registered <= decision_types
    assert decision_types - registered == nested


def test_nested_weapon_ability_allowlist_is_documented_in_adapter_contract() -> None:
    contract = ADAPTER_CONTRACT.read_text(encoding="utf-8")

    assert WEAPON_ABILITY_SELECTION_DECISION_TYPE in contract
    assert "nested-decision allowlist" in contract
    assert "DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT" in contract


def test_decision_type_constant_scan_includes_annotated_assignments() -> None:
    tree = ast.parse(
        """
from typing import Final

ANNOTATED_DECISION_TYPE: Final = "annotated_decision"
PLAIN_DECISION_TYPE = "plain_decision"
NOT_A_DECISION: Final = "ignored"
""",
    )

    assert _decision_type_constants_from_tree(tree) == {
        "annotated_decision",
        "plain_decision",
    }


def test_decision_dispatch_registry_internal_mapping_is_immutable() -> None:
    handler = DecisionDispatchHandler(
        decision_type="immutable_registry_test_decision",
        pre_validator=_always_valid,
        applier=_unused_applier,
    )
    registry = DecisionDispatchRegistry.from_handlers(
        (handler,),
        submission_kinds_by_decision_type={handler.decision_type: DecisionSubmissionKind.FINITE},
    )
    handlers = cast(
        dict[str, DecisionDispatchHandler],
        object.__getattribute__(registry, "_handlers_by_decision_type"),
    )

    with pytest.raises(TypeError):
        handlers["other_decision"] = handler


def test_decision_dispatch_registry_rejects_incomplete_or_drifted_submission_metadata() -> None:
    handler = DecisionDispatchHandler(
        decision_type="submission_metadata_test_decision",
        pre_validator=_always_valid,
        applier=_unused_applier,
    )
    with pytest.raises(GameLifecycleError, match="must exactly cover"):
        DecisionDispatchRegistry.from_handlers(
            (handler,),
            submission_kinds_by_decision_type={},
        )

    registry = DecisionDispatchRegistry.from_handlers(
        (handler,),
        submission_kinds_by_decision_type={handler.decision_type: DecisionSubmissionKind.FINITE},
    )
    parameterized_request = DecisionRequest(
        request_id="submission-metadata-request",
        decision_type=handler.decision_type,
        actor_id="player-a",
        payload={},
        options=(parameterized_decision_option(),),
    )
    with pytest.raises(GameLifecycleError, match="submission kind drifted"):
        registry.validate_request_submission_kind(parameterized_request)

    finite_request = DecisionRequest(
        request_id="submission-metadata-finite-request",
        decision_type=handler.decision_type,
        actor_id="player-a",
        payload={},
        options=(DecisionOption(option_id="finite", label="Finite"),),
    )
    registry.validate_request_submission_kind(finite_request)


def _engine_decision_type_constants() -> set[str]:
    values: set[str] = set()
    for path in sorted(ENGINE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        values.update(_decision_type_constants_from_tree(tree))
    return values


def _decision_type_constants_from_tree(tree: ast.Module) -> set[str]:
    values: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            value = _string_constant(node.value)
            if value is None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith("DECISION_TYPE"):
                    values.add(value)
        if isinstance(node, ast.AnnAssign):
            value = _string_constant(node.value)
            if (
                value is not None
                and isinstance(node.target, ast.Name)
                and node.target.id.endswith("DECISION_TYPE")
            ):
                values.add(value)
    return values


def _string_constant(node: ast.expr | None) -> str | None:
    if not isinstance(node, ast.Constant):
        return None
    if type(node.value) is not str:
        return None
    return node.value


def _always_valid(
    _request: DecisionRequest,
    _result: DecisionResult,
) -> LifecycleStatus | None:
    return None


def _unused_applier(
    _record: DecisionRecord,
    _result: DecisionResult,
) -> LifecycleStatus:
    raise AssertionError("Registry immutability test must not call the applier.")
