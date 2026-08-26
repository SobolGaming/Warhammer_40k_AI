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
    / "core_stratagems_2026_08"
    / "artifacts"
    / "package.json"
)


class CoreStratagemAppSourceBuildError(ValueError):
    """Raised when the reviewed Core Stratagem source artifact cannot be built."""


def _sha256_payload(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _required_dict(value: object, *, field_name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise CoreStratagemAppSourceBuildError(f"{field_name} must be an object.")
    return cast(dict[str, object], value)


def _required_list(value: object, *, field_name: str) -> list[object]:
    if type(value) is not list:
        raise CoreStratagemAppSourceBuildError(f"{field_name} must be a list.")
    return cast(list[object], value)


def _required_text(value: object, *, field_name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise CoreStratagemAppSourceBuildError(f"{field_name} must be non-empty stripped text.")
    return value


def _evidence_payload(
    *,
    context: dict[str, object],
    evidence: dict[str, object],
) -> dict[str, object]:
    return {
        "evidence_id": evidence["evidence_id"],
        "rule_source_id": evidence["rule_source_id"],
        "evidence_kind": context["evidence_kind"],
        "authority": context["authority"],
        "project_authority_policy_id": context["project_authority_policy_id"],
        "review_audit_id": context["review_audit_id"],
        "review_audit_row_id": evidence["review_audit_row_id"],
        "review_audit_source_observation_sha256": evidence[
            "review_audit_source_observation_sha256"
        ],
        "provider_name": context["provider_name"],
        "source_title": context["source_title"],
        "source_platform": context["source_platform"],
        "source_url": evidence["source_url"],
        "observed_at": context["observed_at"],
        "app_version": context["app_version"],
        "app_build": context["app_build"],
        "capture_artifact_path": context["capture_artifact_path"],
        "capture_sha256": context["capture_sha256"],
        "transcription_sha256": evidence["transcription_sha256"],
        "official_corroborating_source_ids": context["official_corroborating_source_ids"],
        "verification_status": evidence["verification_status"],
        "provider_non_affiliation_recorded": context["provider_non_affiliation_recorded"],
        "observation_sha256": evidence["observation_sha256"],
        "load_support_status": evidence["load_support_status"],
        "semantic_execution_status": evidence["semantic_execution_status"],
        "runtime_consumer_ids": evidence["runtime_consumer_ids"],
    }


def _evidence_observation_sha256(payload: dict[str, object]) -> str:
    observation_payload = copy.deepcopy(payload)
    observation_payload["observation_sha256"] = ""
    observation_payload["load_support_status"] = "not_loaded"
    observation_payload["semantic_execution_status"] = "not_certified"
    observation_payload["runtime_consumer_ids"] = []
    return _sha256_payload(observation_payload)


def _anomaly_observation_sha256(anomaly: dict[str, object]) -> str:
    observation_payload = copy.deepcopy(anomaly)
    observation_payload["source_observation_sha256"] = ""
    return _sha256_payload(observation_payload)


def _derived_payload(payload: dict[str, object]) -> dict[str, object]:
    derived = copy.deepcopy(payload)
    contexts = _required_list(derived["evidence_contexts"], field_name="evidence_contexts")
    contexts_by_id = {
        _required_text(context["context_id"], field_name="context_id"): context
        for value in contexts
        for context in (_required_dict(value, field_name="evidence context"),)
    }
    if len(contexts_by_id) != len(contexts):
        raise CoreStratagemAppSourceBuildError("Evidence context IDs must be unique.")

    evidence_values = _required_list(derived["evidence_records"], field_name="evidence_records")
    evidence_records = [
        _required_dict(value, field_name="evidence record") for value in evidence_values
    ]
    evidence_by_id = {
        _required_text(evidence["evidence_id"], field_name="evidence_id"): evidence
        for evidence in evidence_records
    }
    if len(evidence_by_id) != len(evidence_records):
        raise CoreStratagemAppSourceBuildError("Evidence IDs must be unique.")

    rules = _required_list(derived["rules"], field_name="rules")
    for value in rules:
        rule = _required_dict(value, field_name="rule")
        source_text = _required_text(rule["source_text"], field_name="source_text")
        transcription_sha256 = hashlib.sha256(source_text.encode()).hexdigest()
        rule["transcription_sha256"] = transcription_sha256
        evidence_ids = _required_list(rule["evidence_ids"], field_name="evidence_ids")
        mirror_observation_sha256: str | None = None
        for evidence_id_value in evidence_ids:
            evidence_id = _required_text(evidence_id_value, field_name="evidence_id")
            try:
                evidence = evidence_by_id[evidence_id]
            except KeyError as exc:
                raise CoreStratagemAppSourceBuildError(
                    "Rule evidence_id is absent from evidence_records."
                ) from exc
            if evidence["rule_source_id"] != rule["source_id"]:
                raise CoreStratagemAppSourceBuildError(
                    "Rule evidence source identity does not match its rule."
                )
            evidence["transcription_sha256"] = transcription_sha256
            evidence["load_support_status"] = rule["load_support_status"]
            evidence["semantic_execution_status"] = rule["semantic_execution_status"]
            evidence["runtime_consumer_ids"] = rule["runtime_consumer_ids"]
            context_id = _required_text(
                evidence["evidence_context_id"],
                field_name="evidence_context_id",
            )
            try:
                context = contexts_by_id[context_id]
            except KeyError as exc:
                raise CoreStratagemAppSourceBuildError(
                    "Evidence record context is absent from evidence_contexts."
                ) from exc
            evidence_payload = _evidence_payload(context=context, evidence=evidence)
            evidence["observation_sha256"] = _evidence_observation_sha256(evidence_payload)
            if context["evidence_kind"] == "third_party_mirror":
                mirror_observation_sha256 = cast(str, evidence["observation_sha256"])
        if mirror_observation_sha256 is None:
            raise CoreStratagemAppSourceBuildError(
                "Each source rule requires a third-party mirror observation."
            )
        rule["source_observation_sha256"] = mirror_observation_sha256

    anomalies = _required_list(derived["numbering_anomalies"], field_name="numbering_anomalies")
    for value in anomalies:
        anomaly = _required_dict(value, field_name="numbering anomaly")
        source_text = _required_text(
            anomaly["source_text"],
            field_name="numbering anomaly source_text",
        )
        anomaly["transcription_sha256"] = hashlib.sha256(source_text.encode()).hexdigest()
        anomaly["source_observation_sha256"] = _anomaly_observation_sha256(anomaly)

    derived["package_hash"] = ""
    derived["package_hash"] = _sha256_payload(derived)
    return derived


def _canonical_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the reviewed P15D Core Stratagem App-source artifact."
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
            raise CoreStratagemAppSourceBuildError(
                "Core Stratagem App-source artifact is stale; rebuild it without --check."
            )
        return 0
    ARTIFACT_PATH.write_bytes(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
