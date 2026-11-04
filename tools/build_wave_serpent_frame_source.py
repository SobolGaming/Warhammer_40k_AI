"""Rebuild the bounded Wave Serpent FRAME source admission from reviewed bytes."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import cast

from warhammer40k_core.rules.source_overlay import SourceOverlayPack, SourceOverlayPackDraftPayload

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data/source_audits/wave_serpent_frame_2026_11"
PACK = ROOT / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
OBSERVATION_SHA256 = "ffdf2378872f9c4bf75bee0fb91e11bf4cee0f10835480a4d53e316fb28374a3"


def _bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def build_payloads() -> dict[Path, bytes]:
    observed = (AUDIT / "reviewed-observation.json").read_bytes()
    if hashlib.sha256(observed).hexdigest() != OBSERVATION_SHA256:
        raise ValueError("Wave Serpent reviewed source observation drifted.")
    source = json.loads(observed)
    capture = source["capture"]
    template = (PACK / "starfang_keyword_2026_11.audit.json").read_bytes()
    if (
        hashlib.sha256(template).hexdigest()
        != "6c003c857a8bba59ad8fb6b369208800bc8e5271ea858560df7532b32bb493df"
    ):
        raise ValueError("Retained faction audit template drifted.")
    audit = json.loads(template)
    row = copy.deepcopy(audit["observations"][0])
    text = capture["captured_text"]
    operative = text[text.index("Wave Serpent\nDATASHEET") :]
    row.update(
        observation_id="wave-serpent-frame-2026-11-03:datasheet:wave-serpent",
        source_id="faction-app:aeldari:datasheet:wave-serpent",
        source_title="Wave Serpent",
        source_url=capture["url"],
        observed_at=capture["observed_utc"],
        captured_text=text,
        capture_sha256=hashlib.sha256(text.encode()).hexdigest(),
        operative_start="Wave Serpent\nDATASHEET",
        operative_text=operative,
        transcription_sha256=hashlib.sha256(operative.encode()).hexdigest(),
        scope_review=source["authority_limit"]
        + (
            " Only ordinary/global FRAME is added; version995 is global update context, "
            "not keyword change date."
        ),
        geometry=[
            {
                "model_role": "Wave Serpent",
                "base_statement": "Wave Serpent Large Flying Base",
                "base_status": "observed",
                "height_status": "not_observed",
                "fieldability_certified": False,
                "volume_authority": "accepted_model_geometry_catalog_evidence_required",
            }
        ],
    )
    row["source_observation_sha256"] = hashlib.sha256(
        json.dumps(
            {k: v for k, v in row.items() if k != "source_observation_sha256"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    audit.update(
        audit_id="wave-serpent-frame-app-mirror-2026-11-03",
        selected_source_ids=[row["source_id"]],
        observations=[row],
    )
    audit["version_evidence"]["observed_at"] = source["context"]["observed_utc"]
    draft = cast(
        SourceOverlayPackDraftPayload,
        {
            "package_id": {
                "namespace": "40k-app",
                "package_name": "wave-serpent-frame",
                "version": "reviewed-2026-11-03",
            },
            "catalog_version": {
                "version_id": "warhammer-40000-11th-wave-serpent-frame-2026-11",
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
                    "op_id": "wave-serpent-add-ordinary-frame",
                    "order_index": source["new_order_index"],
                    "operation_kind": "add_row",
                    "target_edition": "warhammer-40000-11th",
                    "source_table": "Datasheets_keywords",
                    "source_row_id": source["new_row_id"],
                    "source_reference": capture["url"],
                    "effective_date": "2026-11-03",
                    "reason": (
                        "Add missing ordinary/global FRAME from complete current App observation; "
                        "preserve every predecessor row. The source adapter binds exact "
                        "predecessor table and keyword absence."
                    ),
                    "expected_preimage_hash": None,
                    "fields": {
                        "datasheet_id": "000000599",
                        "is_faction_keyword": "false",
                        "keyword": "Frame",
                        "model": "",
                    },
                }
            ],
        },
    )
    return {
        PACK / "wave_serpent_frame_2026_11.audit.json": _bytes(audit),
        PACK / "wave_serpent_frame_2026_11.overlay-pack.json": _bytes(
            SourceOverlayPack.from_unhashed_payload(draft).to_payload()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, content in build_payloads().items():
        if args.check:
            if path.read_bytes() != content:
                raise ValueError(f"Wave Serpent source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.write_bytes(content)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(content).hexdigest()}")


if __name__ == "__main__":
    main()
