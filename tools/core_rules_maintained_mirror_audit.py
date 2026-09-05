from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from warhammer40k_core.rules.source_authority_registry import (
    CORE_RULES_MAINTAINED_MIRROR_POLICY_ID,
    CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    source_authority_registry,
)

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = (
    ROOT / "data" / "source_audits" / "maintained_app_mirrors" / "core_rules_2026_09_02.audit.json"
)
REPORT_PATH = ROOT / "docs" / "CORE_RULES_MAINTAINED_MIRROR_REVIEW.md"
EXPECTED_SCHEMA = "core-v2-maintained-app-mirror-review-v1"
EXPECTED_AUDIT_ID = "core-rules-maintained-app-mirrors-2026-09-02"
EXPECTED_REVIEWED_AT = "2026-09-02T12:30:09-04:00"
EXPECTED_PROVIDERS = (
    (
        "40k-app",
        "40k.app",
        "https://www.40k.app/rules",
    ),
    (
        "game-datamissions",
        "Game Datamissions",
        "https://game-datamissions.com/11th/rules/changelog",
    ),
)
EXPECTED_OBSERVATIONS = (
    (
        "40k-app-core-rules-observed-2026-08-25",
        "40k-app",
        "https://www.40k.app/rules",
        None,
        "2026-08-25T00:00:00-04:00",
    ),
    (
        "game-datamissions-core-rules-data-931",
        "game-datamissions",
        "https://game-datamissions.com/11th/rules/changelog",
        "931",
        "2026-09-02T12:30:09-04:00",
    ),
    (
        "game-datamissions-core-rules-data-946",
        "game-datamissions",
        "https://game-datamissions.com/11th/rules/changelog",
        "946",
        "2026-09-02T12:30:09-04:00",
    ),
)


@dataclass(frozen=True, slots=True)
class MaintainedMirrorProviderReview:
    provider_id: str
    provider_name: str
    provider_root_url: str
    authority_status: str
    affiliation: str
    runtime_input: bool
    owned_by_games_workshop: bool


@dataclass(frozen=True, slots=True)
class MaintainedMirrorObservationReview:
    observation_id: str
    provider_id: str
    source_url: str
    app_version: str | None
    observed_at: str | None
    reviewed_statement: str
    transcription_sha256: str
    source_observation_sha256: str
    review_record_sha256: str


@dataclass(frozen=True, slots=True)
class CoreRulesMaintainedMirrorAudit:
    audit_id: str
    reviewed_at: str
    edition: str
    review_scope: str
    excluded_scopes: tuple[str, ...]
    project_authority_policy_id: str
    providers: tuple[MaintainedMirrorProviderReview, ...]
    observations: tuple[MaintainedMirrorObservationReview, ...]
    comparison_identity_fields: tuple[str, ...]
    mismatch_disposition: str


def core_rules_maintained_mirror_audit() -> CoreRulesMaintainedMirrorAudit:
    return load_core_rules_maintained_mirror_audit(AUDIT_PATH)


def load_core_rules_maintained_mirror_audit(path: Path) -> CoreRulesMaintainedMirrorAudit:
    payload = json.loads(path.read_text(encoding="utf-8"))
    root = _exact_dict(
        payload,
        {
            "audit_schema",
            "audit_id",
            "reviewed_at",
            "scope",
            "project_authority_policy_id",
            "providers",
            "observations",
            "comparison_policy",
        },
        context="root",
    )
    if _text(root, "audit_schema") != EXPECTED_SCHEMA:
        raise ValueError("Maintained App-mirror audit schema is unsupported.")
    scope = _exact_dict(
        root.get("scope"),
        {"edition", "review_scope", "excluded_scopes"},
        context="scope",
    )
    comparison_policy = _exact_dict(
        root.get("comparison_policy"),
        {"identity_fields", "mismatch_disposition"},
        context="comparison policy",
    )
    audit = CoreRulesMaintainedMirrorAudit(
        audit_id=_text(root, "audit_id"),
        reviewed_at=_timestamp(root, "reviewed_at"),
        edition=_text(scope, "edition"),
        review_scope=_text(scope, "review_scope"),
        excluded_scopes=_text_tuple(scope, "excluded_scopes"),
        project_authority_policy_id=_text(root, "project_authority_policy_id"),
        providers=tuple(
            _provider_review(row) for row in _object_rows(root, "providers", context="providers")
        ),
        observations=tuple(
            _observation_review(row)
            for row in _object_rows(root, "observations", context="observations")
        ),
        comparison_identity_fields=_text_tuple(comparison_policy, "identity_fields"),
        mismatch_disposition=_text(comparison_policy, "mismatch_disposition"),
    )
    _validate_audit(audit)
    return audit


def core_rules_maintained_mirror_markdown(
    audit: CoreRulesMaintainedMirrorAudit | None = None,
) -> str:
    reviewed = core_rules_maintained_mirror_audit() if audit is None else audit
    lines = [
        "# Core Rules Maintained App-data Mirror Review",
        "",
        "This report is generated from the checked-in offline governance audit. It records the "
        "two non-affiliated providers that repository-owner policy accepts as maintained direct "
        "Warhammer App-data mirrors for Warhammer 40,000 11th Edition Core Rules. Neither "
        "provider is presented as owned by, affiliated with, or endorsed by Games Workshop.",
        "",
        f"Policy: `{reviewed.project_authority_policy_id}`.",
        "",
        "## Provider registry",
        "",
        "| Provider | Reviewed URL | Authority | Runtime input |",
        "|---|---|---|---|",
    ]
    lines.extend(
        f"| {provider.provider_name} | [{provider.provider_id}]({provider.provider_root_url}) | "
        f"{provider.authority_status} | {'yes' if provider.runtime_input else 'no'} |"
        for provider in reviewed.providers
    )
    lines.extend(
        (
            "",
            "## Retained governance observations",
            "",
            "These provider-level records establish the governance boundary only. They do not "
            "substitute for the exact operative rule transcription and source-observation "
            "fingerprint required in each implementation PR.",
            "",
            "| Observation | Provider | App-data version or timestamp | Transcription SHA-256 | "
            "Observation fingerprint |",
            "|---|---|---|---|---|",
        )
    )
    provider_names = {row.provider_id: row.provider_name for row in reviewed.providers}
    for observation in reviewed.observations:
        version = (
            f"App-data {observation.app_version}"
            if observation.app_version is not None
            else cast(str, observation.observed_at)
        )
        lines.append(
            f"| `{observation.observation_id}` | {provider_names[observation.provider_id]} | "
            f"{version} | `{observation.transcription_sha256}` | "
            f"`{observation.source_observation_sha256}` |"
        )
    lines.extend(
        (
            "",
            "## Fail-closed comparison rule",
            "",
            "Source-package validation groups project-authoritative mirror records by stable "
            "rule source ID and App-data version. When two named providers are present for the "
            "same group, their transcription hashes must match. A mismatch is rejected and "
            "requires an official-App comparison before certification; it is never resolved by "
            "provider preference or silent fallback.",
            "",
            "The live provider sites are not runtime inputs. Engine loaders consume only reviewed, "
            "normalized, hash-pinned source artifacts.",
            "",
            "Runtime mirror records authenticate their audit ID, audit row ID, retained "
            "fingerprint, provider, URL, and version or timestamp against the hash-pinned "
            "packaged source-authority registry. Rule source packages also carry its typed "
            "Core-Rules-only scope. The superseded 40k.app policy is accepted only for the "
            "registry's exact immutable legacy-observation inventory.",
            "",
        )
    )
    return "\n".join(lines)


def main(argv: tuple[str, ...] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and render the maintained App-data mirror governance audit."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--update-hashes", action="store_true")
    args = parser.parse_args(argv)
    if args.update_hashes:
        _write_refreshed_hashes()
    rendered = core_rules_maintained_mirror_markdown()
    if args.check:
        if not REPORT_PATH.is_file() or REPORT_PATH.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Maintained App-mirror review report is stale.")
        return 0
    REPORT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


def _provider_review(payload: dict[str, object]) -> MaintainedMirrorProviderReview:
    row = _exact_dict(
        payload,
        {
            "provider_id",
            "provider_name",
            "provider_root_url",
            "authority_status",
            "affiliation",
            "runtime_input",
            "owned_by_games_workshop",
        },
        context="provider",
    )
    return MaintainedMirrorProviderReview(
        provider_id=_text(row, "provider_id"),
        provider_name=_text(row, "provider_name"),
        provider_root_url=_https_url(row, "provider_root_url"),
        authority_status=_text(row, "authority_status"),
        affiliation=_text(row, "affiliation"),
        runtime_input=_boolean(row, "runtime_input"),
        owned_by_games_workshop=_boolean(row, "owned_by_games_workshop"),
    )


def _observation_review(payload: dict[str, object]) -> MaintainedMirrorObservationReview:
    row = _exact_dict(
        payload,
        {
            "observation_id",
            "provider_id",
            "source_url",
            "app_version",
            "observed_at",
            "reviewed_statement",
            "transcription_sha256",
            "source_observation_sha256",
            "review_record_sha256",
        },
        context="observation",
    )
    observation = MaintainedMirrorObservationReview(
        observation_id=_text(row, "observation_id"),
        provider_id=_text(row, "provider_id"),
        source_url=_https_url(row, "source_url"),
        app_version=_optional_text(row, "app_version"),
        observed_at=_optional_timestamp(row, "observed_at"),
        reviewed_statement=_text(row, "reviewed_statement"),
        transcription_sha256=_sha256(row, "transcription_sha256"),
        source_observation_sha256=_sha256(row, "source_observation_sha256"),
        review_record_sha256=_sha256(row, "review_record_sha256"),
    )
    if observation.app_version is None and observation.observed_at is None:
        raise ValueError(
            "Maintained App-mirror observation requires an App-data version or timestamp."
        )
    if (
        hashlib.sha256(observation.reviewed_statement.encode()).hexdigest()
        != observation.transcription_sha256
    ):
        raise ValueError("Maintained App-mirror transcription hash drifted.")
    if observation.source_observation_sha256 != _source_observation_hash(row):
        raise ValueError("Maintained App-mirror source-observation fingerprint drifted.")
    if observation.review_record_sha256 != _review_record_hash(row):
        raise ValueError("Maintained App-mirror review-record hash drifted.")
    return observation


def _validate_audit(audit: CoreRulesMaintainedMirrorAudit) -> None:
    if audit.audit_id != EXPECTED_AUDIT_ID or audit.reviewed_at != EXPECTED_REVIEWED_AT:
        raise ValueError("Maintained App-mirror audit identity drifted.")
    if (
        audit.edition != "warhammer_40000_11th"
        or audit.review_scope != "core_rules_only"
        or audit.excluded_scopes != ("factions", "faction_detachments", "faction_datasheets")
        or audit.project_authority_policy_id != CORE_RULES_MAINTAINED_MIRROR_POLICY_ID
    ):
        raise ValueError("Maintained App-mirror scope or policy drifted.")
    observed_providers = tuple(
        (provider.provider_id, provider.provider_name, provider.provider_root_url)
        for provider in audit.providers
    )
    if observed_providers != EXPECTED_PROVIDERS:
        raise ValueError("Maintained App-mirror provider registry drifted.")
    if any(
        provider.authority_status != "project_authoritative_maintained_direct_app_data_mirror"
        or provider.affiliation != "not_affiliated_with_or_endorsed_by_games_workshop"
        or provider.runtime_input
        or provider.owned_by_games_workshop
        for provider in audit.providers
    ):
        raise ValueError("Maintained App-mirror provider authority boundary drifted.")
    provider_ids = {provider.provider_id for provider in audit.providers}
    observed_observations = tuple(
        (
            row.observation_id,
            row.provider_id,
            row.source_url,
            row.app_version,
            row.observed_at,
        )
        for row in audit.observations
    )
    if observed_observations != EXPECTED_OBSERVATIONS:
        raise ValueError("Maintained App-mirror observation inventory drifted.")
    if {row.provider_id for row in audit.observations} != provider_ids:
        raise ValueError("Every maintained App-mirror provider requires retained review evidence.")
    if (
        audit.comparison_identity_fields != ("rule_source_id", "app_version")
        or audit.mismatch_disposition != "official_app_comparison_required"
    ):
        raise ValueError("Maintained App-mirror comparison policy drifted.")
    registry_scope = source_authority_registry().scope(CORE_RULES_SOURCE_AUTHORITY_SCOPE)
    provider_names = {provider.provider_id: provider.provider_name for provider in audit.providers}
    registered_rows = tuple(
        sorted(
            (
                row.audit_id,
                row.row_id,
                row.source_observation_sha256,
                row.provider_name,
                row.source_url,
                row.policy_id,
                row.identity_kind,
                row.identity_value,
            )
            for row in registry_scope.audit_rows
            if row.policy_id == CORE_RULES_MAINTAINED_MIRROR_POLICY_ID
            and row.audit_id == audit.audit_id
        )
    )
    audited_rows = tuple(
        sorted(
            (
                audit.audit_id,
                row.observation_id,
                row.source_observation_sha256,
                provider_names[row.provider_id],
                row.source_url,
                audit.project_authority_policy_id,
                "app_version" if row.app_version is not None else "observed_at",
                row.app_version if row.app_version is not None else row.observed_at,
            )
            for row in audit.observations
        )
    )
    if registered_rows != audited_rows:
        raise ValueError("Maintained App-mirror authority registry drifted from its audit rows.")


def _write_refreshed_hashes() -> None:
    payload = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    root = _exact_dict(
        payload,
        {
            "audit_schema",
            "audit_id",
            "reviewed_at",
            "scope",
            "project_authority_policy_id",
            "providers",
            "observations",
            "comparison_policy",
        },
        context="root",
    )
    for row in _object_rows(root, "observations", context="observations"):
        statement = _text(row, "reviewed_statement")
        row["transcription_sha256"] = hashlib.sha256(statement.encode()).hexdigest()
        row["source_observation_sha256"] = _source_observation_hash(row)
        row["review_record_sha256"] = _review_record_hash(row)
    AUDIT_PATH.write_text(
        json.dumps(root, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _source_observation_hash(payload: dict[str, object]) -> str:
    source_payload = {
        key: payload[key]
        for key in (
            "observation_id",
            "provider_id",
            "source_url",
            "app_version",
            "observed_at",
            "reviewed_statement",
            "transcription_sha256",
        )
    }
    return _payload_sha256(source_payload)


def _review_record_hash(payload: dict[str, object]) -> str:
    hashed_payload = dict(payload)
    hashed_payload["review_record_sha256"] = ""
    return _payload_sha256(hashed_payload)


def _payload_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _exact_dict(value: object, fields: set[str], *, context: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError(f"Maintained App-mirror audit {context} must be an object.")
    row = cast(dict[str, object], value)
    if set(row) != fields:
        raise ValueError(f"Maintained App-mirror audit {context} fields drifted.")
    return row


def _object_rows(
    payload: dict[str, object], key: str, *, context: str
) -> tuple[dict[str, object], ...]:
    value = payload.get(key)
    if type(value) is not list:
        raise ValueError(f"Maintained App-mirror audit {context} must be an object list.")
    rows = cast(list[object], value)
    if not rows or any(type(row) is not dict for row in rows):
        raise ValueError(f"Maintained App-mirror audit {context} must be a non-empty object list.")
    return tuple(cast(dict[str, object], row) for row in rows)


def _text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"Maintained App-mirror audit {key} must be non-empty stripped text.")
    return value


def _optional_text(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    return _text(payload, key)


def _text_tuple(payload: dict[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if type(value) is not list:
        raise ValueError(f"Maintained App-mirror audit {key} must be a text list.")
    values = tuple(_text({key: item}, key) for item in cast(list[object], value))
    if not values or len(values) != len(set(values)):
        raise ValueError(f"Maintained App-mirror audit {key} must be non-empty and unique.")
    return values


def _boolean(payload: dict[str, object], key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise ValueError(f"Maintained App-mirror audit {key} must be a boolean.")
    return value


def _sha256(payload: dict[str, object], key: str) -> str:
    value = _text(payload, key)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"Maintained App-mirror audit {key} must be lowercase SHA-256.")
    return value


def _https_url(payload: dict[str, object], key: str) -> str:
    value = _text(payload, key)
    split = urlsplit(value)
    if (
        any(ord(character) < 32 or ord(character) == 127 for character in value)
        or split.scheme != "https"
        or split.hostname not in {"www.40k.app", "game-datamissions.com"}
        or split.username is not None
        or split.password is not None
        or split.port is not None
        or split.query
        or split.fragment
    ):
        raise ValueError("Maintained App-mirror audit URL is not an approved canonical HTTPS URL.")
    return value


def _timestamp(payload: dict[str, object], key: str) -> str:
    value = _text(payload, key)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Maintained App-mirror audit timestamp must be ISO-8601.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Maintained App-mirror audit timestamp must include a UTC offset.")
    return value


def _optional_timestamp(payload: dict[str, object], key: str) -> str | None:
    if payload.get(key) is None:
        return None
    return _timestamp(payload, key)


if __name__ == "__main__":
    raise SystemExit(main())
