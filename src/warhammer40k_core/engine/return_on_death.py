from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, TypedDict, cast

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    ModelPlacement,
    ModelPlacementPayload,
    PlacementError,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE = "submit_return_on_death_placement"
RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE = "return_on_death_pending_created"
RETURN_ON_DEATH_ROLL_RESOLVED_EVENT_TYPE = "return_on_death_roll_resolved"
RETURN_ON_DEATH_FAILED_ROLL_EVENT_TYPE = "return_on_death_failed_roll"
RETURN_ON_DEATH_SET_BACK_UP_REQUESTED_EVENT_TYPE = "return_on_death_set_back_up_requested"
RETURN_ON_DEATH_SET_BACK_UP_COMPLETED_EVENT_TYPE = "return_on_death_set_back_up_completed"


class ReturnDestroyedTargetScope(StrEnum):
    DESTROYED_MODEL = "destroyed_model"
    DESTROYED_UNIT = "destroyed_unit"


class ReturnRestoreWoundsMode(StrEnum):
    FIXED_REMAINING = "fixed_remaining"
    FULL_HEALTH = "full_health"


class PendingReturnOnDeathPayload(TypedDict):
    pending_id: str
    source_rule_id: str
    source_ability_id: str
    source_clause_id: str
    source_effect_index: int
    owner_player_id: str
    target_scope: str
    destroyed_unit_instance_id: str
    destroyed_model_instance_id: str | None
    destroyed_position_payload: JsonValue
    trigger_battle_round: int
    trigger_phase: str
    resolution_timing: str
    roll_expression: str
    roll_count: int
    success_threshold: int
    placement_anchor: str
    placement_preference: str
    engagement_range_restriction: bool
    restore_wounds_mode: str
    wounds_remaining: int | None
    resolved: bool


@dataclass(frozen=True, slots=True)
class PendingReturnOnDeath:
    pending_id: str
    source_rule_id: str
    source_ability_id: str
    source_clause_id: str
    source_effect_index: int
    owner_player_id: str
    target_scope: ReturnDestroyedTargetScope
    destroyed_unit_instance_id: str
    destroyed_model_instance_id: str | None
    destroyed_position_payload: JsonValue
    trigger_battle_round: int
    trigger_phase: str
    resolution_timing: str
    roll_expression: str
    roll_count: int
    success_threshold: int
    placement_anchor: str
    placement_preference: str
    engagement_range_restriction: bool
    restore_wounds_mode: ReturnRestoreWoundsMode
    wounds_remaining: int | None
    resolved: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "pending_id", _validate_identifier("pending_id", self.pending_id))
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "source_ability_id",
            _validate_identifier("source_ability_id", self.source_ability_id),
        )
        object.__setattr__(
            self,
            "source_clause_id",
            _validate_identifier("source_clause_id", self.source_clause_id),
        )
        object.__setattr__(
            self,
            "source_effect_index",
            _validate_non_negative_int("source_effect_index", self.source_effect_index),
        )
        object.__setattr__(
            self,
            "owner_player_id",
            _validate_identifier("owner_player_id", self.owner_player_id),
        )
        object.__setattr__(self, "target_scope", _target_scope_from_token(self.target_scope))
        object.__setattr__(
            self,
            "destroyed_unit_instance_id",
            _validate_identifier("destroyed_unit_instance_id", self.destroyed_unit_instance_id),
        )
        object.__setattr__(
            self,
            "destroyed_model_instance_id",
            _validate_optional_identifier(
                "destroyed_model_instance_id",
                self.destroyed_model_instance_id,
            ),
        )
        if (
            self.target_scope is ReturnDestroyedTargetScope.DESTROYED_MODEL
            and self.destroyed_model_instance_id is None
        ):
            raise GameLifecycleError("Return-on-death destroyed_model scope requires model ID.")
        object.__setattr__(
            self,
            "destroyed_position_payload",
            validate_json_value(self.destroyed_position_payload),
        )
        object.__setattr__(
            self,
            "trigger_battle_round",
            _validate_positive_int("trigger_battle_round", self.trigger_battle_round),
        )
        object.__setattr__(
            self,
            "trigger_phase",
            _validate_identifier("trigger_phase", self.trigger_phase),
        )
        object.__setattr__(
            self,
            "resolution_timing",
            _validate_supported_token(
                "resolution_timing",
                self.resolution_timing,
                supported=("phase_end",),
            ),
        )
        object.__setattr__(
            self,
            "roll_expression",
            _validate_supported_token("roll_expression", self.roll_expression, supported=("D6",)),
        )
        object.__setattr__(
            self,
            "roll_count",
            _validate_positive_int("roll_count", self.roll_count),
        )
        object.__setattr__(
            self,
            "success_threshold",
            _validate_d6_threshold("success_threshold", self.success_threshold),
        )
        object.__setattr__(
            self,
            "placement_anchor",
            _validate_supported_token(
                "placement_anchor",
                self.placement_anchor,
                supported=("destroyed_position",),
            ),
        )
        object.__setattr__(
            self,
            "placement_preference",
            _validate_supported_token(
                "placement_preference",
                self.placement_preference,
                supported=("as_close_as_possible",),
            ),
        )
        if type(self.engagement_range_restriction) is not bool:
            raise GameLifecycleError("Return-on-death engagement restriction must be bool.")
        if not self.engagement_range_restriction:
            raise GameLifecycleError("Return-on-death requires Engagement Range restriction.")
        object.__setattr__(
            self,
            "restore_wounds_mode",
            _restore_wounds_mode_from_token(self.restore_wounds_mode),
        )
        if self.restore_wounds_mode is ReturnRestoreWoundsMode.FIXED_REMAINING:
            object.__setattr__(
                self,
                "wounds_remaining",
                _validate_positive_int("wounds_remaining", self.wounds_remaining),
            )
        elif self.wounds_remaining is not None:
            raise GameLifecycleError("Return-on-death full_health must not set wounds remaining.")
        if type(self.resolved) is not bool:
            raise GameLifecycleError("Return-on-death resolved must be bool.")

    def mark_resolved(self) -> PendingReturnOnDeath:
        if self.resolved:
            return self
        return replace(self, resolved=True)

    def consumed_key(self) -> str:
        target_id = (
            self.destroyed_model_instance_id
            if self.target_scope is ReturnDestroyedTargetScope.DESTROYED_MODEL
            else self.destroyed_unit_instance_id
        )
        if target_id is None:
            raise GameLifecycleError("Return-on-death consumed key target is missing.")
        return f"{self.source_rule_id}/{self.source_clause_id}/{target_id}/battle"

    def to_payload(self) -> PendingReturnOnDeathPayload:
        return {
            "pending_id": self.pending_id,
            "source_rule_id": self.source_rule_id,
            "source_ability_id": self.source_ability_id,
            "source_clause_id": self.source_clause_id,
            "source_effect_index": self.source_effect_index,
            "owner_player_id": self.owner_player_id,
            "target_scope": self.target_scope.value,
            "destroyed_unit_instance_id": self.destroyed_unit_instance_id,
            "destroyed_model_instance_id": self.destroyed_model_instance_id,
            "destroyed_position_payload": self.destroyed_position_payload,
            "trigger_battle_round": self.trigger_battle_round,
            "trigger_phase": self.trigger_phase,
            "resolution_timing": self.resolution_timing,
            "roll_expression": self.roll_expression,
            "roll_count": self.roll_count,
            "success_threshold": self.success_threshold,
            "placement_anchor": self.placement_anchor,
            "placement_preference": self.placement_preference,
            "engagement_range_restriction": self.engagement_range_restriction,
            "restore_wounds_mode": self.restore_wounds_mode.value,
            "wounds_remaining": self.wounds_remaining,
            "resolved": self.resolved,
        }

    @classmethod
    def from_payload(cls, payload: PendingReturnOnDeathPayload) -> PendingReturnOnDeath:
        return cls(
            pending_id=payload["pending_id"],
            source_rule_id=payload["source_rule_id"],
            source_ability_id=payload["source_ability_id"],
            source_clause_id=payload["source_clause_id"],
            source_effect_index=payload["source_effect_index"],
            owner_player_id=payload["owner_player_id"],
            target_scope=_target_scope_from_token(payload["target_scope"]),
            destroyed_unit_instance_id=payload["destroyed_unit_instance_id"],
            destroyed_model_instance_id=payload["destroyed_model_instance_id"],
            destroyed_position_payload=payload["destroyed_position_payload"],
            trigger_battle_round=payload["trigger_battle_round"],
            trigger_phase=payload["trigger_phase"],
            resolution_timing=payload["resolution_timing"],
            roll_expression=payload["roll_expression"],
            roll_count=payload["roll_count"],
            success_threshold=payload["success_threshold"],
            placement_anchor=payload["placement_anchor"],
            placement_preference=payload["placement_preference"],
            engagement_range_restriction=payload["engagement_range_restriction"],
            restore_wounds_mode=_restore_wounds_mode_from_token(payload["restore_wounds_mode"]),
            wounds_remaining=payload["wounds_remaining"],
            resolved=payload["resolved"],
        )


def resolve_pending_return_on_death_phase_end(
    *,
    state: GameState,
    decisions: DecisionController,
    dice_manager: DiceRollManager | None = None,
) -> DecisionRequest | None:
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    for pending in tuple(state.pending_return_on_death):
        if pending.resolved:
            continue
        if pending.resolution_timing != "phase_end":
            continue
        if pending.trigger_battle_round != state.battle_round:
            continue
        if (
            state.current_battle_phase is None
            or pending.trigger_phase != state.current_battle_phase.value
        ):
            continue
        roll_state = manager.roll(_return_on_death_roll_spec(state=state, pending=pending))
        success = roll_state.current_total >= pending.success_threshold
        decisions.event_log.append(
            RETURN_ON_DEATH_ROLL_RESOLVED_EVENT_TYPE,
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": pending.trigger_phase,
                "pending_id": pending.pending_id,
                "roll_state": roll_state.to_payload(),
                "success_threshold": pending.success_threshold,
                "success": success,
            },
        )
        if not success:
            state.resolve_pending_return_on_death(pending.pending_id)
            decisions.event_log.append(
                RETURN_ON_DEATH_FAILED_ROLL_EVENT_TYPE,
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": pending.trigger_phase,
                    "pending_id": pending.pending_id,
                    "roll_state": roll_state.to_payload(),
                },
            )
            continue
        request = build_return_on_death_placement_request(state=state, pending=pending)
        decisions.request_decision(request)
        decisions.event_log.append(
            RETURN_ON_DEATH_SET_BACK_UP_REQUESTED_EVENT_TYPE,
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": pending.trigger_phase,
                "pending_id": pending.pending_id,
                "request_id": request.request_id,
            },
        )
        return request
    return None


def build_return_on_death_placement_request(
    *,
    state: GameState,
    pending: PendingReturnOnDeath,
) -> DecisionRequest:
    if type(pending) is not PendingReturnOnDeath:
        raise GameLifecycleError("Return-on-death placement request requires pending record.")
    payload = validate_json_value(
        {
            "submission_kind": SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
            "pending_id": pending.pending_id,
            "source_rule_id": pending.source_rule_id,
            "destroyed_unit_instance_id": pending.destroyed_unit_instance_id,
            "destroyed_model_instance_id": pending.destroyed_model_instance_id,
            "placement_anchor": pending.placement_anchor,
            "placement_preference": pending.placement_preference,
            "placement_kind": "battlefield_set_up",
            "restriction": {"not_within_engagement_range_of_enemy_units": True},
        }
    )
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
        actor_id=pending.owner_player_id,
        payload=payload,
        options=(parameterized_decision_option(),),
    )


def invalid_return_on_death_placement_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    try:
        _parse_return_on_death_placement_submission(
            state=state,
            request=request,
            result=result,
            ruleset_descriptor=ruleset_descriptor,
        )
    except (DecisionError, GameLifecycleError, PlacementError, KeyError, TypeError) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Return-on-death placement is invalid.",
            payload={
                "game_id": state.game_id,
                "request_id": request.request_id,
                "result_id": result.result_id,
                "invalid_reason": f"malformed_or_invalid:{type(exc).__name__}",
            },
        )
    return None


def apply_return_on_death_placement_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> PendingReturnOnDeath:
    pending, submission = _parse_return_on_death_placement_submission(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=ruleset_descriptor,
    )
    _restore_returned_target(state=state, pending=pending, placement=submission.attempted_placement)
    resolved = state.resolve_pending_return_on_death(pending.pending_id)
    decisions.event_log.append(
        RETURN_ON_DEATH_SET_BACK_UP_COMPLETED_EVENT_TYPE,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": pending.trigger_phase,
            "request_id": request.request_id,
            "result_id": result.result_id,
            "pending": resolved.to_payload(),
            "placement": submission.attempted_placement.to_payload(),
        },
    )
    return resolved


def _parse_return_on_death_placement_submission(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> tuple[PendingReturnOnDeath, PlacementProposalPayload]:
    if request.decision_type != SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE:
        raise GameLifecycleError("Return-on-death request decision_type drift.")
    result.validate_for_request(request)
    request_payload = _payload_object(request.payload)
    if request_payload.get("submission_kind") != SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE:
        raise GameLifecycleError("Return-on-death request submission_kind drift.")
    pending_id = _payload_string(request_payload, key="pending_id")
    pending = state.pending_return_on_death_by_id(pending_id)
    if pending.resolved:
        raise GameLifecycleError("Return-on-death pending record is stale.")
    if pending.owner_player_id != result.actor_id:
        raise GameLifecycleError("Return-on-death actor drift.")
    result_payload = _payload_object(result.payload)
    if result_payload.get("submission_kind") == SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE:
        attempted = result_payload.get("attempted_placement")
        if not isinstance(attempted, dict):
            raise GameLifecycleError("Return-on-death attempted_placement must be object.")
        placement_payload = cast(
            PlacementProposalPayloadPayload,
            {
                "proposal_request_id": request.request_id,
                "proposal_kind": ProposalKind.REINFORCEMENT.value,
                "unit_instance_id": pending.destroyed_unit_instance_id,
                "placement_kind": BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD.value,
                "attempted_placement": attempted,
            },
        )
    else:
        placement_payload = cast(PlacementProposalPayloadPayload, result_payload)
    submission = PlacementProposalPayload.from_payload(placement_payload)
    if submission.unit_instance_id != pending.destroyed_unit_instance_id:
        raise GameLifecycleError("Return-on-death placement unit drift.")
    if submission.placement_kind is not BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD:
        raise GameLifecycleError("Return-on-death placement kind must return to battlefield.")
    _validate_return_on_death_placement(
        state=state,
        pending=pending,
        placement=submission.attempted_placement,
        ruleset_descriptor=ruleset_descriptor,
    )
    return pending, submission


def _validate_return_on_death_placement(
    *,
    state: GameState,
    pending: PendingReturnOnDeath,
    placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
) -> None:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Return-on-death placement requires RulesetDescriptor.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Return-on-death placement requires battlefield_state.")
    if placement.unit_instance_id != pending.destroyed_unit_instance_id:
        raise GameLifecycleError("Return-on-death placement unit drift.")
    model_ids = {model.model_instance_id for model in placement.model_placements}
    if pending.target_scope is ReturnDestroyedTargetScope.DESTROYED_MODEL:
        if model_ids != {pending.destroyed_model_instance_id}:
            raise GameLifecycleError("Return-on-death model placement must include only target.")
    else:
        unit = _unit_by_id(state=state, unit_instance_id=pending.destroyed_unit_instance_id)
        expected_ids = {model.model_instance_id for model in unit.own_models}
        if model_ids != expected_ids:
            raise GameLifecycleError("Return-on-death unit placement must include all models.")
    _assert_destroyed_position_anchor(
        state=state,
        pending=pending,
        placement=placement,
        ruleset_descriptor=ruleset_descriptor,
    )
    if pending.engagement_range_restriction:
        _assert_not_within_enemy_engagement_range(
            state=state,
            placement=placement,
            ruleset_descriptor=ruleset_descriptor,
            owner_player_id=pending.owner_player_id,
        )


def _assert_destroyed_position_anchor(
    *,
    state: GameState,
    pending: PendingReturnOnDeath,
    placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
) -> None:
    anchor = _destroyed_model_placement_from_pending(pending)
    if anchor.unit_instance_id != pending.destroyed_unit_instance_id:
        raise GameLifecycleError("Return-on-death destroyed position unit drift.")
    if (
        pending.target_scope is ReturnDestroyedTargetScope.DESTROYED_MODEL
        and anchor.model_instance_id != pending.destroyed_model_instance_id
    ):
        raise GameLifecycleError("Return-on-death destroyed position model drift.")
    attempted_anchor = _placement_for_model(
        placement=placement,
        model_instance_id=anchor.model_instance_id,
    )
    if attempted_anchor.pose == anchor.pose:
        return
    if _model_placement_within_enemy_engagement_range(
        state=state,
        model_placement=anchor,
        ruleset_descriptor=ruleset_descriptor,
        owner_player_id=pending.owner_player_id,
    ):
        return
    raise GameLifecycleError("Return-on-death placement must use destroyed position when legal.")


def _destroyed_model_placement_from_pending(pending: PendingReturnOnDeath) -> ModelPlacement:
    payload = _payload_object(pending.destroyed_position_payload)
    if _payload_string(payload, key="source") != "model_destroyed_event":
        raise GameLifecycleError("Return-on-death requires destroyed model placement evidence.")
    event_payload = _payload_object(payload.get("model_destroyed_payload"))
    destroyed_placement_payload = _payload_object(event_payload.get("destroyed_model_placement"))
    for key in ("army_id", "player_id", "unit_instance_id", "model_instance_id", "pose"):
        if key not in destroyed_placement_payload:
            raise GameLifecycleError("Return-on-death destroyed model placement is incomplete.")
    if not isinstance(destroyed_placement_payload["pose"], dict):
        raise GameLifecycleError("Return-on-death destroyed model placement pose must be object.")
    return ModelPlacement.from_payload(cast(ModelPlacementPayload, destroyed_placement_payload))


def _placement_for_model(*, placement: UnitPlacement, model_instance_id: str) -> ModelPlacement:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for model_placement in placement.model_placements:
        if model_placement.model_instance_id == requested_model_id:
            return model_placement
    raise GameLifecycleError("Return-on-death placement is missing destroyed anchor model.")


def _assert_not_within_enemy_engagement_range(
    *,
    state: GameState,
    placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
    owner_player_id: str,
) -> None:
    if _placement_within_enemy_engagement_range(
        state=state,
        placement=placement,
        ruleset_descriptor=ruleset_descriptor,
        owner_player_id=owner_player_id,
    ):
        raise GameLifecycleError("Return-on-death placement is within Engagement Range.")


def _model_placement_within_enemy_engagement_range(
    *,
    state: GameState,
    model_placement: ModelPlacement,
    ruleset_descriptor: RulesetDescriptor,
    owner_player_id: str,
) -> bool:
    return _placement_within_enemy_engagement_range(
        state=state,
        placement=UnitPlacement(
            army_id=model_placement.army_id,
            player_id=model_placement.player_id,
            unit_instance_id=model_placement.unit_instance_id,
            model_placements=(model_placement,),
        ),
        ruleset_descriptor=ruleset_descriptor,
        owner_player_id=owner_player_id,
    )


def _placement_within_enemy_engagement_range(
    *,
    state: GameState,
    placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
    owner_player_id: str,
) -> bool:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Return-on-death engagement check requires battlefield_state.")
    returned_models = tuple(
        geometry_model_for_placement(
            model=_model_by_id(state=state, model_instance_id=model_placement.model_instance_id),
            placement=model_placement,
        )
        for model_placement in placement.model_placements
    )
    for placed_army in battlefield.placed_armies:
        if placed_army.player_id == owner_player_id:
            continue
        for enemy_unit in placed_army.unit_placements:
            for enemy_placement in enemy_unit.model_placements:
                enemy_model = geometry_model_for_placement(
                    model=_model_by_id(
                        state=state,
                        model_instance_id=enemy_placement.model_instance_id,
                    ),
                    placement=enemy_placement,
                )
                if any(
                    returned_model.is_within_engagement_range(
                        enemy_model,
                        horizontal_inches=(ruleset_descriptor.engagement_policy.horizontal_inches),
                        vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
                    )
                    for returned_model in returned_models
                ):
                    return True
    return False


def _restore_returned_target(
    *,
    state: GameState,
    pending: PendingReturnOnDeath,
    placement: UnitPlacement,
) -> None:
    if pending.target_scope is ReturnDestroyedTargetScope.DESTROYED_MODEL:
        model_id = _validate_identifier(
            "destroyed_model_instance_id",
            pending.destroyed_model_instance_id,
        )
        wounds_remaining = (
            pending.wounds_remaining
            if pending.restore_wounds_mode is ReturnRestoreWoundsMode.FIXED_REMAINING
            else _model_by_id(state=state, model_instance_id=model_id).starting_wounds
        )
        if wounds_remaining is None:
            raise GameLifecycleError("Return-on-death fixed wounds are missing.")
        state.army_definitions = list(
            _army_definitions_with_model_wounds(
                armies=tuple(state.army_definitions),
                model_instance_id=model_id,
                wounds_remaining=wounds_remaining,
            )
        )
    else:
        state.army_definitions = list(
            _army_definitions_with_unit_full_health(
                armies=tuple(state.army_definitions),
                unit_instance_id=pending.destroyed_unit_instance_id,
            )
        )
    if state.battlefield_state is None:
        raise GameLifecycleError("Return-on-death restore requires battlefield_state.")
    state.battlefield_state = _battlefield_with_returned_placement(
        battlefield=state.battlefield_state,
        placement=placement,
    )


def _battlefield_with_returned_placement(
    *,
    battlefield: BattlefieldRuntimeState,
    placement: UnitPlacement,
) -> BattlefieldRuntimeState:
    placed_unit_ids = {
        unit_placement.unit_instance_id
        for army in battlefield.placed_armies
        for unit_placement in army.unit_placements
    }
    if placement.unit_instance_id in placed_unit_ids:
        updated = battlefield
        for model_placement in placement.model_placements:
            updated = updated.with_returned_model_placement(model_placement)
        return updated
    returned_model_ids = {model.model_instance_id for model in placement.model_placements}
    if not returned_model_ids <= set(battlefield.removed_model_ids):
        raise GameLifecycleError("Return-on-death placement models must be removed.")
    without_removed = BattlefieldRuntimeState(
        battlefield_id=battlefield.battlefield_id,
        battlefield_width_inches=battlefield.battlefield_width_inches,
        battlefield_depth_inches=battlefield.battlefield_depth_inches,
        terrain_features=battlefield.terrain_features,
        placed_armies=battlefield.placed_armies,
        removed_model_ids=tuple(
            sorted(
                model_id
                for model_id in battlefield.removed_model_ids
                if model_id not in returned_model_ids
            )
        ),
    )
    return without_removed.with_added_unit_placement(placement)


def _return_on_death_roll_spec(
    *,
    state: GameState,
    pending: PendingReturnOnDeath,
) -> DiceRollSpec:
    if pending.roll_expression != "D6" or pending.roll_count != 1:
        raise GameLifecycleError("Return-on-death currently supports exactly one D6.")
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="return_on_death_phase_end_gate",
        roll_type="return_on_death",
        actor_id=pending.owner_player_id,
        reroll_forbidden_rule_ids=(pending.source_rule_id,),
    )


def _unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return unit
    raise GameLifecycleError("Return-on-death unit is unknown.")


def _model_by_id(*, state: GameState, model_instance_id: str) -> ModelInstance:
    requested_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id == requested_id:
                    return model
    raise GameLifecycleError("Return-on-death model is unknown.")


def _army_definitions_with_model_wounds(
    *,
    armies: tuple[ArmyDefinition, ...],
    model_instance_id: str,
    wounds_remaining: int,
) -> tuple[ArmyDefinition, ...]:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    updated_armies: list[ArmyDefinition] = []
    did_update = False
    for army in armies:
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("Return-on-death armies must contain ArmyDefinition.")
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_models: list[ModelInstance] = []
            for model in unit.own_models:
                if model.model_instance_id != requested_model_id:
                    updated_models.append(model)
                    continue
                updated_models.append(replace(model, wounds_remaining=wounds_remaining))
                did_update = True
            updated_units.append(replace(unit, own_models=tuple(updated_models)))
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not did_update:
        raise GameLifecycleError("Return-on-death cannot update an unknown model.")
    return tuple(updated_armies)


def _army_definitions_with_unit_full_health(
    *,
    armies: tuple[ArmyDefinition, ...],
    unit_instance_id: str,
) -> tuple[ArmyDefinition, ...]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    updated_armies: list[ArmyDefinition] = []
    did_update = False
    for army in armies:
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("Return-on-death armies must contain ArmyDefinition.")
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id != requested_unit_id:
                updated_units.append(unit)
                continue
            updated_units.append(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=model.starting_wounds)
                        for model in unit.own_models
                    ),
                )
            )
            did_update = True
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not did_update:
        raise GameLifecycleError("Return-on-death cannot update an unknown unit.")
    return tuple(updated_armies)


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Return-on-death payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Return-on-death payload missing {key}.")
    return _validate_identifier(key, payload[key])


def _target_scope_from_token(token: object) -> ReturnDestroyedTargetScope:
    if type(token) is ReturnDestroyedTargetScope:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Return-on-death target_scope must be a string.")
    try:
        return ReturnDestroyedTargetScope(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported return-on-death target_scope: {token}.") from exc


def _restore_wounds_mode_from_token(token: object) -> ReturnRestoreWoundsMode:
    if type(token) is ReturnRestoreWoundsMode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Return-on-death restore mode must be a string.")
    try:
        return ReturnRestoreWoundsMode(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported return-on-death restore mode: {token}.") from exc


def _validate_supported_token(
    field_name: str,
    value: object,
    *,
    supported: tuple[str, ...],
) -> str:
    token = _validate_identifier(field_name, value)
    if token not in set(supported):
        raise GameLifecycleError(f"Unsupported return-on-death {field_name}: {token}.")
    return token


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Return-on-death {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Return-on-death {field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"Return-on-death {field_name} must be non-negative int.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"Return-on-death {field_name} must be positive int.")
    return value


def _validate_d6_threshold(field_name: str, value: object) -> int:
    if type(value) is not int or value < 2 or value > 6:
        raise GameLifecycleError(f"Return-on-death {field_name} must be a D6 threshold.")
    return value
