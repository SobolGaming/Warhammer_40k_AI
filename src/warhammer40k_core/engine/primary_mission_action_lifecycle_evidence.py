from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlResult,
    ObjectiveControlResultPayload,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    RulesUnitObjectiveProximityWitness,
)
from warhammer40k_core.engine.primary_mission_action_battlefield_evidence import (
    MissionActionBattlefieldBoundaryEvidence,
)

PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY = "mission_action_start_evidence"
PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY = "mission_action_completion_evidence"
PRIMARY_MISSION_ACTION_START_EVIDENCE_SCHEMA = "primary-mission-action-start-evidence-v1"
PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_SCHEMA = "primary-mission-action-completion-evidence-v1"

PRIMARY_MISSION_ACTION_MARKER_EFFECTS = frozenset(
    {
        "central_objective_gains_operation_marker_if_action_unit_controls_target_at_turn_end",
        "objective_becomes_decoy_if_action_unit_controls_target_at_turn_end",
        "objective_becomes_triangulated_if_action_unit_controls_target_at_turn_end",
        "objective_gains_operation_marker_if_action_unit_controls_target_at_turn_end",
    }
)
PRIMARY_MISSION_ACTION_SENSOR_EFFECTS = frozenset(
    {
        "remove_one_friendly_operation_marker_if_action_unit_controls_selected_central_objective_at_turn_end",
        "remove_one_opponent_operation_marker_if_action_unit_controls_selected_central_objective_at_turn_end",
    }
)
PRIMARY_MISSION_ACTION_OBJECTIVE_CONTROL_EFFECTS = frozenset(
    {
        *PRIMARY_MISSION_ACTION_MARKER_EFFECTS,
        *PRIMARY_MISSION_ACTION_SENSOR_EFFECTS,
        "unit_commits_sabotage_if_action_unit_controls_target_at_turn_end",
        "unit_secures_asset_if_action_unit_controls_target_at_turn_end",
    }
)
PRIMARY_MISSION_ACTION_VANGUARD_EFFECT = (
    "unit_performs_vanguard_operation_if_no_enemy_units_in_terrain_area_at_turn_end"
)
PRIMARY_MISSION_ACTION_SURVEIL_EFFECT = "enemy_unit_becomes_surveilled_until_turn_end"


_validate_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class MissionActionPriorUseEvidence:
    action_id: str
    mission_action_id: str
    player_id: str
    battle_round_started: int
    phase_started: str
    unit_instance_id: str
    unit_identity_ids: tuple[str, ...]
    target_id: str
    target_rules_unit_identity_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name, value in (
            ("action_id", self.action_id),
            ("mission_action_id", self.mission_action_id),
            ("player_id", self.player_id),
            ("phase_started", self.phase_started),
            ("unit_instance_id", self.unit_instance_id),
            ("target_id", self.target_id),
        ):
            object.__setattr__(self, field_name, _validate_identifier(field_name, value))
        object.__setattr__(
            self,
            "battle_round_started",
            _positive_int("battle_round_started", self.battle_round_started),
        )
        object.__setattr__(
            self,
            "unit_identity_ids",
            canonical_identifier_tuple(
                "unit_identity_ids", self.unit_identity_ids, require_non_empty=True
            ),
        )
        object.__setattr__(
            self,
            "target_rules_unit_identity_ids",
            canonical_identifier_tuple(
                "target_rules_unit_identity_ids",
                self.target_rules_unit_identity_ids,
                require_non_empty=False,
            ),
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "action_id": self.action_id,
            "mission_action_id": self.mission_action_id,
            "player_id": self.player_id,
            "battle_round_started": self.battle_round_started,
            "phase_started": self.phase_started,
            "unit_instance_id": self.unit_instance_id,
            "unit_identity_ids": list(self.unit_identity_ids),
            "target_id": self.target_id,
            "target_rules_unit_identity_ids": list(self.target_rules_unit_identity_ids),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_mapping(
            payload,
            label="MissionActionPriorUseEvidence",
            keys=(
                "action_id",
                "mission_action_id",
                "player_id",
                "battle_round_started",
                "phase_started",
                "unit_instance_id",
                "unit_identity_ids",
                "target_id",
                "target_rules_unit_identity_ids",
            ),
        )
        return cls(
            action_id=_string(raw, "action_id"),
            mission_action_id=_string(raw, "mission_action_id"),
            player_id=_string(raw, "player_id"),
            battle_round_started=_int(raw, "battle_round_started"),
            phase_started=_string(raw, "phase_started"),
            unit_instance_id=_string(raw, "unit_instance_id"),
            unit_identity_ids=_string_tuple(raw, "unit_identity_ids"),
            target_id=_string(raw, "target_id"),
            target_rules_unit_identity_ids=_string_tuple(raw, "target_rules_unit_identity_ids"),
        )


@dataclass(frozen=True, slots=True)
class MissionActionTerrainIntersectionEvidence:
    logical_terrain_area_id: str
    owner_player_id: str
    rules_unit_instance_id: str
    component_unit_instance_id: str
    model_instance_id: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("logical_terrain_area_id", self.logical_terrain_area_id),
            ("owner_player_id", self.owner_player_id),
            ("rules_unit_instance_id", self.rules_unit_instance_id),
            ("component_unit_instance_id", self.component_unit_instance_id),
            ("model_instance_id", self.model_instance_id),
        ):
            object.__setattr__(self, field_name, _validate_identifier(field_name, value))

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "logical_terrain_area_id": self.logical_terrain_area_id,
            "owner_player_id": self.owner_player_id,
            "rules_unit_instance_id": self.rules_unit_instance_id,
            "component_unit_instance_id": self.component_unit_instance_id,
            "model_instance_id": self.model_instance_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_mapping(
            payload,
            label="MissionActionTerrainIntersectionEvidence",
            keys=(
                "logical_terrain_area_id",
                "owner_player_id",
                "rules_unit_instance_id",
                "component_unit_instance_id",
                "model_instance_id",
            ),
        )
        return cls(
            logical_terrain_area_id=_string(raw, "logical_terrain_area_id"),
            owner_player_id=_string(raw, "owner_player_id"),
            rules_unit_instance_id=_string(raw, "rules_unit_instance_id"),
            component_unit_instance_id=_string(raw, "component_unit_instance_id"),
            model_instance_id=_string(raw, "model_instance_id"),
        )


@dataclass(frozen=True, slots=True)
class MissionActionSurveilTargetEvidence:
    target_rules_unit_instance_id: str
    target_rules_unit_identity_ids: tuple[str, ...]
    target_owner_player_id: str
    placed_alive_target_model_instance_ids: tuple[str, ...]
    observer_component_unit_instance_ids_within_18: tuple[str, ...]
    observer_component_unit_instance_ids_with_line_of_sight: tuple[str, ...]
    visibility_cache_key: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("target_rules_unit_instance_id", self.target_rules_unit_instance_id),
            ("target_owner_player_id", self.target_owner_player_id),
            ("visibility_cache_key", self.visibility_cache_key),
        ):
            object.__setattr__(self, field_name, _validate_identifier(field_name, value))
        for field_name in (
            "target_rules_unit_identity_ids",
            "placed_alive_target_model_instance_ids",
            "observer_component_unit_instance_ids_within_18",
            "observer_component_unit_instance_ids_with_line_of_sight",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier_tuple(
                    field_name,
                    cast(tuple[str, ...], getattr(self, field_name)),
                    require_non_empty=(field_name == "target_rules_unit_identity_ids"),
                ),
            )

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "target_rules_unit_instance_id": self.target_rules_unit_instance_id,
            "target_rules_unit_identity_ids": list(self.target_rules_unit_identity_ids),
            "target_owner_player_id": self.target_owner_player_id,
            "placed_alive_target_model_instance_ids": list(
                self.placed_alive_target_model_instance_ids
            ),
            "observer_component_unit_instance_ids_within_18": list(
                self.observer_component_unit_instance_ids_within_18
            ),
            "observer_component_unit_instance_ids_with_line_of_sight": list(
                self.observer_component_unit_instance_ids_with_line_of_sight
            ),
            "visibility_cache_key": self.visibility_cache_key,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_mapping(
            payload,
            label="MissionActionSurveilTargetEvidence",
            keys=(
                "target_rules_unit_instance_id",
                "target_rules_unit_identity_ids",
                "target_owner_player_id",
                "placed_alive_target_model_instance_ids",
                "observer_component_unit_instance_ids_within_18",
                "observer_component_unit_instance_ids_with_line_of_sight",
                "visibility_cache_key",
            ),
        )
        return cls(
            target_rules_unit_instance_id=_string(raw, "target_rules_unit_instance_id"),
            target_rules_unit_identity_ids=_string_tuple(raw, "target_rules_unit_identity_ids"),
            target_owner_player_id=_string(raw, "target_owner_player_id"),
            placed_alive_target_model_instance_ids=_string_tuple(
                raw, "placed_alive_target_model_instance_ids"
            ),
            observer_component_unit_instance_ids_within_18=_string_tuple(
                raw, "observer_component_unit_instance_ids_within_18"
            ),
            observer_component_unit_instance_ids_with_line_of_sight=_string_tuple(
                raw, "observer_component_unit_instance_ids_with_line_of_sight"
            ),
            visibility_cache_key=_string(raw, "visibility_cache_key"),
        )


@dataclass(frozen=True, slots=True)
class MissionActionStartCandidateUnitEvidence:
    unit_instance_id: str
    unit_identity_ids: tuple[str, ...]
    component_unit_instance_ids: tuple[str, ...]
    alive_model_instance_ids: tuple[str, ...]
    placed_alive_model_instance_ids: tuple[str, ...]
    positive_objective_control_model_instance_ids: tuple[str, ...]
    keyword_tokens: tuple[str, ...]
    battle_shocked: bool
    within_enemy_engagement_range: bool
    advanced_unit_instance_ids: tuple[str, ...]
    fell_back_unit_instance_ids: tuple[str, ...]
    shot_unit_instance_ids: tuple[str, ...]
    unit_ineligibility_reason: str | None
    objective_proximity_witness: RulesUnitObjectiveProximityWitness
    surveil_target_evidence: tuple[MissionActionSurveilTargetEvidence, ...]
    legal_primary_option_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        for field_name, require_non_empty in (
            ("unit_identity_ids", True),
            ("component_unit_instance_ids", True),
            ("alive_model_instance_ids", False),
            ("placed_alive_model_instance_ids", False),
            ("positive_objective_control_model_instance_ids", False),
            ("keyword_tokens", False),
            ("advanced_unit_instance_ids", False),
            ("fell_back_unit_instance_ids", False),
            ("shot_unit_instance_ids", False),
            ("legal_primary_option_ids", False),
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier_tuple(
                    field_name,
                    cast(tuple[str, ...], getattr(self, field_name)),
                    require_non_empty=require_non_empty,
                ),
            )
        for field_name in ("battle_shocked", "within_enemy_engagement_range"):
            if type(getattr(self, field_name)) is not bool:
                raise GameLifecycleError(
                    f"Primary Mission Action candidate {field_name} must be a bool."
                )
        object.__setattr__(
            self,
            "unit_ineligibility_reason",
            _optional_identifier("unit_ineligibility_reason", self.unit_ineligibility_reason),
        )
        if type(self.objective_proximity_witness) is not RulesUnitObjectiveProximityWitness:
            raise GameLifecycleError(
                "Primary Mission Action candidate objective witness is invalid."
            )
        object.__setattr__(
            self,
            "surveil_target_evidence",
            canonical_surveil_target_inventory(self.surveil_target_evidence),
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "unit_instance_id": self.unit_instance_id,
                    "unit_identity_ids": list(self.unit_identity_ids),
                    "component_unit_instance_ids": list(self.component_unit_instance_ids),
                    "alive_model_instance_ids": list(self.alive_model_instance_ids),
                    "placed_alive_model_instance_ids": list(self.placed_alive_model_instance_ids),
                    "positive_objective_control_model_instance_ids": list(
                        self.positive_objective_control_model_instance_ids
                    ),
                    "keyword_tokens": list(self.keyword_tokens),
                    "battle_shocked": self.battle_shocked,
                    "within_enemy_engagement_range": self.within_enemy_engagement_range,
                    "advanced_unit_instance_ids": list(self.advanced_unit_instance_ids),
                    "fell_back_unit_instance_ids": list(self.fell_back_unit_instance_ids),
                    "shot_unit_instance_ids": list(self.shot_unit_instance_ids),
                    "unit_ineligibility_reason": self.unit_ineligibility_reason,
                    "objective_proximity_witness": (self.objective_proximity_witness.to_payload()),
                    "surveil_target_evidence": [
                        item.to_payload() for item in self.surveil_target_evidence
                    ],
                    "legal_primary_option_ids": list(self.legal_primary_option_ids),
                }
            ),
        )

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        keys = (
            "unit_instance_id",
            "unit_identity_ids",
            "component_unit_instance_ids",
            "alive_model_instance_ids",
            "placed_alive_model_instance_ids",
            "positive_objective_control_model_instance_ids",
            "keyword_tokens",
            "battle_shocked",
            "within_enemy_engagement_range",
            "advanced_unit_instance_ids",
            "fell_back_unit_instance_ids",
            "shot_unit_instance_ids",
            "unit_ineligibility_reason",
            "objective_proximity_witness",
            "surveil_target_evidence",
            "legal_primary_option_ids",
        )
        raw = _payload_mapping(
            payload,
            label="MissionActionStartCandidateUnitEvidence",
            keys=keys,
        )
        return cls(
            unit_instance_id=_string(raw, "unit_instance_id"),
            unit_identity_ids=_string_tuple(raw, "unit_identity_ids"),
            component_unit_instance_ids=_string_tuple(raw, "component_unit_instance_ids"),
            alive_model_instance_ids=_string_tuple(raw, "alive_model_instance_ids"),
            placed_alive_model_instance_ids=_string_tuple(raw, "placed_alive_model_instance_ids"),
            positive_objective_control_model_instance_ids=_string_tuple(
                raw, "positive_objective_control_model_instance_ids"
            ),
            keyword_tokens=_string_tuple(raw, "keyword_tokens"),
            battle_shocked=_bool(raw, "battle_shocked"),
            within_enemy_engagement_range=_bool(raw, "within_enemy_engagement_range"),
            advanced_unit_instance_ids=_string_tuple(raw, "advanced_unit_instance_ids"),
            fell_back_unit_instance_ids=_string_tuple(raw, "fell_back_unit_instance_ids"),
            shot_unit_instance_ids=_string_tuple(raw, "shot_unit_instance_ids"),
            unit_ineligibility_reason=_optional_string(raw, "unit_ineligibility_reason"),
            objective_proximity_witness=RulesUnitObjectiveProximityWitness.from_payload(
                raw["objective_proximity_witness"]
            ),
            surveil_target_evidence=tuple(
                MissionActionSurveilTargetEvidence.from_payload(item)
                for item in _list(raw, "surveil_target_evidence")
            ),
            legal_primary_option_ids=_string_tuple(raw, "legal_primary_option_ids"),
        )


@dataclass(frozen=True, slots=True)
class MissionActionStartAuthorityOptionEvidence:
    option_id: str
    label: str
    payload_json: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("option_id", self.option_id),
            ("label", self.label),
        ):
            object.__setattr__(self, field_name, _validate_identifier(field_name, value))
        object.__setattr__(
            self,
            "payload_json",
            _validate_canonical_json_object("payload_json", self.payload_json),
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "option_id": self.option_id,
            "label": self.label,
            "payload_json": self.payload_json,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_mapping(
            payload,
            label="MissionActionStartAuthorityOptionEvidence",
            keys=("option_id", "label", "payload_json"),
        )
        return cls(
            option_id=_string(raw, "option_id"),
            label=_string(raw, "label"),
            payload_json=_string(raw, "payload_json"),
        )


@dataclass(frozen=True, slots=True)
class MissionActionStartAuthorityEvidence:
    request_kind: str
    request_payload_json: str
    battlefield_boundary: MissionActionBattlefieldBoundaryEvidence
    options: tuple[MissionActionStartAuthorityOptionEvidence, ...]
    candidate_units: tuple[MissionActionStartCandidateUnitEvidence, ...]
    terrain_model_inventory: tuple[MissionActionTerrainModelInventoryEvidence, ...]
    battle_shocked_unit_instance_ids: tuple[str, ...] = ()
    advanced_unit_instance_ids: tuple[str, ...] = ()
    fell_back_unit_instance_ids: tuple[str, ...] = ()
    shot_unit_instance_ids: tuple[str, ...] = ()
    active_secondary_mission_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_kind",
            _validate_identifier("request_kind", self.request_kind),
        )
        object.__setattr__(
            self,
            "request_payload_json",
            _validate_canonical_json_object(
                "request_payload_json",
                self.request_payload_json,
            ),
        )
        if self.request_kind not in {"direct", "opportunity"}:
            raise GameLifecycleError(
                "Primary Mission Action start authority request kind is unsupported."
            )
        if type(self.battlefield_boundary) is not MissionActionBattlefieldBoundaryEvidence:
            raise GameLifecycleError(
                "Primary Mission Action start authority battlefield boundary is invalid."
            )
        if (
            type(self.options) is not tuple
            or not self.options
            or any(
                type(option) is not MissionActionStartAuthorityOptionEvidence
                for option in self.options
            )
        ):
            raise GameLifecycleError(
                "Primary Mission Action start authority option inventory is invalid."
            )
        option_ids = tuple(option.option_id for option in self.options)
        if len(set(option_ids)) != len(option_ids):
            raise GameLifecycleError(
                "Primary Mission Action start authority option inventory is duplicated."
            )
        object.__setattr__(
            self,
            "options",
            tuple(sorted(self.options, key=lambda option: option.option_id)),
        )
        object.__setattr__(
            self,
            "candidate_units",
            canonical_start_candidate_units(self.candidate_units),
        )
        object.__setattr__(
            self,
            "terrain_model_inventory",
            canonical_terrain_model_inventory(self.terrain_model_inventory),
        )
        for field_name in (
            "battle_shocked_unit_instance_ids",
            "advanced_unit_instance_ids",
            "fell_back_unit_instance_ids",
            "shot_unit_instance_ids",
            "active_secondary_mission_ids",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier_tuple(
                    field_name,
                    cast(tuple[str, ...], getattr(self, field_name)),
                    require_non_empty=False,
                ),
            )

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "request_kind": self.request_kind,
            "request_payload_json": self.request_payload_json,
            "battlefield_boundary": cast(
                dict[str, JsonValue],
                self.battlefield_boundary.to_payload(),
            ),
            "options": [option.to_payload() for option in self.options],
            "candidate_units": [item.to_payload() for item in self.candidate_units],
            "terrain_model_inventory": [item.to_payload() for item in self.terrain_model_inventory],
            "battle_shocked_unit_instance_ids": list(self.battle_shocked_unit_instance_ids),
            "advanced_unit_instance_ids": list(self.advanced_unit_instance_ids),
            "fell_back_unit_instance_ids": list(self.fell_back_unit_instance_ids),
            "shot_unit_instance_ids": list(self.shot_unit_instance_ids),
            "active_secondary_mission_ids": list(self.active_secondary_mission_ids),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_mapping(
            payload,
            label="MissionActionStartAuthorityEvidence",
            keys=(
                "request_kind",
                "request_payload_json",
                "battlefield_boundary",
                "options",
                "candidate_units",
                "terrain_model_inventory",
                "battle_shocked_unit_instance_ids",
                "advanced_unit_instance_ids",
                "fell_back_unit_instance_ids",
                "shot_unit_instance_ids",
                "active_secondary_mission_ids",
            ),
        )
        return cls(
            request_kind=_string(raw, "request_kind"),
            request_payload_json=_string(raw, "request_payload_json"),
            battlefield_boundary=MissionActionBattlefieldBoundaryEvidence.from_payload(
                raw["battlefield_boundary"]
            ),
            options=tuple(
                MissionActionStartAuthorityOptionEvidence.from_payload(option)
                for option in _list(raw, "options")
            ),
            candidate_units=tuple(
                MissionActionStartCandidateUnitEvidence.from_payload(item)
                for item in _list(raw, "candidate_units")
            ),
            terrain_model_inventory=tuple(
                MissionActionTerrainModelInventoryEvidence.from_payload(item)
                for item in _list(raw, "terrain_model_inventory")
            ),
            battle_shocked_unit_instance_ids=_string_tuple(raw, "battle_shocked_unit_instance_ids"),
            advanced_unit_instance_ids=_string_tuple(raw, "advanced_unit_instance_ids"),
            fell_back_unit_instance_ids=_string_tuple(raw, "fell_back_unit_instance_ids"),
            shot_unit_instance_ids=_string_tuple(raw, "shot_unit_instance_ids"),
            active_secondary_mission_ids=_string_tuple(raw, "active_secondary_mission_ids"),
        )


@dataclass(frozen=True, slots=True)
class MissionActionTerrainModelInventoryEvidence:
    owner_player_id: str
    rules_unit_instance_id: str
    component_unit_instance_id: str
    model_instance_id: str
    wounds_remaining_at_boundary: int
    model_placement_json: str | None
    source_objective_control_json: str
    resolved_objective_control_json: str
    logical_terrain_area_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name, value in (
            ("owner_player_id", self.owner_player_id),
            ("rules_unit_instance_id", self.rules_unit_instance_id),
            ("component_unit_instance_id", self.component_unit_instance_id),
            ("model_instance_id", self.model_instance_id),
        ):
            object.__setattr__(self, field_name, _validate_identifier(field_name, value))
        object.__setattr__(
            self,
            "wounds_remaining_at_boundary",
            _non_negative_int("wounds_remaining_at_boundary", self.wounds_remaining_at_boundary),
        )
        object.__setattr__(
            self,
            "model_placement_json",
            _optional_canonical_json_object("model_placement_json", self.model_placement_json),
        )
        for field_name in (
            "source_objective_control_json",
            "resolved_objective_control_json",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_canonical_json_object(field_name, getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "logical_terrain_area_ids",
            canonical_identifier_tuple(
                "logical_terrain_area_ids",
                self.logical_terrain_area_ids,
                require_non_empty=False,
            ),
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "owner_player_id": self.owner_player_id,
            "rules_unit_instance_id": self.rules_unit_instance_id,
            "component_unit_instance_id": self.component_unit_instance_id,
            "model_instance_id": self.model_instance_id,
            "wounds_remaining_at_boundary": self.wounds_remaining_at_boundary,
            "model_placement_json": self.model_placement_json,
            "source_objective_control_json": self.source_objective_control_json,
            "resolved_objective_control_json": self.resolved_objective_control_json,
            "logical_terrain_area_ids": list(self.logical_terrain_area_ids),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_mapping(
            payload,
            label="MissionActionTerrainModelInventoryEvidence",
            keys=(
                "owner_player_id",
                "rules_unit_instance_id",
                "component_unit_instance_id",
                "model_instance_id",
                "wounds_remaining_at_boundary",
                "model_placement_json",
                "source_objective_control_json",
                "resolved_objective_control_json",
                "logical_terrain_area_ids",
            ),
        )
        return cls(
            owner_player_id=_string(raw, "owner_player_id"),
            rules_unit_instance_id=_string(raw, "rules_unit_instance_id"),
            component_unit_instance_id=_string(raw, "component_unit_instance_id"),
            model_instance_id=_string(raw, "model_instance_id"),
            wounds_remaining_at_boundary=_int(raw, "wounds_remaining_at_boundary"),
            model_placement_json=_optional_string(raw, "model_placement_json"),
            source_objective_control_json=_string(raw, "source_objective_control_json"),
            resolved_objective_control_json=_string(raw, "resolved_objective_control_json"),
            logical_terrain_area_ids=_string_tuple(raw, "logical_terrain_area_ids"),
        )


@dataclass(frozen=True, slots=True)
class PrimaryMissionActionStartEvidence:
    schema_version: str
    game_id: str
    player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    mission_action_id: str
    mission_id: str
    source_id: str
    eligible_unit_policy: str
    target_policy: str
    use_limit: str
    effect_descriptor: str
    unit_instance_id: str
    unit_identity_ids: tuple[str, ...]
    component_unit_instance_ids: tuple[str, ...]
    eligible_unit_instance_ids: tuple[str, ...]
    target_id: str
    condition_target_id: str | None
    ruleset_descriptor_hash: str
    unit_owner_player_id: str
    placed_alive_model_instance_ids: tuple[str, ...]
    positive_objective_control_model_instance_ids: tuple[str, ...]
    keyword_tokens: tuple[str, ...]
    battle_shocked: bool
    within_enemy_engagement_range: bool
    advanced_unit_instance_ids: tuple[str, ...]
    fell_back_unit_instance_ids: tuple[str, ...]
    shot_unit_instance_ids: tuple[str, ...]
    unit_ineligibility_reason: str | None
    objective_proximity_witness: RulesUnitObjectiveProximityWitness | None
    active_primary_mission_marker_ids: tuple[str, ...]
    enemy_territory_logical_terrain_area_ids: tuple[str, ...]
    terrain_intersections: tuple[MissionActionTerrainIntersectionEvidence, ...]
    surveil_target_evidence: MissionActionSurveilTargetEvidence | None
    prior_uses: tuple[MissionActionPriorUseEvidence, ...]
    start_authority: MissionActionStartAuthorityEvidence

    def __post_init__(self) -> None:
        for field_name, value in (
            ("schema_version", self.schema_version),
            ("game_id", self.game_id),
            ("player_id", self.player_id),
            ("active_player_id", self.active_player_id),
            ("phase", self.phase),
            ("mission_action_id", self.mission_action_id),
            ("mission_id", self.mission_id),
            ("source_id", self.source_id),
            ("eligible_unit_policy", self.eligible_unit_policy),
            ("target_policy", self.target_policy),
            ("use_limit", self.use_limit),
            ("effect_descriptor", self.effect_descriptor),
            ("unit_instance_id", self.unit_instance_id),
            ("target_id", self.target_id),
            ("ruleset_descriptor_hash", self.ruleset_descriptor_hash),
            ("unit_owner_player_id", self.unit_owner_player_id),
        ):
            object.__setattr__(self, field_name, _validate_identifier(field_name, value))
        if self.schema_version != PRIMARY_MISSION_ACTION_START_EVIDENCE_SCHEMA:
            raise GameLifecycleError("Primary Mission Action start evidence schema is unsupported.")
        object.__setattr__(self, "battle_round", _positive_int("battle_round", self.battle_round))
        object.__setattr__(
            self,
            "condition_target_id",
            _optional_identifier("condition_target_id", self.condition_target_id),
        )
        for field_name, require_non_empty in (
            ("unit_identity_ids", True),
            ("component_unit_instance_ids", True),
            ("eligible_unit_instance_ids", True),
            ("placed_alive_model_instance_ids", False),
            ("positive_objective_control_model_instance_ids", False),
            ("keyword_tokens", False),
            ("advanced_unit_instance_ids", False),
            ("fell_back_unit_instance_ids", False),
            ("shot_unit_instance_ids", False),
            ("active_primary_mission_marker_ids", False),
            ("enemy_territory_logical_terrain_area_ids", False),
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier_tuple(
                    field_name,
                    cast(tuple[str, ...], getattr(self, field_name)),
                    require_non_empty=require_non_empty,
                ),
            )
        for field_name in ("battle_shocked", "within_enemy_engagement_range"):
            if type(getattr(self, field_name)) is not bool:
                raise GameLifecycleError(f"Primary Mission Action {field_name} must be a bool.")
        object.__setattr__(
            self,
            "unit_ineligibility_reason",
            _optional_identifier("unit_ineligibility_reason", self.unit_ineligibility_reason),
        )
        if (
            self.objective_proximity_witness is not None
            and type(self.objective_proximity_witness) is not RulesUnitObjectiveProximityWitness
        ):
            raise GameLifecycleError(
                "Primary Mission Action objective proximity evidence is invalid."
            )
        object.__setattr__(
            self,
            "terrain_intersections",
            canonical_terrain_intersections(self.terrain_intersections),
        )
        if (
            self.surveil_target_evidence is not None
            and type(self.surveil_target_evidence) is not MissionActionSurveilTargetEvidence
        ):
            raise GameLifecycleError("Primary Mission Action Surveil evidence is invalid.")
        object.__setattr__(
            self,
            "prior_uses",
            canonical_mission_action_prior_uses(self.prior_uses),
        )
        if type(self.start_authority) is not MissionActionStartAuthorityEvidence:
            raise GameLifecycleError("Primary Mission Action complete start authority is invalid.")

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "schema_version": self.schema_version,
                    "game_id": self.game_id,
                    "player_id": self.player_id,
                    "active_player_id": self.active_player_id,
                    "battle_round": self.battle_round,
                    "phase": self.phase,
                    "mission_action_id": self.mission_action_id,
                    "mission_id": self.mission_id,
                    "source_id": self.source_id,
                    "eligible_unit_policy": self.eligible_unit_policy,
                    "target_policy": self.target_policy,
                    "use_limit": self.use_limit,
                    "effect_descriptor": self.effect_descriptor,
                    "unit_instance_id": self.unit_instance_id,
                    "unit_identity_ids": list(self.unit_identity_ids),
                    "component_unit_instance_ids": list(self.component_unit_instance_ids),
                    "eligible_unit_instance_ids": list(self.eligible_unit_instance_ids),
                    "target_id": self.target_id,
                    "condition_target_id": self.condition_target_id,
                    "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
                    "unit_owner_player_id": self.unit_owner_player_id,
                    "placed_alive_model_instance_ids": list(self.placed_alive_model_instance_ids),
                    "positive_objective_control_model_instance_ids": list(
                        self.positive_objective_control_model_instance_ids
                    ),
                    "keyword_tokens": list(self.keyword_tokens),
                    "battle_shocked": self.battle_shocked,
                    "within_enemy_engagement_range": self.within_enemy_engagement_range,
                    "advanced_unit_instance_ids": list(self.advanced_unit_instance_ids),
                    "fell_back_unit_instance_ids": list(self.fell_back_unit_instance_ids),
                    "shot_unit_instance_ids": list(self.shot_unit_instance_ids),
                    "unit_ineligibility_reason": self.unit_ineligibility_reason,
                    "objective_proximity_witness": (
                        None
                        if self.objective_proximity_witness is None
                        else self.objective_proximity_witness.to_payload()
                    ),
                    "active_primary_mission_marker_ids": list(
                        self.active_primary_mission_marker_ids
                    ),
                    "enemy_territory_logical_terrain_area_ids": list(
                        self.enemy_territory_logical_terrain_area_ids
                    ),
                    "terrain_intersections": [
                        item.to_payload() for item in self.terrain_intersections
                    ],
                    "surveil_target_evidence": (
                        None
                        if self.surveil_target_evidence is None
                        else self.surveil_target_evidence.to_payload()
                    ),
                    "prior_uses": [item.to_payload() for item in self.prior_uses],
                    "start_authority": self.start_authority.to_payload(),
                }
            ),
        )

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        keys = (
            "schema_version",
            "game_id",
            "player_id",
            "active_player_id",
            "battle_round",
            "phase",
            "mission_action_id",
            "mission_id",
            "source_id",
            "eligible_unit_policy",
            "target_policy",
            "use_limit",
            "effect_descriptor",
            "unit_instance_id",
            "unit_identity_ids",
            "component_unit_instance_ids",
            "eligible_unit_instance_ids",
            "target_id",
            "condition_target_id",
            "ruleset_descriptor_hash",
            "unit_owner_player_id",
            "placed_alive_model_instance_ids",
            "positive_objective_control_model_instance_ids",
            "keyword_tokens",
            "battle_shocked",
            "within_enemy_engagement_range",
            "advanced_unit_instance_ids",
            "fell_back_unit_instance_ids",
            "shot_unit_instance_ids",
            "unit_ineligibility_reason",
            "objective_proximity_witness",
            "active_primary_mission_marker_ids",
            "enemy_territory_logical_terrain_area_ids",
            "terrain_intersections",
            "surveil_target_evidence",
            "prior_uses",
            "start_authority",
        )
        raw = _payload_mapping(payload, label="PrimaryMissionActionStartEvidence", keys=keys)
        objective_payload = raw["objective_proximity_witness"]
        surveil_payload = raw["surveil_target_evidence"]
        return cls(
            schema_version=_string(raw, "schema_version"),
            game_id=_string(raw, "game_id"),
            player_id=_string(raw, "player_id"),
            active_player_id=_string(raw, "active_player_id"),
            battle_round=_int(raw, "battle_round"),
            phase=_string(raw, "phase"),
            mission_action_id=_string(raw, "mission_action_id"),
            mission_id=_string(raw, "mission_id"),
            source_id=_string(raw, "source_id"),
            eligible_unit_policy=_string(raw, "eligible_unit_policy"),
            target_policy=_string(raw, "target_policy"),
            use_limit=_string(raw, "use_limit"),
            effect_descriptor=_string(raw, "effect_descriptor"),
            unit_instance_id=_string(raw, "unit_instance_id"),
            unit_identity_ids=_string_tuple(raw, "unit_identity_ids"),
            component_unit_instance_ids=_string_tuple(raw, "component_unit_instance_ids"),
            eligible_unit_instance_ids=_string_tuple(raw, "eligible_unit_instance_ids"),
            target_id=_string(raw, "target_id"),
            condition_target_id=_optional_string(raw, "condition_target_id"),
            ruleset_descriptor_hash=_string(raw, "ruleset_descriptor_hash"),
            unit_owner_player_id=_string(raw, "unit_owner_player_id"),
            placed_alive_model_instance_ids=_string_tuple(raw, "placed_alive_model_instance_ids"),
            positive_objective_control_model_instance_ids=_string_tuple(
                raw, "positive_objective_control_model_instance_ids"
            ),
            keyword_tokens=_string_tuple(raw, "keyword_tokens"),
            battle_shocked=_bool(raw, "battle_shocked"),
            within_enemy_engagement_range=_bool(raw, "within_enemy_engagement_range"),
            advanced_unit_instance_ids=_string_tuple(raw, "advanced_unit_instance_ids"),
            fell_back_unit_instance_ids=_string_tuple(raw, "fell_back_unit_instance_ids"),
            shot_unit_instance_ids=_string_tuple(raw, "shot_unit_instance_ids"),
            unit_ineligibility_reason=_optional_string(raw, "unit_ineligibility_reason"),
            objective_proximity_witness=(
                None
                if objective_payload is None
                else RulesUnitObjectiveProximityWitness.from_payload(objective_payload)
            ),
            active_primary_mission_marker_ids=_string_tuple(
                raw, "active_primary_mission_marker_ids"
            ),
            enemy_territory_logical_terrain_area_ids=_string_tuple(
                raw, "enemy_territory_logical_terrain_area_ids"
            ),
            terrain_intersections=tuple(
                MissionActionTerrainIntersectionEvidence.from_payload(item)
                for item in _list(raw, "terrain_intersections")
            ),
            surveil_target_evidence=(
                None
                if surveil_payload is None
                else MissionActionSurveilTargetEvidence.from_payload(surveil_payload)
            ),
            prior_uses=tuple(
                MissionActionPriorUseEvidence.from_payload(item)
                for item in _list(raw, "prior_uses")
            ),
            start_authority=MissionActionStartAuthorityEvidence.from_payload(
                raw["start_authority"]
            ),
        )


@dataclass(frozen=True, slots=True)
class PrimaryMissionActionCompletionEvidence:
    schema_version: str
    boundary_kind: str
    game_id: str
    player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    action_id: str
    mission_action_id: str
    source_id: str
    effect_descriptor: str
    condition_target_id: str | None
    action_unit_identity_ids: tuple[str, ...]
    action_unit_battle_shocked: bool
    objective_control_record_id: str | None
    objective_control_record_hash: str | None
    objective_control_result: ObjectiveControlResult | None
    action_unit_contributor_unit_instance_ids: tuple[str, ...]
    action_unit_contributor_model_instance_ids: tuple[str, ...]
    terrain_intersections: tuple[MissionActionTerrainIntersectionEvidence, ...]
    terrain_model_inventory: tuple[MissionActionTerrainModelInventoryEvidence, ...]
    completion_condition_met: bool

    def __post_init__(self) -> None:
        for field_name, value in (
            ("schema_version", self.schema_version),
            ("boundary_kind", self.boundary_kind),
            ("game_id", self.game_id),
            ("player_id", self.player_id),
            ("active_player_id", self.active_player_id),
            ("phase", self.phase),
            ("action_id", self.action_id),
            ("mission_action_id", self.mission_action_id),
            ("source_id", self.source_id),
            ("effect_descriptor", self.effect_descriptor),
        ):
            object.__setattr__(self, field_name, _validate_identifier(field_name, value))
        if self.schema_version != PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_SCHEMA:
            raise GameLifecycleError(
                "Primary Mission Action completion evidence schema is unsupported."
            )
        if self.boundary_kind not in {"immediate_completion", "turn_end_completion"}:
            raise GameLifecycleError(
                "Primary Mission Action completion evidence boundary is unsupported."
            )
        object.__setattr__(self, "battle_round", _positive_int("battle_round", self.battle_round))
        object.__setattr__(
            self,
            "condition_target_id",
            _optional_identifier("condition_target_id", self.condition_target_id),
        )
        object.__setattr__(
            self,
            "action_unit_identity_ids",
            canonical_identifier_tuple(
                "action_unit_identity_ids",
                self.action_unit_identity_ids,
                require_non_empty=True,
            ),
        )
        for field_name in (
            "action_unit_contributor_unit_instance_ids",
            "action_unit_contributor_model_instance_ids",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_identifier_tuple(
                    field_name,
                    cast(tuple[str, ...], getattr(self, field_name)),
                    require_non_empty=False,
                ),
            )
        object.__setattr__(
            self,
            "objective_control_record_id",
            _optional_identifier("objective_control_record_id", self.objective_control_record_id),
        )
        object.__setattr__(
            self,
            "objective_control_record_hash",
            _optional_identifier(
                "objective_control_record_hash", self.objective_control_record_hash
            ),
        )
        if (
            self.objective_control_result is not None
            and type(self.objective_control_result) is not ObjectiveControlResult
        ):
            raise GameLifecycleError(
                "Primary Mission Action completion objective result is invalid."
            )
        object.__setattr__(
            self,
            "terrain_intersections",
            canonical_terrain_intersections(self.terrain_intersections),
        )
        object.__setattr__(
            self,
            "terrain_model_inventory",
            canonical_terrain_model_inventory(self.terrain_model_inventory),
        )
        for field_name in ("action_unit_battle_shocked", "completion_condition_met"):
            if type(getattr(self, field_name)) is not bool:
                raise GameLifecycleError(f"Primary Mission Action {field_name} must be a bool.")

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "schema_version": self.schema_version,
                    "boundary_kind": self.boundary_kind,
                    "game_id": self.game_id,
                    "player_id": self.player_id,
                    "active_player_id": self.active_player_id,
                    "battle_round": self.battle_round,
                    "phase": self.phase,
                    "action_id": self.action_id,
                    "mission_action_id": self.mission_action_id,
                    "source_id": self.source_id,
                    "effect_descriptor": self.effect_descriptor,
                    "condition_target_id": self.condition_target_id,
                    "action_unit_identity_ids": list(self.action_unit_identity_ids),
                    "action_unit_battle_shocked": self.action_unit_battle_shocked,
                    "objective_control_record_id": self.objective_control_record_id,
                    "objective_control_record_hash": self.objective_control_record_hash,
                    "objective_control_result": (
                        None
                        if self.objective_control_result is None
                        else self.objective_control_result.to_payload()
                    ),
                    "action_unit_contributor_unit_instance_ids": list(
                        self.action_unit_contributor_unit_instance_ids
                    ),
                    "action_unit_contributor_model_instance_ids": list(
                        self.action_unit_contributor_model_instance_ids
                    ),
                    "terrain_intersections": [
                        item.to_payload() for item in self.terrain_intersections
                    ],
                    "terrain_model_inventory": [
                        item.to_payload() for item in self.terrain_model_inventory
                    ],
                    "completion_condition_met": self.completion_condition_met,
                }
            ),
        )

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        keys = (
            "schema_version",
            "boundary_kind",
            "game_id",
            "player_id",
            "active_player_id",
            "battle_round",
            "phase",
            "action_id",
            "mission_action_id",
            "source_id",
            "effect_descriptor",
            "condition_target_id",
            "action_unit_identity_ids",
            "action_unit_battle_shocked",
            "objective_control_record_id",
            "objective_control_record_hash",
            "objective_control_result",
            "action_unit_contributor_unit_instance_ids",
            "action_unit_contributor_model_instance_ids",
            "terrain_intersections",
            "terrain_model_inventory",
            "completion_condition_met",
        )
        raw = _payload_mapping(payload, label="PrimaryMissionActionCompletionEvidence", keys=keys)
        result_payload = raw["objective_control_result"]
        return cls(
            schema_version=_string(raw, "schema_version"),
            boundary_kind=_string(raw, "boundary_kind"),
            game_id=_string(raw, "game_id"),
            player_id=_string(raw, "player_id"),
            active_player_id=_string(raw, "active_player_id"),
            battle_round=_int(raw, "battle_round"),
            phase=_string(raw, "phase"),
            action_id=_string(raw, "action_id"),
            mission_action_id=_string(raw, "mission_action_id"),
            source_id=_string(raw, "source_id"),
            effect_descriptor=_string(raw, "effect_descriptor"),
            condition_target_id=_optional_string(raw, "condition_target_id"),
            action_unit_identity_ids=_string_tuple(raw, "action_unit_identity_ids"),
            action_unit_battle_shocked=_bool(raw, "action_unit_battle_shocked"),
            objective_control_record_id=_optional_string(raw, "objective_control_record_id"),
            objective_control_record_hash=_optional_string(raw, "objective_control_record_hash"),
            objective_control_result=(
                None
                if result_payload is None
                else ObjectiveControlResult.from_payload(
                    cast(ObjectiveControlResultPayload, result_payload)
                )
            ),
            action_unit_contributor_unit_instance_ids=_string_tuple(
                raw, "action_unit_contributor_unit_instance_ids"
            ),
            action_unit_contributor_model_instance_ids=_string_tuple(
                raw, "action_unit_contributor_model_instance_ids"
            ),
            terrain_intersections=tuple(
                MissionActionTerrainIntersectionEvidence.from_payload(item)
                for item in _list(raw, "terrain_intersections")
            ),
            terrain_model_inventory=tuple(
                MissionActionTerrainModelInventoryEvidence.from_payload(item)
                for item in _list(raw, "terrain_model_inventory")
            ),
            completion_condition_met=_bool(raw, "completion_condition_met"),
        )


def canonical_terrain_intersections(
    values: tuple[MissionActionTerrainIntersectionEvidence, ...],
) -> tuple[MissionActionTerrainIntersectionEvidence, ...]:
    if type(values) is not tuple or any(
        type(value) is not MissionActionTerrainIntersectionEvidence for value in values
    ):
        raise GameLifecycleError("Primary Mission Action terrain inventory is invalid.")
    ordered = tuple(
        sorted(
            values,
            key=lambda value: (
                value.logical_terrain_area_id,
                value.owner_player_id,
                value.rules_unit_instance_id,
                value.component_unit_instance_id,
                value.model_instance_id,
            ),
        )
    )
    if len(set(ordered)) != len(ordered):
        raise GameLifecycleError("Primary Mission Action terrain inventory is duplicated.")
    return ordered


def canonical_terrain_model_inventory(
    values: tuple[MissionActionTerrainModelInventoryEvidence, ...],
) -> tuple[MissionActionTerrainModelInventoryEvidence, ...]:
    if type(values) is not tuple or any(
        type(value) is not MissionActionTerrainModelInventoryEvidence for value in values
    ):
        raise GameLifecycleError("Primary Mission Action terrain-model inventory is invalid.")
    ordered = tuple(sorted(values, key=lambda value: value.model_instance_id))
    if len({value.model_instance_id for value in ordered}) != len(ordered):
        raise GameLifecycleError("Primary Mission Action terrain-model inventory is duplicated.")
    return ordered


def canonical_surveil_target_inventory(
    values: tuple[MissionActionSurveilTargetEvidence, ...],
) -> tuple[MissionActionSurveilTargetEvidence, ...]:
    if type(values) is not tuple or any(
        type(value) is not MissionActionSurveilTargetEvidence for value in values
    ):
        raise GameLifecycleError("Primary Mission Action Surveil inventory is invalid.")
    ordered = tuple(sorted(values, key=lambda value: value.target_rules_unit_instance_id))
    if len({value.target_rules_unit_instance_id for value in ordered}) != len(ordered):
        raise GameLifecycleError("Primary Mission Action Surveil inventory is duplicated.")
    return ordered


def canonical_start_candidate_units(
    values: tuple[MissionActionStartCandidateUnitEvidence, ...],
) -> tuple[MissionActionStartCandidateUnitEvidence, ...]:
    if type(values) is not tuple or any(
        type(value) is not MissionActionStartCandidateUnitEvidence for value in values
    ):
        raise GameLifecycleError("Primary Mission Action start candidate inventory is invalid.")
    ordered = tuple(sorted(values, key=lambda value: value.unit_instance_id))
    if len({value.unit_instance_id for value in ordered}) != len(ordered):
        raise GameLifecycleError("Primary Mission Action start candidate inventory is duplicated.")
    return ordered


def canonical_json_object(value: object) -> str:
    validated = validate_json_value(value)
    if type(validated) is not dict:
        raise GameLifecycleError("Mission Action authority payload must be a JSON object.")
    return json.dumps(
        validated,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def canonical_mission_action_prior_uses(
    values: tuple[MissionActionPriorUseEvidence, ...],
) -> tuple[MissionActionPriorUseEvidence, ...]:
    if type(values) is not tuple or any(
        type(value) is not MissionActionPriorUseEvidence for value in values
    ):
        raise GameLifecycleError("Primary Mission Action prior-use inventory is invalid.")
    ordered = tuple(sorted(values, key=lambda value: value.action_id))
    if len({value.action_id for value in ordered}) != len(ordered):
        raise GameLifecycleError("Primary Mission Action prior-use inventory is duplicated.")
    return ordered


def canonical_identifier_tuple(
    field_name: str, values: tuple[str, ...], *, require_non_empty: bool
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated = tuple(sorted(_validate_identifier(field_name, value) for value in values))
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    if require_non_empty and not validated:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return validated


def _positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value <= 0:
        raise GameLifecycleError(f"{field_name} must be a positive int.")
    return value


def _non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"{field_name} must be a non-negative int.")
    return value


def _validate_canonical_json_object(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a canonical JSON string.")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise GameLifecycleError(f"{field_name} must be canonical JSON.") from exc
    if canonical_json_object(decoded) != value:
        raise GameLifecycleError(f"{field_name} must use canonical JSON encoding.")
    return value


def _optional_canonical_json_object(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_canonical_json_object(field_name, value)


def _optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _payload_mapping(payload: object, *, label: str, keys: tuple[str, ...]) -> dict[str, object]:
    if type(payload) is not dict:
        raise GameLifecycleError(f"{label} payload must be an object.")
    raw = cast(dict[object, object], payload)
    if set(raw) != set(keys) or any(type(key) is not str for key in raw):
        raise GameLifecycleError(f"{label} payload fields drifted.")
    return cast(dict[str, object], raw)


def _string(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if type(value) is not str:
        raise GameLifecycleError(f"{key} must be a string.")
    return value


def _optional_string(raw: dict[str, object], key: str) -> str | None:
    value = raw[key]
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(f"{key} must be a string or null.")
    return value


def _int(raw: dict[str, object], key: str) -> int:
    value = raw[key]
    if type(value) is not int:
        raise GameLifecycleError(f"{key} must be an int.")
    return value


def _bool(raw: dict[str, object], key: str) -> bool:
    value = raw[key]
    if type(value) is not bool:
        raise GameLifecycleError(f"{key} must be a bool.")
    return value


def _list(raw: dict[str, object], key: str) -> list[object]:
    value = raw[key]
    if type(value) is not list:
        raise GameLifecycleError(f"{key} must be a list.")
    return cast(list[object], value)


def _string_tuple(raw: dict[str, object], key: str) -> tuple[str, ...]:
    values = _list(raw, key)
    if any(type(value) is not str for value in values):
        raise GameLifecycleError(f"{key} must contain strings.")
    return tuple(cast(list[str], values))


def require_primary_mission_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary Mission Action lifecycle evidence requires GameState.")


__all__ = (
    "PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY",
    "PRIMARY_MISSION_ACTION_MARKER_EFFECTS",
    "PRIMARY_MISSION_ACTION_OBJECTIVE_CONTROL_EFFECTS",
    "PRIMARY_MISSION_ACTION_SENSOR_EFFECTS",
    "PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY",
    "PRIMARY_MISSION_ACTION_SURVEIL_EFFECT",
    "PRIMARY_MISSION_ACTION_VANGUARD_EFFECT",
    "MissionActionPriorUseEvidence",
    "MissionActionStartAuthorityEvidence",
    "MissionActionStartAuthorityOptionEvidence",
    "MissionActionStartCandidateUnitEvidence",
    "MissionActionSurveilTargetEvidence",
    "MissionActionTerrainIntersectionEvidence",
    "MissionActionTerrainModelInventoryEvidence",
    "PrimaryMissionActionCompletionEvidence",
    "PrimaryMissionActionStartEvidence",
    "canonical_identifier_tuple",
    "canonical_json_object",
    "canonical_mission_action_prior_uses",
    "canonical_start_candidate_units",
    "canonical_surveil_target_inventory",
    "canonical_terrain_intersections",
    "canonical_terrain_model_inventory",
    "require_primary_mission_game_state",
)
