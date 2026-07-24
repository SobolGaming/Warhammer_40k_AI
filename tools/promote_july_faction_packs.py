from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import cast

from tools.fetch_official_sources import (
    OfficialSourceManifestEntry,
    load_official_source_manifest,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_source_promotion_2026_07 as promotion,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "data" / "source_manifests"
CURRENT_MANIFEST = MANIFEST_DIR / "gw_11e_faction_packs.yaml"
PENDING_MANIFEST = MANIFEST_DIR / "gw_11e_pending_faction_packs_2026_07.yaml"
PREDECESSOR_MANIFEST = MANIFEST_DIR / "gw_11e_faction_pack_predecessors_2026_06.yaml"
DATASHEET_REVIEW_MANIFEST = MANIFEST_DIR / "faction_pack_datasheet_review_v1.json"
PACKAGE_DIR = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "july_faction_packs_2026_07"
)
ARTIFACT_DIR = PACKAGE_DIR / "artifacts"
CURRENT_SOURCES_ARTIFACT = ARTIFACT_DIR / "current-sources.json"
PACKAGE_ARTIFACT = ARTIFACT_DIR / "package.json"
OLD_SOURCE_PACKAGE_ID = "gw-11e-staged-faction-packs-2026-07"
CURRENT_LICENSE_NOTE = (
    "Official GW downloadable PDF; tracked as current source evidence when present "
    "in data/raw/faction_packs."
)
PREDECESSOR_LICENSE_NOTE = (
    "Official GW downloadable PDF; retained as versioned predecessor source evidence "
    "when present in data/raw/faction_packs."
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Promote the reviewed July faction-pack successor atomically."
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.write:
        _write_promotion()
    _check_promotion()


def _write_promotion() -> None:
    if PENDING_MANIFEST.exists():
        june_entries = load_official_source_manifest(CURRENT_MANIFEST)
        july_entries = load_official_source_manifest(PENDING_MANIFEST)
    else:
        june_entries = load_official_source_manifest(PREDECESSOR_MANIFEST)
        current_entries = load_official_source_manifest(CURRENT_MANIFEST)
        july_entries = tuple(
            entry
            for entry in current_entries
            if entry.package_id != promotion.DEATHWATCH_PACKAGE_ID
        )
        deathwatch = _entry_by_package_id(current_entries, promotion.DEATHWATCH_PACKAGE_ID)
        june_entries = (*june_entries, deathwatch)
    ledger = cast(
        dict[str, object],
        json.loads((ARTIFACT_DIR / "delta-ledger.json").read_text(encoding="utf-8")),
    )
    reviews = cast(list[dict[str, object]], ledger["pack_reviews"])
    _validate_input_sets(
        june_entries=june_entries,
        july_entries=july_entries,
    )
    june_by_faction = {_faction_id(entry): entry for entry in june_entries}
    july_by_faction = {_faction_id(entry): entry for entry in july_entries}
    ledger_by_faction = {cast(str, review["faction_id"]): review for review in reviews}
    no_action = {
        cast(str, review["faction_id"])
        for review in reviews
        if not any(
            cast(str, item["disposition"]).startswith("in_scope")
            for item in cast(list[dict[str, object]], review["review_items"])
        )
    }
    if no_action != promotion.NO_ACTION_FACTION_IDS:
        raise ValueError("July no-action faction set drifted from the reviewed ledger.")

    records: list[dict[str, object]] = []
    current_entries: list[OfficialSourceManifestEntry] = []
    for faction_id in sorted(promotion.PROMOTED_FACTION_IDS):
        current = july_by_faction[faction_id]
        predecessor = june_by_faction[faction_id]
        review = ledger_by_faction[faction_id]
        _require_complete_entry(current)
        _require_complete_entry(predecessor)
        if (
            current.package_id != review["successor_package_id"]
            or current.sha256 != review["successor_pdf_sha256"]
            or current.local_cache_path != review["successor_pdf_path"]
            or predecessor.package_id != review["predecessor_package_id"]
            or predecessor.sha256 != review["predecessor_pdf_sha256"]
        ):
            raise ValueError("July promotion input drifted from the reviewed ledger.")
        records.append(
            _record_payload(
                faction_id=faction_id,
                faction_name=cast(str, review["faction_name"]),
                current=current,
                predecessor=predecessor,
                semantic_change_status=(
                    "provenance_only" if faction_id in no_action else "reviewed_delta"
                ),
            )
        )
        current_entries.append(replace(current, license_note=CURRENT_LICENSE_NOTE))

    deathwatch = june_by_faction[promotion.DEATHWATCH_FACTION_ID]
    _require_complete_entry(deathwatch)
    records.append(
        _record_payload(
            faction_id=promotion.DEATHWATCH_FACTION_ID,
            faction_name="Deathwatch",
            current=deathwatch,
            predecessor=None,
            semantic_change_status="current_no_successor",
        )
    )
    current_entries.append(replace(deathwatch, license_note=CURRENT_LICENSE_NOTE))
    payload: dict[str, object] = {
        "activation_status": promotion.ACTIVATION_STATUS,
        "artifact_schema": promotion.ARTIFACT_SCHEMA,
        "excluded_content_categories": ["imperial-armour", "legends"],
        "records": sorted(records, key=lambda record: cast(str, record["faction_id"])),
        "source_date": promotion.SOURCE_DATE,
        "source_package_id": promotion.SOURCE_PACKAGE_ID,
        "source_title": promotion.SOURCE_TITLE,
        "source_version": promotion.SOURCE_VERSION,
    }

    artifact_payloads = _promoted_artifact_payloads(payload)
    for path, artifact_payload in artifact_payloads.items():
        _write_json(path, artifact_payload)
    CURRENT_MANIFEST.write_text(
        _manifest_text(tuple(sorted(current_entries, key=lambda entry: _faction_id(entry)))),
        encoding="utf-8",
    )
    predecessor_entries = tuple(
        replace(entry, license_note=PREDECESSOR_LICENSE_NOTE)
        for entry in sorted(june_entries, key=lambda entry: _faction_id(entry))
        if entry.package_id != promotion.DEATHWATCH_PACKAGE_ID
    )
    PREDECESSOR_MANIFEST.write_text(
        _manifest_text(predecessor_entries),
        encoding="utf-8",
    )
    if PENDING_MANIFEST.exists():
        PENDING_MANIFEST.unlink()
    _rewrite_datasheet_review_pdf_evidence()
    _rewrite_phase17e_pdf_records()


def _promoted_artifact_payloads(
    current_sources_payload: dict[str, object],
) -> dict[Path, object]:
    payloads: dict[Path, object] = {}
    for path in sorted(ARTIFACT_DIR.glob("*.json")):
        if path in {PACKAGE_ARTIFACT, CURRENT_SOURCES_ARTIFACT}:
            continue
        payloads[path] = _promote_value(json.loads(path.read_text(encoding="utf-8")))
    payloads[CURRENT_SOURCES_ARTIFACT] = current_sources_payload
    exalted_patron = cast(
        dict[str, object],
        payloads[ARTIFACT_DIR / "emperors-children-exalted-patron.json"],
    )
    rule_ir_payload = cast(dict[str, object], exalted_patron["rule_ir_payload"])
    rule_ir_payload["ir_hash"] = ""
    promoted_rule_ir_hash = _canonical_sha256(rule_ir_payload)
    rule_ir_payload["ir_hash"] = promoted_rule_ir_hash
    execution_record = cast(
        dict[str, object],
        exalted_patron["execution_record_payload"],
    )
    execution_record["rule_ir_hash"] = promoted_rule_ir_hash
    execution_record["runtime_support_status"] = "engine_consumed"
    execution_record["source_ids"] = list(
        dict.fromkeys(
            (
                *cast(list[str], execution_record["source_ids"]),
                (
                    "gw-11e-phase17e-exact-faction-subrules-2026-27:"
                    "bridge-source-row:Enhancements:000010654003"
                ),
                (
                    "gw-11e-phase17e-exact-faction-subrules-2026-27:"
                    "enhancement:emperors-children:"
                    "court-of-the-phoenician:000010654003"
                ),
                (
                    "gw-11e-faction-detachments-2026-27:"
                    "detachment:emperors-children:court-of-the-phoenician"
                ),
                ("gw-11e-phase17e-faction-coverage-2026-07:source-pdf:emperors-children"),
            )
        )
    )
    datasheet_path = ARTIFACT_DIR / "datasheets.json"
    preview_path = ARTIFACT_DIR / "datasheet-support-preview.json"
    preview = cast(dict[str, object], payloads[preview_path])
    preview["preview_marker"] = "current_source"
    preview["datasheet_artifact_sha256"] = _canonical_sha256(payloads[datasheet_path])

    package = cast(
        dict[str, object],
        _promote_value(json.loads(PACKAGE_ARTIFACT.read_text(encoding="utf-8"))),
    )
    package["activation_status"] = promotion.ACTIVATION_STATUS
    package["source_title"] = promotion.SOURCE_TITLE
    package["source_version"] = promotion.SOURCE_VERSION
    package["delta_ledger_sha256"] = _canonical_sha256(payloads[ARTIFACT_DIR / "delta-ledger.json"])
    references = cast(list[dict[str, object]], package["staged_data_artifacts"])
    references = [
        reference
        for reference in references
        if reference["artifact_id"] != promotion.SOURCE_PACKAGE_ID
    ]
    references.append(
        {
            "artifact_id": promotion.SOURCE_PACKAGE_ID,
            "artifact_path": "artifacts/current-sources.json",
            "artifact_sha256": _canonical_sha256(current_sources_payload),
        }
    )
    for reference in references:
        artifact_path = ARTIFACT_DIR / Path(cast(str, reference["artifact_path"])).name
        reference["artifact_sha256"] = _canonical_sha256(payloads[artifact_path])
    package["staged_data_artifacts"] = sorted(
        references, key=lambda reference: cast(str, reference["artifact_id"])
    )
    payloads[PACKAGE_ARTIFACT] = package
    return payloads


def _promote_value(value: object) -> object:
    if type(value) is str:
        promoted = value.replace(OLD_SOURCE_PACKAGE_ID, promotion.SOURCE_PACKAGE_ID)
        return promoted.replace("july_2026_candidate", "july_2026")
    if type(value) is list:
        return [_promote_value(item) for item in value]
    if type(value) is dict:
        promoted = {
            cast(str, key): _promote_value(item)
            for key, item in cast(dict[object, object], value).items()
        }
        if "provider_activation_status" in promoted:
            promoted["provider_activation_status"] = "current_default"
        return promoted
    return value


def _rewrite_phase17e_pdf_records() -> None:
    path = (
        ROOT
        / "src"
        / "warhammer40k_core"
        / "rules"
        / "source_packages"
        / "warhammer_40000_11th"
        / "faction_coverage_2026_27.py"
    )
    text = path.read_text(encoding="utf-8")
    marker = "_PDF_RECORDS = _validate_pdf_records("
    prefix, separator, _old_block = text.partition(marker)
    if not separator:
        raise ValueError("Phase 17E PDF record block marker is unavailable.")
    lines = [
        "_PDF_RECORDS = _validate_pdf_records(",
        "    tuple(",
        "        Phase17EFactionPdfRecord(",
        "            faction_id=record.faction_id,",
        "            faction_name=record.faction_name,",
        "            package_id=record.package_id,",
        "            title=record.title,",
        "            source_date=record.source_date,",
        '            pdf_filename=record.pdf_path.rsplit("/", maxsplit=1)[-1],',
        "            sha256=record.sha256,",
        "            bytes=record.bytes,",
        "        )",
        "        for record in faction_source_promotion_2026_07.current_source_records()",
        "    )",
        ")",
        "",
    ]
    replacement = "\n".join(lines)
    path.write_text(prefix + replacement, encoding="utf-8")


def _rewrite_datasheet_review_pdf_evidence() -> None:
    payload = cast(
        dict[str, object],
        json.loads(DATASHEET_REVIEW_MANIFEST.read_text(encoding="utf-8")),
    )
    factions = cast(list[dict[str, object]], payload["factions"])
    records = {
        record.faction_id: record
        for record in promotion.current_source_records()
        if record.faction_id != "chaos-daemons"
    }
    faction_ids = {cast(str, faction["faction_id"]) for faction in factions}
    if faction_ids != records.keys() or len(factions) != len(records):
        raise ValueError(
            "Datasheet review manifest must contain the exact non-Daemons current-source set."
        )
    for faction in factions:
        record = records[cast(str, faction["faction_id"])]
        faction["pdf_filename"] = Path(record.pdf_path).name
        faction["pdf_sha256"] = record.sha256
    _write_json(DATASHEET_REVIEW_MANIFEST, payload)


def _check_promotion() -> None:
    if PENDING_MANIFEST.exists():
        raise ValueError("July faction packs still have a pending-source designation.")
    current = load_official_source_manifest(CURRENT_MANIFEST)
    predecessors = load_official_source_manifest(PREDECESSOR_MANIFEST)
    current_ids = {_faction_id(entry) for entry in current}
    predecessor_ids = {_faction_id(entry) for entry in predecessors}
    if current_ids != promotion.CURRENT_FACTION_IDS:
        raise ValueError("Current faction manifest does not contain the exact 28-faction set.")
    if predecessor_ids != promotion.PROMOTED_FACTION_IDS:
        raise ValueError("June predecessor manifest does not contain the exact 27-faction set.")
    artifact = promotion.current_source_set()
    promotion.audit_exact_current_source_mapping(tuple(artifact.records))
    current_by_package = {entry.package_id: entry for entry in current}
    for record in artifact.records:
        entry = current_by_package.get(record.package_id)
        if entry is None or (
            entry.sha256,
            entry.local_cache_path,
            entry.expected_bytes,
        ) != (record.sha256, record.pdf_path, record.bytes):
            raise ValueError("Current source manifest drifted from the promotion artifact.")
    package = cast(
        dict[str, object],
        json.loads(PACKAGE_ARTIFACT.read_text(encoding="utf-8")),
    )
    if (
        package["source_package_id"] != promotion.SOURCE_PACKAGE_ID
        or package["activation_status"] != promotion.ACTIVATION_STATUS
    ):
        raise ValueError("July source package is not promoted as current.")
    review = cast(
        dict[str, object],
        json.loads(DATASHEET_REVIEW_MANIFEST.read_text(encoding="utf-8")),
    )
    review_factions = cast(list[dict[str, object]], review["factions"])
    review_by_faction = {cast(str, faction["faction_id"]): faction for faction in review_factions}
    expected_review_ids = promotion.CURRENT_FACTION_IDS - {"chaos-daemons"}
    if review_by_faction.keys() != expected_review_ids:
        raise ValueError("Datasheet review manifest current-source set drifted.")
    for record in artifact.records:
        if record.faction_id == "chaos-daemons":
            continue
        faction = review_by_faction[record.faction_id]
        if (
            faction["pdf_filename"] != Path(record.pdf_path).name
            or faction["pdf_sha256"] != record.sha256
        ):
            raise ValueError("Datasheet review PDF evidence is not current.")


def _validate_input_sets(
    *,
    june_entries: tuple[OfficialSourceManifestEntry, ...],
    july_entries: tuple[OfficialSourceManifestEntry, ...],
) -> None:
    june_ids = {_faction_id(entry) for entry in june_entries}
    july_ids = {_faction_id(entry) for entry in july_entries}
    if june_ids != promotion.CURRENT_FACTION_IDS or len(june_entries) != 28:
        raise ValueError("June source input must contain the exact 28-faction set.")
    if july_ids != promotion.PROMOTED_FACTION_IDS or len(july_entries) != 27:
        raise ValueError("July source input must contain the exact 27 replacement factions.")


def _record_payload(
    *,
    faction_id: str,
    faction_name: str,
    current: OfficialSourceManifestEntry,
    predecessor: OfficialSourceManifestEntry | None,
    semantic_change_status: str,
) -> dict[str, object]:
    _require_complete_entry(current)
    if predecessor is not None:
        _require_complete_entry(predecessor)
    return {
        "bytes": current.expected_bytes,
        "faction_id": faction_id,
        "faction_name": faction_name,
        "package_id": current.package_id,
        "pdf_path": current.local_cache_path,
        "predecessor_package_id": (None if predecessor is None else predecessor.package_id),
        "predecessor_pdf_path": (None if predecessor is None else predecessor.local_cache_path),
        "predecessor_pdf_sha256": None if predecessor is None else predecessor.sha256,
        "semantic_change_status": semantic_change_status,
        "sha256": current.sha256,
        "source_date": current.source_date,
        "title": current.title,
    }


def _faction_id(entry: OfficialSourceManifestEntry) -> str:
    prefix = "gw-11e-"
    suffixes = ("-faction-pack-2026-06", "-faction-pack-2026-07")
    for suffix in suffixes:
        if entry.package_id.startswith(prefix) and entry.package_id.endswith(suffix):
            return entry.package_id[len(prefix) : -len(suffix)]
    raise ValueError("Faction-pack package ID is not canonical.")


def _require_complete_entry(entry: OfficialSourceManifestEntry) -> None:
    if not entry.sha256 or entry.expected_bytes is None or entry.local_cache_path is None:
        raise ValueError("Faction-pack source manifest entry is incomplete.")


def _entry_by_package_id(
    entries: tuple[OfficialSourceManifestEntry, ...],
    package_id: str,
) -> OfficialSourceManifestEntry:
    matches = tuple(entry for entry in entries if entry.package_id == package_id)
    if len(matches) != 1:
        raise ValueError("Faction-pack package identity must occur exactly once.")
    return matches[0]


def _manifest_text(entries: tuple[OfficialSourceManifestEntry, ...]) -> str:
    lines = ["sources:"]
    for entry in entries:
        _require_complete_entry(entry)
        values: tuple[tuple[str, object], ...] = (
            ("package_id", entry.package_id),
            ("title", entry.title),
            ("source_url", entry.source_url),
            ("source_page_url", entry.source_page_url),
            ("publisher", entry.publisher),
            ("language", entry.language),
            ("edition", entry.edition),
            ("source_date", entry.source_date),
            ("sha256", entry.sha256),
            ("bytes", entry.expected_bytes),
            ("license_note", entry.license_note),
            ("local_cache_path", entry.local_cache_path),
        )
        for index, (key, value) in enumerate(values):
            prefix = "  - " if index == 0 else "    "
            rendered = str(value) if type(value) is int else json.dumps(value, ensure_ascii=False)
            lines.append(f"{prefix}{key}: {rendered}")
    return "\n".join(lines) + "\n"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _canonical_sha256(payload: object) -> str:
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


if __name__ == "__main__":
    main()
