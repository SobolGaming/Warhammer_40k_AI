from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Self, cast

from warhammer40k_core.core.descriptor_hash import (
    canonical_payload_sha256,
    validate_sha256_hex,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT = "primary_mission_boundary_checkpoint_recorded"
PRIMARY_MISSION_BOUNDARY_CHECKPOINT_SCHEMA = "primary-mission-boundary-checkpoint-v1"

_SECONDARY_MISSION_CARD_STATE_KEYS = frozenset(
    {
        "player_id",
        "secondary_mission_id",
        "mode",
        "battle_round",
        "status",
        "source_result_id",
        "scored_transaction_id",
        "discarded_result_id",
        "selection_payload",
    }
)
_MISSION_ACTION_STATE_KEYS = frozenset(
    {
        "action_id",
        "mission_action_id",
        "player_id",
        "unit_instance_id",
        "target_id",
        "condition_target_id",
        "mission_id",
        "battle_round_started",
        "phase_started",
        "start_timing",
        "completion_timing",
        "eligible_unit_instance_ids",
        "interruption_conditions",
        "scoring_source_id",
        "victory_points",
        "status",
        "completed_battle_round",
        "completed_phase",
        "interrupted_reason",
        "score_transaction_id",
    }
)
_STARTING_STRENGTH_RECORD_KEYS = frozenset(
    {
        "player_id",
        "unit_instance_id",
        "starting_model_count",
        "single_model_starting_wounds",
        "source_id",
    }
)

_validate_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class PrimaryMissionBoundaryCheckpointReference:
    checkpoint_event_id: str
    checkpoint_id: str
    checkpoint_hash: str

    def __post_init__(self) -> None:
        for field_name in ("checkpoint_event_id", "checkpoint_id"):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "checkpoint_hash",
            validate_sha256_hex(
                self.checkpoint_hash,
                field_name="checkpoint_hash",
                error_type=GameLifecycleError,
            ),
        )
        if self.checkpoint_id != f"primary-mission-boundary:{self.checkpoint_hash}":
            raise GameLifecycleError("Primary mission boundary checkpoint identity drifted.")

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "checkpoint_event_id": self.checkpoint_event_id,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_hash": self.checkpoint_hash,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _object(
            payload,
            label="Primary mission boundary checkpoint reference",
            keys=("checkpoint_event_id", "checkpoint_id", "checkpoint_hash"),
        )
        return cls(
            checkpoint_event_id=_string(raw, "checkpoint_event_id"),
            checkpoint_id=_string(raw, "checkpoint_id"),
            checkpoint_hash=_string(raw, "checkpoint_hash"),
        )


@dataclass(frozen=True, slots=True)
class PrimaryMissionBoundaryModelState:
    owner_player_id: str
    rules_unit_instance_id: str
    component_unit_instance_id: str
    model_instance_id: str
    alive: bool
    wounds_remaining: int
    presence: str
    model_placement_json: str | None
    source_objective_control_json: str
    resolved_objective_control_json: str
    logical_terrain_area_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "owner_player_id",
            "rules_unit_instance_id",
            "component_unit_instance_id",
            "model_instance_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        if type(self.alive) is not bool:
            raise GameLifecycleError("Primary mission boundary model alive must be a bool.")
        if type(self.wounds_remaining) is not int or self.wounds_remaining < 0:
            raise GameLifecycleError(
                "Primary mission boundary model wounds_remaining must be non-negative."
            )
        object.__setattr__(self, "presence", _validate_identifier("presence", self.presence))
        if self.presence not in {
            "battlefield",
            "destroyed",
            "embarked",
            "off_battlefield",
            "reserves",
        }:
            raise GameLifecycleError("Primary mission boundary model presence is unsupported.")
        if self.alive is not (self.wounds_remaining > 0):
            raise GameLifecycleError("Primary mission boundary model life state drifted.")
        if (self.presence == "battlefield") is (self.model_placement_json is None):
            raise GameLifecycleError("Primary mission boundary model placement drifted.")
        if self.presence == "destroyed" and self.alive:
            raise GameLifecycleError("A living model cannot have destroyed boundary presence.")
        if not self.alive and self.presence != "destroyed":
            raise GameLifecycleError("A destroyed model must have destroyed boundary presence.")
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
                _canonical_json_object(field_name, getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "logical_terrain_area_ids",
            _identifier_tuple("logical_terrain_area_ids", self.logical_terrain_area_ids),
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "owner_player_id": self.owner_player_id,
            "rules_unit_instance_id": self.rules_unit_instance_id,
            "component_unit_instance_id": self.component_unit_instance_id,
            "model_instance_id": self.model_instance_id,
            "alive": self.alive,
            "wounds_remaining": self.wounds_remaining,
            "presence": self.presence,
            "model_placement_json": self.model_placement_json,
            "source_objective_control_json": self.source_objective_control_json,
            "resolved_objective_control_json": self.resolved_objective_control_json,
            "logical_terrain_area_ids": list(self.logical_terrain_area_ids),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        keys = (
            "owner_player_id",
            "rules_unit_instance_id",
            "component_unit_instance_id",
            "model_instance_id",
            "alive",
            "wounds_remaining",
            "presence",
            "model_placement_json",
            "source_objective_control_json",
            "resolved_objective_control_json",
            "logical_terrain_area_ids",
        )
        raw = _object(payload, label="Primary mission boundary model", keys=keys)
        return cls(
            owner_player_id=_string(raw, "owner_player_id"),
            rules_unit_instance_id=_string(raw, "rules_unit_instance_id"),
            component_unit_instance_id=_string(raw, "component_unit_instance_id"),
            model_instance_id=_string(raw, "model_instance_id"),
            alive=_bool(raw, "alive"),
            wounds_remaining=_int(raw, "wounds_remaining"),
            presence=_string(raw, "presence"),
            model_placement_json=_optional_string(raw, "model_placement_json"),
            source_objective_control_json=_string(raw, "source_objective_control_json"),
            resolved_objective_control_json=_string(raw, "resolved_objective_control_json"),
            logical_terrain_area_ids=_string_tuple(raw, "logical_terrain_area_ids"),
        )


@dataclass(frozen=True, slots=True)
class PrimaryMissionObjectiveControlModifierSource:
    modifier_id: str
    source_id: str
    source_effect_id: str | None
    source_effect_json: str | None

    def __post_init__(self) -> None:
        for field_name in ("modifier_id", "source_id"):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        object.__setattr__(
            self,
            "source_effect_id",
            _optional_identifier("source_effect_id", self.source_effect_id),
        )
        object.__setattr__(
            self,
            "source_effect_json",
            _optional_canonical_json_object("source_effect_json", self.source_effect_json),
        )
        if (self.source_effect_id is None) is not (self.source_effect_json is None):
            raise GameLifecycleError(
                "Primary mission Objective Control modifier effect evidence is incomplete."
            )

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "modifier_id": self.modifier_id,
            "source_id": self.source_id,
            "source_effect_id": self.source_effect_id,
            "source_effect_json": self.source_effect_json,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _object(
            payload,
            label="Primary mission Objective Control modifier source",
            keys=("modifier_id", "source_id", "source_effect_id", "source_effect_json"),
        )
        return cls(
            modifier_id=_string(raw, "modifier_id"),
            source_id=_string(raw, "source_id"),
            source_effect_id=_optional_string(raw, "source_effect_id"),
            source_effect_json=_optional_string(raw, "source_effect_json"),
        )


@dataclass(frozen=True, slots=True)
class PrimaryMissionBoundaryCheckpoint:
    schema_version: str
    boundary_kind: str
    game_id: str
    player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    battlefield_id: str
    model_states: tuple[PrimaryMissionBoundaryModelState, ...]
    attached_unit_formation_jsons: tuple[str, ...]
    battle_shocked_unit_instance_ids: tuple[str, ...]
    advanced_unit_state_jsons: tuple[str, ...]
    fell_back_unit_state_jsons: tuple[str, ...]
    shot_unit_instance_ids: tuple[str, ...]
    objective_control_modifier_sources: tuple[PrimaryMissionObjectiveControlModifierSource, ...]
    active_primary_marker_jsons: tuple[str, ...]
    active_secondary_mission_card_jsons: tuple[str, ...]
    completed_mission_action_state_jsons: tuple[str, ...]
    primary_unit_destruction_state_jsons: tuple[str, ...]
    starting_strength_record_jsons: tuple[str, ...]
    active_secondary_mission_ids: tuple[str, ...]
    mission_action_prior_use_jsons: tuple[str, ...]
    checkpoint_id: str
    checkpoint_hash: str
    _active_secondary_mission_card_jsons_present: bool = field(
        default=True,
        compare=False,
        repr=False,
    )
    _completed_mission_action_state_jsons_present: bool = field(
        default=True,
        compare=False,
        repr=False,
    )
    _primary_unit_destruction_state_jsons_present: bool = field(
        default=True,
        compare=False,
        repr=False,
    )
    _starting_strength_record_jsons_present: bool = field(
        default=True,
        compare=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        for field_name in (
            "schema_version",
            "boundary_kind",
            "game_id",
            "player_id",
            "active_player_id",
            "phase",
            "battlefield_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        if self.schema_version != PRIMARY_MISSION_BOUNDARY_CHECKPOINT_SCHEMA:
            raise GameLifecycleError("Primary mission boundary checkpoint schema is unsupported.")
        if self.boundary_kind not in {
            "action_request",
            "objective_control",
            "turn_end",
            "primary_scoring_commit",
        }:
            raise GameLifecycleError("Primary mission boundary checkpoint kind is unsupported.")
        if type(self.battle_round) is not int or self.battle_round < 1:
            raise GameLifecycleError("Primary mission boundary battle_round must be positive.")
        object.__setattr__(self, "model_states", _model_states(self.model_states))
        for field_name in (
            "attached_unit_formation_jsons",
            "advanced_unit_state_jsons",
            "fell_back_unit_state_jsons",
            "active_primary_marker_jsons",
            "mission_action_prior_use_jsons",
        ):
            object.__setattr__(
                self,
                field_name,
                _canonical_json_tuple(field_name, cast(tuple[str, ...], getattr(self, field_name))),
            )
        for field_name in (
            "battle_shocked_unit_instance_ids",
            "shot_unit_instance_ids",
            "active_secondary_mission_ids",
        ):
            object.__setattr__(
                self,
                field_name,
                _identifier_tuple(field_name, cast(tuple[str, ...], getattr(self, field_name))),
            )
        object.__setattr__(
            self,
            "objective_control_modifier_sources",
            _modifier_sources(self.objective_control_modifier_sources),
        )
        object.__setattr__(
            self,
            "active_secondary_mission_card_jsons",
            _active_secondary_mission_card_jsons(self.active_secondary_mission_card_jsons),
        )
        object.__setattr__(
            self,
            "completed_mission_action_state_jsons",
            _completed_mission_action_state_jsons(self.completed_mission_action_state_jsons),
        )
        object.__setattr__(
            self,
            "primary_unit_destruction_state_jsons",
            _primary_unit_destruction_state_jsons(self.primary_unit_destruction_state_jsons),
        )
        object.__setattr__(
            self,
            "starting_strength_record_jsons",
            _starting_strength_record_jsons(self.starting_strength_record_jsons),
        )
        if (
            type(self._active_secondary_mission_card_jsons_present) is not bool
            or type(self._completed_mission_action_state_jsons_present) is not bool
            or type(self._primary_unit_destruction_state_jsons_present) is not bool
            or type(self._starting_strength_record_jsons_present) is not bool
        ):
            raise GameLifecycleError(
                "Primary mission boundary Secondary authority witness presence must be a bool."
            )
        if (
            not self._active_secondary_mission_card_jsons_present
            and self.active_secondary_mission_card_jsons
        ):
            raise GameLifecycleError(
                "A legacy Primary mission boundary checkpoint cannot carry hidden card evidence."
            )
        if (
            not self._completed_mission_action_state_jsons_present
            and self.completed_mission_action_state_jsons
        ):
            raise GameLifecycleError(
                "A legacy Primary mission boundary checkpoint cannot carry completed Action "
                "evidence."
            )
        if (
            not self._primary_unit_destruction_state_jsons_present
            and self.primary_unit_destruction_state_jsons
        ):
            raise GameLifecycleError(
                "A legacy Primary mission boundary checkpoint cannot carry destruction evidence."
            )
        if not self._starting_strength_record_jsons_present and self.starting_strength_record_jsons:
            raise GameLifecycleError(
                "A legacy Primary mission boundary checkpoint cannot carry Starting Strength "
                "evidence."
            )
        object.__setattr__(
            self,
            "checkpoint_hash",
            validate_sha256_hex(
                self.checkpoint_hash,
                field_name="checkpoint_hash",
                error_type=GameLifecycleError,
            ),
        )
        object.__setattr__(
            self,
            "checkpoint_id",
            _validate_identifier("checkpoint_id", self.checkpoint_id),
        )
        expected_hash = canonical_payload_sha256(self._content_payload())
        if self.checkpoint_hash != expected_hash:
            raise GameLifecycleError("Primary mission boundary checkpoint hash drifted.")
        if self.checkpoint_id != f"primary-mission-boundary:{expected_hash}":
            raise GameLifecycleError("Primary mission boundary checkpoint identity drifted.")
        _validate_modifier_references(self)
        if self._active_secondary_mission_card_jsons_present:
            _validate_active_secondary_mission_card_references(self)
        if self._primary_unit_destruction_state_jsons_present:
            _validate_primary_unit_destruction_references(self)

    @property
    def has_active_secondary_mission_card_witness(self) -> bool:
        return self._active_secondary_mission_card_jsons_present

    @property
    def has_secondary_scoring_authority_witnesses(self) -> bool:
        return (
            self._active_secondary_mission_card_jsons_present
            and self._completed_mission_action_state_jsons_present
            and self._primary_unit_destruction_state_jsons_present
            and self._starting_strength_record_jsons_present
        )

    @classmethod
    def create(
        cls,
        *,
        boundary_kind: str,
        game_id: str,
        player_id: str,
        active_player_id: str,
        battle_round: int,
        phase: str,
        battlefield_id: str,
        model_states: tuple[PrimaryMissionBoundaryModelState, ...],
        attached_unit_formation_jsons: tuple[str, ...],
        battle_shocked_unit_instance_ids: tuple[str, ...],
        advanced_unit_state_jsons: tuple[str, ...],
        fell_back_unit_state_jsons: tuple[str, ...],
        shot_unit_instance_ids: tuple[str, ...],
        objective_control_modifier_sources: tuple[
            PrimaryMissionObjectiveControlModifierSource, ...
        ],
        active_primary_marker_jsons: tuple[str, ...],
        active_secondary_mission_card_jsons: tuple[str, ...],
        completed_mission_action_state_jsons: tuple[str, ...],
        primary_unit_destruction_state_jsons: tuple[str, ...],
        starting_strength_record_jsons: tuple[str, ...],
        active_secondary_mission_ids: tuple[str, ...],
        mission_action_prior_use_jsons: tuple[str, ...],
    ) -> Self:
        include_secondary_scoring_authority_witnesses = boundary_kind == "objective_control"
        canonical_models = _model_states(model_states)
        canonical_attached = _canonical_json_tuple(
            "attached_unit_formation_jsons", attached_unit_formation_jsons
        )
        canonical_shocked = _identifier_tuple(
            "battle_shocked_unit_instance_ids", battle_shocked_unit_instance_ids
        )
        canonical_advanced = _canonical_json_tuple(
            "advanced_unit_state_jsons", advanced_unit_state_jsons
        )
        canonical_fell_back = _canonical_json_tuple(
            "fell_back_unit_state_jsons", fell_back_unit_state_jsons
        )
        canonical_shot = _identifier_tuple("shot_unit_instance_ids", shot_unit_instance_ids)
        canonical_modifiers = _modifier_sources(objective_control_modifier_sources)
        canonical_markers = _canonical_json_tuple(
            "active_primary_marker_jsons", active_primary_marker_jsons
        )
        canonical_secondary_cards = _active_secondary_mission_card_jsons(
            active_secondary_mission_card_jsons
        )
        canonical_completed_actions = _completed_mission_action_state_jsons(
            completed_mission_action_state_jsons
        )
        canonical_destructions = _primary_unit_destruction_state_jsons(
            primary_unit_destruction_state_jsons
        )
        canonical_starting_strength = _starting_strength_record_jsons(
            starting_strength_record_jsons
        )
        canonical_secondaries = _identifier_tuple(
            "active_secondary_mission_ids", active_secondary_mission_ids
        )
        canonical_prior_uses = _canonical_json_tuple(
            "mission_action_prior_use_jsons", mission_action_prior_use_jsons
        )
        if not include_secondary_scoring_authority_witnesses and any(
            (
                canonical_secondary_cards,
                canonical_completed_actions,
                canonical_destructions,
                canonical_starting_strength,
            )
        ):
            raise GameLifecycleError(
                "Primary mission boundary cannot omit non-empty Secondary authority witnesses."
            )
        provisional: dict[str, object] = {
            "schema_version": PRIMARY_MISSION_BOUNDARY_CHECKPOINT_SCHEMA,
            "boundary_kind": boundary_kind,
            "game_id": game_id,
            "player_id": player_id,
            "active_player_id": active_player_id,
            "battle_round": battle_round,
            "phase": phase,
            "battlefield_id": battlefield_id,
            "model_states": [row.to_payload() for row in canonical_models],
            "attached_unit_formation_jsons": list(canonical_attached),
            "battle_shocked_unit_instance_ids": list(canonical_shocked),
            "advanced_unit_state_jsons": list(canonical_advanced),
            "fell_back_unit_state_jsons": list(canonical_fell_back),
            "shot_unit_instance_ids": list(canonical_shot),
            "objective_control_modifier_sources": [row.to_payload() for row in canonical_modifiers],
            "active_primary_marker_jsons": list(canonical_markers),
            "active_secondary_mission_ids": list(canonical_secondaries),
            "mission_action_prior_use_jsons": list(canonical_prior_uses),
        }
        if include_secondary_scoring_authority_witnesses:
            provisional.update(
                {
                    "active_secondary_mission_card_jsons": list(canonical_secondary_cards),
                    "completed_mission_action_state_jsons": list(canonical_completed_actions),
                    "primary_unit_destruction_state_jsons": list(canonical_destructions),
                    "starting_strength_record_jsons": list(canonical_starting_strength),
                }
            )
        digest = canonical_payload_sha256(provisional)
        return cls(
            schema_version=PRIMARY_MISSION_BOUNDARY_CHECKPOINT_SCHEMA,
            boundary_kind=boundary_kind,
            game_id=game_id,
            player_id=player_id,
            active_player_id=active_player_id,
            battle_round=battle_round,
            phase=phase,
            battlefield_id=battlefield_id,
            model_states=canonical_models,
            attached_unit_formation_jsons=canonical_attached,
            battle_shocked_unit_instance_ids=canonical_shocked,
            advanced_unit_state_jsons=canonical_advanced,
            fell_back_unit_state_jsons=canonical_fell_back,
            shot_unit_instance_ids=canonical_shot,
            objective_control_modifier_sources=canonical_modifiers,
            active_primary_marker_jsons=canonical_markers,
            active_secondary_mission_card_jsons=canonical_secondary_cards,
            completed_mission_action_state_jsons=canonical_completed_actions,
            primary_unit_destruction_state_jsons=canonical_destructions,
            starting_strength_record_jsons=canonical_starting_strength,
            active_secondary_mission_ids=canonical_secondaries,
            mission_action_prior_use_jsons=canonical_prior_uses,
            checkpoint_id=f"primary-mission-boundary:{digest}",
            checkpoint_hash=digest,
            _active_secondary_mission_card_jsons_present=(
                include_secondary_scoring_authority_witnesses
            ),
            _completed_mission_action_state_jsons_present=(
                include_secondary_scoring_authority_witnesses
            ),
            _primary_unit_destruction_state_jsons_present=(
                include_secondary_scoring_authority_witnesses
            ),
            _starting_strength_record_jsons_present=(include_secondary_scoring_authority_witnesses),
        )

    def reference(self, *, event_id: str) -> PrimaryMissionBoundaryCheckpointReference:
        return PrimaryMissionBoundaryCheckpointReference(
            checkpoint_event_id=event_id,
            checkpoint_id=self.checkpoint_id,
            checkpoint_hash=self.checkpoint_hash,
        )

    def _content_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "boundary_kind": self.boundary_kind,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "active_player_id": self.active_player_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "battlefield_id": self.battlefield_id,
            "model_states": [row.to_payload() for row in self.model_states],
            "attached_unit_formation_jsons": list(self.attached_unit_formation_jsons),
            "battle_shocked_unit_instance_ids": list(self.battle_shocked_unit_instance_ids),
            "advanced_unit_state_jsons": list(self.advanced_unit_state_jsons),
            "fell_back_unit_state_jsons": list(self.fell_back_unit_state_jsons),
            "shot_unit_instance_ids": list(self.shot_unit_instance_ids),
            "objective_control_modifier_sources": [
                row.to_payload() for row in self.objective_control_modifier_sources
            ],
            "active_primary_marker_jsons": list(self.active_primary_marker_jsons),
            "active_secondary_mission_ids": list(self.active_secondary_mission_ids),
            "mission_action_prior_use_jsons": list(self.mission_action_prior_use_jsons),
        }
        if self._active_secondary_mission_card_jsons_present:
            payload["active_secondary_mission_card_jsons"] = list(
                self.active_secondary_mission_card_jsons
            )
        if self._completed_mission_action_state_jsons_present:
            payload["completed_mission_action_state_jsons"] = list(
                self.completed_mission_action_state_jsons
            )
        if self._primary_unit_destruction_state_jsons_present:
            payload["primary_unit_destruction_state_jsons"] = list(
                self.primary_unit_destruction_state_jsons
            )
        if self._starting_strength_record_jsons_present:
            payload["starting_strength_record_jsons"] = list(self.starting_strength_record_jsons)
        return payload

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    **self._content_payload(),
                    "checkpoint_id": self.checkpoint_id,
                    "checkpoint_hash": self.checkpoint_hash,
                }
            ),
        )

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        required_keys = (
            "schema_version",
            "boundary_kind",
            "game_id",
            "player_id",
            "active_player_id",
            "battle_round",
            "phase",
            "battlefield_id",
            "model_states",
            "attached_unit_formation_jsons",
            "battle_shocked_unit_instance_ids",
            "advanced_unit_state_jsons",
            "fell_back_unit_state_jsons",
            "shot_unit_instance_ids",
            "objective_control_modifier_sources",
            "active_primary_marker_jsons",
            "active_secondary_mission_ids",
            "mission_action_prior_use_jsons",
            "checkpoint_id",
            "checkpoint_hash",
        )
        raw = _object_with_optional(
            payload,
            label="Primary mission boundary checkpoint",
            required_keys=required_keys,
            optional_keys=(
                "active_secondary_mission_card_jsons",
                "completed_mission_action_state_jsons",
                "primary_unit_destruction_state_jsons",
                "starting_strength_record_jsons",
            ),
        )
        has_secondary_card_witness = "active_secondary_mission_card_jsons" in raw
        has_completed_action_witness = "completed_mission_action_state_jsons" in raw
        has_primary_destruction_witness = "primary_unit_destruction_state_jsons" in raw
        has_starting_strength_witness = "starting_strength_record_jsons" in raw
        return cls(
            schema_version=_string(raw, "schema_version"),
            boundary_kind=_string(raw, "boundary_kind"),
            game_id=_string(raw, "game_id"),
            player_id=_string(raw, "player_id"),
            active_player_id=_string(raw, "active_player_id"),
            battle_round=_int(raw, "battle_round"),
            phase=_string(raw, "phase"),
            battlefield_id=_string(raw, "battlefield_id"),
            model_states=tuple(
                PrimaryMissionBoundaryModelState.from_payload(row)
                for row in _list(raw, "model_states")
            ),
            attached_unit_formation_jsons=_string_tuple(raw, "attached_unit_formation_jsons"),
            battle_shocked_unit_instance_ids=_string_tuple(raw, "battle_shocked_unit_instance_ids"),
            advanced_unit_state_jsons=_string_tuple(raw, "advanced_unit_state_jsons"),
            fell_back_unit_state_jsons=_string_tuple(raw, "fell_back_unit_state_jsons"),
            shot_unit_instance_ids=_string_tuple(raw, "shot_unit_instance_ids"),
            objective_control_modifier_sources=tuple(
                PrimaryMissionObjectiveControlModifierSource.from_payload(row)
                for row in _list(raw, "objective_control_modifier_sources")
            ),
            active_primary_marker_jsons=_string_tuple(raw, "active_primary_marker_jsons"),
            active_secondary_mission_card_jsons=(
                _string_tuple(raw, "active_secondary_mission_card_jsons")
                if has_secondary_card_witness
                else ()
            ),
            completed_mission_action_state_jsons=(
                _string_tuple(raw, "completed_mission_action_state_jsons")
                if has_completed_action_witness
                else ()
            ),
            primary_unit_destruction_state_jsons=(
                _string_tuple(raw, "primary_unit_destruction_state_jsons")
                if has_primary_destruction_witness
                else ()
            ),
            starting_strength_record_jsons=(
                _string_tuple(raw, "starting_strength_record_jsons")
                if has_starting_strength_witness
                else ()
            ),
            active_secondary_mission_ids=_string_tuple(raw, "active_secondary_mission_ids"),
            mission_action_prior_use_jsons=_string_tuple(raw, "mission_action_prior_use_jsons"),
            checkpoint_id=_string(raw, "checkpoint_id"),
            checkpoint_hash=_string(raw, "checkpoint_hash"),
            _active_secondary_mission_card_jsons_present=has_secondary_card_witness,
            _completed_mission_action_state_jsons_present=has_completed_action_witness,
            _primary_unit_destruction_state_jsons_present=has_primary_destruction_witness,
            _starting_strength_record_jsons_present=has_starting_strength_witness,
        )


def _validate_modifier_references(checkpoint: PrimaryMissionBoundaryCheckpoint) -> None:
    source_ids = {source.modifier_id for source in checkpoint.objective_control_modifier_sources}
    for model in checkpoint.model_states:
        source = _json_object(model.source_objective_control_json)
        resolved = _json_object(model.resolved_objective_control_json)
        source_modifier_ids = _json_string_list(source, key="applied_modifier_ids")
        resolved_modifier_ids = _json_string_list(resolved, key="applied_modifier_ids")
        added = set(resolved_modifier_ids).difference(source_modifier_ids)
        if not added <= source_ids:
            raise GameLifecycleError(
                "Primary mission boundary Objective Control modifier source is missing."
            )
        if resolved.get("final") != source.get("final") and not added:
            raise GameLifecycleError(
                "Primary mission boundary Objective Control change lacks source identity."
            )


def _validate_active_secondary_mission_card_references(
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> None:
    from warhammer40k_core.engine.scoring import (
        SecondaryMissionCardState,
        SecondaryMissionCardStatePayload,
    )

    cards = tuple(
        SecondaryMissionCardState.from_payload(
            cast(SecondaryMissionCardStatePayload, _json_object(value))
        )
        for value in checkpoint.active_secondary_mission_card_jsons
    )
    if checkpoint.active_secondary_mission_ids != tuple(
        sorted(
            card.secondary_mission_id for card in cards if card.player_id == checkpoint.player_id
        )
    ):
        raise GameLifecycleError(
            "Primary mission boundary active Secondary card references drifted."
        )


def _validate_primary_unit_destruction_references(
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> None:
    from warhammer40k_core.engine.scoring import (
        PrimaryUnitDestructionState,
        PrimaryUnitDestructionStatePayload,
    )

    for value in checkpoint.primary_unit_destruction_state_jsons:
        destruction = PrimaryUnitDestructionState.from_payload(
            cast(PrimaryUnitDestructionStatePayload, _json_object(value))
        )
        if destruction.game_id != checkpoint.game_id:
            raise GameLifecycleError(
                "Primary mission boundary destruction witness game identity drifted."
            )


def _model_states(
    values: tuple[PrimaryMissionBoundaryModelState, ...],
) -> tuple[PrimaryMissionBoundaryModelState, ...]:
    if type(values) is not tuple or any(
        type(value) is not PrimaryMissionBoundaryModelState for value in values
    ):
        raise GameLifecycleError("Primary mission boundary model inventory is invalid.")
    ordered = tuple(sorted(values, key=lambda value: value.model_instance_id))
    if len({value.model_instance_id for value in ordered}) != len(ordered):
        raise GameLifecycleError("Primary mission boundary model inventory is duplicated.")
    return ordered


def _modifier_sources(
    values: tuple[PrimaryMissionObjectiveControlModifierSource, ...],
) -> tuple[PrimaryMissionObjectiveControlModifierSource, ...]:
    if type(values) is not tuple or any(
        type(value) is not PrimaryMissionObjectiveControlModifierSource for value in values
    ):
        raise GameLifecycleError(
            "Primary mission Objective Control modifier source inventory is invalid."
        )
    ordered = tuple(sorted(values, key=lambda value: value.modifier_id))
    if len({value.modifier_id for value in ordered}) != len(ordered):
        raise GameLifecycleError(
            "Primary mission Objective Control modifier source inventory is duplicated."
        )
    return ordered


def _active_secondary_mission_card_jsons(values: tuple[str, ...]) -> tuple[str, ...]:
    from warhammer40k_core.engine.scoring import (
        SecondaryMissionCardMode,
        SecondaryMissionCardState,
        SecondaryMissionCardStatePayload,
        SecondaryMissionCardStatus,
    )

    canonical = _canonical_json_tuple("active_secondary_mission_card_jsons", values)
    seen: set[tuple[str, str, SecondaryMissionCardMode, int]] = set()
    for value in canonical:
        payload = _json_object(value)
        if frozenset(payload) != _SECONDARY_MISSION_CARD_STATE_KEYS:
            raise GameLifecycleError(
                "Primary mission boundary active Secondary card fields drifted."
            )
        card = SecondaryMissionCardState.from_payload(
            cast(SecondaryMissionCardStatePayload, payload)
        )
        if card.status is not SecondaryMissionCardStatus.ACTIVE:
            raise GameLifecycleError(
                "Primary mission boundary Secondary card snapshot must be active."
            )
        if value != json.dumps(
            card.to_payload(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ):
            raise GameLifecycleError(
                "Primary mission boundary active Secondary card payload drifted."
            )
        identity = (
            card.player_id,
            card.secondary_mission_id,
            card.mode,
            card.battle_round,
        )
        if identity in seen:
            raise GameLifecycleError(
                "Primary mission boundary active Secondary card inventory is duplicated."
            )
        seen.add(identity)
    return canonical


def _completed_mission_action_state_jsons(values: tuple[str, ...]) -> tuple[str, ...]:
    from warhammer40k_core.engine.actions import (
        MissionActionState,
        MissionActionStatePayload,
        MissionActionStatus,
    )

    canonical = _canonical_json_tuple("completed_mission_action_state_jsons", values)
    seen_action_ids: set[str] = set()
    for value in canonical:
        payload = _json_object(value)
        if frozenset(payload) != _MISSION_ACTION_STATE_KEYS:
            raise GameLifecycleError(
                "Primary mission boundary completed Mission Action fields drifted."
            )
        action = MissionActionState.from_payload(cast(MissionActionStatePayload, payload))
        if action.status is not MissionActionStatus.COMPLETED:
            raise GameLifecycleError(
                "Primary mission boundary Mission Action witness must be completed."
            )
        if value != json.dumps(
            action.to_payload(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ):
            raise GameLifecycleError(
                "Primary mission boundary completed Mission Action payload drifted."
            )
        if action.action_id in seen_action_ids:
            raise GameLifecycleError(
                "Primary mission boundary completed Mission Action inventory is duplicated."
            )
        seen_action_ids.add(action.action_id)
    return canonical


def _primary_unit_destruction_state_jsons(values: tuple[str, ...]) -> tuple[str, ...]:
    from warhammer40k_core.engine.scoring import (
        PrimaryUnitDestructionState,
        PrimaryUnitDestructionStatePayload,
    )

    canonical = _canonical_json_tuple("primary_unit_destruction_state_jsons", values)
    seen_destruction_ids: set[str] = set()
    for value in canonical:
        destruction = PrimaryUnitDestructionState.from_payload(
            cast(PrimaryUnitDestructionStatePayload, _json_object(value))
        )
        if value != json.dumps(
            destruction.to_payload(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ):
            raise GameLifecycleError(
                "Primary mission boundary destruction witness payload drifted."
            )
        if destruction.destruction_id in seen_destruction_ids:
            raise GameLifecycleError(
                "Primary mission boundary destruction witness inventory is duplicated."
            )
        seen_destruction_ids.add(destruction.destruction_id)
    return canonical


def _starting_strength_record_jsons(values: tuple[str, ...]) -> tuple[str, ...]:
    from warhammer40k_core.engine.unit_state import (
        StartingStrengthRecord,
        StartingStrengthRecordPayload,
    )

    canonical = _canonical_json_tuple("starting_strength_record_jsons", values)
    seen_unit_ids: set[str] = set()
    for value in canonical:
        payload = _json_object(value)
        if frozenset(payload) != _STARTING_STRENGTH_RECORD_KEYS:
            raise GameLifecycleError("Primary mission boundary Starting Strength fields drifted.")
        record = StartingStrengthRecord.from_payload(cast(StartingStrengthRecordPayload, payload))
        if value != json.dumps(
            record.to_payload(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ):
            raise GameLifecycleError("Primary mission boundary Starting Strength payload drifted.")
        if record.unit_instance_id in seen_unit_ids:
            raise GameLifecycleError(
                "Primary mission boundary Starting Strength inventory is duplicated."
            )
        seen_unit_ids.add(record.unit_instance_id)
    return canonical


def _object(
    payload: object,
    *,
    label: str,
    keys: tuple[str, ...],
) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError(f"{label} must be an object.")
    raw_object = cast(dict[object, object], payload)
    if any(type(key) is not str for key in raw_object):
        raise GameLifecycleError(f"{label} must be an object.")
    raw = cast(dict[str, object], raw_object)
    if frozenset(raw) != frozenset(keys):
        raise GameLifecycleError(f"{label} fields drifted.")
    return cast(dict[str, JsonValue], validate_json_value(raw))


def _object_with_optional(
    payload: object,
    *,
    label: str,
    required_keys: tuple[str, ...],
    optional_keys: tuple[str, ...],
) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError(f"{label} must be an object.")
    raw_object = cast(dict[object, object], payload)
    if any(type(key) is not str for key in raw_object):
        raise GameLifecycleError(f"{label} must be an object.")
    raw = cast(dict[str, object], raw_object)
    actual_keys = frozenset(raw)
    required = frozenset(required_keys)
    if not required <= actual_keys or not actual_keys <= required.union(optional_keys):
        raise GameLifecycleError(f"{label} fields drifted.")
    return cast(dict[str, JsonValue], validate_json_value(raw))


def _string(raw: dict[str, JsonValue], key: str) -> str:
    value = raw[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Primary mission boundary {key} must be a string.")
    return value


def _optional_string(raw: dict[str, JsonValue], key: str) -> str | None:
    value = raw[key]
    if value is not None and type(value) is not str:
        raise GameLifecycleError(f"Primary mission boundary {key} must be a string or null.")
    return value


def _int(raw: dict[str, JsonValue], key: str) -> int:
    value = raw[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Primary mission boundary {key} must be an int.")
    return value


def _bool(raw: dict[str, JsonValue], key: str) -> bool:
    value = raw[key]
    if type(value) is not bool:
        raise GameLifecycleError(f"Primary mission boundary {key} must be a bool.")
    return value


def _list(raw: dict[str, JsonValue], key: str) -> list[JsonValue]:
    value = raw[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Primary mission boundary {key} must be a list.")
    return value


def _string_tuple(raw: dict[str, JsonValue], key: str) -> tuple[str, ...]:
    values = _list(raw, key)
    if any(type(value) is not str for value in values):
        raise GameLifecycleError(f"Primary mission boundary {key} must contain strings.")
    return cast(tuple[str, ...], tuple(values))


def _identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Primary mission boundary {field_name} must be a tuple.")
    ordered = tuple(sorted(_validate_identifier(field_name, value) for value in values))
    if len(set(ordered)) != len(ordered):
        raise GameLifecycleError(f"Primary mission boundary {field_name} is duplicated.")
    return ordered


def _canonical_json_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Primary mission boundary {field_name} must be a tuple.")
    ordered = tuple(sorted(_canonical_json_object(field_name, value) for value in values))
    if len(set(ordered)) != len(ordered):
        raise GameLifecycleError(f"Primary mission boundary {field_name} is duplicated.")
    return ordered


def _canonical_json_object(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Primary mission boundary {field_name} must be JSON text.")
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise GameLifecycleError(
            f"Primary mission boundary {field_name} must be canonical JSON."
        ) from exc
    if not isinstance(decoded, dict):
        raise GameLifecycleError(f"Primary mission boundary {field_name} must encode an object.")
    canonical = json.dumps(decoded, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    if value != canonical:
        raise GameLifecycleError(f"Primary mission boundary {field_name} must be canonical JSON.")
    return value


def _optional_canonical_json_object(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _canonical_json_object(field_name, value)


def _optional_identifier(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _json_object(value: str) -> dict[str, JsonValue]:
    decoded: object = json.loads(value)
    if not isinstance(decoded, dict):
        raise GameLifecycleError("Primary mission boundary JSON must encode an object.")
    decoded_object = cast(dict[object, object], decoded)
    return cast(dict[str, JsonValue], validate_json_value(decoded_object))


def _json_string_list(raw: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    value = raw.get(key)
    if not isinstance(value, list) or any(type(item) is not str for item in value):
        raise GameLifecycleError(
            "Primary mission boundary Objective Control modifier inventory is invalid."
        )
    return cast(tuple[str, ...], tuple(value))


__all__ = (
    "PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT",
    "PRIMARY_MISSION_BOUNDARY_CHECKPOINT_SCHEMA",
    "PrimaryMissionBoundaryCheckpoint",
    "PrimaryMissionBoundaryCheckpointReference",
    "PrimaryMissionBoundaryModelState",
    "PrimaryMissionObjectiveControlModifierSource",
)
