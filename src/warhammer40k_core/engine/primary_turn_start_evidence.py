from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import (
    PrimaryObjectiveTurnStartState,
    PrimaryUnitDestructionState,
)
from warhammer40k_core.geometry import shapely_backend

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


class PrimaryUnitTerrainMembershipPayload(TypedDict):
    unit_instance_id: str
    terrain_feature_ids: list[str]


class PrimaryUnitTerrainTurnStartSnapshotPayload(TypedDict):
    snapshot_id: str
    game_id: str
    active_player_id: str
    battle_round: int
    unit_memberships: list[PrimaryUnitTerrainMembershipPayload]
    source_id: str


@dataclass(frozen=True, slots=True)
class PrimaryUnitTerrainMembership:
    unit_instance_id: str
    terrain_feature_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "PrimaryUnitTerrainMembership unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "terrain_feature_ids",
            _validate_identifier_tuple(
                "PrimaryUnitTerrainMembership terrain_feature_ids",
                self.terrain_feature_ids,
            ),
        )

    def to_payload(self) -> PrimaryUnitTerrainMembershipPayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "terrain_feature_ids": list(self.terrain_feature_ids),
        }

    @classmethod
    def from_payload(cls, payload: PrimaryUnitTerrainMembershipPayload) -> Self:
        return cls(
            unit_instance_id=payload["unit_instance_id"],
            terrain_feature_ids=tuple(payload["terrain_feature_ids"]),
        )


@dataclass(frozen=True, slots=True)
class PrimaryUnitTerrainTurnStartSnapshot:
    snapshot_id: str
    game_id: str
    active_player_id: str
    battle_round: int
    unit_memberships: tuple[PrimaryUnitTerrainMembership, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "snapshot_id",
            _validate_identifier(
                "PrimaryUnitTerrainTurnStartSnapshot snapshot_id",
                self.snapshot_id,
            ),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("PrimaryUnitTerrainTurnStartSnapshot game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "PrimaryUnitTerrainTurnStartSnapshot active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "PrimaryUnitTerrainTurnStartSnapshot battle_round",
                self.battle_round,
            ),
        )
        memberships = _validate_unit_memberships(self.unit_memberships)
        object.__setattr__(self, "unit_memberships", memberships)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("PrimaryUnitTerrainTurnStartSnapshot source_id", self.source_id),
        )

    def membership_for_unit(self, unit_instance_id: str) -> PrimaryUnitTerrainMembership:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for membership in self.unit_memberships:
            if membership.unit_instance_id == requested_unit_id:
                return membership
        raise GameLifecycleError(
            "Primary turn-start terrain snapshot has no membership for the requested unit."
        )

    def to_payload(self) -> PrimaryUnitTerrainTurnStartSnapshotPayload:
        return {
            "snapshot_id": self.snapshot_id,
            "game_id": self.game_id,
            "active_player_id": self.active_player_id,
            "battle_round": self.battle_round,
            "unit_memberships": [membership.to_payload() for membership in self.unit_memberships],
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: PrimaryUnitTerrainTurnStartSnapshotPayload) -> Self:
        return cls(
            snapshot_id=payload["snapshot_id"],
            game_id=payload["game_id"],
            active_player_id=payload["active_player_id"],
            battle_round=payload["battle_round"],
            unit_memberships=tuple(
                PrimaryUnitTerrainMembership.from_payload(membership)
                for membership in payload["unit_memberships"]
            ),
            source_id=payload["source_id"],
        )


def record_primary_turn_start_evidence(
    *,
    state: GameState,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> None:
    """Atomically derive turn-start objective control and physical terrain membership."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary turn-start tracking requires GameState.")
    if state.mission_setup is None or state.battlefield_state is None:
        return
    if state.active_player_id is None:
        raise GameLifecycleError("Primary turn-start tracking requires an active player.")
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Primary turn-start tracking requires a battle phase.")
    objective_record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=current_phase,
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
            runtime_modifier_registry=runtime_modifier_registry,
        )
    )
    objective_state = PrimaryObjectiveTurnStartState(
        state_id=_turn_evidence_id("primary-turn-start", state),
        game_id=state.game_id,
        player_id=state.active_player_id,
        active_player_id=state.active_player_id,
        battle_round=state.battle_round,
        controlled_objective_ids=tuple(
            sorted(
                result.objective_id
                for result in objective_record.results
                if result.controlled_by_player_id == state.active_player_id
            )
        ),
        source_id=(
            f"{state.game_id}:primary-turn-start:round-{state.battle_round:02d}:"
            f"{state.active_player_id}"
        ),
    )
    terrain_snapshot = build_primary_unit_terrain_turn_start_snapshot(state=state)
    _validate_new_turn_evidence(
        state=state, objective_state=objective_state, terrain_snapshot=terrain_snapshot
    )
    state.record_primary_objective_turn_start_state(objective_state)
    state.record_primary_unit_terrain_turn_start_snapshot(terrain_snapshot)


def build_primary_unit_terrain_turn_start_snapshot(
    *,
    state: GameState,
) -> PrimaryUnitTerrainTurnStartSnapshot:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary terrain turn-start tracking requires GameState.")
    mission_setup = state.mission_setup
    battlefield = state.battlefield_state
    if mission_setup is None or battlefield is None:
        raise GameLifecycleError(
            "Primary terrain turn-start tracking requires mission and battlefield state."
        )
    if state.active_player_id is None:
        raise GameLifecycleError("Primary terrain turn-start tracking requires an active player.")
    if {feature.feature_id for feature in battlefield.terrain_features} != {
        feature.feature_id for feature in mission_setup.terrain_features
    }:
        raise GameLifecycleError(
            "Primary terrain turn-start tracking requires mission and battlefield terrain parity."
        )
    removed_model_ids = set(battlefield.removed_model_ids)
    memberships: list[PrimaryUnitTerrainMembership] = []
    for army in state.army_definitions:
        for unit in army.units:
            terrain_feature_ids: set[str] = set()
            for model in unit.own_models:
                placement = battlefield.model_placement_or_none(model.model_instance_id)
                if (
                    not model.is_alive
                    or placement is None
                    or model.model_instance_id in removed_model_ids
                ):
                    continue
                geometry_model = geometry_model_for_placement(model=model, placement=placement)
                terrain_feature_ids.update(
                    feature.feature_id
                    for feature in battlefield.terrain_features
                    if shapely_backend.base_footprint_intersects_polygon(
                        geometry_model.base,
                        geometry_model.pose,
                        feature.rules_footprint_points(),
                    )
                )
            memberships.append(
                PrimaryUnitTerrainMembership(
                    unit_instance_id=unit.unit_instance_id,
                    terrain_feature_ids=tuple(sorted(terrain_feature_ids)),
                )
            )
    return PrimaryUnitTerrainTurnStartSnapshot(
        snapshot_id=_turn_evidence_id("primary-unit-terrain-turn-start", state),
        game_id=state.game_id,
        active_player_id=state.active_player_id,
        battle_round=state.battle_round,
        unit_memberships=tuple(memberships),
        source_id=(
            f"{state.game_id}:primary-unit-terrain-turn-start:"
            f"round-{state.battle_round:02d}:{state.active_player_id}"
        ),
    )


def current_primary_unit_terrain_membership(
    *,
    state: GameState,
    unit_instance_id: str,
) -> PrimaryUnitTerrainMembership:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary terrain evidence lookup requires GameState.")
    if state.active_player_id is None:
        raise GameLifecycleError("Primary terrain evidence lookup requires an active player.")
    snapshots = tuple(
        snapshot
        for snapshot in state.primary_unit_terrain_turn_start_snapshots
        if snapshot.battle_round == state.battle_round
        and snapshot.active_player_id == state.active_player_id
    )
    if len(snapshots) != 1:
        raise GameLifecycleError(
            "Primary terrain evidence lookup requires exactly one current-turn snapshot."
        )
    return snapshots[0].membership_for_unit(unit_instance_id)


def record_primary_unit_terrain_turn_start_snapshot(
    *,
    state: GameState,
    snapshot: PrimaryUnitTerrainTurnStartSnapshot,
) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary terrain turn-start evidence requires GameState.")
    if type(snapshot) is not PrimaryUnitTerrainTurnStartSnapshot:
        raise GameLifecycleError("primary terrain turn-start evidence must be a typed snapshot.")
    if state.mission_setup is None or state.active_player_id is None:
        raise GameLifecycleError(
            "Primary terrain turn-start evidence requires mission and active-player state."
        )
    if snapshot.game_id != state.game_id:
        raise GameLifecycleError("PrimaryUnitTerrainTurnStartSnapshot game_id drift.")
    if (snapshot.active_player_id, snapshot.battle_round) != (
        state.active_player_id,
        state.battle_round,
    ):
        raise GameLifecycleError(
            "PrimaryUnitTerrainTurnStartSnapshot must match the current player turn."
        )
    expected_unit_ids = {
        unit.unit_instance_id for army in state.army_definitions for unit in army.units
    }
    actual_unit_ids = {membership.unit_instance_id for membership in snapshot.unit_memberships}
    if actual_unit_ids != expected_unit_ids:
        raise GameLifecycleError(
            "PrimaryUnitTerrainTurnStartSnapshot must contain every physical unit."
        )
    if state.battlefield_state is None:
        raise GameLifecycleError("PrimaryUnitTerrainTurnStartSnapshot requires battlefield state.")
    known_feature_ids = {feature.feature_id for feature in state.battlefield_state.terrain_features}
    if any(
        feature_id not in known_feature_ids
        for membership in snapshot.unit_memberships
        for feature_id in membership.terrain_feature_ids
    ):
        raise GameLifecycleError("PrimaryUnitTerrainTurnStartSnapshot references unknown terrain.")
    if any(
        stored.snapshot_id == snapshot.snapshot_id
        or (stored.active_player_id, stored.battle_round)
        == (snapshot.active_player_id, snapshot.battle_round)
        for stored in state.primary_unit_terrain_turn_start_snapshots
    ):
        raise GameLifecycleError(
            "PrimaryUnitTerrainTurnStartSnapshot already exists for this player turn."
        )
    state.primary_unit_terrain_turn_start_snapshots.append(snapshot)
    state.primary_unit_terrain_turn_start_snapshots.sort(key=lambda stored: stored.snapshot_id)


def primary_unit_terrain_snapshots_with_created_unit(
    snapshots: object,
    *,
    unit_instance_id: str,
) -> list[PrimaryUnitTerrainTurnStartSnapshot]:
    """Backfill an empty historical membership for a unit created after turn start."""
    if not isinstance(snapshots, list):
        raise GameLifecycleError("Primary terrain turn-start snapshots must be a list.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    updated: list[PrimaryUnitTerrainTurnStartSnapshot] = []
    for snapshot in cast(list[object], snapshots):
        if type(snapshot) is not PrimaryUnitTerrainTurnStartSnapshot:
            raise GameLifecycleError(
                "Primary terrain turn-start snapshots must contain snapshot values."
            )
        if any(
            membership.unit_instance_id == requested_unit_id
            for membership in snapshot.unit_memberships
        ):
            raise GameLifecycleError(
                "Primary terrain turn-start snapshot already contains the created unit."
            )
        updated.append(
            replace(
                snapshot,
                unit_memberships=(
                    *snapshot.unit_memberships,
                    PrimaryUnitTerrainMembership(
                        unit_instance_id=requested_unit_id,
                        terrain_feature_ids=(),
                    ),
                ),
            )
        )
    return sorted(updated, key=lambda snapshot: snapshot.snapshot_id)


def validate_primary_objective_turn_start_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[PrimaryObjectiveTurnStartState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState primary turn-start states must be a list.")
    validated: list[PrimaryObjectiveTurnStartState] = []
    seen_ids: set[str] = set()
    seen_turns: set[tuple[str, int]] = set()
    for state in cast(list[object], states):
        if type(state) is not PrimaryObjectiveTurnStartState:
            raise GameLifecycleError(
                "GameState primary turn-start states must contain state values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("PrimaryObjectiveTurnStartState game_id drift.")
        if state.player_id not in player_ids or state.active_player_id not in player_ids:
            raise GameLifecycleError(
                "PrimaryObjectiveTurnStartState player_id is not in this game."
            )
        if state.state_id in seen_ids:
            raise GameLifecycleError("GameState primary turn-start states must be unique.")
        turn_key = (state.player_id, state.battle_round)
        if turn_key in seen_turns:
            raise GameLifecycleError(
                "GameState primary turn-start states must be unique per player turn."
            )
        seen_ids.add(state.state_id)
        seen_turns.add(turn_key)
        validated.append(state)
    return sorted(validated, key=lambda state: state.state_id)


def validate_primary_unit_terrain_turn_start_snapshots(
    snapshots: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
    known_unit_instance_ids: tuple[str, ...],
    known_terrain_feature_ids: tuple[str, ...],
) -> list[PrimaryUnitTerrainTurnStartSnapshot]:
    if not isinstance(snapshots, list):
        raise GameLifecycleError("GameState primary terrain turn-start snapshots must be a list.")
    known_units = set(known_unit_instance_ids)
    known_features = set(known_terrain_feature_ids)
    validated: list[PrimaryUnitTerrainTurnStartSnapshot] = []
    seen_ids: set[str] = set()
    seen_turns: set[tuple[str, int]] = set()
    for snapshot in cast(list[object], snapshots):
        if type(snapshot) is not PrimaryUnitTerrainTurnStartSnapshot:
            raise GameLifecycleError(
                "GameState primary terrain turn-start snapshots must contain snapshot values."
            )
        if snapshot.game_id != game_id:
            raise GameLifecycleError("PrimaryUnitTerrainTurnStartSnapshot game_id drift.")
        if snapshot.active_player_id not in player_ids:
            raise GameLifecycleError(
                "PrimaryUnitTerrainTurnStartSnapshot player_id is not in this game."
            )
        if snapshot.snapshot_id in seen_ids:
            raise GameLifecycleError(
                "GameState primary terrain turn-start snapshots must be unique."
            )
        turn_key = (snapshot.active_player_id, snapshot.battle_round)
        if turn_key in seen_turns:
            raise GameLifecycleError(
                "GameState primary terrain turn-start snapshots must be unique per player turn."
            )
        for membership in snapshot.unit_memberships:
            if membership.unit_instance_id not in known_units:
                raise GameLifecycleError(
                    "Primary terrain turn-start snapshot references an unknown unit."
                )
            if any(
                feature_id not in known_features for feature_id in membership.terrain_feature_ids
            ):
                raise GameLifecycleError(
                    "Primary terrain turn-start snapshot references an unknown terrain feature."
                )
        if {membership.unit_instance_id for membership in snapshot.unit_memberships} != known_units:
            raise GameLifecycleError(
                "Primary terrain turn-start snapshot must contain every physical unit."
            )
        seen_ids.add(snapshot.snapshot_id)
        seen_turns.add(turn_key)
        validated.append(snapshot)
    return sorted(validated, key=lambda snapshot: snapshot.snapshot_id)


def validate_primary_unit_destruction_terrain_evidence(
    *,
    destruction_states: list[PrimaryUnitDestructionState],
    terrain_snapshots: list[PrimaryUnitTerrainTurnStartSnapshot],
) -> None:
    for destruction in destruction_states:
        matching_snapshots = tuple(
            snapshot
            for snapshot in terrain_snapshots
            if (snapshot.active_player_id, snapshot.battle_round)
            == (destruction.active_player_id, destruction.battle_round)
        )
        if len(matching_snapshots) != 1:
            raise GameLifecycleError(
                "Primary unit destruction requires exactly one matching terrain snapshot."
            )
        membership = matching_snapshots[0].membership_for_unit(
            destruction.destroyed_unit_instance_id
        )
        if destruction.started_turn_terrain_feature_ids != membership.terrain_feature_ids:
            raise GameLifecycleError(
                "Primary unit destruction terrain evidence does not match its turn snapshot."
            )


def _validate_new_turn_evidence(
    *,
    state: GameState,
    objective_state: PrimaryObjectiveTurnStartState,
    terrain_snapshot: PrimaryUnitTerrainTurnStartSnapshot,
) -> None:
    turn_key = (state.active_player_id, state.battle_round)
    if any(
        (stored.active_player_id, stored.battle_round) == turn_key
        for stored in state.primary_objective_turn_start_states
    ):
        raise GameLifecycleError("Primary turn-start objective evidence already exists.")
    if any(
        (stored.active_player_id, stored.battle_round) == turn_key
        for stored in state.primary_unit_terrain_turn_start_snapshots
    ):
        raise GameLifecycleError("Primary turn-start terrain evidence already exists.")
    expected_unit_ids = {
        unit.unit_instance_id for army in state.army_definitions for unit in army.units
    }
    actual_unit_ids = {
        membership.unit_instance_id for membership in terrain_snapshot.unit_memberships
    }
    if actual_unit_ids != expected_unit_ids:
        raise GameLifecycleError(
            "Primary turn-start terrain evidence must contain every physical unit exactly once."
        )
    if objective_state.game_id != terrain_snapshot.game_id or (
        objective_state.active_player_id,
        objective_state.battle_round,
    ) != (terrain_snapshot.active_player_id, terrain_snapshot.battle_round):
        raise GameLifecycleError("Primary turn-start objective and terrain evidence must align.")


def _turn_evidence_id(prefix: str, state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Primary turn-start evidence requires an active player.")
    return f"{prefix}:{state.game_id}:round-{state.battle_round:02d}:{state.active_player_id}"


def _validate_unit_memberships(value: object) -> tuple[PrimaryUnitTerrainMembership, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(
            "PrimaryUnitTerrainTurnStartSnapshot unit_memberships must be a tuple."
        )
    memberships: list[PrimaryUnitTerrainMembership] = []
    seen_unit_ids: set[str] = set()
    for membership in cast(tuple[object, ...], value):
        if type(membership) is not PrimaryUnitTerrainMembership:
            raise GameLifecycleError(
                "PrimaryUnitTerrainTurnStartSnapshot unit_memberships must contain memberships."
            )
        if membership.unit_instance_id in seen_unit_ids:
            raise GameLifecycleError(
                "PrimaryUnitTerrainTurnStartSnapshot unit_memberships must be unique per unit."
            )
        seen_unit_ids.add(membership.unit_instance_id)
        memberships.append(membership)
    return tuple(sorted(memberships, key=lambda membership: membership.unit_instance_id))


def _validate_identifier_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(f"{field_name} value", item)
        for item in cast(tuple[object, ...], value)
    )
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(identifiers))


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "PrimaryUnitTerrainMembership",
    "PrimaryUnitTerrainMembershipPayload",
    "PrimaryUnitTerrainTurnStartSnapshot",
    "PrimaryUnitTerrainTurnStartSnapshotPayload",
    "build_primary_unit_terrain_turn_start_snapshot",
    "current_primary_unit_terrain_membership",
    "primary_unit_terrain_snapshots_with_created_unit",
    "record_primary_turn_start_evidence",
    "record_primary_unit_terrain_turn_start_snapshot",
    "validate_primary_objective_turn_start_states",
    "validate_primary_unit_destruction_terrain_evidence",
    "validate_primary_unit_terrain_turn_start_snapshots",
)
