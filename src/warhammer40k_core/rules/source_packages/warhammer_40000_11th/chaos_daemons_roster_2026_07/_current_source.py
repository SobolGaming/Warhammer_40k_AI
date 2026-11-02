"""Authenticate the three current descriptions before historical reconciliation."""

import json
from dataclasses import replace
from hashlib import sha256
from typing import TYPE_CHECKING, Final

import msgspec

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import core_abilities_2026_09

from ._reconciliation import (
    ChaosDaemonsRosterReconciliationError,
    ExactRosterReconciliation,
    catalog_datasheet_gameplay_hash,
    validate_catalog_against_reconciliation,
)

if TYPE_CHECKING:
    from warhammer40k_core.core.datasheet import DatasheetDefinition
    from warhammer40k_core.core.datasheet_ability import DatasheetAbilityDescriptor

_PACKAGE_NAME: Final = __name__.rpartition(".")[0]

ARTIFACT_PATH: Final = "artifacts/deadly-demise-current-source.json"
ARTIFACT_SHA256: Final = "b54d283b513d2cc4f7d032e26cec33ee5a551e573896d9ca1631062ab7bb10b1"
SOURCE_ARTIFACT_NAME: Final = "deadly-demise-current-source.json"


class CurrentDescriptionDelta(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    datasheet_id: str
    ability_id: str
    source_id: str
    parameter_tokens: tuple[str, ...]
    historical_descriptor_sha256: str
    historical_gameplay_sha256: str


class CurrentSourceDerivation(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    schema_version: str
    catalog_id: str
    core_source_id: str
    core_artifact_sha256: str
    historical_text: str
    historical_text_sha256: str
    current_text_sha256: str
    historical_reconciliation_sha256: str
    deltas: tuple[CurrentDescriptionDelta, ...]


def current_source_from_json_bytes(raw: bytes) -> CurrentSourceDerivation:
    if type(raw) is not bytes or sha256(raw).hexdigest() != ARTIFACT_SHA256:
        raise ChaosDaemonsRosterReconciliationError("Current source derivation bytes drifted.")
    try:
        derivation = msgspec.json.decode(raw, type=CurrentSourceDerivation)
    except msgspec.DecodeError as exc:
        raise ChaosDaemonsRosterReconciliationError(
            "Current source derivation is invalid."
        ) from exc

    if derivation.schema_version != "chaos-daemons-deadly-demise-current-source-v1":
        raise ChaosDaemonsRosterReconciliationError("Current source derivation schema drifted.")
    return derivation


def current_source_derivation() -> CurrentSourceDerivation:
    derivation = current_source_from_json_bytes(
        package_artifact_bytes(_PACKAGE_NAME, ARTIFACT_PATH)
    )
    historical_raw = package_artifact_bytes(
        _PACKAGE_NAME, "artifacts/official-pdf-reconciliation.json"
    )
    if sha256(historical_raw).hexdigest() != derivation.historical_reconciliation_sha256:
        raise ChaosDaemonsRosterReconciliationError(
            "Current derivation historical manifest drifted."
        )
    return derivation


def historical_catalog_for_current_source(catalog: ArmyCatalog) -> ArmyCatalog:
    """Project only authenticated current prose; reject every other descriptor delta."""
    derivation = current_source_derivation()
    rule = core_abilities_2026_09.source_rule_record()
    if (
        catalog.catalog_id != derivation.catalog_id
        or derivation.core_source_id not in catalog.source_ids
        or rule.source_id != derivation.core_source_id
        or derivation.core_artifact_sha256 != core_abilities_2026_09.EXPECTED_ARTIFACT_SHA256
        or sha256(rule.source_text.encode()).hexdigest() != derivation.current_text_sha256
        or sha256(derivation.historical_text.encode()).hexdigest()
        != derivation.historical_text_sha256
    ):
        raise ChaosDaemonsRosterReconciliationError(
            "Current Deadly Demise source identity drifted."
        )
    expected = {(row.datasheet_id, row.source_id): row for row in derivation.deltas}
    observed = tuple(
        (row.datasheet_id, ability.source_id)
        for row in catalog.datasheets
        for ability in row.abilities
        if ability.ability_id == "000008339"
    )
    if len(observed) != len(expected) or set(observed) != set(expected):
        raise ChaosDaemonsRosterReconciliationError(
            "Current Deadly Demise occurrence closure drifted."
        )
    projected: list[DatasheetDefinition] = []
    for datasheet in catalog.datasheets:
        abilities: list[DatasheetAbilityDescriptor] = []
        for ability in datasheet.abilities:
            if ability.ability_id != "000008339":
                abilities.append(ability)
                continue
            delta = expected[(datasheet.datasheet_id, ability.source_id)]
            historical = replace(ability, effect_description=derivation.historical_text)
            descriptor_sha256 = sha256(
                json.dumps(historical.to_payload(), sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if (
                ability.ability_id != delta.ability_id
                or ability.effect_description != rule.source_text
                or ability.parameter_tokens != delta.parameter_tokens
                or descriptor_sha256 != delta.historical_descriptor_sha256
            ):
                raise ChaosDaemonsRosterReconciliationError(
                    "Current Deadly Demise descriptor delta drifted."
                )
            abilities.append(historical)
        projected.append(replace(datasheet, abilities=tuple(abilities)))
    historical_catalog = replace(catalog, datasheets=tuple(projected))
    for delta in derivation.deltas:
        if (
            catalog_datasheet_gameplay_hash(
                catalog=historical_catalog, datasheet_id=delta.datasheet_id
            )
            != delta.historical_gameplay_sha256
        ):
            raise ChaosDaemonsRosterReconciliationError(
                "Current derivation gameplay baseline drifted."
            )
    return historical_catalog


def validate_current_catalog_against_reconciliation(
    *, catalog: ArmyCatalog, reconciliation: ExactRosterReconciliation
) -> None:
    validate_catalog_against_reconciliation(
        catalog=historical_catalog_for_current_source(catalog), reconciliation=reconciliation
    )
