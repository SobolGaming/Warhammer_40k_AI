"""Offline, fail-closed source/clause/owner/assertion inventory for PEVIDENCE.

Assertions are checked against their actual test AST, not a test-name search.
This artifact records both evidence and its limits; it is not CAUDIT-01.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

from tools.core_rules_40k_app_audit import roadmap_rows
from tools.core_rules_order84_capture import fingerprint, source_inventory
from tools.core_rules_order97_models import Inventory

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "data/source_audits/order97"
REPORT = ROOT / "docs/ORDER_97_EVIDENCE_REPORT.md"
REVIEW_SHA256 = "84072e04c70da0e85401def04b07a4b19bed24da5982972d5e9e193787da665e"


class InventoryError(ValueError):
    """The reviewed source or assertion inventory is incomplete or has drifted."""


def _path(reference: str, root: Path) -> Path:
    path = root / reference
    if Path(reference).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise InventoryError(f"Evidence path escapes the repository: {reference}.")
    if not path.is_file():
        raise InventoryError(f"Evidence file is absent: {reference}.")
    return path


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InventoryError(f"Inventory evidence is malformed or unavailable: {path}.") from exc


def assemble_inventory(*, root: Path = ROOT) -> dict[str, Any]:
    """Deterministically join reviewed JSON records; never infer semantic evidence."""
    directory = root / DIRECTORY.relative_to(ROOT)
    raw_manifest = _read(directory / "manifest.json")
    if not isinstance(raw_manifest, dict):
        raise InventoryError("Manifest must be a JSON object.")
    payload = cast(dict[str, Any], raw_manifest)
    payload["sources"] = _read(directory / "selected-sources.json")
    payload["runtime_packages"] = _read(directory / "runtime-reconciliation.json")
    payload["changelog"] = _read(directory / "changelog-reconciliation.json")
    requirements: list[dict[str, Any]] = []
    nonoperative: list[dict[str, Any]] = []
    assertions: dict[tuple[str, str], dict[str, str]] = {}
    trees: dict[str, ast.Module] = {}
    for category in ("00", *payload["categories"]):
        rows = _read(directory / "categories" / f"{category}.json")
        for row in rows:
            if set(row) != {"row_id", "requirements", "nonoperative_blocks"}:
                raise InventoryError("Clause row has missing or unknown fields.")
            for requirement in row["requirements"]:
                requirements.append({"row_id": row["row_id"], **requirement})
                for evidence in requirement["evidence"]:
                    receipt = {
                        "nodeid": evidence["nodeid"],
                        "assertion": evidence["assertion"],
                        "sha256": fingerprint(evidence["assertion"]),
                        "test_ast_sha256": fingerprint(
                            ast.dump(_symbol(evidence["nodeid"], trees, root))
                        ),
                    }
                    assertions[(receipt["nodeid"], receipt["assertion"])] = receipt
            nonoperative.extend(
                {"row_id": row["row_id"], **block} for block in row["nonoperative_blocks"]
            )
    payload["requirements"] = requirements
    payload["nonoperative"] = nonoperative
    payload["assertions"] = [assertions[key] for key in sorted(assertions)]
    return payload


def load_inventory(*, payload: object | None = None, root: Path = ROOT) -> Inventory:
    try:
        inventory = Inventory.model_validate(
            assemble_inventory(root=root) if payload is None else payload
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise InventoryError("Order 97 inventory is malformed or incomplete.") from exc
    validate_inventory(inventory, root=root)
    return inventory


def _symbol(
    reference: str, trees: dict[str, ast.Module], root: Path, *, seen: tuple[str, ...] = ()
) -> ast.AST:
    if reference in seen:
        raise InventoryError(f"Cyclic evidence re-export: {reference}.")
    filename, separator, symbol = reference.replace("::", ":").partition(":")
    if not separator or not symbol:
        raise InventoryError(f"Evidence must identify an exact symbol: {reference}.")
    if filename not in trees:
        try:
            trees[filename] = ast.parse(_path(filename, root).read_text())
        except (OSError, SyntaxError) as exc:
            raise InventoryError(f"Evidence Python cannot be parsed: {filename}.") from exc
    node: ast.AST = trees[filename]
    parts = symbol.replace("::", ".").split(".")
    for index, part in enumerate(parts):
        candidates = [
            child
            for child in ast.iter_child_nodes(node)
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and child.name == part
        ]
        if not candidates and isinstance(node, ast.Module):
            imports = [
                (child.module, alias.name)
                for child in node.body
                if isinstance(child, ast.ImportFrom) and child.level == 0 and child.module
                for alias in child.names
                if (alias.asname or alias.name) == part
            ]
            if len(imports) == 1:
                module, imported = imports[0]
                assert module is not None
                return _symbol(
                    f"src/{module.replace('.', '/')}.py:"
                    + ".".join((imported, *parts[index + 1 :])),
                    trees,
                    root,
                    seen=(*seen, reference),
                )
        if len(candidates) != 1:
            raise InventoryError(f"Evidence symbol does not resolve uniquely: {reference}.")
        node = candidates[0]
    return node


def helper_source_paths(inventory: Inventory, *, root: Path = ROOT) -> set[str]:
    """Retain the shared fixture code that gives assertion ASTs their meaning."""
    pending = {a.nodeid.split("::", 1)[0] for a in inventory.assertions}
    pending.update(
        item.path
        for item in inventory.files
        if item.path.startswith("tests/order97_gap_probes_") and item.path.endswith(".py")
    )
    visited: set[str] = set()
    helpers: set[str] = set(pending)
    for filename in tuple(pending):
        for parent in (root / filename).parents:
            if not parent.is_relative_to(root):
                break
            conftest = parent / "conftest.py"
            if conftest.is_file():
                relative = str(conftest.relative_to(root))
                helpers.add(relative)
                pending.add(relative)
    while pending:
        filename = pending.pop()
        if filename in visited:
            continue
        visited.add(filename)
        tree = ast.parse(_path(filename, root).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if not node.module.startswith("tests."):
                continue
            path = node.module.replace(".", "/") + ".py"
            if not (root / path).is_file():
                path = node.module.replace(".", "/") + "/__init__.py"
            _path(path, root)
            helpers.add(path)
            pending.add(path)
    return helpers


def _unique(values: list[str], label: str) -> set[str]:
    if len(values) != len(set(values)):
        raise InventoryError(f"Duplicated {label}.")
    return set(values)


def _assertion(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        return True
    return isinstance(node, ast.With) and any(
        isinstance(item.context_expr, ast.Call)
        and isinstance(item.context_expr.func, ast.Attribute)
        and isinstance(item.context_expr.func.value, ast.Name)
        and item.context_expr.func.value.id == "pytest"
        and item.context_expr.func.attr == "raises"
        for item in node.items
    )


def validate_inventory(inventory: Inventory, *, root: Path = ROOT) -> None:
    if fingerprint(inventory.model_dump()) != REVIEW_SHA256:
        raise InventoryError("Order 97 reviewed inventory identity changed.")
    if _unique(inventory.categories, "category") != {f"{i:02d}" for i in range(1, 26)}:
        raise InventoryError("All 25 categories are required.")
    _unique([item.path for item in inventory.files], "evidence file")
    for item in inventory.files:
        if hashlib.sha256(_path(item.path, root).read_bytes()).hexdigest() != item.sha256:
            raise InventoryError(f"Pinned evidence file drifted: {item.path}.")
    pinned_paths = {item.path for item in inventory.files}
    if not helper_source_paths(inventory, root=root) <= pinned_paths:
        raise InventoryError("Assertion fixture dependencies must be pinned.")
    if "src/warhammer40k_core/_engine_build_manifest.json" not in pinned_paths:
        raise InventoryError("The reviewed runtime build identity must be pinned.")
    _validate_sources(inventory, root)
    trees: dict[str, ast.Module] = {}
    _validate_requirements(inventory, root, trees)
    _validate_runtime(inventory, root, trees)
    _validate_changelog(inventory, root)
    _validate_followups(inventory, root)


def _validate_sources(inventory: Inventory, root: Path) -> None:
    directory = root / DIRECTORY.relative_to(ROOT)
    original = source_inventory(_read(directory / "source-capture.json"))
    history = _read(root / "data/source_audits/order84/audit.json")["source_inventory"]
    if original != history:
        raise InventoryError("Decoded source capture does not reproduce the historical inventory.")
    if _unique([s.row_id for s in inventory.sources], "source row") != {
        row["row_id"] for row in original
    }:
        raise InventoryError("Selected sources omit or introduce historical rows.")
    originals = {row["row_id"]: row for row in original}
    reviews = _read(root / "data/source_audits/order95/audit.json")["row_reviews"]
    review_categories = {row["row_id"]: row["review_category"] for row in reviews}
    for source in inventory.sources:
        old = originals[source.row_id]
        if (
            any(
                getattr(source, field) != old[field]
                for field in ("category", "locator", "title", "occurrence")
            )
            or source.review_category != review_categories[source.row_id]
        ):
            raise InventoryError(f"Source locator or review category drifted: {source.row_id}.")
        if source.locator != "15.11" and (
            source.source_sha256 != old["source_sha256"]
            or source.selected_provider != "Game Datamissions"
            or source.historical_blocks is not None
        ):
            raise InventoryError(f"Unreviewed source substitution: {source.row_id}.")
        if source.historical_source_row_sha256 != fingerprint(old):
            raise InventoryError(f"Historical source row drifted: {source.row_id}.")
        blocks = source.historical_blocks if source.historical_blocks is not None else source.blocks
        if [{k: v for k, v in b.model_dump().items() if k != "value"} for b in blocks] != old[
            "blocks"
        ]:
            raise InventoryError(f"Historical blocks drifted: {source.row_id}.")
        for block in (*source.blocks, *(source.historical_blocks or [])):
            if fingerprint(block.value) != block.sha256:
                raise InventoryError(f"Source transcription fingerprint drifted: {source.row_id}.")
        if [block.ordinal for block in source.blocks] != list(range(1, len(source.blocks) + 1)):
            raise InventoryError("Selected source block ordinals are incomplete.")
    heroic = next(s for s in inventory.sources if s.locator == "15.11")
    complete = _read(root / "data/source_audits/order94/audit.json")
    selected = [c["selected_text"] for c in complete["clause_reviews"]]
    if (
        [b.value for b in heroic.blocks] != selected
        or heroic.selected_provider != "40k.app Order94"
        or heroic.source_sha256 != fingerprint(selected)
    ):
        raise InventoryError("Heroic Intervention must select the complete Order 94 observation.")


def _validate_requirements(inventory: Inventory, root: Path, trees: dict[str, ast.Module]) -> None:
    _unique([r.requirement_id for r in inventory.requirements], "requirement ID")
    coverage: dict[str, set[int]] = {source.row_id: set() for source in inventory.sources}
    for requirement in inventory.requirements:
        if (
            requirement.row_id not in coverage
            or not requirement.source_blocks
            or not requirement.owners
            or not requirement.summary.strip()
            or len(set(requirement.source_blocks)) != len(requirement.source_blocks)
            or len(set(requirement.owners)) != len(requirement.owners)
        ):
            raise InventoryError(
                "Every operative requirement needs a source span and engine owner."
            )
        coverage[requirement.row_id].update(requirement.source_blocks)
        for owner in requirement.owners:
            _symbol(owner, trees, root)
        for link in requirement.evidence:
            if "::test_" not in link.nodeid or not link.proves.strip():
                raise InventoryError("Evidence must name an actual test and explain its assertion.")
        if not requirement.evidence and not any(
            text.startswith(("Evidence gap:", "Gameplay gap:", "Source gap:"))
            for text in requirement.qualifications
        ):
            raise InventoryError(
                "An uncovered requirement must explicitly identify its evidence gap."
            )
    _unique(
        [fingerprint(block.model_dump(exclude={"reason"})) for block in inventory.nonoperative],
        "nonoperative disposition",
    )
    for block in inventory.nonoperative:
        if (
            block.row_id not in coverage
            or not block.reason.strip()
            or not block.source_blocks
            or len(block.source_blocks) != len(set(block.source_blocks))
        ):
            raise InventoryError(
                "Nonoperative blocks require an explicit source and classification."
            )
        coverage[block.row_id].update(block.source_blocks)
    for source in inventory.sources:
        if coverage[source.row_id] != {b.ordinal for b in source.blocks}:
            raise InventoryError(f"Unclassified or invented source block: {source.row_id}.")
    expected = {(e.nodeid, e.assertion) for r in inventory.requirements for e in r.evidence}
    receipts = [(a.nodeid, a.assertion) for a in inventory.assertions]
    if len(receipts) != len(set(receipts)) or set(receipts) != expected:
        raise InventoryError("Assertion receipt inventory is incomplete or duplicated.")
    for evidence in inventory.assertions:
        node = _symbol(evidence.nodeid, trees, root)
        statements = {ast.unparse(child) for child in ast.walk(node) if _assertion(child)}
        try:
            cited = ast.parse(evidence.assertion)
        except SyntaxError as exc:
            raise InventoryError(f"Invalid assertion syntax: {evidence.nodeid}.") from exc
        if (
            len(cited.body) != 1
            or not _assertion(cited.body[0])
            or ast.unparse(cited.body[0]) not in statements
            or evidence.sha256 != fingerprint(evidence.assertion)
            or evidence.test_ast_sha256 != fingerprint(ast.dump(node))
        ):
            raise InventoryError(f"Cited assertion is absent or changed: {evidence.nodeid}.")


def _validate_runtime(inventory: Inventory, root: Path, trees: dict[str, ast.Module]) -> None:
    old = _read(root / "data/source_audits/order95/audit.json")["retained_core_packages"]
    if _unique([p.path for p in inventory.runtime_packages], "runtime package") != {
        p["path"] for p in old
    }:
        raise InventoryError("Runtime package inventory is incomplete.")
    sources = {source.row_id for source in inventory.sources}
    for package in inventory.runtime_packages:
        raw = _path(package.path, root).read_bytes()
        current = json.loads(raw)
        if (
            hashlib.sha256(raw).hexdigest() != package.sha256
            or current["package_hash"] != package.package_hash
            or current["source_package_id"] != package.source_package_id
            or current["source_version"] != package.source_version
            or fingerprint({key: value for key, value in current.items() if key != "rules"})
            != package.metadata_sha256
        ):
            raise InventoryError(f"Pinned runtime package drifted: {package.path}.")
        rows = {row["source_id"]: row for row in current["rules"]}
        if _unique([r.source_id for r in package.rules], "runtime source ID") != set(rows):
            raise InventoryError("Runtime source rows are missing or duplicated.")
        for rule in package.rules:
            row = rows[rule.source_id]
            for field in (
                "section_id",
                "source_text",
                "transcription_sha256",
                "load_support_status",
                "semantic_execution_status",
                "runtime_consumer_ids",
            ):
                if getattr(rule, field) != row[field]:
                    raise InventoryError(
                        f"Runtime source receipt drifted: {rule.source_id}:{field}."
                    )
            if not rule.selected_rows or not set(rule.selected_rows) <= sources or not rule.review:
                raise InventoryError("Runtime rows need explicit selected-source reconciliation.")
            if not set(rule.retired_consumer_successors) <= set(rule.runtime_consumer_ids) or any(
                not successors for successors in rule.retired_consumer_successors.values()
            ):
                raise InventoryError("Retired consumers require declared IDs and real successors.")
            if rule.relation == "superseded" and (
                rule.runtime_consumer_ids or rule.semantic_execution_status != "not_certified"
            ):
                raise InventoryError("Superseded source rows cannot claim semantic execution.")
            for consumer in rule.runtime_consumer_ids:
                if consumer in rule.retired_consumer_successors:
                    if rule.relation != "source_repair_required":
                        raise InventoryError("Stale declared consumer IDs require source repair.")
                    for successor in rule.retired_consumer_successors[consumer]:
                        _symbol(successor, trees, root)
                else:
                    module, separator, symbol = consumer.partition(":")
                    filename = f"src/{module.replace('.', '/')}.py"
                    if separator:
                        _symbol(f"{filename}:{symbol}", trees, root)
                    else:
                        _path(filename, root)


def _validate_changelog(inventory: Inventory, root: Path) -> None:
    versions = _read(root / DIRECTORY.relative_to(ROOT) / "changelog-capture.json")
    expected = {
        f"{v['version']}:{kind}:{i}": entry
        for v in versions
        for kind, field in (("change", "changes"), ("note", "notes"))
        for i, entry in enumerate(v.get(field, []), 1)
    }
    if _unique([entry.entry_id for entry in inventory.changelog], "changelog entry") != set(
        expected
    ):
        raise InventoryError("Changelog disposition inventory is incomplete.")
    requirements = {r.requirement_id: r.row_id for r in inventory.requirements}
    for entry in inventory.changelog:
        original = expected[entry.entry_id]
        expected_kind = (
            cast(dict[str, Any], original)["kind"] if isinstance(original, dict) else "note"
        )
        if (
            entry.entry != original
            or entry.entry_sha256 != fingerprint(entry.entry)
            or entry.version != entry.entry_id.split(":", 1)[0]
            or entry.kind != expected_kind
        ):
            raise InventoryError("Changelog transcription differs from the retained capture.")
        if (
            len(entry.source_rows) != len(set(entry.source_rows))
            or not set(entry.source_rows) <= {source.row_id for source in inventory.sources}
            or not entry.summary.strip()
            or not entry.disposition.strip()
            or not entry.qualification.strip()
        ):
            raise InventoryError("Changelog dispositions require valid selected sources and scope.")
        if not set(entry.requirement_ids) <= set(requirements):
            raise InventoryError("Changelog references unknown requirements.")
        if any(requirements[r] not in entry.source_rows for r in entry.requirement_ids):
            raise InventoryError("Changelog clause references disagree with its selected sources.")
        if entry.source_rows and not entry.requirement_ids:
            raise InventoryError("Operative changelog entries must resolve to selected clauses.")


def _validate_followups(inventory: Inventory, root: Path) -> None:
    followups = inventory.followups
    _unique([f.finding_id for f in followups], "follow-up finding")
    required = {
        r.requirement_id
        for r in inventory.requirements
        if not r.evidence
        or any(
            q.startswith(("Evidence gap:", "Gameplay gap:", "Source gap:"))
            for q in r.qualifications
        )
    }
    scheduled = {r for f in followups for r in f.requirement_ids}
    known_requirements = {r.requirement_id for r in inventory.requirements}
    known_sources = {r.source_id for p in inventory.runtime_packages for r in p.rules}
    for finding in followups:
        if (
            not finding.description.strip()
            or not (finding.requirement_ids or finding.runtime_source_ids)
            or not set(finding.requirement_ids) <= known_requirements
            or not set(finding.runtime_source_ids) <= known_sources
        ):
            raise InventoryError("Follow-ups must identify existing affected clauses or sources.")
    if not required <= scheduled:
        raise InventoryError("Uncovered clauses require an owned prerequisite before PFINAL.")
    source_gaps = {
        r.source_id
        for p in inventory.runtime_packages
        for r in p.rules
        if r.relation == "source_repair_required"
    }
    if not source_gaps <= {r for f in followups for r in f.runtime_source_ids}:
        raise InventoryError("Unreconciled source rows require a scheduled source repair.")
    planned = roadmap_rows((root / "docs/CORE_RULES_REMEDIATION_ROADMAP.md").read_text())
    owners = {finding: row for row in planned for finding in row.finding_ids}
    for finding in followups:
        if (
            finding.finding_id not in owners
            or owners[finding.finding_id].pr_id != finding.pr_id
            or finding.pr_id not in planned[-1].prerequisites
        ):
            raise InventoryError(f"Follow-up is not a PFINAL prerequisite: {finding.finding_id}.")


def markdown(inventory: Inventory) -> str:
    lines = [
        "# Order 97 clause evidence inventory",
        "",
        "Generated by `uv run python -m tools.core_rules_order97_inventory`.",
        "",
        "This inventory is not a Core Rules compliance certificate. CAUDIT-01 stays open.",
        "Historical Orders 84 and 95 retain their negative dispositions.",
        "Assertion-bound includes qualified and negative evidence; "
        "it does not mean the clause passes.",
        "",
        "| Category | Operative requirements | Assertion-bound | Explicit repair/proof gaps |",
        "|---|---:|---:|---:|",
    ]
    categories = {s.row_id: s.review_category for s in inventory.sources}
    for category in inventory.categories:
        rows = [r for r in inventory.requirements if categories[r.row_id] == category]
        bound = sum(bool(r.evidence) for r in rows)
        gaps = sum(
            not r.evidence
            or any(
                q.startswith(("Evidence gap:", "Gameplay gap:", "Source gap:"))
                for q in r.qualifications
            )
            for r in rows
        )
        lines.append(f"| {category} | {len(rows)} | {bound} | {gaps} |")
    relations = Counter(r.relation for p in inventory.runtime_packages for r in p.rules)
    lines.extend(["", "## Pinned runtime reconciliation", ""])
    lines.extend(f"- {key}: {value}" for key, value in sorted(relations.items()))
    lines.extend(["", "## Qualifications", ""])
    lines.extend(f"- {text}" for text in inventory.qualifications)
    lines.extend(["", "## Required follow-ups before PFINAL", ""])
    lines.extend(f"- **{f.finding_id} / {f.pr_id}:** {f.description}" for f in inventory.followups)
    lines.extend(["", "## Clause lookup", ""])
    for requirement in inventory.requirements:
        evidence = (
            "; ".join(f"`{e.nodeid}` ({e.role}: {e.proves})" for e in requirement.evidence)
            or "**Evidence gap; prerequisite repair required.**"
        )
        lines.extend(
            [
                f"### {requirement.requirement_id}",
                "",
                f"Source `{requirement.row_id}`, blocks {requirement.source_blocks}: "
                + requirement.summary,
                "",
                "Owners: " + ", ".join(f"`{o}`" for o in requirement.owners) + ".",
                "",
                evidence,
            ]
        )
        if requirement.source_detail:
            lines.append("\nSource detail: " + requirement.source_detail)
        repairs = [
            f for f in inventory.followups if requirement.requirement_id in f.requirement_ids
        ]
        if repairs:
            lines.append(
                "\nRequired before PFINAL: "
                + ", ".join(f"**{f.finding_id} / {f.pr_id}**" for f in repairs)
                + "."
            )
        lines.extend(f"\nQualification: {q}" for q in requirement.qualifications)
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    inventory = load_inventory()
    rendered = markdown(inventory)
    if args.check:
        if not REPORT.is_file() or REPORT.read_text() != rendered:
            raise InventoryError("Order 97 generated report is stale.")
    else:
        REPORT.write_text(rendered)
    print(f"Order 97: {len(inventory.requirements)} requirements; CAUDIT-01 remains open.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
