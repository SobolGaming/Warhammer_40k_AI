from __future__ import annotations

import re

from warhammer40k_core.core.datasheet import WargearOptionEffectKind
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow
from warhammer40k_core.rules.wahapedia_wargear_option_bridge_support import (
    name_key,
    option_common,
    positive_count,
    required_field,
    required_model_profile_id,
    required_wargear_id,
)

_ALL_MODELS_PAIRED_REPLACEMENT_RE = re.compile(
    r"^All of the models in this unit can each have their (?P<replaced>.+?) replaced with "
    r"1 (?P<replacement_first>.+?) and 1 (?P<replacement_second>.+?)\.$",
    re.IGNORECASE,
)
_THIS_MODEL_PAIRED_REPLACEMENT_RE = re.compile(
    r"^This model's (?P<replaced>.+?) can be replaced with "
    r"1 (?P<replacement_first>.+?) and 1 (?P<replacement_second>.+?)\.$",
    re.IGNORECASE,
)
_NAMED_MODEL_PAIRED_REPLACEMENT_RE = re.compile(
    r"^The (?P<model>.+?)(?: model)?'s (?P<replaced>.+?) can be replaced with "
    r"1 (?P<replacement_first>.+?) and 1 (?P<replacement_second>.+?)\.$",
    re.IGNORECASE,
)
_LIMITED_MODEL_SINGLE_REPLACEMENT_RE = re.compile(
    r"^Up to (?P<maximum>\w+) (?P<model>.+?) can each replace their "
    r"(?P<replaced>.+?) with 1 (?P<replacement>.+?)\.$",
    re.IGNORECASE,
)


def append_paired_replacement_option_rows(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    minimum_unit_models: int,
    maximum_unit_models: int,
    wargear_ids_by_name: dict[str, str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> bool:
    description = required_field(row, "description", error_type=error_type)
    all_models_match = _ALL_MODELS_PAIRED_REPLACEMENT_RE.fullmatch(description)
    if all_models_match is not None:
        if minimum_unit_models != maximum_unit_models:
            raise error_type("All-model paired replacement requires a fixed unit size.")
        _append_paired_replacement(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            model_name=None,
            model_count=maximum_unit_models,
            wargear_ids_by_name=wargear_ids_by_name,
            match=all_models_match,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    this_model_match = _THIS_MODEL_PAIRED_REPLACEMENT_RE.fullmatch(description)
    if this_model_match is not None:
        _append_paired_replacement(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            model_name=None,
            model_count=1,
            wargear_ids_by_name=wargear_ids_by_name,
            match=this_model_match,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    named_model_match = _NAMED_MODEL_PAIRED_REPLACEMENT_RE.fullmatch(description)
    if named_model_match is not None:
        _append_paired_replacement(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            model_name=named_model_match.group("model"),
            model_count=1,
            wargear_ids_by_name=wargear_ids_by_name,
            match=named_model_match,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    limited_model_match = _LIMITED_MODEL_SINGLE_REPLACEMENT_RE.fullmatch(description)
    if limited_model_match is None:
        return False
    _append_limited_model_replacement(
        row=row,
        datasheet_id=datasheet_id,
        model_profile_by_name=model_profile_by_name,
        minimum_unit_models=minimum_unit_models,
        wargear_ids_by_name=wargear_ids_by_name,
        match=limited_model_match,
        bridged_rows=bridged_rows,
        error_type=error_type,
    )
    return True


def _append_paired_replacement(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    model_name: str | None,
    model_count: int,
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    if model_name is None:
        model_profile_ids = tuple(sorted(set(model_profile_by_name.values())))
        if len(model_profile_ids) != 1:
            raise error_type("Generic paired replacement requires one model profile.")
        model_profile_id = model_profile_ids[0]
    else:
        model_profile_id = required_model_profile_id(
            model_profile_by_name,
            model_name,
            error_type=error_type,
        )
    replaced_id = required_wargear_id(
        wargear_ids_by_name,
        match.group("replaced"),
        error_type=error_type,
    )
    replacement_ids = tuple(
        required_wargear_id(
            wargear_ids_by_name,
            match.group(group),
            error_type=error_type,
        )
        for group in ("replacement_first", "replacement_second")
    )
    source_line = required_field(row, "line", error_type=error_type)
    common = option_common(
        row=row,
        datasheet_id=datasheet_id,
        option_id=(
            f"{datasheet_id}:{name_key(match.group('replacement_first'))}-"
            f"{name_key(match.group('replacement_second'))}:option-{source_line}"
        ),
        model_profile_id=model_profile_id,
        allowed_wargear_ids=replacement_ids,
        max_selections=2,
    )
    bridged_rows["Datasheets_options"].extend(
        (
            {
                **common,
                "line": f"{source_line}.1",
                "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
                "effect_wargear_id": replacement_ids[0],
                "effect_replaced_wargear_id": replaced_id,
                "effect_model_count": str(model_count),
                "effect_wargear_count": "1",
            },
            {
                **common,
                "line": f"{source_line}.2",
                "effect_kind": WargearOptionEffectKind.ADD_WARGEAR.value,
                "effect_wargear_id": replacement_ids[1],
                "effect_replaced_wargear_id": "",
                "effect_model_count": str(model_count),
                "effect_wargear_count": "1",
            },
        )
    )


def _append_limited_model_replacement(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    minimum_unit_models: int,
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    model_profile_id = required_model_profile_id(
        model_profile_by_name,
        match.group("model"),
        error_type=error_type,
    )
    replaced_id = required_wargear_id(
        wargear_ids_by_name,
        match.group("replaced"),
        error_type=error_type,
    )
    replacement_id = required_wargear_id(
        wargear_ids_by_name,
        match.group("replacement"),
        error_type=error_type,
    )
    maximum = positive_count(
        match.group("maximum"),
        field_name="limited replacement maximum",
        error_type=error_type,
    )
    source_line = required_field(row, "line", error_type=error_type)
    bridged_rows["Datasheets_options"].append(
        {
            **option_common(
                row=row,
                datasheet_id=datasheet_id,
                option_id=(
                    f"{datasheet_id}:{name_key(match.group('replaced'))}-"
                    f"{name_key(match.group('replacement'))}:option-{source_line}"
                ),
                model_profile_id=model_profile_id,
                allowed_wargear_ids=(replacement_id,),
                max_selections=maximum,
            ),
            "line": source_line,
            "selection_group_id": (
                f"{datasheet_id}:limited-model-replacement-option-{source_line}"
            ),
            "selection_models_per_increment": str(minimum_unit_models),
            "selection_group_max_per_increment": str(maximum),
            "selection_option_max_per_increment": str(maximum),
            "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
            "effect_wargear_id": replacement_id,
            "effect_replaced_wargear_id": replaced_id,
            "effect_model_count": "1",
            "effect_wargear_count": "1",
        }
    )
