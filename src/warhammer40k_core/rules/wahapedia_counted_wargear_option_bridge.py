from __future__ import annotations

import re

from warhammer40k_core.core.datasheet import WargearOptionEffectKind
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow
from warhammer40k_core.rules.wahapedia_wargear_option_bridge_support import (
    name_key as _name_key,
)
from warhammer40k_core.rules.wahapedia_wargear_option_bridge_support import (
    option_common as _option_common,
)
from warhammer40k_core.rules.wahapedia_wargear_option_bridge_support import (
    positive_count as _positive_count,
)
from warhammer40k_core.rules.wahapedia_wargear_option_bridge_support import (
    required_field as _required_field,
)
from warhammer40k_core.rules.wahapedia_wargear_option_bridge_support import (
    required_model_profile_id as _required_model_profile_id,
)
from warhammer40k_core.rules.wahapedia_wargear_option_bridge_support import (
    required_wargear_id as _required_wargear_id,
)

_COUNTED_NAMED_ADDITIVE_RE = re.compile(
    r"^(?P<max_selections>\d+) (?P<model>.+?) can be equipped with "
    r"(?P<wargear_count>\d+) (?P<granted>.+?)\.$",
    re.IGNORECASE,
)
_SCALED_SINGLE_REPLACEMENT_RE = re.compile(
    r"^For every (?P<models_per_increment>\d+) models in this unit, "
    r"(?P<max_per_increment>\d+) (?P<model>.+?)'s (?P<replaced>.+?) "
    r"can be replaced with (?P<replacement_count>\d+) (?P<replacement>.+?)\.$",
    re.IGNORECASE,
)


def append_counted_wargear_option_rows(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    maximum_unit_models: int,
    wargear_ids_by_name: dict[str, str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> bool:
    description = _required_field(row, "description", error_type=error_type)
    scaled_replacement = _SCALED_SINGLE_REPLACEMENT_RE.fullmatch(description)
    if scaled_replacement is not None:
        _append_scaled_single_replacement(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            maximum_unit_models=maximum_unit_models,
            wargear_ids_by_name=wargear_ids_by_name,
            match=scaled_replacement,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    counted_additive = _COUNTED_NAMED_ADDITIVE_RE.fullmatch(description)
    if counted_additive is None or _has_embedded_condition(counted_additive.group("model")):
        return False
    _append_counted_additive(
        row=row,
        datasheet_id=datasheet_id,
        model_profile_by_name=model_profile_by_name,
        wargear_ids_by_name=wargear_ids_by_name,
        match=counted_additive,
        bridged_rows=bridged_rows,
        error_type=error_type,
    )
    return True


def _has_embedded_condition(model_text: str) -> bool:
    normalized = model_text.casefold()
    return any(token in normalized for token in (" equipped ", " that ", " not ", " in this unit"))


def _append_counted_additive(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    max_selections = _positive_count(
        match.group("max_selections"),
        field_name="Counted additive maximum",
        error_type=error_type,
    )
    wargear_count = _positive_count(
        match.group("wargear_count"),
        field_name="Counted additive wargear count",
        error_type=error_type,
    )
    granted_id = _required_wargear_id(
        wargear_ids_by_name, match.group("granted"), error_type=error_type
    )
    source_line = _required_field(row, "line", error_type=error_type)
    bridged_rows["Datasheets_options"].append(
        {
            **_option_common(
                row=row,
                datasheet_id=datasheet_id,
                option_id=f"{datasheet_id}:{_name_key(match.group('granted'))}:option-{source_line}",
                model_profile_id=_required_model_profile_id(
                    model_profile_by_name, match.group("model"), error_type=error_type
                ),
                allowed_wargear_ids=(granted_id,),
                max_selections=max_selections,
            ),
            "line": source_line,
            "effect_kind": WargearOptionEffectKind.ADD_WARGEAR.value,
            "effect_wargear_id": granted_id,
            "effect_replaced_wargear_id": "",
            "effect_model_count": "1",
            "effect_wargear_count": str(wargear_count),
        }
    )


def _append_scaled_single_replacement(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    maximum_unit_models: int,
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    models_per_increment = _positive_count(
        match.group("models_per_increment"),
        field_name="Scaled replacement models per increment",
        error_type=error_type,
    )
    max_per_increment = _positive_count(
        match.group("max_per_increment"),
        field_name="Scaled replacement maximum per increment",
        error_type=error_type,
    )
    replacement_count = _positive_count(
        match.group("replacement_count"),
        field_name="Scaled replacement wargear count",
        error_type=error_type,
    )
    replaced_id = _required_wargear_id(
        wargear_ids_by_name, match.group("replaced"), error_type=error_type
    )
    replacement_id = _required_wargear_id(
        wargear_ids_by_name, match.group("replacement"), error_type=error_type
    )
    source_line = _required_field(row, "line", error_type=error_type)
    max_selections = (maximum_unit_models // models_per_increment) * max_per_increment
    if max_selections < 1:
        raise error_type("Scaled replacement is unavailable at maximum unit size.")
    bridged_rows["Datasheets_options"].append(
        {
            **_option_common(
                row=row,
                datasheet_id=datasheet_id,
                option_id=(
                    f"{datasheet_id}:{_name_key(match.group('replaced'))}-"
                    f"{_name_key(match.group('replacement'))}:option-{source_line}"
                ),
                model_profile_id=_required_model_profile_id(
                    model_profile_by_name, match.group("model"), error_type=error_type
                ),
                allowed_wargear_ids=(replacement_id,),
                max_selections=max_selections,
            ),
            "line": source_line,
            "selection_group_id": f"{datasheet_id}:scaled-replacement-option-{source_line}",
            "selection_models_per_increment": str(models_per_increment),
            "selection_group_max_per_increment": str(max_per_increment),
            "selection_option_max_per_increment": str(max_per_increment),
            "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
            "effect_wargear_id": replacement_id,
            "effect_replaced_wargear_id": replaced_id,
            "effect_model_count": "1",
            "effect_wargear_count": str(replacement_count),
        }
    )
