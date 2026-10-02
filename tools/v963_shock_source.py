"""Reviewed, offline current Shock source and its immutable observation tuple."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from tools.core_rules_order84_capture import capture_literals, fingerprint

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "data/source_audits/v963_shock"
AUDIT_PATH = DIRECTORY / "source.audit.json"
AUDIT_ID = "core-shock-disembark-maintained-app-mirror-2026-10-01"
ROW_ID = "rule:18.07:current-observation"
SOURCE_ID = "gw-11e-core-rules:transports:shock-disembark-move"
SOURCE_URL = "https://game-datamissions.com/11th/rules/core-rules"
OBSERVED_AT = "2026-10-01T12:04:31.127429+00:00"
POLICY_ID = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
SELECTED_RECORDS_SHA256 = "cf540b36de3a31ed1902a67330b0243519ce14c84b85fb46feb0f88885b02b00"
CAPTURE_SHA256S = {
    "changelog.html": "64ecd26644424f89e7a4760a037680d380a295b20ec24fa3a017066e255cc9fa",
    "core-rules.html": "e3a570737daa7dad215efce14d606e95e7cd194df2d7d61bed9a2353caeb8744",
    "core-page.js": "8b7e7a4004f8a55b17305013f181bf25933dff763e6737af407da254c5656026",
}


def sha256_payload(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def selected_records() -> dict[str, Any]:
    raw = (DIRECTORY / "selected-records.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != SELECTED_RECORDS_SHA256:
        raise ValueError("Reviewed V963 Shock source records drifted.")
    return json.loads(raw)  # type: ignore[no-any-return]


def shock_source_text() -> str:
    record = selected_records()["18.07"]
    # These are provider formatting delimiters, retained literally in the capture.
    blocks = ["".join(char for char in block if ord(char) >= 32) for block in record["text"]]
    return "\n".join([record["title"].upper(), *blocks])


def verify_source_observation() -> None:
    """Reproduce the selected full records from fixed captured literals offline."""
    for filename, expected in CAPTURE_SHA256S.items():
        if hashlib.sha256((DIRECTORY / "captures" / filename).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Reviewed V963 capture drifted: {filename}")
    captured = capture_literals((DIRECTORY / "captures/core-page.js").read_text(encoding="utf-8"))
    selected = selected_records()
    rules = {
        rule["ref"]: rule
        for group in captured["categories"]
        for section in group["subsections"]
        for rule in (section, *section.get("accordions", []))
    }
    for ref in ("03.02", "04.03.05", "12.08", "18.07"):
        if rules[ref] != selected[ref]:
            raise ValueError(f"Selected full V963 record differs from capture: {ref}")
    for key in ("duration-faq", "weaponless-faq"):
        if selected[key] not in captured["faqs"]:
            raise ValueError(f"Selected FAQ differs from capture: {key}")
    html = (DIRECTORY / "captures/changelog.html").read_text(encoding="utf-8")
    flight = "".join(
        json.loads(value)[1]
        for value in re.findall(r"self.__next_f.push\((\[1,.*?\])\)</script>", html)
    )
    start = flight.index('"versions":') + len('"versions":')
    versions = json.JSONDecoder().raw_decode(flight[start:])[0]
    for version in ("931", "963"):
        changes = next(row["changes"] for row in versions if row["version"] == version)
        if (
            selected[f"18.07-v{version}-{'added' if version == '931' else 'change'}-record"]
            not in changes
        ):
            raise ValueError(f"Selected v{version} change differs from capture.")
    baseline = json.loads((ROOT / "data/source_audits/order97/selected-sources.json").read_bytes())
    for ref in ("03.02", "04.03.05", "12.08"):
        old = next(row for row in baseline if row["locator"] == ref)
        current = {key: value for key, value in selected[ref].items() if key != "accordions"}
        if fingerprint(current) != old["source_sha256"]:
            raise ValueError(f"Unchanged controlling source drifted: {ref}")


def build_audit() -> dict[str, object]:
    row: dict[str, object] = {
        "row_id": ROW_ID,
        "provider_name": "Game Datamissions",
        "source_url": SOURCE_URL,
        "observed_at": OBSERVED_AT,
        "app_version": None,
        "app_build": None,
        "locale": "en",
        "policy_id": POLICY_ID,
        "rule_source_id": SOURCE_ID,
        "transcription": shock_source_text(),
        "transcription_sha256": hashlib.sha256(shock_source_text().encode()).hexdigest(),
        "provider_non_affiliation_recorded": True,
        "selected_records_sha256": SELECTED_RECORDS_SHA256,
        "capture_artifact_path": "data/source_audits/v963_shock/captures/core-page.js",
        "capture_sha256": "8b7e7a4004f8a55b17305013f181bf25933dff763e6737af407da254c5656026",
        "official_corroborating_source_ids": [],
    }
    row["source_observation_sha256"] = sha256_payload(row)
    return {
        "audit_id": AUDIT_ID,
        "source_authority": "project_authoritative_app_mirror",
        "rows": [row],
        "version_qualification": (
            "Full current live body observed at the stated timestamp; no live-body App-data "
            "version asserted. Separately retained v963 changelog identifies the change. "
            "Former full text is the v931 added record, not a separately archived v946 export."
        ),
        "supersession": {
            "scope": "Current 18.07 setup and after-moving consequences only",
            "historical_source": "v931 added record and pre-V963 runtime transcription retained",
            "removed": ["passenger engagement retention", "mandatory enemy Fight selections"],
            "added": ["charge ineligibility until the end of the turn"],
            "unchanged": [
                "source-backed permission",
                "embarked passenger in a placed Transport",
                "did not embark within that Transport this phase",
                "three-inch setup distance and ordinary 03.02 setup",
                "12.08 Engaging forced enemy Fight selections",
                "04.03.05 and weaponless FAQ selection/completion distinction",
            ],
            "historical_assertion_receipts": "data/source_audits/v963_shock/historical-inputs.json",
        },
    }
