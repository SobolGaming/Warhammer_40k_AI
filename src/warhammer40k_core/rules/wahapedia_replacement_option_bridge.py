from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from warhammer40k_core.core.datasheet import WargearOptionEffectKind
from warhammer40k_core.rules.wahapedia_bridge_patterns import (
    COUNT_WORDS,
    DUPLICATE_EQUIPMENT_RESTRICTION_RE,
    NAMED_MODEL_REPLACEMENT_WITH_CHOICES_RE,
    OPTION_CHOICE_RE,
    OPTION_CHOICE_RESTRICTION_RE,
    PAIRED_OPTION_CHOICE_RE,
    SCALED_MODEL_REPLACEMENT_WITH_PAIRED_CHOICES_RE,
    SCALED_OPTION_DUPLICATE_RESTRICTION_RE,
)
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


@dataclass(frozen=True, slots=True)
class ReplacementChoice:
    name: str
    duplicate_limited_name: str | None = None


def append_extended_replacement_rows(
    *,
    row: NormalizedSourceRow,
    option_rows: tuple[NormalizedSourceRow, ...],
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    wargear_ids_by_name: dict[str, str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> bool:
    description = _required_field(row, "description", error_type=error_type)
    named_match = NAMED_MODEL_REPLACEMENT_WITH_CHOICES_RE.fullmatch(description)
    if named_match is not None:
        _append_named_model_replacement_rows(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_id=_required_model_profile_id(
                model_profile_by_name,
                named_match.group("model"),
                error_type=error_type,
            ),
            wargear_ids_by_name=wargear_ids_by_name,
            match=named_match,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    scaled_match = SCALED_MODEL_REPLACEMENT_WITH_PAIRED_CHOICES_RE.fullmatch(description)
    restriction_match = SCALED_OPTION_DUPLICATE_RESTRICTION_RE.fullmatch(description)
    if scaled_match is None and restriction_match is None:
        return False
    scaled_rows = tuple(
        candidate
        for candidate in option_rows
        if SCALED_MODEL_REPLACEMENT_WITH_PAIRED_CHOICES_RE.fullmatch(
            _required_field(candidate, "description", error_type=error_type)
        )
        is not None
    )
    restriction_rows = tuple(
        candidate
        for candidate in option_rows
        if SCALED_OPTION_DUPLICATE_RESTRICTION_RE.fullmatch(
            _required_field(candidate, "description", error_type=error_type)
        )
        is not None
    )
    if len(scaled_rows) != 1 or len(restriction_rows) != 1:
        raise error_type(
            "Scaled wargear options require one option row and one duplicate restriction row."
        )
    if restriction_match is not None:
        return True
    if scaled_match is None:
        raise error_type("Scaled wargear option row is malformed.")
    _append_scaled_model_replacement_rows(
        row=row,
        restriction_row=restriction_rows[0],
        datasheet_id=datasheet_id,
        model_profile_id=_required_model_profile_id(
            model_profile_by_name,
            scaled_match.group("model"),
            error_type=error_type,
        ),
        wargear_ids_by_name=wargear_ids_by_name,
        match=scaled_match,
        bridged_rows=bridged_rows,
        error_type=error_type,
    )
    return True


def _append_named_model_replacement_rows(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_id: str,
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    replaced_wargear_id = _required_wargear_id(
        wargear_ids_by_name,
        match.group("replaced"),
        error_type=error_type,
    )
    choice_ids = tuple(
        _required_wargear_id(wargear_ids_by_name, choice.name, error_type=error_type)
        for choice in replacement_choices(match.group("choices"), error_type=error_type)
    )
    source_line = _required_field(row, "line", error_type=error_type)
    option_id = (
        f"{datasheet_id}:{_name_key(match.group('model'), error_type=error_type)}-replacement:"
        f"option-{source_line}"
    )
    common_fields = {
        "datasheet_id": datasheet_id,
        "description": _raw_or_field(row, "description"),
        "option_id": option_id,
        "model_profile_id": model_profile_id,
        "default_wargear_ids": "",
        "allowed_wargear_ids": ",".join(choice_ids),
        "min_selections": "0",
        "max_selections": "1",
        "condition_kind": "",
        "condition_wargear_ids": "",
        "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
        "effect_replaced_wargear_id": replaced_wargear_id,
        "effect_model_count": "1",
        "effect_wargear_count": "1",
        "source_ids": ",".join(_source_ids(row)),
    }
    bridged_rows["Datasheets_options"].extend(
        {
            **common_fields,
            "line": f"{source_line}.{choice_index}",
            "effect_wargear_id": choice_id,
        }
        for choice_index, choice_id in enumerate(choice_ids, start=1)
    )


def _append_scaled_model_replacement_rows(
    *,
    row: NormalizedSourceRow,
    restriction_row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_id: str,
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    restriction_match = SCALED_OPTION_DUPLICATE_RESTRICTION_RE.fullmatch(
        _required_field(restriction_row, "description", error_type=error_type)
    )
    if restriction_match is None:
        raise error_type("Scaled wargear duplicate restriction row is malformed.")
    models_per_increment = _positive_int(
        match.group("models_per_increment"),
        field_name="scaled wargear models per increment",
        error_type=error_type,
    )
    max_per_increment = _positive_int(
        match.group("max_per_increment"),
        field_name="scaled wargear maximum per increment",
        error_type=error_type,
    )
    threshold = _positive_int(
        restriction_match.group("threshold"),
        field_name="scaled wargear duplicate threshold",
        error_type=error_type,
    )
    max_duplicates = _positive_count(
        restriction_match.group("max_duplicates"),
        field_name="scaled wargear duplicate maximum",
        error_type=error_type,
    )
    if threshold != models_per_increment * 2 or max_duplicates != 2:
        raise error_type("Unsupported scaled wargear duplicate restriction semantics.")
    choices = tuple(
        _paired_replacement_choice(line, error_type=error_type)
        for line in match.group("choices").splitlines()
        if line.strip()
    )
    if not choices:
        raise error_type("Scaled wargear option has no paired choices.")
    replaced_ids = (
        _required_wargear_id(
            wargear_ids_by_name,
            match.group("replaced_first"),
            error_type=error_type,
        ),
        _required_wargear_id(
            wargear_ids_by_name,
            match.group("replaced_second"),
            error_type=error_type,
        ),
    )
    source_line = _required_field(row, "line", error_type=error_type)
    selection_group_id = f"{datasheet_id}:scaled-replacement-option-{source_line}"
    for choice_index, (first_name, second_name) in enumerate(choices, start=1):
        choice_ids = tuple(
            _required_wargear_id(wargear_ids_by_name, name, error_type=error_type)
            for name in (first_name, second_name)
        )
        option_id = (
            f"{datasheet_id}:{_name_key(first_name, error_type=error_type)}-"
            f"{_name_key(second_name, error_type=error_type)}:option-{source_line}"
        )
        common_fields = {
            "datasheet_id": datasheet_id,
            "description": _raw_or_field(row, "description"),
            "option_id": option_id,
            "model_profile_id": model_profile_id,
            "default_wargear_ids": "",
            "allowed_wargear_ids": ",".join(choice_ids),
            "min_selections": "0",
            "max_selections": "2",
            "condition_kind": "",
            "condition_wargear_ids": "",
            "selection_group_id": selection_group_id,
            "selection_models_per_increment": str(models_per_increment),
            "selection_group_max_per_increment": str(max_per_increment),
            "selection_option_max_per_increment": "1",
            "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
            "effect_model_count": "1",
            "effect_wargear_count": "1",
            "source_ids": ",".join(_source_ids(row, restriction_row)),
        }
        bridged_rows["Datasheets_options"].extend(
            {
                **common_fields,
                "line": f"{source_line}.{choice_index}.{effect_index}",
                "effect_wargear_id": choice_id,
                "effect_replaced_wargear_id": replaced_id,
            }
            for effect_index, (choice_id, replaced_id) in enumerate(
                zip(choice_ids, replaced_ids, strict=True),
                start=1,
            )
        )


def replacement_choices(
    choices_text: str, *, error_type: type[ValueError]
) -> tuple[ReplacementChoice, ...]:
    choices: list[ReplacementChoice] = []
    for line in choices_text.splitlines():
        match = OPTION_CHOICE_RE.fullmatch(line.strip())
        if match is None:
            raise error_type("Unsupported replacement wargear choice row shape.")
        choices.append(_replacement_choice(match.group("name"), error_type=error_type))
    if not choices:
        raise error_type("Replacement wargear option has no choices.")
    return tuple(choices)


def _replacement_choice(choice_text: str, *, error_type: type[ValueError]) -> ReplacementChoice:
    restriction_match = OPTION_CHOICE_RESTRICTION_RE.fullmatch(choice_text)
    if restriction_match is None:
        return ReplacementChoice(name=choice_text)
    name = restriction_match.group("name")
    duplicate_match = DUPLICATE_EQUIPMENT_RESTRICTION_RE.fullmatch(
        restriction_match.group("restriction")
    )
    if duplicate_match is None:
        raise error_type("Unsupported replacement wargear choice restriction.")
    duplicate_name = duplicate_match.group("name")
    if _name_key(duplicate_name, error_type=error_type) != _name_key(
        name,
        error_type=error_type,
    ):
        raise error_type("Replacement wargear duplicate restriction target drift.")
    return ReplacementChoice(name=name, duplicate_limited_name=duplicate_name)


def _paired_replacement_choice(
    choice_text: str, *, error_type: type[ValueError]
) -> tuple[str, str]:
    match = PAIRED_OPTION_CHOICE_RE.fullmatch(choice_text.strip())
    if match is None:
        raise error_type("Unsupported paired replacement wargear choice row shape.")
    return match.group("first"), match.group("second")


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


def _source_ids(*rows: NormalizedSourceRow) -> tuple[str, ...]:
    source_ids: list[str] = []
    for row in rows:
        source_ids.append(row.stable_source_id())
        explicit_source_ids = row.runtime_fields_payload().get("source_ids")
        if explicit_source_ids is not None:
            source_ids.extend(
                item.strip() for item in explicit_source_ids.split(",") if item.strip()
            )
    return tuple(dict.fromkeys(source_ids))


def _required_model_profile_id(
    model_profile_by_name: dict[str, str],
    model_name: str,
    *,
    error_type: type[ValueError],
) -> str:
    model_profile_id = model_profile_by_name.get(_name_key(model_name, error_type=error_type))
    if model_profile_id is None:
        raise error_type("Wargear option references an unknown model profile.")
    return model_profile_id


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


def _positive_count(value: str, *, field_name: str, error_type: type[ValueError]) -> int:
    count = COUNT_WORDS.get(" ".join(value.casefold().strip().split()))
    if count is not None:
        return count
    return _positive_int(value, field_name=field_name, error_type=error_type)


def _positive_int(value: str, *, field_name: str, error_type: type[ValueError]) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise error_type(f"{field_name} must be an integer.") from exc
    if result < 1:
        raise error_type(f"{field_name} must be at least 1.")
    return result


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
