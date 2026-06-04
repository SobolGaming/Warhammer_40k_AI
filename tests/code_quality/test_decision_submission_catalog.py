from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src" / "warhammer40k_core"
CATALOG_PATH = ROOT / "docs" / "DECISION_SUBMISSION_CATALOG.md"

TABLE_HEADER = (
    "| Decision Description | Decision Options | Phase (or Phases the Decision can be made in) | "
    "List of Tests that verify implementation |"
)
RETIRED_PLACEMENT_FALLBACK_TOKENS = (
    "_deterministic_disembark_placement",
    "place_disembark_unit",
    "place_reinforcement_unit",
)


def test_decision_submission_catalog_has_required_sections_and_tables() -> None:
    catalog = CATALOG_PATH.read_text(encoding="utf-8")

    assert "## Finite" in catalog
    assert "## Parameterized" in catalog
    assert catalog.count(TABLE_HEADER) == 2


def test_decision_submission_catalog_lists_runtime_decision_and_proposal_tokens() -> None:
    catalog = CATALOG_PATH.read_text(encoding="utf-8")
    tokens = sorted(
        {
            *_decision_type_tokens(),
            *_proposal_kind_tokens(),
            "FiniteOptionSubmission",
            "ParameterizedSubmission",
            "submit_parameterized_payload",
        }
    )

    missing = [token for token in tokens if f"`{token}`" not in catalog]

    assert not missing, "Decision submission catalog is missing tokens: " + ", ".join(missing)


def test_retired_placement_fallback_decisions_do_not_reappear() -> None:
    catalog = CATALOG_PATH.read_text(encoding="utf-8")
    catalog_matches = [token for token in RETIRED_PLACEMENT_FALLBACK_TOKENS if token in catalog]

    source_matches: list[str] = []
    for path in _source_paths():
        text = path.read_text(encoding="utf-8")
        for token in RETIRED_PLACEMENT_FALLBACK_TOKENS:
            if token in text:
                source_matches.append(f"{path.relative_to(ROOT)}:{token}")

    assert not catalog_matches, "Retired placement fallback tokens in catalog: " + ", ".join(
        catalog_matches
    )
    assert not source_matches, "Retired placement fallback tokens in source: " + ", ".join(
        source_matches
    )


def _decision_type_tokens() -> tuple[str, ...]:
    values: set[str] = set()
    for path in _source_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            value = _string_constant(node.value)
            if value is None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith("DECISION_TYPE"):
                    values.add(value)
    return tuple(sorted(values))


def _proposal_kind_tokens() -> tuple[str, ...]:
    values: set[str] = set()
    for path in _source_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                value = _string_constant(node.value)
                if value is None:
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.endswith(
                        ("_PROPOSAL_KIND", "_PROPOSAL_PAYLOAD_KIND")
                    ):
                        values.add(value)
            if isinstance(node, ast.ClassDef) and node.name == "ProposalKind":
                values.update(_enum_string_values(node))
    return tuple(sorted(values))


def _enum_string_values(node: ast.ClassDef) -> tuple[str, ...]:
    values: set[str] = set()
    for item in node.body:
        if not isinstance(item, ast.Assign):
            continue
        value = _string_constant(item.value)
        if value is not None:
            values.add(value)
    return tuple(sorted(values))


def _string_constant(node: ast.expr) -> str | None:
    if not isinstance(node, ast.Constant):
        return None
    if type(node.value) is not str:
        return None
    return node.value


def _source_paths() -> tuple[Path, ...]:
    return tuple(sorted(path for path in SRC_ROOT.rglob("*.py") if path.is_file()))
