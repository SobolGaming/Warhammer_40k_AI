"""A current source observation cannot relabel or overwrite its predecessor."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.support import section08_native_mission_source as source
from tests.support.faction_batch01 import faction_definitions
from tests.support.section02_fixtures import Section02Definitions

ROOT = Path(__file__).resolve().parents[2]
__all__ = ("faction_definitions",)


def test_native_mission_current_mirror_crosswalk_keeps_exact_predecessor() -> None:
    row = source.validate_observation((ROOT / source.PATH).read_bytes())
    assert row["app_version"] == "995"
    assert row["identity_crosswalk"]["runtime_source_id"] == source.SOURCE_ID
    assert row["historical_lineage"]["bridge_ability_sha256"] == source.PREDECESSOR
    assert row["provider_owned_by_games_workshop"] is False
    assert (
        row["version_evidence"]["meaning"] == "current App-data snapshot; not last changed version"
    )


@pytest.mark.parametrize(
    "field", ["captured_text", "ability_text", "identity_crosswalk", "historical_lineage"]
)
def test_native_mission_source_pin_rejects_tamper(field: str) -> None:
    row = json.loads((ROOT / source.PATH).read_bytes())
    row[field] = "changed"
    with pytest.raises(ValueError, match="reviewed source observation changed"):
        source.validate_observation(json.dumps(row).encode())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("edition", "wrong-edition"),
        ("provider_name", "other-provider"),
        ("provider_owned_by_games_workshop", True),
        ("datasheet_id", "000004080"),
        ("app_version", "946"),
        ("url", "https://www.40k.app/factions/aeldari/units/tormentors"),
    ],
)
def test_native_mission_source_semantics_reject_even_a_blind_repin(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    row = json.loads((ROOT / source.PATH).read_bytes())
    row[field] = value
    raw = json.dumps(row).encode()
    monkeypatch.setattr(source, "SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError, match="provider/edition/page ownership changed"):
        source.validate_observation(raw)


def test_native_mission_factory_changes_only_the_reviewed_ability_identity(
    faction_definitions: Section02Definitions,
) -> None:
    before = faction_definitions.package.to_payload()
    updated = source.source_backed_command_definitions(faction_definitions)
    sheet = faction_definitions.package.army_catalog.datasheet_by_id("000004079")
    current = updated.package.army_catalog.datasheet_by_id("000004079")
    row = source.validate_observation((ROOT / source.PATH).read_bytes())
    target = row["ability_id"]
    prior = next(a for a in sheet.abilities if a.ability_id == target)
    active = next(a for a in current.abilities if a.ability_id == target)
    assert replace(active, source_id=prior.source_id) == prior
    assert active.source_id == source.SOURCE_ID
    assert current.source_ids == tuple(
        sorted(
            {
                *sheet.source_ids,
                prior.source_id,
                source.SOURCE_ID,
                row["identity_crosswalk"]["page_source_id"],
            }
        )
    )
    assert replace(current, abilities=sheet.abilities, source_ids=sheet.source_ids) == sheet
    assert tuple(
        d for d in updated.package.army_catalog.datasheets if d.datasheet_id != sheet.datasheet_id
    ) == tuple(
        d
        for d in faction_definitions.package.army_catalog.datasheets
        if d.datasheet_id != sheet.datasheet_id
    )
    assert faction_definitions.package.to_payload() == before


def test_native_mission_factory_rejects_wrong_predecessor_identity(
    faction_definitions: Section02Definitions,
) -> None:
    package = faction_definitions.package
    sheet = package.army_catalog.datasheet_by_id("000004079")
    altered = replace(
        sheet,
        abilities=tuple(
            replace(a, source_id="wrong-edition:source")
            if a.ability_id == "000004079:objective-defiled"
            else a
            for a in sheet.abilities
        ),
    )
    catalog = replace(
        package.army_catalog,
        datasheets=tuple(
            altered if d.datasheet_id == sheet.datasheet_id else d
            for d in package.army_catalog.datasheets
        ),
    )
    definitions = replace(faction_definitions, package=replace(package, army_catalog=catalog))
    with pytest.raises(ValueError, match="predecessor identity or semantics changed"):
        source.source_backed_command_definitions(definitions)
