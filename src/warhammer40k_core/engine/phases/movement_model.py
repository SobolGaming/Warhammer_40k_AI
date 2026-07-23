# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phases.movement_imports import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mission_setup import MissionSetup
    from warhammer40k_core.engine.phases.movement_state import MovementPhaseState, NormalMoveResolution, AdvanceMoveResolution, FallBackActionResult, _ResolvedUnitMove
    from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler, _begin_reinforcements_step, _complete_reinforcements_step
    from warhammer40k_core.engine.phases.movement_reactions import _request_end_opponent_movement_reaction_if_available, _request_end_movement_active_player_stratagem_if_available, _request_rapid_ingress_reaction_if_available, _request_fire_overwatch_reaction_if_available, _request_selected_to_move_stratagem_if_available, _request_selected_to_fall_back_stratagem_if_available, _request_friendly_unit_fell_back_stratagem_if_available, _friendly_unit_fell_back_context_from_event, _friendly_unit_fell_back_timing_window_id, _stratagem_used_for_context, _selected_to_fall_back_trigger_payload, _selected_to_fall_back_timing_window_id, _selected_to_move_timing_window_id, _stratagem_use_payload_factory, _stratagem_target_proposal_payload_factory, _request_movement_end_surge_if_available, _movement_end_surge_distance_roll_spec, _eligible_triggered_movement_units_from_grants, _movement_end_surge_grant_distance_bonus, _movement_end_surge_event_already_processed, _active_player_end_movement_overwatch_trigger_unit_ids, _fire_overwatch_end_movement_trigger_payload
    from warhammer40k_core.engine.phases.movement_reinforcements import _reinforcement_unit_options, _eligible_reinforcement_reserve_states, _required_reinforcement_reserve_states, _overdue_required_reinforcement_reserve_states, _apply_reinforcement_unit_selection_decision, _request_reinforcement_placement, _reserve_placement_kinds_for_unit, _reserve_proposal_kind, _request_placement_proposal_retry, _optional_proposal_context_string, _resolve_reinforcement_placement_submission, _deep_strike_enemy_distance_for_reserve_arrival, _unit_for_reserve_state, _apply_valid_reinforcement_placement
    from warhammer40k_core.engine.phases.movement_transports import _request_pre_move_disembark_if_available, _request_post_normal_move_disembark_if_available, _pre_move_disembark_entries, _post_normal_move_disembark_entries, _disembark_unit_selection_options, _apply_disembark_unit_selection_decision, _request_disembark_placement, _resolve_disembark_placement_submission, _allowed_disembark_modes_for_placement_request, _resolve_combat_disembark_placement_submission
    from warhammer40k_core.engine.phases.movement_placement_proposals import _parse_movement_proposal_submission_or_invalid, _parse_placement_proposal_submission_or_invalid, _proposal_payload_parse_failure, _key_error_field, _apply_placement_proposal_decision, _missing_disembark_proposal_field, _apply_valid_disembark, _apply_valid_combat_disembark
    from warhammer40k_core.engine.phases.movement_action_decisions import _request_movement_action, _apply_movement_action_decision, _request_advance_move_grant_decision_if_available, _decline_advance_move_grant_option, _advance_move_grant_option, _apply_advance_move_grant_decision, _assert_advance_move_grant_still_available, _record_movement_action_grant_effects, _movement_action_grant_unit_effect_target_ids, _movement_action_grant_effect_expiration, _resolve_pending_movement_action_after_grants, _resolve_pending_advance_action, _request_pending_movement_action_proposal, _request_movement_proposal, _forced_desperate_escape_sources_for_unit, _forced_desperate_escape_source_rule_ids_from_context, _request_movement_proposal_retry
    from warhammer40k_core.engine.phases.movement_resolution_flow import _apply_movement_proposal_decision, _action_result_from_proposal_request, _reject_invalid_proposal, _reject_invalid_movement_resolution, _apply_advance_roll_reroll_decision, _resolve_and_apply_advance_move, _advance_move_grants_from_context, _selected_advance_move_grant_hook_ids_from_context, _apply_advance_move_grants, _grant_ranged_weapon_keywords, _aircraft_reserve_transition_reason_for_normal_move, _apply_aircraft_reserve_transition_for_normal_move
    from warhammer40k_core.engine.phases.movement_fall_back_embark import _apply_desperate_escape_model_selection_decision, _apply_fall_back_result, _request_embark_after_move_or_complete_activation, _complete_activation_then_request_post_normal_disembark_if_available, _post_move_embark_options, _apply_embark_transport_selection_decision, _apply_valid_embark, _complete_movement_activation, _complete_movement_activation_with_record_ids, _maximum_model_distance_inches_from_witness, _interrupt_started_mission_actions_for_movement_activation
    from warhammer40k_core.engine.phases.movement_options_dice import _mission_action_state_is_active_for_unit, _movement_action_options, _advance_roll_request_for_action, _roll_advance_dice, _record_advance_roll_resolved_event, _advance_roll_reroll_request, _dice_roll_manager_for_state, _advance_reroll_permission_for_unit, _roll_desperate_escape_dice, _desperate_escape_model_selection_request, _desperate_escape_model_selection_options
    from warhammer40k_core.engine.phases.movement_resolvers import resolve_normal_move, resolve_advance_move, resolve_fall_back_move, _resolve_unit_move, _default_move_witness, _default_fall_back_witness, _movement_transition_batch, _fall_back_transition_batch, _normal_move_transition_batch, _movement_action_availability_result
    from warhammer40k_core.engine.phases.movement_geometry import _movement_action_availability_context, _enemy_engagement_model_ids_for_unit, _enemy_engaged_unit_ids_for_unit_placement, _hover_mode_state_for_unit, _desperate_escape_requirements_for_fall_back, _enemy_model_ids_crossed_by_witness, _sampled_witness_transit_poses, _interpolate_pose, _model_at_pose, _geometry_models_for_unit_placement, _friendly_geometry_models_for_path, _enemy_geometry_models_for_player, _friendly_vehicle_monster_model_ids, _enemy_vehicle_monster_model_ids_for_player, _unit_has_vehicle_or_monster_keyword, _unit_has_deep_strike_keyword, _canonical_keyword, _validate_ability_index_mapping, _ability_index_for_player, _validate_move_witness_matches_unit, _path_result_with_aircraft_violations, _normal_move_violation_code
    from warhammer40k_core.engine.phases.movement_validation import _movement_action_invalid_payload, assert_move_units_step_complete_for_reinforcements, _remaining_move_units_unit_ids, _normal_move_invalid_message, _ensure_movement_phase_state, _validate_movement_phase_state, _battlefield_scenario, _movement_unit_options, _active_player_id, movement_phase_action_kind_from_token, fall_back_mode_kind_from_token, movement_phase_step_kind_from_token, desperate_escape_requirement_reason_from_token, movement_mode_for_phase_action, _movement_mode_from_payload, _movement_mode_from_proposal_submission, _fall_back_mode_from_payload, _fall_back_mode_from_proposal_submission, _movement_action_option_id, _movement_action_label, _movement_modes_for_action_options, _unit_can_take_to_the_skies, _fall_back_modes_for_parameterized_option, _fall_back_result_with_mode, _fall_back_mode_violation_code, _model_movement_inches, _model_base_movement_inches, _model_movement_budget_inches, _movement_distance_modifier_inches, _movement_mode_for_action, _temporary_movement_keywords_for_unit, _movement_bonus_inches_for_unit, _effective_movement_keywords, _model_default_movement_distance_inches, _modified_movement_inches, _runtime_modifier_registry, _default_move_end_pose, _ruleset_descriptor_for_handler, _mission_setup_for_live_reinforcements, _objective_markers_for_state, _active_movement_selection, _ensure_transport_cargo_phase_states, _unit_instance_by_id, _unit_has_keyword, _transport_status_for_movement_action, _movement_completion_context_payload, _transport_operation_invalid_payload, _request_payload_for_result, _decision_payload_object, _payload_string, _payload_object, _payload_json_object, _identifier_list_from_json_object, _payload_positive_int, _optional_payload_path_witness, _payload_model_displacement_kind, _payload_transition_batch, _payload_json_array, _validate_json_object, _validate_movement_action_tuple, _validate_transport_restriction_override_tuple, _validate_path_validation_result_tuple, _validate_terrain_path_legality_result_tuple, _validate_desperate_escape_reason_tuple, _validate_desperate_escape_requirement_tuple, _validate_desperate_escape_roll_tuple, _validate_identifier_tuple, _validate_movement_distance_records, _validate_objective_marker_tuple, _validate_advance_roll_spec, _validate_identifier, _validate_positive_int, _validate_non_negative_finite_number, _validate_bool
# fmt: on

__all__ = (
    "COMPLETE_DISEMBARKS_OPTION_ID",
    "COMPLETE_REINFORCEMENTS_OPTION_ID",
    "DECLINE_EMBARK_OPTION_ID",
    "SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE",
    "SELECT_DISEMBARK_UNIT_DECISION_TYPE",
    "SELECT_EMBARK_TRANSPORT_DECISION_TYPE",
    "SELECT_MOVEMENT_ACTION_DECISION_TYPE",
    "SELECT_MOVEMENT_UNIT_DECISION_TYPE",
    "SELECT_REINFORCEMENT_UNIT_DECISION_TYPE",
    "_ADVANCED_UNIT_CLEANUP_POINT",
    "_ADVANCE_REROLL_KEYWORD",
    "_DESPERATE_ESCAPE_ROLL_TYPE",
    "_FELL_BACK_UNIT_CLEANUP_POINT",
    "_MOVEMENT_ACTIONS_INSIDE_ENEMY_ENGAGEMENT",
    "_MOVEMENT_ACTIONS_OUTSIDE_ENEMY_ENGAGEMENT",
    "AdvanceRollRequest",
    "AdvanceRollRequestPayload",
    "AdvanceRollResult",
    "AdvanceRollResultPayload",
    "AdvancedUnitState",
    "AdvancedUnitStatePayload",
    "DesperateEscapeRequirement",
    "DesperateEscapeRequirementPayload",
    "DesperateEscapeRequirementReason",
    "DesperateEscapeRoll",
    "DesperateEscapeRollPayload",
    "DisembarkCandidate",
    "FallBackActionResultPayload",
    "FallBackModeKind",
    "FellBackUnitState",
    "FellBackUnitStatePayload",
    "MovementActionAvailabilityContext",
    "MovementActionAvailabilityContextPayload",
    "MovementActionAvailabilityResult",
    "MovementActionAvailabilityResultPayload",
    "MovementDiceRecord",
    "MovementDiceRecordPayload",
    "MovementDistanceRecord",
    "MovementDistanceRecordPayload",
    "MovementPhaseActionKind",
    "MovementPhaseStatePayload",
    "MovementPhaseStepKind",
    "MovementUnitSelection",
    "MovementUnitSelectionPayload",
    "PendingMovementActionSelection",
    "PendingMovementActionSelectionPayload",
    "_MovementProposalParseResult",
    "_PlacementProposalParseResult",
    "_empty_ability_indexes",
)

SELECT_MOVEMENT_UNIT_DECISION_TYPE = "select_movement_unit"
SELECT_MOVEMENT_ACTION_DECISION_TYPE = "select_movement_action"
SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE = "select_desperate_escape_model"
SELECT_REINFORCEMENT_UNIT_DECISION_TYPE = "select_reinforcement_unit"
SELECT_DISEMBARK_UNIT_DECISION_TYPE = "select_disembark_unit"
SELECT_EMBARK_TRANSPORT_DECISION_TYPE = "select_embark_transport"
COMPLETE_REINFORCEMENTS_OPTION_ID = "complete_reinforcements"
COMPLETE_DISEMBARKS_OPTION_ID = "complete_disembarks"
DECLINE_EMBARK_OPTION_ID = "decline_embark"


class MovementPhaseStepKind(StrEnum):
    MOVE_UNITS = "move_units"
    REINFORCEMENTS = "reinforcements"


class MovementPhaseActionKind(StrEnum):
    REMAIN_STATIONARY = "remain_stationary"
    NORMAL_MOVE = "normal_move"
    ADVANCE = "advance"
    FALL_BACK = "fall_back"


class FallBackModeKind(StrEnum):
    ORDERED_RETREAT = "ordered_retreat"
    DESPERATE_ESCAPE = "desperate_escape"


class DesperateEscapeRequirementReason(StrEnum):
    ENEMY_MODEL_OVERFLIGHT = "enemy_model_overflight"
    BATTLE_SHOCKED = "battle_shocked"
    FORCED_BY_RULE = "forced_by_rule"


_MOVEMENT_ACTIONS_OUTSIDE_ENEMY_ENGAGEMENT = (
    MovementPhaseActionKind.REMAIN_STATIONARY,
    MovementPhaseActionKind.NORMAL_MOVE,
    MovementPhaseActionKind.ADVANCE,
)
_MOVEMENT_ACTIONS_INSIDE_ENEMY_ENGAGEMENT = (
    MovementPhaseActionKind.REMAIN_STATIONARY,
    MovementPhaseActionKind.FALL_BACK,
)
_ADVANCE_REROLL_KEYWORD = "ADVANCE_REROLL"
_ADVANCED_UNIT_CLEANUP_POINT = "end_of_turn"
_FELL_BACK_UNIT_CLEANUP_POINT = "end_of_turn"
_DESPERATE_ESCAPE_ROLL_TYPE = "desperate_escape_roll"


def _empty_ability_indexes() -> Mapping[str, AbilityCatalogIndex]:
    return MappingProxyType({})


def _validate_movement_roll_modifiers(
    field_name: str,
    value: object,
) -> tuple[RollModifier, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    modifiers: list[RollModifier] = []
    seen: set[str] = set()
    for modifier in cast(tuple[object, ...], value):
        if type(modifier) is not RollModifier:
            raise GameLifecycleError(f"{field_name} must contain RollModifier values.")
        if modifier.modifier_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate modifier IDs.")
        seen.add(modifier.modifier_id)
        modifiers.append(modifier)
    return tuple(modifiers)


type _MovementProposalParseResult = (
    tuple[MovementProposalRequest, MovementProposalPayload] | LifecycleStatus
)
type _PlacementProposalParseResult = (
    tuple[MovementProposalRequest, PlacementProposalPayload] | LifecycleStatus
)


class MovementUnitSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str


class PendingMovementActionSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    movement_phase_action: str
    movement_mode: str
    fall_back_mode: str | None
    request_id: str
    result_id: str
    selected_option_id: str


class MovementPhaseStatePayload(TypedDict):
    battle_round: int
    active_player_id: str
    step: str
    reinforcements_completed: bool
    declined_disembark_unit_ids: list[str]
    declined_post_normal_move_disembark_unit_ids: list[str]
    selected_unit_ids: list[str]
    moved_unit_ids: list[str]
    movement_distance_records: NotRequired[list[MovementDistanceRecordPayload]]
    active_selection: MovementUnitSelectionPayload | None
    pending_action: PendingMovementActionSelectionPayload | None


class MovementActionAvailabilityContextPayload(TypedDict):
    ruleset_descriptor_hash: str
    unit_instance_id: str
    player_id: str
    enemy_engagement_model_ids: list[str]
    enemy_aircraft_engagement_model_ids: NotRequired[list[str]]
    aircraft_movement_policy: NotRequired[AircraftMovementPolicyPayload]


class MovementActionAvailabilityResultPayload(TypedDict):
    context: MovementActionAvailabilityContextPayload
    available_actions: list[str]
    unavailable_actions: list[str]


class MovementDistanceRecordPayload(TypedDict):
    unit_instance_id: str
    maximum_model_distance_inches: float
    maximum_model_horizontal_distance_inches: float


class AdvanceRollRequestPayload(TypedDict):
    request_id: str
    game_id: str
    battle_round: int
    player_id: str
    unit_instance_id: str
    spec: DiceRollSpecPayload
    roll_modifiers: list[RollModifierPayload]
    reroll_permission: RerollPermissionPayload | None


class AdvanceRollResultPayload(TypedDict):
    request: AdvanceRollRequestPayload
    roll_state: DiceRollStatePayload
    value: int


class MovementDiceRecordPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    movement_phase_action: str
    advance_roll: AdvanceRollResultPayload


class AdvancedUnitStatePayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    movement_dice_record: MovementDiceRecordPayload
    can_shoot: bool
    can_declare_charge: bool
    cleanup_point: str


class DesperateEscapeRequirementPayload(TypedDict):
    requirement_id: str
    player_id: str
    battle_round: int
    unit_instance_id: str
    model_instance_id: str
    reasons: list[str]
    enemy_model_ids: list[str]


class DesperateEscapeRollPayload(TypedDict):
    requirement: DesperateEscapeRequirementPayload
    roll_state: DiceRollStatePayload
    roll_modifiers: list[RollModifierPayload]
    value: int


class FellBackUnitStatePayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    desperate_escape_rolls: list[DesperateEscapeRollPayload]
    can_shoot: bool
    can_declare_charge: bool
    cleanup_point: str


class FallBackActionResultPayload(TypedDict):
    unit_instance_id: str
    attempted_placement: UnitPlacementPayload
    witness: PathWitnessPayload
    desperate_escape_requirements: list[DesperateEscapeRequirementPayload]
    desperate_escape_rolls: list[DesperateEscapeRollPayload]
    path_validation_results: list[PathValidationResultPayload]
    terrain_path_legality_results: list[TerrainPathLegalityResultPayload]
    coherency_result: UnitCoherencyResultPayload
    rollback_record: MovementRollbackRecordPayload | None
    movement_payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class MovementActionAvailabilityContext:
    ruleset_descriptor_hash: str
    unit_instance_id: str
    player_id: str
    enemy_engagement_model_ids: tuple[str, ...] = ()
    enemy_aircraft_engagement_model_ids: tuple[str, ...] = ()
    aircraft_movement_policy: AircraftMovementPolicy | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "MovementActionAvailabilityContext ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "MovementActionAvailabilityContext unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("MovementActionAvailabilityContext player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "enemy_engagement_model_ids",
            _validate_identifier_tuple(
                "MovementActionAvailabilityContext enemy_engagement_model_ids",
                self.enemy_engagement_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "enemy_aircraft_engagement_model_ids",
            _validate_identifier_tuple(
                "MovementActionAvailabilityContext enemy_aircraft_engagement_model_ids",
                self.enemy_aircraft_engagement_model_ids,
            ),
        )
        if self.aircraft_movement_policy is not None:
            if type(self.aircraft_movement_policy) is not AircraftMovementPolicy:
                raise GameLifecycleError(
                    "MovementActionAvailabilityContext aircraft_movement_policy must be "
                    "AircraftMovementPolicy."
                )
            if self.aircraft_movement_policy.unit_instance_id != self.unit_instance_id:
                raise GameLifecycleError(
                    "MovementActionAvailabilityContext aircraft_movement_policy unit drift."
                )
            if (
                self.aircraft_movement_policy.ruleset_descriptor_hash
                != self.ruleset_descriptor_hash
            ):
                raise GameLifecycleError(
                    "MovementActionAvailabilityContext aircraft_movement_policy descriptor drift."
                )

    @property
    def is_within_enemy_engagement_range(self) -> bool:
        return bool(self.enemy_engagement_model_ids)

    def evaluate(self) -> MovementActionAvailabilityResult:
        available_actions: tuple[MovementPhaseActionKind, ...]
        if (
            self.aircraft_movement_policy is not None
            and self.aircraft_movement_policy.uses_aircraft_rules
        ):
            available_actions = (MovementPhaseActionKind.NORMAL_MOVE,)
        elif self.is_within_enemy_engagement_range:
            available_actions = _MOVEMENT_ACTIONS_INSIDE_ENEMY_ENGAGEMENT
        else:
            available_actions = _MOVEMENT_ACTIONS_OUTSIDE_ENEMY_ENGAGEMENT
        unavailable_actions = tuple(
            action for action in MovementPhaseActionKind if action not in available_actions
        )
        return MovementActionAvailabilityResult(
            context=self,
            available_actions=available_actions,
            unavailable_actions=unavailable_actions,
        )

    def to_payload(self) -> MovementActionAvailabilityContextPayload:
        payload: MovementActionAvailabilityContextPayload = {
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "unit_instance_id": self.unit_instance_id,
            "player_id": self.player_id,
            "enemy_engagement_model_ids": list(self.enemy_engagement_model_ids),
        }
        if self.enemy_aircraft_engagement_model_ids:
            payload["enemy_aircraft_engagement_model_ids"] = list(
                self.enemy_aircraft_engagement_model_ids
            )
        if self.aircraft_movement_policy is not None:
            payload["aircraft_movement_policy"] = self.aircraft_movement_policy.to_payload()
        return payload

    @classmethod
    def from_payload(cls, payload: MovementActionAvailabilityContextPayload) -> Self:
        aircraft_policy_payload = payload.get("aircraft_movement_policy")
        aircraft_engagement_payload = payload.get("enemy_aircraft_engagement_model_ids")
        return cls(
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            unit_instance_id=payload["unit_instance_id"],
            player_id=payload["player_id"],
            enemy_engagement_model_ids=tuple(payload["enemy_engagement_model_ids"]),
            enemy_aircraft_engagement_model_ids=()
            if aircraft_engagement_payload is None
            else tuple(aircraft_engagement_payload),
            aircraft_movement_policy=None
            if aircraft_policy_payload is None
            else AircraftMovementPolicy.from_payload(aircraft_policy_payload),
        )


@dataclass(frozen=True, slots=True)
class MovementActionAvailabilityResult:
    context: MovementActionAvailabilityContext
    available_actions: tuple[MovementPhaseActionKind, ...]
    unavailable_actions: tuple[MovementPhaseActionKind, ...]

    def __post_init__(self) -> None:
        if type(self.context) is not MovementActionAvailabilityContext:
            raise GameLifecycleError("MovementActionAvailabilityResult context must be a context.")
        object.__setattr__(
            self,
            "available_actions",
            _validate_movement_action_tuple(
                "MovementActionAvailabilityResult available_actions",
                self.available_actions,
            ),
        )
        object.__setattr__(
            self,
            "unavailable_actions",
            _validate_movement_action_tuple(
                "MovementActionAvailabilityResult unavailable_actions",
                self.unavailable_actions,
            ),
        )
        if set(self.available_actions) & set(self.unavailable_actions):
            raise GameLifecycleError(
                "MovementActionAvailabilityResult actions must not be both available "
                "and unavailable."
            )
        if set(self.available_actions) | set(self.unavailable_actions) != set(
            MovementPhaseActionKind
        ):
            raise GameLifecycleError(
                "MovementActionAvailabilityResult must classify every movement action."
            )

    def is_available(self, action: object) -> bool:
        return movement_phase_action_kind_from_token(action) in self.available_actions

    def to_payload(self) -> MovementActionAvailabilityResultPayload:
        return {
            "context": self.context.to_payload(),
            "available_actions": [action.value for action in self.available_actions],
            "unavailable_actions": [action.value for action in self.unavailable_actions],
        }

    @classmethod
    def from_payload(cls, payload: MovementActionAvailabilityResultPayload) -> Self:
        return cls(
            context=MovementActionAvailabilityContext.from_payload(payload["context"]),
            available_actions=tuple(
                movement_phase_action_kind_from_token(action)
                for action in payload["available_actions"]
            ),
            unavailable_actions=tuple(
                movement_phase_action_kind_from_token(action)
                for action in payload["unavailable_actions"]
            ),
        )


@dataclass(frozen=True, slots=True)
class AdvanceRollRequest:
    request_id: str
    game_id: str
    battle_round: int
    player_id: str
    unit_instance_id: str
    spec: DiceRollSpec
    roll_modifiers: tuple[RollModifier, ...] = ()
    reroll_permission: RerollPermission | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("AdvanceRollRequest request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("AdvanceRollRequest game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("AdvanceRollRequest battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("AdvanceRollRequest player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("AdvanceRollRequest unit_instance_id", self.unit_instance_id),
        )
        if type(self.spec) is not DiceRollSpec:
            raise GameLifecycleError("AdvanceRollRequest spec must be a DiceRollSpec.")
        modifiers = _validate_movement_roll_modifiers(
            "AdvanceRollRequest roll_modifiers",
            self.roll_modifiers,
        )
        object.__setattr__(self, "roll_modifiers", modifiers)
        _validate_advance_roll_spec(
            self.spec,
            unit_instance_id=self.unit_instance_id,
            expression_modifier=sum(modifier.operand for modifier in modifiers),
        )
        if self.reroll_permission is not None:
            if type(self.reroll_permission) is not RerollPermission:
                raise GameLifecycleError(
                    "AdvanceRollRequest reroll_permission must be a RerollPermission."
                )
            if self.reroll_permission.owning_player_id != self.player_id:
                raise GameLifecycleError(
                    "AdvanceRollRequest reroll_permission owner must match player_id."
                )
            if self.reroll_permission.eligible_roll_type != self.spec.roll_type:
                raise GameLifecycleError(
                    "AdvanceRollRequest reroll_permission must target advance_roll."
                )

    @classmethod
    def for_unit(
        cls,
        *,
        request_id: str,
        game_id: str,
        battle_round: int,
        player_id: str,
        unit_instance_id: str,
        roll_modifiers: tuple[RollModifier, ...] = (),
        reroll_permission: RerollPermission | None = None,
    ) -> Self:
        modifiers = _validate_movement_roll_modifiers(
            "AdvanceRollRequest roll_modifiers",
            roll_modifiers,
        )
        return cls(
            request_id=request_id,
            game_id=game_id,
            battle_round=battle_round,
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            spec=DiceRollSpec(
                expression=DiceExpression(
                    quantity=1,
                    sides=6,
                    modifier=sum(modifier.operand for modifier in modifiers),
                ),
                reason=f"Advance roll for {unit_instance_id}",
                roll_type="advance_roll",
                actor_id=unit_instance_id,
            ),
            roll_modifiers=modifiers,
            reroll_permission=reroll_permission,
        )

    def to_payload(self) -> AdvanceRollRequestPayload:
        return {
            "request_id": self.request_id,
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "spec": self.spec.to_payload(),
            "roll_modifiers": [modifier.to_payload() for modifier in self.roll_modifiers],
            "reroll_permission": (
                None if self.reroll_permission is None else self.reroll_permission.to_payload()
            ),
        }

    @classmethod
    def from_payload(cls, payload: AdvanceRollRequestPayload) -> Self:
        reroll_permission_payload = payload["reroll_permission"]
        return cls(
            request_id=payload["request_id"],
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            spec=DiceRollSpec.from_payload(payload["spec"]),
            roll_modifiers=tuple(
                RollModifier.from_payload(modifier) for modifier in payload["roll_modifiers"]
            ),
            reroll_permission=(
                None
                if reroll_permission_payload is None
                else RerollPermission.from_payload(reroll_permission_payload)
            ),
        )


@dataclass(frozen=True, slots=True)
class AdvanceRollResult:
    request: AdvanceRollRequest
    roll_state: DiceRollState
    value: int

    def __post_init__(self) -> None:
        if type(self.request) is not AdvanceRollRequest:
            raise GameLifecycleError("AdvanceRollResult request must be an AdvanceRollRequest.")
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("AdvanceRollResult roll_state must be a DiceRollState.")
        if self.roll_state.original_result.spec != self.request.spec:
            raise GameLifecycleError("AdvanceRollResult roll_state spec must match request.")
        if self.value != self.roll_state.current_total:
            raise GameLifecycleError("AdvanceRollResult value must match roll_state total.")
        min_value = 1 + self.request.spec.expression.modifier
        max_value = self.request.spec.expression.sides + self.request.spec.expression.modifier
        if self.value < min_value or self.value > max_value:
            raise GameLifecycleError("AdvanceRollResult value must match request bounds.")

    @classmethod
    def from_roll_state(cls, *, request: AdvanceRollRequest, roll_state: DiceRollState) -> Self:
        return cls(request=request, roll_state=roll_state, value=roll_state.current_total)

    def to_payload(self) -> AdvanceRollResultPayload:
        return {
            "request": self.request.to_payload(),
            "roll_state": self.roll_state.to_payload(),
            "value": self.value,
        }

    @classmethod
    def from_payload(cls, payload: AdvanceRollResultPayload) -> Self:
        return cls(
            request=AdvanceRollRequest.from_payload(payload["request"]),
            roll_state=DiceRollState.from_payload(payload["roll_state"]),
            value=payload["value"],
        )


@dataclass(frozen=True, slots=True)
class MovementDiceRecord:
    player_id: str
    battle_round: int
    unit_instance_id: str
    movement_phase_action: MovementPhaseActionKind
    advance_roll: AdvanceRollResult

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("MovementDiceRecord player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("MovementDiceRecord battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("MovementDiceRecord unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "movement_phase_action",
            movement_phase_action_kind_from_token(self.movement_phase_action),
        )
        if self.movement_phase_action is not MovementPhaseActionKind.ADVANCE:
            raise GameLifecycleError("MovementDiceRecord currently supports only Advance dice.")
        if type(self.advance_roll) is not AdvanceRollResult:
            raise GameLifecycleError("MovementDiceRecord advance_roll must be AdvanceRollResult.")
        if self.advance_roll.request.player_id != self.player_id:
            raise GameLifecycleError("MovementDiceRecord advance_roll player_id drift.")
        if self.advance_roll.request.battle_round != self.battle_round:
            raise GameLifecycleError("MovementDiceRecord advance_roll battle_round drift.")
        if self.advance_roll.request.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError("MovementDiceRecord advance_roll unit_instance_id drift.")

    def to_payload(self) -> MovementDiceRecordPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "movement_phase_action": self.movement_phase_action.value,
            "advance_roll": self.advance_roll.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: MovementDiceRecordPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            movement_phase_action=movement_phase_action_kind_from_token(
                payload["movement_phase_action"]
            ),
            advance_roll=AdvanceRollResult.from_payload(payload["advance_roll"]),
        )


@dataclass(frozen=True, slots=True)
class AdvancedUnitState:
    player_id: str
    battle_round: int
    unit_instance_id: str
    movement_dice_record: MovementDiceRecord
    can_shoot: bool = False
    can_declare_charge: bool = False
    cleanup_point: str = _ADVANCED_UNIT_CLEANUP_POINT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("AdvancedUnitState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("AdvancedUnitState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("AdvancedUnitState unit_instance_id", self.unit_instance_id),
        )
        if type(self.movement_dice_record) is not MovementDiceRecord:
            raise GameLifecycleError(
                "AdvancedUnitState movement_dice_record must be MovementDiceRecord."
            )
        if self.movement_dice_record.player_id != self.player_id:
            raise GameLifecycleError("AdvancedUnitState movement_dice_record player_id drift.")
        if self.movement_dice_record.battle_round != self.battle_round:
            raise GameLifecycleError("AdvancedUnitState movement_dice_record battle_round drift.")
        if self.movement_dice_record.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError("AdvancedUnitState movement_dice_record unit drift.")
        object.__setattr__(
            self,
            "can_shoot",
            _validate_bool("AdvancedUnitState can_shoot", self.can_shoot),
        )
        object.__setattr__(
            self,
            "can_declare_charge",
            _validate_bool("AdvancedUnitState can_declare_charge", self.can_declare_charge),
        )
        object.__setattr__(
            self,
            "cleanup_point",
            _validate_identifier("AdvancedUnitState cleanup_point", self.cleanup_point),
        )
        if self.cleanup_point != _ADVANCED_UNIT_CLEANUP_POINT:
            raise GameLifecycleError("AdvancedUnitState cleanup_point must be end_of_turn.")

    def to_payload(self) -> AdvancedUnitStatePayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "movement_dice_record": self.movement_dice_record.to_payload(),
            "can_shoot": self.can_shoot,
            "can_declare_charge": self.can_declare_charge,
            "cleanup_point": self.cleanup_point,
        }

    @classmethod
    def from_payload(cls, payload: AdvancedUnitStatePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            movement_dice_record=MovementDiceRecord.from_payload(payload["movement_dice_record"]),
            can_shoot=payload["can_shoot"],
            can_declare_charge=payload["can_declare_charge"],
            cleanup_point=payload["cleanup_point"],
        )


@dataclass(frozen=True, slots=True)
class DesperateEscapeRequirement:
    requirement_id: str
    player_id: str
    battle_round: int
    unit_instance_id: str
    model_instance_id: str
    reasons: tuple[DesperateEscapeRequirementReason, ...]
    enemy_model_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requirement_id",
            _validate_identifier(
                "DesperateEscapeRequirement requirement_id",
                self.requirement_id,
            ),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DesperateEscapeRequirement player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("DesperateEscapeRequirement battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "DesperateEscapeRequirement unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "DesperateEscapeRequirement model_instance_id",
                self.model_instance_id,
            ),
        )
        if not self.model_instance_id.startswith(f"{self.unit_instance_id}:"):
            raise GameLifecycleError(
                "DesperateEscapeRequirement model_instance_id must belong to unit_instance_id."
            )
        object.__setattr__(
            self,
            "reasons",
            _validate_desperate_escape_reason_tuple(
                "DesperateEscapeRequirement reasons",
                self.reasons,
            ),
        )
        object.__setattr__(
            self,
            "enemy_model_ids",
            _validate_identifier_tuple(
                "DesperateEscapeRequirement enemy_model_ids",
                self.enemy_model_ids,
            ),
        )
        if (
            DesperateEscapeRequirementReason.ENEMY_MODEL_OVERFLIGHT in self.reasons
            and not self.enemy_model_ids
        ):
            raise GameLifecycleError(
                "DesperateEscapeRequirement enemy overflight requires enemy_model_ids."
            )

    def roll_spec(self) -> DiceRollSpec:
        return DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Desperate Escape roll for {self.model_instance_id}",
            roll_type=_DESPERATE_ESCAPE_ROLL_TYPE,
            actor_id=self.model_instance_id,
        )

    def to_payload(self) -> DesperateEscapeRequirementPayload:
        return {
            "requirement_id": self.requirement_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "model_instance_id": self.model_instance_id,
            "reasons": [reason.value for reason in self.reasons],
            "enemy_model_ids": list(self.enemy_model_ids),
        }

    @classmethod
    def from_payload(cls, payload: DesperateEscapeRequirementPayload) -> Self:
        return cls(
            requirement_id=payload["requirement_id"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            model_instance_id=payload["model_instance_id"],
            reasons=tuple(
                desperate_escape_requirement_reason_from_token(reason)
                for reason in payload["reasons"]
            ),
            enemy_model_ids=tuple(payload["enemy_model_ids"]),
        )


@dataclass(frozen=True, slots=True)
class DesperateEscapeRoll:
    requirement: DesperateEscapeRequirement
    roll_state: DiceRollState
    value: int
    roll_modifiers: tuple[RollModifier, ...] = ()

    def __post_init__(self) -> None:
        if type(self.requirement) is not DesperateEscapeRequirement:
            raise GameLifecycleError(
                "DesperateEscapeRoll requirement must be a DesperateEscapeRequirement."
            )
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("DesperateEscapeRoll roll_state must be a DiceRollState.")
        if self.roll_state.original_result.spec != self.requirement.roll_spec():
            raise GameLifecycleError("DesperateEscapeRoll roll_state spec must match requirement.")
        modifiers = tuple(self.roll_modifiers)
        for modifier in modifiers:
            if type(modifier) is not RollModifier:
                raise GameLifecycleError(
                    "DesperateEscapeRoll roll_modifiers must contain RollModifier values."
                )
        object.__setattr__(self, "roll_modifiers", modifiers)
        modified_value, _applied_modifier_ids = apply_roll_modifiers(
            self.roll_state.current_total,
            modifiers,
        )
        if self.value != modified_value:
            raise GameLifecycleError("DesperateEscapeRoll value must match modified total.")
        if type(self.value) is not int:
            raise GameLifecycleError("DesperateEscapeRoll value must be an integer.")

    @classmethod
    def from_roll_state(
        cls,
        *,
        requirement: DesperateEscapeRequirement,
        roll_state: DiceRollState,
        roll_modifiers: tuple[RollModifier, ...] = (),
    ) -> Self:
        value, _applied_modifier_ids = apply_roll_modifiers(
            roll_state.current_total,
            roll_modifiers,
        )
        return cls(
            requirement=requirement,
            roll_state=roll_state,
            value=value,
            roll_modifiers=roll_modifiers,
        )

    @property
    def is_failed(self) -> bool:
        return self.value <= 2

    def to_payload(self) -> DesperateEscapeRollPayload:
        return {
            "requirement": self.requirement.to_payload(),
            "roll_state": self.roll_state.to_payload(),
            "roll_modifiers": [modifier.to_payload() for modifier in self.roll_modifiers],
            "value": self.value,
        }

    @classmethod
    def from_payload(cls, payload: DesperateEscapeRollPayload) -> Self:
        return cls(
            requirement=DesperateEscapeRequirement.from_payload(payload["requirement"]),
            roll_state=DiceRollState.from_payload(payload["roll_state"]),
            roll_modifiers=tuple(
                RollModifier.from_payload(modifier) for modifier in payload["roll_modifiers"]
            ),
            value=payload["value"],
        )


@dataclass(frozen=True, slots=True)
class FellBackUnitState:
    player_id: str
    battle_round: int
    unit_instance_id: str
    desperate_escape_rolls: tuple[DesperateEscapeRoll, ...] = ()
    can_shoot: bool = False
    can_declare_charge: bool = False
    cleanup_point: str = _FELL_BACK_UNIT_CLEANUP_POINT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("FellBackUnitState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("FellBackUnitState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("FellBackUnitState unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "desperate_escape_rolls",
            _validate_desperate_escape_roll_tuple(
                "FellBackUnitState desperate_escape_rolls",
                self.desperate_escape_rolls,
            ),
        )
        for roll in self.desperate_escape_rolls:
            requirement = roll.requirement
            if requirement.player_id != self.player_id:
                raise GameLifecycleError("FellBackUnitState roll player_id drift.")
            if requirement.battle_round != self.battle_round:
                raise GameLifecycleError("FellBackUnitState roll battle_round drift.")
            if requirement.unit_instance_id != self.unit_instance_id:
                raise GameLifecycleError("FellBackUnitState roll unit drift.")
        object.__setattr__(
            self,
            "can_shoot",
            _validate_bool("FellBackUnitState can_shoot", self.can_shoot),
        )
        object.__setattr__(
            self,
            "can_declare_charge",
            _validate_bool("FellBackUnitState can_declare_charge", self.can_declare_charge),
        )
        object.__setattr__(
            self,
            "cleanup_point",
            _validate_identifier("FellBackUnitState cleanup_point", self.cleanup_point),
        )
        if self.cleanup_point != _FELL_BACK_UNIT_CLEANUP_POINT:
            raise GameLifecycleError("FellBackUnitState cleanup_point must be end_of_turn.")

    def to_payload(self) -> FellBackUnitStatePayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "desperate_escape_rolls": [roll.to_payload() for roll in self.desperate_escape_rolls],
            "can_shoot": self.can_shoot,
            "can_declare_charge": self.can_declare_charge,
            "cleanup_point": self.cleanup_point,
        }

    @classmethod
    def from_payload(cls, payload: FellBackUnitStatePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            desperate_escape_rolls=tuple(
                DesperateEscapeRoll.from_payload(roll) for roll in payload["desperate_escape_rolls"]
            ),
            can_shoot=payload["can_shoot"],
            can_declare_charge=payload["can_declare_charge"],
            cleanup_point=payload["cleanup_point"],
        )


@dataclass(frozen=True, slots=True)
class MovementUnitSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("MovementUnitSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("MovementUnitSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("MovementUnitSelection unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("MovementUnitSelection request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("MovementUnitSelection result_id", self.result_id),
        )

    def to_payload(self) -> MovementUnitSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "request_id": self.request_id,
            "result_id": self.result_id,
        }

    @classmethod
    def from_payload(cls, payload: MovementUnitSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
        )


@dataclass(frozen=True, slots=True)
class PendingMovementActionSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    movement_phase_action: MovementPhaseActionKind
    movement_mode: MovementMode
    fall_back_mode: FallBackModeKind | None
    request_id: str
    result_id: str
    selected_option_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("PendingMovementActionSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "PendingMovementActionSelection battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "PendingMovementActionSelection unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "movement_phase_action",
            movement_phase_action_kind_from_token(self.movement_phase_action),
        )
        object.__setattr__(
            self,
            "movement_mode",
            movement_mode_from_token(self.movement_mode),
        )
        if self.fall_back_mode is not None:
            object.__setattr__(
                self,
                "fall_back_mode",
                fall_back_mode_kind_from_token(self.fall_back_mode),
            )
        if (
            self.movement_phase_action is MovementPhaseActionKind.FALL_BACK
            and self.fall_back_mode is None
        ):
            raise GameLifecycleError("Pending Fall Back action requires fall_back_mode.")
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("PendingMovementActionSelection request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("PendingMovementActionSelection result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "selected_option_id",
            _validate_identifier(
                "PendingMovementActionSelection selected_option_id",
                self.selected_option_id,
            ),
        )

    @classmethod
    def from_result(
        cls,
        *,
        result: DecisionResult,
        player_id: str,
        battle_round: int,
        unit_instance_id: str,
        movement_phase_action: MovementPhaseActionKind,
        movement_mode: MovementMode,
        fall_back_mode: FallBackModeKind | None,
    ) -> Self:
        return cls(
            player_id=player_id,
            battle_round=battle_round,
            unit_instance_id=unit_instance_id,
            movement_phase_action=movement_phase_action,
            movement_mode=movement_mode,
            fall_back_mode=fall_back_mode,
            request_id=result.request_id,
            result_id=result.result_id,
            selected_option_id=result.selected_option_id,
        )

    def to_decision_result(self) -> DecisionResult:
        payload: dict[str, JsonValue] = {
            "movement_phase_action": self.movement_phase_action.value,
            "unit_instance_id": self.unit_instance_id,
            "movement_mode": self.movement_mode.value,
        }
        if self.fall_back_mode is not None:
            payload["fall_back_mode"] = self.fall_back_mode.value
        return DecisionResult(
            result_id=self.result_id,
            request_id=self.request_id,
            decision_type=SELECT_MOVEMENT_ACTION_DECISION_TYPE,
            actor_id=self.player_id,
            selected_option_id=self.selected_option_id,
            payload=validate_json_value(payload),
        )

    def to_payload(self) -> PendingMovementActionSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "movement_phase_action": self.movement_phase_action.value,
            "movement_mode": self.movement_mode.value,
            "fall_back_mode": None if self.fall_back_mode is None else self.fall_back_mode.value,
            "request_id": self.request_id,
            "result_id": self.result_id,
            "selected_option_id": self.selected_option_id,
        }

    @classmethod
    def from_payload(cls, payload: PendingMovementActionSelectionPayload) -> Self:
        fall_back_mode_payload = payload["fall_back_mode"]
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            movement_phase_action=movement_phase_action_kind_from_token(
                payload["movement_phase_action"]
            ),
            movement_mode=movement_mode_from_token(payload["movement_mode"]),
            fall_back_mode=None
            if fall_back_mode_payload is None
            else fall_back_mode_kind_from_token(fall_back_mode_payload),
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            selected_option_id=payload["selected_option_id"],
        )


@dataclass(frozen=True, slots=True)
class DisembarkCandidate:
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    disembark_mode: DisembarkModeKind
    transport_movement_status: TransportMovementStatus
    restriction_overrides: tuple[TransportRestrictionOverride, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DisembarkCandidate player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("DisembarkCandidate battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "DisembarkCandidate unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "DisembarkCandidate transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "disembark_mode",
            disembark_mode_kind_from_token(self.disembark_mode),
        )
        object.__setattr__(
            self,
            "transport_movement_status",
            transport_movement_status_from_token(self.transport_movement_status),
        )
        object.__setattr__(
            self,
            "restriction_overrides",
            _validate_transport_restriction_override_tuple(
                "DisembarkCandidate restriction_overrides",
                self.restriction_overrides,
            ),
        )


@dataclass(frozen=True, slots=True)
class MovementDistanceRecord:
    unit_instance_id: str
    maximum_model_distance_inches: float
    maximum_model_horizontal_distance_inches: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("MovementDistanceRecord unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "maximum_model_distance_inches",
            _validate_non_negative_finite_number(
                "MovementDistanceRecord maximum_model_distance_inches",
                self.maximum_model_distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "maximum_model_horizontal_distance_inches",
            _validate_non_negative_finite_number(
                "MovementDistanceRecord maximum_model_horizontal_distance_inches",
                self.maximum_model_horizontal_distance_inches,
            ),
        )
        if self.maximum_model_horizontal_distance_inches > self.maximum_model_distance_inches:
            raise GameLifecycleError(
                "MovementDistanceRecord horizontal distance cannot exceed total distance."
            )

    def to_payload(self) -> MovementDistanceRecordPayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "maximum_model_distance_inches": self.maximum_model_distance_inches,
            "maximum_model_horizontal_distance_inches": (
                self.maximum_model_horizontal_distance_inches
            ),
        }

    @classmethod
    def from_payload(cls, payload: MovementDistanceRecordPayload) -> Self:
        return cls(
            unit_instance_id=payload["unit_instance_id"],
            maximum_model_distance_inches=payload["maximum_model_distance_inches"],
            maximum_model_horizontal_distance_inches=payload[
                "maximum_model_horizontal_distance_inches"
            ],
        )
