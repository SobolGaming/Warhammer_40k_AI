from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError


class MarkerAnchorKind(StrEnum):
    OBJECTIVE = "objective"
    TERRAIN_FEATURE = "terrain_feature"


class PrimaryMissionMarkerStatus(StrEnum):
    ACTIVE = "active"
    REMOVED = "removed"


class PrimaryConsecrationStatus(StrEnum):
    ACTIVE = "active"
    CONSUMED = "consumed"


class PrimaryMissionMarkerStatePayload(TypedDict):
    marker_id: str
    game_id: str
    owner_player_id: str
    mission_id: str
    source_rule_id: str
    source_descriptor_id: str
    marker_kind: str
    anchor_kind: str
    objective_marker_id: str | None
    terrain_feature_id: str | None
    created_battle_round: int | None
    created_phase: str | None
    created_active_player_id: str | None
    source_event_id: str
    source_result_id: str | None
    source_action_id: str | None
    source_destruction_id: str | None
    source_designation_id: str | None
    status: str
    removed_battle_round: int | None
    removed_phase: str | None
    removed_active_player_id: str | None
    removal_source_id: str | None
    removal_event_id: str | None
    removal_result_id: str | None
    removal_action_id: str | None


class PrimaryCondemnedSelectionStatePayload(TypedDict):
    selection_id: str
    game_id: str
    owner_player_id: str
    mission_id: str
    source_rule_id: str
    source_descriptor_id: str
    battle_round: int
    active_player_id: str
    candidate_policy_id: str
    candidate_rules_unit_instance_ids: list[str]
    candidate_evidence_ids: list[str]
    selected_rules_unit_instance_ids: list[str]
    minimum_selection_count: int
    maximum_selection_count: int
    used_fallback_candidates: bool
    selection_request_id: str | None
    selection_result_id: str | None
    source_event_id: str


class PrimaryConsecrationDesignationStatePayload(TypedDict):
    designation_id: str
    game_id: str
    owner_player_id: str
    mission_id: str
    source_rule_id: str
    source_descriptor_id: str
    rules_unit_instance_id: str
    component_unit_instance_ids: list[str]
    source_destruction_id: str
    created_battle_round: int
    created_phase: str
    created_active_player_id: str
    source_event_id: str
    last_resolved_battle_round: int | None
    last_resolved_active_player_id: str | None
    last_resolution_event_id: str | None
    last_resolution_result_id: str | None
    status: str
    consumed_marker_id: str | None
    consumed_battle_round: int | None
    consumed_phase: str | None
    consumed_active_player_id: str | None
    consumption_source_id: str | None
    consumption_event_id: str | None
    consumption_result_id: str | None


class PrimaryMissionProgressStatePayload(TypedDict):
    markers: list[PrimaryMissionMarkerStatePayload]
    condemned_selections: list[PrimaryCondemnedSelectionStatePayload]
    consecration_designations: list[PrimaryConsecrationDesignationStatePayload]


@dataclass(frozen=True, slots=True)
class PrimaryMissionMarkerState:
    marker_id: str
    game_id: str
    owner_player_id: str
    mission_id: str
    source_rule_id: str
    source_descriptor_id: str
    marker_kind: str
    anchor_kind: MarkerAnchorKind
    objective_marker_id: str | None
    terrain_feature_id: str | None
    created_battle_round: int | None
    created_phase: str | None
    created_active_player_id: str | None
    source_event_id: str
    source_result_id: str | None
    source_action_id: str | None
    source_destruction_id: str | None
    source_designation_id: str | None
    status: PrimaryMissionMarkerStatus = PrimaryMissionMarkerStatus.ACTIVE
    removed_battle_round: int | None = None
    removed_phase: str | None = None
    removed_active_player_id: str | None = None
    removal_source_id: str | None = None
    removal_event_id: str | None = None
    removal_result_id: str | None = None
    removal_action_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "game_id", _identifier("marker game_id", self.game_id))
        object.__setattr__(
            self,
            "owner_player_id",
            _identifier("marker owner_player_id", self.owner_player_id),
        )
        object.__setattr__(self, "mission_id", _identifier("marker mission_id", self.mission_id))
        object.__setattr__(
            self,
            "source_rule_id",
            _identifier("marker source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "source_descriptor_id",
            _identifier("marker source_descriptor_id", self.source_descriptor_id),
        )
        object.__setattr__(self, "marker_kind", _identifier("marker kind", self.marker_kind))
        object.__setattr__(self, "anchor_kind", _marker_anchor_kind(self.anchor_kind))
        object.__setattr__(
            self,
            "objective_marker_id",
            _optional_identifier("marker objective_marker_id", self.objective_marker_id),
        )
        object.__setattr__(
            self,
            "terrain_feature_id",
            _optional_identifier("marker terrain_feature_id", self.terrain_feature_id),
        )
        _validate_marker_anchor(self)
        created_context = _battle_context(
            label="marker creation",
            battle_round=self.created_battle_round,
            phase=self.created_phase,
            active_player_id=self.created_active_player_id,
            optional=True,
        )
        object.__setattr__(self, "created_battle_round", created_context[0])
        object.__setattr__(self, "created_phase", created_context[1])
        object.__setattr__(self, "created_active_player_id", created_context[2])
        object.__setattr__(
            self,
            "source_event_id",
            _identifier("marker source_event_id", self.source_event_id),
        )
        for field_name in (
            "source_result_id",
            "source_action_id",
            "source_destruction_id",
            "source_designation_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_identifier(f"marker {field_name}", getattr(self, field_name)),
            )
        if self.source_action_id is not None and self.source_designation_id is not None:
            raise GameLifecycleError(
                "A primary mission marker cannot originate from both an action and a designation."
            )
        object.__setattr__(self, "status", _marker_status(self.status))
        _validate_marker_removal(self)
        expected_id = primary_mission_marker_id(
            game_id=self.game_id,
            owner_player_id=self.owner_player_id,
            mission_id=self.mission_id,
            source_rule_id=self.source_rule_id,
            source_descriptor_id=self.source_descriptor_id,
            marker_kind=self.marker_kind,
            anchor_kind=self.anchor_kind,
            objective_marker_id=self.objective_marker_id,
            terrain_feature_id=self.terrain_feature_id,
            created_battle_round=self.created_battle_round,
            created_phase=self.created_phase,
            created_active_player_id=self.created_active_player_id,
            source_event_id=self.source_event_id,
            source_result_id=self.source_result_id,
            source_action_id=self.source_action_id,
            source_destruction_id=self.source_destruction_id,
            source_designation_id=self.source_designation_id,
        )
        object.__setattr__(self, "marker_id", _identifier("marker marker_id", self.marker_id))
        if self.marker_id != expected_id:
            raise GameLifecycleError("Primary mission marker_id drift.")

    def removed(
        self,
        *,
        battle_round: int,
        phase: str,
        active_player_id: str,
        source_id: str,
        event_id: str,
        result_id: str | None = None,
        action_id: str | None = None,
    ) -> Self:
        if self.status is not PrimaryMissionMarkerStatus.ACTIVE:
            raise GameLifecycleError("Only an active primary mission marker can be removed.")
        return replace(
            self,
            status=PrimaryMissionMarkerStatus.REMOVED,
            removed_battle_round=battle_round,
            removed_phase=phase,
            removed_active_player_id=active_player_id,
            removal_source_id=source_id,
            removal_event_id=event_id,
            removal_result_id=result_id,
            removal_action_id=action_id,
        )

    def to_payload(self) -> PrimaryMissionMarkerStatePayload:
        return {
            "marker_id": self.marker_id,
            "game_id": self.game_id,
            "owner_player_id": self.owner_player_id,
            "mission_id": self.mission_id,
            "source_rule_id": self.source_rule_id,
            "source_descriptor_id": self.source_descriptor_id,
            "marker_kind": self.marker_kind,
            "anchor_kind": self.anchor_kind.value,
            "objective_marker_id": self.objective_marker_id,
            "terrain_feature_id": self.terrain_feature_id,
            "created_battle_round": self.created_battle_round,
            "created_phase": self.created_phase,
            "created_active_player_id": self.created_active_player_id,
            "source_event_id": self.source_event_id,
            "source_result_id": self.source_result_id,
            "source_action_id": self.source_action_id,
            "source_destruction_id": self.source_destruction_id,
            "source_designation_id": self.source_designation_id,
            "status": self.status.value,
            "removed_battle_round": self.removed_battle_round,
            "removed_phase": self.removed_phase,
            "removed_active_player_id": self.removed_active_player_id,
            "removal_source_id": self.removal_source_id,
            "removal_event_id": self.removal_event_id,
            "removal_result_id": self.removal_result_id,
            "removal_action_id": self.removal_action_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_mapping(
            payload,
            payload_name="Primary mission marker",
            keys=tuple(PrimaryMissionMarkerStatePayload.__annotations__),
        )
        return cls(
            marker_id=cast(str, raw["marker_id"]),
            game_id=cast(str, raw["game_id"]),
            owner_player_id=cast(str, raw["owner_player_id"]),
            mission_id=cast(str, raw["mission_id"]),
            source_rule_id=cast(str, raw["source_rule_id"]),
            source_descriptor_id=cast(str, raw["source_descriptor_id"]),
            marker_kind=cast(str, raw["marker_kind"]),
            anchor_kind=_marker_anchor_kind(raw["anchor_kind"]),
            objective_marker_id=cast(str | None, raw["objective_marker_id"]),
            terrain_feature_id=cast(str | None, raw["terrain_feature_id"]),
            created_battle_round=cast(int | None, raw["created_battle_round"]),
            created_phase=cast(str | None, raw["created_phase"]),
            created_active_player_id=cast(str | None, raw["created_active_player_id"]),
            source_event_id=cast(str, raw["source_event_id"]),
            source_result_id=cast(str | None, raw["source_result_id"]),
            source_action_id=cast(str | None, raw["source_action_id"]),
            source_destruction_id=cast(str | None, raw["source_destruction_id"]),
            source_designation_id=cast(str | None, raw["source_designation_id"]),
            status=_marker_status(raw["status"]),
            removed_battle_round=cast(int | None, raw["removed_battle_round"]),
            removed_phase=cast(str | None, raw["removed_phase"]),
            removed_active_player_id=cast(str | None, raw["removed_active_player_id"]),
            removal_source_id=cast(str | None, raw["removal_source_id"]),
            removal_event_id=cast(str | None, raw["removal_event_id"]),
            removal_result_id=cast(str | None, raw["removal_result_id"]),
            removal_action_id=cast(str | None, raw["removal_action_id"]),
        )


def is_consecrated_objective_marker(
    marker: PrimaryMissionMarkerState,
    source_identity: tuple[str, str],
) -> bool:
    return (
        (marker.source_rule_id, marker.source_descriptor_id) == source_identity
        and marker.source_designation_id is not None
        and marker.anchor_kind is MarkerAnchorKind.OBJECTIVE
    )


@dataclass(frozen=True, slots=True)
class PrimaryCondemnedSelectionState:
    selection_id: str
    game_id: str
    owner_player_id: str
    mission_id: str
    source_rule_id: str
    source_descriptor_id: str
    battle_round: int
    active_player_id: str
    candidate_policy_id: str
    candidate_rules_unit_instance_ids: tuple[str, ...]
    candidate_evidence_ids: tuple[str, ...]
    selected_rules_unit_instance_ids: tuple[str, ...]
    minimum_selection_count: int
    maximum_selection_count: int
    used_fallback_candidates: bool
    selection_request_id: str | None
    selection_result_id: str | None
    source_event_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "game_id",
            "owner_player_id",
            "mission_id",
            "source_rule_id",
            "source_descriptor_id",
            "active_player_id",
            "candidate_policy_id",
            "source_event_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _identifier(f"condemned selection {field_name}", getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "battle_round",
            _positive_int("condemned selection battle_round", self.battle_round),
        )
        if self.active_player_id != self.owner_player_id:
            raise GameLifecycleError(
                "A condemned selection must be recorded during its owner's player turn."
            )
        candidates = _identifier_tuple(
            "condemned selection candidate_rules_unit_instance_ids",
            self.candidate_rules_unit_instance_ids,
            allow_empty=True,
        )
        evidence_ids = _identifier_tuple(
            "condemned selection candidate_evidence_ids",
            self.candidate_evidence_ids,
            allow_empty=True,
        )
        selected = _identifier_tuple(
            "condemned selection selected_rules_unit_instance_ids",
            self.selected_rules_unit_instance_ids,
            allow_empty=True,
        )
        if not set(selected) <= set(candidates):
            raise GameLifecycleError("Condemned units must belong to the recorded candidate set.")
        object.__setattr__(self, "candidate_rules_unit_instance_ids", candidates)
        object.__setattr__(self, "candidate_evidence_ids", evidence_ids)
        object.__setattr__(self, "selected_rules_unit_instance_ids", selected)
        minimum = _non_negative_int(
            "condemned selection minimum_selection_count",
            self.minimum_selection_count,
        )
        maximum = _non_negative_int(
            "condemned selection maximum_selection_count",
            self.maximum_selection_count,
        )
        if minimum > maximum:
            raise GameLifecycleError("Condemned selection minimum cannot exceed maximum.")
        if maximum > len(candidates):
            raise GameLifecycleError("Condemned selection maximum exceeds candidate count.")
        if not minimum <= len(selected) <= maximum:
            raise GameLifecycleError("Condemned selection count is outside its recorded bounds.")
        if not candidates and (minimum != 0 or maximum != 0 or selected):
            raise GameLifecycleError("An empty condemned candidate set requires an empty choice.")
        if candidates and minimum == 0:
            raise GameLifecycleError("A non-empty condemned candidate set requires a choice.")
        object.__setattr__(self, "minimum_selection_count", minimum)
        object.__setattr__(self, "maximum_selection_count", maximum)
        object.__setattr__(
            self,
            "used_fallback_candidates",
            _bool("condemned selection used_fallback_candidates", self.used_fallback_candidates),
        )
        if self.used_fallback_candidates and not candidates:
            raise GameLifecycleError("Fallback candidate use requires candidates.")
        request_id = _optional_identifier(
            "condemned selection selection_request_id",
            self.selection_request_id,
        )
        result_id = _optional_identifier(
            "condemned selection selection_result_id",
            self.selection_result_id,
        )
        if (request_id is None) != (result_id is None):
            raise GameLifecycleError(
                "Condemned selection request and result provenance must be recorded together."
            )
        if candidates and result_id is None:
            raise GameLifecycleError("A condemned unit choice requires decision provenance.")
        object.__setattr__(self, "selection_request_id", request_id)
        object.__setattr__(self, "selection_result_id", result_id)
        expected_id = primary_condemned_selection_id(
            game_id=self.game_id,
            owner_player_id=self.owner_player_id,
            mission_id=self.mission_id,
            source_rule_id=self.source_rule_id,
            source_descriptor_id=self.source_descriptor_id,
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            candidate_policy_id=self.candidate_policy_id,
            candidate_rules_unit_instance_ids=self.candidate_rules_unit_instance_ids,
            candidate_evidence_ids=self.candidate_evidence_ids,
            selected_rules_unit_instance_ids=self.selected_rules_unit_instance_ids,
            minimum_selection_count=self.minimum_selection_count,
            maximum_selection_count=self.maximum_selection_count,
            used_fallback_candidates=self.used_fallback_candidates,
            selection_request_id=self.selection_request_id,
            selection_result_id=self.selection_result_id,
            source_event_id=self.source_event_id,
        )
        object.__setattr__(
            self,
            "selection_id",
            _identifier("condemned selection selection_id", self.selection_id),
        )
        if self.selection_id != expected_id:
            raise GameLifecycleError("Primary condemned selection_id drift.")

    def to_payload(self) -> PrimaryCondemnedSelectionStatePayload:
        return {
            "selection_id": self.selection_id,
            "game_id": self.game_id,
            "owner_player_id": self.owner_player_id,
            "mission_id": self.mission_id,
            "source_rule_id": self.source_rule_id,
            "source_descriptor_id": self.source_descriptor_id,
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "candidate_policy_id": self.candidate_policy_id,
            "candidate_rules_unit_instance_ids": list(self.candidate_rules_unit_instance_ids),
            "candidate_evidence_ids": list(self.candidate_evidence_ids),
            "selected_rules_unit_instance_ids": list(self.selected_rules_unit_instance_ids),
            "minimum_selection_count": self.minimum_selection_count,
            "maximum_selection_count": self.maximum_selection_count,
            "used_fallback_candidates": self.used_fallback_candidates,
            "selection_request_id": self.selection_request_id,
            "selection_result_id": self.selection_result_id,
            "source_event_id": self.source_event_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_mapping(
            payload,
            payload_name="Primary condemned selection",
            keys=tuple(PrimaryCondemnedSelectionStatePayload.__annotations__),
        )
        return cls(
            selection_id=cast(str, raw["selection_id"]),
            game_id=cast(str, raw["game_id"]),
            owner_player_id=cast(str, raw["owner_player_id"]),
            mission_id=cast(str, raw["mission_id"]),
            source_rule_id=cast(str, raw["source_rule_id"]),
            source_descriptor_id=cast(str, raw["source_descriptor_id"]),
            battle_round=cast(int, raw["battle_round"]),
            active_player_id=cast(str, raw["active_player_id"]),
            candidate_policy_id=cast(str, raw["candidate_policy_id"]),
            candidate_rules_unit_instance_ids=_payload_identifier_tuple(
                raw["candidate_rules_unit_instance_ids"],
                "Primary condemned selection candidate_rules_unit_instance_ids",
            ),
            candidate_evidence_ids=_payload_identifier_tuple(
                raw["candidate_evidence_ids"],
                "Primary condemned selection candidate_evidence_ids",
            ),
            selected_rules_unit_instance_ids=_payload_identifier_tuple(
                raw["selected_rules_unit_instance_ids"],
                "Primary condemned selection selected_rules_unit_instance_ids",
            ),
            minimum_selection_count=cast(int, raw["minimum_selection_count"]),
            maximum_selection_count=cast(int, raw["maximum_selection_count"]),
            used_fallback_candidates=cast(bool, raw["used_fallback_candidates"]),
            selection_request_id=cast(str | None, raw["selection_request_id"]),
            selection_result_id=cast(str | None, raw["selection_result_id"]),
            source_event_id=cast(str, raw["source_event_id"]),
        )


@dataclass(frozen=True, slots=True)
class PrimaryConsecrationDesignationState:
    """A destruction-created unit designation retained after it is consumed."""

    designation_id: str
    game_id: str
    owner_player_id: str
    mission_id: str
    source_rule_id: str
    source_descriptor_id: str
    rules_unit_instance_id: str
    component_unit_instance_ids: tuple[str, ...]
    source_destruction_id: str
    created_battle_round: int
    created_phase: str
    created_active_player_id: str
    source_event_id: str
    last_resolved_battle_round: int | None = None
    last_resolved_active_player_id: str | None = None
    last_resolution_event_id: str | None = None
    last_resolution_result_id: str | None = None
    status: PrimaryConsecrationStatus = PrimaryConsecrationStatus.ACTIVE
    consumed_marker_id: str | None = None
    consumed_battle_round: int | None = None
    consumed_phase: str | None = None
    consumed_active_player_id: str | None = None
    consumption_source_id: str | None = None
    consumption_event_id: str | None = None
    consumption_result_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "game_id",
            "owner_player_id",
            "mission_id",
            "source_rule_id",
            "source_descriptor_id",
            "rules_unit_instance_id",
            "source_destruction_id",
            "source_event_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _identifier(f"consecration designation {field_name}", getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "component_unit_instance_ids",
            _identifier_tuple(
                "consecration designation component_unit_instance_ids",
                self.component_unit_instance_ids,
                allow_empty=False,
            ),
        )
        created_context = _battle_context(
            label="consecration designation creation",
            battle_round=self.created_battle_round,
            phase=self.created_phase,
            active_player_id=self.created_active_player_id,
            optional=False,
        )
        object.__setattr__(self, "created_battle_round", created_context[0])
        object.__setattr__(self, "created_phase", created_context[1])
        object.__setattr__(self, "created_active_player_id", created_context[2])
        _validate_designation_last_resolution(self)
        object.__setattr__(self, "status", _consecration_status(self.status))
        _validate_designation_consumption(self)
        expected_id = primary_consecration_designation_id(
            game_id=self.game_id,
            owner_player_id=self.owner_player_id,
            mission_id=self.mission_id,
            source_rule_id=self.source_rule_id,
            source_descriptor_id=self.source_descriptor_id,
            rules_unit_instance_id=self.rules_unit_instance_id,
            component_unit_instance_ids=self.component_unit_instance_ids,
            source_destruction_id=self.source_destruction_id,
            created_battle_round=self.created_battle_round,
            created_phase=self.created_phase,
            created_active_player_id=self.created_active_player_id,
            source_event_id=self.source_event_id,
        )
        object.__setattr__(
            self,
            "designation_id",
            _identifier("consecration designation designation_id", self.designation_id),
        )
        if self.designation_id != expected_id:
            raise GameLifecycleError("Primary consecration designation_id drift.")

    def resolved_without_consumption(
        self,
        *,
        battle_round: int,
        active_player_id: str,
        event_id: str,
        result_id: str | None = None,
    ) -> Self:
        if self.status is not PrimaryConsecrationStatus.ACTIVE:
            raise GameLifecycleError(
                "Only an active consecration designation can record no selection."
            )
        turn = (
            _positive_int("consecration resolution battle_round", battle_round),
            _identifier("consecration resolution active_player_id", active_player_id),
        )
        if turn == (
            self.last_resolved_battle_round,
            self.last_resolved_active_player_id,
        ):
            raise GameLifecycleError(
                "Consecration designation was already resolved for this owner turn."
            )
        if self.last_resolved_battle_round is not None and (
            turn[0] < self.last_resolved_battle_round
        ):
            raise GameLifecycleError("Consecration resolution cannot move backwards in time.")
        return replace(
            self,
            last_resolved_battle_round=turn[0],
            last_resolved_active_player_id=turn[1],
            last_resolution_event_id=event_id,
            last_resolution_result_id=result_id,
        )

    def was_resolved_for_turn(self, *, battle_round: int, active_player_id: str) -> bool:
        return (
            self.last_resolved_battle_round,
            self.last_resolved_active_player_id,
        ) == (
            _positive_int("consecration resolution battle_round", battle_round),
            _identifier("consecration resolution active_player_id", active_player_id),
        )

    def consumed(
        self,
        *,
        marker_id: str,
        battle_round: int,
        phase: str,
        active_player_id: str,
        source_id: str,
        event_id: str,
        result_id: str,
    ) -> Self:
        if self.status is not PrimaryConsecrationStatus.ACTIVE:
            raise GameLifecycleError("Only an active consecration designation can be consumed.")
        if self.was_resolved_for_turn(
            battle_round=battle_round,
            active_player_id=active_player_id,
        ):
            raise GameLifecycleError(
                "A consecration designation cannot be consumed after declining in this turn."
            )
        return replace(
            self,
            status=PrimaryConsecrationStatus.CONSUMED,
            consumed_marker_id=marker_id,
            consumed_battle_round=battle_round,
            consumed_phase=phase,
            consumed_active_player_id=active_player_id,
            consumption_source_id=source_id,
            consumption_event_id=event_id,
            consumption_result_id=result_id,
        )

    def to_payload(self) -> PrimaryConsecrationDesignationStatePayload:
        return {
            "designation_id": self.designation_id,
            "game_id": self.game_id,
            "owner_player_id": self.owner_player_id,
            "mission_id": self.mission_id,
            "source_rule_id": self.source_rule_id,
            "source_descriptor_id": self.source_descriptor_id,
            "rules_unit_instance_id": self.rules_unit_instance_id,
            "component_unit_instance_ids": list(self.component_unit_instance_ids),
            "source_destruction_id": self.source_destruction_id,
            "created_battle_round": self.created_battle_round,
            "created_phase": self.created_phase,
            "created_active_player_id": self.created_active_player_id,
            "source_event_id": self.source_event_id,
            "last_resolved_battle_round": self.last_resolved_battle_round,
            "last_resolved_active_player_id": self.last_resolved_active_player_id,
            "last_resolution_event_id": self.last_resolution_event_id,
            "last_resolution_result_id": self.last_resolution_result_id,
            "status": self.status.value,
            "consumed_marker_id": self.consumed_marker_id,
            "consumed_battle_round": self.consumed_battle_round,
            "consumed_phase": self.consumed_phase,
            "consumed_active_player_id": self.consumed_active_player_id,
            "consumption_source_id": self.consumption_source_id,
            "consumption_event_id": self.consumption_event_id,
            "consumption_result_id": self.consumption_result_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_mapping(
            payload,
            payload_name="Primary consecration designation",
            keys=tuple(PrimaryConsecrationDesignationStatePayload.__annotations__),
        )
        return cls(
            designation_id=cast(str, raw["designation_id"]),
            game_id=cast(str, raw["game_id"]),
            owner_player_id=cast(str, raw["owner_player_id"]),
            mission_id=cast(str, raw["mission_id"]),
            source_rule_id=cast(str, raw["source_rule_id"]),
            source_descriptor_id=cast(str, raw["source_descriptor_id"]),
            rules_unit_instance_id=cast(str, raw["rules_unit_instance_id"]),
            component_unit_instance_ids=_payload_identifier_tuple(
                raw["component_unit_instance_ids"],
                "Primary consecration designation component_unit_instance_ids",
            ),
            source_destruction_id=cast(str, raw["source_destruction_id"]),
            created_battle_round=cast(int, raw["created_battle_round"]),
            created_phase=cast(str, raw["created_phase"]),
            created_active_player_id=cast(str, raw["created_active_player_id"]),
            source_event_id=cast(str, raw["source_event_id"]),
            last_resolved_battle_round=cast(int | None, raw["last_resolved_battle_round"]),
            last_resolved_active_player_id=cast(
                str | None,
                raw["last_resolved_active_player_id"],
            ),
            last_resolution_event_id=cast(str | None, raw["last_resolution_event_id"]),
            last_resolution_result_id=cast(str | None, raw["last_resolution_result_id"]),
            status=_consecration_status(raw["status"]),
            consumed_marker_id=cast(str | None, raw["consumed_marker_id"]),
            consumed_battle_round=cast(int | None, raw["consumed_battle_round"]),
            consumed_phase=cast(str | None, raw["consumed_phase"]),
            consumed_active_player_id=cast(str | None, raw["consumed_active_player_id"]),
            consumption_source_id=cast(str | None, raw["consumption_source_id"]),
            consumption_event_id=cast(str | None, raw["consumption_event_id"]),
            consumption_result_id=cast(str | None, raw["consumption_result_id"]),
        )


@dataclass(frozen=True, slots=True)
class PrimaryMissionProgressState:
    markers: tuple[PrimaryMissionMarkerState, ...]
    condemned_selections: tuple[PrimaryCondemnedSelectionState, ...]
    consecration_designations: tuple[PrimaryConsecrationDesignationState, ...]

    def __post_init__(self) -> None:
        markers = _typed_tuple(
            "primary mission markers",
            self.markers,
            PrimaryMissionMarkerState,
            id_attribute="marker_id",
        )
        selections = _typed_tuple(
            "primary condemned selections",
            self.condemned_selections,
            PrimaryCondemnedSelectionState,
            id_attribute="selection_id",
        )
        designations = _typed_tuple(
            "primary consecration designations",
            self.consecration_designations,
            PrimaryConsecrationDesignationState,
            id_attribute="designation_id",
        )
        object.__setattr__(self, "markers", markers)
        object.__setattr__(self, "condemned_selections", selections)
        object.__setattr__(self, "consecration_designations", designations)
        self._validate_invariants()

    @classmethod
    def empty(cls) -> Self:
        return cls(markers=(), condemned_selections=(), consecration_designations=())

    def add_marker(self, marker: PrimaryMissionMarkerState) -> Self:
        return replace(self, markers=(*self.markers, marker))

    def replace_marker(self, marker: PrimaryMissionMarkerState) -> Self:
        _exact_type("primary mission marker", marker, PrimaryMissionMarkerState)
        return replace(
            self,
            markers=_replace_by_id(self.markers, marker, "marker_id", "primary mission marker"),
        )

    def add_condemned_selection(self, selection: PrimaryCondemnedSelectionState) -> Self:
        return replace(self, condemned_selections=(*self.condemned_selections, selection))

    def replace_condemned_selection(
        self,
        selection: PrimaryCondemnedSelectionState,
    ) -> Self:
        _exact_type("primary condemned selection", selection, PrimaryCondemnedSelectionState)
        return replace(
            self,
            condemned_selections=_replace_by_id(
                self.condemned_selections,
                selection,
                "selection_id",
                "primary condemned selection",
            ),
        )

    def add_consecration_designation(
        self,
        designation: PrimaryConsecrationDesignationState,
    ) -> Self:
        return replace(
            self,
            consecration_designations=(*self.consecration_designations, designation),
        )

    def replace_consecration_designation(
        self,
        designation: PrimaryConsecrationDesignationState,
    ) -> Self:
        _exact_type(
            "primary consecration designation",
            designation,
            PrimaryConsecrationDesignationState,
        )
        return replace(
            self,
            consecration_designations=_replace_by_id(
                self.consecration_designations,
                designation,
                "designation_id",
                "primary consecration designation",
            ),
        )

    def to_payload(self) -> PrimaryMissionProgressStatePayload:
        return {
            "markers": [marker.to_payload() for marker in self.markers],
            "condemned_selections": [
                selection.to_payload() for selection in self.condemned_selections
            ],
            "consecration_designations": [
                designation.to_payload() for designation in self.consecration_designations
            ],
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_mapping(
            payload,
            payload_name="Primary mission progress",
            keys=tuple(PrimaryMissionProgressStatePayload.__annotations__),
        )
        return cls(
            markers=tuple(
                PrimaryMissionMarkerState.from_payload(value)
                for value in _payload_list(raw["markers"], "Primary mission progress markers")
            ),
            condemned_selections=tuple(
                PrimaryCondemnedSelectionState.from_payload(value)
                for value in _payload_list(
                    raw["condemned_selections"],
                    "Primary mission progress condemned_selections",
                )
            ),
            consecration_designations=tuple(
                PrimaryConsecrationDesignationState.from_payload(value)
                for value in _payload_list(
                    raw["consecration_designations"],
                    "Primary mission progress consecration_designations",
                )
            ),
        )

    def _validate_invariants(self) -> None:
        game_ids = {
            *(marker.game_id for marker in self.markers),
            *(selection.game_id for selection in self.condemned_selections),
            *(designation.game_id for designation in self.consecration_designations),
        }
        if len(game_ids) > 1:
            raise GameLifecycleError("Primary mission progress cannot mix game identities.")
        turn_keys: set[tuple[str, str, str, int]] = set()
        for selection in self.condemned_selections:
            turn_key = (
                selection.owner_player_id,
                selection.mission_id,
                selection.source_descriptor_id,
                selection.battle_round,
            )
            if turn_key in turn_keys:
                raise GameLifecycleError(
                    "Primary condemned selections must be unique per owner mission turn."
                )
            turn_keys.add(turn_key)
        active_designation_keys: set[tuple[str, str, str, str]] = set()
        destruction_keys: set[tuple[str, str, str]] = set()
        for designation in self.consecration_designations:
            destruction_key = (
                designation.owner_player_id,
                designation.source_descriptor_id,
                designation.source_destruction_id,
            )
            if destruction_key in destruction_keys:
                raise GameLifecycleError(
                    "Consecration designations must be unique per destruction occurrence."
                )
            destruction_keys.add(destruction_key)
            if designation.status is PrimaryConsecrationStatus.ACTIVE:
                active_key = (
                    designation.owner_player_id,
                    designation.mission_id,
                    designation.source_descriptor_id,
                    designation.rules_unit_instance_id,
                )
                if active_key in active_designation_keys:
                    raise GameLifecycleError(
                        "A rules unit cannot have duplicate active consecration designations."
                    )
                active_designation_keys.add(active_key)
        markers_by_id = {marker.marker_id: marker for marker in self.markers}
        designations_by_id = {
            designation.designation_id: designation
            for designation in self.consecration_designations
        }
        for marker in self.markers:
            designation_id = marker.source_designation_id
            if designation_id is None:
                continue
            linked_designation = designations_by_id.get(designation_id)
            if linked_designation is None:
                raise GameLifecycleError(
                    "Primary mission marker references an unknown consecration designation."
                )
            if marker.anchor_kind is not MarkerAnchorKind.OBJECTIVE:
                raise GameLifecycleError("A consecration marker must anchor to an objective.")
            if marker.source_result_id is None or marker.source_destruction_id is None:
                raise GameLifecycleError(
                    "A consecration marker requires result and destruction provenance."
                )
            marker_identity = (
                marker.game_id,
                marker.owner_player_id,
                marker.mission_id,
                marker.source_destruction_id,
            )
            designation_identity = (
                linked_designation.game_id,
                linked_designation.owner_player_id,
                linked_designation.mission_id,
                linked_designation.source_destruction_id,
            )
            if marker_identity != designation_identity:
                raise GameLifecycleError("Consecration marker provenance drift.")
        for designation in self.consecration_designations:
            if designation.status is not PrimaryConsecrationStatus.CONSUMED:
                continue
            if designation.consumed_marker_id is None:
                raise GameLifecycleError("Consumed consecration designation is missing marker.")
            designation_id = designation.designation_id
            linked_marker = markers_by_id.get(designation.consumed_marker_id)
            if linked_marker is None or linked_marker.source_designation_id != designation_id:
                raise GameLifecycleError(
                    "Consumed consecration designation marker linkage is invalid."
                )


def primary_mission_marker_id(
    *,
    game_id: str,
    owner_player_id: str,
    mission_id: str,
    source_rule_id: str,
    source_descriptor_id: str,
    marker_kind: str,
    anchor_kind: MarkerAnchorKind,
    objective_marker_id: str | None,
    terrain_feature_id: str | None,
    created_battle_round: int | None,
    created_phase: str | None,
    created_active_player_id: str | None,
    source_event_id: str,
    source_result_id: str | None,
    source_action_id: str | None,
    source_destruction_id: str | None,
    source_designation_id: str | None,
) -> str:
    kind = _marker_anchor_kind(anchor_kind)
    objective_id = _optional_identifier("marker objective_marker_id", objective_marker_id)
    terrain_id = _optional_identifier("marker terrain_feature_id", terrain_feature_id)
    if (kind is MarkerAnchorKind.OBJECTIVE) != (objective_id is not None):
        raise GameLifecycleError("Primary mission marker objective anchor drift.")
    if (kind is MarkerAnchorKind.TERRAIN_FEATURE) != (terrain_id is not None):
        raise GameLifecycleError("Primary mission marker terrain anchor drift.")
    created_context = _battle_context(
        label="marker creation",
        battle_round=created_battle_round,
        phase=created_phase,
        active_player_id=created_active_player_id,
        optional=True,
    )
    payload: dict[str, object] = {
        "game_id": _identifier("marker game_id", game_id),
        "owner_player_id": _identifier("marker owner_player_id", owner_player_id),
        "mission_id": _identifier("marker mission_id", mission_id),
        "source_rule_id": _identifier("marker source_rule_id", source_rule_id),
        "source_descriptor_id": _identifier("marker source_descriptor_id", source_descriptor_id),
        "marker_kind": _identifier("marker kind", marker_kind),
        "anchor_kind": kind.value,
        "objective_marker_id": objective_id,
        "terrain_feature_id": terrain_id,
        "created_battle_round": created_context[0],
        "created_phase": created_context[1],
        "created_active_player_id": created_context[2],
        "source_event_id": _identifier("marker source_event_id", source_event_id),
        "source_result_id": _optional_identifier("marker source_result_id", source_result_id),
        "source_action_id": _optional_identifier("marker source_action_id", source_action_id),
        "source_destruction_id": _optional_identifier(
            "marker source_destruction_id", source_destruction_id
        ),
        "source_designation_id": _optional_identifier(
            "marker source_designation_id", source_designation_id
        ),
    }
    return f"primary-mission-marker:{canonical_payload_sha256(payload)}"


def primary_condemned_selection_id(
    *,
    game_id: str,
    owner_player_id: str,
    mission_id: str,
    source_rule_id: str,
    source_descriptor_id: str,
    battle_round: int,
    active_player_id: str,
    candidate_policy_id: str,
    candidate_rules_unit_instance_ids: tuple[str, ...],
    candidate_evidence_ids: tuple[str, ...],
    selected_rules_unit_instance_ids: tuple[str, ...],
    minimum_selection_count: int,
    maximum_selection_count: int,
    used_fallback_candidates: bool,
    selection_request_id: str | None,
    selection_result_id: str | None,
    source_event_id: str,
) -> str:
    candidates = _identifier_tuple(
        "condemned selection candidate_rules_unit_instance_ids",
        candidate_rules_unit_instance_ids,
        allow_empty=True,
    )
    evidence_ids = _identifier_tuple(
        "condemned selection candidate_evidence_ids",
        candidate_evidence_ids,
        allow_empty=True,
    )
    selected = _identifier_tuple(
        "condemned selection selected_rules_unit_instance_ids",
        selected_rules_unit_instance_ids,
        allow_empty=True,
    )
    payload: dict[str, object] = {
        "game_id": _identifier("condemned selection game_id", game_id),
        "owner_player_id": _identifier("condemned selection owner_player_id", owner_player_id),
        "mission_id": _identifier("condemned selection mission_id", mission_id),
        "source_rule_id": _identifier("condemned selection source_rule_id", source_rule_id),
        "source_descriptor_id": _identifier(
            "condemned selection source_descriptor_id", source_descriptor_id
        ),
        "battle_round": _positive_int("condemned selection battle_round", battle_round),
        "active_player_id": _identifier("condemned selection active_player_id", active_player_id),
        "candidate_policy_id": _identifier(
            "condemned selection candidate_policy_id", candidate_policy_id
        ),
        "candidate_rules_unit_instance_ids": list(candidates),
        "candidate_evidence_ids": list(evidence_ids),
        "selected_rules_unit_instance_ids": list(selected),
        "minimum_selection_count": _non_negative_int(
            "condemned selection minimum_selection_count", minimum_selection_count
        ),
        "maximum_selection_count": _non_negative_int(
            "condemned selection maximum_selection_count", maximum_selection_count
        ),
        "used_fallback_candidates": _bool(
            "condemned selection used_fallback_candidates", used_fallback_candidates
        ),
        "selection_request_id": _optional_identifier(
            "condemned selection selection_request_id", selection_request_id
        ),
        "selection_result_id": _optional_identifier(
            "condemned selection selection_result_id", selection_result_id
        ),
        "source_event_id": _identifier("condemned selection source_event_id", source_event_id),
    }
    return f"primary-condemned-selection:{canonical_payload_sha256(payload)}"


def primary_consecration_designation_id(
    *,
    game_id: str,
    owner_player_id: str,
    mission_id: str,
    source_rule_id: str,
    source_descriptor_id: str,
    rules_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
    source_destruction_id: str,
    created_battle_round: int,
    created_phase: str,
    created_active_player_id: str,
    source_event_id: str,
) -> str:
    payload: dict[str, object] = {
        "game_id": _identifier("consecration designation game_id", game_id),
        "owner_player_id": _identifier("consecration designation owner_player_id", owner_player_id),
        "mission_id": _identifier("consecration designation mission_id", mission_id),
        "source_rule_id": _identifier("consecration designation source_rule_id", source_rule_id),
        "source_descriptor_id": _identifier(
            "consecration designation source_descriptor_id", source_descriptor_id
        ),
        "rules_unit_instance_id": _identifier(
            "consecration designation rules_unit_instance_id", rules_unit_instance_id
        ),
        "component_unit_instance_ids": list(
            _identifier_tuple(
                "consecration designation component_unit_instance_ids",
                component_unit_instance_ids,
                allow_empty=False,
            )
        ),
        "source_destruction_id": _identifier(
            "consecration designation source_destruction_id", source_destruction_id
        ),
        "created_battle_round": _positive_int(
            "consecration designation created_battle_round", created_battle_round
        ),
        "created_phase": _identifier("consecration designation created_phase", created_phase),
        "created_active_player_id": _identifier(
            "consecration designation created_active_player_id", created_active_player_id
        ),
        "source_event_id": _identifier("consecration designation source_event_id", source_event_id),
    }
    return f"primary-consecration-designation:{canonical_payload_sha256(payload)}"


def _validate_marker_anchor(marker: PrimaryMissionMarkerState) -> None:
    if marker.anchor_kind is MarkerAnchorKind.OBJECTIVE:
        if marker.objective_marker_id is None or marker.terrain_feature_id is not None:
            raise GameLifecycleError(
                "An objective-anchored primary mission marker requires only objective_marker_id."
            )
    elif marker.terrain_feature_id is None or marker.objective_marker_id is not None:
        raise GameLifecycleError(
            "A terrain-anchored primary mission marker requires only terrain_feature_id."
        )


def _validate_marker_removal(marker: PrimaryMissionMarkerState) -> None:
    optional_fields = (
        marker.removed_battle_round,
        marker.removed_phase,
        marker.removed_active_player_id,
        marker.removal_source_id,
        marker.removal_event_id,
        marker.removal_result_id,
        marker.removal_action_id,
    )
    if marker.status is PrimaryMissionMarkerStatus.ACTIVE:
        if any(value is not None for value in optional_fields):
            raise GameLifecycleError("An active primary mission marker cannot have removal data.")
        return
    removed_context = _battle_context(
        label="marker removal",
        battle_round=marker.removed_battle_round,
        phase=marker.removed_phase,
        active_player_id=marker.removed_active_player_id,
        optional=False,
    )
    object.__setattr__(marker, "removed_battle_round", removed_context[0])
    object.__setattr__(marker, "removed_phase", removed_context[1])
    object.__setattr__(marker, "removed_active_player_id", removed_context[2])
    object.__setattr__(
        marker,
        "removal_source_id",
        _identifier("marker removal_source_id", marker.removal_source_id),
    )
    object.__setattr__(
        marker,
        "removal_event_id",
        _identifier("marker removal_event_id", marker.removal_event_id),
    )
    object.__setattr__(
        marker,
        "removal_result_id",
        _optional_identifier("marker removal_result_id", marker.removal_result_id),
    )
    object.__setattr__(
        marker,
        "removal_action_id",
        _optional_identifier("marker removal_action_id", marker.removal_action_id),
    )


def _validate_designation_consumption(
    designation: PrimaryConsecrationDesignationState,
) -> None:
    optional_fields = (
        designation.consumed_marker_id,
        designation.consumed_battle_round,
        designation.consumed_phase,
        designation.consumed_active_player_id,
        designation.consumption_source_id,
        designation.consumption_event_id,
        designation.consumption_result_id,
    )
    if designation.status is PrimaryConsecrationStatus.ACTIVE:
        if any(value is not None for value in optional_fields):
            raise GameLifecycleError(
                "An active consecration designation cannot have consumption data."
            )
        return
    consumed_context = _battle_context(
        label="consecration designation consumption",
        battle_round=designation.consumed_battle_round,
        phase=designation.consumed_phase,
        active_player_id=designation.consumed_active_player_id,
        optional=False,
    )
    object.__setattr__(designation, "consumed_battle_round", consumed_context[0])
    object.__setattr__(designation, "consumed_phase", consumed_context[1])
    object.__setattr__(designation, "consumed_active_player_id", consumed_context[2])
    if consumed_context[2] != designation.owner_player_id:
        raise GameLifecycleError("Consecration designation must be consumed in its owner turn.")
    if (consumed_context[0], consumed_context[2]) == (
        designation.last_resolved_battle_round,
        designation.last_resolved_active_player_id,
    ):
        raise GameLifecycleError("A declined designation cannot be consumed in the same turn.")
    for field_name in (
        "consumed_marker_id",
        "consumption_source_id",
        "consumption_event_id",
        "consumption_result_id",
    ):
        object.__setattr__(
            designation,
            field_name,
            _identifier(
                f"consecration designation {field_name}",
                getattr(designation, field_name),
            ),
        )


def _validate_designation_last_resolution(
    designation: PrimaryConsecrationDesignationState,
) -> None:
    required_values = (
        designation.last_resolved_battle_round,
        designation.last_resolved_active_player_id,
        designation.last_resolution_event_id,
    )
    if all(value is None for value in required_values):
        if designation.last_resolution_result_id is not None:
            raise GameLifecycleError(
                "Consecration result provenance requires a resolved owner turn."
            )
        return
    if any(value is None for value in required_values):
        raise GameLifecycleError(
            "Consecration last-resolution turn and event must be recorded together."
        )
    battle_round = _positive_int(
        "consecration last_resolved_battle_round",
        designation.last_resolved_battle_round,
    )
    active_player_id = _identifier(
        "consecration last_resolved_active_player_id",
        designation.last_resolved_active_player_id,
    )
    if battle_round < designation.created_battle_round:
        raise GameLifecycleError("Consecration resolution cannot predate its designation.")
    if active_player_id != designation.owner_player_id:
        raise GameLifecycleError("Consecration no-selection resolution must be an owner turn.")
    object.__setattr__(designation, "last_resolved_battle_round", battle_round)
    object.__setattr__(designation, "last_resolved_active_player_id", active_player_id)
    object.__setattr__(
        designation,
        "last_resolution_event_id",
        _identifier(
            "consecration last_resolution_event_id",
            designation.last_resolution_event_id,
        ),
    )
    object.__setattr__(
        designation,
        "last_resolution_result_id",
        _optional_identifier(
            "consecration last_resolution_result_id",
            designation.last_resolution_result_id,
        ),
    )


def _battle_context(
    *,
    label: str,
    battle_round: object,
    phase: object,
    active_player_id: object,
    optional: bool,
) -> tuple[int | None, str | None, str | None]:
    values = (battle_round, phase, active_player_id)
    if optional and all(value is None for value in values):
        return None, None, None
    if any(value is None for value in values):
        raise GameLifecycleError(f"{label} battle context must be all present or all absent.")
    return (
        _positive_int(f"{label} battle_round", battle_round),
        _identifier(f"{label} phase", phase),
        _identifier(f"{label} active_player_id", active_player_id),
    )


def _typed_tuple[T](
    label: str,
    values: object,
    expected_type: type[T],
    *,
    id_attribute: str,
) -> tuple[T, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{label} must be a tuple.")
    typed_values: list[T] = []
    seen_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        _exact_type(label, value, expected_type)
        typed_value = cast(T, value)
        record_id = cast(str, getattr(typed_value, id_attribute))
        if record_id in seen_ids:
            raise GameLifecycleError(f"{label} must not contain duplicate identities.")
        seen_ids.add(record_id)
        typed_values.append(typed_value)
    return tuple(sorted(typed_values, key=lambda value: cast(str, getattr(value, id_attribute))))


def _replace_by_id[T](
    values: tuple[T, ...],
    replacement: T,
    id_attribute: str,
    label: str,
) -> tuple[T, ...]:
    replacement_id = cast(str, getattr(replacement, id_attribute))
    if all(cast(str, getattr(value, id_attribute)) != replacement_id for value in values):
        raise GameLifecycleError(f"Cannot replace unknown {label}.")
    return tuple(
        replacement if cast(str, getattr(value, id_attribute)) == replacement_id else value
        for value in values
    )


def _exact_type[T](label: str, value: object, expected_type: type[T]) -> None:
    if type(value) is not expected_type:
        raise GameLifecycleError(f"{label} must contain typed {expected_type.__name__} values.")


def _payload_mapping(
    payload: object,
    *,
    payload_name: str,
    keys: tuple[str, ...],
) -> dict[str, object]:
    if type(payload) is not dict:
        raise GameLifecycleError(f"{payload_name} payload must be an object.")
    raw = cast(dict[str, object], payload)
    missing = tuple(key for key in keys if key not in raw)
    if missing:
        raise GameLifecycleError(f"{payload_name} payload is missing field: {missing[0]}.")
    unexpected = tuple(sorted(set(raw).difference(keys)))
    if unexpected:
        raise GameLifecycleError(
            f"{payload_name} payload contains unexpected field: {unexpected[0]}."
        )
    return raw


def _payload_list(value: object, label: str) -> list[object]:
    if type(value) is not list:
        raise GameLifecycleError(f"{label} must be a list.")
    return cast(list[object], value)


def _payload_identifier_tuple(value: object, label: str) -> tuple[str, ...]:
    return tuple(cast(list[str], _payload_list(value, label)))


def _identifier_tuple(label: str, value: object, *, allow_empty: bool) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{label} must be a tuple.")
    identifiers = tuple(
        _identifier(f"{label} value", item) for item in cast(tuple[object, ...], value)
    )
    if not allow_empty and not identifiers:
        raise GameLifecycleError(f"{label} must not be empty.")
    if len(identifiers) != len(set(identifiers)):
        raise GameLifecycleError(f"{label} must not contain duplicates.")
    return tuple(sorted(identifiers))


def _optional_identifier(label: str, value: object) -> str | None:
    if value is None:
        return None
    return _identifier(label, value)


def _positive_int(label: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"{label} must be a positive integer.")
    return value


def _non_negative_int(label: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"{label} must be a non-negative integer.")
    return value


def _bool(label: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{label} must be a bool.")
    return value


def _marker_anchor_kind(value: object) -> MarkerAnchorKind:
    if type(value) is MarkerAnchorKind:
        return value
    token = _identifier("marker anchor_kind", value)
    try:
        return MarkerAnchorKind(token)
    except ValueError as exc:
        raise GameLifecycleError("Primary mission marker anchor_kind is unsupported.") from exc


def _marker_status(value: object) -> PrimaryMissionMarkerStatus:
    if type(value) is PrimaryMissionMarkerStatus:
        return value
    token = _identifier("marker status", value)
    try:
        return PrimaryMissionMarkerStatus(token)
    except ValueError as exc:
        raise GameLifecycleError("Primary mission marker status is unsupported.") from exc


def _consecration_status(value: object) -> PrimaryConsecrationStatus:
    if type(value) is PrimaryConsecrationStatus:
        return value
    token = _identifier("consecration designation status", value)
    try:
        return PrimaryConsecrationStatus(token)
    except ValueError as exc:
        raise GameLifecycleError("Primary consecration status is unsupported.") from exc


_identifier = IdentifierValidator(GameLifecycleError)

__all__ = (
    "MarkerAnchorKind",
    "PrimaryCondemnedSelectionState",
    "PrimaryCondemnedSelectionStatePayload",
    "PrimaryConsecrationDesignationState",
    "PrimaryConsecrationDesignationStatePayload",
    "PrimaryConsecrationStatus",
    "PrimaryMissionMarkerState",
    "PrimaryMissionMarkerStatePayload",
    "PrimaryMissionMarkerStatus",
    "PrimaryMissionProgressState",
    "PrimaryMissionProgressStatePayload",
    "is_consecrated_objective_marker",
    "primary_condemned_selection_id",
    "primary_consecration_designation_id",
    "primary_mission_marker_id",
)
