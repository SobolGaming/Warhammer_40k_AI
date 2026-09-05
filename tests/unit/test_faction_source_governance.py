from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from warhammer40k_core.rules.faction_source_governance import (
    FACTION_SOURCE_POLICY_ID,
    FactionSourceError,
    faction_source_audit,
    load_faction_source_audit_bytes,
    observation_fingerprint,
    validate_faction_source_audit_bytes,
)
from warhammer40k_core.rules.faction_source_package import faction_source_package
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.source_evidence import (
    RuleEvidenceError,
    RuleEvidenceRecord,
    SourceEvidenceCatalog,
)

AUDIT_PATH = Path("data/source_audits/maintained_app_mirrors/factions_2026_09_05.audit.json")


def _payload() -> dict[str, object]:
    return cast(dict[str, object], json.loads(AUDIT_PATH.read_bytes()))


def _rows(payload: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], payload["observations"])


def _bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode()


def _rehash(row: dict[str, object]) -> None:
    row["transcription_sha256"] = hashlib.sha256(str(row["operative_text"]).encode()).hexdigest()
    row["capture_sha256"] = hashlib.sha256(str(row["captured_text"]).encode()).hexdigest()
    row["source_observation_sha256"] = observation_fingerprint(row)


def test_f00_complete_observations_load_through_shared_source_package() -> None:
    audit = faction_source_audit()
    package = faction_source_package()
    assert audit.app_version == "946"
    assert {row.content_kind for row in audit.observations} == {
        "faction",
        "detachment",
        "datasheet",
    }
    assert package.source_authority_scope == "warhammer_40000_11th_factions"
    assert len(package.evidence_required_source_ids) == 3
    for row in audit.observations:
        text = package.source_catalog.source_text_by_id(row.source_id)
        assert text.raw_text == row.operative_text
        assert text.objective_scope is ObjectiveRuleScope.NON_CORE_RULES
        assert row.operative_text in row.captured_text
        assert hashlib.sha256(row.captured_text.encode()).hexdigest() == row.capture_sha256
        records = package.source_evidence_catalog.records_for_source_id(row.source_id)
        assert len(records) == 2
        assert {record.authority for record in records} == {
            "unverified_transcription_only",
            "project_authoritative_app_mirror",
        }
        for record in records:
            assert RuleEvidenceRecord.from_payload(record.to_payload()) == record
            assert record.load_support_status == "loaded"
            assert record.semantic_execution_status == "not_certified"
            assert not record.runtime_consumer_ids
        mirror = next(record for record in records if record.evidence_kind == "third_party_mirror")
        assert mirror.project_authority_policy_id == FACTION_SOURCE_POLICY_ID
        assert mirror.provider_non_affiliation_recorded
        assert mirror.app_version == row.app_version == audit.app_version
        assert mirror.observed_at == row.observed_at
    army, detachment, datasheet = audit.observations
    assert "At the start of each turn." in army.operative_text
    assert "Chorus of Repudiation" in detachment.operative_text
    assert "2nd+ in your army\n+40 pts" in datasheet.operative_text
    assert "DAMAGED: 1-4 WOUNDS REMAINING" in datasheet.operative_text
    assert datasheet.geometry[0].base_statement == "Hull"
    assert datasheet.geometry[0].height_status == "not_observed"
    assert not datasheet.geometry[0].fieldability_certified


@pytest.mark.parametrize("field", ["operative_text", "captured_text", "observed_at", "source_id"])
def test_f00_observation_hash_covers_text_and_identity(field: str) -> None:
    payload = _payload()
    row = _rows(payload)[0]
    row[field] = str(row[field]) + " drift"
    with pytest.raises(FactionSourceError):
        validate_faction_source_audit_bytes(_bytes(payload))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_name", "Games Workshop"),
        ("provider_name", "39k PRO"),
        ("provider_non_affiliation_recorded", False),
        ("app_version", "931"),
        ("content_kind", "core_rules"),
        ("scope_classification", "legends"),
        ("scope_classification", "forge_world"),
        ("scope_classification", "crusade"),
        ("scope_classification", "boarding_actions"),
        ("scope_classification", "kill_team"),
        ("identity_status", "unresolved"),
        ("identity_status", "conflict"),
        ("completeness", "excerpt"),
        ("owning_faction_source_id", "faction-app:chaos-daemons"),
        ("objective_scope", "core_rules"),
        ("source_url", "https://www.40k.app/factions/orks/units/warbuggies"),
        ("source_url", "https://www.40k.app/factions/titan-legions/army-rules"),
        ("source_url", "http://www.40k.app/factions/adepta-sororitas/army-rules"),
        ("source_url", "https://www.40k.app.evil.test/factions/adepta-sororitas/army-rules"),
        ("source_url", "https://www.40k.app/factions/adepta-sororitas/army-rules?version=946"),
        ("source_url", "https://www.40k.app/factions/adepta-sororitas/army-rules#rules"),
        ("source_url", "https://www.40k.app:443/factions/adepta-sororitas/army-rules"),
        ("source_url", "https://user@www.40k.app/factions/adepta-sororitas/army-rules"),
        ("source_url", "https://www.40k.app/factions/adepta-sororitas/../orks/army-rules"),
    ],
)
def test_f00_rejects_rehashed_scope_identity_and_provenance_drift(
    field: str, value: object
) -> None:
    payload = _payload()
    row = _rows(payload)[0]
    row[field] = value
    _rehash(row)
    with pytest.raises(FactionSourceError):
        validate_faction_source_audit_bytes(_bytes(payload))


def test_f00_rejects_missing_duplicate_and_truncated_observations() -> None:
    for mutation in ("missing", "duplicate", "truncated"):
        payload = _payload()
        rows = _rows(payload)
        if mutation == "missing":
            rows.pop()
        elif mutation == "duplicate":
            rows.append(copy.deepcopy(rows[0]))
        else:
            rows[0]["operative_text"] = "At the start of each turn."
            _rehash(rows[0])
        with pytest.raises(FactionSourceError):
            validate_faction_source_audit_bytes(_bytes(payload))


def test_f00_rejects_same_version_divergence_before_authorization() -> None:
    payload = _payload()
    divergent = copy.deepcopy(_rows(payload)[0])
    divergent["observation_id"] = "divergent-observation"
    divergent["operative_text"] = str(divergent["operative_text"]).replace(
        "each turn", "each battle round"
    )
    divergent["captured_text"] = str(divergent["captured_text"]).replace(
        "each turn", "each battle round"
    )
    _rehash(divergent)
    _rows(payload).append(divergent)
    with pytest.raises(FactionSourceError, match="disagree"):
        validate_faction_source_audit_bytes(_bytes(payload))


@pytest.mark.parametrize(
    "mutation", ["geometry_missing", "height_invented", "fieldable", "unknown_field"]
)
def test_f00_geometry_authority_does_not_invent_missing_dimensions(mutation: str) -> None:
    payload = _payload()
    row = _rows(payload)[2]
    geometry = cast(list[dict[str, object]], row["geometry"])
    if mutation == "geometry_missing":
        geometry.clear()
    elif mutation == "height_invented":
        geometry[0]["height_status"] = "accepted"
    elif mutation == "fieldable":
        geometry[0]["fieldability_certified"] = True
    else:
        geometry[0]["height_inches"] = 0
    _rehash(row)
    with pytest.raises(FactionSourceError):
        validate_faction_source_audit_bytes(_bytes(payload))


def test_f00_raw_artifact_is_pinned_and_schema_is_fail_closed() -> None:
    raw = AUDIT_PATH.read_bytes()
    assert load_faction_source_audit_bytes(raw) == faction_source_audit()
    with pytest.raises(FactionSourceError, match="pin"):
        load_faction_source_audit_bytes(raw + b"\n")
    for raw_invalid in (b"{", b"null", b"{}", b'{"audit_schema":12}'):
        with pytest.raises(FactionSourceError):
            validate_faction_source_audit_bytes(raw_invalid)


@pytest.mark.parametrize(
    "field", ["transcription_sha256", "rule_source_id", "observed_at", "source_title"]
)
def test_f00_shared_evidence_rejects_reused_audit_for_different_observation(field: str) -> None:
    mirror = next(
        record
        for record in faction_source_package().source_evidence_catalog.records
        if record.evidence_kind == "third_party_mirror"
    )
    payload = cast(dict[str, object], mirror.to_payload())
    payload[field] = "0" * 64 if field == "transcription_sha256" else "unregistered"
    if field == "observed_at":
        payload[field] = "2026-09-05T00:00:00+00:00"
    hashed = dict(payload)
    hashed.update(
        observation_sha256="",
        load_support_status="not_loaded",
        semantic_execution_status="not_certified",
        runtime_consumer_ids=[],
    )
    payload["observation_sha256"] = hashlib.sha256(
        json.dumps(hashed, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with pytest.raises(RuleEvidenceError):
        RuleEvidenceRecord.from_payload(payload)


@pytest.mark.parametrize(
    "mutation", ["extra_source", "wrong_normalization", "no_mirror", "core_scope"]
)
def test_f00_package_cannot_bypass_reviewed_source_inventory(mutation: str) -> None:
    package = faction_source_package()
    catalog = package.source_catalog
    document = catalog.documents[0]
    source = document.source_texts[0]
    evidence = package.source_evidence_catalog
    scope = package.source_authority_scope
    if mutation == "extra_source":
        extra = replace(source, source_id="faction-app:unreviewed:army-rules")
        catalog = replace(
            catalog,
            documents=(
                replace(document, source_texts=(*document.source_texts, extra)),
                *catalog.documents[1:],
            ),
        )
    elif mutation == "wrong_normalization":
        wrong_scope = replace(source, objective_scope=ObjectiveRuleScope.CORE_RULES)
        catalog = replace(
            catalog,
            documents=(replace(document, source_texts=(wrong_scope,)), *catalog.documents[1:]),
        )
    elif mutation == "no_mirror":
        evidence = SourceEvidenceCatalog(
            records=tuple(
                record
                for record in package.source_evidence_catalog.records
                if record.evidence_kind != "third_party_mirror"
            )
        )
    else:
        scope = "warhammer_40000_11th_core_rules"
    with pytest.raises(RuleEvidenceError):
        replace(
            package,
            source_catalog=catalog,
            source_evidence_catalog=evidence,
            source_authority_scope=scope,
        )


@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("root", "policy_id", "core-only-policy"),
        ("root", "app_version", "latest"),
        ("root", "selected_source_ids", []),
        ("root", "locale", "pl"),
        ("version_evidence", "source_url", "https://example.org"),
        ("version_evidence", "statement", "Version 931\nReleased 2026-08-26."),
        ("version_evidence", "observed_at", "2026-09-05"),
        ("official", "source_url", "https://www.40k.app/source.pdf"),
        ("official", "artifact_path", "../../outside.pdf"),
        ("official", "sha256", "unknown"),
        ("observation", "official_source_ids", ["unretained-primary"]),
        ("observation", "observed_at", "invalid-timestamp"),
        ("observation", "source_title", ""),
        ("observation", "source_url", "https://www.40k.app/factions/adepta-sororitas/units"),
    ],
)
def test_f00_review_candidate_rejects_incomplete_selected_version_and_provenance(
    target: str, field: str, value: object
) -> None:
    payload = _payload()
    if target == "root":
        row = payload
    elif target == "official":
        row = cast(list[dict[str, object]], payload["official_sources"])[0]
    elif target == "observation":
        row = _rows(payload)[0]
    else:
        row = cast(dict[str, object], payload[target])
    row[field] = value
    if target == "observation":
        _rehash(row)
    if field == "statement":
        row["transcription_sha256"] = hashlib.sha256(str(value).encode()).hexdigest()
    with pytest.raises(FactionSourceError):
        validate_faction_source_audit_bytes(_bytes(payload))


def test_f00_rehashing_an_entire_truncated_capture_does_not_grant_authority() -> None:
    payload = _payload()
    row = _rows(payload)[0]
    row["captured_text"] = row["operative_text"] = row["operative_start"]
    _rehash(row)
    # A candidate's claimed completeness cannot prove what the provider displayed.
    # Only review plus the immutable pin authorizes the whole retained observation.
    validate_faction_source_audit_bytes(_bytes(payload))
    with pytest.raises(FactionSourceError, match="pin"):
        load_faction_source_audit_bytes(_bytes(payload))


def test_f00_unknown_base_remains_an_explicit_unresolved_candidate() -> None:
    payload = _payload()
    row = _rows(payload)[2]
    geometry = cast(list[dict[str, object]], row["geometry"])[0]
    geometry["base_statement"] = None
    geometry["base_status"] = "not_observed"
    _rehash(row)
    candidate = validate_faction_source_audit_bytes(_bytes(payload))
    assert candidate.observations[2].geometry[0].base_statement is None
    assert not candidate.observations[2].geometry[0].fieldability_certified
    with pytest.raises(FactionSourceError, match="pin"):
        load_faction_source_audit_bytes(_bytes(payload))
