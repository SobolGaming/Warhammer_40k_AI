from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelPlacement,
    ModelRemovalRecord,
    UnitPlacement,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyResult,
    UnitCoherencyResultPayload,
    unit_placement_coherency_result,
)


class CoherencyCleanupRemovalPayload(TypedDict):
    player_id: str
    unit_instance_id: str
    model_instance_id: str
    removal_kind: str
    source_rule_id: str
    destroyed_model_rules_triggered: bool


class EndTurnCleanupStatePayload(TypedDict):
    cleanup_id: str
    game_id: str
    battle_round: int
    active_player_id: str
    phase: str
    removals: list[CoherencyCleanupRemovalPayload]
    coherency_results: list[UnitCoherencyResultPayload]
    transition_batch: BattlefieldTransitionBatchPayload


_COHERENCY_CLEANUP_RULE_ID = "core_rules_unit_coherency_cleanup"


@dataclass(frozen=True, slots=True)
class CoherencyCleanupRemoval:
    player_id: str
    unit_instance_id: str
    model_instance_id: str
    removal_kind: BattlefieldRemovalKind = BattlefieldRemovalKind.DESTROYED
    source_rule_id: str = _COHERENCY_CLEANUP_RULE_ID
    destroyed_model_rules_triggered: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("CoherencyCleanupRemoval player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "CoherencyCleanupRemoval unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "CoherencyCleanupRemoval model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "removal_kind",
            battlefield_removal_kind_from_token(self.removal_kind),
        )
        if self.removal_kind is not BattlefieldRemovalKind.DESTROYED:
            raise GameLifecycleError("Coherency cleanup removals must count as destroyed.")
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("CoherencyCleanupRemoval source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "destroyed_model_rules_triggered",
            _validate_bool(
                "CoherencyCleanupRemoval destroyed_model_rules_triggered",
                self.destroyed_model_rules_triggered,
            ),
        )
        if self.destroyed_model_rules_triggered:
            raise GameLifecycleError("Coherency cleanup must not trigger destroyed-model rules.")

    def to_payload(self) -> CoherencyCleanupRemovalPayload:
        return {
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "model_instance_id": self.model_instance_id,
            "removal_kind": self.removal_kind.value,
            "source_rule_id": self.source_rule_id,
            "destroyed_model_rules_triggered": self.destroyed_model_rules_triggered,
        }

    @classmethod
    def from_payload(cls, payload: CoherencyCleanupRemovalPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            model_instance_id=payload["model_instance_id"],
            removal_kind=battlefield_removal_kind_from_token(payload["removal_kind"]),
            source_rule_id=payload["source_rule_id"],
            destroyed_model_rules_triggered=payload["destroyed_model_rules_triggered"],
        )


@dataclass(frozen=True, slots=True)
class EndTurnCleanupState:
    cleanup_id: str
    game_id: str
    battle_round: int
    active_player_id: str
    phase: str
    removals: tuple[CoherencyCleanupRemoval, ...]
    coherency_results: tuple[UnitCoherencyResult, ...]
    transition_batch: BattlefieldTransitionBatch

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "cleanup_id",
            _validate_identifier("EndTurnCleanupState cleanup_id", self.cleanup_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("EndTurnCleanupState game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("EndTurnCleanupState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("EndTurnCleanupState active_player_id", self.active_player_id),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_identifier("EndTurnCleanupState phase", self.phase),
        )
        object.__setattr__(
            self,
            "removals",
            _validate_cleanup_removal_tuple("EndTurnCleanupState removals", self.removals),
        )
        object.__setattr__(
            self,
            "coherency_results",
            _validate_coherency_result_tuple(
                "EndTurnCleanupState coherency_results",
                self.coherency_results,
            ),
        )
        if type(self.transition_batch) is not BattlefieldTransitionBatch:
            raise GameLifecycleError(
                "EndTurnCleanupState transition_batch must be BattlefieldTransitionBatch."
            )

    @property
    def removed_model_instance_ids(self) -> tuple[str, ...]:
        return tuple(removal.model_instance_id for removal in self.removals)

    def to_payload(self) -> EndTurnCleanupStatePayload:
        return {
            "cleanup_id": self.cleanup_id,
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "phase": self.phase,
            "removals": [removal.to_payload() for removal in self.removals],
            "coherency_results": [result.to_payload() for result in self.coherency_results],
            "transition_batch": self.transition_batch.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: EndTurnCleanupStatePayload) -> Self:
        return cls(
            cleanup_id=payload["cleanup_id"],
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            phase=payload["phase"],
            removals=tuple(
                CoherencyCleanupRemoval.from_payload(removal) for removal in payload["removals"]
            ),
            coherency_results=tuple(
                UnitCoherencyResult.from_payload(result) for result in payload["coherency_results"]
            ),
            transition_batch=BattlefieldTransitionBatch.from_payload(payload["transition_batch"]),
        )


def resolve_end_turn_cleanup(
    *,
    game_id: str,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    battle_round: int,
    active_player_id: str,
    phase: BattlePhase,
) -> tuple[EndTurnCleanupState, BattlefieldRuntimeState]:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("End-turn cleanup requires a BattlefieldScenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("End-turn cleanup requires a RulesetDescriptor.")
    requested_game_id = _validate_identifier("game_id", game_id)
    requested_round = _validate_positive_int("battle_round", battle_round)
    requested_player_id = _validate_identifier("active_player_id", active_player_id)
    if type(phase) is not BattlePhase:
        raise GameLifecycleError("End-turn cleanup phase must be a BattlePhase.")

    battlefield_state = scenario.battlefield_state
    removals: list[CoherencyCleanupRemoval] = []
    coherency_results: list[UnitCoherencyResult] = []
    initial_unit_ids = tuple(
        unit_placement.unit_instance_id
        for placed_army in battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
    )
    for unit_instance_id in initial_unit_ids:
        while _unit_is_placed(battlefield_state, unit_instance_id):
            current_scenario = BattlefieldScenario(
                armies=scenario.armies,
                battlefield_state=battlefield_state,
            )
            unit_placement = battlefield_state.unit_placement_by_id(unit_instance_id)
            result = unit_placement_coherency_result(
                scenario=current_scenario,
                ruleset_descriptor=ruleset_descriptor,
                unit_placement=unit_placement,
            )
            if result.is_coherent:
                break
            coherency_results.append(result)
            model_id = _next_cleanup_model_id(result)
            model_placement = _model_placement_for_unit(unit_placement, model_id)
            removals.append(
                CoherencyCleanupRemoval(
                    player_id=model_placement.player_id,
                    unit_instance_id=unit_placement.unit_instance_id,
                    model_instance_id=model_id,
                )
            )
            battlefield_state = battlefield_state.with_removed_models((model_id,))

    transition_batch = BattlefieldTransitionBatch(
        removals=tuple(
            ModelRemovalRecord(
                model_instance_id=removal.model_instance_id,
                removal_kind=BattlefieldRemovalKind.DESTROYED,
                source_phase=phase.value,
                source_step="end_turn_cleanup",
                source_rule_id=removal.source_rule_id,
                source_event_id=None,
                destination_id=None,
            )
            for removal in removals
        )
    )
    cleanup = EndTurnCleanupState(
        cleanup_id=(
            f"end-turn-cleanup:{requested_game_id}:round-{requested_round:02d}:"
            f"{requested_player_id}"
        ),
        game_id=requested_game_id,
        battle_round=requested_round,
        active_player_id=requested_player_id,
        phase=phase.value,
        removals=tuple(removals),
        coherency_results=tuple(coherency_results),
        transition_batch=transition_batch,
    )
    return cleanup, battlefield_state


def _next_cleanup_model_id(result: UnitCoherencyResult) -> str:
    if type(result) is not UnitCoherencyResult:
        raise GameLifecycleError("Cleanup model selection requires UnitCoherencyResult.")
    offending_ids = result.offending_model_instance_ids
    if not offending_ids:
        raise GameLifecycleError("Broken coherency result must identify offending models.")
    return offending_ids[0]


def _model_placement_for_unit(
    unit_placement: UnitPlacement,
    model_instance_id: str,
) -> ModelPlacement:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for model_placement in unit_placement.model_placements:
        if model_placement.model_instance_id == requested_model_id:
            return model_placement
    raise GameLifecycleError("Cleanup model must be present in unit placement.")


def _unit_is_placed(battlefield_state: BattlefieldRuntimeState, unit_instance_id: str) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return any(
        unit_placement.unit_instance_id == requested_unit_id
        for placed_army in battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
    )


def battlefield_removal_kind_from_token(token: object) -> BattlefieldRemovalKind:
    if type(token) is BattlefieldRemovalKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("BattlefieldRemovalKind token must be a string.")
    try:
        return BattlefieldRemovalKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported BattlefieldRemovalKind token: {token}.") from exc


def _validate_cleanup_removal_tuple(
    field_name: str,
    values: object,
) -> tuple[CoherencyCleanupRemoval, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    removals: list[CoherencyCleanupRemoval] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not CoherencyCleanupRemoval:
            raise GameLifecycleError(f"{field_name} must contain cleanup removals.")
        if value.model_instance_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate models.")
        seen.add(value.model_instance_id)
        removals.append(value)
    return tuple(removals)


def _validate_coherency_result_tuple(
    field_name: str,
    values: object,
) -> tuple[UnitCoherencyResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    results: list[UnitCoherencyResult] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not UnitCoherencyResult:
            raise GameLifecycleError(f"{field_name} must contain coherency results.")
        results.append(value)
    return tuple(results)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value
