from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from warhammer40k_core.core.missions import MissionSourcePackageDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.rules.source_catalog import SourceCatalog
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2026_27,
    core_abilities,
    core_rules,
    core_stratagems,
    july_rules_updates_2026_07,
)


def test_eleventh_core_rules_source_catalog_cites_local_pdf_and_round_trips() -> None:
    catalog = core_rules.source_catalog()
    payload = catalog.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    bundle = catalog.ruleset_bundles[0]
    document = catalog.documents[0]

    assert bundle.ruleset_id.to_payload()["edition"] == "11e"
    assert core_rules.LOCAL_CORE_RULES_PDF in document.title
    assert any(
        core_rules.LOCAL_CORE_RULES_PDF in source.raw_text for source in document.source_texts
    )
    assert len(document.source_texts) == 1
    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert SourceCatalog.from_payload(payload).to_payload() == payload


def test_july_rules_updates_source_catalog_cites_both_committed_pdfs() -> None:
    catalog = july_rules_updates_2026_07.source_catalog()
    payload = catalog.to_payload()
    encoded = json.dumps(payload, sort_keys=True)

    assert len(catalog.documents) == 2
    universal_documents = tuple(
        document
        for document in catalog.documents
        if july_rules_updates_2026_07.UNIVERSAL_RULES_LOCAL_PDF in document.title
    )
    event_companion_documents = tuple(
        document
        for document in catalog.documents
        if july_rules_updates_2026_07.EVENT_COMPANION_LOCAL_PDF in document.title
    )
    assert len(universal_documents) == 1
    assert len(event_companion_documents) == 1
    universal_document = universal_documents[0]
    event_companion_document = event_companion_documents[0]
    universal_rules = july_rules_updates_2026_07.universal_rule_records()
    event_rules = july_rules_updates_2026_07.event_companion_rule_records()
    assert {rule.rule_id: rule.behavior_descriptor for rule in universal_rules} == {
        "modifying-a-stratagem-cp-cost": "unnamed_zero_cp_reduces_cost_by_one",
        "stratagem-repeat-and-limit-exceptions": (
            "repeat_or_limit_exception_requires_named_stratagem"
        ),
        "stratagems-that-prevent-targeting": ("protective_targeting_range_is_eighteen_inches"),
        "stratagems-that-add-identical-units": ("identical_unit_replacement_once_per_battle"),
    }
    assert {rule.rule_id: rule.behavior_descriptor for rule in event_rules} == {
        "generating-command-points": "non_core_cp_gain_maximum_one_per_battle_round",
    }
    assert len(july_rules_updates_2026_07.changed_event_layouts()) == 8
    assert all(
        not row.deployment_zones_changed
        for row in july_rules_updates_2026_07.changed_event_layouts()
    )
    assert july_rules_updates_2026_07.UNIVERSAL_RULES_LOCAL_PDF in encoded
    assert july_rules_updates_2026_07.EVENT_COMPANION_LOCAL_PDF in encoded
    assert july_rules_updates_2026_07.UNIVERSAL_RULES_PDF_SHA256 in encoded
    assert july_rules_updates_2026_07.EVENT_COMPANION_PDF_SHA256 in encoded
    universal_source_ids = {source.source_id for source in universal_document.source_texts}
    event_source_texts_by_id = {
        source.source_id: source for source in event_companion_document.source_texts
    }
    assert {rule.source_id for rule in universal_rules} <= universal_source_ids
    assert july_rules_updates_2026_07.NON_CORE_CP_GAIN_CAP_SOURCE_ID not in universal_source_ids
    assert july_rules_updates_2026_07.NON_CORE_CP_GAIN_CAP_SOURCE_ID in event_source_texts_by_id
    assert (
        "maximum of 1CP per battle round"
        in event_source_texts_by_id[
            july_rules_updates_2026_07.NON_CORE_CP_GAIN_CAP_SOURCE_ID
        ].raw_text
    )
    assert SourceCatalog.from_payload(payload).to_payload() == payload

    for relative_path, expected_sha256 in (
        (
            july_rules_updates_2026_07.UNIVERSAL_RULES_LOCAL_PDF,
            july_rules_updates_2026_07.UNIVERSAL_RULES_PDF_SHA256,
        ),
        (
            july_rules_updates_2026_07.EVENT_COMPANION_LOCAL_PDF,
            july_rules_updates_2026_07.EVENT_COMPANION_PDF_SHA256,
        ),
    ):
        assert hashlib.sha256(Path(relative_path).read_bytes()).hexdigest() == expected_sha256


def test_july_rules_updates_artifact_rejects_unknown_fields() -> None:
    payload = _july_rules_update_payload()
    payload["unexpected"] = True

    with pytest.raises(july_rules_updates_2026_07.JulyRulesUpdateArtifactError):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("rule_id", "unexpected-global-rule"),
        ("behavior_descriptor", "unexpected_global_behavior"),
    ],
)
def test_july_rules_updates_artifact_rejects_universal_rule_identity_drift(
    field_name: str,
    replacement: str,
) -> None:
    payload = _july_rules_update_payload()
    _universal_rule_payload(payload)[field_name] = replacement

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="Universal rules-update rule identity inventory drifted",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_july_rules_updates_artifact_rejects_universal_rule_source_suffix_drift() -> None:
    payload = _july_rules_update_payload()
    _universal_rule_payload(payload)["source_id"] = (
        "gw-11e-rules-and-event-updates-2026-07-22:universal-rules:wrong-rule"
    )

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="Universal rules-update source identity drifted",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


@pytest.mark.parametrize(
    "field_name",
    ["document_id", "source_version", "source_url", "local_pdf"],
)
def test_july_rules_updates_artifact_rejects_universal_document_metadata_drift(
    field_name: str,
) -> None:
    payload = _july_rules_update_payload()
    universal_update = cast(dict[str, object], payload["universal_rules_update"])
    universal_update[field_name] = "unexpected"

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="Universal rules-update document metadata drifted",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_eleventh_source_package_identity_payloads_are_json_safe() -> None:
    mission_package = chapter_approved_2026_27.source_package_definition()
    mission_payload = mission_package.to_payload()
    ability_identity = core_abilities.source_package_identity_payload()
    stratagem_identity = core_stratagems.source_package_identity_payload()
    payload = {
        "mission_package": mission_payload,
        "ability_identity": ability_identity,
        "stratagem_identity": stratagem_identity,
    }
    encoded = json.dumps(payload, sort_keys=True)

    assert mission_payload["edition_id"] == "warhammer_40000_11th"
    assert ability_identity["edition_id"] == "warhammer_40000_11th"
    assert stratagem_identity["edition_id"] == "warhammer_40000_11th"
    assert mission_payload["source_package_id"].startswith("gw-11e-")
    assert ability_identity["source_package_id"].startswith("gw-11e-")
    assert stratagem_identity["source_package_id"].startswith("gw-11e-")
    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert MissionSourcePackageDefinition.from_payload(mission_payload).to_payload() == (
        mission_payload
    )


def test_ruleset_descriptor_hash_is_eleventh_only_and_deterministic() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    payload = descriptor.to_payload()

    assert payload["ruleset_id"]["edition"] == "11e"
    assert descriptor.descriptor_hash == RulesetDescriptor.from_payload(payload).descriptor_hash


def _july_rules_update_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(
            Path(
                "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
                "july_rules_updates_2026_07/artifacts/package.json"
            ).read_text()
        ),
    )


def _universal_rule_payload(payload: dict[str, object]) -> dict[str, object]:
    universal_update = cast(dict[str, object], payload["universal_rules_update"])
    rules = cast(list[dict[str, object]], universal_update["rules"])
    return rules[0]
