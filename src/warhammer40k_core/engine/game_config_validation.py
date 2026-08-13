from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError


def validate_army_definitions(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[ArmyDefinition]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState army_definitions must be a list.")
    validated: list[ArmyDefinition] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not ArmyDefinition:
            raise GameLifecycleError(
                "GameState army_definitions must contain ArmyDefinition values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("ArmyDefinition player_id is not in this game.")
        if value.player_id in seen:
            raise GameLifecycleError("GameState army_definitions must be unique by player.")
        seen.add(value.player_id)
        validated.append(value)
    return sorted(validated, key=lambda stored: stored.player_id)


def validate_army_muster_requests(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> tuple[ArmyMusterRequest, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("GameConfig army_muster_requests must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    if len(raw_values) != len(player_ids):
        raise GameLifecycleError(
            "GameConfig army_muster_requests must include every player exactly once."
        )
    validated: list[ArmyMusterRequest] = []
    seen: set[str] = set()
    for value in raw_values:
        if type(value) is not ArmyMusterRequest:
            raise GameLifecycleError(
                "GameConfig army_muster_requests must contain ArmyMusterRequest values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("ArmyMusterRequest player_id is not in this game.")
        if value.player_id in seen:
            raise GameLifecycleError("GameConfig army_muster_requests must be unique by player.")
        seen.add(value.player_id)
        validated.append(value)
    if set(seen) != set(player_ids):
        raise GameLifecycleError(
            "GameConfig army_muster_requests must include every player exactly once."
        )
    return tuple(sorted(validated, key=lambda request: request.player_id))


def validate_strict_roster_legality_requests(
    values: tuple[ArmyMusterRequest, ...],
) -> None:
    non_strict_player_ids = tuple(
        request.player_id for request in values if not request.roster_legality_required
    )
    if non_strict_player_ids:
        raise GameLifecycleError(
            "GameConfig production path requires roster_legality_required for every "
            "ArmyMusterRequest. Legacy smoke fixtures must set "
            "allow_legacy_non_strict_rosters explicitly."
        )


def validate_mission_setup_muster_dispositions(
    mission_setup: MissionSetup | None,
    *,
    army_muster_requests: tuple[ArmyMusterRequest, ...],
) -> None:
    if mission_setup is None:
        return
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("mission_setup must be a MissionSetup or None.")
    requests_by_player = {request.player_id: request for request in army_muster_requests}
    for assignment in mission_setup.primary_mission_assignments:
        request = requests_by_player[assignment.player_id]
        if assignment.force_disposition_id != request.force_disposition_id:
            raise GameLifecycleError(
                "GameConfig mission Primary assignment Force Disposition does not match "
                "ArmyMusterRequest."
            )


def validate_mission_setup_army_dispositions(
    mission_setup: MissionSetup | None,
    *,
    army_definitions: list[ArmyDefinition] | tuple[ArmyDefinition, ...],
) -> None:
    if mission_setup is None:
        return
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("mission_setup must be a MissionSetup or None.")
    for army in army_definitions:
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("army_definitions must contain ArmyDefinition values.")
        assignment = mission_setup.primary_mission_assignment_for_player(army.player_id)
        if assignment.force_disposition_id != army.force_disposition_id:
            raise GameLifecycleError(
                "GameState mission Primary assignment Force Disposition does not match "
                "ArmyDefinition."
            )


__all__ = (
    "validate_army_definitions",
    "validate_army_muster_requests",
    "validate_mission_setup_army_dispositions",
    "validate_mission_setup_muster_dispositions",
    "validate_strict_roster_legality_requests",
)
