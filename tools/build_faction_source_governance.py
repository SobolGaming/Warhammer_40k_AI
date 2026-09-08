"""Validate and package retained F00 observations offline."""

from __future__ import annotations

import argparse
from pathlib import Path

from warhammer40k_core.rules.faction_source_governance import (
    EXPECTED_FACTION_AUDIT_SHA256,
    FACTION_AUDIT_PATH,
    FactionSourceAudit,
    FactionSourceError,
    load_faction_source_audit_bytes,
)
from warhammer40k_core.rules.faction_source_package import (
    faction_source_catalog,
    faction_source_package,
)
from warhammer40k_core.rules.source_authority_registry import (
    SourceAuthorityRegistry,
    SourcePackageAuthorization,
    source_authority_registry,
)
from warhammer40k_core.rules.source_catalog import SourceCatalogError, SourceFileChecksum

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "data/source_audits/maintained_app_mirrors/factions_2026_09_05.audit.json"
REPORT_PATH = ROOT / "docs/FACTION_SOURCE_GOVERNANCE_REVIEW.md"


def review_markdown(audit: FactionSourceAudit) -> str:
    lines = [
        "# F00 faction source governance review",
        "",
        "Generated offline by `uv run python tools/build_faction_source_governance.py`.",
        "",
        f"Policy: `{audit.policy_id}`. Selected App-data: **{audit.app_version}**, "
        f"locale `{audit.locale}`.",
        f"Retained artifact SHA-256: `{EXPECTED_FACTION_AUDIT_SHA256}`.",
        f"Canonical source-catalog SHA-256: `{faction_source_catalog(audit).catalog_sha256()}`.",
        "",
        "These three complete observations exercise faction, detachment and datasheet package "
        "governance. They are a bounded source selection, not the F01 corpus reconciliation. "
        "Page source IDs are stable provenance identities, not runtime rule or catalog IDs. "
        "Each page still needs clause-level identity and consumer review before execution.",
        "",
        "| Source page | Kind | Observation fingerprint | Load | Execution |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in audit.observations:
        lines.append(
            f"| [{row.source_title}]({row.source_url}) | {row.content_kind} | "
            f"`{row.source_observation_sha256}` | loaded | not certified |"
        )
    lines.extend(
        [
            "",
            "## Source and geometry limits",
            "",
            "40k.app is a non-affiliated maintained mirror. The current observation is project "
            "authority, never official-primary evidence. The retained July Games Workshop PDF "
            "keeps its independent URL and hash as historical primary evidence; no current "
            "corroboration or unchanged-clause claim is inferred from that relationship.",
            "",
            "The Exorcist page supplies Hull, but no dimensions or height. Its geometry obligation "
            "blocks fieldability pending accepted, variant-specific ModelGeometryCatalogRecord "
            "evidence. Source loading cannot accept a default base, zero height, or an invented "
            "measurement. F06 owns those measurements.",
            "",
            "The captured text preserves each complete main element. Operative text begins at the "
            "reviewed heading and includes the remainder, including points, choices, restrictions, "
            "profiles, subrules, examples and damaged sections where present. Page navigation may "
            "remain in that retained document; it is not gameplay semantics. Normalization reuses "
            "the shared non-Core objective terminology boundary.",
            "",
            "The source invariant is enforced at observation parsing, the reviewed byte pin, the "
            "authority registry, RuleEvidenceRecord, and RuleSourcePackage. Source IDs are "
            "globally unique across documents. Package version/date derive from the audit; "
            "the registry authenticates the full canonical catalog hash. Recomputed hashes "
            "alone cannot authorize new text, owners, URLs, source identities or catalog metadata. "
            "Conflicts, ambiguous identity, mixed versions/locales and excluded classifications "
            "fail closed. No site is fetched by the loader.",
            "",
            "Candidate validation checks structural completeness: schema, declared review "
            "status, capture/suffix relationship and hashes. Human review establishes actual "
            "provider-page completeness, authenticated by the immutable byte pin. A mutually "
            "truncated capture and suffix can pass structural validation after rehashing, but "
            "cannot pass the reviewed pin. Official artifact paths must be normalized relative "
            "POSIX paths, and the shared checksum reader requires resolved containment beneath "
            "the artifact root, including symlink targets.",
            "",
            "## Remaining work",
            "",
            "F01 owns all remaining admitted URLs, provider/catalog crosswalks, historical deltas "
            "and the Warbuggies identity hold. F02-F09 own gameplay and roster certification. "
            "Acts of Faith's turn-start change is retained here; its consumer is unchanged.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_official_artifacts(audit: FactionSourceAudit) -> None:
    for source in audit.official_sources:
        try:
            checksum = SourceFileChecksum.from_path(
                root=ROOT / "data/raw/faction_packs", path=ROOT / source.artifact_path
            )
        except (SourceCatalogError, OSError) as exc:
            raise FactionSourceError(f"Faction historical primary artifact: {exc}") from exc
        if checksum.checksum_sha256 != source.sha256:
            raise FactionSourceError("Faction historical primary artifact hash drifted.")


def validate_registry(
    audit: FactionSourceAudit, *, registry: SourceAuthorityRegistry | None = None
) -> None:
    authority = source_authority_registry() if registry is None else registry
    scope = authority.scope("warhammer_40000_11th_factions")
    retained = {
        (
            audit.audit_id,
            row.observation_id,
            row.source_observation_sha256,
            row.provider_name,
            row.source_url,
            audit.policy_id,
            "versioned_observation",
            f"{row.app_version}@{row.observed_at}",
        )
        for row in audit.observations
    }
    registered = {
        (
            row.audit_id,
            row.row_id,
            row.source_observation_sha256,
            row.provider_name,
            row.source_url,
            row.policy_id,
            row.identity_kind,
            row.identity_value,
        )
        for row in scope.audit_rows
        if row.audit_id == audit.audit_id
    }
    if retained != registered:
        raise FactionSourceError("Faction authority registry does not match retained observations.")
    catalog = faction_source_catalog(audit)
    expected_package = SourcePackageAuthorization(
        namespace=catalog.package_id.namespace,
        package_name=catalog.package_id.package_name,
        version=catalog.package_id.version,
        allowed_rule_source_ids=tuple(sorted(audit.selected_source_ids)),
        catalog_sha256=catalog.catalog_sha256(),
    )
    registered_packages = tuple(
        package
        for package in scope.source_packages
        if (package.namespace, package.package_name)
        == (expected_package.namespace, expected_package.package_name)
    )
    if registered_packages != (expected_package,):
        raise FactionSourceError(
            "Faction source-package authorization does not match its audit catalog."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    raw = AUDIT_PATH.read_bytes()
    audit = load_faction_source_audit_bytes(raw)
    validate_official_artifacts(audit)
    validate_registry(audit)
    report = review_markdown(audit)
    if args.check:
        if FACTION_AUDIT_PATH.read_bytes() != raw or REPORT_PATH.read_text() != report:
            raise FactionSourceError("Generated faction source artifacts are stale.")
    else:
        FACTION_AUDIT_PATH.write_bytes(raw)
        REPORT_PATH.write_text(report, encoding="utf-8", newline="\n")
    faction_source_package()


if __name__ == "__main__":
    main()
