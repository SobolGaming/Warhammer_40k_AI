from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from warhammer40k_core.core.mission_errors import MissionPackError


class MissionScoringResolutionMode(StrEnum):
    INDEPENDENT = "independent"
    CUMULATIVE = "cumulative"
    EXCLUSIVE_HIGHEST = "exclusive_highest"


type MissionScoringResolutionGroupBinding = tuple[
    str,
    str,
    str,
    MissionScoringResolutionMode,
    str | None,
]
type MissionScoringResolutionOwnerBinding = tuple[str, str | None]


def mission_scoring_resolution_mode_from_token(
    value: object,
) -> MissionScoringResolutionMode:
    if type(value) is not str:
        raise MissionPackError("Mission scoring resolution mode must be a string.")
    try:
        return MissionScoringResolutionMode(value)
    except ValueError as exc:
        raise MissionPackError("Mission scoring resolution mode is unsupported.") from exc


def validate_mission_scoring_resolution_groups(
    *,
    field_name: str,
    bindings: tuple[MissionScoringResolutionGroupBinding, ...],
    error_factory: Callable[[str], ValueError],
) -> None:
    """Validate complete resolution groups inside one mission-card rule tuple."""

    groups: dict[str, list[MissionScoringResolutionGroupBinding]] = {}
    for binding in bindings:
        group_id = binding[4]
        if group_id is not None:
            groups.setdefault(group_id, []).append(binding)
    for group_id, group in groups.items():
        if len(group) < 2:
            raise error_factory(
                f"{field_name} resolution group {group_id} must contain at least two rules."
            )
        timings = {binding[1] for binding in group}
        source_kinds = {binding[2] for binding in group}
        modes = {binding[3] for binding in group}
        if len(timings) != 1 or len(source_kinds) != 1 or len(modes) != 1:
            raise error_factory(
                f"{field_name} resolution group {group_id} must share timing, source kind, "
                "and resolution mode within one mission card."
            )


def validate_mission_scoring_resolution_group_ownership(
    *,
    bindings: tuple[MissionScoringResolutionOwnerBinding, ...],
    error_factory: Callable[[str], ValueError],
) -> None:
    owner_by_group_id: dict[str, str] = {}
    for owner_id, group_id in bindings:
        if group_id is None:
            continue
        existing_owner = owner_by_group_id.get(group_id)
        if existing_owner is not None and existing_owner != owner_id:
            raise error_factory("Mission scoring resolution groups must not span mission cards.")
        owner_by_group_id[group_id] = owner_id


__all__ = (
    "MissionScoringResolutionGroupBinding",
    "MissionScoringResolutionMode",
    "MissionScoringResolutionOwnerBinding",
    "mission_scoring_resolution_mode_from_token",
    "validate_mission_scoring_resolution_group_ownership",
    "validate_mission_scoring_resolution_groups",
)
