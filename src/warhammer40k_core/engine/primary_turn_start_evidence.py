from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.scoring import (
    PrimaryObjectiveTurnStartState,
    PrimaryUnitDestructionState,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


class PrimaryObjectiveMarkerWitnessPayload(TypedDict):
    objective_marker_id: str
    model_instance_ids: list[str]


class PrimaryComponentTurnStartMembershipPayload(TypedDict):
    unit_instance_id: str
    evaluated_model_instance_ids: list[str]
    logical_terrain_area_ids: list[str]
    objective_marker_witnesses: list[PrimaryObjectiveMarkerWitnessPayload]


class PrimaryRulesUnitTurnStartMembershipPayload(TypedDict):
    rules_unit_instance_id: str
    component_memberships: list[PrimaryComponentTurnStartMembershipPayload]


class PrimaryRulesUnitTurnStartSnapshotPayload(TypedDict):
    snapshot_id: str
    game_id: str
    active_player_id: str
    battle_round: int
    rules_unit_memberships: list[PrimaryRulesUnitTurnStartMembershipPayload]
    source_id: str


@dataclass(frozen=True, slots=True)
class PrimaryObjectiveMarkerWitness:
    """Exact models from one component that were in range of one objective."""

    objective_marker_id: str
    model_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "objective_marker_id",
            _validate_identifier(
                "PrimaryObjectiveMarkerWitness objective_marker_id",
                self.objective_marker_id,
            ),
        )
        model_ids = _validate_identifier_tuple(
            "PrimaryObjectiveMarkerWitness model_instance_ids",
            self.model_instance_ids,
        )
        if not model_ids:
            raise GameLifecycleError("PrimaryObjectiveMarkerWitness requires at least one model.")
        object.__setattr__(self, "model_instance_ids", model_ids)

    def to_payload(self) -> PrimaryObjectiveMarkerWitnessPayload:
        return {
            "objective_marker_id": self.objective_marker_id,
            "model_instance_ids": list(self.model_instance_ids),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw_payload = _required_payload_mapping(
            payload,
            field_name="PrimaryObjectiveMarkerWitness payload",
            required_keys=("objective_marker_id", "model_instance_ids"),
        )
        model_instance_ids = _required_payload_list(
            raw_payload["model_instance_ids"],
            field_name="PrimaryObjectiveMarkerWitness model_instance_ids",
        )
        return cls(
            objective_marker_id=cast(str, raw_payload["objective_marker_id"]),
            model_instance_ids=tuple(cast(list[str], model_instance_ids)),
        )


@dataclass(frozen=True, slots=True)
class PrimaryComponentTurnStartMembership:
    """Exact turn-start position evidence for one physical component unit."""

    unit_instance_id: str
    evaluated_model_instance_ids: tuple[str, ...]
    logical_terrain_area_ids: tuple[str, ...]
    objective_marker_witnesses: tuple[PrimaryObjectiveMarkerWitness, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "PrimaryComponentTurnStartMembership unit_instance_id",
                self.unit_instance_id,
            ),
        )
        evaluated_model_ids = _validate_identifier_tuple(
            "PrimaryComponentTurnStartMembership evaluated_model_instance_ids",
            self.evaluated_model_instance_ids,
        )
        object.__setattr__(self, "evaluated_model_instance_ids", evaluated_model_ids)
        object.__setattr__(
            self,
            "logical_terrain_area_ids",
            _validate_identifier_tuple(
                "PrimaryComponentTurnStartMembership logical_terrain_area_ids",
                self.logical_terrain_area_ids,
            ),
        )
        witnesses = _validate_objective_marker_witnesses(self.objective_marker_witnesses)
        if any(
            model_id not in evaluated_model_ids
            for witness in witnesses
            for model_id in witness.model_instance_ids
        ):
            raise GameLifecycleError(
                "PrimaryComponentTurnStartMembership objective witness references an "
                "unevaluated model."
            )
        object.__setattr__(self, "objective_marker_witnesses", witnesses)

    @property
    def objective_marker_ids(self) -> tuple[str, ...]:
        return tuple(witness.objective_marker_id for witness in self.objective_marker_witnesses)

    def to_payload(self) -> PrimaryComponentTurnStartMembershipPayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "evaluated_model_instance_ids": list(self.evaluated_model_instance_ids),
            "logical_terrain_area_ids": list(self.logical_terrain_area_ids),
            "objective_marker_witnesses": [
                witness.to_payload() for witness in self.objective_marker_witnesses
            ],
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw_payload = _required_payload_mapping(
            payload,
            field_name="PrimaryComponentTurnStartMembership payload",
            required_keys=(
                "unit_instance_id",
                "evaluated_model_instance_ids",
                "logical_terrain_area_ids",
                "objective_marker_witnesses",
            ),
        )
        evaluated_model_instance_ids = _required_payload_list(
            raw_payload["evaluated_model_instance_ids"],
            field_name=("PrimaryComponentTurnStartMembership evaluated_model_instance_ids"),
        )
        logical_terrain_area_ids = _required_payload_list(
            raw_payload["logical_terrain_area_ids"],
            field_name="PrimaryComponentTurnStartMembership logical_terrain_area_ids",
        )
        objective_marker_witnesses = _required_payload_list(
            raw_payload["objective_marker_witnesses"],
            field_name="PrimaryComponentTurnStartMembership objective_marker_witnesses",
        )
        return cls(
            unit_instance_id=cast(str, raw_payload["unit_instance_id"]),
            evaluated_model_instance_ids=tuple(cast(list[str], evaluated_model_instance_ids)),
            logical_terrain_area_ids=tuple(cast(list[str], logical_terrain_area_ids)),
            objective_marker_witnesses=tuple(
                PrimaryObjectiveMarkerWitness.from_payload(witness)
                for witness in objective_marker_witnesses
            ),
        )


@dataclass(frozen=True, slots=True)
class PrimaryRulesUnitTurnStartMembership:
    """A rules unit plus its non-collapsed physical component evidence."""

    rules_unit_instance_id: str
    component_memberships: tuple[PrimaryComponentTurnStartMembership, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rules_unit_instance_id",
            _validate_identifier(
                "PrimaryRulesUnitTurnStartMembership rules_unit_instance_id",
                self.rules_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "component_memberships",
            _validate_component_memberships(self.component_memberships),
        )

    @property
    def component_unit_instance_ids(self) -> tuple[str, ...]:
        return tuple(component.unit_instance_id for component in self.component_memberships)

    @property
    def evaluated_model_instance_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                model_id
                for component in self.component_memberships
                for model_id in component.evaluated_model_instance_ids
            )
        )

    @property
    def logical_terrain_area_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    area_id
                    for component in self.component_memberships
                    for area_id in component.logical_terrain_area_ids
                }
            )
        )

    @property
    def terrain_feature_ids(self) -> tuple[str, ...]:
        """Union used by the existing destruction evidence payload contract.

        The identifiers are authoritative logical terrain-area IDs. The legacy
        destruction field retains its public name until that payload family is
        deliberately migrated.
        """
        return self.logical_terrain_area_ids

    @property
    def objective_marker_witnesses(self) -> tuple[PrimaryObjectiveMarkerWitness, ...]:
        model_ids_by_objective: dict[str, set[str]] = {}
        for component in self.component_memberships:
            for witness in component.objective_marker_witnesses:
                model_ids_by_objective.setdefault(witness.objective_marker_id, set()).update(
                    witness.model_instance_ids
                )
        return tuple(
            PrimaryObjectiveMarkerWitness(
                objective_marker_id=objective_id,
                model_instance_ids=tuple(sorted(model_ids)),
            )
            for objective_id, model_ids in sorted(model_ids_by_objective.items())
        )

    @property
    def objective_marker_ids(self) -> tuple[str, ...]:
        return tuple(witness.objective_marker_id for witness in self.objective_marker_witnesses)

    def component_membership_for_unit(
        self,
        unit_instance_id: str,
    ) -> PrimaryComponentTurnStartMembership:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for membership in self.component_memberships:
            if membership.unit_instance_id == requested_unit_id:
                return membership
        raise GameLifecycleError(
            "Primary rules-unit turn-start membership has no requested component."
        )

    def to_payload(self) -> PrimaryRulesUnitTurnStartMembershipPayload:
        return {
            "rules_unit_instance_id": self.rules_unit_instance_id,
            "component_memberships": [
                component.to_payload() for component in self.component_memberships
            ],
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw_payload = _required_payload_mapping(
            payload,
            field_name="PrimaryRulesUnitTurnStartMembership payload",
            required_keys=("rules_unit_instance_id", "component_memberships"),
        )
        component_memberships = _required_payload_list(
            raw_payload["component_memberships"],
            field_name="PrimaryRulesUnitTurnStartMembership component_memberships",
        )
        return cls(
            rules_unit_instance_id=cast(str, raw_payload["rules_unit_instance_id"]),
            component_memberships=tuple(
                PrimaryComponentTurnStartMembership.from_payload(component)
                for component in component_memberships
            ),
        )


@dataclass(frozen=True, slots=True)
class PrimaryRulesUnitTurnStartSnapshot:
    snapshot_id: str
    game_id: str
    active_player_id: str
    battle_round: int
    rules_unit_memberships: tuple[PrimaryRulesUnitTurnStartMembership, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "snapshot_id",
            _validate_identifier(
                "PrimaryRulesUnitTurnStartSnapshot snapshot_id",
                self.snapshot_id,
            ),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("PrimaryRulesUnitTurnStartSnapshot game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "PrimaryRulesUnitTurnStartSnapshot active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "PrimaryRulesUnitTurnStartSnapshot battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "rules_unit_memberships",
            _validate_rules_unit_memberships(self.rules_unit_memberships),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier(
                "PrimaryRulesUnitTurnStartSnapshot source_id",
                self.source_id,
            ),
        )

    def membership_for_rules_unit(
        self,
        rules_unit_instance_id: str,
    ) -> PrimaryRulesUnitTurnStartMembership:
        requested_rules_unit_id = _validate_identifier(
            "rules_unit_instance_id", rules_unit_instance_id
        )
        for membership in self.rules_unit_memberships:
            if membership.rules_unit_instance_id == requested_rules_unit_id:
                return membership
        raise GameLifecycleError(
            "Primary turn-start snapshot has no membership for the requested rules unit."
        )

    def membership_for_component_unit(
        self,
        unit_instance_id: str,
    ) -> PrimaryRulesUnitTurnStartMembership:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        matches = tuple(
            membership
            for membership in self.rules_unit_memberships
            if requested_unit_id in membership.component_unit_instance_ids
        )
        if len(matches) != 1:
            raise GameLifecycleError(
                "Primary turn-start snapshot requires exactly one membership for the "
                "requested component."
            )
        return matches[0]

    def membership_for_unit_identity(
        self,
        unit_instance_id: str,
    ) -> PrimaryRulesUnitTurnStartMembership:
        """Resolve either a canonical rules-unit ID or one of its components."""
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        matches = tuple(
            membership
            for membership in self.rules_unit_memberships
            if requested_unit_id == membership.rules_unit_instance_id
            or requested_unit_id in membership.component_unit_instance_ids
        )
        if len(matches) != 1:
            raise GameLifecycleError(
                "Primary turn-start snapshot requires exactly one membership for the "
                "requested unit identity."
            )
        return matches[0]

    def component_membership_for_unit(
        self,
        unit_instance_id: str,
    ) -> PrimaryComponentTurnStartMembership:
        membership = self.membership_for_component_unit(unit_instance_id)
        return membership.component_membership_for_unit(unit_instance_id)

    def to_payload(self) -> PrimaryRulesUnitTurnStartSnapshotPayload:
        return {
            "snapshot_id": self.snapshot_id,
            "game_id": self.game_id,
            "active_player_id": self.active_player_id,
            "battle_round": self.battle_round,
            "rules_unit_memberships": [
                membership.to_payload() for membership in self.rules_unit_memberships
            ],
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw_payload = _required_payload_mapping(
            payload,
            field_name="PrimaryRulesUnitTurnStartSnapshot payload",
            required_keys=(
                "snapshot_id",
                "game_id",
                "active_player_id",
                "battle_round",
                "rules_unit_memberships",
                "source_id",
            ),
        )
        rules_unit_memberships = _required_payload_list(
            raw_payload["rules_unit_memberships"],
            field_name="PrimaryRulesUnitTurnStartSnapshot rules_unit_memberships",
        )
        return cls(
            snapshot_id=cast(str, raw_payload["snapshot_id"]),
            game_id=cast(str, raw_payload["game_id"]),
            active_player_id=cast(str, raw_payload["active_player_id"]),
            battle_round=cast(int, raw_payload["battle_round"]),
            rules_unit_memberships=tuple(
                PrimaryRulesUnitTurnStartMembership.from_payload(membership)
                for membership in rules_unit_memberships
            ),
            source_id=cast(str, raw_payload["source_id"]),
        )


def primary_rules_unit_turn_start_snapshots_from_payload(
    payload: object,
) -> list[PrimaryRulesUnitTurnStartSnapshot]:
    snapshots = _required_payload_list(
        payload,
        field_name="GameState primary rules-unit turn-start snapshots",
    )
    return [PrimaryRulesUnitTurnStartSnapshot.from_payload(snapshot) for snapshot in snapshots]


def record_primary_turn_start_evidence(
    *,
    state: GameState,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> None:
    """Atomically derive objective control and exact rules-unit position evidence."""
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
            timing=ObjectiveControlTiming.TURN_START,
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
        source_objective_control_record=objective_record,
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
    position_snapshot = build_primary_rules_unit_turn_start_snapshot(state=state)
    _validate_new_turn_evidence(
        state=state,
        objective_state=objective_state,
        position_snapshot=position_snapshot,
    )
    state.record_primary_objective_turn_start_state(objective_state)
    state.record_primary_rules_unit_turn_start_snapshot(position_snapshot)


def build_primary_rules_unit_turn_start_snapshot(
    *,
    state: GameState,
) -> PrimaryRulesUnitTurnStartSnapshot:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary turn-start position tracking requires GameState.")
    mission_setup = state.mission_setup
    battlefield = state.battlefield_state
    if mission_setup is None or battlefield is None:
        raise GameLifecycleError(
            "Primary turn-start position tracking requires mission and battlefield state."
        )
    if state.active_player_id is None:
        raise GameLifecycleError("Primary turn-start position tracking requires an active player.")
    memberships = build_current_primary_rules_unit_memberships(state=state)
    return PrimaryRulesUnitTurnStartSnapshot(
        snapshot_id=_turn_evidence_id("primary-rules-unit-turn-start", state),
        game_id=state.game_id,
        active_player_id=state.active_player_id,
        battle_round=state.battle_round,
        rules_unit_memberships=memberships,
        source_id=(
            f"{state.game_id}:primary-rules-unit-turn-start:"
            f"round-{state.battle_round:02d}:{state.active_player_id}"
        ),
    )


def build_current_primary_rules_unit_memberships(
    *,
    state: GameState,
) -> tuple[PrimaryRulesUnitTurnStartMembership, ...]:
    """Build group-aware physical membership witnesses at the current boundary."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary current-position tracking requires GameState.")
    mission_setup = state.mission_setup
    battlefield = state.battlefield_state
    if mission_setup is None or battlefield is None:
        raise GameLifecycleError(
            "Primary current-position tracking requires mission and battlefield state."
        )
    if {feature.feature_id for feature in battlefield.terrain_features} != {
        feature.feature_id for feature in mission_setup.terrain_features
    }:
        raise GameLifecycleError(
            "Primary turn-start position tracking requires mission and battlefield terrain parity."
        )
    return tuple(
        _build_rules_unit_membership(
            state=state,
            rules_unit=rules_unit,
        )
        for rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
    )


def current_primary_rules_unit_turn_start_membership(
    *,
    state: GameState,
    unit_instance_id: str,
) -> PrimaryRulesUnitTurnStartMembership:
    snapshot = _current_primary_rules_unit_turn_start_snapshot(state=state)
    return snapshot.membership_for_unit_identity(unit_instance_id)


def current_primary_rules_unit_turn_start_membership_for_lineage(
    *,
    state: GameState,
    rules_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
) -> PrimaryRulesUnitTurnStartMembership:
    """Resolve one retained rules-unit identity at this turn's start."""
    snapshot = _current_primary_rules_unit_turn_start_snapshot(state=state)
    return primary_rules_unit_turn_start_membership_for_lineage(
        snapshot=snapshot,
        rules_unit_instance_id=rules_unit_instance_id,
        component_unit_instance_ids=component_unit_instance_ids,
    )


def primary_rules_unit_turn_start_membership_for_lineage(
    *,
    snapshot: PrimaryRulesUnitTurnStartSnapshot,
    rules_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
) -> PrimaryRulesUnitTurnStartMembership:
    if type(snapshot) is not PrimaryRulesUnitTurnStartSnapshot:
        raise GameLifecycleError("Primary turn-start lineage lookup requires a snapshot.")
    requested_rules_unit_id = _validate_identifier(
        "rules_unit_instance_id",
        rules_unit_instance_id,
    )
    requested_component_ids = _validate_identifier_tuple(
        "component_unit_instance_ids",
        component_unit_instance_ids,
    )
    if not requested_component_ids:
        raise GameLifecycleError(
            "Primary turn-start lineage lookup requires at least one component."
        )
    matches = tuple(
        membership
        for membership in snapshot.rules_unit_memberships
        if membership.rules_unit_instance_id == requested_rules_unit_id
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Primary turn-start retained identity requires exactly one membership."
        )
    if matches[0].component_unit_instance_ids != requested_component_ids:
        raise GameLifecycleError("Primary turn-start lineage component identity drift.")
    return matches[0]


def current_primary_component_turn_start_membership(
    *,
    state: GameState,
    unit_instance_id: str,
) -> PrimaryComponentTurnStartMembership:
    snapshot = _current_primary_rules_unit_turn_start_snapshot(state=state)
    return snapshot.component_membership_for_unit(unit_instance_id)


def record_primary_rules_unit_turn_start_snapshot(
    *,
    state: GameState,
    snapshot: PrimaryRulesUnitTurnStartSnapshot,
) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary turn-start position evidence requires GameState.")
    if type(snapshot) is not PrimaryRulesUnitTurnStartSnapshot:
        raise GameLifecycleError("Primary turn-start position evidence must be a typed snapshot.")
    if state.mission_setup is None or state.active_player_id is None:
        raise GameLifecycleError(
            "Primary turn-start position evidence requires mission and active-player state."
        )
    if snapshot.game_id != state.game_id:
        raise GameLifecycleError("PrimaryRulesUnitTurnStartSnapshot game_id drift.")
    if (snapshot.active_player_id, snapshot.battle_round) != (
        state.active_player_id,
        state.battle_round,
    ):
        raise GameLifecycleError(
            "PrimaryRulesUnitTurnStartSnapshot must match the current player turn."
        )
    if snapshot != build_primary_rules_unit_turn_start_snapshot(state=state):
        raise GameLifecycleError(
            "PrimaryRulesUnitTurnStartSnapshot does not match authoritative geometry."
        )
    if any(
        stored.snapshot_id == snapshot.snapshot_id
        or (stored.active_player_id, stored.battle_round)
        == (snapshot.active_player_id, snapshot.battle_round)
        for stored in state.primary_rules_unit_turn_start_snapshots
    ):
        raise GameLifecycleError(
            "PrimaryRulesUnitTurnStartSnapshot already exists for this player turn."
        )
    state.primary_rules_unit_turn_start_snapshots.append(snapshot)
    state.primary_rules_unit_turn_start_snapshots.sort(key=lambda stored: stored.snapshot_id)


def primary_rules_unit_turn_start_snapshots_with_created_unit(
    snapshots: object,
    *,
    unit_instance_id: str,
) -> list[PrimaryRulesUnitTurnStartSnapshot]:
    """Backfill explicit empty historical evidence for a runtime-created unit."""
    if not isinstance(snapshots, list):
        raise GameLifecycleError("Primary rules-unit turn-start snapshots must be a list.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    empty_membership = PrimaryRulesUnitTurnStartMembership(
        rules_unit_instance_id=requested_unit_id,
        component_memberships=(
            PrimaryComponentTurnStartMembership(
                unit_instance_id=requested_unit_id,
                evaluated_model_instance_ids=(),
                logical_terrain_area_ids=(),
                objective_marker_witnesses=(),
            ),
        ),
    )
    updated: list[PrimaryRulesUnitTurnStartSnapshot] = []
    for snapshot in cast(list[object], snapshots):
        if type(snapshot) is not PrimaryRulesUnitTurnStartSnapshot:
            raise GameLifecycleError(
                "Primary rules-unit turn-start snapshots must contain snapshot values."
            )
        if any(
            requested_unit_id in membership.component_unit_instance_ids
            or requested_unit_id == membership.rules_unit_instance_id
            for membership in snapshot.rules_unit_memberships
        ):
            raise GameLifecycleError(
                "Primary turn-start snapshot already contains the created unit."
            )
        updated.append(
            replace(
                snapshot,
                rules_unit_memberships=(
                    *snapshot.rules_unit_memberships,
                    empty_membership,
                ),
            )
        )
    return sorted(updated, key=lambda snapshot: snapshot.snapshot_id)


def validate_primary_objective_turn_start_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
    known_objective_marker_ids: tuple[str, ...],
) -> list[PrimaryObjectiveTurnStartState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState primary turn-start states must be a list.")
    validated: list[PrimaryObjectiveTurnStartState] = []
    seen_ids: set[str] = set()
    seen_turns: set[tuple[str, int]] = set()
    known_objectives = frozenset(known_objective_marker_ids)
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
        expected_state_id = _expected_turn_evidence_id(
            "primary-turn-start",
            game_id=game_id,
            battle_round=state.battle_round,
            active_player_id=state.active_player_id,
        )
        if state.state_id != expected_state_id:
            raise GameLifecycleError("PrimaryObjectiveTurnStartState state_id drift.")
        expected_source_id = (
            f"{game_id}:primary-turn-start:round-{state.battle_round:02d}:{state.active_player_id}"
        )
        if state.source_id != expected_source_id:
            raise GameLifecycleError("PrimaryObjectiveTurnStartState source_id drift.")
        unknown_objective_ids = set(state.controlled_objective_ids).difference(known_objectives)
        if unknown_objective_ids:
            raise GameLifecycleError(
                "PrimaryObjectiveTurnStartState contains an unknown objective marker."
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


def validate_primary_rules_unit_turn_start_snapshots(
    snapshots: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
    known_component_model_ids_by_unit: tuple[tuple[str, tuple[str, ...]], ...],
    known_attached_component_ids_by_rules_unit: tuple[tuple[str, tuple[str, ...]], ...],
    known_logical_terrain_area_ids: tuple[str, ...],
    known_objective_marker_ids: tuple[str, ...],
) -> list[PrimaryRulesUnitTurnStartSnapshot]:
    if not isinstance(snapshots, list):
        raise GameLifecycleError(
            "GameState primary rules-unit turn-start snapshots must be a list."
        )
    known_models_by_unit = _validated_known_models_by_unit(known_component_model_ids_by_unit)
    attached_components_by_rules_unit = _validated_attached_components_by_rules_unit(
        known_attached_component_ids_by_rules_unit,
        known_unit_ids=frozenset(known_models_by_unit),
    )
    known_areas = frozenset(known_logical_terrain_area_ids)
    known_objectives = frozenset(known_objective_marker_ids)
    validated: list[PrimaryRulesUnitTurnStartSnapshot] = []
    seen_ids: set[str] = set()
    seen_turns: set[tuple[str, int]] = set()
    for snapshot in cast(list[object], snapshots):
        if type(snapshot) is not PrimaryRulesUnitTurnStartSnapshot:
            raise GameLifecycleError(
                "GameState primary rules-unit turn-start snapshots must contain snapshot values."
            )
        if snapshot.game_id != game_id:
            raise GameLifecycleError("PrimaryRulesUnitTurnStartSnapshot game_id drift.")
        if snapshot.active_player_id not in player_ids:
            raise GameLifecycleError(
                "PrimaryRulesUnitTurnStartSnapshot player_id is not in this game."
            )
        expected_snapshot_id = _expected_turn_evidence_id(
            "primary-rules-unit-turn-start",
            game_id=game_id,
            battle_round=snapshot.battle_round,
            active_player_id=snapshot.active_player_id,
        )
        if snapshot.snapshot_id != expected_snapshot_id:
            raise GameLifecycleError("PrimaryRulesUnitTurnStartSnapshot snapshot_id drift.")
        expected_source_id = (
            f"{game_id}:primary-rules-unit-turn-start:round-{snapshot.battle_round:02d}:"
            f"{snapshot.active_player_id}"
        )
        if snapshot.source_id != expected_source_id:
            raise GameLifecycleError("PrimaryRulesUnitTurnStartSnapshot source_id drift.")
        if snapshot.snapshot_id in seen_ids:
            raise GameLifecycleError(
                "GameState primary rules-unit turn-start snapshots must be unique."
            )
        turn_key = (snapshot.active_player_id, snapshot.battle_round)
        if turn_key in seen_turns:
            raise GameLifecycleError(
                "GameState primary rules-unit turn-start snapshots must be unique per player turn."
            )
        _validate_snapshot_membership_references(
            snapshot=snapshot,
            known_models_by_unit=known_models_by_unit,
            attached_components_by_rules_unit=attached_components_by_rules_unit,
            known_areas=known_areas,
            known_objectives=known_objectives,
        )
        seen_ids.add(snapshot.snapshot_id)
        seen_turns.add(turn_key)
        validated.append(snapshot)
    return sorted(validated, key=lambda snapshot: snapshot.snapshot_id)


def validate_primary_turn_start_evidence_graph(
    *,
    objective_states: list[PrimaryObjectiveTurnStartState],
    position_snapshots: list[PrimaryRulesUnitTurnStartSnapshot],
) -> None:
    """Require the two independently useful turn-start records to remain atomic."""
    objective_turn_keys = {
        (state.active_player_id, state.battle_round) for state in objective_states
    }
    position_turn_keys = {
        (snapshot.active_player_id, snapshot.battle_round) for snapshot in position_snapshots
    }
    if objective_turn_keys != position_turn_keys:
        raise GameLifecycleError(
            "Primary turn-start objective and position evidence turn keys must match exactly."
        )


def validate_primary_unit_destruction_turn_start_evidence(
    *,
    destruction_states: list[PrimaryUnitDestructionState],
    position_snapshots: list[PrimaryRulesUnitTurnStartSnapshot],
    known_rules_unit_components_by_id: dict[str, tuple[str, ...]],
) -> None:
    for destruction in destruction_states:
        matching_snapshots = tuple(
            snapshot
            for snapshot in position_snapshots
            if (snapshot.active_player_id, snapshot.battle_round)
            == (destruction.active_player_id, destruction.battle_round)
        )
        if len(matching_snapshots) != 1:
            raise GameLifecycleError(
                "Primary unit destruction requires exactly one matching turn-start "
                "position snapshot."
            )
        component_ids = known_rules_unit_components_by_id.get(
            destruction.destroyed_unit_instance_id
        )
        if component_ids is None:
            raise GameLifecycleError(
                "Primary unit destruction references no known rules-unit lineage."
            )
        membership = primary_rules_unit_turn_start_membership_for_lineage(
            snapshot=matching_snapshots[0],
            rules_unit_instance_id=destruction.destroyed_unit_instance_id,
            component_unit_instance_ids=component_ids,
        )
        if destruction.started_turn_terrain_feature_ids != membership.terrain_feature_ids:
            raise GameLifecycleError(
                "Primary unit destruction terrain evidence does not match its turn snapshot."
            )
        if destruction.started_turn_objective_marker_ids != membership.objective_marker_ids:
            raise GameLifecycleError(
                "Primary unit destruction objective evidence does not match its turn snapshot."
            )


def _build_rules_unit_membership(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> PrimaryRulesUnitTurnStartMembership:
    from warhammer40k_core.engine.primary_position_membership import (
        build_primary_rules_unit_membership_from_model_placements,
    )

    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError(
            "Primary turn-start position membership requires battlefield state."
        )
    removed_model_ids = frozenset(battlefield.removed_model_ids)
    unavailable_model_ids = frozenset(state.unavailable_model_ids())
    placements_by_id: dict[str, ModelPlacement] = {}
    for component in rules_unit.components:
        for model in component.unit.own_models:
            if not model.is_alive:
                continue
            placement = battlefield.model_placement_or_none(model.model_instance_id)
            removed = model.model_instance_id in removed_model_ids
            unavailable = model.model_instance_id in unavailable_model_ids
            if placement is None:
                if not removed and not unavailable:
                    raise GameLifecycleError(
                        "Primary position evidence found an alive model with no accounted "
                        "placement."
                    )
                continue
            if removed or unavailable:
                raise GameLifecycleError(
                    "Primary position evidence found a placed model marked unavailable."
                )
            if placement.player_id != rules_unit.owner_player_id:
                raise GameLifecycleError("Primary position evidence model placement owner drift.")
            if placement.unit_instance_id != component.unit.unit_instance_id:
                raise GameLifecycleError("Primary position evidence component placement drift.")
            placements_by_id[model.model_instance_id] = placement
    return build_primary_rules_unit_membership_from_model_placements(
        state=state,
        rules_unit_instance_id=rules_unit.unit_instance_id,
        owner_player_id=rules_unit.owner_player_id,
        component_unit_instance_ids=rules_unit.component_unit_instance_ids,
        model_placements=tuple(placements_by_id.values()),
    )


def _current_primary_rules_unit_turn_start_snapshot(
    *,
    state: GameState,
) -> PrimaryRulesUnitTurnStartSnapshot:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary turn-start evidence lookup requires GameState.")
    if state.active_player_id is None:
        raise GameLifecycleError("Primary turn-start evidence lookup requires an active player.")
    snapshots = tuple(
        snapshot
        for snapshot in state.primary_rules_unit_turn_start_snapshots
        if snapshot.battle_round == state.battle_round
        and snapshot.active_player_id == state.active_player_id
    )
    if len(snapshots) != 1:
        raise GameLifecycleError(
            "Primary turn-start evidence lookup requires exactly one current-turn snapshot."
        )
    return snapshots[0]


def _validate_new_turn_evidence(
    *,
    state: GameState,
    objective_state: PrimaryObjectiveTurnStartState,
    position_snapshot: PrimaryRulesUnitTurnStartSnapshot,
) -> None:
    turn_key = (state.active_player_id, state.battle_round)
    if any(
        (stored.active_player_id, stored.battle_round) == turn_key
        for stored in state.primary_objective_turn_start_states
    ):
        raise GameLifecycleError("Primary turn-start objective evidence already exists.")
    if any(
        (stored.active_player_id, stored.battle_round) == turn_key
        for stored in state.primary_rules_unit_turn_start_snapshots
    ):
        raise GameLifecycleError("Primary turn-start position evidence already exists.")
    expected_component_ids = {
        unit.unit_instance_id for army in state.army_definitions for unit in army.units
    }
    actual_component_ids = {
        component.unit_instance_id
        for membership in position_snapshot.rules_unit_memberships
        for component in membership.component_memberships
    }
    if actual_component_ids != expected_component_ids:
        raise GameLifecycleError(
            "Primary turn-start position evidence must contain every physical unit exactly once."
        )
    if objective_state.game_id != position_snapshot.game_id or (
        objective_state.active_player_id,
        objective_state.battle_round,
    ) != (position_snapshot.active_player_id, position_snapshot.battle_round):
        raise GameLifecycleError("Primary turn-start objective and position evidence must align.")


def _validate_snapshot_membership_references(
    *,
    snapshot: PrimaryRulesUnitTurnStartSnapshot,
    known_models_by_unit: dict[str, frozenset[str]],
    attached_components_by_rules_unit: dict[str, tuple[str, ...]],
    known_areas: frozenset[str],
    known_objectives: frozenset[str],
) -> None:
    actual_component_ids = {
        component.unit_instance_id
        for membership in snapshot.rules_unit_memberships
        for component in membership.component_memberships
    }
    if actual_component_ids != set(known_models_by_unit):
        raise GameLifecycleError(
            "Primary rules-unit turn-start snapshot must contain every physical unit."
        )
    membership_by_rules_unit_id = {
        membership.rules_unit_instance_id: membership
        for membership in snapshot.rules_unit_memberships
    }
    attached_component_ids: set[str] = set()
    for attached_rules_unit_id, component_ids in attached_components_by_rules_unit.items():
        attached_component_ids.update(component_ids)
        attached_membership = membership_by_rules_unit_id.get(attached_rules_unit_id)
        if attached_membership is None:
            raise GameLifecycleError(
                "Primary rules-unit turn-start snapshot must preserve its attached identity."
            )
        if attached_membership.component_unit_instance_ids != component_ids:
            raise GameLifecycleError(
                "Primary rules-unit turn-start snapshot has invalid attached-unit grouping."
            )
    if any(
        membership_by_rules_unit_id.get(unit_id) is None
        or membership_by_rules_unit_id[unit_id].component_unit_instance_ids != (unit_id,)
        for unit_id in known_models_by_unit
        if unit_id not in attached_component_ids
    ):
        raise GameLifecycleError(
            "Primary rules-unit turn-start snapshot has invalid independent-unit grouping."
        )
    for membership in snapshot.rules_unit_memberships:
        for component in membership.component_memberships:
            known_model_ids = known_models_by_unit.get(component.unit_instance_id)
            if known_model_ids is None:
                raise GameLifecycleError(
                    "Primary turn-start snapshot references an unknown component unit."
                )
            if any(
                model_id not in known_model_ids
                for model_id in component.evaluated_model_instance_ids
            ):
                raise GameLifecycleError(
                    "Primary turn-start snapshot references a model outside its component."
                )
            if any(area_id not in known_areas for area_id in component.logical_terrain_area_ids):
                raise GameLifecycleError(
                    "Primary turn-start snapshot references an unknown logical terrain area."
                )
            if any(
                witness.objective_marker_id not in known_objectives
                for witness in component.objective_marker_witnesses
            ):
                raise GameLifecycleError(
                    "Primary turn-start snapshot references an unknown objective marker."
                )


def _validated_known_models_by_unit(
    values: object,
) -> dict[str, frozenset[str]]:
    if type(values) is not tuple:
        raise GameLifecycleError("Known component model records must be a tuple.")
    result: dict[str, frozenset[str]] = {}
    seen_model_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not tuple:
            raise GameLifecycleError("Known component model records must contain pair tuples.")
        pair = cast(tuple[object, ...], value)
        if len(pair) != 2:
            raise GameLifecycleError("Known component model records must contain pair tuples.")
        unit_id = _validate_identifier("known component unit_instance_id", pair[0])
        if unit_id in result:
            raise GameLifecycleError("Known component unit IDs must be unique.")
        model_ids = _validate_identifier_tuple(
            "known component model_instance_ids",
            pair[1],
        )
        if seen_model_ids.intersection(model_ids):
            raise GameLifecycleError("Known component model IDs must not overlap.")
        result[unit_id] = frozenset(model_ids)
        seen_model_ids.update(model_ids)
    return result


def _validated_attached_components_by_rules_unit(
    values: object,
    *,
    known_unit_ids: frozenset[str],
) -> dict[str, tuple[str, ...]]:
    if type(values) is not tuple:
        raise GameLifecycleError("Known attached rules-unit records must be a tuple.")
    result: dict[str, tuple[str, ...]] = {}
    used_component_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not tuple:
            raise GameLifecycleError("Known attached rules-unit records must contain pair tuples.")
        pair = cast(tuple[object, ...], value)
        if len(pair) != 2:
            raise GameLifecycleError("Known attached rules-unit records must contain pair tuples.")
        rules_unit_id = _validate_identifier("known attached rules_unit_instance_id", pair[0])
        if rules_unit_id in result or rules_unit_id in known_unit_ids:
            raise GameLifecycleError(
                "Known attached rules-unit identities must be unique and non-physical."
            )
        component_ids = _validate_identifier_tuple(
            "known attached component_unit_instance_ids",
            pair[1],
        )
        if len(component_ids) < 2:
            raise GameLifecycleError("Known attached rules units require at least two components.")
        if any(component_id not in known_unit_ids for component_id in component_ids):
            raise GameLifecycleError("Known attached rules-unit component is not a physical unit.")
        if used_component_ids.intersection(component_ids):
            raise GameLifecycleError("Known attached rules-unit components must not overlap.")
        result[rules_unit_id] = component_ids
        used_component_ids.update(component_ids)
    return result


def _validate_rules_unit_memberships(
    value: object,
) -> tuple[PrimaryRulesUnitTurnStartMembership, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(
            "PrimaryRulesUnitTurnStartSnapshot rules_unit_memberships must be a tuple."
        )
    memberships: list[PrimaryRulesUnitTurnStartMembership] = []
    seen_rules_unit_ids: set[str] = set()
    seen_component_ids: set[str] = set()
    for membership in cast(tuple[object, ...], value):
        if type(membership) is not PrimaryRulesUnitTurnStartMembership:
            raise GameLifecycleError(
                "PrimaryRulesUnitTurnStartSnapshot rules_unit_memberships must contain memberships."
            )
        if membership.rules_unit_instance_id in seen_rules_unit_ids:
            raise GameLifecycleError(
                "PrimaryRulesUnitTurnStartSnapshot rules-unit memberships must be unique."
            )
        if seen_component_ids.intersection(membership.component_unit_instance_ids):
            raise GameLifecycleError(
                "PrimaryRulesUnitTurnStartSnapshot physical components must not overlap."
            )
        seen_rules_unit_ids.add(membership.rules_unit_instance_id)
        seen_component_ids.update(membership.component_unit_instance_ids)
        memberships.append(membership)
    return tuple(sorted(memberships, key=lambda membership: membership.rules_unit_instance_id))


def _validate_component_memberships(
    value: object,
) -> tuple[PrimaryComponentTurnStartMembership, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(
            "PrimaryRulesUnitTurnStartMembership component_memberships must be a tuple."
        )
    memberships: list[PrimaryComponentTurnStartMembership] = []
    seen_unit_ids: set[str] = set()
    for membership in cast(tuple[object, ...], value):
        if type(membership) is not PrimaryComponentTurnStartMembership:
            raise GameLifecycleError(
                "PrimaryRulesUnitTurnStartMembership component_memberships must contain "
                "memberships."
            )
        if membership.unit_instance_id in seen_unit_ids:
            raise GameLifecycleError(
                "PrimaryRulesUnitTurnStartMembership components must be unique."
            )
        seen_unit_ids.add(membership.unit_instance_id)
        memberships.append(membership)
    if not memberships:
        raise GameLifecycleError(
            "PrimaryRulesUnitTurnStartMembership requires at least one component."
        )
    return tuple(sorted(memberships, key=lambda membership: membership.unit_instance_id))


def _validate_objective_marker_witnesses(
    value: object,
) -> tuple[PrimaryObjectiveMarkerWitness, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(
            "PrimaryComponentTurnStartMembership objective_marker_witnesses must be a tuple."
        )
    witnesses: list[PrimaryObjectiveMarkerWitness] = []
    seen_objective_ids: set[str] = set()
    for witness in cast(tuple[object, ...], value):
        if type(witness) is not PrimaryObjectiveMarkerWitness:
            raise GameLifecycleError(
                "PrimaryComponentTurnStartMembership objective_marker_witnesses must "
                "contain witnesses."
            )
        if witness.objective_marker_id in seen_objective_ids:
            raise GameLifecycleError(
                "PrimaryComponentTurnStartMembership objective witnesses must be unique."
            )
        seen_objective_ids.add(witness.objective_marker_id)
        witnesses.append(witness)
    return tuple(sorted(witnesses, key=lambda witness: witness.objective_marker_id))


def _required_payload_mapping(
    payload: object,
    *,
    field_name: str,
    required_keys: tuple[str, ...],
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    raw_payload = cast(dict[str, object], payload)
    missing_keys = tuple(key for key in required_keys if key not in raw_payload)
    if missing_keys:
        raise GameLifecycleError(f"{field_name} is missing required field: {missing_keys[0]}.")
    unexpected_keys = tuple(sorted(set(raw_payload).difference(required_keys)))
    if unexpected_keys:
        raise GameLifecycleError(f"{field_name} contains unexpected field: {unexpected_keys[0]}.")
    return raw_payload


def _required_payload_list(value: object, *, field_name: str) -> list[object]:
    if type(value) is not list:
        raise GameLifecycleError(f"{field_name} must be a list.")
    return cast(list[object], value)


def _turn_evidence_id(prefix: str, state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Primary turn-start evidence requires an active player.")
    return _expected_turn_evidence_id(
        prefix,
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
    )


def _expected_turn_evidence_id(
    prefix: str,
    *,
    game_id: str,
    battle_round: int,
    active_player_id: str,
) -> str:
    return f"{prefix}:{game_id}:round-{battle_round:02d}:{active_player_id}"


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
    "PrimaryComponentTurnStartMembership",
    "PrimaryComponentTurnStartMembershipPayload",
    "PrimaryObjectiveMarkerWitness",
    "PrimaryObjectiveMarkerWitnessPayload",
    "PrimaryRulesUnitTurnStartMembership",
    "PrimaryRulesUnitTurnStartMembershipPayload",
    "PrimaryRulesUnitTurnStartSnapshot",
    "PrimaryRulesUnitTurnStartSnapshotPayload",
    "build_current_primary_rules_unit_memberships",
    "build_primary_rules_unit_turn_start_snapshot",
    "current_primary_component_turn_start_membership",
    "current_primary_rules_unit_turn_start_membership",
    "current_primary_rules_unit_turn_start_membership_for_lineage",
    "primary_rules_unit_turn_start_membership_for_lineage",
    "primary_rules_unit_turn_start_snapshots_from_payload",
    "primary_rules_unit_turn_start_snapshots_with_created_unit",
    "record_primary_rules_unit_turn_start_snapshot",
    "record_primary_turn_start_evidence",
    "validate_primary_objective_turn_start_states",
    "validate_primary_rules_unit_turn_start_snapshots",
    "validate_primary_turn_start_evidence_graph",
    "validate_primary_unit_destruction_turn_start_evidence",
)
