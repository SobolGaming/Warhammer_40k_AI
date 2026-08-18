from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.objective_control_record_authority import (
    ObjectiveControlRecordAuthority,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry import shapely_backend

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
    from warhammer40k_core.engine.scoring import VictoryPointAward

_validate_identifier = IdentifierValidator(GameLifecycleError)
SCORING_COMMIT_CHECKPOINT_ID_KEY = "scoring_commit_checkpoint_id"
SCORING_COMMIT_CHECKPOINT_HASH_KEY = "scoring_commit_checkpoint_hash"


def enemy_unit_ids_in_player_deployment_zone_from_battlefield(
    *,
    state: GameState,
    player_id: str,
) -> tuple[str, ...]:
    """Score current deployment-zone occupancy from the live battlefield."""
    from warhammer40k_core.engine.game_state import GameState as _GameState

    if type(state) is not _GameState:
        raise GameLifecycleError("Deployment-zone secondary scoring requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Deployment-zone secondary scoring requires battlefield_state.")
    placements = tuple(
        model_placement
        for placed_army in state.battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
        for model_placement in unit_placement.model_placements
    )
    return enemy_unit_ids_in_player_deployment_zone_from_model_placements(
        state=state,
        player_id=player_id,
        model_placements=placements,
    )


def enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    player_id: str,
) -> tuple[str, ...]:
    """Rebuild zone occupancy from the scoring-boundary checkpoint, not live placements."""
    from warhammer40k_core.engine.game_state import GameState as _GameState

    if type(state) is not _GameState:
        raise GameLifecycleError("Deployment-zone secondary scoring requires GameState.")
    from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
        primary_mission_model_placements_from_checkpoint,
    )

    authority = _objective_control_authority(state=state, record=record)
    placements = primary_mission_model_placements_from_checkpoint(
        state=state,
        checkpoint=authority.boundary_checkpoint,
    )
    return enemy_unit_ids_in_player_deployment_zone_from_model_placements(
        state=state,
        player_id=player_id,
        model_placements=placements,
    )


def enemy_unit_ids_in_player_deployment_zone_from_model_placements(
    *,
    state: GameState,
    player_id: str,
    model_placements: Sequence[ModelPlacement],
) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState as _GameState

    if type(state) is not _GameState:
        raise GameLifecycleError("Deployment-zone secondary scoring requires GameState.")
    if state.mission_setup is None:
        raise GameLifecycleError("Deployment-zone secondary scoring requires MissionSetup.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Deployment-zone secondary scoring requires battlefield_state.")
    requested_player = _validate_identifier("player_id", player_id)
    if requested_player not in state.player_ids:
        raise GameLifecycleError("player_id is not in this game.")
    zones = tuple(
        zone for zone in state.mission_setup.deployment_zones if zone.player_id == requested_player
    )
    if not zones:
        raise GameLifecycleError("Deployment-zone secondary scoring requires player zone.")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    enemy_unit_ids: set[str] = set()
    for placement in model_placements:
        if type(placement) is not ModelPlacement:
            raise GameLifecycleError(
                "Deployment-zone secondary scoring requires ModelPlacement rows."
            )
        if placement.player_id == requested_player:
            continue
        model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        if any(
            shapely_backend.base_footprint_intersects_deployment_zone(
                model.base,
                model.pose,
                zone,
            )
            for zone in zones
        ):
            enemy_unit_ids.add(placement.unit_instance_id)
    return tuple(sorted(enemy_unit_ids))


def bind_state_backed_secondary_scoring_commit(
    award: VictoryPointAward,
    *,
    state: GameState,
    record: ObjectiveControlRecord,
) -> VictoryPointAward:
    checkpoint = _objective_control_authority(state=state, record=record).boundary_checkpoint
    metadata = award.metadata
    if not isinstance(metadata, dict):
        raise GameLifecycleError("Secondary VP metadata must be an object.")
    bound: dict[str, JsonValue] = dict(metadata)
    bound[SCORING_COMMIT_CHECKPOINT_ID_KEY] = checkpoint.checkpoint_id
    bound[SCORING_COMMIT_CHECKPOINT_HASH_KEY] = checkpoint.checkpoint_hash
    return replace(award, metadata=validate_json_value(bound))


def require_state_backed_secondary_scoring_commit(
    *,
    metadata: JsonValue,
    state: GameState,
    record: ObjectiveControlRecord,
) -> None:
    if not isinstance(metadata, dict):
        raise GameLifecycleError("Secondary VP metadata must be an object.")
    checkpoint = _objective_control_authority(state=state, record=record).boundary_checkpoint
    checkpoint_id = metadata.get(SCORING_COMMIT_CHECKPOINT_ID_KEY)
    checkpoint_hash = metadata.get(SCORING_COMMIT_CHECKPOINT_HASH_KEY)
    if checkpoint_id != checkpoint.checkpoint_id:
        raise GameLifecycleError(
            "State-backed Secondary VP scoring-boundary checkpoint identity drifted."
        )
    if checkpoint_hash != checkpoint.checkpoint_hash:
        raise GameLifecycleError(
            "State-backed Secondary VP scoring-boundary checkpoint hash drifted."
        )


def _objective_control_authority(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
) -> ObjectiveControlRecordAuthority:
    matches = tuple(
        authority
        for authority in state.objective_control_record_authorities
        if authority.objective_control_record_id == record.record_id
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "State-backed Secondary VP requires one Objective Control authority."
        )
    return matches[0]


__all__ = (
    "SCORING_COMMIT_CHECKPOINT_HASH_KEY",
    "SCORING_COMMIT_CHECKPOINT_ID_KEY",
    "bind_state_backed_secondary_scoring_commit",
    "enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary",
    "enemy_unit_ids_in_player_deployment_zone_from_battlefield",
    "enemy_unit_ids_in_player_deployment_zone_from_model_placements",
    "require_state_backed_secondary_scoring_commit",
)
