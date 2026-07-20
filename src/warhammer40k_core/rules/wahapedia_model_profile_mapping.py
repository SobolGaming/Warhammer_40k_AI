from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from typing import Protocol

from warhammer40k_core.rules.wahapedia_invulnerable_save_bridge import (
    ConditionalInvulnerableSaveBridge,
    conditional_invulnerable_save_bridge_for_model_row,
)
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow


class ModelCompositionProfile(Protocol):
    @property
    def model_profile_id(self) -> str: ...

    @property
    def model_name(self) -> str: ...


def model_source_rows_by_profile_id(
    *,
    composition_profiles: Iterable[ModelCompositionProfile],
    model_source_rows: tuple[NormalizedSourceRow, ...],
    error_type: type[ValueError],
) -> dict[str, NormalizedSourceRow]:
    profiles = tuple(composition_profiles)
    if len(model_source_rows) == 1:
        return {profile.model_profile_id: model_source_rows[0] for profile in profiles}
    source_rows_by_key: dict[str, NormalizedSourceRow] = {}
    for row in model_source_rows:
        source_name = _required_model_name(row, error_type=error_type)
        for key in _model_stat_name_keys(source_name, error_type=error_type):
            previous = source_rows_by_key.get(key)
            if previous is not None and previous.stable_source_id() != row.stable_source_id():
                raise error_type("Wahapedia model stat names are ambiguous.")
            source_rows_by_key[key] = row
    resolved: dict[str, NormalizedSourceRow] = {}
    consumed_source_ids: set[str] = set()
    for profile in profiles:
        matched_row = source_rows_by_key.get(_name_key(profile.model_name, error_type=error_type))
        if matched_row is None:
            raise error_type(
                "Unit composition model name has no matching Wahapedia model stat row."
            )
        resolved[profile.model_profile_id] = matched_row
        consumed_source_ids.add(matched_row.stable_source_id())
    expected_source_ids = {row.stable_source_id() for row in model_source_rows}
    if consumed_source_ids != expected_source_ids:
        raise error_type(
            "Wahapedia model stat rows do not map one-to-one onto unit composition profiles."
        )
    return resolved


def conditional_invulnerable_save_for_model_rows(
    *,
    datasheet_id: str,
    model_source_rows: tuple[NormalizedSourceRow, ...],
    error_type: type[ValueError],
) -> ConditionalInvulnerableSaveBridge | None:
    bridges = tuple(
        bridge
        for row in model_source_rows
        if (
            bridge := conditional_invulnerable_save_bridge_for_model_row(
                datasheet_id=datasheet_id,
                model_source_row=row,
            )
        )
        is not None
    )
    if not bridges:
        return None
    if len(model_source_rows) != 1:
        raise error_type(
            "Conditional invulnerable saves on multi-profile datasheets require profile-scoped IR."
        )
    return bridges[0]


def _model_stat_name_keys(name: str, *, error_type: type[ValueError]) -> tuple[str, ...]:
    key = _name_key(name, error_type=error_type)
    plural_keys = {key, f"{key}s"}
    if key.endswith("y") and not key.endswith(("ay", "ey", "iy", "oy", "uy")):
        plural_keys.add(f"{key[:-1]}ies")
    if key.endswith(("s", "x", "z", "ch", "sh")):
        plural_keys.add(f"{key}es")
    return tuple(sorted(plural_keys))


def _required_model_name(
    row: NormalizedSourceRow,
    *,
    error_type: type[ValueError],
) -> str:
    fields = row.runtime_fields_payload()
    if "name" not in fields:
        raise error_type("Required source column is missing: name.")
    name = fields["name"].strip()
    if not name:
        raise error_type("Required source column is empty: name.")
    return name


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
