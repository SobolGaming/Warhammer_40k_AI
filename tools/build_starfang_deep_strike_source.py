"""Build the two bounded current source admissions from pinned reviewed observations."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from warhammer40k_core.rules.source_overlay import SourceOverlayPack, SourceOverlayPackDraftPayload

ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = ROOT / "data/source_audits/starfang_deep_strike_2026_11"
PACKAGES = ROOT / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
OBSERVATIONS_SHA256 = "048e21d8284625e4ddb89111a06fdb064e499e80530428f2db6ed978c05798e1"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
AUDIT_ID = "deep-strike-maintained-app-mirror-2026-11-03"


def _hash(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _canonical_hash(value: object) -> str:
    return _hash(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def build_payloads() -> dict[Path, bytes]:
    raw = (AUDIT_DIR / "reviewed-observations.json").read_bytes()
    if _hash(raw) != OBSERVATIONS_SHA256:
        raise ValueError("Starfang/Deep Strike reviewed observations drifted.")
    observations = json.loads(raw)
    fresh = observations["fresh_observations"]
    starfang, core = fresh[0], fresh[2]
    scope = observations["scope"]["deep_strike"]
    # Reuse the admitted v2 faction observation shape and historical-primary link.
    template_raw = (PACKAGES / "aeldari_banshee_eldrad_2026_11.audit.json").read_bytes()
    if _hash(template_raw) != "51e632f19ebf8a2d8537946f5267a9fe19c4eeba9c632129f172e940dd098108":
        raise ValueError("Retained faction audit template drifted.")
    template = json.loads(template_raw)
    row = copy.deepcopy(template["observations"][0])
    operative = starfang["main_text"][starfang["main_text"].index("Starfangs\nDATASHEET") :]
    row.update(
        observation_id="starfang-keyword-2026-11-03:datasheet:starfangs",
        source_id="faction-app:aeldari:datasheet:starfangs",
        source_title="Starfangs",
        source_url=starfang["url"],
        observed_at=starfang["observed_utc"],
        captured_text=starfang["main_text"],
        capture_sha256=_hash(starfang["main_text"]),
        operative_start="Starfangs\nDATASHEET",
        operative_text=operative,
        transcription_sha256=_hash(operative),
        scope_review=(
            "Complete retained Starfangs page; this admission corrects on"
            "ly ordinary keyword STARFANG. Preserve plural datasheet and "
            "model identity STARFANGS and all unrelated data. Version 995"
            " is update-list context, not an App-build or keyword-change-"
            "date attestation. No new geometry or gameplay certification."
        ),
        geometry=[
            {
                "base_statement": "Starfangs 105x70mm Oval Base",
                "base_status": "observed",
                "fieldability_certified": False,
                "height_status": "not_observed",
                "model_role": "Starfangs",
                "volume_authority": "accepted_model_geometry_catalog_evidence_required",
            }
        ],
    )
    row["source_observation_sha256"] = _canonical_hash(
        {k: v for k, v in row.items() if k != "source_observation_sha256"}
    )
    statement = "Version 995\nReleased 2026-10-16."
    audit = {
        **template,
        "audit_id": "starfang-keyword-app-mirror-2026-11-03",
        "selected_source_ids": [row["source_id"]],
        "observations": [row],
        "version_evidence": {
            "source_url": observations["updates_context"]["url"],
            "observed_at": observations["updates_context"]["observed_utc"],
            "statement": statement,
            "transcription_sha256": _hash(statement),
        },
    }
    draft: SourceOverlayPackDraftPayload = {
        "package_id": {
            "namespace": "40k-app",
            "package_name": "starfang-keyword",
            "version": "reviewed-2026-11-03",
        },
        "catalog_version": {
            "version_id": "warhammer-40000-11th-starfang-keyword-2026-11",
            "source_date": "2026-11-03",
        },
        "base_source_package_id": {
            "namespace": "wahapedia",
            "package_name": "source-mirror",
            "version": "10th-edition-2026-06-14",
        },
        "target_edition": "warhammer-40000-11th",
        "effective_date": "2026-11-03",
        "schema_version": "phase17-source-overlay-v1",
        "operations": [
            {
                "target_edition": "warhammer-40000-11th",
                "source_table": "Datasheets_keywords",
                "source_reference": starfang["url"],
                "effective_date": "2026-11-03",
                "reason": (
                    "Correct ordinary STARFANG keyword; preserve plural exact nam"
                    "e identity. Both row identities and the predecessor preimage"
                    " are bound by this governed overlay."
                ),
                "op_id": "starfang-retire-plural-ordinary-keyword",
                "order_index": 1,
                "operation_kind": "supersede_row",
                "source_row_id": "000004195:Starfangs:global:false:15639",
                "expected_preimage_hash": (
                    "055b20e2b17f63cd0abb28aef0691b11ffb99c7f11df66f68298ac5018582aac"
                ),
                "fields": {},
            },
            {
                "target_edition": "warhammer-40000-11th",
                "source_table": "Datasheets_keywords",
                "source_reference": starfang["url"],
                "effective_date": "2026-11-03",
                "reason": (
                    "Correct ordinary STARFANG keyword; preserve plural exact nam"
                    "e identity. Both row identities and the predecessor preimage"
                    " are bound by this governed overlay."
                ),
                "op_id": "starfang-add-singular-ordinary-keyword",
                "order_index": 15637,
                "operation_kind": "add_row",
                "source_row_id": "000004195:Starfang:global:false:15639",
                "expected_preimage_hash": None,
                "fields": {
                    "datasheet_id": "000004195",
                    "is_faction_keyword": "false",
                    "keyword": "Starfang",
                    "model": "",
                },
            },
        ],
    }
    overlay = SourceOverlayPack.from_unhashed_payload(draft).to_payload()
    text, source_id, dependency = (
        scope["proposed_description"],
        scope["proposed_source_id"],
        scope["dependency_source_id"],
    )
    core_row = {
        "row_id": "24.09:40k-app",
        "provider_name": "40k.app",
        "source_url": core["url"].split("#")[0],
        "observed_at": core["observed_utc"],
        "app_version": None,
        "policy_id": POLICY,
        "rule_source_id": source_id,
        "transcription_sha256": _hash(text),
        "provider_non_affiliation_recorded": True,
        "rendered_section_sha256": _hash(core["main_text"]),
        "reviewed_observations_sha256": OBSERVATIONS_SHA256,
    }
    core_row_hash = _canonical_hash(core_row)
    template_raw = (PACKAGES / "core_descriptions_2026_11/artifacts/package.json").read_bytes()
    if _hash(template_raw) != "8a82ba2800f48d34993ed332cc1a4d11e7eda895ee61bd2af36a51a98a51649e":
        raise ValueError("Retained Core description template drifted.")
    evidence: list[dict[str, Any]] = []
    for original in json.loads(template_raw)["evidence"][:2]:
        item = {
            **original,
            "rule_source_id": source_id,
            "source_title": "40k.app 24.09",
            "transcription_sha256": _hash(text),
            "evidence_id": "deep-strike-review:24.09"
            if original["source_platform"] == "Repository"
            else "deep-strike:24.09:40k-app",
            "observation_sha256": "",
        }
        if original["source_platform"] == "Web":
            item.update(
                source_url=core_row["source_url"],
                observed_at=core["observed_utc"],
                review_audit_id=AUDIT_ID,
                review_audit_row_id=core_row["row_id"],
                review_audit_source_observation_sha256=core_row_hash,
            )
        item["observation_sha256"] = _canonical_hash({**item, "load_support_status": "not_loaded"})
        evidence.append(item)
    artifact: dict[str, object] = {
        "artifact_schema": "core-v2-core-descriptions-source-v1",
        "source_package_id": "gw-11e-core-deep-strike-description",
        "source_version": "maintained-app-mirror-observed-2026-11-03",
        "rules": [
            {
                "source_id": source_id,
                "section_id": "24.09",
                "source_text": text,
                "transcription_sha256": _hash(text),
                "dependency_source_ids": [dependency],
                "load_support_status": "loaded",
                "semantic_execution_status": "not_certified",
                "runtime_consumer_ids": [],
            }
        ],
        "evidence": evidence,
        "package_hash": "",
    }
    artifact["package_hash"] = _canonical_hash(artifact)
    admission = {
        "audit_id": AUDIT_ID,
        "rows": [{**core_row, "source_observation_sha256": core_row_hash}],
        "starfang": {
            "audit_id": audit["audit_id"],
            "observation_sha256": row["source_observation_sha256"],
            "overlay_sha256": _hash(_bytes(overlay)),
            "old_row_id": overlay["operations"][0]["source_row_id"],
            "new_row_id": overlay["operations"][1]["source_row_id"],
            "preimage": overlay["operations"][0]["expected_preimage_hash"],
        },
        "dependency": {
            "source_id": dependency,
            "artifact_sha256": "d22f5ca58b27172445f595ebe4a4763e372162950cb825d48cb7816073c488c1",
            "transcription_sha256": (
                "3ebcf9f594a98f20242c6e3272a5bb3ef63345bd1aff0657560b887321464eba"
            ),
        },
        "authority_limit": observations["authority_limit"],
    }
    catalog_ids = {
        "native60": "chaos-daemons-bridge-catalog",
        "paired27": "core-v2:court-of-slaughter-anvanth:2026-08",
        "Daemons5": "core-v2:chaos-daemons-roster:2026-07",
    }
    successor = {
        "schema": "core-v2-deep-strike-catalog-successor-v1",
        "ability_id": scope["ability_id"],
        "source_id": source_id,
        "dependency_source_id": dependency,
        "historical_text": scope["old_description"],
        "current_text": text,
        "occurrences": [
            {
                "catalog_id": catalog_ids[occurrence["surface"]],
                "datasheet_id": occurrence["datasheet_id"],
                "historical_descriptor_sha256": _canonical_hash(occurrence["descriptor"]),
                "current_descriptor_sha256": _canonical_hash(
                    {**occurrence["descriptor"], "effect_description": text}
                ),
            }
            for occurrence in scope["occurrences"]
        ],
    }
    return {
        PACKAGES / "starfang_keyword_2026_11.audit.json": _bytes(audit),
        PACKAGES / "starfang_keyword_2026_11.overlay-pack.json": _bytes(overlay),
        PACKAGES / "core_deep_strike_description_2026_11/artifacts/package.json": _bytes(artifact),
        AUDIT_DIR / "source-admission.audit.json": _bytes(admission),
        PACKAGES / "core_deep_strike_description_2026_11/artifacts/catalog-successor.json": _bytes(
            successor
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, raw in build_payloads().items():
        if args.check:
            if path.read_bytes() != raw:
                raise ValueError(f"Bounded source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {_hash(raw)}")


if __name__ == "__main__":
    main()
