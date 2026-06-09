from __future__ import annotations

import json

from warhammer40k_core.core.missions import MissionSourcePackageDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.rules.source_catalog import SourceCatalog
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2026_27,
    core_abilities,
    core_rules,
    core_stratagems,
)


def test_eleventh_core_rules_source_catalog_cites_local_pdf_and_round_trips() -> None:
    catalog = core_rules.source_catalog()
    payload = catalog.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    bundle = catalog.ruleset_bundles[0]
    document = catalog.documents[0]

    assert bundle.ruleset_id.to_payload()["edition"] == "11e"
    assert core_rules.LOCAL_CORE_RULES_PDF in document.title
    assert core_rules.LOCAL_CORE_RULES_PDF in document.source_texts[0].raw_text
    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert SourceCatalog.from_payload(payload).to_payload() == payload


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
