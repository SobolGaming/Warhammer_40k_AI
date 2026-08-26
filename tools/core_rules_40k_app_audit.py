from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "data" / "source_audits" / "40k_app" / "core_rules_2026_08_25.audit.json"
REPORT_PATH = ROOT / "docs" / "CORE_RULES_40K_APP_COMPARISON.md"
EXPECTED_SCHEMA = "core-v2-40k-app-core-rules-audit-v1"
EXPECTED_AUDIT_ID = "40k-app-core-rules-2026-08-25"
EXPECTED_OBSERVED_AT = "2026-08-25T00:00:00-04:00"
EXPECTED_OFFICIAL_PDF_PATH = (
    "docs/source_rules/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf"
)
EXPECTED_OFFICIAL_PDF_SHA256 = "f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833"
EXPECTED_CATEGORIES = (
    ("01", "Core Concepts", "01-core-concepts"),
    ("02", "Datasheets", "02-datasheets"),
    ("03", "Moving", "03-moving"),
    ("04", "Making Attacks", "04-making-attacks"),
    ("05", "Attack Sequence", "05-attack-sequence"),
    ("06", "Other Concepts", "06-other-concepts"),
    ("07", "The Battle Round", "07-the-battle-round"),
    ("08", "Command Phase", "08-command-phase"),
    ("09", "Movement Phase", "09-movement-phase"),
    ("10", "Shooting Phase", "10-shooting-phase"),
    ("11", "Charge Phase", "11-charge-phase"),
    ("12", "Fight Phase", "12-fight-phase"),
    ("13", "Terrain", "13-terrain"),
    ("14", "Objectives", "14-objectives"),
    ("15", "Stratagems", "15-stratagems"),
    ("16", "Actions", "16-actions"),
    ("17", "Monsters And Vehicles", "17-monsters-and-vehicles"),
    ("18", "Transports", "18-transports"),
    ("19", "Attached Units", "19-attached-units"),
    ("20", "Strategic Reserves", "20-strategic-reserves"),
    ("21", "Flying and Surging", "21-flying-and-surging"),
    ("22", "Other Rules And Abilities", "22-other-rules-and-abilities"),
    ("23", "Aircraft", "23-aircraft"),
    ("24", "Core Abilities", "24-core-abilities"),
    ("25", "Muster Armies", "25-muster-armies"),
)
EXPECTED_FINDING_IDS_BY_CATEGORY = {
    "05": ("40k-app-numbering-05-03-02",),
    "09": ("40k-app-duplicate-09-07-01",),
    "12": ("july-transcription-conflict-12-08",),
    "15": ("official-pdf-mirror-order-15-05-15-06",),
    "21": ("july-transcription-not-observed-fly-heavy",),
    "24": ("july-transcription-not-observed-mixed-hazard",),
}


@dataclass(frozen=True, slots=True)
class CoreRulesCategoryAuditRow:
    category_id: str
    category_title: str
    display_order: int
    provider_url: str
    section_id: str
    official_source_status: str
    provider_comparison_status: str
    implementation_status: str
    finding_ids: tuple[str, ...]
    evidence_sha256: str


@dataclass(frozen=True, slots=True)
class CoreRulesFindingAuditRow:
    finding_id: str
    category_id: str
    finding_kind: str
    how_currently_recorded: str
    how_it_should_be_treated: str
    specific_source_basis: str
    verification_status: str
    evidence_sha256: str


@dataclass(frozen=True, slots=True)
class CoreRulesFortyKAppAudit:
    audit_id: str
    observed_at: str
    scope: str
    edition: str
    expected_category_count: int
    excluded_scopes: tuple[str, ...]
    provider_id: str
    provider_root_url: str
    provider_authority: str
    provider_affiliation: str
    runtime_input: bool
    network_capture_retained: bool
    official_package_id: str
    official_pdf_path: str
    official_pdf_sha256: str
    official_catalog_source_id: str
    authority_statement: str
    categories: tuple[CoreRulesCategoryAuditRow, ...]
    findings: tuple[CoreRulesFindingAuditRow, ...]


def core_rules_forty_k_app_audit() -> CoreRulesFortyKAppAudit:
    return load_core_rules_forty_k_app_audit(AUDIT_PATH)


def load_core_rules_forty_k_app_audit(path: Path) -> CoreRulesFortyKAppAudit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    root = _exact_dict(
        payload,
        {
            "audit_schema",
            "audit_id",
            "observed_at",
            "scope",
            "provider",
            "official_source",
            "categories",
            "findings",
        },
        context="root",
    )
    if _text(root, "audit_schema") != EXPECTED_SCHEMA:
        raise ValueError("40k.app core-rules audit schema is unsupported.")
    scope = _exact_dict(
        root.get("scope"),
        {"edition", "review_scope", "expected_category_count", "excluded_scopes"},
        context="scope",
    )
    provider = _exact_dict(
        root.get("provider"),
        {
            "provider_id",
            "root_url",
            "authority_status",
            "affiliation",
            "runtime_input",
            "network_capture_retained",
        },
        context="provider",
    )
    official = _exact_dict(
        root.get("official_source"),
        {
            "package_id",
            "pdf_path",
            "pdf_sha256",
            "catalog_source_id",
            "authority_statement",
        },
        context="official source",
    )
    categories = tuple(
        _category_row(row) for row in _object_rows(root, "categories", context="categories")
    )
    findings = tuple(
        _finding_row(row) for row in _object_rows(root, "findings", context="findings")
    )
    audit = CoreRulesFortyKAppAudit(
        audit_id=_text(root, "audit_id"),
        observed_at=_text(root, "observed_at"),
        scope=_text(scope, "review_scope"),
        edition=_text(scope, "edition"),
        expected_category_count=_positive_int(scope, "expected_category_count"),
        excluded_scopes=_text_tuple(scope, "excluded_scopes"),
        provider_id=_text(provider, "provider_id"),
        provider_root_url=_text(provider, "root_url"),
        provider_authority=_text(provider, "authority_status"),
        provider_affiliation=_text(provider, "affiliation"),
        runtime_input=_boolean(provider, "runtime_input"),
        network_capture_retained=_boolean(provider, "network_capture_retained"),
        official_package_id=_text(official, "package_id"),
        official_pdf_path=_text(official, "pdf_path"),
        official_pdf_sha256=_sha256(official, "pdf_sha256"),
        official_catalog_source_id=_text(official, "catalog_source_id"),
        authority_statement=_text(official, "authority_statement"),
        categories=categories,
        findings=findings,
    )
    _validate_audit(audit)
    return audit


def core_rules_forty_k_app_audit_markdown(
    audit: CoreRulesFortyKAppAudit | None = None,
) -> str:
    reviewed = core_rules_forty_k_app_audit() if audit is None else audit
    lines = [
        "# Core Rules 40k.app Comparison Evidence",
        "",
        "This report is generated from the checked-in offline audit artifact. 40k.app is a "
        "secondary, unofficial comparison source; it is not an official Games Workshop source "
        "and is never runtime catalog input.",
        "",
        "Faction review is explicitly excluded, including faction detachments and faction "
        "datasheet content.",
        "",
        "## Authority boundary",
        "",
        f"- Official anchor: `{reviewed.official_pdf_path}` (`{reviewed.official_pdf_sha256}`).",
        "- Official GW artifacts and captured official-App evidence outrank mirror observations.",
        "- A mirror conflict remains blocked until a pinned primary source resolves it.",
        "- Observation hashes protect the committed review rows; they do not authenticate the "
        "external website.",
        "",
        "## Category inventory",
        "",
        "| Category | Provider locator | Provider comparison | Implementation evaluation |",
        "|---|---|---|---|",
    ]
    lines.extend(
        f"| {row.category_id} {row.category_title} | [{row.section_id}]({row.provider_url}) | "
        f"{row.provider_comparison_status} | {row.implementation_status} |"
        for row in reviewed.categories
    )
    lines.extend(("", "## Source and provider findings", ""))
    for finding in reviewed.findings:
        lines.extend(
            (
                f"### {finding.finding_id} - Category {finding.category_id}",
                "",
                f"- How it is currently recorded: {finding.how_currently_recorded}",
                f"- How it should be treated: {finding.how_it_should_be_treated}",
                f"- Specific rule/source basis: {finding.specific_source_basis}",
                f"- Verification status: `{finding.verification_status}`",
                "",
            )
        )
    lines.extend(
        (
            "## P00 implementation boundary",
            "",
            "The July App-core rows retain their stable package, document, rule, and source IDs. "
            "Their separate evidence records now state that no official App version, build, URL, "
            "screenshot, or binary is retained. Fight On Death is recorded as partial runtime "
            "execution, and Objective Consolidation is blocked by a source conflict. No gameplay "
            "semantics are changed by P00.",
            "",
        )
    )
    return "\n".join(lines)


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and render the offline 40k.app core-rules comparison audit."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--update-evidence-hashes", action="store_true")
    args = parser.parse_args(argv)
    if args.update_evidence_hashes:
        _write_refreshed_audit_hashes()
    rendered = core_rules_forty_k_app_audit_markdown()
    if args.check:
        if not REPORT_PATH.is_file() or REPORT_PATH.read_text(encoding="utf-8") != rendered:
            raise SystemExit("40k.app core-rules comparison report is stale.")
        return 0
    REPORT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


def _write_refreshed_audit_hashes() -> None:
    payload = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    root = _exact_dict(
        payload,
        {
            "audit_schema",
            "audit_id",
            "observed_at",
            "scope",
            "provider",
            "official_source",
            "categories",
            "findings",
        },
        context="root",
    )
    for key in ("categories", "findings"):
        for row in _object_rows(root, key, context=key):
            if "evidence_sha256" not in row:
                raise ValueError(f"40k.app audit {key} row is missing evidence_sha256.")
            row["evidence_sha256"] = _evidence_hash(row)
    AUDIT_PATH.write_text(
        json.dumps(root, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _category_row(payload: dict[str, object]) -> CoreRulesCategoryAuditRow:
    row = _exact_dict(
        payload,
        {
            "category_id",
            "category_title",
            "display_order",
            "provider_url",
            "section_id",
            "official_source_status",
            "provider_comparison_status",
            "implementation_status",
            "finding_ids",
            "evidence_sha256",
        },
        context="category",
    )
    category = CoreRulesCategoryAuditRow(
        category_id=_text(row, "category_id"),
        category_title=_text(row, "category_title"),
        display_order=_positive_int(row, "display_order"),
        provider_url=_text(row, "provider_url"),
        section_id=_text(row, "section_id"),
        official_source_status=_text(row, "official_source_status"),
        provider_comparison_status=_text(row, "provider_comparison_status"),
        implementation_status=_text(row, "implementation_status"),
        finding_ids=_text_tuple(row, "finding_ids", allow_empty=True),
        evidence_sha256=_sha256(row, "evidence_sha256"),
    )
    _validate_rules_url(category.provider_url)
    if category.evidence_sha256 != _evidence_hash(row):
        raise ValueError("40k.app category evidence hash drifted.")
    return category


def _finding_row(payload: dict[str, object]) -> CoreRulesFindingAuditRow:
    row = _exact_dict(
        payload,
        {
            "finding_id",
            "category_id",
            "finding_kind",
            "how_currently_recorded",
            "how_it_should_be_treated",
            "specific_source_basis",
            "verification_status",
            "evidence_sha256",
        },
        context="finding",
    )
    finding = CoreRulesFindingAuditRow(
        finding_id=_text(row, "finding_id"),
        category_id=_text(row, "category_id"),
        finding_kind=_text(row, "finding_kind"),
        how_currently_recorded=_text(row, "how_currently_recorded"),
        how_it_should_be_treated=_text(row, "how_it_should_be_treated"),
        specific_source_basis=_text(row, "specific_source_basis"),
        verification_status=_text(row, "verification_status"),
        evidence_sha256=_sha256(row, "evidence_sha256"),
    )
    if finding.evidence_sha256 != _evidence_hash(row):
        raise ValueError("40k.app finding evidence hash drifted.")
    return finding


def _validate_audit(audit: CoreRulesFortyKAppAudit) -> None:
    if audit.audit_id != EXPECTED_AUDIT_ID or audit.observed_at != EXPECTED_OBSERVED_AT:
        raise ValueError("40k.app core-rules audit identity drifted.")
    _validate_timestamp(audit.observed_at)
    if (
        audit.scope != "core_rules_only"
        or audit.edition != "warhammer_40000_11th"
        or audit.expected_category_count != 25
        or audit.excluded_scopes != ("factions", "faction_detachments", "faction_datasheets")
    ):
        raise ValueError("40k.app audit must retain its core-rules-only scope.")
    if (
        audit.provider_id != "40k-app"
        or audit.provider_root_url != "https://www.40k.app/rules"
        or audit.provider_authority != "secondary_unofficial"
        or audit.provider_affiliation != "not_affiliated_with_or_endorsed_by_games_workshop"
        or audit.runtime_input
        or audit.network_capture_retained
    ):
        raise ValueError("40k.app provider authority boundary drifted.")
    if (
        audit.official_package_id != "gw-11e-core-rules"
        or audit.official_pdf_path != EXPECTED_OFFICIAL_PDF_PATH
        or audit.official_pdf_sha256 != EXPECTED_OFFICIAL_PDF_SHA256
        or audit.official_catalog_source_id != "gw-11e-core-rules:manifest:local-core-rules-pdf"
        or audit.authority_statement
        != "official_gw_artifacts_and_captured_official_app_evidence_are_authoritative"
    ):
        raise ValueError("40k.app audit official-source anchor drifted.")
    official_path = ROOT / audit.official_pdf_path
    if hashlib.sha256(official_path.read_bytes()).hexdigest() != audit.official_pdf_sha256:
        raise ValueError("40k.app audit official PDF content hash drifted.")
    if len(audit.categories) != audit.expected_category_count:
        raise ValueError("40k.app audit must retain exactly 25 core-rules categories.")
    expected_category_rows = tuple(
        (
            category_id,
            title,
            display_order,
            f"https://www.40k.app/rules/{slug}",
            f"{category_id}.00",
        )
        for display_order, (category_id, title, slug) in enumerate(EXPECTED_CATEGORIES, start=1)
    )
    observed_category_rows = tuple(
        (
            row.category_id,
            row.category_title,
            row.display_order,
            row.provider_url,
            row.section_id,
        )
        for row in audit.categories
    )
    if observed_category_rows != expected_category_rows:
        raise ValueError("40k.app category inventory or ordering drifted.")
    if len({row.provider_url for row in audit.categories}) != len(audit.categories):
        raise ValueError("40k.app category URLs must be unique.")
    for row in audit.categories:
        _validate_rules_url(row.provider_url)
        expected_finding_ids = EXPECTED_FINDING_IDS_BY_CATEGORY.get(row.category_id, ())
        if row.category_id in {"12", "15"}:
            expected_comparison = "conflict"
        elif row.category_id in {"21", "24"}:
            expected_comparison = "transcription_not_observed"
        else:
            expected_comparison = "mirror_only"
        if (
            row.official_source_status != "retained_official_pdf_anchor"
            or row.provider_comparison_status != expected_comparison
            or row.implementation_status != "not_assessed_in_p00"
            or row.finding_ids != expected_finding_ids
        ):
            raise ValueError("40k.app category conclusion drifted from retained findings.")
    finding_by_id = {row.finding_id: row for row in audit.findings}
    all_expected_finding_ids = {
        finding_id
        for finding_ids in EXPECTED_FINDING_IDS_BY_CATEGORY.values()
        for finding_id in finding_ids
    }
    if len(finding_by_id) != len(audit.findings) or set(finding_by_id) != all_expected_finding_ids:
        raise ValueError("40k.app finding inventory drifted.")
    for category_id, finding_ids in EXPECTED_FINDING_IDS_BY_CATEGORY.items():
        if any(finding_by_id[finding_id].category_id != category_id for finding_id in finding_ids):
            raise ValueError("40k.app finding parent category drifted.")
    if {row.verification_status for row in audit.findings} - {
        "provider_local_only",
        "needs_official_app_capture",
        "official_pdf_controls",
    }:
        raise ValueError("40k.app finding verification status is unsupported.")


def _validate_rules_url(value: str) -> str:
    split = urlsplit(value)
    if (
        split.scheme != "https"
        or split.hostname != "www.40k.app"
        or split.username is not None
        or split.password is not None
        or split.port is not None
        or split.query
        or split.fragment
        or not split.path.startswith("/rules/")
    ):
        raise ValueError("40k.app audit contains an invalid 40k.app rules URL.")
    return value


def _evidence_hash(payload: dict[str, object]) -> str:
    hashed_payload = dict(payload)
    hashed_payload["evidence_sha256"] = ""
    encoded = json.dumps(hashed_payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _exact_dict(value: object, fields: set[str], *, context: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError(f"40k.app audit {context} must be an object.")
    row = cast(dict[str, object], value)
    if set(row) != fields:
        raise ValueError(f"40k.app audit {context} fields drifted.")
    return row


def _object_rows(
    payload: dict[str, object], key: str, *, context: str
) -> tuple[dict[str, object], ...]:
    value = payload.get(key)
    if type(value) is not list:
        raise ValueError(f"40k.app audit {context} must be a non-empty object list.")
    rows = cast(list[object], value)
    if not rows or any(type(row) is not dict for row in rows):
        raise ValueError(f"40k.app audit {context} must be a non-empty object list.")
    return tuple(cast(dict[str, object], row) for row in rows)


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"40k.app audit {key} must be non-empty stripped text.")
    return value


def _text_tuple(
    payload: dict[str, object], key: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    value = payload.get(key)
    if type(value) is not list:
        raise ValueError(f"40k.app audit {key} must be a text list.")
    items = cast(list[object], value)
    if not allow_empty and not items:
        raise ValueError(f"40k.app audit {key} must be a text list.")
    result = tuple(_text({key: item}, key) for item in items)
    if len(result) != len(set(result)):
        raise ValueError(f"40k.app audit {key} must be unique.")
    return result


def _positive_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 1:
        raise ValueError(f"40k.app audit {key} must be a positive integer.")
    return value


def _boolean(payload: dict[str, object], key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise ValueError(f"40k.app audit {key} must be a boolean.")
    return value


def _sha256(payload: dict[str, object], key: str) -> str:
    value = _text(payload, key)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"40k.app audit {key} must be lowercase SHA-256.")
    return value


def _validate_timestamp(value: str) -> None:
    try:
        observed_at = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("40k.app audit observed_at must be ISO-8601.") from exc
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("40k.app audit observed_at must include a UTC offset.")


if __name__ == "__main__":
    raise SystemExit(main())
