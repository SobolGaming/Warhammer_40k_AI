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
    owned_packages = tuple(
        registered
        for registered in scope.source_packages
        if registered.package_name == package.source_catalog.package_id.package_name
        and registered.namespace == package.source_catalog.package_id.namespace
    )
    assert len(owned_packages) == 1
    assert owned_packages[0].catalog_sha256 == package.source_catalog.catalog_sha256()
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


def test_aeldari_current_source_evidence_overlay_and_index_dependencies_agree() -> None:
    import hashlib
    import json

    from tools.ability_support_sources import ability_support_index_inputs
    from tools.aeldari_datasheet_semantic_coverage import SOURCE_JSON_DIR
    from tools.generate_aeldari_current_source import generated_overlay_pack

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        aeldari_current_2026_11 as current,
    )

    root = Path(__file__).resolve().parents[2]
    source_dir = SOURCE_JSON_DIR
    data = root / "data/source_audits/aeldari_current_2026_11"
    audit = current.source_audit()
    assert (data / "source.audit.json").read_bytes() == Path(current.__file__).with_name(
        current.AUDIT_ARTIFACT_NAME
    ).read_bytes()
    validate_official_artifacts(audit)
    package = current.source_package()
    scope = source_authority_registry().scope("warhammer_40000_11th_factions")
    registered = next(
        row for row in scope.source_packages if row.package_name == current.SOURCE_PACKAGE_NAME
    )
    assert registered.catalog_sha256 == package.source_catalog.catalog_sha256()
    assert generated_overlay_pack().to_payload() == current.overlay_pack().to_payload()
    inputs = set(ability_support_index_inputs(source_dir))
    assert Path(current.__file__).with_name(current.ARTIFACT_NAME) in inputs
    assert Path(current.__file__).with_name(current.AUDIT_ARTIFACT_NAME) in inputs
    assert root / "src/warhammer40k_core/rules/source_authority_registry.json" in inputs
    captures = json.loads((data / "browser-captures.json").read_bytes())
    assert hashlib.sha256(captures["version_feed"]["text"].encode()).hexdigest() == (
        "cd829c4c4b04d96ce0afe32582c6a80917bfea368c8b271e24eff0fc8b03e205"
    )
    for label, row in zip(("army_rules", "voidscarred"), audit.observations, strict=True):
        assert captures[label]["captured_text"] == row.captured_text
    assert all(
        record.semantic_execution_status == "not_certified"
        for record in package.source_evidence_catalog.records
    )
