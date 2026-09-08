"""Preserve model-scoped keyword source rows in the reviewed catalog bridge."""

import json
from collections.abc import Callable

from warhammer40k_core.core.model_keywords import ModelKeywordAssignment
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


def scoped_model_keyword_fields(
    *,
    datasheet_id: str,
    model_profile_id: str,
    profiles: tuple[tuple[str, str], ...],
    materialization_profiles: tuple[tuple[str, str, str], ...],
    name_key: Callable[[str], str],
    keyword_rows: tuple[NormalizedSourceRow, ...],
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
    error_type: type[ValueError],
) -> dict[str, str]:
    scoped: dict[tuple[str, bool], set[tuple[str, str | None]]] = {}
    global_keys: set[tuple[str, bool]] = set()
    sources: set[str] = set()
    for row in keyword_rows:
        if row.source_table != "Datasheets_keywords":
            sources.add(row.stable_source_id())
            continue
        fields = row.runtime_fields_payload()
        token = fields["keyword"]
        faction = fields["is_faction_keyword"] == "true"
        if token not in (faction_keywords if faction else keywords):
            continue
        sources.add(row.stable_source_id())
        scope = fields["model"].strip()
        if not scope or scope == "ALL MODELS":
            global_keys.add((token, faction))
            continue
        # Source model labels use regular plurals while composition profiles may
        # be singular. Normalize both sides together and reject ambiguous owners.
        scope_key = name_key(scope).removesuffix("s")
        candidates: tuple[tuple[str, str, str | None], ...] = (
            *((name, profile_id, None) for name, profile_id in profiles),
            *materialization_profiles,
        )
        owners = {
            (profile_id, descriptor_id)
            for name, profile_id, descriptor_id in candidates
            if name_key(name).removesuffix("s") == scope_key
        }
        if not owners or len({profile_id for profile_id, _ in owners}) != 1:
            raise error_type(f"Model keyword scope has no exact composition owner: {scope}.")
        scoped.setdefault((token, faction), set()).update(owners)
    if not scoped:
        return {}

    def applies(keyword: str, faction: bool, descriptor_id: str | None) -> bool:
        key = (keyword, faction)
        return (
            key in global_keys
            or key not in scoped
            or (model_profile_id, descriptor_id) in scoped[key]
        )

    descriptors = (
        None,
        *sorted(
            {
                descriptor
                for _, profile, descriptor in materialization_profiles
                if profile == model_profile_id
            }
        ),
    )
    assignments = tuple(
        ModelKeywordAssignment(
            datasheet_id=datasheet_id,
            model_profile_id=model_profile_id,
            keywords=tuple(k for k in keywords if applies(k, False, descriptor)),
            faction_keywords=tuple(k for k in faction_keywords if applies(k, True, descriptor)),
            source_ids=tuple(sorted(sources | ({descriptor} if descriptor is not None else set()))),
            materialization_descriptor_id=descriptor,
        ).to_payload()
        for descriptor in descriptors
    )
    return {
        "model_keyword_assignments": json.dumps(assignments, sort_keys=True, separators=(",", ":"))
    }
