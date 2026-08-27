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

_REVIEWED_SEARCH_INDEX_OBSERVATION_ID = "40k-app-command-phase-search-index-2026-08-26"
_REVIEWED_SEARCH_INDEX_OBSERVATION_ROW_ID = "heading-sequence:command-phase"
_REVIEWED_SEARCH_INDEX_URL = "https://www.40k.app/rules"
_REVIEWED_SEARCH_INDEX_OBSERVED_AT = "2026-08-26T14:49:10-04:00"
_REVIEWED_PROJECT_AUTHORITY_POLICY_ID = (
    "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
)
_REVIEWED_SEARCH_INDEX_SOURCE_OBSERVATION_SHA256 = (
    "e646d81ba284b1a4b5572b96d68cbfca52ef8cdf15cedf7c2c69ae8b5066c0ab"
)
_REVIEWED_CATEGORY_CONTEXT: tuple[tuple[str, object], ...] = (
    ("authoritative_category_url", "https://www.40k.app/rules/08-command-phase"),
    ("authoritative_category_observed_at", "2026-08-25T00:00:00-04:00"),
    ("authoritative_category_scope", "category_08_review_audit_record"),
    ("category_body_capture_status", "review_audit_without_retained_page_body"),
    ("review_audit_id", "40k-app-core-rules-2026-08-25"),
    ("review_audit_row_id", "category:08"),
    (
        "review_audit_source_observation_sha256",
        "0920fa00c1f4ecbc9e46795c1d72695872b61e7577eeaa693c57eb12c26c871e",
    ),
)
_REVIEWED_SEARCH_INDEX_CONTEXT: tuple[tuple[str, object], ...] = (
    ("observation_id", _REVIEWED_SEARCH_INDEX_OBSERVATION_ID),
    ("observation_row_id", _REVIEWED_SEARCH_INDEX_OBSERVATION_ROW_ID),
    ("provider_name", "40k.app"),
    ("source_platform", "Web"),
    ("source_url", _REVIEWED_SEARCH_INDEX_URL),
    ("observed_at", _REVIEWED_SEARCH_INDEX_OBSERVED_AT),
    ("observation_scope", "command_phase_five_heading_sequence_only"),
    (
        "project_authority_policy_id",
        _REVIEWED_PROJECT_AUTHORITY_POLICY_ID,
    ),
    ("provider_non_affiliation_recorded", True),
    (
        "source_observation_sha256",
        _REVIEWED_SEARCH_INDEX_SOURCE_OBSERVATION_SHA256,
    ),
)
_REVIEWED_SEARCH_INDEX_HEADINGS: tuple[tuple[str, int, str], ...] = (
    ("start-of-command-phase", 1, "START OF COMMAND PHASE"),
    ("gain-core-cp", 2, "GAIN CORE CP"),
    ("battle-shock", 3, "BATTLE-SHOCK"),
    ("command-abilities", 4, "COMMAND ABILITIES"),
    ("end-of-command-phase", 5, "END OF COMMAND PHASE"),
)
_REVIEWED_RULE_EVIDENCE_LINKS: dict[str, tuple[str, str, str]] = {
    "start-of-command-phase": (
        "gw-11e-core-rules:command-phase:start-of-command-phase",
        "core-v2-p08a-source-review:start-of-command-phase",
        "40k-app-command-phase-search-index-2026-08-26:start-of-command-phase",
    ),
    "gain-core-cp": (
        "gw-11e-core-rules:command-phase:gain-core-cp",
        "core-v2-p08a-source-review:gain-core-cp",
        "40k-app-command-phase-search-index-2026-08-26:gain-core-cp",
    ),
    "battle-shock": (
        "gw-11e-core-rules:command-phase:battle-shock",
        "core-v2-p08b-source-review:battle-shock",
        "40k-app-command-phase-search-index-2026-08-26:battle-shock",
    ),
}


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


def _search_index_source_observation_sha256(observation: dict[str, object]) -> str:
    source_observation = copy.deepcopy(observation)
    source_observation["source_observation_sha256"] = ""
    return _sha256_payload(source_observation)


def _require_reviewed_fields(
    payload: dict[str, object],
    *,
    expected_fields: tuple[tuple[str, object], ...],
    context: str,
) -> None:
    if any(
        field_name not in payload or payload[field_name] != expected_value
        for field_name, expected_value in expected_fields
    ):
        raise CoreCommandPhaseSourceBuildError(
            f"Command-phase {context} drifted from its reviewed semantic identity."
        )


def _validate_reviewed_source_observation_identity(
    payload: dict[str, object],
) -> dict[str, object]:
    source_document = _required_dict(
        payload["source_document"],
        field_name="source_document",
    )
    _require_reviewed_fields(
        source_document,
        expected_fields=_REVIEWED_CATEGORY_CONTEXT,
        context="category locator",
    )
    search_index_observation = _required_dict(
        payload["search_index_observation"],
        field_name="search_index_observation",
    )
    _require_reviewed_fields(
        search_index_observation,
        expected_fields=_REVIEWED_SEARCH_INDEX_CONTEXT,
        context="search-index observation",
    )
    heading_values = _required_list(
        search_index_observation["headings"],
        field_name="search_index_observation.headings",
    )
    headings = tuple(
        _required_dict(value, field_name="search-index heading") for value in heading_values
    )
    observed_heading_identity = tuple(
        (
            heading.get("heading_id"),
            heading.get("display_order"),
            heading.get("normalized_heading"),
        )
        for heading in headings
    )
    if observed_heading_identity != _REVIEWED_SEARCH_INDEX_HEADINGS:
        raise CoreCommandPhaseSourceBuildError(
            "Command-phase search-index heading sequence drifted from its reviewed semantic "
            "identity."
        )
    return search_index_observation


def _validate_reviewed_rule_evidence_links(
    *,
    rules: list[object],
    evidence_by_id: dict[str, dict[str, object]],
) -> None:
    expected_evidence_ids = tuple(
        evidence_id
        for _, project_review_evidence_id, mirror_evidence_id in (
            _REVIEWED_RULE_EVIDENCE_LINKS.values()
        )
        for evidence_id in (project_review_evidence_id, mirror_evidence_id)
    )
    if tuple(evidence_by_id) != expected_evidence_ids:
        raise CoreCommandPhaseSourceBuildError(
            "Command-phase evidence inventory drifted from its reviewed semantic identity."
        )
    for value in rules:
        rule = _required_dict(value, field_name="rule")
        rule_id = _required_text(rule["rule_id"], field_name="rule_id")
        try:
            expected_source_id, project_review_evidence_id, mirror_evidence_id = (
                _REVIEWED_RULE_EVIDENCE_LINKS[rule_id]
            )
        except KeyError as exc:
            raise CoreCommandPhaseSourceBuildError(
                "Command-phase rule inventory drifted from its reviewed semantic identity."
            ) from exc
        evidence_ids = _required_list(rule["evidence_ids"], field_name="evidence_ids")
        if rule["source_id"] != expected_source_id or evidence_ids != [
            project_review_evidence_id,
            mirror_evidence_id,
        ]:
            raise CoreCommandPhaseSourceBuildError(
                "Command-phase rule/evidence link drifted from its reviewed semantic identity."
            )
        mirror = evidence_by_id[mirror_evidence_id]
        _require_reviewed_fields(
            mirror,
            expected_fields=(
                ("rule_source_id", expected_source_id),
                ("evidence_kind", "third_party_mirror"),
                ("authority", "project_authoritative_app_mirror"),
                (
                    "project_authority_policy_id",
                    _REVIEWED_PROJECT_AUTHORITY_POLICY_ID,
                ),
                ("review_audit_id", _REVIEWED_SEARCH_INDEX_OBSERVATION_ID),
                ("review_audit_row_id", _REVIEWED_SEARCH_INDEX_OBSERVATION_ROW_ID),
                (
                    "review_audit_source_observation_sha256",
                    _REVIEWED_SEARCH_INDEX_SOURCE_OBSERVATION_SHA256,
                ),
                ("provider_name", "40k.app"),
                ("source_platform", "Web"),
                ("source_url", _REVIEWED_SEARCH_INDEX_URL),
                ("observed_at", _REVIEWED_SEARCH_INDEX_OBSERVED_AT),
                ("verification_status", "authoritative_app_mirror"),
                ("provider_non_affiliation_recorded", True),
            ),
            context="search-index evidence link",
        )


def _derived_payload(payload: dict[str, object]) -> dict[str, object]:
    derived = copy.deepcopy(payload)
    search_index_observation = _validate_reviewed_source_observation_identity(derived)
    heading_values = _required_list(
        search_index_observation["headings"],
        field_name="search_index_observation.headings",
    )
    headings = [
        _required_dict(value, field_name="search-index heading") for value in heading_values
    ]
    normalized_headings: list[str] = []
    for heading in headings:
        normalized_heading = _required_text(
            heading["normalized_heading"],
            field_name="normalized_heading",
        )
        normalized_headings.append(normalized_heading)
        heading["transcription_sha256"] = hashlib.sha256(normalized_heading.encode()).hexdigest()
    normalized_observed_text = "\n".join(normalized_headings)
    search_index_observation["normalized_observed_text"] = normalized_observed_text
    search_index_observation["sequence_transcription_sha256"] = hashlib.sha256(
        normalized_observed_text.encode()
    ).hexdigest()
    search_index_observation["source_observation_sha256"] = _search_index_source_observation_sha256(
        search_index_observation
    )

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
    _validate_reviewed_rule_evidence_links(rules=rules, evidence_by_id=evidence_by_id)
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
            if evidence["evidence_kind"] == "third_party_mirror":
                evidence["review_audit_id"] = search_index_observation["observation_id"]
                evidence["review_audit_row_id"] = search_index_observation["observation_row_id"]
                evidence["review_audit_source_observation_sha256"] = search_index_observation[
                    "source_observation_sha256"
                ]
                evidence["source_url"] = search_index_observation["source_url"]
                evidence["observed_at"] = search_index_observation["observed_at"]
            observation_sha256 = _evidence_observation_sha256(evidence)
            evidence["observation_sha256"] = observation_sha256
            if evidence["evidence_kind"] == "third_party_mirror":
                mirror_observation_sha256 = observation_sha256
        if mirror_observation_sha256 is None:
            raise CoreCommandPhaseSourceBuildError(
                "Each Command-phase rule requires a search-index mirror observation."
            )
        rule["source_observation_sha256"] = mirror_observation_sha256

    derived["package_hash"] = ""
    derived["package_hash"] = _sha256_payload(derived)
    return derived


def build_core_command_phase_source_payload(
    payload: dict[str, object],
) -> dict[str, object]:
    return _derived_payload(payload)


def _canonical_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the reviewed Command-phase source artifact."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail instead of writing when the committed artifact is stale.",
    )
    args = parser.parse_args()

    raw = ARTIFACT_PATH.read_bytes()
    payload = _required_dict(json.loads(raw), field_name="artifact")
    expected = _canonical_bytes(build_core_command_phase_source_payload(payload))
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
