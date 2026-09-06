from __future__ import annotations

import ast
from pathlib import Path

from tools.build_faction_source_governance import (
    AUDIT_PATH,
    REPORT_PATH,
    review_markdown,
    validate_official_artifacts,
    validate_registry,
)

from warhammer40k_core.rules.faction_source_governance import (
    FACTION_AUDIT_PATH,
    faction_source_audit,
)
from warhammer40k_core.rules.faction_source_package import faction_source_package
from warhammer40k_core.rules.source_authority_registry import source_authority_registry


def test_f00_retained_generated_and_registered_evidence_agrees() -> None:
    audit = faction_source_audit()
    assert FACTION_AUDIT_PATH.read_bytes() == AUDIT_PATH.read_bytes()
    assert REPORT_PATH.read_text() == review_markdown(audit)
    validate_registry(audit)
    validate_official_artifacts(audit)
    package = faction_source_package()
    assert len(package.evidence_required_source_ids) == 3
    scope = source_authority_registry().scope("warhammer_40000_11th_factions")
    assert len(scope.source_packages) == 1
    assert scope.source_packages[0].catalog_sha256 == package.source_catalog.catalog_sha256()
    assert package.source_catalog.package_id.version == audit.package_version()


def test_f00_source_governance_has_no_live_fetch_or_engine_dependency() -> None:
    paths = (
        Path("src/warhammer40k_core/rules/faction_source_governance.py"),
        Path("src/warhammer40k_core/rules/faction_source_package.py"),
        Path("tools/build_faction_source_governance.py"),
    )
    forbidden = (
        "requests",
        "httpx",
        "http.client",
        "urllib.request",
        "socket",
        "subprocess",
        "warhammer40k_core.engine",
        "warhammer40k_core.adapters",
    )
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                imports = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports = (node.module,)
            else:
                continue
            assert not any(
                name == prefix or name.startswith(prefix + ".")
                for name in imports
                for prefix in forbidden
            ), path


def test_f00_policy_preserves_holds_and_distinguishes_source_from_execution() -> None:
    policy = Path("docs/FACTION_RULES_SOURCE_POLICY.md").read_text()
    for required in (
        "Forge World",
        "Crusade",
        "Boarding Action",
        "Kill Team",
        "Legends",
        "Warbuggies",
        "ModelGeometryCatalogRecord",
        "946",
        "39k PRO",
        "F01",
        "official_primary",
        "non-affiliated",
        "structural completeness",
        "Human review",
        "provider-page completeness",
        "globally unique source IDs",
    ):
        assert required in policy
    for record in faction_source_package().source_evidence_catalog.records:
        assert record.semantic_execution_status == "not_certified"
        assert not record.runtime_consumer_ids
