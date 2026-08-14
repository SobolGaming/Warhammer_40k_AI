from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.destruction_provenance import ModelDestructionAttribution
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    RulesUnitObjectiveProximityWitness,
)


@dataclass(frozen=True, slots=True)
class PrimaryUnitDestructionEvidence:
    destruction_id: str
    battle_round: int
    active_player_id: str
    destroying_player_id: str | None
    destroyed_player_id: str
    destroyed_unit_instance_id: str
    destruction_attribution: ModelDestructionAttribution | None
    source_rules_unit_objective_proximity_witness: RulesUnitObjectiveProximityWitness | None
    started_turn_terrain_feature_ids: tuple[str, ...]
    started_turn_objective_marker_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "destruction_id",
            _validate_identifier(
                "Primary destruction evidence destruction_id",
                self.destruction_id,
            ),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("Primary destruction evidence battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "Primary destruction evidence active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "destroying_player_id",
            _validate_optional_identifier(
                "Primary destruction evidence destroying_player_id",
                self.destroying_player_id,
            ),
        )
        object.__setattr__(
            self,
            "destroyed_player_id",
            _validate_identifier(
                "Primary destruction evidence destroyed_player_id",
                self.destroyed_player_id,
            ),
        )
        object.__setattr__(
            self,
            "destroyed_unit_instance_id",
            _validate_identifier(
                "Primary destruction evidence destroyed_unit_instance_id",
                self.destroyed_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "destruction_attribution",
            _validate_destruction_attribution(self.destruction_attribution),
        )
        object.__setattr__(
            self,
            "source_rules_unit_objective_proximity_witness",
            _validate_source_objective_witness(self.source_rules_unit_objective_proximity_witness),
        )
        object.__setattr__(
            self,
            "started_turn_terrain_feature_ids",
            _validate_identifier_tuple(
                "Primary destruction evidence started_turn_terrain_feature_ids",
                self.started_turn_terrain_feature_ids,
            ),
        )
        object.__setattr__(
            self,
            "started_turn_objective_marker_ids",
            _validate_identifier_tuple(
                "Primary destruction evidence started_turn_objective_marker_ids",
                self.started_turn_objective_marker_ids,
            ),
        )
        attribution = self.destruction_attribution
        source_witness = self.source_rules_unit_objective_proximity_witness
        if attribution is None:
            if self.destroying_player_id is not None or source_witness is not None:
                raise GameLifecycleError(
                    "Unattributed Primary destruction evidence cannot identify a destroyer."
                )
            return
        if attribution.destroying_player_id != self.destroying_player_id:
            raise GameLifecycleError(
                "Primary destruction evidence destroying-player attribution drift."
            )
        source_rules_unit_id = attribution.source_rules_unit_instance_id
        if source_rules_unit_id is None:
            if source_witness is not None:
                raise GameLifecycleError(
                    "Player-only Primary destruction attribution cannot carry a source-unit "
                    "objective witness."
                )
            return
        if source_witness is None or source_witness.rules_unit_instance_id != source_rules_unit_id:
            raise GameLifecycleError(
                "Source-unit Primary destruction attribution requires its exact objective "
                "proximity witness."
            )


def primary_score_count_evidence(
    *,
    score_count: int,
    controlled_objective_ids: tuple[str, ...] = (),
    home_objective_ids: tuple[str, ...] = (),
    turn_start_controlled_objective_ids: tuple[str, ...] = (),
    trapped_terrain_feature_ids: tuple[str, ...] = (),
    destroyed_unit_instance_ids: tuple[str, ...] = (),
    destruction_ids: tuple[str, ...] | None = None,
) -> dict[str, JsonValue]:
    evidence: dict[str, JsonValue] = {
        "score_count": _validate_non_negative_int("score_count", score_count),
        "controlled_objective_ids": list(
            _validate_identifier_tuple("controlled_objective_ids", controlled_objective_ids)
        ),
        "home_objective_ids": list(
            _validate_identifier_tuple("home_objective_ids", home_objective_ids)
        ),
        "turn_start_controlled_objective_ids": list(
            _validate_identifier_tuple(
                "turn_start_controlled_objective_ids",
                turn_start_controlled_objective_ids,
            )
        ),
        "trapped_terrain_feature_ids": list(
            _validate_identifier_tuple(
                "trapped_terrain_feature_ids",
                trapped_terrain_feature_ids,
            )
        ),
        "destroyed_unit_instance_ids": list(
            _validate_identifier_tuple(
                "destroyed_unit_instance_ids",
                destroyed_unit_instance_ids,
            )
        ),
    }
    if destruction_ids is not None:
        evidence["destruction_ids"] = list(
            _validate_identifier_tuple(
                "destruction_ids",
                destruction_ids,
            )
        )
    return evidence


def cross_turn_destruction_comparison_evidence(
    *,
    turn_order: tuple[str, ...],
    battle_round: int,
    active_player_id: str,
    scoring_player_id: str,
    destruction_evidence: tuple[PrimaryUnitDestructionEvidence, ...],
) -> dict[str, JsonValue]:
    ordered_players = _validate_identifier_tuple(
        "Cross-turn destruction comparison turn_order",
        turn_order,
        min_length=2,
        preserve_order=True,
    )
    requested_round = _validate_positive_int(
        "Cross-turn destruction comparison battle_round",
        battle_round,
    )
    requested_active = _validate_identifier(
        "Cross-turn destruction comparison active_player_id",
        active_player_id,
    )
    requested_scorer = _validate_identifier(
        "Cross-turn destruction comparison scoring_player_id",
        scoring_player_id,
    )
    if requested_active not in ordered_players:
        raise GameLifecycleError(
            "Cross-turn destruction comparison active player is not in turn_order."
        )
    if requested_scorer not in ordered_players:
        raise GameLifecycleError(
            "Cross-turn destruction comparison scoring player is not in turn_order."
        )
    if requested_scorer != requested_active:
        raise GameLifecycleError(
            "Cross-turn destruction comparison scoring player must be the active player."
        )
    evidence_rows = _validate_destruction_evidence(destruction_evidence)
    if any(
        row.active_player_id not in ordered_players
        or row.destroyed_player_id not in ordered_players
        for row in evidence_rows
    ):
        raise GameLifecycleError(
            "Cross-turn destruction comparison destruction player is not in turn_order."
        )
    previous_battle_round, previous_active_player_id = _previous_player_turn_key(
        turn_order=ordered_players,
        battle_round=requested_round,
        active_player_id=requested_active,
    )
    current_turn_enemy_rows = tuple(
        row
        for row in evidence_rows
        if row.battle_round == requested_round
        and row.active_player_id == requested_active
        and row.destroyed_player_id != requested_scorer
    )
    previous_turn_friendly_rows = tuple(
        row
        for row in evidence_rows
        if row.battle_round == previous_battle_round
        and row.active_player_id == previous_active_player_id
        and row.destroyed_player_id == requested_scorer
    )
    evidence = primary_score_count_evidence(
        score_count=(1 if len(current_turn_enemy_rows) > len(previous_turn_friendly_rows) else 0),
        destroyed_unit_instance_ids=tuple(
            sorted({row.destroyed_unit_instance_id for row in current_turn_enemy_rows})
        ),
        destruction_ids=tuple(row.destruction_id for row in current_turn_enemy_rows),
    )
    evidence.update(
        {
            "current_turn_battle_round": requested_round,
            "current_turn_active_player_id": requested_active,
            "previous_turn_battle_round": previous_battle_round,
            "previous_turn_active_player_id": previous_active_player_id,
            "enemy_destroyed_unit_instance_ids": cast(
                JsonValue,
                sorted({row.destroyed_unit_instance_id for row in current_turn_enemy_rows}),
            ),
            "friendly_destroyed_unit_instance_ids": cast(
                JsonValue,
                sorted({row.destroyed_unit_instance_id for row in previous_turn_friendly_rows}),
            ),
            "enemy_destruction_ids": [row.destruction_id for row in current_turn_enemy_rows],
            "friendly_destruction_ids": [row.destruction_id for row in previous_turn_friendly_rows],
            "enemy_units_destroyed": len(current_turn_enemy_rows),
            "friendly_units_destroyed": len(previous_turn_friendly_rows),
        }
    )
    return evidence


def opponent_home_control_evidence(
    *,
    mission_setup: MissionSetup,
    player_id: str,
    controlled_objective_ids: tuple[str, ...],
) -> dict[str, JsonValue]:
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Opponent-home scoring requires MissionSetup.")
    requested_player = _validate_identifier("Opponent-home scoring player_id", player_id)
    controlled_ids = _validate_identifier_tuple(
        "Opponent-home scoring controlled_objective_ids",
        controlled_objective_ids,
    )
    mission_player_ids = (
        mission_setup.attacker_player_id,
        mission_setup.defender_player_id,
    )
    if requested_player not in mission_player_ids:
        raise GameLifecycleError("Opponent-home scoring player is not in MissionSetup.")
    opponent_player_id = next(
        mission_player_id
        for mission_player_id in mission_player_ids
        if mission_player_id != requested_player
    )
    opponent_home_ids = home_objective_ids(
        mission_setup,
        player_id=opponent_player_id,
    )
    controlled_opponent_home_ids = tuple(
        objective_id for objective_id in controlled_ids if objective_id in opponent_home_ids
    )
    evidence = primary_score_count_evidence(
        score_count=1 if controlled_opponent_home_ids else 0,
        controlled_objective_ids=controlled_opponent_home_ids,
        home_objective_ids=opponent_home_ids,
    )
    evidence["opponent_home_objective_ids"] = list(opponent_home_ids)
    return evidence


def home_objective_ids(
    mission_setup: MissionSetup,
    *,
    player_id: str,
) -> tuple[str, ...]:
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Home objective lookup requires MissionSetup.")
    requested_player = _validate_identifier("Home objective player_id", player_id)
    if requested_player == mission_setup.attacker_player_id:
        home_role = ObjectiveMarkerRole.ATTACKER_HOME
    elif requested_player == mission_setup.defender_player_id:
        home_role = ObjectiveMarkerRole.DEFENDER_HOME
    else:
        raise GameLifecycleError("Home objective player is not in MissionSetup.")
    return tuple(
        sorted(
            marker.objective_marker_id
            for marker in mission_setup.objective_markers
            if marker.objective_role is home_role
        )
    )


def _previous_player_turn_key(
    *,
    turn_order: tuple[str, ...],
    battle_round: int,
    active_player_id: str,
) -> tuple[int, str]:
    active_index = turn_order.index(active_player_id)
    if active_index > 0:
        return battle_round, turn_order[active_index - 1]
    previous_round = battle_round - 1
    if previous_round < 1:
        raise GameLifecycleError("Previous player turn does not exist before battle round one.")
    return previous_round, turn_order[-1]


def _validate_destruction_evidence(
    values: object,
) -> tuple[PrimaryUnitDestructionEvidence, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Primary destruction evidence must be a tuple.")
    rows: list[PrimaryUnitDestructionEvidence] = []
    seen_destruction_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PrimaryUnitDestructionEvidence:
            raise GameLifecycleError(
                "Primary destruction evidence must contain typed evidence rows."
            )
        if value.destruction_id in seen_destruction_ids:
            raise GameLifecycleError(
                "Primary destruction evidence must not duplicate destruction occurrences."
            )
        seen_destruction_ids.add(value.destruction_id)
        rows.append(value)
    return tuple(sorted(rows, key=lambda row: row.destruction_id))


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int = 0,
    preserve_order: bool = False,
) -> tuple[str, ...]:
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
    if len(identifiers) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    return tuple(identifiers if preserve_order else sorted(identifiers))


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_destruction_attribution(
    value: object | None,
) -> ModelDestructionAttribution | None:
    if value is None:
        return None
    if type(value) is not ModelDestructionAttribution:
        raise GameLifecycleError(
            "Primary destruction evidence attribution must be ModelDestructionAttribution."
        )
    return value


def _validate_source_objective_witness(
    value: object | None,
) -> RulesUnitObjectiveProximityWitness | None:
    if value is None:
        return None
    if type(value) is not RulesUnitObjectiveProximityWitness:
        raise GameLifecycleError(
            "Primary destruction evidence source objective witness must be typed."
        )
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"{field_name} must be a positive integer.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"{field_name} must be a non-negative integer.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)
