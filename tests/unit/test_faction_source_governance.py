from __future__ import annotations

import copy
import hashlib
import json
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import cast

if sys.platform == "win32":
    import _winapi

import pytest
from tools import build_faction_source_governance as governance_builder

from warhammer40k_core.core.ruleset import RulesetId
from warhammer40k_core.rules.data_package import CatalogVersion, RulesetBundle
from warhammer40k_core.rules.faction_source_governance import (
    FACTION_SOURCE_POLICY_ID,
    FactionSourceError,
    faction_source_audit,
    load_faction_source_audit_bytes,
    observation_fingerprint,
    validate_faction_source_audit_bytes,
)
from warhammer40k_core.rules.faction_source_package import (
    faction_source_catalog,
    faction_source_package,
)
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.source_authority_registry import (
    SourceAuthorityRegistryError,
    SourcePackageAuthorization,
    source_authority_registry,
)
from warhammer40k_core.rules.source_catalog import SourceCatalog, SourceCatalogError
from warhammer40k_core.rules.source_data import RuleSourceText
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


@pytest.mark.parametrize("document_id", ["aaa-duplicate", "zzz-duplicate"])
@pytest.mark.parametrize("alter_text", [False, True])
def test_source_catalog_rejects_duplicate_source_ids_across_documents(
    document_id: str, alter_text: bool
) -> None:
    catalog = faction_source_package().source_catalog
    document = catalog.documents[0]
    source = document.source_texts[0]
    duplicate = replace(
        document,
        document_id=replace(document.document_id, document_id=document_id),
        source_texts=(
            RuleSourceText.from_raw(
                source_id=source.source_id,
                raw_text="Unreviewed duplicate text." if alter_text else source.raw_text,
                objective_scope=source.objective_scope,
            ),
        ),
    )
    with pytest.raises(SourceCatalogError, match="duplicate source IDs"):
        replace(catalog, documents=(*catalog.documents, duplicate))


@pytest.mark.parametrize(
    "mutation", ["catalog_version", "source_date", "document_id", "document_title", "bundle"]
)
def test_f00_rejects_catalog_identity_drift_with_unchanged_package_and_text(mutation: str) -> None:
    package = faction_source_package()
    catalog = package.source_catalog
    document = catalog.documents[0]
    if mutation == "catalog_version":
        catalog = replace(
            catalog, catalog_version=replace(catalog.catalog_version, version_id="drift")
        )
    elif mutation == "source_date":
        catalog = replace(
            catalog,
            catalog_version=CatalogVersion.dated(
                version_id=catalog.catalog_version.version_id, source_date=date(2026, 9, 6)
            ),
        )
    elif mutation == "bundle":
        catalog = replace(
            catalog,
            ruleset_bundles=(
                RulesetBundle(
                    bundle_id="unreviewed-bundle",
                    ruleset_id=RulesetId.warhammer_40000_eleventh(version="f00-test"),
                    package_id=catalog.package_id,
                    catalog_version=catalog.catalog_version,
                    source_document_ids=(document.document_id,),
                ),
            ),
        )
    else:
        document = (
            replace(document, title="Unreviewed title")
            if mutation == "document_title"
            else replace(
                document,
                document_id=replace(document.document_id, document_id="unreviewed-document"),
            )
        )
        catalog = replace(catalog, documents=(document, *catalog.documents[1:]))
    with pytest.raises(RuleEvidenceError, match="catalog"):
        replace(package, source_catalog=catalog)


@pytest.mark.parametrize(
    "relative_path",
    [
        "../../../../tmp/probe.pdf",
        "./probe.pdf",
        "one/../probe.pdf",
        "one//probe.pdf",
        "one\\probe.pdf",
        "C:/probe.pdf",
        "probe\x00.pdf",
        "probe\n.pdf",
        "probe\x7f.pdf",
        "%2e%2e/probe.pdf",
        "one%2f..%2fprobe.pdf",
    ],
)
def test_f00_rejects_paired_official_url_and_artifact_path_escape(relative_path: str) -> None:
    payload = _payload()
    official = cast(list[dict[str, object]], payload["official_sources"])[0]
    official["source_url"] = f"https://assets.warhammer-community.com/{relative_path}"
    official["artifact_path"] = f"data/raw/faction_packs/{relative_path}"
    with pytest.raises(FactionSourceError):
        validate_faction_source_audit_bytes(_bytes(payload))


def test_f00_official_artifact_rejects_symlink_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _payload()
    official = cast(list[dict[str, object]], payload["official_sources"])[0]
    filename = Path(str(official["artifact_path"])).name
    official["source_url"] = f"https://assets.warhammer-community.com/linked/{filename}"
    official["artifact_path"] = f"data/raw/faction_packs/linked/{filename}"
    outside = tmp_path / "outside" / filename
    outside.parent.mkdir()
    outside.write_bytes(b"outside artifact root")
    official["sha256"] = hashlib.sha256(outside.read_bytes()).hexdigest()
    candidate = validate_faction_source_audit_bytes(_bytes(payload))
    artifact = tmp_path / candidate.official_sources[0].artifact_path
    artifact.parent.parent.mkdir(parents=True)
    if sys.platform == "win32":
        # Junctions exercise real resolved containment without symlink privileges.
        _winapi.CreateJunction(str(outside.parent), str(artifact.parent))
    else:
        artifact.parent.symlink_to(outside.parent, target_is_directory=True)
    monkeypatch.setattr(governance_builder, "ROOT", tmp_path)
    with pytest.raises(FactionSourceError, match="inside root"):
        governance_builder.validate_official_artifacts(candidate)


@pytest.mark.parametrize("latest_observation", ["version_evidence", "page"])
def test_f00_future_audit_cannot_reuse_previous_package_authorization(
    latest_observation: str,
) -> None:
    payload = _payload()
    payload["app_version"] = "947"
    version = cast(dict[str, object], payload["version_evidence"])
    version["statement"] = "Version 947\nReleased 2026-09-06."
    version["transcription_sha256"] = hashlib.sha256(str(version["statement"]).encode()).hexdigest()
    version["observed_at"] = "2026-09-06T00:00:00+00:00"
    for row in _rows(payload):
        row["app_version"] = "947"
        row["observed_at"] = "2026-09-06T00:00:00+00:00"
    latest = version if latest_observation == "version_evidence" else _rows(payload)[0]
    # The completion date is determined in UTC, including the version observation.
    latest["observed_at"] = "2026-09-06T23:30:00-02:00"
    for row in _rows(payload):
        _rehash(row)
    candidate = validate_faction_source_audit_bytes(_bytes(payload))
    catalog = faction_source_catalog(candidate)
    assert catalog.package_id.version == "app-data-947-observed-2026-09-07"
    assert catalog.catalog_version.version_id == catalog.package_id.version
    assert catalog.catalog_version.source_date == "2026-09-07"

    registry = source_authority_registry()
    scope = registry.scope("warhammer_40000_11th_factions")
    observations = {row.observation_id: row for row in candidate.observations}
    updated_scope = replace(
        scope,
        audit_rows=tuple(
            replace(
                row,
                source_observation_sha256=observations[row.row_id].source_observation_sha256,
                identity_value=f"947@{observations[row.row_id].observed_at}",
            )
            if row.audit_id == candidate.audit_id
            else row
            for row in scope.audit_rows
        ),
    )
    updated_registry = replace(
        registry,
        scopes=tuple(
            updated_scope if row.scope_id == scope.scope_id else row for row in registry.scopes
        ),
    )
    # All audit-row registrations now agree, but the retained package registration is stale.
    with pytest.raises(FactionSourceError, match="source-package authorization"):
        governance_builder.validate_registry(candidate, registry=updated_registry)
    with pytest.raises(SourceAuthorityRegistryError, match="identity is not authorized"):
        updated_registry.authorize_source_package(
            scope_id=scope.scope_id,
            namespace=catalog.package_id.namespace,
            package_name=catalog.package_id.package_name,
            version=catalog.package_id.version,
            rule_source_ids=candidate.selected_source_ids,
            catalog_sha256=catalog.catalog_sha256(),
        )


@pytest.mark.parametrize("mutation", ["catalog_hash", "inventory", "missing", "extra"])
def test_f00_generator_checks_entire_package_registration(mutation: str) -> None:
    registry = source_authority_registry()
    scope = registry.scope("warhammer_40000_11th_factions")
    package = scope.source_packages[0]
    packages: tuple[SourcePackageAuthorization, ...]
    if mutation == "catalog_hash":
        packages = (replace(package, catalog_sha256="0" * 64),)
    elif mutation == "inventory":
        packages = (replace(package, allowed_rule_source_ids=package.allowed_rule_source_ids[:-1]),)
    elif mutation == "missing":
        packages = ()
    else:
        packages = (*scope.source_packages, replace(package, version="unreviewed"))
    drifted = replace(
        registry,
        scopes=tuple(
            replace(row, source_packages=packages) if row.scope_id == scope.scope_id else row
            for row in registry.scopes
        ),
    )
    with pytest.raises(FactionSourceError, match="source-package authorization"):
        governance_builder.validate_registry(faction_source_audit(), registry=drifted)


def test_f00_catalog_hash_is_canonical_across_document_order_and_payload_round_trip() -> None:
    catalog = faction_source_package().source_catalog
    reordered = replace(catalog, documents=tuple(reversed(catalog.documents)))
    restored = SourceCatalog.from_payload(json.loads(json.dumps(reordered.to_payload())))
    expected_hash = hashlib.sha256(
        json.dumps(catalog.to_payload(), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert catalog.catalog_sha256() == reordered.catalog_sha256() == restored.catalog_sha256()
    assert catalog.catalog_sha256() == expected_hash


def test_source_authorization_rejects_duplicate_inventory_before_set_comparison() -> None:
    catalog = faction_source_package().source_catalog
    source_ids = faction_source_audit().selected_source_ids
    with pytest.raises(SourceAuthorityRegistryError, match="source IDs must be unique"):
        source_authority_registry().authorize_source_package(
            scope_id="warhammer_40000_11th_factions",
            namespace=catalog.package_id.namespace,
            package_name=catalog.package_id.package_name,
            version=catalog.package_id.version,
            rule_source_ids=(*source_ids, source_ids[0]),
            catalog_sha256=catalog.catalog_sha256(),
        )
