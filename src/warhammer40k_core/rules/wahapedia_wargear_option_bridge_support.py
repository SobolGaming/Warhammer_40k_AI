from __future__ import annotations

import re
import unicodedata

from warhammer40k_core.rules.wahapedia_bridge_patterns import COUNT_WORDS
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


def positive_count(value: str, *, field_name: str, error_type: type[ValueError]) -> int:
    count = COUNT_WORDS.get(" ".join(value.casefold().strip().split()))
    if count is not None:
        return count
    try:
        count = int(value)
    except ValueError as exc:
        raise error_type(f"{field_name} must be a positive count.") from exc
    if count < 1:
        raise error_type(f"{field_name} must be positive.")
    return count


def option_common(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    option_id: str,
    model_profile_id: str,
    allowed_wargear_ids: tuple[str, ...],
    max_selections: int,
) -> dict[str, str]:
    return {
        "datasheet_id": datasheet_id,
        "description": raw_or_field(row, "description"),
        "option_id": option_id,
        "model_profile_id": model_profile_id,
        "default_wargear_ids": "",
        "allowed_wargear_ids": ",".join(allowed_wargear_ids),
        "min_selections": "0",
        "max_selections": str(max_selections),
        "condition_kind": "",
        "condition_wargear_ids": "",
        "selection_group_id": "",
        "selection_models_per_increment": "",
        "selection_group_max_per_increment": "",
        "selection_option_max_per_increment": "",
        "source_ids": ",".join(source_ids(row)),
    }


def required_model_profile_id(
    model_profile_by_name: dict[str, str],
    model_name: str,
    *,
    error_type: type[ValueError],
) -> str:
    profile_id = model_profile_by_name.get(name_key(model_name))
    if profile_id is None and name_key(model_name).endswith("s"):
        profile_id = model_profile_by_name.get(name_key(model_name)[:-1])
    if profile_id is None:
        raise error_type("Wargear option references an unknown model profile.")
    return profile_id


def required_wargear_id(
    wargear_ids_by_name: dict[str, str],
    wargear_name: str,
    *,
    error_type: type[ValueError],
) -> str:
    key = name_key(wargear_name)
    wargear_id = wargear_ids_by_name.get(key)
    if wargear_id is None and key.endswith("s"):
        wargear_id = wargear_ids_by_name.get(key[:-1])
    if wargear_id is None:
        raise error_type(f"Wargear option references an unknown wargear item: {wargear_name!r}.")
    return wargear_id


def required_field(
    row: NormalizedSourceRow,
    column_name: str,
    *,
    error_type: type[ValueError],
) -> str:
    value = row.runtime_fields_payload().get(column_name)
    if value is None:
        raise error_type(f"Required source column is missing: {column_name}.")
    stripped = value.strip()
    if not stripped:
        raise error_type(f"Required source column is empty: {column_name}.")
    return stripped


def raw_or_field(row: NormalizedSourceRow, column_name: str) -> str:
    for text_field in row.text_fields:
        if text_field.column_name == column_name:
            return text_field.raw_text
    return row.runtime_fields_payload().get(column_name, "")


def source_ids(row: NormalizedSourceRow) -> tuple[str, ...]:
    values = [row.stable_source_id()]
    explicit_source_ids = row.runtime_fields_payload().get("source_ids")
    if explicit_source_ids is not None:
        values.extend(item.strip() for item in explicit_source_ids.split(",") if item.strip())
    return tuple(dict.fromkeys(values))


def name_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    lowered = normalized.casefold().replace("'", "").replace("&", " and ")
    return "-".join(part for part in re.split(r"[^a-z0-9]+", lowered) if part)
