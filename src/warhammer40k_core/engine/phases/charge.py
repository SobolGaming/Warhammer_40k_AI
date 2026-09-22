from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
    movement_mode_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine import unit_move_completed_hooks as _umc
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.aircraft import AircraftMovementPolicy
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    PlacementError,
)
from warhammer40k_core.engine.charge_declaration_hooks import (
    DECLINE_CHARGE_DECLARATION_GRANT_OPTION_ID,
    SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE,
    ChargeDeclarationContext,
    ChargeDeclarationGrant,
    ChargeDeclarationGrantPayload,
    ChargeDeclarationHookRegistry,
)
from warhammer40k_core.engine.charge_eligibility import (
    charge_after_fall_back_allowed_by_effects as _charge_after_fall_back_allowed_by_effects,
)
from warhammer40k_core.engine.charge_eligibility import (
    charge_forbidden_by_effects as _charge_forbidden_by_effects,
)
from warhammer40k_core.engine.charge_eligibility import (
    charge_unit_ineligibility_reason as _charge_unit_ineligibility_reason,
)
from warhammer40k_core.engine.charge_eligibility import (
    legal_charging_unit_ids as _legal_charging_unit_ids,
)
from warhammer40k_core.engine.charge_endpoints import (
    ChargeEndpointWitness as ChargeEndpointWitness,
)
from warhammer40k_core.engine.charge_endpoints import (
    ChargeEndpointWitnessPayload as ChargeEndpointWitnessPayload,
)
from warhammer40k_core.engine.charge_endpoints import (
    _charge_endpoint_violation_code as _charge_endpoint_violation_code,
)
from warhammer40k_core.engine.charge_endpoints import (
    _charge_endpoint_witness as _charge_endpoint_witness,
)
from warhammer40k_core.engine.charge_move_event_schema import (
    CHARGE_MOVE_COMPLETED_OPTIONAL_PAYLOAD_KEYS,
    CHARGE_MOVE_COMPLETED_PAYLOAD_KEYS,
    CHARGE_MOVE_COMPLETED_STATUS,
    CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _charge_move_transition_batch as _charge_move_transition_batch,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _closest_distance_between_model_groups as _closest_distance_between_model_groups,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _enemy_geometry_models_for_player as _enemy_geometry_models_for_player,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _friendly_geometry_models_for_charge_path as _friendly_geometry_models_for_charge_path,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _friendly_vehicle_monster_model_ids as _friendly_vehicle_monster_model_ids,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _geometry_models_for_unit as _geometry_models_for_unit,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _geometry_models_for_unit_placement as _geometry_models_for_unit_placement,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _model_groups_are_engaged as _model_groups_are_engaged,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _terrain_volumes_for_features as _terrain_volumes_for_features,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _validate_charge_witness_matches_unit as _validate_charge_witness_matches_unit,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _validate_distance_map as _validate_distance_map,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _validate_json_object as _validate_json_object,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _validate_path_validation_results as _validate_path_validation_results,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _validate_terrain_path_legality_results as _validate_terrain_path_legality_results,
)
from warhammer40k_core.engine.charge_move_resolution import (
    ChargeMoveResolution as ChargeMoveResolution,
)
from warhammer40k_core.engine.charge_move_resolution import (
    resolve_charge_move as resolve_charge_move,
)
from warhammer40k_core.engine.charge_movement_source import validate_charge_witness_for_proposal
from warhammer40k_core.engine.charge_phase_state import (
    ChargePhaseState as ChargePhaseState,
)
from warhammer40k_core.engine.charge_phase_state import (
    ChargePhaseStatePayload as ChargePhaseStatePayload,
)
from warhammer40k_core.engine.charge_phase_state import (
    ChargingUnitSelection as ChargingUnitSelection,
)
from warhammer40k_core.engine.charge_phase_state import (
    ChargingUnitSelectionPayload as ChargingUnitSelectionPayload,
)
from warhammer40k_core.engine.charge_phase_state import (
    _validate_identifier_tuple,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.charge_required_targets import (
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
)
from warhammer40k_core.engine.charge_roll_flow import (
    _apply_charge_roll_reroll_decision,
    _resolve_charge_roll,
    _resolve_charge_roll_state,
)
from warhammer40k_core.engine.charge_targets import (
    charge_target_candidates as _charge_target_candidates,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_resources import (
    apply_faction_resource_spend_effect,
    faction_resource_result_enriched_payload,
    resolve_faction_resource_refund_roll,
)
from warhammer40k_core.engine.move_completion_rule_hooks import MoveCompletionRuleRegistry
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
    ProposalValidationResult,
    proposal_kind_from_token,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.phases import charge_modifier_ignore as _modifier_ignore
from warhammer40k_core.engine.phases.charge_move_completed_hooks import (
    validate_charge_move_completed_hook_provider,
)
from warhammer40k_core.engine.phases.charge_proposal_flow import (
    _apply_charge_move_proposal_decision,
    _request_charge_move_proposal_retry,
)
from warhammer40k_core.engine.phases.charge_proposal_flow import (
    invalid_charge_move_proposal_status as invalid_charge_move_proposal_status,
)
from warhammer40k_core.engine.physical_engagement import (
    scenario_physically_engaged_enemy_rules_unit_ids,
)
from warhammer40k_core.engine.physical_proposal_validation import (
    physical_proposal_invalid_status as _reject_invalid_charge_proposal,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    placed_alive_rules_unit_views,
    rules_unit_view_by_id,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.target_restriction_hooks import (
    ChargeTargetRestrictionHookRegistry,
)
from warhammer40k_core.geometry.pathing import (
    PathWitness,
    PathWitnessPayload,
)
from warhammer40k_core.geometry.pose import GeometryError

COMPLETE_CHARGE_PHASE_OPTION_ID = _modifier_ignore.COMPLETE_CHARGE_PHASE_OPTION_ID
SELECT_CHARGING_UNIT_DECISION_TYPE = _modifier_ignore.SELECT_CHARGING_UNIT_DECISION_TYPE

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.reaction_queue import ReactionQueue
    from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex


CHARGE_MOVE_ACTION = "charge_move"
FIGHTS_FIRST_CHARGE_EFFECT_KIND = "charge_grants_fights_first"
CHARGE_AFTER_FALL_BACK_EFFECT_KIND = "charge_after_fall_back_allowed"
_CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS = CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS
_CHARGE_MOVE_INVALID_STATUS = "charge_move_invalid"
_CHARGE_MOVE_DECLINED_STATUS = "charge_move_declined"
_CHARGE_MOVE_COMPLETED_STATUS = CHARGE_MOVE_COMPLETED_STATUS


def _empty_ability_indexes() -> Mapping[str, AbilityCatalogIndex]:
    return MappingProxyType({})


def _default_stratagem_index() -> StratagemCatalogIndex:
    from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index

    return eleventh_edition_stratagem_index()


def _empty_stratagem_cost_modifier_registry() -> StratagemCostModifierRegistry:
    from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry

    return StratagemCostModifierRegistry.empty()


class ChargeMoveProposalPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    unit_instance_id: str
    movement_phase_action: str
    movement_mode: str
    charge_target_unit_instance_ids: list[str]
    witness: NotRequired[object]


@dataclass(frozen=True, slots=True)
class ChargeMoveProposal:
    proposal_request_id: str
    proposal_kind: ProposalKind
    unit_instance_id: str
    movement_phase_action: str
    movement_mode: MovementMode
    charge_target_unit_instance_ids: tuple[str, ...]
    witness: PathWitness | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_request_id",
            _validate_identifier(
                "ChargeMoveProposal proposal_request_id", self.proposal_request_id
            ),
        )
        object.__setattr__(self, "proposal_kind", _charge_proposal_kind(self.proposal_kind))
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("ChargeMoveProposal unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "movement_phase_action",
            _validate_charge_move_action(self.movement_phase_action),
        )
        object.__setattr__(self, "movement_mode", _charge_movement_mode(self.movement_mode))
        object.__setattr__(
            self,
            "charge_target_unit_instance_ids",
            _validate_identifier_tuple(
                "ChargeMoveProposal charge_target_unit_instance_ids",
                self.charge_target_unit_instance_ids,
            ),
        )
        if self.witness is not None and type(self.witness) is not PathWitness:
            raise GameLifecycleError("ChargeMoveProposal witness must be a PathWitness.")

    @property
    def is_no_move_choice(self) -> bool:
        return not self.charge_target_unit_instance_ids

    def validation_result_for_request(
        self,
        request: MovementProposalRequest,
    ) -> ProposalValidationResult:
        if type(request) is not MovementProposalRequest:
            raise GameLifecycleError("Charge proposal validation requires a request.")
        if self.proposal_request_id != request.request_id:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="stale_proposal_request",
                message="Charge Move proposal request_id does not match the pending request.",
                field="proposal_request_id",
                status="stale",
            )
        if request.proposal_kind is not ProposalKind.CHARGE_MOVE:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_kind_drift",
                message="Pending request is not a Charge Move proposal.",
                field="proposal_kind",
            )
        if self.proposal_kind is not request.proposal_kind:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_kind_drift",
                message="Charge Move proposal kind does not match the pending request.",
                field="proposal_kind",
            )
        if self.unit_instance_id != request.unit_instance_id:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_unit_drift",
                message="Charge Move proposal unit does not match the pending request.",
                field="unit_instance_id",
            )
        if request.movement_phase_action != CHARGE_MOVE_ACTION:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_action_drift",
                message="Pending request does not carry Charge Move action context.",
                field="movement_phase_action",
            )
        if self.movement_phase_action != request.movement_phase_action:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_action_drift",
                message="Charge Move proposal action does not match the pending request.",
                field="movement_phase_action",
            )
        context = _proposal_context(request)
        if self.movement_mode.value != _payload_string(context, key="movement_mode"):
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_movement_mode_drift",
                message="Charge Move proposal mode does not match the pending request.",
                field="movement_mode",
            )
        reachable_target_ids = set(
            _payload_identifier_list(context, key="reachable_target_unit_instance_ids")
        )
        required_target_ids = set(
            _payload_optional_identifier_list(
                context,
                key=CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
            )
        )
        selected_target_ids = set(self.charge_target_unit_instance_ids)
        if selected_target_ids - reachable_target_ids:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="charge_target_not_reachable",
                message="Charge Move selected a target that is not currently reachable.",
                field="charge_target_unit_instance_ids",
            )
        if self.is_no_move_choice:
            if required_target_ids:
                return ProposalValidationResult.invalid(
                    proposal_request_id=request.request_id,
                    proposal_kind=request.proposal_kind,
                    violation_code="charge_required_target_not_selected",
                    message="Charge Move must select a required reachable target.",
                    field="charge_target_unit_instance_ids",
                )
            if self.witness is not None:
                return ProposalValidationResult.invalid(
                    proposal_request_id=request.request_id,
                    proposal_kind=request.proposal_kind,
                    violation_code="no_move_witness_forbidden",
                    message="Charge no-move submissions must not include a witness.",
                    field="witness",
                )
            return ProposalValidationResult.valid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
            )
        if not required_target_ids.issubset(selected_target_ids):
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="charge_required_target_not_selected",
                message="Charge Move selected targets did not include every required target.",
                field="charge_target_unit_instance_ids",
            )
        if self.witness is None:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="charge_move_witness_required",
                message="Charge Move target submissions require a PathWitness.",
                field="witness",
            )
        return ProposalValidationResult.valid(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
        )

    def to_payload(self) -> ChargeMoveProposalPayload:
        payload: ChargeMoveProposalPayload = {
            "proposal_request_id": self.proposal_request_id,
            "proposal_kind": self.proposal_kind.value,
            "unit_instance_id": self.unit_instance_id,
            "movement_phase_action": self.movement_phase_action,
            "movement_mode": self.movement_mode.value,
            "charge_target_unit_instance_ids": list(self.charge_target_unit_instance_ids),
        }
        if self.witness is not None:
            payload["witness"] = self.witness.to_payload()
        return payload

    @classmethod
    def from_payload(cls, payload: ChargeMoveProposalPayload) -> Self:
        witness_payload = payload.get("witness")
        return cls(
            proposal_request_id=payload["proposal_request_id"],
            proposal_kind=_proposal_kind_from_token(payload["proposal_kind"]),
            unit_instance_id=payload["unit_instance_id"],
            movement_phase_action=payload["movement_phase_action"],
            movement_mode=_movement_mode_from_token(payload["movement_mode"]),
            charge_target_unit_instance_ids=tuple(payload["charge_target_unit_instance_ids"]),
            witness=None
            if witness_payload is None
            else PathWitness.from_payload(cast(PathWitnessPayload, witness_payload)),
        )


@dataclass(frozen=True, slots=True)
class ChargePhaseHandler:
    move_completion_rule_registry: MoveCompletionRuleRegistry = field(
        default_factory=lambda: MoveCompletionRuleRegistry(())
    )
    ruleset_descriptor: RulesetDescriptor | None = None
    stratagem_index: StratagemCatalogIndex = field(default_factory=_default_stratagem_index)
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry = field(
        default_factory=_empty_stratagem_cost_modifier_registry
    )
    charge_declaration_hooks: ChargeDeclarationHookRegistry = field(
        default_factory=ChargeDeclarationHookRegistry.empty
    )
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry = field(
        default_factory=ChargeTargetRestrictionHookRegistry.empty
    )
    unit_move_completed_mortal_wound_hooks: _umc.UnitMoveCompletedMortalWoundHookRegistry = field(
        default_factory=_umc.UnitMoveCompletedMortalWoundHookRegistry.empty
    )
    unit_move_completed_battle_shock_hooks: _umc.UnitMoveCompletedBattleShockHookRegistry = field(
        default_factory=_umc.UnitMoveCompletedBattleShockHookRegistry.empty
    )
    battle_shock_hooks: BattleShockHookRegistry = field(
        default_factory=BattleShockHookRegistry.empty
    )
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] = field(
        default_factory=_empty_ability_indexes
    )
    runtime_modifier_registry: RuntimeModifierRegistry = field(
        default_factory=RuntimeModifierRegistry.empty
    )

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
        from warhammer40k_core.engine.stratagems import StratagemCatalogIndex

        if (
            self.ruleset_descriptor is not None
            and type(self.ruleset_descriptor) is not RulesetDescriptor
        ):
            raise GameLifecycleError(
                "ChargePhaseHandler ruleset_descriptor must be a RulesetDescriptor."
            )
        if type(self.stratagem_index) is not StratagemCatalogIndex:
            raise GameLifecycleError("ChargePhaseHandler stratagem_index must be an index.")
        if type(self.stratagem_cost_modifier_registry) is not StratagemCostModifierRegistry:
            raise GameLifecycleError(
                "ChargePhaseHandler stratagem_cost_modifier_registry must be a registry."
            )
        if type(self.charge_declaration_hooks) is not ChargeDeclarationHookRegistry:
            raise GameLifecycleError(
                "ChargePhaseHandler charge_declaration_hooks must be a registry."
            )
        if type(self.charge_target_restriction_hooks) is not ChargeTargetRestrictionHookRegistry:
            raise GameLifecycleError(
                "ChargePhaseHandler charge_target_restriction_hooks must be a registry."
            )
        validate_charge_move_completed_hook_provider(self)
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            _validate_ability_index_mapping(self.ability_indexes_by_player_id),
        )
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError(
                "ChargePhaseHandler runtime_modifier_registry must be a registry."
            )

    @property
    def phase(self) -> BattlePhase:
        return BattlePhase.CHARGE

    def ability_index_for_player(self, player_id: str) -> AbilityCatalogIndex:
        return _ability_index_for_player(
            self.ability_indexes_by_player_id,
            player_id=player_id,
        )

    def begin_phase(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus:
        from warhammer40k_core.engine.charge_phase_flow import begin_phase

        return begin_phase(self, state=state, decisions=decisions, reaction_queue=reaction_queue)

    def apply_decision(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> LifecycleStatus | None:
        if result.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE:
            return _apply_charging_unit_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                charge_declaration_hooks=self.charge_declaration_hooks,
                ability_index=_ability_index_for_player(
                    self.ability_indexes_by_player_id,
                    player_id=_active_player_id(state),
                ),
                runtime_modifier_registry=self.runtime_modifier_registry,
                charge_target_restriction_hooks=self.charge_target_restriction_hooks,
            )
        if result.decision_type == SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE:
            return _apply_charge_declaration_grant_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                charge_declaration_hooks=self.charge_declaration_hooks,
                ability_index=_ability_index_for_player(
                    self.ability_indexes_by_player_id,
                    player_id=_active_player_id(state),
                ),
                runtime_modifier_registry=self.runtime_modifier_registry,
                charge_target_restriction_hooks=self.charge_target_restriction_hooks,
            )
        if result.decision_type == DICE_REROLL_DECISION_TYPE:
            reroll_record = decisions.record_for_result(result)
            if _umc.is_unit_move_completed_battle_shock_reroll_request(reroll_record.request):
                return _umc.apply_unit_move_completed_battle_shock_reroll_decision(
                    state=state,
                    result=result,
                    decisions=decisions,
                    battle_shock_hooks=self.battle_shock_hooks,
                )
            return _apply_charge_roll_reroll_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                ability_index=self.ability_index_for_player(_active_player_id(state)),
                runtime_modifier_registry=self.runtime_modifier_registry,
                charge_target_restriction_hooks=self.charge_target_restriction_hooks,
            )
        if result.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            return _apply_charge_move_proposal_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                charge_target_restriction_hooks=self.charge_target_restriction_hooks,
                ability_index=_ability_index_for_player(
                    self.ability_indexes_by_player_id,
                    player_id=_active_player_id(state),
                ),
            )
        raise GameLifecycleError("Charge phase received unsupported decision type.")


def _complete_charge_phase_or_request_heroic_intervention(
    *,
    handler: ChargePhaseHandler,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
) -> LifecycleStatus:
    from warhammer40k_core.engine.phases.charge_reactions import (
        request_end_opponent_charge_heroic_intervention_if_available,
    )

    reaction_status = request_end_opponent_charge_heroic_intervention_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        stratagem_index=handler.stratagem_index,
        stratagem_cost_modifier_registry=handler.stratagem_cost_modifier_registry,
    )
    if reaction_status is not None:
        return reaction_status
    payload = _charge_phase_status_payload(
        state=state,
        phase_body_status=_modifier_ignore.COMPLETE_CHARGE_PHASE_STATUS,
    )
    decisions.event_log.append("charge_phase_completed", payload)
    return LifecycleStatus.advanced(
        stage=GameLifecycleStage.BATTLE,
        payload=payload,
    )


def invalid_charging_unit_selection_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> LifecycleStatus | None:
    invalid_status = _invalid_charging_unit_finite_decision_status(
        state=state,
        request=request,
        result=result,
    )
    if invalid_status is not None:
        return invalid_status
    charge_state = state.charge_phase_state
    if charge_state is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Charging unit selection has no active charge phase state.",
            payload={
                "invalid_reason": "invalid_charging_unit_result",
                "field": "charge_phase_state",
            },
        )
    current_legal_ids = _legal_charging_unit_ids(
        state=state,
        charge_state=charge_state,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )
    payload = _decision_payload_object(result.payload)
    if result.selected_option_id == COMPLETE_CHARGE_PHASE_OPTION_ID:
        submitted_skipped = _payload_identifier_list(payload, key="skipped_unit_ids")
        if submitted_skipped != current_legal_ids:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Charge phase completion skipped units no longer match legal units.",
                payload={
                    "invalid_reason": "invalid_charging_unit_result",
                    "field": "skipped_unit_ids",
                },
            )
        return None
    selected_unit_id = _payload_string(payload, key="unit_instance_id")
    if selected_unit_id not in current_legal_ids:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Charging unit selection is no longer legal.",
            payload={
                "invalid_reason": "invalid_charging_unit_result",
                "field": "unit_instance_id",
            },
        )
    current_options = _modifier_ignore.charging_unit_options_with_modifier_ignore_choices(
        state=state,
        unit_ids=current_legal_ids,
        include_complete=True,
        ruleset_descriptor=ruleset_descriptor,
        ability_index=ability_index,
        runtime_modifier_registry=runtime_modifier_registry,
        active_player_id=_active_player_id(state),
        unit_lookup=_unit_by_id,
        target_candidate_provider=_charge_target_candidates,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )
    return _modifier_ignore.invalid_charge_modifier_ignore_context_status(
        state=state,
        result=result,
        current_options=current_options,
    )


def invalid_charge_declaration_grant_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    charge_declaration_hooks: ChargeDeclarationHookRegistry,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    if request.decision_type != SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE:
        raise GameLifecycleError(
            "Charge declaration grant prevalidation received unsupported decision_type."
        )
    try:
        result.validate_for_request(request)
    except DecisionError as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Charge declaration grant result is malformed.",
            payload={
                "invalid_reason": "invalid_charge_declaration_grant_result",
                "detail": str(exc),
            },
        )
    charge_state = state.charge_phase_state
    if charge_state is None or charge_state.active_selection is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Charge declaration grant has no active selection.",
            payload={
                "invalid_reason": "invalid_charge_declaration_grant_result",
                "field": "charge_phase_state",
            },
        )
    selection = charge_state.active_selection
    ineligibility_reason = _charge_unit_ineligibility_reason(
        state=state,
        unit_instance_id=selection.unit_instance_id,
        ruleset_descriptor=ruleset_descriptor,
        charge_state=charge_state,
        ignore_already_selected=True,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )
    if ineligibility_reason is not None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Charge declaration grant source is no longer eligible to declare.",
            payload={
                "invalid_reason": "invalid_charge_declaration_grant_result",
                "field": "eligibility_context",
            },
        )
    payload = _decision_payload_object(result.payload)
    if _payload_string(payload, key="unit_instance_id") != selection.unit_instance_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Charge declaration grant unit drifted.",
            payload={
                "invalid_reason": "invalid_charge_declaration_grant_result",
                "field": "unit_instance_id",
            },
        )
    if result.selected_option_id == DECLINE_CHARGE_DECLARATION_GRANT_OPTION_ID:
        return None
    selected_grants = _selected_charge_declaration_grants_from_payload(
        cast(dict[str, JsonValue], payload)
    )
    try:
        _validate_selected_charge_declaration_grants(
            state=state,
            selection=selection,
            registry=charge_declaration_hooks,
            selected_grants=selected_grants,
        )
    except GameLifecycleError as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Charge declaration grant is no longer legal.",
            payload={
                "invalid_reason": "invalid_charge_declaration_grant_result",
                "detail": str(exc),
            },
        )
    return None


def _apply_charging_unit_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    charge_declaration_hooks: ChargeDeclarationHookRegistry,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    _validate_charge_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Charging unit selection actor must be the active player.")
    charge_state = state.charge_phase_state
    if charge_state is None:
        raise GameLifecycleError("Charging unit selection requires charge_phase_state.")
    if result.selected_option_id == COMPLETE_CHARGE_PHASE_OPTION_ID:
        payload = _decision_payload_object(result.payload)
        skipped_unit_ids = _payload_identifier_list(payload, key="skipped_unit_ids")
        state.replace_charge_phase_state(
            charge_state.with_phase_complete(skipped_unit_ids=skipped_unit_ids)
        )
        decisions.event_log.append(
            "charge_phase_completion_declared",
            _charge_phase_status_payload(
                state=state,
                phase_body_status=_modifier_ignore.COMPLETE_CHARGE_PHASE_STATUS,
                skipped_unit_ids=skipped_unit_ids,
            ),
        )
        return None

    payload = _decision_payload_object(result.payload)
    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    legal_unit_ids = _legal_charging_unit_ids(
        state=state,
        charge_state=charge_state,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )
    if unit_instance_id not in legal_unit_ids:
        raise GameLifecycleError("Charging unit selection is not currently legal.")
    _modifier_ignore.record_charge_modifier_ignore_selection(
        state=state,
        decisions=decisions,
        result=result,
        unit_instance_id=unit_instance_id,
    )
    from warhammer40k_core.engine.take_to_the_skies import flight_selection

    selection = ChargingUnitSelection(
        take_to_the_skies=flight_selection(result.payload),
        player_id=active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    state.replace_charge_phase_state(charge_state.with_unit_selection(selection))
    decisions.event_log.append(
        "charging_unit_selected",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.CHARGE.value,
                "active_player_id": active_player_id,
                "unit_instance_id": unit_instance_id,
                "source_decision_request_id": result.request_id,
                "source_decision_result_id": result.result_id,
            }
        ),
    )
    grant_status = _request_charge_declaration_grant_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=charge_declaration_hooks,
    )
    if grant_status is not None:
        return grant_status
    return _resolve_charge_roll(
        state=state,
        selection=selection,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        ability_index=ability_index,
        runtime_modifier_registry=runtime_modifier_registry,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )


def _request_charge_declaration_grant_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    selection: ChargingUnitSelection,
    registry: ChargeDeclarationHookRegistry,
) -> LifecycleStatus | None:
    if type(selection) is not ChargingUnitSelection:
        raise GameLifecycleError("Charge declaration grant request requires a selection.")
    if type(registry) is not ChargeDeclarationHookRegistry:
        raise GameLifecycleError("Charge declaration grant request requires a registry.")
    context = ChargeDeclarationContext(
        state=state,
        player_id=selection.player_id,
        battle_round=state.battle_round,
        unit_instance_id=selection.unit_instance_id,
        selection_request_id=selection.request_id,
        selection_result_id=selection.result_id,
    )
    grants = registry.grants_for(context)
    if not grants:
        return None
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE,
        actor_id=selection.player_id,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.CHARGE.value,
                "active_player_id": selection.player_id,
                "unit_instance_id": selection.unit_instance_id,
                "source_decision_request_id": selection.request_id,
                "source_decision_result_id": selection.result_id,
                "available_charge_declaration_grants": [grant.to_payload() for grant in grants],
            }
        ),
        options=_charge_declaration_grant_options(selection=selection, grants=grants),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "charge_declaration_grant_decision_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.CHARGE.value,
                "active_player_id": selection.player_id,
                "unit_instance_id": selection.unit_instance_id,
                "request_id": request.request_id,
                "source_decision_request_id": selection.request_id,
                "source_decision_result_id": selection.result_id,
                "available_charge_declaration_grants": [grant.to_payload() for grant in grants],
                "phase_body_status": "charge_declaration_grant_decision_pending",
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.CHARGE.value,
            "phase_body_status": "charge_declaration_grant_decision_pending",
            "battle_round": state.battle_round,
            "active_player_id": selection.player_id,
            "unit_instance_id": selection.unit_instance_id,
            "decision_type": request.decision_type,
        },
    )


def _charge_declaration_grant_options(
    *,
    selection: ChargingUnitSelection,
    grants: tuple[ChargeDeclarationGrant, ...],
) -> tuple[DecisionOption, ...]:
    options = [
        DecisionOption(
            option_id=DECLINE_CHARGE_DECLARATION_GRANT_OPTION_ID,
            label="Decline Charge Declaration Grant",
            payload=validate_json_value(
                {
                    "submission_kind": SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE,
                    "unit_instance_id": selection.unit_instance_id,
                    "source_decision_request_id": selection.request_id,
                    "source_decision_result_id": selection.result_id,
                    "selected_charge_declaration_grants": [],
                }
            ),
        )
    ]
    for grant in grants:
        options.append(
            DecisionOption(
                option_id=grant.hook_id,
                label=grant.label,
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE,
                        "unit_instance_id": selection.unit_instance_id,
                        "source_decision_request_id": selection.request_id,
                        "source_decision_result_id": selection.result_id,
                        "selected_charge_declaration_grants": [grant.to_payload()],
                    }
                ),
            )
        )
    return tuple(options)


def _apply_charge_declaration_grant_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    charge_declaration_hooks: ChargeDeclarationHookRegistry,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    charge_state = state.charge_phase_state
    if charge_state is None or charge_state.active_selection is None:
        raise GameLifecycleError("Charge declaration grant requires active selection.")
    selection = charge_state.active_selection
    payload = _decision_payload_object(result.payload)
    if _payload_string(payload, key="unit_instance_id") != selection.unit_instance_id:
        raise GameLifecycleError("Charge declaration grant unit drift.")
    if (
        _payload_string(payload, key="source_decision_request_id") != selection.request_id
        or _payload_string(payload, key="source_decision_result_id") != selection.result_id
    ):
        raise GameLifecycleError("Charge declaration grant source decision drift.")
    if result.selected_option_id == DECLINE_CHARGE_DECLARATION_GRANT_OPTION_ID:
        selected_grants: tuple[ChargeDeclarationGrant, ...] = ()
    else:
        selected_grants = _selected_charge_declaration_grants_from_payload(
            cast(dict[str, JsonValue], payload)
        )
        _validate_selected_charge_declaration_grants(
            state=state,
            selection=selection,
            registry=charge_declaration_hooks,
            selected_grants=selected_grants,
        )
    persisting_effects = tuple(
        effect
        for grant in selected_grants
        for effect in _record_charge_declaration_grant_effects(
            state=state,
            decisions=decisions,
            result=result,
            selection=selection,
            grant=grant,
        )
    )
    decisions.event_log.append(
        "charge_declaration_grant_decision_resolved",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.CHARGE.value,
                "active_player_id": selection.player_id,
                "unit_instance_id": selection.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "selected_option_id": result.selected_option_id,
                "selected_charge_declaration_grants": [
                    grant.to_payload() for grant in selected_grants
                ],
                "persisting_effects": [effect.to_payload() for effect in persisting_effects],
                "phase_body_status": "charge_declaration_grant_decision_resolved",
            }
        ),
    )
    return _resolve_charge_roll(
        state=state,
        selection=selection,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        ability_index=ability_index,
        runtime_modifier_registry=runtime_modifier_registry,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )


def _selected_charge_declaration_grants_from_payload(
    payload: dict[str, JsonValue],
) -> tuple[ChargeDeclarationGrant, ...]:
    raw_grants = payload.get("selected_charge_declaration_grants")
    if not isinstance(raw_grants, list):
        raise GameLifecycleError("Charge declaration grant payload missing selected grants.")
    grants: list[ChargeDeclarationGrant] = []
    for raw_grant in raw_grants:
        if not isinstance(raw_grant, dict):
            raise GameLifecycleError("Charge declaration selected grants must be objects.")
        grants.append(
            ChargeDeclarationGrant.from_payload(cast(ChargeDeclarationGrantPayload, raw_grant))
        )
    return tuple(sorted(grants, key=lambda grant: grant.hook_id))


def _validate_selected_charge_declaration_grants(
    *,
    state: GameState,
    selection: ChargingUnitSelection,
    registry: ChargeDeclarationHookRegistry,
    selected_grants: tuple[ChargeDeclarationGrant, ...],
) -> None:
    if not selected_grants:
        raise GameLifecycleError("Charge declaration grant selection requires a selected grant.")
    context = ChargeDeclarationContext(
        state=state,
        player_id=selection.player_id,
        battle_round=state.battle_round,
        unit_instance_id=selection.unit_instance_id,
        selection_request_id=selection.request_id,
        selection_result_id=selection.result_id,
    )
    available_payloads = {
        grant.hook_id: grant.to_payload() for grant in registry.grants_for(context)
    }
    for grant in selected_grants:
        expected = available_payloads.get(grant.hook_id)
        if expected is None:
            raise GameLifecycleError("Selected charge declaration grant is not available.")
        if grant.to_payload() != expected:
            raise GameLifecycleError("Selected charge declaration grant payload drift.")


def _record_charge_declaration_grant_effects(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    selection: ChargingUnitSelection,
    grant: ChargeDeclarationGrant,
) -> tuple[PersistingEffect, ...]:
    effects: list[PersistingEffect] = []
    if grant.decision_effect_payload is not None:
        resource_spend_result = apply_faction_resource_spend_effect(
            state=state,
            player_id=selection.player_id,
            source_id=f"{grant.source_id}:{result.request_id}:{result.result_id}:spend",
            effect_payload=grant.decision_effect_payload,
        )
        spend_effect = PersistingEffect(
            effect_id=f"{result.result_id}:{grant.hook_id}:decision",
            source_rule_id=grant.source_id,
            owner_player_id=selection.player_id,
            target_unit_instance_ids=(selection.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.CHARGE,
            expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
            effect_payload=faction_resource_result_enriched_payload(
                effect_payload=grant.decision_effect_payload,
                result=resource_spend_result,
            ),
        )
        state.record_persisting_effect(spend_effect)
        resolve_faction_resource_refund_roll(
            state=state,
            decisions=decisions,
            spend_effect=spend_effect,
        )
        effects.append(spend_effect)
    if grant.unit_effect_payload is None:
        if not effects:
            raise GameLifecycleError("Charge declaration grant has no effect to record.")
        return tuple(effects)
    unit_effect = PersistingEffect(
        effect_id=f"{result.result_id}:{grant.hook_id}:unit",
        source_rule_id=grant.source_id,
        owner_player_id=selection.player_id,
        target_unit_instance_ids=_charge_declaration_grant_unit_effect_target_ids(
            unit_instance_id=selection.unit_instance_id,
            effect_payload=grant.unit_effect_payload,
        ),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.CHARGE,
        expiration=_charge_declaration_grant_unit_effect_expiration(
            state=state,
            grant=grant,
        ),
        effect_payload=grant.unit_effect_payload,
    )
    state.record_persisting_effect(unit_effect)
    effects.append(unit_effect)
    return tuple(effects)


def _charge_declaration_grant_unit_effect_target_ids(
    *,
    unit_instance_id: str,
    effect_payload: JsonValue,
) -> tuple[str, ...]:
    if not isinstance(effect_payload, dict):
        return (_validate_identifier("unit_instance_id", unit_instance_id),)
    raw_target_ids = effect_payload.get("target_unit_instance_ids")
    if raw_target_ids is None:
        return (_validate_identifier("unit_instance_id", unit_instance_id),)
    if not isinstance(raw_target_ids, list):
        raise GameLifecycleError(
            "Charge declaration grant target_unit_instance_ids must be a list."
        )
    target_ids = tuple(
        _validate_identifier("target_unit_instance_ids", raw_id) for raw_id in raw_target_ids
    )
    if not target_ids:
        raise GameLifecycleError("Charge declaration grant target_unit_instance_ids is empty.")
    if len(set(target_ids)) != len(target_ids):
        raise GameLifecycleError(
            "Charge declaration grant target_unit_instance_ids are duplicated."
        )
    return target_ids


def _charge_declaration_grant_unit_effect_expiration(
    *,
    state: GameState,
    grant: ChargeDeclarationGrant,
) -> EffectExpiration:
    turn_player_id = state.active_player_id
    if turn_player_id is None:
        raise GameLifecycleError("Charge grant expiration requires a turn owner.")
    if grant.unit_effect_expiration == "end_phase":
        return EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=BattlePhaseKind.CHARGE,
            player_id=turn_player_id,
        )
    if grant.unit_effect_expiration == "end_turn":
        return EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=turn_player_id,
        )
    raise GameLifecycleError("Charge declaration grant effect expiration is unsupported.")


def legal_charge_target_unit_instance_ids(
    *,
    state: GameState,
    unit_instance_id: str,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> tuple[str, ...]:
    return tuple(
        candidate.target_unit_instance_id
        for candidate in _charge_target_candidates(
            state=state,
            unit_instance_id=unit_instance_id,
            ruleset_descriptor=ruleset_descriptor,
            charge_target_restriction_hooks=charge_target_restriction_hooks,
        )
        if candidate.is_legal
    )


def _reachable_charge_target_distances(
    *,
    state: GameState,
    unit_instance_id: str,
    maximum_distance_inches: float,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> dict[str, float]:
    distances: dict[str, float] = {}
    for candidate in _charge_target_candidates(
        state=state,
        unit_instance_id=unit_instance_id,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    ):
        if candidate.is_legal and candidate.closest_distance_inches <= maximum_distance_inches:
            distances[candidate.target_unit_instance_id] = candidate.closest_distance_inches
    return dict(sorted(distances.items()))


def _unit_is_engaged(
    *,
    state: GameState,
    unit_instance_id: str,
    player_id: str,
    ruleset_descriptor: RulesetDescriptor,
) -> bool:
    scenario = _battlefield_scenario(state)
    source = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=unit_instance_id,
    )
    if source.owner_player_id != player_id:
        raise GameLifecycleError(
            "Charge Engagement Range query player does not own the rules unit."
        )
    return bool(
        scenario_physically_engaged_enemy_rules_unit_ids(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_instance_id=source.unit_instance_id,
        )
    )


def _charge_actor_can_declare_charge(
    *,
    state: GameState,
    unit_instance_id: str,
    ruleset_descriptor: RulesetDescriptor,
) -> bool:
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    return all(
        AircraftMovementPolicy.from_unit(
            unit=component.unit,
            ruleset_descriptor=ruleset_descriptor,
        ).can_declare_charge
        for component in view.living_components
    )


def _ensure_charge_phase_state(*, state: GameState) -> ChargePhaseState:
    current = state.charge_phase_state
    active_player_id = _active_player_id(state)
    if current is not None:
        return current
    charge_state = ChargePhaseState(
        battle_round=state.battle_round,
        active_player_id=active_player_id,
    )
    state.replace_charge_phase_state(charge_state)
    return charge_state


def _validate_charge_phase_state(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Charge phase requires battle stage.")
    if state.current_battle_phase is not BattlePhase.CHARGE:
        raise GameLifecycleError("Charge phase requires CHARGE phase.")
    _active_player_id(state)
    if state.battlefield_state is None:
        raise GameLifecycleError("Charge phase requires battlefield_state.")
    if state.charge_phase_state is None:
        return
    charge_state = state.charge_phase_state
    if charge_state.battle_round != state.battle_round:
        raise GameLifecycleError("charge_phase_state battle round drift.")
    parent = (
        charge_state
        if charge_state.interruption is None
        else charge_state.interruption.suspended_phase
    )
    if parent.active_player_id != state.active_player_id:
        raise GameLifecycleError("charge_phase_state active player drift.")


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Charge phase requires battlefield_state.")
    try:
        scenario = battlefield_scenario_for_state(state=state)
        scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
    except PlacementError as exc:
        raise GameLifecycleError("Charge battlefield scenario is invalid.") from exc
    return scenario


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Charge phase requires active_player_id.")
    phase = state.charge_phase_state
    return state.active_player_id if phase is None else phase.active_player_id


def _active_player_placed_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            view.unit_instance_id
            for view in placed_alive_rules_unit_views(state=state)
            if view.owner_player_id == player_id
        )
    )


def _unit_by_id(*, state: GameState, unit_instance_id: str) -> RulesUnitView:
    return rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)


def _unit_for_selection(*, state: GameState, selection: ChargingUnitSelection) -> RulesUnitView:
    if type(selection) is not ChargingUnitSelection:
        raise GameLifecycleError("Charge unit lookup requires a ChargingUnitSelection.")
    return _unit_by_id(state=state, unit_instance_id=selection.unit_instance_id)


def _validate_ability_index_mapping(indexes: object) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(indexes, Mapping):
        raise GameLifecycleError("ability_indexes_by_player_id must be a mapping.")
    mapped_indexes = cast(Mapping[object, object], indexes)
    validated: dict[str, AbilityCatalogIndex] = {}
    for raw_player_id, raw_index in mapped_indexes.items():
        player_id = _validate_identifier("ability_indexes_by_player_id key", raw_player_id)
        if type(raw_index) is not AbilityCatalogIndex:
            raise GameLifecycleError(
                "ability_indexes_by_player_id values must be AbilityCatalogIndex."
            )
        validated[player_id] = raw_index
    return MappingProxyType(validated)


def _ability_index_for_player(
    indexes: object,
    *,
    player_id: str,
) -> AbilityCatalogIndex:
    player = _validate_identifier("player_id", player_id)
    if not isinstance(indexes, Mapping):
        raise GameLifecycleError("ability_indexes_by_player_id must be a mapping.")
    mapped_indexes = cast(Mapping[str, AbilityCatalogIndex], indexes)
    index = mapped_indexes.get(player)
    if index is None:
        return AbilityCatalogIndex.from_records(())
    if type(index) is not AbilityCatalogIndex:
        raise GameLifecycleError("ability index mapping contained an invalid value.")
    return index


def _charge_phase_status_payload(
    *,
    state: GameState,
    phase_body_status: str,
    skipped_unit_ids: tuple[str, ...] = (),
) -> dict[str, JsonValue]:
    skipped_ids = _validate_identifier_tuple("skipped_unit_ids", skipped_unit_ids)
    return {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "phase": BattlePhase.CHARGE.value,
        "phase_body_status": phase_body_status,
        "skipped_unit_ids": list(skipped_ids),
    }


def _parse_charge_move_proposal_submission_or_invalid(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
) -> tuple[MovementProposalRequest, ChargeMoveProposal] | LifecycleStatus:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    try:
        proposal = ChargeMoveProposal.from_payload(
            cast(ChargeMoveProposalPayload, _decision_payload_object(result.payload))
        )
    except (GameLifecycleError, GeometryError, KeyError, TypeError) as exc:
        return _reject_invalid_charge_proposal(
            state=state,
            result=result,
            proposal_validation=_charge_proposal_payload_parse_failure(
                proposal_request=proposal_request,
                error=exc,
            ),
            message="Charge Move proposal payload is malformed.",
        )
    return (proposal_request, proposal)


def _charge_proposal_payload_parse_failure(
    *,
    proposal_request: MovementProposalRequest,
    error: GameLifecycleError | GeometryError | KeyError | TypeError,
) -> ProposalValidationResult:
    if type(error) is KeyError:
        missing = _key_error_field(error)
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="proposal_payload_missing_field",
            message=f"Charge Move proposal payload missing required field: {missing}.",
            field=missing,
        )
    field = "payload"
    message = str(error)
    if "proposal_kind" in message:
        field = "proposal_kind"
    elif "movement_mode" in message or "MovementMode" in message:
        field = "movement_mode"
    elif "movement_phase_action" in message:
        field = "movement_phase_action"
    elif "charge_target_unit_instance_ids" in message:
        field = "charge_target_unit_instance_ids"
    elif "witness" in message or "PathWitness" in message:
        field = "witness"
    return ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code="proposal_payload_malformed",
        message=f"Charge Move proposal payload is malformed: {message}",
        field=field,
    )


def _reject_invalid_charge_move_resolution(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    proposal_request: MovementProposalRequest,
    proposal_validation: ProposalValidationResult,
    resolution: ChargeMoveResolution,
    violation_code: str,
    message: str,
) -> LifecycleStatus:
    invalid_validation = ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code=violation_code,
        message=message,
        field=_charge_move_violation_field(violation_code),
    )
    invalid_payload = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "phase": BattlePhase.CHARGE.value,
            "unit_instance_id": resolution.unit_instance_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": _CHARGE_MOVE_INVALID_STATUS,
            "violation_code": violation_code,
            "proposal_request_id": proposal_request.request_id,
            "proposal_validation": invalid_validation.to_payload(),
            "pre_apply_proposal_validation": proposal_validation.to_payload(),
            **resolution.movement_payload,
        }
    )
    decisions.event_log.append("charge_move_invalid", invalid_payload)
    retry_request = _request_charge_move_proposal_retry(
        state=state,
        decisions=decisions,
        proposal_request=proposal_request,
        rejected_result=result,
    )
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message=message,
        payload={
            "phase": BattlePhase.CHARGE.value,
            "phase_body_status": _CHARGE_MOVE_INVALID_STATUS,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "unit_instance_id": resolution.unit_instance_id,
            "movement_phase_action": CHARGE_MOVE_ACTION,
            "violation_code": violation_code,
            "next_request_id": retry_request.request_id,
            "proposal_validation": validate_json_value(invalid_validation.to_payload()),
        },
    )


def _charge_move_completed_payload(
    *,
    state: GameState,
    result: DecisionResult,
    proposal_request: MovementProposalRequest,
    proposal_validation: ProposalValidationResult,
    resolution: ChargeMoveResolution,
    transition_batch: BattlefieldTransitionBatch,
    persisting_effect: PersistingEffect | None,
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": _active_player_id(state),
        "phase": BattlePhase.CHARGE.value,
        "unit_instance_id": resolution.unit_instance_id,
        "request_id": result.request_id,
        "result_id": result.result_id,
        "proposal_request_id": proposal_request.request_id,
        "phase_body_status": _CHARGE_MOVE_COMPLETED_STATUS,
        "proposal_validation": validate_json_value(proposal_validation.to_payload()),
        "transition_batch": validate_json_value(transition_batch.to_payload()),
        **resolution.movement_payload,
    }
    if persisting_effect is not None:
        payload["persisting_effect"] = validate_json_value(persisting_effect.to_payload())
    expected_keys: frozenset[str] = CHARGE_MOVE_COMPLETED_PAYLOAD_KEYS | (
        CHARGE_MOVE_COMPLETED_OPTIONAL_PAYLOAD_KEYS
        if persisting_effect is not None
        else frozenset[str]()
    )
    if frozenset(payload) != expected_keys:
        raise GameLifecycleError("charge_move_completed payload shape drifted.")
    return _validate_json_object("charge_move_completed payload", payload)


def _record_fights_first_effect_if_needed(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    proposal_request: MovementProposalRequest,
    result: DecisionResult,
    unit_instance_id: str,
) -> PersistingEffect | None:
    if not ruleset_descriptor.charge_policy.grants_fights_first_until_end_turn:
        return None
    active_player_id = _active_player_id(state)
    turn_player_id = state.active_player_id
    if turn_player_id is None:
        raise GameLifecycleError("Charge bonus requires the current turn owner.")
    effect = PersistingEffect(
        effect_id=f"{result.result_id}:charge:fights-first",
        source_rule_id="core-rules:charge:fights-first",
        owner_player_id=active_player_id,
        target_unit_instance_ids=(unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.CHARGE,
        expiration=EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=turn_player_id,
        ),
        effect_payload={
            "effect_kind": FIGHTS_FIRST_CHARGE_EFFECT_KIND,
            "proposal_request_id": proposal_request.request_id,
            "decision_result_id": result.result_id,
        },
    )
    state.record_persisting_effect(effect)
    return effect


def _charge_move_violation_code(
    *,
    resolution: ChargeMoveResolution,
    ruleset_descriptor: RulesetDescriptor,
    maximum_distance_inches: float,
) -> str | None:
    return charge_move_violation_code(
        resolution=resolution,
        ruleset_descriptor=ruleset_descriptor,
        maximum_distance_inches=maximum_distance_inches,
    )


def charge_move_violation_code(
    *,
    resolution: ChargeMoveResolution,
    ruleset_descriptor: RulesetDescriptor,
    maximum_distance_inches: float,
) -> str | None:
    for path_result in resolution.path_validation_results:
        if not path_result.is_valid:
            return path_result.violations[0].violation_code
    for terrain_result in resolution.terrain_path_legality_results:
        if not terrain_result.is_valid:
            return terrain_result.violations[0].violation_code
    if resolution.rollback_record is not None or not resolution.coherency_result.is_coherent:
        return "unit_coherency_broken"
    endpoint_violation = _charge_endpoint_violation_code(
        endpoint_witness=resolution.endpoint_witness,
        ruleset_descriptor=ruleset_descriptor,
        maximum_distance_inches=maximum_distance_inches,
    )
    if endpoint_violation is not None:
        return endpoint_violation
    return None


def charge_move_invalid_message(violation_code: str) -> str:
    return _charge_move_invalid_message(violation_code)


def charge_move_violation_field(violation_code: str) -> str:
    return _charge_move_violation_field(violation_code)


def _charge_move_invalid_message(violation_code: str) -> str:
    code = _validate_identifier("Charge Move violation_code", violation_code)
    if code == "unit_coherency_broken":
        return "Charge Move endpoint violates unit coherency."
    if code.startswith("charge_"):
        return "Charge Move endpoint violates charge rules."
    if code.startswith("terrain") or code in {
        "endpoint_only_path",
        "end_on_forbidden_terrain",
        "upper_floor_keyword_forbidden",
        "base_overhangs_support_surface",
        "model_cannot_be_placed_at_endpoint",
        "ends_mid_climb",
        "manual_geometry_required",
    }:
        return "Charge Move terrain path is invalid."
    return "Charge Move path is invalid."


def _charge_move_violation_field(violation_code: str) -> str:
    code = _validate_identifier("Charge Move violation_code", violation_code)
    if code.startswith("charge_"):
        return "charge_target_unit_instance_ids"
    return "witness"


def _charge_witness_matches_current_unit_status(
    *,
    state: GameState,
    proposal_request: MovementProposalRequest,
    proposal: ChargeMoveProposal,
) -> ProposalValidationResult | None:
    return validate_charge_witness_for_proposal(
        state=state, request=proposal_request, witness=proposal.witness
    )


def _proposal_context(request: MovementProposalRequest) -> dict[str, object]:
    if type(request) is not MovementProposalRequest:
        raise GameLifecycleError("Proposal context requires a MovementProposalRequest.")
    context = request.context or {}
    return cast(dict[str, object], context)


def _charge_proposal_kind(value: object) -> ProposalKind:
    proposal_kind = proposal_kind_from_token(value)
    if proposal_kind is not ProposalKind.CHARGE_MOVE:
        raise GameLifecycleError("ChargeMoveProposal proposal_kind must be charge_move.")
    return proposal_kind


def _proposal_kind_from_token(value: object) -> ProposalKind:
    return proposal_kind_from_token(value)


def _charge_movement_mode(value: object) -> MovementMode:
    movement_mode = movement_mode_from_token(value)
    if movement_mode is not MovementMode.CHARGE:
        raise GameLifecycleError("ChargeMoveProposal movement_mode must be charge.")
    return movement_mode


def _movement_mode_from_token(value: object) -> MovementMode:
    return movement_mode_from_token(value)


def _validate_charge_move_action(value: object) -> str:
    action = _validate_identifier("ChargeMoveProposal movement_phase_action", value)
    if action != CHARGE_MOVE_ACTION:
        raise GameLifecycleError("ChargeMoveProposal movement_phase_action must be charge_move.")
    return action


def _payload_distance_map(payload: dict[str, object], *, key: str) -> dict[str, float]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Payload field {key} must be an object.")
    return _validate_distance_map(key, cast(dict[str, object], value))


def _key_error_field(error: KeyError) -> str:
    if len(error.args) != 1:
        return "payload"
    key = error.args[0]
    if type(key) is str and key.strip():
        return key.strip()
    return "payload"


def _decision_payload_object(payload: JsonValue) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return cast(dict[str, object], payload)


def _payload_string(payload: dict[str, object], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Payload field {key} must be a string.")
    return _validate_identifier(key, value)


def _payload_object(payload: dict[str, object], *, key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Payload field {key} must be an object.")
    return cast(dict[str, object], value)


def _payload_identifier_list(payload: Mapping[str, object], *, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if type(value) is not list:
        raise GameLifecycleError(f"Payload field {key} must be a list.")
    raw_values = cast(list[object], value)
    validated = tuple(_validate_identifier(key, raw_value) for raw_value in raw_values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"Payload field {key} must not contain duplicates.")
    return tuple(sorted(validated))


def _payload_optional_identifier_list(
    payload: Mapping[str, object],
    *,
    key: str,
) -> tuple[str, ...]:
    if key not in payload:
        return ()
    return _payload_identifier_list(payload, key=key)


def _invalid_charging_unit_finite_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result does not match the pending charge request.",
            payload={"invalid_reason": "invalid_charging_unit_result", "field": "request_id"},
        )
    if result.decision_type != request.decision_type:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result type does not match the pending charge request.",
            payload={"invalid_reason": "invalid_charging_unit_result", "field": "decision_type"},
        )
    if result.actor_id != request.actor_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result actor does not match the pending charge request.",
            payload={"invalid_reason": "invalid_charging_unit_result", "field": "actor_id"},
        )
    selected_payload: JsonValue = None
    selected_option_found = False
    for option in request.options:
        if option.option_id == result.selected_option_id:
            selected_payload = option.payload
            selected_option_found = True
            break
    if not selected_option_found:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result selected option is not pending for charge.",
            payload={
                "invalid_reason": "invalid_charging_unit_result",
                "field": "selected_option_id",
            },
        )
    if result.payload != selected_payload:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result payload does not match the pending charge option.",
            payload={"invalid_reason": "invalid_charging_unit_result", "field": "payload"},
        )
    return None


def _ruleset_descriptor_for_handler(handler: ChargePhaseHandler) -> RulesetDescriptor:
    if type(handler) is not ChargePhaseHandler:
        raise GameLifecycleError("Charge ruleset descriptor requires a ChargePhaseHandler.")
    if handler.ruleset_descriptor is None:
        raise GameLifecycleError("Charge phase requires a RulesetDescriptor.")
    return handler.ruleset_descriptor


_validate_identifier = IdentifierValidator(GameLifecycleError)

__all__ = (
    "_ability_index_for_player",
    "_active_player_id",
    "_active_player_placed_unit_ids",
    "_apply_charge_declaration_grant_decision",
    "_apply_charge_roll_reroll_decision",
    "_apply_charging_unit_selection_decision",
    "_battlefield_scenario",
    "_charge_actor_can_declare_charge",
    "_charge_after_fall_back_allowed_by_effects",
    "_charge_declaration_grant_options",
    "_charge_declaration_grant_unit_effect_expiration",
    "_charge_declaration_grant_unit_effect_target_ids",
    "_charge_endpoint_violation_code",
    "_charge_endpoint_witness",
    "_charge_forbidden_by_effects",
    "_charge_move_completed_payload",
    "_charge_move_invalid_message",
    "_charge_move_transition_batch",
    "_charge_move_violation_code",
    "_charge_move_violation_field",
    "_charge_movement_mode",
    "_charge_phase_status_payload",
    "_charge_proposal_kind",
    "_charge_proposal_payload_parse_failure",
    "_charge_unit_ineligibility_reason",
    "_charge_witness_matches_current_unit_status",
    "_closest_distance_between_model_groups",
    "_complete_charge_phase_or_request_heroic_intervention",
    "_decision_payload_object",
    "_default_stratagem_index",
    "_empty_ability_indexes",
    "_empty_stratagem_cost_modifier_registry",
    "_enemy_geometry_models_for_player",
    "_ensure_charge_phase_state",
    "_friendly_geometry_models_for_charge_path",
    "_friendly_vehicle_monster_model_ids",
    "_geometry_models_for_unit",
    "_geometry_models_for_unit_placement",
    "_invalid_charging_unit_finite_decision_status",
    "_key_error_field",
    "_legal_charging_unit_ids",
    "_model_groups_are_engaged",
    "_movement_mode_from_token",
    "_parse_charge_move_proposal_submission_or_invalid",
    "_payload_distance_map",
    "_payload_identifier_list",
    "_payload_object",
    "_payload_optional_identifier_list",
    "_payload_string",
    "_proposal_context",
    "_proposal_kind_from_token",
    "_reachable_charge_target_distances",
    "_record_charge_declaration_grant_effects",
    "_record_fights_first_effect_if_needed",
    "_reject_invalid_charge_move_resolution",
    "_reject_invalid_charge_proposal",
    "_request_charge_declaration_grant_if_available",
    "_resolve_charge_roll",
    "_resolve_charge_roll_state",
    "_ruleset_descriptor_for_handler",
    "_selected_charge_declaration_grants_from_payload",
    "_terrain_volumes_for_features",
    "_unit_by_id",
    "_unit_for_selection",
    "_unit_is_engaged",
    "_validate_ability_index_mapping",
    "_validate_charge_move_action",
    "_validate_charge_phase_state",
    "_validate_charge_witness_matches_unit",
    "_validate_distance_map",
    "_validate_json_object",
    "_validate_path_validation_results",
    "_validate_selected_charge_declaration_grants",
    "_validate_terrain_path_legality_results",
    "charge_move_invalid_message",
    "charge_move_violation_code",
    "charge_move_violation_field",
    "invalid_charge_declaration_grant_status",
    "invalid_charging_unit_selection_status",
    "legal_charge_target_unit_instance_ids",
    "resolve_charge_move",
)
