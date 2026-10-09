"""Complete current source/owner/assertion inventory; runtime receipts stay separate.

This audit reads live files directly, never the Order97 historical resolver.
Exact static bindings cannot establish rules correctness or runtime pass by
themselves. Delivery requires the complete current cohort and two independent
exact-final reviews under SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from tools.core_rules_order84_capture import capture_literals, fingerprint, source_inventory

ROOT = Path(__file__).resolve().parents[1]
AUDIT = Path("data/source_audits/order135")
OUTPUT = AUDIT / "current-inventory.json"
SELECTED_SHA256 = "96f19958884c07990dba01c1506dea7a23793e1501c79f25a7b4598f00f23971"
RETAINED_SHA256 = "a473e270f76d9556c25e68477abf040bc8a7f1a6c21c1fd9d9a0fa960edd627f"
RECONCILIATION_SHA256 = "805d993c40aed49ac57d9f645164fa8ad3136060bfe4332c5f7271c0b59d1bab"
CAPTURE = Path("data/source_audits/v963_shock/captures/core-page.js")
CAPTURE_SHA256 = "8b7e7a4004f8a55b17305013f181bf25933dff763e6737af407da254c5656026"


class CurrentAuditError(ValueError):
    """A required current source/owner/assertion input is incomplete or drifted."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(root: Path, path: Path) -> Any:
    return json.loads((root / path).read_bytes())


class LiveSymbols:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.trees: dict[str, ast.Module] = {}
        self.files: dict[str, dict[str, Any]] = {}
        self.owners: dict[str, dict[str, Any]] = {}
        self.tests: dict[str, dict[str, Any]] = {}

    def tree(self, filename: str) -> ast.Module:
        if filename not in self.trees:
            raw = (self.root / filename).read_bytes()
            self.files[filename] = {"sha256": _sha(raw), "bytes": len(raw)}
            self.trees[filename] = ast.parse(raw, filename=filename)
        return self.trees[filename]

    def symbol(self, reference: str, seen: tuple[str, ...] = ()) -> tuple[str, ast.AST]:
        if reference in seen:
            raise CurrentAuditError("Cyclic live reexport: " + reference)
        filename, separator, name = reference.replace("::", ":").partition(":")
        if not separator or not name:
            raise CurrentAuditError("Malformed current symbol: " + reference)
        node: ast.AST = self.tree(filename)
        parts = name.split(".")
        for index, part in enumerate(parts):
            choices = [
                child
                for child in ast.iter_child_nodes(node)
                if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name == part
            ]
            if not choices and isinstance(node, ast.Module):
                imports = [
                    (child.module, alias.name)
                    for child in node.body
                    if isinstance(child, ast.ImportFrom) and child.level == 0 and child.module
                    for alias in child.names
                    if (alias.asname or alias.name) == part
                ]
                if len(imports) == 1:
                    module, imported = imports[0]
                    return self.symbol(
                        "src/"
                        + module.replace(".", "/")
                        + ".py:"
                        + ".".join((imported, *parts[index + 1 :])),
                        (*seen, reference),
                    )
            if len(choices) != 1:
                raise CurrentAuditError("Unresolved current symbol: " + reference)
            node = choices[0]
        return filename, node

    def owner(self, reference: str) -> str:
        if reference not in self.owners:
            filename, node = self.symbol(reference)
            self.owners[reference] = {
                "resolved_path": filename,
                "symbol_ast_sha256": _sha(ast.dump(node).encode()),
                "file_sha256": self.files[filename]["sha256"],
            }
        return reference

    def test(self, reference: str) -> dict[str, Any]:
        if reference not in self.tests:
            filename, node = self.symbol(reference)
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                raise CurrentAuditError("Current test is not a function: " + reference)
            assertions = [
                ast.unparse(child)
                for child in ast.walk(node)
                if isinstance(child, ast.Assert)
                or (
                    isinstance(child, ast.With)
                    and any(
                        isinstance(item.context_expr, ast.Call)
                        and isinstance(item.context_expr.func, ast.Attribute)
                        and isinstance(item.context_expr.func.value, ast.Name)
                        and item.context_expr.func.value.id == "pytest"
                        and item.context_expr.func.attr == "raises"
                        for item in child.items
                    )
                )
            ]
            self.tests[reference] = {
                "resolved_path": filename,
                "symbol_ast_sha256": _sha(ast.dump(node).encode()),
                "file_sha256": self.files[filename]["sha256"],
                "assertions": assertions,
                "complete_current_body": ast.unparse(node),
                "assertion_mode": "inline"
                if assertions
                else "delegated helper; full file/body retained for semantic review",
                "runtime_pass_claimed": False,
            }
        return self.tests[reference]

    def file_tests(self, filename: str) -> list[str]:
        return [
            filename + "::" + node.name
            for node in self.tree(filename).body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
        ]


def visibility_source_registration(root: Path) -> dict[str, Any]:
    audit = _read(root, AUDIT / "visibility-source.audit.json")
    raw = (root / CAPTURE).read_bytes()
    if _sha(raw) != CAPTURE_SHA256:
        raise CurrentAuditError("Retained complete source capture drifted.")
    capture = capture_literals(raw.decode())
    records = [r for r in capture["faqs"] if r["id"] == "9638115f-b94b-4d05-ba62-df9fba2805ac"]
    if records != [audit["selected_record"]]:
        raise CurrentAuditError("Complete visibility FAQ differs from retained capture.")
    (row,) = audit["rows"]
    expected = dict(row)
    recorded = expected.pop("source_observation_sha256")
    if (
        fingerprint(expected) != recorded
        or _sha(audit["source_text"].encode()) != row["transcription_sha256"]
    ):
        raise CurrentAuditError("Visibility source observation/transcription drifted.")
    package_path = (
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_other_concepts_2026_08/artifacts/package.json"
    )
    package = _read(root, Path(package_path))
    original = _read(root, AUDIT / "baseline" / (package_path + ".txt"))
    if package["rules"][:4] != original["rules"] or package["evidence"][:8] != original["evidence"]:
        raise CurrentAuditError("Original Other Concepts clauses or observations changed.")
    if len(package["rules"]) != 5 or len(package["evidence"]) != 10:
        raise CurrentAuditError("Visibility source append is incomplete or duplicated.")
    rule = package["rules"][-1]
    review = package["evidence"][-2]
    evidence = package["evidence"][-1]
    if (
        rule["source_id"] != row["rule_source_id"]
        or rule["source_text"] != audit["source_text"]
        or evidence["review_audit_source_observation_sha256"] != recorded
        or evidence["capture_sha256"] is not None
        or evidence["capture_artifact_path"] is not None
        or evidence["observed_at"] != row["observed_at"]
        or evidence["app_version"] is not None
        or evidence["app_build"] is not None
        or review["rule_source_id"] != row["rule_source_id"]
        or review["evidence_kind"] != "project_reviewed_app_transcription"
        or review["authority"] != "unverified_transcription_only"
        or review["transcription_sha256"] != row["transcription_sha256"]
        or review["runtime_consumer_ids"] != rule["runtime_consumer_ids"]
    ):
        raise CurrentAuditError("Current visibility package/source identity drifted.")
    provider_path = package_path.removesuffix("artifacts/package.json") + "__init__.py"
    provider_raw = (root / provider_path).read_bytes()
    tree = ast.parse(provider_raw)
    compositions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "source_packages"
    ]
    if len(compositions) != 1 or [
        ast.unparse(node.value) if node.value is not None else ""
        for node in ast.walk(compositions[0])
        if isinstance(node, ast.Return)
    ] != ["(source_package(), battlefield_edge_source_package())"]:
        raise CurrentAuditError("Mandatory original/current source-provider composition drifted.")
    registry = _read(root, Path("src/warhammer40k_core/rules/source_authority_registry.json"))
    (scope,) = [s for s in registry["scopes"] if s["scope_id"] == "warhammer_40000_11th_core_rules"]
    (extension,) = scope["source_package_extensions"]
    if (
        len(scope["source_packages"]) != 54
        or extension["package_name"] != "gw-11e-core-other-concepts-battlefield-edge"
        or extension["version"] != "maintained-app-mirror-observed-2026-10-01"
        or extension["allowed_rule_source_ids"] != [row["rule_source_id"]]
        or not extension["catalog_sha256"]
    ):
        raise CurrentAuditError("Current source-package authorization is incomplete.")
    return {
        "audit": audit,
        "package_sha256": _sha((root / package_path).read_bytes()),
        "preserved_original_rules": 4,
        "preserved_original_observations": 8,
        "mandatory_provider_composition": {
            "path": provider_path,
            "sha256": _sha(provider_raw),
            "complete_body": ast.unparse(compositions[0]),
            "current_authorization": extension,
            "required_package_count": 2,
            "current_rule_count": 1,
            "current_observation_count": 2,
        },
    }


def build(root: Path = ROOT) -> dict[str, Any]:
    selected_raw = (root / AUDIT / "selected-inputs.json").read_bytes()
    if _sha(selected_raw) != SELECTED_SHA256:
        raise CurrentAuditError("Authenticated complete selected inputs drifted.")
    selected = json.loads(selected_raw)
    retained_raw = (root / AUDIT / "retained-current-sources.json").read_bytes()
    if _sha(retained_raw) != RETAINED_SHA256:
        raise CurrentAuditError("Authenticated complete retained source packet drifted.")
    retained = json.loads(retained_raw)
    if retained["current_source_inventory"] != source_inventory(
        retained["full_current_core_capture"]
    ):
        raise CurrentAuditError("Retained current source inventory is incomplete.")
    if (
        fingerprint(retained["full_current_core_capture"])
        != retained["current_capture_fingerprint"]
    ):
        raise CurrentAuditError("Complete current source capture fingerprint drifted.")
    bindings = _read(root, AUDIT / "current-bindings.json")
    reconciliation_raw = (root / AUDIT / "source-reconciliation.json").read_bytes()
    if _sha(reconciliation_raw) != RECONCILIATION_SHA256:
        raise CurrentAuditError("Authenticated complete source reconciliation drifted.")
    reconciliation = json.loads(reconciliation_raw)
    old_sources = {r["row_id"]: r for r in selected["selected_sources"]}
    current_sources = {r["row_id"]: r for r in retained["current_source_inventory"]}
    if (
        len(old_sources) != 345
        or len(current_sources) != 350
        or set(old_sources) - set(current_sources)
    ):
        raise CurrentAuditError("Complete old/current source row coverage drifted.")
    changed = {
        rid
        for rid in old_sources
        if old_sources[rid]["source_sha256"] != current_sources[rid]["source_sha256"]
    }
    if (
        reconciliation["unchanged_rows"] != len(old_sources) - len(changed)
        or {row["row_id"] for row in reconciliation["changed_source_rows"]} != changed
        or any(
            row["previous"] != old_sources[row["row_id"]]
            or row["current"] != current_sources[row["row_id"]]
            for row in reconciliation["changed_source_rows"]
        )
        or sorted(reconciliation["new_complete_faqs"], key=lambda row: row["id"])
        != sorted(
            [
                row
                for row in retained["full_current_core_capture"]["faqs"]
                if "faq:" + row["id"] in set(current_sources) - set(old_sources)
            ],
            key=lambda row: row["id"],
        )
    ):
        raise CurrentAuditError("Complete changed/added source reconciliation differs from inputs.")
    live = LiveSymbols(root)
    rows = []
    categories = {
        "00": _read(root, Path("data/source_audits/order97/categories/00.json")),
        **selected["categories"],
    }
    changed_links = []
    no_original = []
    for category, source_rows in categories.items():
        for source_row in source_rows:
            rid = source_row["row_id"]
            if rid not in old_sources:
                raise CurrentAuditError("Requirement has no complete selected source: " + rid)
            for requirement in source_row["requirements"]:
                qid = requirement["requirement_id"]
                nodes = []
                evidence = []
                for original in requirement["evidence"]:
                    if rid == "rule:18:18.07:1" and original["nodeid"] in {
                        "tests/unit/test_phase10q_transports.py::"
                        "test_order62_transport_only_engagement_does_not_force_passenger_fight",
                        "tests/unit/test_phase10q_transports.py::"
                        "test_shock_disembark_routes_opponent_through_canonical_fight_activation_and_replay",
                    }:
                        if qid not in bindings["requirement_bindings"]:
                            raise CurrentAuditError("Superseded Shock clause lacks live successor.")
                        evidence.append(
                            {
                                **original,
                                "original_assertion_present": False,
                                "disposition": (
                                    "Historical pre-V963 semantics; original source/evidence "
                                    "is retained and superseded for current gameplay."
                                ),
                            }
                        )
                        changed_links.append({"requirement_id": qid, "original": original})
                        continue
                    test = live.test(original["nodeid"])
                    present = (
                        ast.unparse(ast.parse(original["assertion"]).body[0]) in test["assertions"]
                    )
                    evidence.append({**original, "original_assertion_present": present})
                    nodes.append(original["nodeid"])
                    if not present:
                        changed_links.append({"requirement_id": qid, "original": original})
                        if original["nodeid"].endswith(
                            "::test_category07_facade_round_turn_phase_order_and_restore"
                        ):
                            if "assert windows == expected" not in test["assertions"]:
                                raise CurrentAuditError(
                                    "Current complete phase-window assertion absent."
                                )
                        elif qid not in bindings["requirement_bindings"]:
                            raise CurrentAuditError(
                                "Changed assertion has no current successor: " + qid
                            )
                if not requirement["evidence"]:
                    no_original.append(qid)
                    if qid not in bindings["requirement_bindings"]:
                        raise CurrentAuditError("Unlinked clause has no current successor: " + qid)
                successor = bindings["requirement_bindings"].get(qid)
                if successor:
                    nodes.extend(successor["current_test_nodes"])
                supersession = bindings["source_supersessions"].get(rid)
                if supersession:
                    for filename in supersession["test_files"]:
                        nodes.extend(live.file_tests(filename))
                for reference in dict.fromkeys(nodes):
                    live.test(reference)
                rows.append(
                    {
                        "category": category,
                        "row_id": rid,
                        "original_requirement": requirement,
                        "selected_source_sha256": old_sources[rid]["source_sha256"],
                        "retained_current_source_sha256": current_sources[rid]["source_sha256"],
                        "current_owners": [
                            live.owner(o)
                            for o in dict.fromkeys(
                                [
                                    *requirement["owners"],
                                    *(successor or {}).get("current_additional_owners", []),
                                ]
                            )
                        ],
                        "original_evidence_dispositions": evidence,
                        "current_test_nodes": list(dict.fromkeys(nodes)),
                        "current_successor": successor,
                        "current_source_disposition": supersession,
                        "runtime_pass_claimed": False,
                    }
                )
    if len(rows) != 1078 or len(no_original) != 34 or len(changed_links) != 14:
        raise CurrentAuditError("Complete original obligation/link inventory drifted.")
    additions = []
    for faq_id, binding in bindings["current_new_faqs"].items():
        source = current_sources["faq:" + faq_id]
        nodes = [node for filename in binding["test_files"] for node in live.file_tests(filename)]
        for node in nodes:
            live.test(node)
        additions.append(
            {
                "complete_source": source,
                **binding,
                "current_owners": [live.owner(o) for o in binding["owners"]],
                "current_test_nodes": nodes,
                "runtime_pass_claimed": False,
            }
        )
    if {"faq:" + key for key in bindings["current_new_faqs"]} != set(current_sources) - set(
        old_sources
    ):
        raise CurrentAuditError("New complete FAQ reconciliation is incomplete.")
    september = _read(root, Path("data/source_audits/order95/audit.json"))["september10_reviews"]
    changelog = _read(root, Path("data/source_audits/order97/changelog-reconciliation.json"))
    package_root = root / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
    packages = {
        path.relative_to(root).as_posix(): {
            "sha256": _sha(path.read_bytes()),
            "bytes": len(path.read_bytes()),
            "complete_package": json.loads(path.read_bytes()),
            "runtime_pass_claimed": False,
        }
        for path in sorted(package_root.rglob("package.json"))
    }
    return {
        "schema": "order135-complete-current-clause-inventory-v1",
        "base": selected["base"],
        "acceptance": selected["acceptance"],
        "selected_inputs_sha256": SELECTED_SHA256,
        "complete_selected_sources": selected["selected_sources"],
        "complete_current_sources": retained,
        "complete_current_source_packages": packages,
        "current_source_reconciliation": reconciliation,
        "requirements": rows,
        "new_complete_faq_bindings": additions,
        "owners": live.owners,
        "tests": live.tests,
        "current_files_observed": live.files,
        "september10_review_dispositions": september,
        "complete_historical_changelog_dispositions": changelog,
        "visibility_source_registration": visibility_source_registration(root),
        "conditional_core_acceptance": _read(root, AUDIT / "conditional-core-acceptance.json"),
        "approved_visibility_scope": _read(root, AUDIT / "visibility-scope-approval.json"),
        "approved_los_rng_compatibility": _read(
            root, AUDIT / "los-rng-compatibility-approval.json"
        ),
        "authentic_base_rng_control": _read(root, AUDIT / "los-rng-base-control.json"),
        "approved_b01_boundary_persistence_repair": _read(
            root, AUDIT / "b01-explicit-repair-approval.json"
        ),
        "approved_b02_core_counteroffensive_timing_repair": _read(
            root, AUDIT / "b02-explicit-repair-approval.json"
        ),
        "approved_b03_shared_live_context_boundary_repair": _read(
            root, AUDIT / "b03-explicit-repair-approval.json"
        ),
        "approved_b03_type_safe_same_boundary_clarification": _read(
            root, AUDIT / "b03-type-safe-boundary-user-clarification.json"
        ),
        "approved_b04_b05_transport_repairs": _read(
            root, AUDIT / "b04-b05-explicit-repair-approval.json"
        ),
        "approved_counter_band_eligibility_repair": _read(
            root, AUDIT / "counter-band-explicit-repair-approval.json"
        ),
        "approved_fight_transition_repair": _read(
            root, AUDIT / "fight-transition-explicit-repair-approval.json"
        ),
        "approved_pass_eligibility_repair_and_assertion_exception": _read(
            root, AUDIT / "pass-explicit-repair-and-assertion-approval.json"
        ),
        "approved_d02_d03_repairs_and_assertion_exceptions": _read(
            root, AUDIT / "d02-d03-explicit-repair-and-assertion-approval.json"
        ),
        "pr576_owner_cutoff_and_follow_up_inventory": _read(
            root, AUDIT / "pr576-follow-up-inventory.json"
        ),
        "retained_baseline_consumer_report": (
            root / AUDIT / "current-consumer-dispositions.md"
        ).read_text(),
        "retained_baseline_source_report": (
            root / AUDIT / "current-source-qualifications.md"
        ).read_text(),
        "runtime_pass_claimed": False,
        "qualification": (
            "All25 categories plus universal00; complete source observations, exact live owners "
            "and assertion bodies. Static presence is not semantic certification. Current complete "
            "gates and two exact-final reviews independently establish delivery; historical "
            "assertions, qualified authority and conditional providers remain distinct."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = (json.dumps(build(), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    path = ROOT / OUTPUT
    if args.check:
        if path.read_bytes() != raw:
            raise CurrentAuditError("Complete current source/owner/assertion inventory drifted.")
    else:
        path.write_bytes(raw)
    print(
        "Complete current inventory: 1078 original obligations, 5 new FAQ bindings, "
        "exact live bodies; no runtime-pass claim."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
