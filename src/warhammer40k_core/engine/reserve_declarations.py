from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.list_validation import (
    ListValidationError,
    battle_size_mustering_policy,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    SetupStep,
)
from warhammer40k_core.engine.reserves import (
    AircraftReserveDeclaration,
    DeepStrikeSetupDeclaration,
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReserveState,
    ReserveStatus,
    ReserveUnitPointValue,
    StrategicReserveDeclaration,
    reserve_kind_from_token,
    reserve_origin_from_token,
)
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.unit_abilities import unit_has_deep_strike
from warhammer40k_core.engine.unit_factory import UnitInstance

SELECT_RESERVE_DECLARATION_DECISION_TYPE = "select_reserve_declaration"
COMPLETE_RESERVE_DECLARATIONS_OPTION_ID = "complete_reserve_declarations"
STRATEGIC_RESERVES_SOURCE_RULE_ID = "strategic_reserves"
DEEP_STRIKE_SOURCE_RULE_ID = "deep_strike"
AIRCRAFT_MANDATORY_RESERVE_SOURCE_RULE_ID = "aircraft_mandatory_reserve"


class ReserveDeclarationAction(StrEnum):
    DECLARE_RESERVE = "declare_reserve"
    COMPLETE_RESERVE_DECLARATIONS = "complete_reserve_declarations"


class BattleFormationDeclarationStatePayload(TypedDict):
    setup_step: str
    next_player_id: str | None
    available_declaration_count_by_player: dict[str, int]
    completed_player_ids: list[str]


class ReserveDeclarationRequestPayload(TypedDict):
    request_id: str
    decision_type: str
    actor_id: str
    game_id: str
    setup_step: str
    player_id: str
    ruleset_descriptor_hash: str
    strategic_reserves_points_limit: int
    current_strategic_reserves_points: int
    available_declaration_count: int


class ReserveDeclarationSelectionPayload(TypedDict):
    submission_kind: str
    action_kind: str
    game_id: str
    player_id: str
    setup_step: str
    ruleset_descriptor_hash: str
    reserve_origin: str | None
    reserve_kind: str | None
    source_rule_id: str | None
    unit_instance_id: str | None
    unit_points: int
    embarked_unit_points: int
    strategic_reserves_points_limit: int
    current_strategic_reserves_points: int
    points_after_declaration: int
    points_contribution: int
    embarked_unit_instance_ids: list[str]
    source_ids: list[str]


class ReserveLegalityContextPayload(TypedDict):
    player_id: str
    battle_size_points_limit: int
    strategic_reserves_points_limit: int
    current_strategic_reserves_points: int
    unit_points: list[dict[str, JsonValue]]


class ReserveLegalityReportPayload(TypedDict):
    is_legal: bool
    violation_codes: list[str]
    message: str | None


@dataclass(frozen=True, slots=True)
class BattleFormationDeclarationState:
    setup_step: SetupStep
    next_player_id: str | None
    available_declaration_count_by_player: dict[str, int]
    completed_player_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
            raise GameLifecycleError(
                "BattleFormationDeclarationState requires DECLARE_BATTLE_FORMATIONS."
            )
        object.__setattr__(
            self,
            "next_player_id",
            _validate_optional_identifier(
                "BattleFormationDeclarationState next_player_id",
                self.next_player_id,
            ),
        )
        counts: dict[str, int] = {}
        for player_id, count in self.available_declaration_count_by_player.items():
            counts[_validate_identifier("BattleFormationDeclarationState player_id", player_id)] = (
                _validate_non_negative_int("available_declaration_count", count)
            )
        object.__setattr__(self, "available_declaration_count_by_player", counts)
        object.__setattr__(
            self,
            "completed_player_ids",
            _validate_identifier_tuple(
                "BattleFormationDeclarationState completed_player_ids",
                self.completed_player_ids,
            ),
        )

    def to_payload(self) -> BattleFormationDeclarationStatePayload:
        return {
            "setup_step": self.setup_step.value,
            "next_player_id": self.next_player_id,
            "available_declaration_count_by_player": dict(
                self.available_declaration_count_by_player
            ),
            "completed_player_ids": list(self.completed_player_ids),
        }


@dataclass(frozen=True, slots=True)
class ReserveLegalityContext:
    player_id: str
    battle_size_points_limit: int
    strategic_reserves_points_limit: int
    current_strategic_reserves_points: int
    unit_points: tuple[ReserveUnitPointValue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ReserveLegalityContext player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_size_points_limit",
            _validate_positive_int(
                "ReserveLegalityContext battle_size_points_limit",
                self.battle_size_points_limit,
            ),
        )
        object.__setattr__(
            self,
            "strategic_reserves_points_limit",
            _validate_non_negative_int(
                "ReserveLegalityContext strategic_reserves_points_limit",
                self.strategic_reserves_points_limit,
            ),
        )
        object.__setattr__(
            self,
            "current_strategic_reserves_points",
            _validate_non_negative_int(
                "ReserveLegalityContext current_strategic_reserves_points",
                self.current_strategic_reserves_points,
            ),
        )
        points = _validate_reserve_unit_point_tuple(
            "ReserveLegalityContext unit_points",
            self.unit_points,
        )
        object.__setattr__(self, "unit_points", points)
        if self.strategic_reserves_points_limit > self.battle_size_points_limit:
            raise GameLifecycleError(
                "ReserveLegalityContext strategic limit cannot exceed battle size limit."
            )
        if self.current_strategic_reserves_points > self.strategic_reserves_points_limit:
            raise GameLifecycleError("ReserveLegalityContext current points exceed limit.")

    def points_for_unit(self, unit_instance_id: str) -> ReserveUnitPointValue | None:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for entry in self.unit_points:
            if entry.unit_instance_id == requested_unit_id:
                return entry
        return None

    def to_payload(self) -> ReserveLegalityContextPayload:
        return {
            "player_id": self.player_id,
            "battle_size_points_limit": self.battle_size_points_limit,
            "strategic_reserves_points_limit": self.strategic_reserves_points_limit,
            "current_strategic_reserves_points": self.current_strategic_reserves_points,
            "unit_points": [
                cast(dict[str, JsonValue], entry.to_payload()) for entry in self.unit_points
            ],
        }


@dataclass(frozen=True, slots=True)
class ReserveLegalityReport:
    is_legal: bool
    violation_codes: tuple[str, ...] = ()
    message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "is_legal", _validate_bool("is_legal", self.is_legal))
        object.__setattr__(
            self,
            "violation_codes",
            _validate_identifier_tuple(
                "ReserveLegalityReport violation_codes",
                self.violation_codes,
            ),
        )
        object.__setattr__(
            self,
            "message",
            _validate_optional_string("ReserveLegalityReport message", self.message),
        )
        if self.is_legal and self.violation_codes:
            raise GameLifecycleError("ReserveLegalityReport legal result cannot have violations.")

    def to_payload(self) -> ReserveLegalityReportPayload:
        return {
            "is_legal": self.is_legal,
            "violation_codes": list(self.violation_codes),
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ReserveDeclarationRequest:
    request_id: str
    actor_id: str
    game_id: str
    player_id: str
    ruleset_descriptor_hash: str
    strategic_reserves_points_limit: int
    current_strategic_reserves_points: int
    available_declaration_count: int
    setup_step: SetupStep = SetupStep.DECLARE_BATTLE_FORMATIONS

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("ReserveDeclarationRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "actor_id",
            _validate_identifier("ReserveDeclarationRequest actor_id", self.actor_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("ReserveDeclarationRequest game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ReserveDeclarationRequest player_id", self.player_id),
        )
        if self.actor_id != self.player_id:
            raise GameLifecycleError("ReserveDeclarationRequest actor_id must match player_id.")
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "ReserveDeclarationRequest ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "strategic_reserves_points_limit",
            _validate_non_negative_int(
                "ReserveDeclarationRequest strategic_reserves_points_limit",
                self.strategic_reserves_points_limit,
            ),
        )
        object.__setattr__(
            self,
            "current_strategic_reserves_points",
            _validate_non_negative_int(
                "ReserveDeclarationRequest current_strategic_reserves_points",
                self.current_strategic_reserves_points,
            ),
        )
        object.__setattr__(
            self,
            "available_declaration_count",
            _validate_non_negative_int(
                "ReserveDeclarationRequest available_declaration_count",
                self.available_declaration_count,
            ),
        )
        if self.setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
            raise GameLifecycleError(
                "ReserveDeclarationRequest requires DECLARE_BATTLE_FORMATIONS."
            )

    def to_decision_request(self, options: tuple[DecisionOption, ...]) -> DecisionRequest:
        return DecisionRequest(
            request_id=self.request_id,
            decision_type=SELECT_RESERVE_DECLARATION_DECISION_TYPE,
            actor_id=self.actor_id,
            payload={"reserve_declaration_request": validate_json_value(self.to_payload())},
            options=options,
        )

    def to_payload(self) -> ReserveDeclarationRequestPayload:
        return {
            "request_id": self.request_id,
            "decision_type": SELECT_RESERVE_DECLARATION_DECISION_TYPE,
            "actor_id": self.actor_id,
            "game_id": self.game_id,
            "setup_step": self.setup_step.value,
            "player_id": self.player_id,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "strategic_reserves_points_limit": self.strategic_reserves_points_limit,
            "current_strategic_reserves_points": self.current_strategic_reserves_points,
            "available_declaration_count": self.available_declaration_count,
        }

    @classmethod
    def from_decision_request_payload(cls, payload: object) -> Self:
        json_payload = validate_json_value(payload)
        if not isinstance(json_payload, dict):
            raise GameLifecycleError(
                "Reserve declaration DecisionRequest payload must be an object."
            )
        request_payload = json_payload.get("reserve_declaration_request")
        if not isinstance(request_payload, dict):
            raise GameLifecycleError("Reserve declaration DecisionRequest payload missing request.")
        typed_payload = cast(ReserveDeclarationRequestPayload, request_payload)
        return cls(
            request_id=typed_payload["request_id"],
            actor_id=typed_payload["actor_id"],
            game_id=typed_payload["game_id"],
            player_id=typed_payload["player_id"],
            ruleset_descriptor_hash=typed_payload["ruleset_descriptor_hash"],
            strategic_reserves_points_limit=typed_payload["strategic_reserves_points_limit"],
            current_strategic_reserves_points=typed_payload["current_strategic_reserves_points"],
            available_declaration_count=typed_payload["available_declaration_count"],
            setup_step=_setup_step_from_token(typed_payload["setup_step"]),
        )


@dataclass(frozen=True, slots=True)
class ReserveDeclarationSelection:
    submission_kind: str
    action_kind: ReserveDeclarationAction
    game_id: str
    player_id: str
    setup_step: SetupStep
    ruleset_descriptor_hash: str
    reserve_origin: ReserveOrigin | None
    reserve_kind: ReserveKind | None
    source_rule_id: str | None
    unit_instance_id: str | None
    unit_points: int
    embarked_unit_points: int
    strategic_reserves_points_limit: int
    current_strategic_reserves_points: int
    points_after_declaration: int
    points_contribution: int
    embarked_unit_instance_ids: tuple[str, ...]
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "submission_kind",
            _validate_identifier(
                "ReserveDeclarationSelection submission_kind",
                self.submission_kind,
            ),
        )
        if self.submission_kind != SELECT_RESERVE_DECLARATION_DECISION_TYPE:
            raise GameLifecycleError("Reserve declaration selection submission kind drift.")
        object.__setattr__(
            self,
            "action_kind",
            reserve_declaration_action_from_token(self.action_kind),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("ReserveDeclarationSelection game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ReserveDeclarationSelection player_id", self.player_id),
        )
        if self.setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
            raise GameLifecycleError(
                "ReserveDeclarationSelection requires DECLARE_BATTLE_FORMATIONS."
            )
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "ReserveDeclarationSelection ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        origin = (
            None if self.reserve_origin is None else reserve_origin_from_token(self.reserve_origin)
        )
        kind = None if self.reserve_kind is None else reserve_kind_from_token(self.reserve_kind)
        source_rule_id = (
            None
            if self.source_rule_id is None
            else _validate_identifier(
                "ReserveDeclarationSelection source_rule_id",
                self.source_rule_id,
            )
        )
        unit_instance_id = (
            None
            if self.unit_instance_id is None
            else _validate_identifier(
                "ReserveDeclarationSelection unit_instance_id",
                self.unit_instance_id,
            )
        )
        object.__setattr__(self, "reserve_origin", origin)
        object.__setattr__(self, "reserve_kind", kind)
        object.__setattr__(self, "source_rule_id", source_rule_id)
        object.__setattr__(self, "unit_instance_id", unit_instance_id)
        object.__setattr__(
            self,
            "unit_points",
            _validate_non_negative_int("ReserveDeclarationSelection unit_points", self.unit_points),
        )
        object.__setattr__(
            self,
            "embarked_unit_points",
            _validate_non_negative_int(
                "ReserveDeclarationSelection embarked_unit_points",
                self.embarked_unit_points,
            ),
        )
        object.__setattr__(
            self,
            "strategic_reserves_points_limit",
            _validate_non_negative_int(
                "ReserveDeclarationSelection strategic_reserves_points_limit",
                self.strategic_reserves_points_limit,
            ),
        )
        object.__setattr__(
            self,
            "current_strategic_reserves_points",
            _validate_non_negative_int(
                "ReserveDeclarationSelection current_strategic_reserves_points",
                self.current_strategic_reserves_points,
            ),
        )
        object.__setattr__(
            self,
            "points_after_declaration",
            _validate_non_negative_int(
                "ReserveDeclarationSelection points_after_declaration",
                self.points_after_declaration,
            ),
        )
        object.__setattr__(
            self,
            "points_contribution",
            _validate_non_negative_int(
                "ReserveDeclarationSelection points_contribution",
                self.points_contribution,
            ),
        )
        object.__setattr__(
            self,
            "embarked_unit_instance_ids",
            _validate_identifier_tuple(
                "ReserveDeclarationSelection embarked_unit_instance_ids",
                self.embarked_unit_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("ReserveDeclarationSelection source_ids", self.source_ids),
        )
        if self.action_kind is ReserveDeclarationAction.COMPLETE_RESERVE_DECLARATIONS:
            if kind is not None or origin is not None or source_rule_id is not None:
                raise GameLifecycleError(
                    "Reserve completion selection must not set reserve fields."
                )
            if unit_instance_id is not None:
                raise GameLifecycleError("Reserve completion selection must not set unit.")
            return
        if kind is None or origin is None or source_rule_id is None or unit_instance_id is None:
            raise GameLifecycleError("Reserve declaration selection requires reserve context.")

    @classmethod
    def from_payload(cls, payload: ReserveDeclarationSelectionPayload) -> Self:
        return cls(
            submission_kind=payload["submission_kind"],
            action_kind=reserve_declaration_action_from_token(payload["action_kind"]),
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            setup_step=_setup_step_from_token(payload["setup_step"]),
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            reserve_origin=(
                None
                if payload["reserve_origin"] is None
                else reserve_origin_from_token(payload["reserve_origin"])
            ),
            reserve_kind=(
                None
                if payload["reserve_kind"] is None
                else reserve_kind_from_token(payload["reserve_kind"])
            ),
            source_rule_id=payload["source_rule_id"],
            unit_instance_id=payload["unit_instance_id"],
            unit_points=payload["unit_points"],
            embarked_unit_points=payload["embarked_unit_points"],
            strategic_reserves_points_limit=payload["strategic_reserves_points_limit"],
            current_strategic_reserves_points=payload["current_strategic_reserves_points"],
            points_after_declaration=payload["points_after_declaration"],
            points_contribution=payload["points_contribution"],
            embarked_unit_instance_ids=tuple(payload["embarked_unit_instance_ids"]),
            source_ids=tuple(payload["source_ids"]),
        )

    def to_payload(self) -> ReserveDeclarationSelectionPayload:
        return {
            "submission_kind": self.submission_kind,
            "action_kind": self.action_kind.value,
            "game_id": self.game_id,
            "player_id": self.player_id,
            "setup_step": self.setup_step.value,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "reserve_origin": None if self.reserve_origin is None else self.reserve_origin.value,
            "reserve_kind": None if self.reserve_kind is None else self.reserve_kind.value,
            "source_rule_id": self.source_rule_id,
            "unit_instance_id": self.unit_instance_id,
            "unit_points": self.unit_points,
            "embarked_unit_points": self.embarked_unit_points,
            "strategic_reserves_points_limit": self.strategic_reserves_points_limit,
            "current_strategic_reserves_points": self.current_strategic_reserves_points,
            "points_after_declaration": self.points_after_declaration,
            "points_contribution": self.points_contribution,
            "embarked_unit_instance_ids": list(self.embarked_unit_instance_ids),
            "source_ids": list(self.source_ids),
        }


def apply_mandatory_aircraft_reserve_declarations(
    *,
    state: GameState,
    config: GameConfig,
    decisions: DecisionController,
) -> tuple[ReserveState, ...]:
    if state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        raise GameLifecycleError("Aircraft reserve declarations require DECLARE_BATTLE_FORMATIONS.")
    policy = ReserveDestructionTimingPolicy.from_mission_policy(
        config.ruleset_descriptor.mission_policy
    )
    recorded: list[ReserveState] = []
    for army in state.army_definitions:
        context = reserve_legality_context_for_player(
            state=state,
            config=config,
            player_id=army.player_id,
        )
        current_points = context.current_strategic_reserves_points
        for unit in sorted(army.units, key=lambda item: item.unit_instance_id):
            if not _unit_has_keyword(unit, "AIRCRAFT"):
                continue
            if state.reserve_state_for_unit(unit.unit_instance_id) is not None:
                continue
            point_value = context.points_for_unit(unit.unit_instance_id)
            if point_value is None:
                raise GameLifecycleError(
                    "Aircraft reserve declaration requires source-backed unit points."
                )
            if current_points + point_value.points > context.strategic_reserves_points_limit:
                raise GameLifecycleError(
                    "Aircraft reserve declarations exceed the player's points limit."
                )
            declaration = AircraftReserveDeclaration.for_unit(
                unit=unit,
                player_id=army.player_id,
                unit_points=point_value.points,
                points_limit=context.strategic_reserves_points_limit,
            )
            reserve_state = declaration.to_reserve_state(destruction_deadline_policy=policy)
            state.record_reserve_state(reserve_state)
            current_points += point_value.points
            recorded.append(reserve_state)
            decisions.event_log.append(
                "aircraft_reserve_declared",
                {
                    "game_id": state.game_id,
                    "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                    "player_id": army.player_id,
                    "unit_instance_id": unit.unit_instance_id,
                    "declaration": declaration.to_payload(),
                    "reserve_state": reserve_state.to_payload(),
                    "source_id": AIRCRAFT_MANDATORY_RESERVE_SOURCE_RULE_ID,
                },
            )
    return tuple(sorted(recorded, key=lambda item: item.unit_instance_id))


def reserve_declaration_state_for_state(
    *,
    state: GameState,
    config: GameConfig,
    decisions: DecisionController,
    require_current_step: bool = True,
) -> BattleFormationDeclarationState:
    _validate_declaration_state(state, require_current_step=require_current_step)
    completed = _completed_player_ids(decisions)
    counts = {
        player_id: len(
            reserve_declaration_options_for_player(
                state=state,
                config=config,
                player_id=player_id,
                include_completion=False,
                require_current_step=require_current_step,
            )
        )
        for player_id in state.player_ids
    }
    next_player_id = None
    for player_id in state.player_ids:
        if player_id in completed:
            continue
        if counts[player_id] > 0:
            next_player_id = player_id
            break
    return BattleFormationDeclarationState(
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        next_player_id=next_player_id,
        available_declaration_count_by_player=counts,
        completed_player_ids=tuple(sorted(completed)),
    )


def reserve_declaration_request_for_next_player(
    *,
    state: GameState,
    config: GameConfig,
    decisions: DecisionController,
) -> DecisionRequest | None:
    setup_state = reserve_declaration_state_for_state(
        state=state,
        config=config,
        decisions=decisions,
    )
    if setup_state.next_player_id is None:
        return None
    return reserve_declaration_request_for_player(
        state=state,
        config=config,
        player_id=setup_state.next_player_id,
    )


def reserve_declaration_request_for_player(
    *,
    state: GameState,
    config: GameConfig,
    player_id: str,
) -> DecisionRequest:
    requested_player_id = _validate_player_id(player_id, state=state)
    context = reserve_legality_context_for_player(
        state=state,
        config=config,
        player_id=requested_player_id,
    )
    declaration_options = reserve_declaration_options_for_player(
        state=state,
        config=config,
        player_id=requested_player_id,
        include_completion=False,
    )
    request_context = ReserveDeclarationRequest(
        request_id=state.next_decision_request_id(),
        actor_id=requested_player_id,
        game_id=state.game_id,
        player_id=requested_player_id,
        ruleset_descriptor_hash=config.ruleset_descriptor.descriptor_hash,
        strategic_reserves_points_limit=context.strategic_reserves_points_limit,
        current_strategic_reserves_points=context.current_strategic_reserves_points,
        available_declaration_count=len(declaration_options),
    )
    options = (*declaration_options, _completion_option(state=state, context=context))
    return request_context.to_decision_request(options=options)


def reserve_declaration_options_for_player(
    *,
    state: GameState,
    config: GameConfig,
    player_id: str,
    include_completion: bool,
    require_current_step: bool = True,
) -> tuple[DecisionOption, ...]:
    _validate_declaration_state(state, require_current_step=require_current_step)
    requested_player_id = _validate_player_id(player_id, state=state)
    context = reserve_legality_context_for_player(
        state=state,
        config=config,
        player_id=requested_player_id,
    )
    options: list[DecisionOption] = []
    for unit in _declarable_units_for_player(state=state, player_id=requested_player_id):
        strategic = _strategic_reserves_option_for_unit(
            state=state,
            config=config,
            context=context,
            unit=unit,
        )
        if strategic is not None:
            options.append(strategic)
        deep_strike = _deep_strike_option_for_unit(
            state=state,
            config=config,
            context=context,
            unit=unit,
        )
        if deep_strike is not None:
            options.append(deep_strike)
    if include_completion:
        options.append(_completion_option(state=state, context=context))
    return tuple(sorted(options, key=lambda option: option.option_id))


def invalid_reserve_declaration_status(
    *,
    state: GameState,
    config: GameConfig,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if request.decision_type != SELECT_RESERVE_DECLARATION_DECISION_TYPE:
        return None
    try:
        result.validate_for_request(request)
    except DecisionError as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Reserve declaration result does not match the pending request.",
            payload={
                "invalid_reason": "invalid_reserve_declaration_result",
                "detail": str(exc),
                "request_id": request.request_id,
            },
        )
    try:
        request_context = ReserveDeclarationRequest.from_decision_request_payload(request.payload)
        selection = ReserveDeclarationSelection.from_payload(
            cast(ReserveDeclarationSelectionPayload, result.payload)
        )
    except (KeyError, TypeError, GameLifecycleError) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Reserve declaration submission is malformed.",
            payload={
                "invalid_reason": "malformed_reserve_declaration",
                "detail": str(exc),
                "request_id": request.request_id,
            },
        )
    drift_field = _reserve_request_drift_field(
        state=state,
        config=config,
        request=request_context,
    )
    if drift_field is not None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Reserve declaration request no longer matches setup state.",
            payload={
                "invalid_reason": "reserve_declaration_request_drift",
                "field": drift_field,
                "request_id": request.request_id,
            },
        )
    legal_options = reserve_declaration_options_for_player(
        state=state,
        config=config,
        player_id=request_context.player_id,
        include_completion=True,
    )
    legal_payload_by_id = {option.option_id: option.payload for option in legal_options}
    if result.selected_option_id not in legal_payload_by_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Reserve declaration option is no longer legal.",
            payload={
                "invalid_reason": "reserve_declaration_request_drift",
                "field": "selected_option_id",
                "request_id": request.request_id,
            },
        )
    if selection.to_payload() != legal_payload_by_id[result.selected_option_id]:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Reserve declaration payload no longer matches setup state.",
            payload={
                "invalid_reason": "reserve_declaration_request_drift",
                "field": "payload",
                "request_id": request.request_id,
            },
        )
    return None


def apply_reserve_declaration_decision(
    *,
    state: GameState,
    config: GameConfig,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    if state.stage is not GameLifecycleStage.SETUP:
        raise GameLifecycleError("Reserve declarations can be applied only in setup.")
    if state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        raise GameLifecycleError("Reserve declarations require DECLARE_BATTLE_FORMATIONS.")
    if request.decision_type != SELECT_RESERVE_DECLARATION_DECISION_TYPE:
        raise GameLifecycleError("Reserve declaration apply requires reserve request.")
    selection = ReserveDeclarationSelection.from_payload(
        cast(ReserveDeclarationSelectionPayload, result.payload)
    )
    record = decisions.record_for_result(result)
    if selection.action_kind is ReserveDeclarationAction.COMPLETE_RESERVE_DECLARATIONS:
        decisions.event_log.append(
            "reserve_declarations_completed",
            {
                "game_id": state.game_id,
                "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
                "player_id": selection.player_id,
                "source_decision_record_id": record.record_id,
                "source_decision_request_id": request.request_id,
                "source_decision_result_id": result.result_id,
            },
        )
        return
    unit_id = _require_selection_unit(selection)
    rules_unit = _unit_for_player(
        state=state,
        player_id=selection.player_id,
        unit_instance_id=unit_id,
    )
    policy = ReserveDestructionTimingPolicy.from_mission_policy(
        config.ruleset_descriptor.mission_policy
    )
    if selection.reserve_kind is ReserveKind.STRATEGIC_RESERVES:
        declaration = StrategicReserveDeclaration(
            player_id=selection.player_id,
            unit_instance_id=rules_unit.unit_instance_id,
            reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
            declared_during_step=SetupStep.DECLARE_BATTLE_FORMATIONS.value,
            unit_points=selection.unit_points,
            embarked_unit_points=selection.embarked_unit_points,
            points_limit=selection.strategic_reserves_points_limit,
            source_rule_id=_require_source_rule_id(selection),
            has_fortification_keyword=any(
                _unit_has_keyword(component.unit, "FORTIFICATION")
                for component in rules_unit.components
            ),
            embarked_unit_instance_ids=selection.embarked_unit_instance_ids,
        )
        reserve_states = state.apply_strategic_reserve_declarations(
            declarations=(declaration,),
            destruction_deadline_policy=policy,
        )
        reserve_state = reserve_states[0]
        declaration_payload = validate_json_value(declaration.to_payload())
    elif selection.reserve_kind is ReserveKind.DEEP_STRIKE:
        deep_strike_declaration = DeepStrikeSetupDeclaration(
            player_id=selection.player_id,
            unit_instance_id=rules_unit.unit_instance_id,
            reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
            declared_during_step=SetupStep.DECLARE_BATTLE_FORMATIONS.value,
            has_deep_strike_keyword=all(
                unit_has_deep_strike(component.unit) for component in rules_unit.components
            ),
            points_contribution=selection.points_contribution,
            source_rule_id=_require_source_rule_id(selection),
        )
        reserve_state = deep_strike_declaration.to_reserve_state(destruction_deadline_policy=policy)
        if state.reserve_state_for_unit(rules_unit.unit_instance_id) is not None:
            raise GameLifecycleError("Reserve declaration unit already has a ReserveState.")
        state.record_reserve_state(reserve_state)
        declaration_payload = validate_json_value(deep_strike_declaration.to_payload())
    else:
        raise GameLifecycleError("Unsupported reserve declaration kind.")
    decisions.event_log.append(
        "reserve_unit_declared",
        {
            "game_id": state.game_id,
            "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
            "player_id": selection.player_id,
            "unit_instance_id": rules_unit.unit_instance_id,
            "component_unit_instance_ids": list(rules_unit.component_unit_instance_ids),
            "reserve_kind": reserve_state.reserve_kind.value,
            "reserve_origin": reserve_state.reserve_origin.value,
            "declaration": declaration_payload,
            "reserve_state": reserve_state.to_payload(),
            "source_decision_record_id": record.record_id,
            "source_decision_request_id": request.request_id,
            "source_decision_result_id": result.result_id,
        },
    )


def reserve_legality_context_for_player(
    *,
    state: GameState,
    config: GameConfig,
    player_id: str,
) -> ReserveLegalityContext:
    requested_player_id = _validate_player_id(player_id, state=state)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        raise GameLifecycleError("Reserve declaration requires a mustered army.")
    try:
        battle_size_policy = battle_size_mustering_policy(army.battle_size)
    except ListValidationError as exc:
        raise GameLifecycleError("Reserve declaration requires supported battle size.") from exc
    player_unit_points = tuple(
        entry
        for entry in config.reserve_unit_points
        if _unit_owner_by_id(state).get(entry.unit_instance_id) == requested_player_id
    )
    strategic_limit = battle_size_policy.points_limit // 2
    return ReserveLegalityContext(
        player_id=requested_player_id,
        battle_size_points_limit=battle_size_policy.points_limit,
        strategic_reserves_points_limit=strategic_limit,
        current_strategic_reserves_points=_current_strategic_reserves_points(
            state=state,
            player_id=requested_player_id,
        ),
        unit_points=player_unit_points,
    )


def reserve_declaration_action_from_token(token: object) -> ReserveDeclarationAction:
    if type(token) is ReserveDeclarationAction:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ReserveDeclarationAction token must be a string.")
    try:
        return ReserveDeclarationAction(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported ReserveDeclarationAction token: {token}.") from exc


def _strategic_reserves_option_for_unit(
    *,
    state: GameState,
    config: GameConfig,
    context: ReserveLegalityContext,
    unit: RulesUnitView,
) -> DecisionOption | None:
    if any(_unit_has_keyword(component.unit, "FORTIFICATION") for component in unit.components):
        return None
    component_points = _points_for_rules_unit(context=context, view=unit)
    if component_points is None:
        return None
    cargo_unit_ids = tuple(
        sorted(
            {
                cargo_unit_id
                for component_unit_id in unit.component_unit_instance_ids
                for cargo_unit_id in _cargo_unit_ids_for_transport(
                    state=state,
                    transport_unit_id=component_unit_id,
                )
            }
        )
    )
    embarked_points = _embarked_points_for_unit_ids(
        context=context,
        unit_instance_ids=cargo_unit_ids,
    )
    if embarked_points is None:
        return None
    contribution = sum(point_value.points for point_value in component_points) + embarked_points
    after = context.current_strategic_reserves_points + contribution
    if after > context.strategic_reserves_points_limit:
        return None
    payload = _selection_payload(
        state=state,
        config=config,
        context=context,
        action_kind=ReserveDeclarationAction.DECLARE_RESERVE,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
        source_rule_id=STRATEGIC_RESERVES_SOURCE_RULE_ID,
        unit=unit,
        unit_points=sum(point_value.points for point_value in component_points),
        embarked_unit_points=embarked_points,
        points_contribution=contribution,
        points_after_declaration=after,
        embarked_unit_instance_ids=cargo_unit_ids,
        source_ids=tuple(sorted({point_value.source_id for point_value in component_points})),
    )
    return DecisionOption(
        option_id=f"declare_strategic_reserves:{unit.unit_instance_id}",
        label=f"Declare Strategic Reserves {unit.unit_instance_id}",
        payload=validate_json_value(payload),
    )


def _deep_strike_option_for_unit(
    *,
    state: GameState,
    config: GameConfig,
    context: ReserveLegalityContext,
    unit: RulesUnitView,
) -> DecisionOption | None:
    if not all(unit_has_deep_strike(component.unit) for component in unit.components):
        return None
    component_points = _points_for_rules_unit(context=context, view=unit)
    source_ids = tuple(
        sorted(
            {
                source_id
                for component in unit.components
                for source_id in component.unit.datasheet_source_ids
            }
        )
    )
    if component_points is not None:
        source_ids = tuple(
            sorted(
                {
                    *source_ids,
                    *(point_value.source_id for point_value in component_points),
                }
            )
        )
    payload = _selection_payload(
        state=state,
        config=config,
        context=context,
        action_kind=ReserveDeclarationAction.DECLARE_RESERVE,
        reserve_kind=ReserveKind.DEEP_STRIKE,
        reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
        source_rule_id=DEEP_STRIKE_SOURCE_RULE_ID,
        unit=unit,
        unit_points=0,
        embarked_unit_points=0,
        points_contribution=0,
        points_after_declaration=context.current_strategic_reserves_points,
        embarked_unit_instance_ids=(),
        source_ids=source_ids,
    )
    return DecisionOption(
        option_id=f"declare_deep_strike:{unit.unit_instance_id}",
        label=f"Declare Deep Strike {unit.unit_instance_id}",
        payload=validate_json_value(payload),
    )


def _completion_option(*, state: GameState, context: ReserveLegalityContext) -> DecisionOption:
    payload: ReserveDeclarationSelectionPayload = {
        "submission_kind": SELECT_RESERVE_DECLARATION_DECISION_TYPE,
        "action_kind": ReserveDeclarationAction.COMPLETE_RESERVE_DECLARATIONS.value,
        "game_id": state.game_id,
        "player_id": context.player_id,
        "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
        "ruleset_descriptor_hash": state.ruleset_descriptor_hash,
        "reserve_origin": None,
        "reserve_kind": None,
        "source_rule_id": None,
        "unit_instance_id": None,
        "unit_points": 0,
        "embarked_unit_points": 0,
        "strategic_reserves_points_limit": context.strategic_reserves_points_limit,
        "current_strategic_reserves_points": context.current_strategic_reserves_points,
        "points_after_declaration": context.current_strategic_reserves_points,
        "points_contribution": 0,
        "embarked_unit_instance_ids": [],
        "source_ids": [],
    }
    return DecisionOption(
        option_id=COMPLETE_RESERVE_DECLARATIONS_OPTION_ID,
        label="Complete Reserve Declarations",
        payload=validate_json_value(payload),
    )


def _selection_payload(
    *,
    state: GameState,
    config: GameConfig,
    context: ReserveLegalityContext,
    action_kind: ReserveDeclarationAction,
    reserve_kind: ReserveKind,
    reserve_origin: ReserveOrigin,
    source_rule_id: str,
    unit: RulesUnitView,
    unit_points: int,
    embarked_unit_points: int,
    points_contribution: int,
    points_after_declaration: int,
    embarked_unit_instance_ids: tuple[str, ...],
    source_ids: tuple[str, ...],
) -> ReserveDeclarationSelectionPayload:
    payload: ReserveDeclarationSelectionPayload = {
        "submission_kind": SELECT_RESERVE_DECLARATION_DECISION_TYPE,
        "action_kind": action_kind.value,
        "game_id": state.game_id,
        "player_id": context.player_id,
        "setup_step": SetupStep.DECLARE_BATTLE_FORMATIONS.value,
        "ruleset_descriptor_hash": config.ruleset_descriptor.descriptor_hash,
        "reserve_origin": reserve_origin.value,
        "reserve_kind": reserve_kind.value,
        "source_rule_id": source_rule_id,
        "unit_instance_id": unit.unit_instance_id,
        "unit_points": unit_points,
        "embarked_unit_points": embarked_unit_points,
        "strategic_reserves_points_limit": context.strategic_reserves_points_limit,
        "current_strategic_reserves_points": context.current_strategic_reserves_points,
        "points_after_declaration": points_after_declaration,
        "points_contribution": points_contribution,
        "embarked_unit_instance_ids": list(embarked_unit_instance_ids),
        "source_ids": list(source_ids),
    }
    return payload


def _reserve_request_drift_field(
    *,
    state: GameState,
    config: GameConfig,
    request: ReserveDeclarationRequest,
) -> str | None:
    if state.stage is not GameLifecycleStage.SETUP:
        return "stage"
    if state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        return "setup_step"
    if request.game_id != state.game_id:
        return "game_id"
    if request.ruleset_descriptor_hash != config.ruleset_descriptor.descriptor_hash:
        return "ruleset_descriptor_hash"
    if request.player_id not in state.player_ids:
        return "player_id"
    context = reserve_legality_context_for_player(
        state=state,
        config=config,
        player_id=request.player_id,
    )
    if request.strategic_reserves_points_limit != context.strategic_reserves_points_limit:
        return "strategic_reserves_points_limit"
    if request.current_strategic_reserves_points != context.current_strategic_reserves_points:
        return "current_strategic_reserves_points"
    return None


def _completed_player_ids(decisions: DecisionController) -> set[str]:
    completed: set[str] = set()
    for record in decisions.records:
        if record.request.decision_type != SELECT_RESERVE_DECLARATION_DECISION_TYPE:
            continue
        selection = ReserveDeclarationSelection.from_payload(
            cast(ReserveDeclarationSelectionPayload, record.result.payload)
        )
        if selection.action_kind is ReserveDeclarationAction.COMPLETE_RESERVE_DECLARATIONS:
            completed.add(selection.player_id)
    return completed


def _declarable_units_for_player(
    *,
    state: GameState,
    player_id: str,
) -> tuple[RulesUnitView, ...]:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise GameLifecycleError("Reserve declarations require a mustered army.")
    placed_armies = () if state.battlefield_state is None else state.battlefield_state.placed_armies
    placed_unit_ids = {
        unit_placement.unit_instance_id
        for placed_army in placed_armies
        for unit_placement in placed_army.unit_placements
    }
    embarked_ids = {
        unit_id
        for cargo_state in state.transport_cargo_states
        for unit_id in cargo_state.embarked_unit_instance_ids
    }
    units: list[RulesUnitView] = []
    seen_rules_unit_ids: set[str] = set()
    for physical_unit in army.units:
        view = rules_unit_view_by_id(
            state=state,
            unit_instance_id=physical_unit.unit_instance_id,
        )
        if view.unit_instance_id in seen_rules_unit_ids:
            continue
        seen_rules_unit_ids.add(view.unit_instance_id)
        component_ids = set(view.component_unit_instance_ids)
        if component_ids & placed_unit_ids:
            continue
        if component_ids & embarked_ids:
            continue
        reserve_state = state.reserve_state_for_unit(view.unit_instance_id)
        if reserve_state is not None and reserve_state.status is ReserveStatus.IN_RESERVES:
            continue
        units.append(view)
    return tuple(sorted(units, key=lambda unit: unit.unit_instance_id))


def _current_strategic_reserves_points(*, state: GameState, player_id: str) -> int:
    return sum(
        reserve_state.points_contribution
        for reserve_state in state.reserve_states
        if reserve_state.player_id == player_id
        and reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
        and reserve_state.status is ReserveStatus.IN_RESERVES
    )


def _cargo_unit_ids_for_transport(
    *,
    state: GameState,
    transport_unit_id: str,
) -> tuple[str, ...]:
    cargo_state = state.transport_cargo_state_for_transport(transport_unit_id)
    if cargo_state is None:
        return ()
    return cargo_state.embarked_unit_instance_ids


def _embarked_points_for_unit_ids(
    *,
    context: ReserveLegalityContext,
    unit_instance_ids: tuple[str, ...],
) -> int | None:
    total = 0
    for unit_id in unit_instance_ids:
        point_value = context.points_for_unit(unit_id)
        if point_value is None:
            return None
        total += point_value.points
    return total


def _points_for_rules_unit(
    *,
    context: ReserveLegalityContext,
    view: RulesUnitView,
) -> tuple[ReserveUnitPointValue, ...] | None:
    point_values: list[ReserveUnitPointValue] = []
    for component_unit_id in view.component_unit_instance_ids:
        point_value = context.points_for_unit(component_unit_id)
        if point_value is None:
            return None
        point_values.append(point_value)
    return tuple(point_values)


def _unit_for_player(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> RulesUnitView:
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if view.owner_player_id != player_id:
        raise GameLifecycleError("Reserve declaration unit player_id drift.")
    return view


def _unit_owner_by_id(state: GameState) -> dict[str, str]:
    return {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("unit must be a UnitInstance.")
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {_canonical_keyword(stored) for stored in unit.keywords}


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace(" ", "_").replace("-", "_")


def _require_selection_unit(selection: ReserveDeclarationSelection) -> str:
    if selection.unit_instance_id is None:
        raise GameLifecycleError("Reserve declaration selection requires unit_instance_id.")
    return selection.unit_instance_id


def _require_source_rule_id(selection: ReserveDeclarationSelection) -> str:
    if selection.source_rule_id is None:
        raise GameLifecycleError("Reserve declaration selection requires source_rule_id.")
    return selection.source_rule_id


def _validate_declaration_state(state: GameState, *, require_current_step: bool = True) -> None:
    if type(require_current_step) is not bool:
        raise GameLifecycleError("Reserve declaration current-step requirement must be a bool.")
    if state.stage is not GameLifecycleStage.SETUP:
        raise GameLifecycleError("Reserve declarations require setup stage.")
    if require_current_step and state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        raise GameLifecycleError("Reserve declarations require DECLARE_BATTLE_FORMATIONS.")
    if state.missing_army_player_ids():
        raise GameLifecycleError("Reserve declarations require mustered armies.")


def _validate_player_id(value: object, *, state: GameState) -> str:
    player_id = _validate_identifier("player_id", value)
    if player_id not in state.player_ids:
        raise GameLifecycleError("player_id is not in this game.")
    return player_id


def _setup_step_from_token(token: object) -> SetupStep:
    if type(token) is SetupStep:
        return token
    if type(token) is not str:
        raise GameLifecycleError("SetupStep token must be a string.")
    try:
        return SetupStep(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported setup step token: {token}.") from exc


def _validate_reserve_unit_point_tuple(
    field_name: str,
    values: object,
) -> tuple[ReserveUnitPointValue, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[ReserveUnitPointValue] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not ReserveUnitPointValue:
            raise GameLifecycleError(f"{field_name} must contain ReserveUnitPointValue values.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate unit IDs.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda entry: entry.unit_instance_id))


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_optional_string(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value
