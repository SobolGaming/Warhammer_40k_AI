"""Rebuild the bounded Daemons source correction from reviewed rendered observations."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, cast

from warhammer40k_core.rules.source_overlay import SourceOverlayPack, SourceOverlayPackDraftPayload

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data/source_audits/daemons_native_2026_11"
PACK = ROOT / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
OBSERVATION_SHA256 = "185e1eef3f58b8e7f7357a93e2f6cb694614c2339893a8a8cb70d2c9bb022d13"


def _bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def build_payloads() -> dict[Path, bytes]:
    raw = (AUDIT / "reviewed-observation.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != OBSERVATION_SHA256:
        raise ValueError("Daemons reviewed source observation drifted.")
    source = json.loads(raw)
    template = (PACK / "wave_serpent_frame_2026_11.audit.json").read_bytes()
    if (
        hashlib.sha256(template).hexdigest()
        != "b4c1acebb902bac7811df028b8f107ed47e531ba8bf0e3e69fbb8b1e9f518e7d"
    ):
        raise ValueError("Retained faction audit schema template drifted.")
    audit = json.loads(template)
    observations: list[dict[str, Any]] = []
    for slug, title, bases in (
        ("belakor", "Be\u2019lakor", ("Be\u2019lakor 100mm",)),
        ("bloodletters", "Bloodletters", ("Bloodreaper 32mm", "Bloodletter 32mm")),
    ):
        capture = next(c for c in source["captures"] if c["file"] == slug + "-current.txt")
        row = copy.deepcopy(audit["observations"][0])
        text = capture["captured_text"]
        start = title + "\nDATASHEET"
        operative = text[text.index(start) :]
        row.update(
            observation_id="daemons-native-2026-11-04:datasheet:" + slug,
            source_id="faction-app:chaos-daemons:datasheet:" + slug,
            owning_faction_source_id="faction-app:chaos-daemons",
            source_title=title,
            source_url=capture["url"],
            observed_at=capture["observed_utc"],
            captured_text=text,
            capture_sha256=hashlib.sha256(text.encode()).hexdigest(),
            operative_start=start,
            operative_text=operative,
            transcription_sha256=hashlib.sha256(operative.encode()).hexdigest(),
            scope_review=source["authority_limit"],
            official_source_ids=[source["historical_primary"]["source_id"]],
            geometry=[
                {
                    "model_role": base.rsplit(" ", 1)[0],
                    "base_statement": base,
                    "base_status": "observed",
                    "height_status": "not_observed",
                    "fieldability_certified": False,
                    "volume_authority": "accepted_model_geometry_catalog_evidence_required",
                }
                for base in bases
            ],
        )
        row["source_observation_sha256"] = hashlib.sha256(
            json.dumps(
                {k: v for k, v in row.items() if k != "source_observation_sha256"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        observations.append(row)
    audit.update(
        audit_id="daemons-native-app-mirror-2026-11-04",
        observations=observations,
        selected_source_ids=[r["source_id"] for r in observations],
        official_sources=[source["historical_primary"]],
    )
    context = next(c for c in source["captures"] if c["file"] == "app-updates-index-context.txt")
    audit["version_evidence"]["observed_at"] = context["observed_utc"]
    predecessor = next(r for r in source["predecessor"]["rows"] if r["table"] == "Datasheets")
    fields = predecessor["fields"]
    if fields["damaged_w"] != "1-6" or fields["damaged_description"].count("1-6") != 1:
        raise ValueError("Be'lakor damaged preimage drifted.")
    draft = cast(
        SourceOverlayPackDraftPayload,
        {
            "package_id": {
                "namespace": "40k-app",
                "package_name": "daemons-native",
                "version": "reviewed-2026-11-04",
            },
            "catalog_version": {
                "version_id": "warhammer-40000-11th-daemons-native-2026-11",
                "source_date": "2026-11-04",
            },
            "base_source_package_id": {
                "namespace": "wahapedia",
                "package_name": "source-mirror",
                "version": "10th-edition-2026-06-14",
            },
            "target_edition": "warhammer-40000-11th",
            "effective_date": "2026-11-04",
            "schema_version": "phase17-source-overlay-v1",
            "operations": [
                {
                    "op_id": "belakor-current-damaged-one-to-seven",
                    "order_index": 0,
                    "operation_kind": "update_row",
                    "target_edition": "warhammer-40000-11th",
                    "source_table": "Datasheets",
                    "source_row_id": "000001148",
                    "source_reference": observations[0]["source_url"],
                    "effective_date": "2026-11-04",
                    "reason": (
                        "Current complete App datasheet requires DAMAGED 1-7; "
                        "update only threshold and corresponding prose."
                    ),
                    "expected_preimage_hash": predecessor["preimage_hash"],
                    "fields": {
                        "damaged_w": "1-7",
                        "damaged_description": fields["damaged_description"].replace("1-6", "1-7"),
                    },
                }
            ],
        },
    )
    return {
        PACK / "daemons_native_2026_11.audit.json": _bytes(audit),
        PACK / "daemons_native_2026_11.overlay-pack.json": _bytes(
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
                raise ValueError(f"Daemons source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.write_bytes(content)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(content).hexdigest()}")


if __name__ == "__main__":
    main()
