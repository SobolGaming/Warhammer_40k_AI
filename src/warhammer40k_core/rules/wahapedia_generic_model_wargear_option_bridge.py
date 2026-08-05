from __future__ import annotations

import re

from warhammer40k_core.core.datasheet import WargearOptionEffectKind
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow
from warhammer40k_core.rules.wahapedia_wargear_option_bridge_support import (
    name_key,
    option_common,
    positive_count,
    required_field,
    required_wargear_id,
)

_GENERIC_MODEL_SINGLE_REPLACEMENT_RE = re.compile(
    r"^(?P<maximum>\d+) models?'s (?P<replaced>.+?) can be replaced with "
    r"1 (?P<replacement>.+?)\.$",
    re.IGNORECASE,
)
_GENERIC_MODEL_MULTIPLE_REPLACEMENT_RE = re.compile(
    r"^(?P<maximum>\d+) models?'s (?P<replaced>.+? and .+?) can be replaced with "
    r"1 (?P<replacement>.+?)\.$",
    re.IGNORECASE,
)
_GENERIC_MODELS_LIMITED_REPLACEMENT_RE = re.compile(
    r"^Up to (?P<maximum>\w+) models can each have their (?P<replaced>.+?) replaced "
    r"with 1 (?P<replacement>.+?)\.$",
    re.IGNORECASE,
)


def append_generic_model_replacement_rows(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_ids: tuple[str, ...],
    max_models_by_profile_id: dict[str, int],
    minimum_unit_models: int,
    maximum_unit_models: int,
    wargear_ids_by_name: dict[str, str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> bool:
    description = required_field(row, "description", error_type=error_type)
    multiple_match = _GENERIC_MODEL_MULTIPLE_REPLACEMENT_RE.fullmatch(description)
    single_match = _GENERIC_MODEL_SINGLE_REPLACEMENT_RE.fullmatch(description)
    limited_match = _GENERIC_MODELS_LIMITED_REPLACEMENT_RE.fullmatch(description)
    match = multiple_match or single_match or limited_match
    if match is None:
        return False
    if minimum_unit_models != maximum_unit_models:
        raise error_type("Generic counted model replacement requires a fixed unit size.")
    maximum = positive_count(
        match.group("maximum"),
        field_name="generic model replacement maximum",
        error_type=error_type,
    )
    if maximum > maximum_unit_models:
        raise error_type("Generic model replacement maximum exceeds unit size.")
    replaced_names = tuple(name.strip() for name in match.group("replaced").split(" and "))
    if (multiple_match is None) == (len(replaced_names) != 1):
        raise error_type("Generic model replacement wargear shape drifted.")
    _append_generic_model_replacements(
        row=row,
        datasheet_id=datasheet_id,
        model_profile_ids=model_profile_ids,
        max_models_by_profile_id=max_models_by_profile_id,
        unit_models=maximum_unit_models,
        maximum=maximum,
        replaced_names=replaced_names,
        replacement_name=match.group("replacement"),
        wargear_ids_by_name=wargear_ids_by_name,
        bridged_rows=bridged_rows,
        error_type=error_type,
    )
    return True


def _append_generic_model_replacements(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_ids: tuple[str, ...],
    max_models_by_profile_id: dict[str, int],
    unit_models: int,
    maximum: int,
    replaced_names: tuple[str, ...],
    replacement_name: str,
    wargear_ids_by_name: dict[str, str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    profile_ids = tuple(sorted(set(model_profile_ids)))
    if not profile_ids:
        raise error_type("Generic model replacement requires model profiles.")
    replacement_id = required_wargear_id(
        wargear_ids_by_name,
        replacement_name,
        error_type=error_type,
    )
    replaced_ids = tuple(
        required_wargear_id(wargear_ids_by_name, name, error_type=error_type)
        for name in replaced_names
    )
    source_line = required_field(row, "line", error_type=error_type)
    selection_group_id = f"{datasheet_id}:generic-model-replacement-option-{source_line}"
    for profile_index, model_profile_id in enumerate(profile_ids, start=1):
        profile_maximum = min(maximum, max_models_by_profile_id[model_profile_id])
        if profile_maximum < 1:
            continue
        common = {
            **option_common(
                row=row,
                datasheet_id=datasheet_id,
                option_id=(
                    f"{datasheet_id}:{name_key(replacement_name)}-"
                    f"{name_key(model_profile_id.rsplit(':', maxsplit=1)[-1])}:"
                    f"option-{source_line}"
                ),
                model_profile_id=model_profile_id,
                allowed_wargear_ids=(replacement_id,),
                max_selections=profile_maximum,
            ),
            "selection_group_id": selection_group_id,
            "selection_models_per_increment": str(unit_models),
            "selection_group_max_per_increment": str(maximum),
            "selection_option_max_per_increment": str(profile_maximum),
        }
        effects = [
            {
                **common,
                "line": f"{source_line}.{profile_index}.1",
                "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
                "effect_wargear_id": replacement_id,
                "effect_replaced_wargear_id": replaced_ids[0],
                "effect_model_count": "1",
                "effect_wargear_count": "1",
            }
        ]
        effects.extend(
            {
                **common,
                "line": f"{source_line}.{profile_index}.{effect_index}",
                "effect_kind": WargearOptionEffectKind.REMOVE_WARGEAR_IF_SELECTED.value,
                "effect_wargear_id": replacement_id,
                "effect_replaced_wargear_id": replaced_id,
                "effect_model_count": "1",
                "effect_wargear_count": "0",
            }
            for effect_index, replaced_id in enumerate(replaced_ids[1:], start=2)
        )
        bridged_rows["Datasheets_options"].extend(effects)
