from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from warhammer40k_core.core.datasheet import WargearOptionEffectKind
from warhammer40k_core.rules.wahapedia_bridge_patterns import (
    EQUIPMENT_CHOICE_RE,
    EQUIPMENT_WITH_CHOICES_RE,
)
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


@dataclass(frozen=True, slots=True)
class _EquipmentChoice:
    name: str
    count: int


def append_choice_rows(
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_ids: tuple[str, ...],
    wargear_ids_by_name: dict[str, str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> bool:
    description = _required_field(row, "description", error_type=error_type)
    match = EQUIPMENT_WITH_CHOICES_RE.fullmatch(description)
    if match is None:
        return False
    choices = _equipment_choices(match.group("choices"), error_type=error_type)
    for choice in choices:
        if choice.count != 1:
            raise error_type("Equipment choice bridge only supports single-item additive choices.")
    choice_wargear_ids = tuple(
        _required_wargear_id(wargear_ids_by_name, choice.name, error_type=error_type)
        for choice in choices
    )
    if len(set(choice_wargear_ids)) != len(choice_wargear_ids):
        raise error_type("Equipment choice bridge requires unique wargear choices.")
    if len(model_profile_ids) != 1:
        raise error_type("This-model equipment choice requires one model profile.")
    source_line = _required_field(row, "line", error_type=error_type)
    option_id = f"{datasheet_id}:equipment-choice:option-{source_line}"
    common_fields = {
        "datasheet_id": datasheet_id,
        "description": _raw_or_field(row, "description"),
        "option_id": option_id,
        "model_profile_id": model_profile_ids[0],
        "default_wargear_ids": "",
        "allowed_wargear_ids": ",".join(choice_wargear_ids),
        "min_selections": "0",
        "max_selections": "1",
        "condition_kind": "",
        "condition_wargear_ids": "",
        "effect_replaced_wargear_id": "",
        "effect_model_count": "1",
        "effect_wargear_count": "1",
        "source_ids": ",".join(_source_ids(row)),
    }
    bridged_rows["Datasheets_options"].extend(
        {
            **common_fields,
            "line": f"{source_line}.{choice_index}",
            "effect_kind": WargearOptionEffectKind.ADD_WARGEAR_IF_SELECTED.value,
            "effect_wargear_id": choice_wargear_id,
        }
        for choice_index, choice_wargear_id in enumerate(choice_wargear_ids, start=1)
    )
    return True


def _equipment_choices(
    choices_text: str, *, error_type: type[ValueError]
) -> tuple[_EquipmentChoice, ...]:
    choices: list[_EquipmentChoice] = []
    for line in choices_text.splitlines():
        match = EQUIPMENT_CHOICE_RE.fullmatch(line.strip())
        if match is None:
            raise error_type("Unsupported equipment wargear choice row shape.")
        count_text = match.group("count")
        count = 1 if count_text is None else int(count_text)
        if count < 1:
            raise error_type("equipment count must be at least 1.")
        choices.append(_EquipmentChoice(name=match.group("name"), count=count))
    if not choices:
        raise error_type("Equipment wargear option has no choices.")
    return tuple(choices)


def _required_field(
    row: NormalizedSourceRow, column_name: str, *, error_type: type[ValueError]
) -> str:
    fields = row.runtime_fields_payload()
    if column_name not in fields:
        raise error_type(f"Required source column is missing: {column_name}.")
    value = fields[column_name].strip()
    if not value and column_name not in {"ability_id", "description", "parameter", "faction_id"}:
        raise error_type(f"Required source column is empty: {column_name}.")
    return value


def _raw_or_field(row: NormalizedSourceRow, column_name: str) -> str:
    for text_field in row.text_fields:
        if text_field.column_name == column_name:
            return text_field.raw_text
    return row.runtime_fields_payload().get(column_name, "")


def _source_ids(row: NormalizedSourceRow) -> tuple[str, ...]:
    source_ids = [row.stable_source_id()]
    explicit_source_ids = row.runtime_fields_payload().get("source_ids")
    if explicit_source_ids is not None:
        source_ids.extend(item.strip() for item in explicit_source_ids.split(",") if item.strip())
    return tuple(dict.fromkeys(source_ids))


def _required_wargear_id(
    wargear_ids_by_name: dict[str, str],
    wargear_name: str,
    *,
    error_type: type[ValueError],
) -> str:
    key = _name_key(wargear_name, error_type=error_type)
    wargear_id = wargear_ids_by_name.get(key)
    if wargear_id is None and key.endswith("s"):
        wargear_id = wargear_ids_by_name.get(key[:-1])
    if wargear_id is None:
        raise error_type("Wargear option references an unknown wargear item.")
    return wargear_id


def _name_key(value: str, *, error_type: type[ValueError]) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    lowered = normalized.casefold().replace("'", "").replace("&", " and ")
    characters: list[str] = []
    previous_dash = False
    for character in lowered:
        if character.isalnum():
            characters.append(character)
            previous_dash = False
        elif not previous_dash:
            characters.append("-")
            previous_dash = True
    slug = "".join(characters).strip("-")
    if not slug:
        raise error_type("Could not derive a stable slug.")
    return slug
