from __future__ import annotations

import re

from warhammer40k_core.core.datasheet import (
    WargearOptionConditionKind,
    WargearOptionEffectKind,
)
from warhammer40k_core.rules.wahapedia_loadout_bridge import LoadoutAssignments
from warhammer40k_core.rules.wahapedia_replacement_option_bridge import replacement_choices
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

NAMED_REPLACEMENT_CHOICES_RE = re.compile(
    r"^The (?P<model>.+?)(?: model)?'s (?P<replaced>.+?) can be replaced with "
    r"(?:one|1) of the following:\n"
    r"(?P<choices>(?:- 1 .+?(?:\n|$))+)$",
    re.IGNORECASE,
)
NAMED_REPLACEMENT_WITH_REQUIRED_CHOICES_RE = re.compile(
    r"^The (?P<model>.+?)(?: model)?'s (?P<replaced>.+?) can be replaced with "
    r"1 (?P<required>.+?) and one of the following:\n"
    r"(?P<choices>(?:- 1 .+?(?:\n|$))+)$",
    re.IGNORECASE,
)
NAMED_MULTIPLE_SINGLE_REPLACEMENT_RE = re.compile(
    r"^The (?P<model>.+?)(?: model)?'s (?P<replaced>.+?) can be replaced with "
    r"1 (?P<replacement>.+?)\.$",
    re.IGNORECASE,
)
NAMED_ADDITIVE_RE = re.compile(
    r"^The (?P<model>.+?) can be equipped with(?::\n-)? 1 (?P<granted>.+?)\.?$",
    re.IGNORECASE,
)
ANY_NUMBER_REPLACEMENT_CHOICES_RE = re.compile(
    r"^Any number of (?P<model>.+?)(?: in this unit)? can each have their "
    r"(?P<replaced>.+?) replaced with one of the following:\n"
    r"(?P<choices>(?:- 1 .+?(?:\n|$))+)$",
    re.IGNORECASE,
)
ANY_NUMBER_SINGLE_REPLACEMENT_RE = re.compile(
    r"^Any number of (?P<model>.+?)(?: in this unit)? can each have their "
    r"(?P<replaced>.+?) replaced with 1 (?P<replacement>.+?)\.$",
    re.IGNORECASE,
)
ANY_NUMBER_PAIRED_REPLACEMENT_RE = re.compile(
    r"^Any number of (?P<model>.+?)(?: in this unit)? can each have their "
    r"(?P<replaced_first>.+?) and (?P<replaced_second>.+?) replaced with 1 "
    r"(?P<replacement>.+?)\.$",
    re.IGNORECASE,
)
ALL_MODELS_PAIRED_REPLACEMENT_RE = re.compile(
    r"^All of the models in this unit can each have their (?P<replaced>.+?) replaced with "
    r"1 (?P<replacement_first>.+?) and 1 (?P<replacement_second>.+?)\.$",
    re.IGNORECASE,
)
SCALED_ALTERNATIVE_REPLACEMENT_RE = re.compile(
    r"^For every (?P<models_per_increment>\d+) models in this unit, "
    r"(?P<max_per_increment>\d+) (?P<model>.+?)'s (?P<replaced_first>.+?)"
    r"(?: or (?P<replaced_second>.+?))? can be replaced with one of the following:\n"
    r"(?P<choices>(?:- 1 .+?(?:\n|$))+)$",
    re.IGNORECASE,
)
UNIT_SIZE_REPLACEMENT_RE = re.compile(
    r"^If this unit contains (?P<unit_models>\d+) models, (?P<max_selections>\d+) "
    r"(?P<model>.+?)'s (?P<replaced>.+?) can be replaced with "
    r"(?:(?:one of the following:\n(?P<choices>(?:- 1 .+?(?:\n|$))+))|"
    r"(?:1 (?P<replacement>.+?)\.))$",
    re.IGNORECASE,
)
CONDITIONAL_ADDITIVE_RE = re.compile(
    r"^(?P<max_selections>\d+) (?P<model>.+?) model equipped with a (?P<required_first>.+?) "
    r"and (?P<required_second>.+?) can be equipped with 1 (?P<granted>.+?)\.$",
    re.IGNORECASE,
)
CONDITIONAL_SAME_WARGEAR_ADDITIVE_RE = re.compile(
    r"^If this unit's (?P<model>.+?) is equipped with 1 (?P<required>.+?), "
    r"it can be equipped with 1 additional (?P<granted>.+?)\.$",
    re.IGNORECASE,
)
EACH_MODEL_EQUIPPED_REPLACEMENT_CHOICES_RE = re.compile(
    r"^Each model can have each (?P<replaced>.+?) it is equipped with replaced with one of "
    r"the following:\n(?P<choices>(?:- 1 .+?(?:\n|$))+)$",
    re.IGNORECASE,
)
EACH_THIS_MODEL_SINGLE_REPLACEMENT_RE = re.compile(
    r"^Each of this model's (?P<replaced>.+?) can be replaced with 1 "
    r"(?P<replacement>.+?)\.$",
    re.IGNORECASE,
)
THIS_MODEL_UP_TO_ADDITIVE_CHOICES_RE = re.compile(
    r"^This model can be equipped with up to (?P<maximum>\w+) of the following:\n"
    r"(?P<choices>(?:- 1 .+?(?:\n|$))+)$",
    re.IGNORECASE,
)
THIS_MODEL_SINGLE_ADDITIVE_RE = re.compile(
    r"^This model can be equipped with 1 (?P<granted>.+?)\.$",
    re.IGNORECASE,
)
UNIT_RESOURCE_RE = re.compile(
    r"^For every (?P<models_per_increment>\d+) models in this unit, it can have "
    r"(?P<max_per_increment>\d+) (?P<resource_name>.+?)\.$",
    re.IGNORECASE,
)


def append_unit_wargear_option_rows(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    max_models_by_profile_id: dict[str, int],
    required_model_profile_ids: tuple[str, ...],
    minimum_unit_models: int,
    maximum_unit_models: int,
    resource_namespace: str,
    loadout_assignments: LoadoutAssignments | None,
    wargear_ids_by_name: dict[str, str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> bool:
    description = _required_field(row, "description", error_type=error_type)
    unit_resource = UNIT_RESOURCE_RE.fullmatch(description)
    if unit_resource is not None:
        _append_unit_resource_option(
            row=row,
            datasheet_id=datasheet_id,
            required_model_profile_ids=required_model_profile_ids,
            maximum_unit_models=maximum_unit_models,
            resource_namespace=resource_namespace,
            wargear_ids_by_name=wargear_ids_by_name,
            match=unit_resource,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    each_model_replacement = EACH_MODEL_EQUIPPED_REPLACEMENT_CHOICES_RE.fullmatch(description)
    if each_model_replacement is not None:
        _append_each_equipped_replacement_choices(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            max_models_by_profile_id=max_models_by_profile_id,
            loadout_assignments=loadout_assignments,
            wargear_ids_by_name=wargear_ids_by_name,
            match=each_model_replacement,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    each_this_model_replacement = EACH_THIS_MODEL_SINGLE_REPLACEMENT_RE.fullmatch(description)
    if each_this_model_replacement is not None:
        _append_each_equipped_single_replacement(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            max_models_by_profile_id=max_models_by_profile_id,
            loadout_assignments=loadout_assignments,
            wargear_ids_by_name=wargear_ids_by_name,
            match=each_this_model_replacement,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    additive_choices = THIS_MODEL_UP_TO_ADDITIVE_CHOICES_RE.fullmatch(description)
    if additive_choices is not None:
        _append_this_model_additive_choices(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            wargear_ids_by_name=wargear_ids_by_name,
            match=additive_choices,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    single_additive = THIS_MODEL_SINGLE_ADDITIVE_RE.fullmatch(description)
    if single_additive is not None:
        _append_this_model_single_additive(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            wargear_ids_by_name=wargear_ids_by_name,
            match=single_additive,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    named_replacement = NAMED_REPLACEMENT_CHOICES_RE.fullmatch(description)
    if named_replacement is not None:
        _append_named_replacement(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            wargear_ids_by_name=wargear_ids_by_name,
            match=named_replacement,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    named_required_replacement = NAMED_REPLACEMENT_WITH_REQUIRED_CHOICES_RE.fullmatch(description)
    if named_required_replacement is not None:
        _append_named_required_replacement(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            wargear_ids_by_name=wargear_ids_by_name,
            match=named_required_replacement,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    named_multiple_single_replacement = NAMED_MULTIPLE_SINGLE_REPLACEMENT_RE.fullmatch(description)
    if named_multiple_single_replacement is not None:
        replaced_names = _multiple_wargear_names(
            named_multiple_single_replacement.group("replaced")
        )
        if len(replaced_names) < 2:
            _append_named_single_replacement(
                row=row,
                datasheet_id=datasheet_id,
                model_profile_by_name=model_profile_by_name,
                wargear_ids_by_name=wargear_ids_by_name,
                match=named_multiple_single_replacement,
                bridged_rows=bridged_rows,
                error_type=error_type,
            )
            return True
        _append_named_multiple_replacement_choices(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_id=_required_model_profile_id(
                model_profile_by_name,
                named_multiple_single_replacement.group("model"),
                error_type=error_type,
            ),
            model_name=named_multiple_single_replacement.group("model"),
            replaced_names=replaced_names,
            choice_groups=((named_multiple_single_replacement.group("replacement"),),),
            wargear_ids_by_name=wargear_ids_by_name,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    named_additive = NAMED_ADDITIVE_RE.fullmatch(description)
    if named_additive is not None:
        _append_additive(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            wargear_ids_by_name=wargear_ids_by_name,
            match=named_additive,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    any_number_choices = ANY_NUMBER_REPLACEMENT_CHOICES_RE.fullmatch(description)
    if any_number_choices is not None:
        _append_any_number_replacement_choices(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            max_models_by_profile_id=max_models_by_profile_id,
            wargear_ids_by_name=wargear_ids_by_name,
            match=any_number_choices,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    paired_replacement = ANY_NUMBER_PAIRED_REPLACEMENT_RE.fullmatch(description)
    if paired_replacement is not None:
        _append_any_number_paired_replacement(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            max_models_by_profile_id=max_models_by_profile_id,
            wargear_ids_by_name=wargear_ids_by_name,
            match=paired_replacement,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    any_number_single = ANY_NUMBER_SINGLE_REPLACEMENT_RE.fullmatch(description)
    if any_number_single is not None:
        _append_any_number_single_replacement(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            max_models_by_profile_id=max_models_by_profile_id,
            wargear_ids_by_name=wargear_ids_by_name,
            match=any_number_single,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    all_models_paired = ALL_MODELS_PAIRED_REPLACEMENT_RE.fullmatch(description)
    if all_models_paired is not None:
        _append_all_models_paired_replacement(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            minimum_unit_models=minimum_unit_models,
            maximum_unit_models=maximum_unit_models,
            wargear_ids_by_name=wargear_ids_by_name,
            match=all_models_paired,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    scaled_replacement = SCALED_ALTERNATIVE_REPLACEMENT_RE.fullmatch(description)
    if scaled_replacement is not None:
        _append_scaled_alternative_replacements(
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
    unit_size_replacement = UNIT_SIZE_REPLACEMENT_RE.fullmatch(description)
    if unit_size_replacement is not None:
        _append_unit_size_replacements(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            wargear_ids_by_name=wargear_ids_by_name,
            match=unit_size_replacement,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    conditional_additive = CONDITIONAL_ADDITIVE_RE.fullmatch(description)
    if conditional_additive is not None:
        _append_conditional_additive(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            wargear_ids_by_name=wargear_ids_by_name,
            match=conditional_additive,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    conditional_same_additive = CONDITIONAL_SAME_WARGEAR_ADDITIVE_RE.fullmatch(description)
    if conditional_same_additive is not None:
        _append_conditional_same_wargear_additive(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_by_name=model_profile_by_name,
            wargear_ids_by_name=wargear_ids_by_name,
            match=conditional_same_additive,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return True
    return False


def _append_unit_resource_option(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    required_model_profile_ids: tuple[str, ...],
    maximum_unit_models: int,
    resource_namespace: str,
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    models_per_increment = int(match.group("models_per_increment"))
    max_per_increment = int(match.group("max_per_increment"))
    if models_per_increment < 1 or max_per_increment < 1:
        raise error_type("Unit-resource wargear option counts must be positive.")
    max_selections = (maximum_unit_models // models_per_increment) * max_per_increment
    if max_selections < 1:
        raise error_type("Unit-resource wargear option is unavailable at maximum unit size.")
    required_profiles = tuple(sorted(set(required_model_profile_ids)))
    if not required_profiles:
        raise error_type("Unit-resource wargear option requires a mandatory model profile.")
    resource_name = match.group("resource_name")
    wargear_id = _required_wargear_id(
        wargear_ids_by_name,
        resource_name,
        error_type=error_type,
    )
    source_line = _required_field(row, "line", error_type=error_type)
    resource_slug = _name_key(resource_name).replace("_", "-")
    namespace_slug = _name_key(resource_namespace).replace("_", "-")
    bridged_rows["Datasheets_options"].append(
        {
            **_option_common(
                row=row,
                datasheet_id=datasheet_id,
                option_id=f"{datasheet_id}:{resource_slug}:option-{source_line}",
                model_profile_id=required_profiles[0],
                allowed_wargear_ids=(wargear_id,),
                max_selections=1,
            ),
            "line": source_line,
            "selection_group_id": f"{datasheet_id}:unit-resource-option-{source_line}",
            "selection_models_per_increment": str(models_per_increment),
            "selection_group_max_per_increment": str(max_per_increment),
            "selection_option_max_per_increment": str(max_per_increment),
            "unit_resource_kind": f"{namespace_slug}:{resource_slug}",
            "unit_resource_amount_per_selection": "1",
        }
    )


def _append_each_equipped_replacement_choices(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    max_models_by_profile_id: dict[str, int],
    loadout_assignments: LoadoutAssignments | None,
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    model_profile_id = _single_model_profile_id(
        model_profile_by_name,
        error_type=error_type,
    )
    copies_per_model = _required_loadout_count(
        loadout_assignments=loadout_assignments,
        wargear_name=match.group("replaced"),
        model_profile_id=model_profile_id,
        error_type=error_type,
    )
    replaced_id = _required_wargear_id(
        wargear_ids_by_name,
        match.group("replaced"),
        error_type=error_type,
    )
    choices = replacement_choices(match.group("choices"), error_type=error_type)
    source_line = _required_field(row, "line", error_type=error_type)
    selection_group_id = f"{datasheet_id}:each-equipped-replacement-option-{source_line}"
    maximum = copies_per_model * max_models_by_profile_id[model_profile_id]
    for choice_index, choice in enumerate(choices, start=1):
        choice_id = _required_wargear_id(
            wargear_ids_by_name,
            choice.name,
            error_type=error_type,
        )
        bridged_rows["Datasheets_options"].append(
            {
                **_option_common(
                    row=row,
                    datasheet_id=datasheet_id,
                    option_id=(
                        f"{datasheet_id}:{_name_key(match.group('replaced'))}-"
                        f"{_name_key(choice.name)}:option-{source_line}"
                    ),
                    model_profile_id=model_profile_id,
                    allowed_wargear_ids=(choice_id,),
                    max_selections=maximum,
                ),
                "line": f"{source_line}.{choice_index}",
                **_selection_limit_fields(
                    selection_group_id=selection_group_id,
                    group_max_per_model=copies_per_model,
                    option_max_per_model=copies_per_model,
                ),
                "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
                "effect_wargear_id": choice_id,
                "effect_replaced_wargear_id": replaced_id,
                "effect_model_count": "1",
                "effect_wargear_count": "1",
            }
        )


def _append_each_equipped_single_replacement(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    max_models_by_profile_id: dict[str, int],
    loadout_assignments: LoadoutAssignments | None,
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    model_profile_id = _single_model_profile_id(
        model_profile_by_name,
        error_type=error_type,
    )
    copies_per_model = _required_loadout_count(
        loadout_assignments=loadout_assignments,
        wargear_name=match.group("replaced"),
        model_profile_id=model_profile_id,
        error_type=error_type,
    )
    replaced_id = _required_wargear_id(
        wargear_ids_by_name,
        match.group("replaced"),
        error_type=error_type,
    )
    replacement_id = _required_wargear_id(
        wargear_ids_by_name,
        match.group("replacement"),
        error_type=error_type,
    )
    source_line = _required_field(row, "line", error_type=error_type)
    selection_group_id = f"{datasheet_id}:each-equipped-replacement-option-{source_line}"
    bridged_rows["Datasheets_options"].append(
        {
            **_option_common(
                row=row,
                datasheet_id=datasheet_id,
                option_id=(
                    f"{datasheet_id}:{_name_key(match.group('replaced'))}-"
                    f"{_name_key(match.group('replacement'))}:option-{source_line}"
                ),
                model_profile_id=model_profile_id,
                allowed_wargear_ids=(replacement_id,),
                max_selections=(copies_per_model * max_models_by_profile_id[model_profile_id]),
            ),
            "line": source_line,
            **_selection_limit_fields(
                selection_group_id=selection_group_id,
                group_max_per_model=copies_per_model,
                option_max_per_model=copies_per_model,
            ),
            "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
            "effect_wargear_id": replacement_id,
            "effect_replaced_wargear_id": replaced_id,
            "effect_model_count": "1",
            "effect_wargear_count": "1",
        }
    )


def _append_this_model_additive_choices(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    maximum = _positive_count(
        match.group("maximum"),
        field_name="this-model additive maximum",
        error_type=error_type,
    )
    model_profile_id = _single_model_profile_id(
        model_profile_by_name,
        error_type=error_type,
    )
    choices = replacement_choices(match.group("choices"), error_type=error_type)
    choice_ids = tuple(
        _required_wargear_id(
            wargear_ids_by_name,
            choice.name,
            error_type=error_type,
        )
        for choice in choices
    )
    source_line = _required_field(row, "line", error_type=error_type)
    common = {
        **_option_common(
            row=row,
            datasheet_id=datasheet_id,
            option_id=f"{datasheet_id}:additive-choice:option-{source_line}",
            model_profile_id=model_profile_id,
            allowed_wargear_ids=choice_ids,
            max_selections=maximum,
        ),
        **_selection_limit_fields(
            selection_group_id=f"{datasheet_id}:additive-choice-option-{source_line}",
            group_max_per_model=maximum,
            option_max_per_model=maximum,
        ),
    }
    bridged_rows["Datasheets_options"].extend(
        {
            **common,
            "line": f"{source_line}.{choice_index}",
            "effect_kind": WargearOptionEffectKind.ADD_WARGEAR_IF_SELECTED.value,
            "effect_wargear_id": choice_id,
            "effect_replaced_wargear_id": "",
            "effect_model_count": "1",
            "effect_wargear_count": "1",
        }
        for choice_index, choice_id in enumerate(choice_ids, start=1)
    )


def _append_this_model_single_additive(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    granted_id = _required_wargear_id(
        wargear_ids_by_name,
        match.group("granted"),
        error_type=error_type,
    )
    source_line = _required_field(row, "line", error_type=error_type)
    bridged_rows["Datasheets_options"].append(
        {
            **_option_common(
                row=row,
                datasheet_id=datasheet_id,
                option_id=f"{datasheet_id}:{_name_key(match.group('granted'))}:option-{source_line}",
                model_profile_id=_single_model_profile_id(
                    model_profile_by_name,
                    error_type=error_type,
                ),
                allowed_wargear_ids=(granted_id,),
                max_selections=1,
            ),
            "line": source_line,
            "effect_kind": WargearOptionEffectKind.ADD_WARGEAR.value,
            "effect_wargear_id": granted_id,
            "effect_replaced_wargear_id": "",
            "effect_model_count": "1",
            "effect_wargear_count": "1",
        }
    )


def _single_model_profile_id(
    model_profile_by_name: dict[str, str],
    *,
    error_type: type[ValueError],
) -> str:
    profile_ids = tuple(sorted(set(model_profile_by_name.values())))
    if len(profile_ids) != 1:
        raise error_type("This-model wargear option requires one model profile.")
    return profile_ids[0]


def _required_loadout_count(
    *,
    loadout_assignments: LoadoutAssignments | None,
    wargear_name: str,
    model_profile_id: str,
    error_type: type[ValueError],
) -> int:
    if loadout_assignments is None:
        raise error_type("Each-equipped replacement requires structured default loadout.")
    count = loadout_assignments.count_for(
        wargear_name,
        model_profile_id=model_profile_id,
    )
    if count < 1:
        raise error_type("Each-equipped replacement target is absent from default loadout.")
    return count


def _selection_limit_fields(
    *,
    selection_group_id: str,
    group_max_per_model: int,
    option_max_per_model: int,
) -> dict[str, str]:
    return {
        "selection_group_id": selection_group_id,
        "selection_models_per_increment": "1",
        "selection_group_max_per_increment": str(group_max_per_model),
        "selection_option_max_per_increment": str(option_max_per_model),
    }


def _append_named_replacement(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    model_profile_id = _required_model_profile_id(
        model_profile_by_name, match.group("model"), error_type=error_type
    )
    replaced_names = _multiple_wargear_names(match.group("replaced"))
    replaced_name = next(iter(replaced_names), None)
    if replaced_name is None:
        raise error_type("Named replacement must identify replaced wargear.")
    choices = replacement_choices(match.group("choices"), error_type=error_type)
    choice_groups = tuple(_replacement_choice_wargear_names(choice.name) for choice in choices)
    source_line = _required_field(row, "line", error_type=error_type)
    if len(replaced_names) > 1:
        _append_named_multiple_replacement_choices(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_id=model_profile_id,
            model_name=match.group("model"),
            replaced_names=replaced_names,
            choice_groups=choice_groups,
            wargear_ids_by_name=wargear_ids_by_name,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return
    replaced_id = _required_wargear_id(wargear_ids_by_name, replaced_name, error_type=error_type)
    if any(len(choice_group) > 1 for choice_group in choice_groups):
        _append_named_paired_replacement_choices(
            row=row,
            datasheet_id=datasheet_id,
            model_profile_id=model_profile_id,
            model_name=match.group("model"),
            replaced_id=replaced_id,
            choice_groups=choice_groups,
            wargear_ids_by_name=wargear_ids_by_name,
            source_line=source_line,
            bridged_rows=bridged_rows,
            error_type=error_type,
        )
        return
    choice_ids = tuple(
        _required_wargear_id(wargear_ids_by_name, names[0], error_type=error_type)
        for names in choice_groups
    )
    common = _option_common(
        row=row,
        datasheet_id=datasheet_id,
        option_id=f"{datasheet_id}:{_name_key(match.group('model'))}-replacement:option-{source_line}",
        model_profile_id=model_profile_id,
        allowed_wargear_ids=choice_ids,
        max_selections=1,
    )
    bridged_rows["Datasheets_options"].extend(
        {
            **common,
            "line": f"{source_line}.{index}",
            "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
            "effect_wargear_id": choice_id,
            "effect_replaced_wargear_id": replaced_id,
            "effect_model_count": "1",
            "effect_wargear_count": "1",
        }
        for index, choice_id in enumerate(choice_ids, start=1)
    )


def _append_named_required_replacement(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    choices = replacement_choices(match.group("choices"), error_type=error_type)
    choice_groups = tuple((match.group("required"), choice.name) for choice in choices)
    _append_named_paired_replacement_choices(
        row=row,
        datasheet_id=datasheet_id,
        model_profile_id=_required_model_profile_id(
            model_profile_by_name,
            match.group("model"),
            error_type=error_type,
        ),
        model_name=match.group("model"),
        replaced_id=_required_wargear_id(
            wargear_ids_by_name,
            match.group("replaced"),
            error_type=error_type,
        ),
        choice_groups=choice_groups,
        wargear_ids_by_name=wargear_ids_by_name,
        source_line=_required_field(row, "line", error_type=error_type),
        bridged_rows=bridged_rows,
        error_type=error_type,
    )


def _append_named_single_replacement(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    replaced_id = _required_wargear_id(
        wargear_ids_by_name,
        match.group("replaced"),
        error_type=error_type,
    )
    replacement_id = _required_wargear_id(
        wargear_ids_by_name,
        match.group("replacement"),
        error_type=error_type,
    )
    source_line = _required_field(row, "line", error_type=error_type)
    bridged_rows["Datasheets_options"].append(
        {
            **_option_common(
                row=row,
                datasheet_id=datasheet_id,
                option_id=(
                    f"{datasheet_id}:{_name_key(match.group('model'))}-"
                    f"{_name_key(match.group('replacement'))}:option-{source_line}"
                ),
                model_profile_id=_required_model_profile_id(
                    model_profile_by_name,
                    match.group("model"),
                    error_type=error_type,
                ),
                allowed_wargear_ids=(replacement_id,),
                max_selections=1,
            ),
            "line": source_line,
            "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
            "effect_wargear_id": replacement_id,
            "effect_replaced_wargear_id": replaced_id,
            "effect_model_count": "1",
            "effect_wargear_count": "1",
        }
    )


def _replacement_choice_wargear_names(choice_name: str) -> tuple[str, ...]:
    paired_match = re.fullmatch(r"(?P<first>.+?) and 1 (?P<second>.+)", choice_name)
    if paired_match is None:
        return (choice_name,)
    return paired_match.group("first"), paired_match.group("second")


def _multiple_wargear_names(value: str) -> tuple[str, ...]:
    normalized = value.replace(", and ", ", ")
    return tuple(part.strip() for part in re.split(r", | and ", normalized) if part.strip())


def _append_named_multiple_replacement_choices(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_id: str,
    model_name: str,
    replaced_names: tuple[str, ...],
    choice_groups: tuple[tuple[str, ...], ...],
    wargear_ids_by_name: dict[str, str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    replaced_ids = tuple(
        _required_wargear_id(wargear_ids_by_name, name, error_type=error_type)
        for name in replaced_names
    )
    source_line = _required_field(row, "line", error_type=error_type)
    selection_group_id = f"{datasheet_id}:named-multiple-replacement-option-{source_line}"
    for choice_index, choice_names in enumerate(choice_groups, start=1):
        choice_ids = tuple(
            _required_wargear_id(wargear_ids_by_name, name, error_type=error_type)
            for name in choice_names
        )
        option_id = (
            f"{datasheet_id}:{_name_key(model_name)}-multiple-replacement-"
            f"{'-'.join(_name_key(name) for name in choice_names)}:option-{source_line}"
        )
        common = {
            **_option_common(
                row=row,
                datasheet_id=datasheet_id,
                option_id=option_id,
                model_profile_id=model_profile_id,
                allowed_wargear_ids=choice_ids,
                max_selections=len(choice_ids),
            ),
            **_selection_limit_fields(
                selection_group_id=selection_group_id,
                group_max_per_model=1,
                option_max_per_model=1,
            ),
        }
        effects: list[dict[str, str]] = [
            {
                **common,
                "line": f"{source_line}.{choice_index}.1",
                "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
                "effect_wargear_id": choice_ids[0],
                "effect_replaced_wargear_id": replaced_ids[0],
                "effect_model_count": "1",
                "effect_wargear_count": "1",
            }
        ]
        effects.extend(
            {
                **common,
                "line": f"{source_line}.{choice_index}.{effect_index}",
                "effect_kind": WargearOptionEffectKind.ADD_WARGEAR_IF_SELECTED.value,
                "effect_wargear_id": choice_id,
                "effect_replaced_wargear_id": "",
                "effect_model_count": "1",
                "effect_wargear_count": "1",
            }
            for effect_index, choice_id in enumerate(choice_ids[1:], start=2)
        )
        effects.extend(
            {
                **common,
                "line": f"{source_line}.{choice_index}.{effect_index}",
                "effect_kind": WargearOptionEffectKind.REMOVE_WARGEAR_IF_SELECTED.value,
                "effect_wargear_id": choice_ids[0],
                "effect_replaced_wargear_id": replaced_id,
                "effect_model_count": "1",
                "effect_wargear_count": "0",
            }
            for effect_index, replaced_id in enumerate(replaced_ids[1:], start=len(choice_ids) + 1)
        )
        bridged_rows["Datasheets_options"].extend(effects)


def _append_named_paired_replacement_choices(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_id: str,
    model_name: str,
    replaced_id: str,
    choice_groups: tuple[tuple[str, ...], ...],
    wargear_ids_by_name: dict[str, str],
    source_line: str,
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    selection_group_id = f"{datasheet_id}:named-replacement-option-{source_line}"
    for choice_index, choice_names in enumerate(choice_groups, start=1):
        choice_ids = tuple(
            _required_wargear_id(wargear_ids_by_name, name, error_type=error_type)
            for name in choice_names
        )
        option_id = (
            f"{datasheet_id}:{_name_key(model_name)}-replacement-"
            f"{'-'.join(_name_key(name) for name in choice_names)}:option-{source_line}"
        )
        common = {
            **_option_common(
                row=row,
                datasheet_id=datasheet_id,
                option_id=option_id,
                model_profile_id=model_profile_id,
                allowed_wargear_ids=choice_ids,
                max_selections=len(choice_ids),
            ),
            **_selection_limit_fields(
                selection_group_id=selection_group_id,
                group_max_per_model=1,
                option_max_per_model=1,
            ),
        }
        bridged_rows["Datasheets_options"].extend(
            {
                **common,
                "line": f"{source_line}.{choice_index}.{effect_index}",
                "effect_kind": (
                    WargearOptionEffectKind.REPLACE_WARGEAR.value
                    if effect_index == 1
                    else WargearOptionEffectKind.ADD_WARGEAR.value
                ),
                "effect_wargear_id": choice_id,
                "effect_replaced_wargear_id": replaced_id if effect_index == 1 else "",
                "effect_model_count": "1",
                "effect_wargear_count": "1",
            }
            for effect_index, choice_id in enumerate(choice_ids, start=1)
        )


def _append_additive(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
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
                max_selections=1,
            ),
            "line": source_line,
            "effect_kind": WargearOptionEffectKind.ADD_WARGEAR.value,
            "effect_wargear_id": granted_id,
            "effect_replaced_wargear_id": "",
            "effect_model_count": "1",
            "effect_wargear_count": "1",
        }
    )


def _append_any_number_replacement_choices(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    max_models_by_profile_id: dict[str, int],
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    model_profile_id = _any_number_model_profile_id(
        model_profile_by_name,
        match.group("model"),
        error_type=error_type,
    )
    replaced_id = _required_wargear_id(
        wargear_ids_by_name,
        match.group("replaced"),
        error_type=error_type,
    )
    choices = replacement_choices(match.group("choices"), error_type=error_type)
    source_line = _required_field(row, "line", error_type=error_type)
    selection_group_id = f"{datasheet_id}:any-number-replacement-option-{source_line}"
    for choice_index, choice in enumerate(choices, start=1):
        choice_id = _required_wargear_id(
            wargear_ids_by_name,
            choice.name,
            error_type=error_type,
        )
        bridged_rows["Datasheets_options"].append(
            {
                **_option_common(
                    row=row,
                    datasheet_id=datasheet_id,
                    option_id=(
                        f"{datasheet_id}:{_name_key(match.group('replaced'))}-"
                        f"{_name_key(choice.name)}:option-{source_line}"
                    ),
                    model_profile_id=model_profile_id,
                    allowed_wargear_ids=(choice_id,),
                    max_selections=max_models_by_profile_id[model_profile_id],
                ),
                "line": f"{source_line}.{choice_index}",
                **_any_number_selection_limit_fields(selection_group_id),
                "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
                "effect_wargear_id": choice_id,
                "effect_replaced_wargear_id": replaced_id,
                "effect_model_count": "1",
                "effect_wargear_count": "1",
            }
        )


def _append_any_number_single_replacement(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    max_models_by_profile_id: dict[str, int],
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    model_profile_id = _any_number_model_profile_id(
        model_profile_by_name,
        match.group("model"),
        error_type=error_type,
    )
    replacement_id = _required_wargear_id(
        wargear_ids_by_name,
        match.group("replacement"),
        error_type=error_type,
    )
    replaced_id = _required_wargear_id(
        wargear_ids_by_name,
        match.group("replaced"),
        error_type=error_type,
    )
    source_line = _required_field(row, "line", error_type=error_type)
    selection_group_id = f"{datasheet_id}:any-number-replacement-option-{source_line}"
    bridged_rows["Datasheets_options"].append(
        {
            **_option_common(
                row=row,
                datasheet_id=datasheet_id,
                option_id=(
                    f"{datasheet_id}:{_name_key(match.group('replaced'))}-"
                    f"{_name_key(match.group('replacement'))}:option-{source_line}"
                ),
                model_profile_id=model_profile_id,
                allowed_wargear_ids=(replacement_id,),
                max_selections=max_models_by_profile_id[model_profile_id],
            ),
            "line": source_line,
            **_any_number_selection_limit_fields(selection_group_id),
            "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
            "effect_wargear_id": replacement_id,
            "effect_replaced_wargear_id": replaced_id,
            "effect_model_count": "1",
            "effect_wargear_count": "1",
        }
    )


def _any_number_model_profile_id(
    model_profile_by_name: dict[str, str],
    model_name: str,
    *,
    error_type: type[ValueError],
) -> str:
    if _name_key(model_name) not in {"model", "models"}:
        return _required_model_profile_id(
            model_profile_by_name,
            model_name,
            error_type=error_type,
        )
    profile_ids = tuple(sorted(set(model_profile_by_name.values())))
    if len(profile_ids) != 1:
        raise error_type("Generic any-number wargear option requires one model profile.")
    return profile_ids[0]


def _append_all_models_paired_replacement(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    minimum_unit_models: int,
    maximum_unit_models: int,
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    if minimum_unit_models != maximum_unit_models:
        raise error_type("All-model paired replacement requires a fixed unit size.")
    model_profile_ids = tuple(sorted(set(model_profile_by_name.values())))
    if len(model_profile_ids) != 1:
        raise error_type("All-model paired replacement requires one model profile.")
    replaced_id = _required_wargear_id(
        wargear_ids_by_name,
        match.group("replaced"),
        error_type=error_type,
    )
    replacement_ids = tuple(
        _required_wargear_id(
            wargear_ids_by_name,
            match.group(group),
            error_type=error_type,
        )
        for group in ("replacement_first", "replacement_second")
    )
    source_line = _required_field(row, "line", error_type=error_type)
    common = _option_common(
        row=row,
        datasheet_id=datasheet_id,
        option_id=(
            f"{datasheet_id}:{_name_key(match.group('replacement_first'))}-"
            f"{_name_key(match.group('replacement_second'))}:option-{source_line}"
        ),
        model_profile_id=model_profile_ids[0],
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
                "effect_model_count": str(maximum_unit_models),
                "effect_wargear_count": "1",
            },
            {
                **common,
                "line": f"{source_line}.2",
                "effect_kind": WargearOptionEffectKind.ADD_WARGEAR.value,
                "effect_wargear_id": replacement_ids[1],
                "effect_replaced_wargear_id": "",
                "effect_model_count": str(maximum_unit_models),
                "effect_wargear_count": "1",
            },
        )
    )


def _append_any_number_paired_replacement(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    max_models_by_profile_id: dict[str, int],
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    model_profile_id = _required_model_profile_id(
        model_profile_by_name, match.group("model"), error_type=error_type
    )
    replacement_id = _required_wargear_id(
        wargear_ids_by_name, match.group("replacement"), error_type=error_type
    )
    replaced_ids = tuple(
        _required_wargear_id(wargear_ids_by_name, match.group(group), error_type=error_type)
        for group in ("replaced_first", "replaced_second")
    )
    source_line = _required_field(row, "line", error_type=error_type)
    selection_group_id = f"{datasheet_id}:any-number-replacement-option-{source_line}"
    common = _option_common(
        row=row,
        datasheet_id=datasheet_id,
        option_id=f"{datasheet_id}:{_name_key(match.group('replacement'))}:option-{source_line}",
        model_profile_id=model_profile_id,
        allowed_wargear_ids=(replacement_id,),
        max_selections=max_models_by_profile_id[model_profile_id],
    )
    common.update(_any_number_selection_limit_fields(selection_group_id))
    bridged_rows["Datasheets_options"].extend(
        (
            {
                **common,
                "line": f"{source_line}.1",
                "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
                "effect_wargear_id": replacement_id,
                "effect_replaced_wargear_id": replaced_ids[0],
                "effect_model_count": "1",
                "effect_wargear_count": "1",
            },
            {
                **common,
                "line": f"{source_line}.2",
                "effect_kind": WargearOptionEffectKind.REMOVE_WARGEAR_IF_SELECTED.value,
                "effect_wargear_id": replacement_id,
                "effect_replaced_wargear_id": replaced_ids[1],
                "effect_model_count": "1",
                "effect_wargear_count": "0",
            },
        )
    )


def _any_number_selection_limit_fields(selection_group_id: str) -> dict[str, str]:
    return {
        "selection_group_id": selection_group_id,
        "selection_models_per_increment": "1",
        "selection_group_max_per_increment": "1",
        "selection_option_max_per_increment": "1",
    }


def _append_scaled_alternative_replacements(
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
    models_per_increment = int(match.group("models_per_increment"))
    max_per_increment = int(match.group("max_per_increment"))
    model_profile_id = _required_model_profile_id(
        model_profile_by_name, match.group("model"), error_type=error_type
    )
    choices = replacement_choices(match.group("choices"), error_type=error_type)
    source_line = _required_field(row, "line", error_type=error_type)
    selection_group_id = f"{datasheet_id}:scaled-replacement-option-{source_line}"
    max_selections = (maximum_unit_models // models_per_increment) * max_per_increment
    replaced_names = tuple(
        name
        for name in (match.group("replaced_first"), match.group("replaced_second"))
        if name is not None
    )
    for replaced_name in replaced_names:
        replaced_id = _required_wargear_id(
            wargear_ids_by_name, replaced_name, error_type=error_type
        )
        for choice in choices:
            choice_id = _required_wargear_id(
                wargear_ids_by_name, choice.name, error_type=error_type
            )
            option_id = (
                f"{datasheet_id}:{_name_key(replaced_name)}-to-{_name_key(choice.name)}:"
                f"option-{source_line}"
            )
            bridged_rows["Datasheets_options"].append(
                {
                    **_option_common(
                        row=row,
                        datasheet_id=datasheet_id,
                        option_id=option_id,
                        model_profile_id=model_profile_id,
                        allowed_wargear_ids=(choice_id,),
                        max_selections=max_selections,
                    ),
                    "line": f"{source_line}.{len(bridged_rows['Datasheets_options']) + 1}",
                    "selection_group_id": selection_group_id,
                    "selection_models_per_increment": str(models_per_increment),
                    "selection_group_max_per_increment": str(max_per_increment),
                    "selection_option_max_per_increment": str(max_per_increment),
                    "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
                    "effect_wargear_id": choice_id,
                    "effect_replaced_wargear_id": replaced_id,
                    "effect_model_count": "1",
                    "effect_wargear_count": "1",
                }
            )


def _append_unit_size_replacements(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    choices_text = match.group("choices")
    choice_names = (
        tuple(choice.name for choice in replacement_choices(choices_text, error_type=error_type))
        if choices_text is not None
        else (match.group("replacement"),)
    )
    replaced_id = _required_wargear_id(
        wargear_ids_by_name, match.group("replaced"), error_type=error_type
    )
    source_line = _required_field(row, "line", error_type=error_type)
    selection_group_id = f"{datasheet_id}:unit-size-replacement-option-{source_line}"
    for index, choice_name in enumerate(choice_names, start=1):
        choice_id = _required_wargear_id(wargear_ids_by_name, choice_name, error_type=error_type)
        bridged_rows["Datasheets_options"].append(
            {
                **_option_common(
                    row=row,
                    datasheet_id=datasheet_id,
                    option_id=(
                        f"{datasheet_id}:{_name_key(match.group('replaced'))}-to-"
                        f"{_name_key(choice_name)}:option-{source_line}"
                    ),
                    model_profile_id=_required_model_profile_id(
                        model_profile_by_name, match.group("model"), error_type=error_type
                    ),
                    allowed_wargear_ids=(choice_id,),
                    max_selections=int(match.group("max_selections")),
                ),
                "line": f"{source_line}.{index}",
                "selection_group_id": selection_group_id,
                "selection_models_per_increment": match.group("unit_models"),
                "selection_group_max_per_increment": match.group("max_selections"),
                "selection_option_max_per_increment": match.group("max_selections"),
                "effect_kind": WargearOptionEffectKind.REPLACE_WARGEAR.value,
                "effect_wargear_id": choice_id,
                "effect_replaced_wargear_id": replaced_id,
                "effect_model_count": "1",
                "effect_wargear_count": "1",
            }
        )


def _append_conditional_additive(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    required_ids = tuple(
        _required_wargear_id(wargear_ids_by_name, match.group(group), error_type=error_type)
        for group in ("required_first", "required_second")
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
                max_selections=int(match.group("max_selections")),
            ),
            "line": source_line,
            "condition_kind": WargearOptionConditionKind.MODEL_EQUIPPED_WITH.value,
            "condition_wargear_ids": ",".join(required_ids),
            "effect_kind": WargearOptionEffectKind.ADD_WARGEAR.value,
            "effect_wargear_id": granted_id,
            "effect_replaced_wargear_id": "",
            "effect_model_count": "1",
            "effect_wargear_count": "1",
        }
    )


def _append_conditional_same_wargear_additive(
    *,
    row: NormalizedSourceRow,
    datasheet_id: str,
    model_profile_by_name: dict[str, str],
    wargear_ids_by_name: dict[str, str],
    match: re.Match[str],
    bridged_rows: dict[str, list[dict[str, str]]],
    error_type: type[ValueError],
) -> None:
    required_id = _required_wargear_id(
        wargear_ids_by_name,
        match.group("required"),
        error_type=error_type,
    )
    granted_id = _required_wargear_id(
        wargear_ids_by_name,
        match.group("granted"),
        error_type=error_type,
    )
    if required_id != granted_id:
        raise error_type("Conditional additional wargear must duplicate its required wargear.")
    source_line = _required_field(row, "line", error_type=error_type)
    bridged_rows["Datasheets_options"].append(
        {
            **_option_common(
                row=row,
                datasheet_id=datasheet_id,
                option_id=f"{datasheet_id}:{_name_key(match.group('granted'))}:option-{source_line}",
                model_profile_id=_required_model_profile_id(
                    model_profile_by_name,
                    match.group("model"),
                    error_type=error_type,
                ),
                allowed_wargear_ids=(granted_id,),
                max_selections=1,
            ),
            "line": source_line,
            "condition_kind": WargearOptionConditionKind.MODEL_EQUIPPED_WITH.value,
            "condition_wargear_ids": required_id,
            "effect_kind": WargearOptionEffectKind.ADD_WARGEAR.value,
            "effect_wargear_id": granted_id,
            "effect_replaced_wargear_id": "",
            "effect_model_count": "1",
            "effect_wargear_count": "1",
        }
    )
