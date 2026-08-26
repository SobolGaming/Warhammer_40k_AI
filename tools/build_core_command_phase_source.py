from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "core_command_phase_2026_08"
    / "artifacts"
    / "package.json"
)


class CoreCommandPhaseSourceBuildError(ValueError):
    """Raised when the reviewed Command-phase source artifact cannot be built."""


def _sha256_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _required_dict(value: object, *, field_name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise CoreCommandPhaseSourceBuildError(f"{field_name} must be an object.")
    return cast(dict[str, object], value)


def _required_list(value: object, *, field_name: str) -> list[object]:
    if type(value) is not list:
        raise CoreCommandPhaseSourceBuildError(f"{field_name} must be a list.")
    return cast(list[object], value)


def _required_text(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise CoreCommandPhaseSourceBuildError(f"{field_name} must be non-empty stripped text.")
    return value


def _evidence_observation_sha256(evidence: dict[str, object]) -> str:
    observation = copy.deepcopy(evidence)
    observation["observation_sha256"] = ""
    observation["load_support_status"] = "not_loaded"
    observation["semantic_execution_status"] = "not_certified"
    observation["runtime_consumer_ids"] = []
    return _sha256_payload(observation)


def _derived_payload(payload: dict[str, object]) -> dict[str, object]:
    derived = copy.deepcopy(payload)
    evidence_values = _required_list(
        derived["evidence_records"],
        field_name="evidence_records",
    )
    evidence_records = [
        _required_dict(value, field_name="evidence record") for value in evidence_values
    ]
    evidence_by_id = {
        _required_text(evidence["evidence_id"], field_name="evidence_id"): evidence
        for evidence in evidence_records
    }
    if len(evidence_by_id) != len(evidence_records):
        raise CoreCommandPhaseSourceBuildError("Evidence IDs must be unique.")

    rules = _required_list(derived["rules"], field_name="rules")
    for value in rules:
        rule = _required_dict(value, field_name="rule")
        source_text = _required_text(
            rule["source_text"],
            field_name="source_text",
        )
        official_pdf_source_text = _required_text(
            rule["official_pdf_source_text"],
            field_name="official_pdf_source_text",
        )
        transcription_sha256 = hashlib.sha256(source_text.encode()).hexdigest()
        rule["transcription_sha256"] = transcription_sha256
        rule["official_pdf_transcription_sha256"] = hashlib.sha256(
            official_pdf_source_text.encode()
        ).hexdigest()
        evidence_ids = _required_list(rule["evidence_ids"], field_name="evidence_ids")
        mirror_observation_sha256: str | None = None
        for evidence_id_value in evidence_ids:
            evidence_id = _required_text(evidence_id_value, field_name="evidence_id")
            try:
                evidence = evidence_by_id[evidence_id]
            except KeyError as exc:
                raise CoreCommandPhaseSourceBuildError(
                    "Rule evidence_id is absent from evidence_records."
                ) from exc
            if evidence["rule_source_id"] != rule["source_id"]:
                raise CoreCommandPhaseSourceBuildError(
                    "Rule evidence source identity does not match its rule."
                )
            evidence["transcription_sha256"] = transcription_sha256
            evidence["load_support_status"] = rule["load_support_status"]
            evidence["semantic_execution_status"] = rule["semantic_execution_status"]
            evidence["runtime_consumer_ids"] = rule["runtime_consumer_ids"]
            evidence["observation_sha256"] = _evidence_observation_sha256(evidence)
            if evidence["evidence_kind"] == "third_party_mirror":
                mirror_observation_sha256 = cast(str, evidence["observation_sha256"])
        if mirror_observation_sha256 is None:
            raise CoreCommandPhaseSourceBuildError(
                "Each Command-phase rule requires an audited-category mirror observation."
            )
        rule["source_observation_sha256"] = mirror_observation_sha256

    derived["package_hash"] = ""
    derived["package_hash"] = _sha256_payload(derived)
    return derived


def _canonical_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the reviewed P08A Command-phase source artifact."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail instead of writing when the committed artifact is stale.",
    )
    args = parser.parse_args()

    raw = ARTIFACT_PATH.read_bytes()
    payload = _required_dict(json.loads(raw), field_name="artifact")
    expected = _canonical_bytes(_derived_payload(payload))
    if args.check:
        if raw != expected:
            raise CoreCommandPhaseSourceBuildError(
                "Command-phase source artifact is stale; rebuild it without --check."
            )
        return 0
    ARTIFACT_PATH.write_bytes(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
