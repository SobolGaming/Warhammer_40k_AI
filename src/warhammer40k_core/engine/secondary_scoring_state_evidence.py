from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256, validate_sha256_hex
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.objective_control import ObjectiveControlRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    objective_control_record_hash,
)
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    SecondaryObjectiveCleanseState,
    SecondaryObjectiveCleanseStatePayload,
    SecondaryTerrainPlunderState,
    SecondaryTerrainPlunderStatePayload,
    SecondaryUnitDestructionState,
    SecondaryUnitDestructionStatePayload,
    VictoryPointAward,
    VictoryPointSourceKind,
    secondary_mission_card_mode_from_token,
    secondary_mission_card_status_from_token,
    victory_point_source_kind_from_token,
)
from warhammer40k_core.engine.secondary_scoring_conditions import SecondaryScoringConditionContext
from warhammer40k_core.engine.secondary_scoring_occupancy import (
    SecondaryBattlefieldOccupancy,
    SecondaryBattlefieldOccupancyPayload,
)
from warhammer40k_core.engine.unit_state import (
    StartingStrengthRecord,
    StartingStrengthRecordPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mission_setup import MissionSetup

SECONDARY_SCORING_STATE_EVIDENCE_SCHEMA = "secondary-scoring-state-evidence-v1"
SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY = "secondary_scoring_state_evidence_id"
SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY = "secondary_scoring_state_evidence_hash"
_EVIDENCE_ID_PREFIX = "secondary-scoring-state-evidence"
_validate_identifier = IdentifierValidator(GameLifecycleError)


class SecondaryScoringStateEvidencePayload(TypedDict):
    schema_version: str
    game_id: str
    scoring_player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    secondary_mission_id: str
    card_mode: str
    card_status: str
    card_battle_round: int
    selection_payload: JsonValue | None
    occupancy: SecondaryBattlefieldOccupancyPayload | None
    unit_destruction_states: list[SecondaryUnitDestructionStatePayload]
    objective_cleanse_states: list[SecondaryObjectiveCleanseStatePayload]
    terrain_plunder_states: list[SecondaryTerrainPlunderStatePayload]
    starting_strength_records: list[StartingStrengthRecordPayload]
    enemy_unit_ids_in_player_deployment_zone: list[str]
    objective_control_record_id: str
    objective_control_record_hash: str
    scoring_rule_ids: list[str]
    scoring_rule_conditions: list[str]
    scoring_rule_source_ids: list[str]
    evidence_id: str
    evidence_hash: str


@dataclass(frozen=True, slots=True)
class SecondaryScoringStateEvidence:
    schema_version: str
    game_id: str
    scoring_player_id: str
    active_player_id: str
    battle_round: int
    phase: str
    secondary_mission_id: str
    card_mode: SecondaryMissionCardMode
    card_status: SecondaryMissionCardStatus
    card_battle_round: int
    selection_payload: JsonValue | None
    occupancy: SecondaryBattlefieldOccupancy | None
    unit_destruction_states: tuple[SecondaryUnitDestructionState, ...]
    objective_cleanse_states: tuple[SecondaryObjectiveCleanseState, ...]
    terrain_plunder_states: tuple[SecondaryTerrainPlunderState, ...]
    starting_strength_records: tuple[StartingStrengthRecord, ...]
    enemy_unit_ids_in_player_deployment_zone: tuple[str, ...]
    objective_control_record_id: str
    objective_control_record_hash: str
    scoring_rule_ids: tuple[str, ...]
    scoring_rule_conditions: tuple[str, ...]
    scoring_rule_source_ids: tuple[str, ...]
    evidence_id: str
    evidence_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != SECONDARY_SCORING_STATE_EVIDENCE_SCHEMA:
            raise GameLifecycleError("Secondary scoring state evidence schema is unsupported.")
        for field_name in (
            "game_id",
            "scoring_player_id",
            "active_player_id",
            "phase",
            "secondary_mission_id",
            "objective_control_record_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(
                    f"SecondaryScoringStateEvidence {field_name}",
                    getattr(self, field_name),
                ),
            )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("SecondaryScoringStateEvidence battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "card_battle_round",
            _validate_positive_int(
                "SecondaryScoringStateEvidence card_battle_round",
                self.card_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "card_mode",
            secondary_mission_card_mode_from_token(self.card_mode),
        )
        object.__setattr__(
            self,
            "card_status",
            secondary_mission_card_status_from_token(self.card_status),
        )
        object.__setattr__(
            self,
            "selection_payload",
            None if self.selection_payload is None else validate_json_value(self.selection_payload),
        )
        if self.occupancy is not None and type(self.occupancy) is not SecondaryBattlefieldOccupancy:
            raise GameLifecycleError("Secondary scoring state evidence occupancy is invalid.")
        object.__setattr__(
            self,
            "enemy_unit_ids_in_player_deployment_zone",
            _identifier_tuple(
                "enemy_unit_ids_in_player_deployment_zone",
                self.enemy_unit_ids_in_player_deployment_zone,
            ),
        )
        object.__setattr__(
            self,
            "scoring_rule_ids",
            _identifier_tuple("scoring_rule_ids", self.scoring_rule_ids),
        )
        object.__setattr__(
            self,
            "scoring_rule_conditions",
            _identifier_tuple("scoring_rule_conditions", self.scoring_rule_conditions),
        )
        object.__setattr__(
            self,
            "scoring_rule_source_ids",
            _identifier_tuple("scoring_rule_source_ids", self.scoring_rule_source_ids),
        )
        object.__setattr__(
            self,
            "objective_control_record_hash",
            validate_sha256_hex(
                self.objective_control_record_hash,
                field_name="SecondaryScoringStateEvidence objective_control_record_hash",
                error_type=GameLifecycleError,
            ),
        )
        object.__setattr__(
            self,
            "evidence_hash",
            validate_sha256_hex(
                self.evidence_hash,
                field_name="SecondaryScoringStateEvidence evidence_hash",
                error_type=GameLifecycleError,
            ),
        )
        object.__setattr__(
            self,
            "evidence_id",
            _validate_identifier("SecondaryScoringStateEvidence evidence_id", self.evidence_id),
        )
        expected_hash = canonical_payload_sha256(self._content_payload())
        if self.evidence_hash != expected_hash:
            raise GameLifecycleError("Secondary scoring state evidence hash drifted.")
        if self.evidence_id != f"{_EVIDENCE_ID_PREFIX}:{expected_hash}":
            raise GameLifecycleError("Secondary scoring state evidence identity drifted.")

    def _content_payload(self) -> dict[str, object]:
        payload = dict(self.to_payload())
        payload.pop("evidence_id")
        payload.pop("evidence_hash")
        return payload

    def to_payload(self) -> SecondaryScoringStateEvidencePayload:
        return {
            "schema_version": self.schema_version,
            "game_id": self.game_id,
            "scoring_player_id": self.scoring_player_id,
            "active_player_id": self.active_player_id,
            "battle_round": self.battle_round,
            "phase": self.phase,
            "secondary_mission_id": self.secondary_mission_id,
            "card_mode": self.card_mode.value,
            "card_status": self.card_status.value,
            "card_battle_round": self.card_battle_round,
            "selection_payload": self.selection_payload,
            "occupancy": None if self.occupancy is None else self.occupancy.to_payload(),
            "unit_destruction_states": [
                state.to_payload() for state in self.unit_destruction_states
            ],
            "objective_cleanse_states": [
                state.to_payload() for state in self.objective_cleanse_states
            ],
            "terrain_plunder_states": [state.to_payload() for state in self.terrain_plunder_states],
            "starting_strength_records": [
                record.to_payload() for record in self.starting_strength_records
            ],
            "enemy_unit_ids_in_player_deployment_zone": list(
                self.enemy_unit_ids_in_player_deployment_zone
            ),
            "objective_control_record_id": self.objective_control_record_id,
            "objective_control_record_hash": self.objective_control_record_hash,
            "scoring_rule_ids": list(self.scoring_rule_ids),
            "scoring_rule_conditions": list(self.scoring_rule_conditions),
            "scoring_rule_source_ids": list(self.scoring_rule_source_ids),
            "evidence_id": self.evidence_id,
            "evidence_hash": self.evidence_hash,
        }

    @classmethod
    def from_payload(cls, payload: SecondaryScoringStateEvidencePayload) -> Self:
        occupancy_payload = payload["occupancy"]
        return cls(
            schema_version=payload["schema_version"],
            game_id=payload["game_id"],
            scoring_player_id=payload["scoring_player_id"],
            active_player_id=payload["active_player_id"],
            battle_round=payload["battle_round"],
            phase=payload["phase"],
            secondary_mission_id=payload["secondary_mission_id"],
            card_mode=secondary_mission_card_mode_from_token(payload["card_mode"]),
            card_status=secondary_mission_card_status_from_token(payload["card_status"]),
            card_battle_round=payload["card_battle_round"],
            selection_payload=payload["selection_payload"],
            occupancy=(
                None
                if occupancy_payload is None
                else SecondaryBattlefieldOccupancy.from_payload(occupancy_payload)
            ),
            unit_destruction_states=tuple(
                SecondaryUnitDestructionState.from_payload(state)
                for state in payload["unit_destruction_states"]
            ),
            objective_cleanse_states=tuple(
                SecondaryObjectiveCleanseState.from_payload(state)
                for state in payload["objective_cleanse_states"]
            ),
            terrain_plunder_states=tuple(
                SecondaryTerrainPlunderState.from_payload(state)
                for state in payload["terrain_plunder_states"]
            ),
            starting_strength_records=tuple(
                StartingStrengthRecord.from_payload(record)
                for record in payload["starting_strength_records"]
            ),
            enemy_unit_ids_in_player_deployment_zone=tuple(
                payload["enemy_unit_ids_in_player_deployment_zone"]
            ),
            objective_control_record_id=payload["objective_control_record_id"],
            objective_control_record_hash=payload["objective_control_record_hash"],
            scoring_rule_ids=tuple(payload["scoring_rule_ids"]),
            scoring_rule_conditions=tuple(payload["scoring_rule_conditions"]),
            scoring_rule_source_ids=tuple(payload["scoring_rule_source_ids"]),
            evidence_id=payload["evidence_id"],
            evidence_hash=payload["evidence_hash"],
        )

    @classmethod
    def create(
        cls,
        *,
        game_id: str,
        scoring_player_id: str,
        active_player_id: str,
        battle_round: int,
        phase: str,
        secondary_mission_id: str,
        card_mode: SecondaryMissionCardMode,
        card_status: SecondaryMissionCardStatus,
        card_battle_round: int,
        selection_payload: JsonValue | None,
        occupancy: SecondaryBattlefieldOccupancy | None,
        unit_destruction_states: tuple[SecondaryUnitDestructionState, ...],
        objective_cleanse_states: tuple[SecondaryObjectiveCleanseState, ...],
        terrain_plunder_states: tuple[SecondaryTerrainPlunderState, ...],
        starting_strength_records: tuple[StartingStrengthRecord, ...],
        enemy_unit_ids_in_player_deployment_zone: tuple[str, ...],
        objective_control_record_id: str,
        objective_control_record_hash: str,
        scoring_rule_ids: tuple[str, ...],
        scoring_rule_conditions: tuple[str, ...],
        scoring_rule_source_ids: tuple[str, ...],
    ) -> Self:
        occupancy_payload = None if occupancy is None else occupancy.to_payload()
        validated_selection = (
            None if selection_payload is None else validate_json_value(selection_payload)
        )
        content: dict[str, object] = {
            "schema_version": SECONDARY_SCORING_STATE_EVIDENCE_SCHEMA,
            "game_id": game_id,
            "scoring_player_id": scoring_player_id,
            "active_player_id": active_player_id,
            "battle_round": battle_round,
            "phase": phase,
            "secondary_mission_id": secondary_mission_id,
            "card_mode": card_mode.value,
            "card_status": card_status.value,
            "card_battle_round": card_battle_round,
            "selection_payload": validated_selection,
            "occupancy": occupancy_payload,
            "unit_destruction_states": [state.to_payload() for state in unit_destruction_states],
            "objective_cleanse_states": [state.to_payload() for state in objective_cleanse_states],
            "terrain_plunder_states": [state.to_payload() for state in terrain_plunder_states],
            "starting_strength_records": [
                record.to_payload() for record in starting_strength_records
            ],
            "enemy_unit_ids_in_player_deployment_zone": list(
                enemy_unit_ids_in_player_deployment_zone
            ),
            "objective_control_record_id": objective_control_record_id,
            "objective_control_record_hash": objective_control_record_hash,
            "scoring_rule_ids": list(scoring_rule_ids),
            "scoring_rule_conditions": list(scoring_rule_conditions),
            "scoring_rule_source_ids": list(scoring_rule_source_ids),
        }
        evidence_hash = canonical_payload_sha256(content)
        return cls(
            schema_version=SECONDARY_SCORING_STATE_EVIDENCE_SCHEMA,
            game_id=game_id,
            scoring_player_id=scoring_player_id,
            active_player_id=active_player_id,
            battle_round=battle_round,
            phase=phase,
            secondary_mission_id=secondary_mission_id,
            card_mode=card_mode,
            card_status=card_status,
            card_battle_round=card_battle_round,
            selection_payload=validated_selection,
            occupancy=occupancy,
            unit_destruction_states=unit_destruction_states,
            objective_cleanse_states=objective_cleanse_states,
            terrain_plunder_states=terrain_plunder_states,
            starting_strength_records=starting_strength_records,
            enemy_unit_ids_in_player_deployment_zone=enemy_unit_ids_in_player_deployment_zone,
            objective_control_record_id=objective_control_record_id,
            objective_control_record_hash=objective_control_record_hash,
            scoring_rule_ids=scoring_rule_ids,
            scoring_rule_conditions=scoring_rule_conditions,
            scoring_rule_source_ids=scoring_rule_source_ids,
            evidence_id=f"{_EVIDENCE_ID_PREFIX}:{evidence_hash}",
            evidence_hash=evidence_hash,
        )


def build_secondary_scoring_state_evidence(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    record: ObjectiveControlRecord,
    context: SecondaryScoringConditionContext,
    award: VictoryPointAward,
) -> SecondaryScoringStateEvidence:
    metadata = award.metadata
    if not isinstance(metadata, dict):
        raise GameLifecycleError("Secondary scoring evidence requires object award metadata.")
    return SecondaryScoringStateEvidence.create(
        game_id=state.game_id,
        scoring_player_id=card.player_id,
        active_player_id=record.active_player_id,
        battle_round=record.battle_round,
        phase=record.phase,
        secondary_mission_id=card.secondary_mission_id,
        card_mode=card.mode,
        card_status=card.status,
        card_battle_round=card.battle_round,
        selection_payload=_selection_payload_at_record_boundary(card=card, record=record),
        occupancy=context.occupancy,
        unit_destruction_states=tuple(
            value
            for value in context.unit_destruction_states
            if type(value) is SecondaryUnitDestructionState
        ),
        objective_cleanse_states=tuple(
            value
            for value in context.objective_cleanse_states
            if type(value) is SecondaryObjectiveCleanseState
        ),
        terrain_plunder_states=tuple(
            value
            for value in context.terrain_plunder_states
            if type(value) is SecondaryTerrainPlunderState
        ),
        starting_strength_records=context.starting_strength_records,
        enemy_unit_ids_in_player_deployment_zone=context.enemy_unit_ids_in_player_deployment_zone,
        objective_control_record_id=record.record_id,
        objective_control_record_hash=objective_control_record_hash(record),
        scoring_rule_ids=_string_tuple(metadata.get("scoring_rule_ids"), "scoring_rule_ids"),
        scoring_rule_conditions=_string_tuple(
            metadata.get("scoring_rule_conditions"),
            "scoring_rule_conditions",
        ),
        scoring_rule_source_ids=_string_tuple(
            metadata.get("scoring_rule_source_ids"),
            "scoring_rule_source_ids",
        ),
    )


def capture_secondary_scoring_state_evidence(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    record: ObjectiveControlRecord,
    context: SecondaryScoringConditionContext,
    award: VictoryPointAward,
) -> SecondaryScoringStateEvidence:
    evidence = build_secondary_scoring_state_evidence(
        state=state,
        card=card,
        record=record,
        context=context,
        award=award,
    )
    from warhammer40k_core.engine.secondary_scoring_state_evidence_authority import (
        validate_secondary_scoring_state_evidence_authority,
    )

    validate_secondary_scoring_state_evidence_authority(evidence, state=state)
    matches = tuple(
        stored
        for stored in state.secondary_scoring_state_evidence_records
        if stored.evidence_id == evidence.evidence_id
    )
    if matches:
        if len(matches) != 1 or matches[0] != evidence:
            raise GameLifecycleError("Secondary scoring evidence identity is ambiguous.")
        return matches[0]
    state.record_secondary_scoring_state_evidence(evidence)
    return evidence


def bind_secondary_scoring_state_evidence(
    award: VictoryPointAward,
    evidence: SecondaryScoringStateEvidence,
) -> VictoryPointAward:
    metadata = award.metadata
    if not isinstance(metadata, dict):
        raise GameLifecycleError("Secondary VP metadata must be an object.")
    bound: dict[str, JsonValue] = dict(metadata)
    if SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY in bound:
        raise GameLifecycleError("Secondary VP metadata already binds scoring-state evidence.")
    bound[SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY] = evidence.evidence_id
    bound[SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY] = evidence.evidence_hash
    bound["scoring_turn_active_player_id"] = evidence.active_player_id
    return replace(award, metadata=validate_json_value(bound))


def secondary_scoring_condition_context_from_evidence(
    *,
    evidence: SecondaryScoringStateEvidence,
    record: ObjectiveControlRecord,
    mission_setup: MissionSetup,
) -> SecondaryScoringConditionContext:
    if evidence.objective_control_record_id != record.record_id:
        raise GameLifecycleError("Secondary scoring evidence record identity drifted.")
    if evidence.objective_control_record_hash != objective_control_record_hash(record):
        raise GameLifecycleError("Secondary scoring evidence record hash drifted.")
    return SecondaryScoringConditionContext(
        record=record,
        mission_setup=mission_setup,
        player_id=evidence.scoring_player_id,
        unit_destruction_states=evidence.unit_destruction_states,
        objective_cleanse_states=evidence.objective_cleanse_states,
        terrain_plunder_states=evidence.terrain_plunder_states,
        enemy_unit_ids_in_player_deployment_zone=(
            evidence.enemy_unit_ids_in_player_deployment_zone
        ),
        starting_strength_records=evidence.starting_strength_records,
        occupancy=evidence.occupancy,
    )


def require_bound_secondary_scoring_state_evidence(
    *,
    metadata: JsonValue,
    state: GameState,
    player_id: str,
    source_id: str,
    source_kind: VictoryPointSourceKind,
    card: SecondaryMissionCardState,
    record: ObjectiveControlRecord,
) -> SecondaryScoringStateEvidence:
    if not isinstance(metadata, dict):
        raise GameLifecycleError("Secondary VP metadata must be an object.")
    evidence_id = metadata.get(SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY)
    evidence_hash = metadata.get(SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY)
    if type(evidence_id) is not str or type(evidence_hash) is not str:
        raise GameLifecycleError("Secondary VP metadata must bind scoring-state evidence.")
    matches = tuple(
        stored
        for stored in state.secondary_scoring_state_evidence_records
        if stored.evidence_id == evidence_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Secondary scoring-state evidence is missing.")
    evidence = matches[0]
    if evidence.evidence_hash != evidence_hash:
        raise GameLifecycleError("Secondary scoring-state evidence hash drifted.")
    validate_secondary_scoring_state_evidence_binding(
        evidence=evidence,
        metadata=metadata,
        state=state,
        player_id=player_id,
        source_id=source_id,
        source_kind=source_kind,
        card=card,
        record=record,
    )
    return evidence


def validate_secondary_scoring_state_evidence_binding(
    *,
    evidence: SecondaryScoringStateEvidence,
    metadata: JsonValue,
    state: GameState,
    player_id: str,
    source_id: str,
    source_kind: VictoryPointSourceKind,
    card: SecondaryMissionCardState,
    record: ObjectiveControlRecord,
) -> None:
    """Bind immutable condition evidence to one scoring principal, card, and boundary."""
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.secondary_scoring_inventory import (
        canonical_secondary_mission_id,
    )

    if type(evidence) is not SecondaryScoringStateEvidence:
        raise GameLifecycleError("Secondary scoring evidence binding requires typed evidence.")
    if type(state) is not GameState:
        raise GameLifecycleError("Secondary scoring evidence binding requires GameState.")
    if type(card) is not SecondaryMissionCardState:
        raise GameLifecycleError("Secondary scoring evidence binding requires a card.")
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError("Secondary scoring evidence binding requires an objective record.")
    if not isinstance(metadata, dict):
        raise GameLifecycleError("Secondary VP metadata must be an object.")

    requested_player = _validate_identifier("player_id", player_id)
    requested_secondary = canonical_secondary_mission_id(source_id)
    requested_kind = victory_point_source_kind_from_token(source_kind)
    if requested_kind is VictoryPointSourceKind.FIXED_SECONDARY:
        expected_mode = SecondaryMissionCardMode.FIXED
    elif requested_kind is VictoryPointSourceKind.TACTICAL_SECONDARY:
        expected_mode = SecondaryMissionCardMode.TACTICAL
    else:
        raise GameLifecycleError("Secondary scoring evidence requires a Secondary source kind.")

    if record.game_id != state.game_id or evidence.game_id != state.game_id:
        raise GameLifecycleError("Secondary scoring evidence game identity drifted.")
    if card.player_id != requested_player or evidence.scoring_player_id != requested_player:
        raise GameLifecycleError("Secondary scoring evidence player identity drifted.")
    if (
        canonical_secondary_mission_id(card.secondary_mission_id) != requested_secondary
        or evidence.secondary_mission_id != requested_secondary
    ):
        raise GameLifecycleError("Secondary scoring evidence mission identity drifted.")
    if card.mode is not expected_mode or evidence.card_mode is not expected_mode:
        raise GameLifecycleError("Secondary scoring evidence card mode drifted.")
    if evidence.card_battle_round != card.battle_round:
        raise GameLifecycleError("Secondary scoring evidence card battle round drifted.")
    if evidence.card_status is not SecondaryMissionCardStatus.ACTIVE:
        raise GameLifecycleError("Secondary scoring evidence card was not active at capture.")
    if evidence.active_player_id != record.active_player_id:
        raise GameLifecycleError("Secondary scoring evidence active player drifted.")
    if evidence.battle_round != record.battle_round:
        raise GameLifecycleError("Secondary scoring evidence battle round drifted.")
    if evidence.phase != record.phase:
        raise GameLifecycleError("Secondary scoring evidence phase drifted.")
    if evidence.objective_control_record_id != record.record_id:
        raise GameLifecycleError("Secondary scoring evidence record identity drifted.")
    if evidence.objective_control_record_hash != objective_control_record_hash(record):
        raise GameLifecycleError("Secondary scoring evidence record hash drifted.")

    if evidence.scoring_rule_ids != _string_tuple(
        metadata.get("scoring_rule_ids"),
        "scoring_rule_ids",
    ):
        raise GameLifecycleError("Secondary scoring evidence scoring rule IDs drifted.")
    if evidence.scoring_rule_conditions != _string_tuple(
        metadata.get("scoring_rule_conditions"),
        "scoring_rule_conditions",
    ):
        raise GameLifecycleError("Secondary scoring evidence scoring rule conditions drifted.")
    if evidence.scoring_rule_source_ids != _string_tuple(
        metadata.get("scoring_rule_source_ids"),
        "scoring_rule_source_ids",
    ):
        raise GameLifecycleError("Secondary scoring evidence scoring rule source IDs drifted.")
    scoring_turn_active_player_id = metadata.get("scoring_turn_active_player_id")
    if (
        type(scoring_turn_active_player_id) is not str
        or scoring_turn_active_player_id != evidence.active_player_id
    ):
        raise GameLifecycleError("Secondary scoring evidence scoring-turn active player drifted.")


def validate_secondary_scoring_state_evidence_records(
    records: object,
    *,
    game_id: str,
) -> list[SecondaryScoringStateEvidence]:
    if not isinstance(records, list):
        raise GameLifecycleError("Secondary scoring state evidence records must be a list.")
    validated: list[SecondaryScoringStateEvidence] = []
    seen: set[str] = set()
    for value in cast(list[object], records):
        if type(value) is not SecondaryScoringStateEvidence:
            raise GameLifecycleError(
                "Secondary scoring state evidence records must contain evidence values."
            )
        if value.game_id != game_id:
            raise GameLifecycleError("Secondary scoring state evidence game_id drift.")
        if value.evidence_id in seen:
            raise GameLifecycleError("Secondary scoring state evidence records must be unique.")
        seen.add(value.evidence_id)
        validated.append(value)
    return sorted(validated, key=lambda stored: stored.evidence_id)


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if type(value) is not list or not value:
        raise GameLifecycleError(f"Secondary scoring evidence requires {field_name}.")
    return _identifier_tuple(field_name, tuple(cast(list[object], value)))


def _selection_payload_at_record_boundary(
    *,
    card: SecondaryMissionCardState,
    record: ObjectiveControlRecord,
) -> JsonValue | None:
    from warhammer40k_core.engine.secondary_mission_selection import (
        secondary_mission_selection_from_json,
    )

    selection = secondary_mission_selection_from_json(card.selection_payload)
    if selection is None or record.record_id not in selection.resolved_objective_control_record_ids:
        return card.selection_payload
    return replace(
        selection,
        resolved_objective_control_record_ids=tuple(
            record_id
            for record_id in selection.resolved_objective_control_record_ids
            if record_id != record.record_id
        ),
    ).to_json_value()


def _identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(identifiers)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value <= 0:
        raise GameLifecycleError(f"{field_name} must be a positive int.")
    return value


__all__ = (
    "SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY",
    "SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY",
    "SECONDARY_SCORING_STATE_EVIDENCE_SCHEMA",
    "SecondaryScoringStateEvidence",
    "SecondaryScoringStateEvidencePayload",
    "bind_secondary_scoring_state_evidence",
    "build_secondary_scoring_state_evidence",
    "capture_secondary_scoring_state_evidence",
    "require_bound_secondary_scoring_state_evidence",
    "secondary_scoring_condition_context_from_evidence",
    "validate_secondary_scoring_state_evidence_binding",
    "validate_secondary_scoring_state_evidence_records",
)
