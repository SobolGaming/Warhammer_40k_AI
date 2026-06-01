from __future__ import annotations

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import battle_phase_kind_from_token
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    KeywordGate,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.source_packages.warhammer_40000_10th import (
    core_abilities as source_data,
)

TENTH_EDITION_CORE_ABILITY_SOURCE_PACKAGE_ID = source_data.SOURCE_PACKAGE_ID


def tenth_edition_core_ability_catalog_records() -> tuple[AbilityCatalogRecord, ...]:
    return tuple(_record_from_source_row(row) for row in source_data.core_ability_rows())


def tenth_edition_core_ability_index() -> AbilityCatalogIndex:
    return AbilityCatalogIndex.from_records(tenth_edition_core_ability_catalog_records())


def tenth_edition_ability_catalog_records() -> tuple[AbilityCatalogRecord, ...]:
    return tuple(_record_from_source_row(row) for row in source_data.ability_rows())


def tenth_edition_ability_index() -> AbilityCatalogIndex:
    return AbilityCatalogIndex.from_records(tenth_edition_ability_catalog_records())


def build_player_ability_index(
    records: tuple[AbilityCatalogRecord, ...],
    *,
    army: ArmyDefinition,
    catalog: ArmyCatalog | None = None,
) -> AbilityCatalogIndex:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Player Ability index requires an ArmyDefinition.")
    if catalog is not None and type(catalog) is not ArmyCatalog:
        raise GameLifecycleError("Player Ability index catalog must be an ArmyCatalog.")
    validated_records = AbilityCatalogIndex.from_records(records).all_records()
    selected_datasheet_ids = frozenset(unit.datasheet_id for unit in army.units)
    selected_wargear_ids = frozenset(
        wargear_id
        for unit in army.units
        for selection in unit.wargear_selections
        for wargear_id in selection.wargear_ids
    )
    selected_weapon_profile_ids = (
        _selected_weapon_profile_ids(catalog=catalog, wargear_ids=selected_wargear_ids)
        if catalog is not None
        else frozenset[str]()
    )
    selected_weapon_keywords = (
        _selected_weapon_keywords(catalog=catalog, wargear_ids=selected_wargear_ids)
        if catalog is not None
        else frozenset[str]()
    )

    player_records: list[AbilityCatalogRecord] = []
    for record in validated_records:
        if not _record_source_matches_player(
            record=record,
            army=army,
            selected_datasheet_ids=selected_datasheet_ids,
            selected_wargear_ids=selected_wargear_ids,
            selected_weapon_profile_ids=selected_weapon_profile_ids,
            selected_weapon_keywords=selected_weapon_keywords,
            has_weapon_profile_context=catalog is not None,
        ):
            continue
        if not _record_keyword_gate_matches_player(
            record=record,
            army=army,
            selected_weapon_keywords=selected_weapon_keywords,
        ):
            continue
        player_records.append(record)
    return AbilityCatalogIndex.from_records(tuple(player_records))


def _record_from_source_row(row: source_data.SourceAbilityRow) -> AbilityCatalogRecord:
    return AbilityCatalogRecord(
        record_id=f"{source_data.SOURCE_PACKAGE_ID}:{row.source_kind}:{row.ability_id}",
        definition=AbilityDefinition(
            ability_id=row.ability_id,
            name=row.name,
            source_id=row.source_id,
            when_descriptor=row.when_descriptor,
            effect_descriptor=row.effect_descriptor,
            restrictions_descriptor=row.restrictions_descriptor,
            timing=AbilityTimingDescriptor(
                trigger_kind=TimingTriggerKind(row.trigger_kind),
                phase=None if row.phase is None else battle_phase_kind_from_token(row.phase),
            ),
            keyword_gate=KeywordGate(
                required_keywords=row.required_keywords,
                forbidden_keywords=row.forbidden_keywords,
            ),
            handler_id=row.handler_id,
            required_input_keys=row.required_input_keys,
            replay_payload=validate_json_value(row.effect_payload),
        ),
        source_kind=AbilitySourceKind(row.source_kind),
        faction_id=row.faction_id,
        detachment_id=row.detachment_id,
        datasheet_id=row.datasheet_id,
        wargear_id=row.wargear_id,
        weapon_profile_id=row.weapon_profile_id,
        disabled=row.disabled,
    )


def _record_source_matches_player(
    *,
    record: AbilityCatalogRecord,
    army: ArmyDefinition,
    selected_datasheet_ids: frozenset[str],
    selected_wargear_ids: frozenset[str],
    selected_weapon_profile_ids: frozenset[str],
    selected_weapon_keywords: frozenset[str],
    has_weapon_profile_context: bool,
) -> bool:
    source_kind = record.source_kind
    if source_kind in {AbilitySourceKind.CORE, AbilitySourceKind.KEYWORD}:
        return True
    if source_kind is AbilitySourceKind.FACTION:
        return record.faction_id == army.detachment_selection.faction_id
    if source_kind is AbilitySourceKind.DETACHMENT:
        return record.detachment_id == army.detachment_selection.detachment_id
    if source_kind is AbilitySourceKind.ENHANCEMENT:
        return (
            record.detachment_id == army.detachment_selection.detachment_id
            and record.definition.ability_id in army.detachment_selection.enhancement_ids
        )
    if source_kind is AbilitySourceKind.DATASHEET:
        return record.datasheet_id in selected_datasheet_ids
    if source_kind is AbilitySourceKind.WARGEAR:
        return record.wargear_id in selected_wargear_ids
    if source_kind is AbilitySourceKind.WEAPON:
        if not has_weapon_profile_context:
            return False
        if record.weapon_profile_id is not None:
            return record.weapon_profile_id in selected_weapon_profile_ids
        return record.definition.keyword_gate.matches(tuple(selected_weapon_keywords))
    raise GameLifecycleError(f"Unsupported AbilitySourceKind: {source_kind}.")


def _record_keyword_gate_matches_player(
    *,
    record: AbilityCatalogRecord,
    army: ArmyDefinition,
    selected_weapon_keywords: frozenset[str],
) -> bool:
    if record.definition.keyword_gate.is_empty:
        return True
    if record.source_kind is AbilitySourceKind.WEAPON:
        return record.definition.keyword_gate.matches(tuple(selected_weapon_keywords))
    return any(
        record.definition.keyword_gate.matches((*unit.keywords, *unit.faction_keywords))
        for unit in army.units
    )


def _selected_weapon_profile_ids(
    *,
    catalog: ArmyCatalog | None,
    wargear_ids: frozenset[str],
) -> frozenset[str]:
    if catalog is None:
        return frozenset()
    selected: set[str] = set()
    for wargear_id in wargear_ids:
        wargear = _wargear_by_id(catalog=catalog, wargear_id=wargear_id)
        selected.update(profile.profile_id for profile in wargear.weapon_profiles)
    return frozenset(selected)


def _selected_weapon_keywords(
    *,
    catalog: ArmyCatalog | None,
    wargear_ids: frozenset[str],
) -> frozenset[str]:
    if catalog is None:
        return frozenset()
    selected: set[str] = set()
    for wargear_id in wargear_ids:
        wargear = _wargear_by_id(catalog=catalog, wargear_id=wargear_id)
        for profile in wargear.weapon_profiles:
            selected.update(_canonical_keyword(keyword.value) for keyword in profile.keywords)
            selected.update(
                _canonical_keyword(ability.ability_kind.value) for ability in profile.abilities
            )
    return frozenset(selected)


def _wargear_by_id(*, catalog: ArmyCatalog, wargear_id: str) -> Wargear:
    requested_id = _validate_identifier("wargear_id", wargear_id)
    for wargear in catalog.wargear:
        if wargear.wargear_id == requested_id:
            return wargear
    raise GameLifecycleError("Player Ability index references unknown wargear.")


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace(" ", "_").replace("-", "_")
