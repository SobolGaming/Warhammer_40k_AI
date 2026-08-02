from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "data" / "source_audits" / "39k_pro" / "aeldari_2026_08_01.audit.json"
EXPECTED_SCHEMA = "core-v2-39k-pro-aeldari-audit-v1"
EXPECTED_OFFICIAL_PDF_SHA256 = "2a1954801042948256c002095937be88c9d334994f0b01d7a63510c94d39fe1d"
EXPECTED_FACTION_REFERENCE_URL = "https://39k.pro/faction/-utUCEwvtbI"
EXPECTED_DETACHMENT_REFERENCE_URLS = {
    "armoured-warhost": "https://39k.pro/detachment/p1wVZLW_vjA",
    "aspect-host": "https://39k.pro/detachment/mE_ck6Yuw4o",
    "corsair-coterie": "https://39k.pro/detachment/-pNM9njdl5I",
    "devoted-of-ynnead": "https://39k.pro/detachment/ORwGrXjanQM",
    "eldritch-raiders": "https://39k.pro/detachment/9WTJbql97EM",
    "fateful-performance": "https://39k.pro/detachment/fPaMgt_y_lE",
    "ghosts-of-the-webway": "https://39k.pro/detachment/kVja2920vrE",
    "guardian-battlehost": "https://39k.pro/detachment/y63o6ssMqQo",
    "path-of-the-outcast": "https://39k.pro/detachment/-DkoEgrDkD0",
    "seer-council": "https://39k.pro/detachment/ecgTNVmjAWo",
    "serpents-brood": "https://39k.pro/detachment/ivZhnRZTWZE",
    "spirit-conclave": "https://39k.pro/detachment/lwUZoioUEUs",
    "twilight-flickers": "https://39k.pro/detachment/x4BFJKs6oiU",
    "warhost": "https://39k.pro/detachment/G2IByiBHSZA",
    "windrider-host": "https://39k.pro/detachment/4FEBuGuye6Q",
}
EXPECTED_RULE_NAMES_BY_DETACHMENT_ID = {
    "armoured-warhost": ("Skilled Crews",),
    "aspect-host": ("Path of the Warrior",),
    "corsair-coterie": ("Relentless Raiders", "Veterans of the Void"),
    "devoted-of-ynnead": ("Strength from Death",),
    "eldritch-raiders": ("Veterans of the Void", "Yriel's Own"),
    "fateful-performance": ("Acrobatic Onslaught",),
    "ghosts-of-the-webway": ("Acrobatic Onslaught",),
    "guardian-battlehost": ("Defend At All Costs",),
    "path-of-the-outcast": ("Far-reaching Doom",),
    "seer-council": ("Strands of Fate",),
    "serpents-brood": ("Boons of the Brood",),
    "spirit-conclave": ("Shepherds of the Dead",),
    "twilight-flickers": ("Dance of Distortion",),
    "warhost": ("Martial Grace",),
    "windrider-host": ("Ride the Wind",),
}


@dataclass(frozen=True, slots=True)
class AeldariDetachmentAuditRow:
    detachment_id: str
    detachment_name: str
    provider_url: str
    rule_names: tuple[str, ...]
    enhancement_count: int
    stratagem_count: int


@dataclass(frozen=True, slots=True)
class AeldariSupplementalStratagemAuditRow:
    detachment_id: str
    detachment_name: str
    stratagem_id: str
    stratagem_name: str
    command_point_cost: int
    timing_descriptor: str
    category: str
    official_pdf_page: int

    @property
    def official_source_id(self) -> str:
        return (
            "gw-11e-aeldari-faction-pack-2026-07:"
            f"p{self.official_pdf_page}:stratagem:{self.detachment_id}:{self.stratagem_id}"
        )


@dataclass(frozen=True, slots=True)
class AeldariThirtyNineKProAudit:
    audit_id: str
    audited_at: str
    official_pdf_path: str
    official_pdf_sha256: str
    faction_reference_url: str
    publication_id: str
    publication_name: str
    errata_date: str
    in_scope_datasheet_count: int
    exact_ability_count: int
    matched_exact_ability_count: int
    excluded_content: tuple[str, ...]
    provider_navigation_name_discrepancy: str
    detachments: tuple[AeldariDetachmentAuditRow, ...]
    supplemental_stratagems: tuple[AeldariSupplementalStratagemAuditRow, ...]

    @property
    def enhancement_count(self) -> int:
        return sum(row.enhancement_count for row in self.detachments)

    @property
    def stratagem_count(self) -> int:
        return sum(row.stratagem_count for row in self.detachments)


def aeldari_thirty_nine_k_pro_audit() -> AeldariThirtyNineKProAudit:
    return load_aeldari_thirty_nine_k_pro_audit(AUDIT_PATH)


def load_aeldari_thirty_nine_k_pro_audit(path: Path) -> AeldariThirtyNineKProAudit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if type(payload) is not dict or payload.get("audit_schema") != EXPECTED_SCHEMA:
        raise ValueError("Aeldari 39k PRO audit schema is unsupported.")
    official = _required_dict(payload, "official_source")
    provider = _required_dict(payload, "provider")
    datasheets = _required_dict(payload, "datasheet_reconciliation")
    detachments = tuple(
        AeldariDetachmentAuditRow(
            detachment_id=_required_text(row, "detachment_id"),
            detachment_name=_required_text(row, "detachment_name"),
            provider_url=_verified_reference_url(
                _required_text(row, "provider_url"), expected_kind="detachment"
            ),
            rule_names=_required_text_tuple(row, "rule_names"),
            enhancement_count=_required_non_negative_int(row, "enhancement_count"),
            stratagem_count=_required_non_negative_int(row, "stratagem_count"),
        )
        for row in _required_dict_rows(payload, "detachments")
    )
    supplemental = tuple(
        AeldariSupplementalStratagemAuditRow(
            detachment_id=_required_text(row, "detachment_id"),
            detachment_name=_required_text(row, "detachment_name"),
            stratagem_id=_required_text(row, "stratagem_id"),
            stratagem_name=_required_text(row, "stratagem_name"),
            command_point_cost=_required_non_negative_int(row, "command_point_cost"),
            timing_descriptor=_required_text(row, "timing_descriptor"),
            category=_required_text(row, "category"),
            official_pdf_page=_required_positive_int(row, "official_pdf_page"),
        )
        for row in _required_dict_rows(payload, "supplemental_stratagems")
    )
    audit = AeldariThirtyNineKProAudit(
        audit_id=_required_text(payload, "audit_id"),
        audited_at=_required_text(payload, "audited_at"),
        official_pdf_path=_required_text(official, "pdf_path"),
        official_pdf_sha256=_required_text(official, "pdf_sha256"),
        faction_reference_url=_verified_reference_url(
            _required_text(provider, "faction_reference_url"), expected_kind="faction"
        ),
        publication_id=_required_text(provider, "publication_id"),
        publication_name=_required_text(provider, "publication_name"),
        errata_date=_required_text(provider, "errata_date"),
        in_scope_datasheet_count=_required_positive_int(datasheets, "in_scope_datasheet_count"),
        exact_ability_count=_required_positive_int(datasheets, "exact_ability_count"),
        matched_exact_ability_count=_required_positive_int(
            datasheets, "matched_exact_ability_count"
        ),
        excluded_content=_required_text_tuple(datasheets, "excluded_content"),
        provider_navigation_name_discrepancy=_required_text(
            datasheets, "provider_navigation_name_discrepancy"
        ),
        detachments=detachments,
        supplemental_stratagems=supplemental,
    )
    _validate_audit(audit)
    return audit


def _validate_audit(audit: AeldariThirtyNineKProAudit) -> None:
    if audit.official_pdf_sha256 != EXPECTED_OFFICIAL_PDF_SHA256:
        raise ValueError("Aeldari audit official PDF hash is stale.")
    official_path = ROOT / audit.official_pdf_path
    if hashlib.sha256(official_path.read_bytes()).hexdigest() != audit.official_pdf_sha256:
        raise ValueError("Aeldari audit official PDF content hash drifted.")
    if len(audit.detachments) != 15:
        raise ValueError("Aeldari audit must contain all 15 current detachments.")
    if len({row.detachment_id for row in audit.detachments}) != len(audit.detachments):
        raise ValueError("Aeldari audit detachment IDs must be unique.")
    if len({row.provider_url for row in audit.detachments}) != len(audit.detachments):
        raise ValueError("Aeldari audit detachment URLs must be unique.")
    if audit.faction_reference_url != EXPECTED_FACTION_REFERENCE_URL:
        raise ValueError("Aeldari audit faction reference URL drifted.")
    if audit.publication_id != audit.faction_reference_url.rsplit("/", 1)[-1]:
        raise ValueError("Aeldari audit publication ID mismatched its faction reference URL.")
    urls_by_detachment_id = {row.detachment_id: row.provider_url for row in audit.detachments}
    if urls_by_detachment_id != EXPECTED_DETACHMENT_REFERENCE_URLS:
        raise ValueError("Aeldari audit verified detachment references drifted.")
    rule_names_by_detachment_id = {row.detachment_id: row.rule_names for row in audit.detachments}
    if rule_names_by_detachment_id != EXPECTED_RULE_NAMES_BY_DETACHMENT_ID:
        raise ValueError("Aeldari audit named detachment rules drifted.")
    if audit.enhancement_count != 52 or audit.stratagem_count != 78:
        raise ValueError("Aeldari audit exact subrule totals drifted.")
    if audit.exact_ability_count != audit.matched_exact_ability_count:
        raise ValueError("Aeldari audit contains unmatched exact abilities.")
    supplemental_ids = {
        (row.detachment_id, row.stratagem_id) for row in audit.supplemental_stratagems
    }
    if len(supplemental_ids) != len(audit.supplemental_stratagems):
        raise ValueError("Aeldari supplemental Stratagem IDs must be unique per detachment.")
    if len(audit.supplemental_stratagems) != 12:
        raise ValueError("Aeldari supplemental Stratagem inventory drifted.")
    if {row.detachment_id for row in audit.supplemental_stratagems} != {
        "armoured-warhost",
        "fateful-performance",
        "path-of-the-outcast",
        "twilight-flickers",
    }:
        raise ValueError("Aeldari supplemental Stratagem detachment scope drifted.")


def _verified_reference_url(value: str, *, expected_kind: str) -> str:
    split = urlsplit(value)
    path_parts = tuple(part for part in split.path.split("/") if part)
    if (
        split.scheme != "https"
        or split.hostname != "39k.pro"
        or split.query
        or split.fragment
        or len(path_parts) != 2
        or path_parts[0] != expected_kind
        or not path_parts[1]
    ):
        raise ValueError("Aeldari audit contains an unverified 39k PRO reference URL.")
    return value


def _required_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if type(value) is not dict:
        raise ValueError(f"Aeldari audit {key} must be an object.")
    return value


def _required_dict_rows(payload: dict[str, object], key: str) -> tuple[dict[str, object], ...]:
    value = payload.get(key)
    if type(value) is not list or not value or any(type(row) is not dict for row in value):
        raise ValueError(f"Aeldari audit {key} must be a non-empty object list.")
    return tuple(value)


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise ValueError(f"Aeldari audit {key} must be non-empty text.")
    return value


def _required_text_tuple(payload: dict[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if (
        type(value) is not list
        or not value
        or any(type(item) is not str or not item.strip() for item in value)
    ):
        raise ValueError(f"Aeldari audit {key} must be a non-empty text list.")
    return tuple(value)


def _required_non_negative_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int or value < 0:
        raise ValueError(f"Aeldari audit {key} must be a non-negative integer.")
    return value


def _required_positive_int(payload: dict[str, object], key: str) -> int:
    value = _required_non_negative_int(payload, key)
    if value == 0:
        raise ValueError(f"Aeldari audit {key} must be positive.")
    return value
