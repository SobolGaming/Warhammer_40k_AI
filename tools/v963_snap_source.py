"""Select complete Snap Shooting authority from the retained maintained-mirror capture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.core_rules_order84_capture import capture_literals

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_PATH = "data/source_audits/v963_shock/captures/core-page.js"
CAPTURE_SHA256 = "8b7e7a4004f8a55b17305013f181bf25933dff763e6737af407da254c5656026"
OBSERVED_AT = "2026-10-01T12:04:31.127429+00:00"
SOURCE_URL = "https://game-datamissions.com/11th/rules/core-rules"
SOURCE_ID = "gw-11e-core-critical-hits:snap-shooting-no-critical-hits"
AUDIT_ID = "core-snap-shooting-maintained-app-mirror-2026-10-01"
ROW_ID = "rule:15.09:current-observation"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"


def selected_record() -> dict[str, object]:
    raw = (ROOT / CAPTURE_PATH).read_bytes()
    if hashlib.sha256(raw).hexdigest() != CAPTURE_SHA256:
        raise ValueError("Snap Shooting source capture differs from the reviewed bytes.")
    captured = capture_literals(raw.decode("utf-8"))
    matches = [
        rule
        for category in captured["categories"]
        for section in category["subsections"]
        for rule in (section, *section.get("accordions", []))
        if rule["ref"] == "15.09"
    ]
    if len(matches) != 1:
        raise ValueError("Snap Shooting requires exactly one complete source record.")
    return dict(matches[0])


def source_text() -> str:
    record = selected_record()
    blocks = record["text"]
    if not isinstance(blocks, list) or not all(isinstance(block, str) for block in blocks):
        raise ValueError("Snap Shooting source text blocks must be strings.")
    return "\n".join(
        [str(record["title"]).upper(), *("".join(c for c in b if ord(c) >= 32) for b in blocks)]
    )


def audit_row() -> dict[str, object]:
    row: dict[str, object] = {
        "row_id": ROW_ID,
        "provider_name": "Game Datamissions",
        "source_url": SOURCE_URL,
        "observed_at": OBSERVED_AT,
        "app_version": None,
        "app_build": None,
        "policy_id": POLICY,
        "rule_source_id": SOURCE_ID,
        "capture_artifact_path": CAPTURE_PATH,
        "capture_sha256": CAPTURE_SHA256,
        "transcription_sha256": hashlib.sha256(source_text().encode()).hexdigest(),
        "provider_non_affiliation_recorded": True,
    }
    row["source_observation_sha256"] = hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return row
