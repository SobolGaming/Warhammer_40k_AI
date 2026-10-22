"""Reviewed mirror-to-RuleIR crosswalk for one native component fixture.

This never admits a full catalog or rewrites historical source identities.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from tests.support.section02_fixtures import Section02Definitions

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import faction_pack_rule_ir

PATH = "data/source_audits/section08_native_mission_2026_10_22/observation.json"
SHA256 = "dc4d92037d661208270d1c178625de3aa85b984b6f06b7f21dc1f313e4ce1f10"
PACKAGE = "gw-11e-emperors-children-infractors-tormentors-datasheets-2026-08"
SOURCE_ID = PACKAGE + ":datasheet:000004079:3"
PREDECESSOR = "ea77045ee0940a8d12e330080f69790c64839932109a190b19195426f3320cce"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_observation(raw: bytes) -> dict[str, Any]:
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise ValueError("Native Command reviewed source observation changed.")
    row: dict[str, Any] = json.loads(raw)
    if (
        row["provider_name"] != "40k.app"
        or row["provider_owned_by_games_workshop"] is not False
        or row["edition"] != "warhammer_40000_11th"
        or row["app_version"] != "995"
        or row["locale"] != "en"
        or row["url"] != "https://www.40k.app/factions/emperors-children/units/tormentors"
        or row["datasheet_id"] != "000004079"
        or row["owning_faction_id"] != "emperors-children"
    ):
        raise ValueError("Native Command provider/edition/page ownership changed.")
    fingerprint = {k: v for k, v in row.items() if k != "observation_sha256"}
    if _digest(fingerprint) != row["observation_sha256"]:
        raise ValueError("Native Command source observation fingerprint changed.")
    crosswalk = row["identity_crosswalk"]
    artifact = faction_pack_rule_ir.source_package_artifact(PACKAGE)
    payload = artifact.datasheet_rule_ir_payload_by_source_row_id("000004079:3")
    if (
        payload is None
        or crosswalk["admitted_package_id"] != PACKAGE
        or crosswalk["page_source_id"] != "faction-app:emperors-children:datasheet:tormentors"
        or artifact.package_hash != crosswalk["admitted_package_hash"]
        or payload["source_id"] != SOURCE_ID
        or crosswalk["runtime_source_id"] != SOURCE_ID
        or crosswalk["runtime_rule_id"] != payload["rule_id"]
        or crosswalk["rule_ir_hash"] != payload["ir_hash"]
        or hashlib.sha256(payload["normalized_text"].encode()).hexdigest()
        != crosswalk["normalized_text_sha256"]
        or row["ability_text"].replace("\u2019", "'") != payload["normalized_text"]
    ):
        raise ValueError("Native Command current observation/RuleIR crosswalk changed.")
    capture = row["captured_text"]
    heading = "\nTormentors\n"
    if (
        capture.count(heading) != 1
        or capture[capture.index(heading) + 1 :] != row["operative_text"]
        or not capture.endswith("\nObjective Defiled\n\n" + row["ability_text"])
        or hashlib.sha256(capture.encode()).hexdigest() != row["captured_text_sha256"]
        or hashlib.sha256(row["operative_text"].encode()).hexdigest()
        != row["operative_text_sha256"]
    ):
        raise ValueError("Native Command full capture or operative suffix changed.")
    return row


def source_backed_command_definitions(definitions: Section02Definitions) -> Section02Definitions:
    root = Path(__file__).resolve().parents[2]
    row = validate_observation((root / PATH).read_bytes())
    package = definitions.package
    sheet = package.army_catalog.datasheet_by_id("000004079")
    abilities = tuple(a for a in sheet.abilities if a.ability_id == row["ability_id"])
    if (
        len(abilities) != 1
        or _digest(abilities[0].to_payload()) != PREDECESSOR
        or sheet.source_ids != tuple(row["historical_lineage"]["datasheet_source_ids"])
    ):
        raise ValueError("Native Command sticky predecessor identity or semantics changed.")
    ability = abilities[0]
    if ability.to_payload() != row["historical_lineage"]["bridge_ability"]:
        raise ValueError("Native Command exact historical ability lineage changed.")
    current = replace(ability, source_id=SOURCE_ID)
    current_sheet = replace(
        sheet,
        abilities=tuple(
            current if a.ability_id == ability.ability_id else a for a in sheet.abilities
        ),
        source_ids=tuple(
            dict.fromkeys(
                (
                    *sheet.source_ids,
                    ability.source_id,
                    SOURCE_ID,
                    row["identity_crosswalk"]["page_source_id"],
                )
            )
        ),
    )
    catalog = replace(
        package.army_catalog,
        datasheets=tuple(
            current_sheet if d.datasheet_id == sheet.datasheet_id else d
            for d in package.army_catalog.datasheets
        ),
    )
    return replace(definitions, package=replace(package, army_catalog=catalog))
