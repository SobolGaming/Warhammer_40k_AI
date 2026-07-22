from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.dice import (
    DiceRollState,
    DiceRollStatePayload,
    RerollPermission,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
    movement_mode_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine import unit_move_completed_hooks as _umc
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.aircraft import AircraftMovementPolicy, HoverModeState
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelPlacement,
    PlacementError,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    conditional_charge_after_movement_action_allowed,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_charge_roll_modifiers_for_unit,
)
from warhammer40k_core.engine.charge_declaration import (
    CHARGE_MOVE_PENDING_STATUS,
    CHARGE_ROLL_COMMAND_REROLL_FORBIDDEN_RULE_ID,
    ChargeDistanceState,
    ChargeDistanceStatePayload,
    ChargeEligibilityContext,
    ChargeRollRequest,
    ChargeRollRequestPayload,
    ChargeRollResult,
    ChargeTargetCandidate,
    phase15a_charge_roll_payload,
)
from warhammer40k_core.engine.charge_declaration_hooks import (
    DECLINE_CHARGE_DECLARATION_GRANT_OPTION_ID,
    SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE,
    ChargeDeclarationContext,
    ChargeDeclarationGrant,
    ChargeDeclarationGrantPayload,
    ChargeDeclarationHookRegistry,
)
from warhammer40k_core.engine.charge_effects import charge_after_advance_allowed_by_effects
from warhammer40k_core.engine.charge_roll_permissions import (
    charge_reroll_permission_for_unit as _charge_reroll_permission_for_unit,
)
from warhammer40k_core.engine.charge_roll_permissions import (
    current_model_instance_ids_for_charge_unit as _current_model_instance_ids_for_charge_unit,
)
from warhammer40k_core.engine.charge_rule_effects import (
    charge_path_context_with_rule_effect_permissions,
    enemy_vehicle_monster_model_ids_for_player,
    unit_has_vehicle_or_monster_keyword,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_resources import (
    apply_faction_resource_spend_effect,
    faction_resource_result_enriched_payload,
    resolve_faction_resource_refund_roll,
)
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
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
from warhammer40k_core.engine.phases.charge_move_completed_hooks import (
    resolve_charge_move_completed_hooks,
    validate_charge_move_completed_hook_provider,
)
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ChargeTargetRestrictionContext,
    ChargeTargetRestrictionHookRegistry,
    TargetRestriction,
)
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    UnitCoherencyResult,
    resolve_unit_movement_endpoint_coherency,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathWitness,
    PathWitnessPayload,
    TerrainPathLegalityResult,
)
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.reaction_queue import ReactionQueue


SELECT_CHARGING_UNIT_DECISION_TYPE = "select_charging_unit"
COMPLETE_CHARGE_PHASE_OPTION_ID = "complete_charge_phase"
CHARGE_MOVE_ACTION = "charge_move"
FIGHTS_FIRST_CHARGE_EFFECT_KIND = "charge_grants_fights_first"
CHARGE_AFTER_FALL_BACK_EFFECT_KIND = "charge_after_fall_back_allowed"
CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY = "charge_move_required_target_unit_instance_ids"
_COMPLETE_CHARGE_PHASE_STATUS = "charge_phase_complete"
_CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS = "charge_move_proposal_required"
_CHARGE_MOVE_INVALID_STATUS = "charge_move_invalid"
_CHARGE_MOVE_DECLINED_STATUS = "charge_move_declined"
_CHARGE_MOVE_COMPLETED_STATUS = "charge_move_completed"


def _empty_ability_indexes() -> Mapping[str, AbilityCatalogIndex]:
    return MappingProxyType({})


def _empty_declared_charge_targets() -> dict[str, tuple[str, ...]]:
    return {}


class ChargingUnitSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str


class ChargePhaseStatePayload(TypedDict):
    battle_round: int
    active_player_id: str
    phase_complete: bool
    selected_unit_ids: list[str]
    active_selection: ChargingUnitSelectionPayload | None
    distance_states: list[ChargeDistanceStatePayload]
    declared_target_unit_instance_ids_by_unit: dict[str, list[str]]


class ChargeMoveProposalPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    unit_instance_id: str
    movement_phase_action: str
    movement_mode: str
    charge_target_unit_instance_ids: list[str]
    witness: NotRequired[object]


class ChargeEndpointWitnessPayload(TypedDict):
    selected_target_unit_instance_ids: list[str]
    target_distances_before_inches: dict[str, float]
    target_distances_after_inches: dict[str, float]
    engaged_target_unit_instance_ids: list[str]
    preferred_distance_target_unit_instance_ids: list[str]
    non_target_engaged_unit_instance_ids: list[str]


@dataclass(frozen=True, slots=True)
class ChargingUnitSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ChargingUnitSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ChargingUnitSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "ChargingUnitSelection unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("ChargingUnitSelection request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("ChargingUnitSelection result_id", self.result_id),
        )

    def to_payload(self) -> ChargingUnitSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "request_id": self.request_id,
            "result_id": self.result_id,
        }

    @classmethod
    def from_payload(cls, payload: ChargingUnitSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
        )


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
        if required_target_ids and selected_target_ids.isdisjoint(required_target_ids):
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="charge_required_target_not_selected",
                message="Charge Move selected targets did not include a required reachable target.",
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
class ChargeEndpointWitness:
    selected_target_unit_instance_ids: tuple[str, ...]
    target_distances_before_inches: dict[str, float]
    target_distances_after_inches: dict[str, float]
    engaged_target_unit_instance_ids: tuple[str, ...]
    preferred_distance_target_unit_instance_ids: tuple[str, ...]
    non_target_engaged_unit_instance_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "selected_target_unit_instance_ids",
            _validate_identifier_tuple(
                "ChargeEndpointWitness selected_target_unit_instance_ids",
                self.selected_target_unit_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "target_distances_before_inches",
            _validate_distance_map(
                "ChargeEndpointWitness target_distances_before_inches",
                self.target_distances_before_inches,
            ),
        )
        object.__setattr__(
            self,
            "target_distances_after_inches",
            _validate_distance_map(
                "ChargeEndpointWitness target_distances_after_inches",
                self.target_distances_after_inches,
            ),
        )
        object.__setattr__(
            self,
            "engaged_target_unit_instance_ids",
            _validate_identifier_tuple(
                "ChargeEndpointWitness engaged_target_unit_instance_ids",
                self.engaged_target_unit_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "preferred_distance_target_unit_instance_ids",
            _validate_identifier_tuple(
                "ChargeEndpointWitness preferred_distance_target_unit_instance_ids",
                self.preferred_distance_target_unit_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "non_target_engaged_unit_instance_ids",
            _validate_identifier_tuple(
                "ChargeEndpointWitness non_target_engaged_unit_instance_ids",
                self.non_target_engaged_unit_instance_ids,
            ),
        )

    def to_payload(self) -> ChargeEndpointWitnessPayload:
        return {
            "selected_target_unit_instance_ids": list(self.selected_target_unit_instance_ids),
            "target_distances_before_inches": dict(
                sorted(self.target_distances_before_inches.items())
            ),
            "target_distances_after_inches": dict(
                sorted(self.target_distances_after_inches.items())
            ),
            "engaged_target_unit_instance_ids": list(self.engaged_target_unit_instance_ids),
            "preferred_distance_target_unit_instance_ids": list(
                self.preferred_distance_target_unit_instance_ids
            ),
            "non_target_engaged_unit_instance_ids": list(self.non_target_engaged_unit_instance_ids),
        }


@dataclass(frozen=True, slots=True)
class ChargeMoveResolution:
    unit_instance_id: str
    selected_target_unit_instance_ids: tuple[str, ...]
    attempted_placement: UnitPlacement
    witness: PathWitness
    endpoint_witness: ChargeEndpointWitness
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult
    rollback_record: MovementRollbackRecord | None
    movement_payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("ChargeMoveResolution unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "selected_target_unit_instance_ids",
            _validate_identifier_tuple(
                "ChargeMoveResolution selected_target_unit_instance_ids",
                self.selected_target_unit_instance_ids,
            ),
        )
        if type(self.attempted_placement) is not UnitPlacement:
            raise GameLifecycleError(
                "ChargeMoveResolution attempted_placement must be UnitPlacement."
            )
        if self.attempted_placement.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError("ChargeMoveResolution attempted_placement unit drift.")
        if type(self.witness) is not PathWitness:
            raise GameLifecycleError("ChargeMoveResolution witness must be a PathWitness.")
        if type(self.endpoint_witness) is not ChargeEndpointWitness:
            raise GameLifecycleError(
                "ChargeMoveResolution endpoint_witness must be ChargeEndpointWitness."
            )
        object.__setattr__(
            self,
            "path_validation_results",
            _validate_path_validation_results(self.path_validation_results),
        )
        object.__setattr__(
            self,
            "terrain_path_legality_results",
            _validate_terrain_path_legality_results(self.terrain_path_legality_results),
        )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise GameLifecycleError(
                "ChargeMoveResolution coherency_result must be UnitCoherencyResult."
            )
        if (
            self.rollback_record is not None
            and type(self.rollback_record) is not MovementRollbackRecord
        ):
            raise GameLifecycleError(
                "ChargeMoveResolution rollback_record must be MovementRollbackRecord."
            )
        object.__setattr__(
            self,
            "movement_payload",
            _validate_json_object("ChargeMoveResolution movement_payload", self.movement_payload),
        )

    @property
    def is_valid(self) -> bool:
        return (
            all(result.is_valid for result in self.path_validation_results)
            and all(result.is_valid for result in self.terrain_path_legality_results)
            and self.rollback_record is None
        )

    def transition_batch(self, *, before: UnitPlacement) -> BattlefieldTransitionBatch:
        if not self.is_valid:
            raise GameLifecycleError("Invalid Charge Move cannot emit displacement records.")
        return _charge_move_transition_batch(
            before=before,
            after=self.attempted_placement,
            witness=self.witness,
        )


@dataclass(frozen=True, slots=True)
class ChargePhaseState:
    battle_round: int
    active_player_id: str
    phase_complete: bool = False
    selected_unit_ids: tuple[str, ...] = ()
    active_selection: ChargingUnitSelection | None = None
    distance_states: tuple[ChargeDistanceState, ...] = ()
    declared_target_unit_instance_ids_by_unit: dict[str, tuple[str, ...]] = field(
        default_factory=_empty_declared_charge_targets
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ChargePhaseState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("ChargePhaseState active_player_id", self.active_player_id),
        )
        if type(self.phase_complete) is not bool:
            raise GameLifecycleError("ChargePhaseState phase_complete must be a bool.")
        object.__setattr__(
            self,
            "selected_unit_ids",
            _validate_identifier_tuple(
                "ChargePhaseState selected_unit_ids", self.selected_unit_ids
            ),
        )
        if self.active_selection is not None:
            if type(self.active_selection) is not ChargingUnitSelection:
                raise GameLifecycleError(
                    "ChargePhaseState active_selection must be ChargingUnitSelection."
                )
            if self.active_selection.player_id != self.active_player_id:
                raise GameLifecycleError("Charge active_selection active player drift.")
            if self.active_selection.battle_round != self.battle_round:
                raise GameLifecycleError("Charge active_selection battle round drift.")
            if self.active_selection.unit_instance_id not in self.selected_unit_ids:
                raise GameLifecycleError("Charge active_selection must be selected.")
        object.__setattr__(
            self,
            "distance_states",
            _validate_charge_distance_states(self.distance_states),
        )
        object.__setattr__(
            self,
            "declared_target_unit_instance_ids_by_unit",
            _validate_charge_declared_target_map(self.declared_target_unit_instance_ids_by_unit),
        )
        if self.phase_complete and self.active_selection is not None:
            raise GameLifecycleError("Completed Charge phase cannot have active_selection.")
        if self.phase_complete and self.move_pending_distance_state() is not None:
            raise GameLifecycleError("Completed Charge phase cannot have pending charge movement.")

    def with_unit_selection(self, selection: ChargingUnitSelection) -> Self:
        if type(selection) is not ChargingUnitSelection:
            raise GameLifecycleError("Charge selection must be ChargingUnitSelection.")
        if self.phase_complete:
            raise GameLifecycleError("Cannot select a charging unit after phase completion.")
        if self.active_selection is not None:
            raise GameLifecycleError("Charge unit selection requires no active selection.")
        if selection.player_id != self.active_player_id:
            raise GameLifecycleError("Charge selection player drift.")
        if selection.battle_round != self.battle_round:
            raise GameLifecycleError("Charge selection battle round drift.")
        if selection.unit_instance_id in self.selected_unit_ids:
            raise GameLifecycleError("Charge unit was already selected.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=(*self.selected_unit_ids, selection.unit_instance_id),
            active_selection=selection,
            distance_states=self.distance_states,
            declared_target_unit_instance_ids_by_unit=(
                self.declared_target_unit_instance_ids_by_unit
            ),
        )

    def with_charge_roll_result(self, roll_result: ChargeRollResult) -> Self:
        if type(roll_result) is not ChargeRollResult:
            raise GameLifecycleError("Charge roll result must be ChargeRollResult.")
        if self.phase_complete:
            raise GameLifecycleError("Cannot record a charge roll after phase completion.")
        if self.active_selection is None:
            raise GameLifecycleError("Charge roll requires active_selection.")
        if roll_result.request.player_id != self.active_player_id:
            raise GameLifecycleError("Charge roll player drift.")
        if roll_result.request.battle_round != self.battle_round:
            raise GameLifecycleError("Charge roll battle round drift.")
        if roll_result.request.unit_instance_id != self.active_selection.unit_instance_id:
            raise GameLifecycleError("Charge roll unit drift.")
        distance_state = ChargeDistanceState(
            roll_result=roll_result,
            source_decision_request_id=roll_result.request.source_decision_request_id,
            source_decision_result_id=roll_result.request.source_decision_result_id,
        )
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=self.selected_unit_ids,
            active_selection=self.active_selection if roll_result.move_available else None,
            distance_states=(*self.distance_states, distance_state),
            declared_target_unit_instance_ids_by_unit=(
                self.declared_target_unit_instance_ids_by_unit
            ),
        )

    def with_charge_move_resolved(
        self,
        unit_instance_id: str,
        *,
        selected_target_unit_instance_ids: tuple[str, ...] = (),
    ) -> Self:
        resolved_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        target_ids = _validate_identifier_tuple(
            "selected_target_unit_instance_ids",
            selected_target_unit_instance_ids,
        )
        if self.phase_complete:
            raise GameLifecycleError("Cannot resolve a charge move after phase completion.")
        if self.active_selection is None:
            raise GameLifecycleError("Charge move resolution requires active_selection.")
        if self.active_selection.unit_instance_id != resolved_unit_id:
            raise GameLifecycleError("Charge move resolution unit drift.")
        if self.move_pending_distance_state() is None:
            raise GameLifecycleError("Charge move resolution requires pending distance state.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=self.selected_unit_ids,
            active_selection=None,
            distance_states=self.distance_states,
            declared_target_unit_instance_ids_by_unit={
                **self.declared_target_unit_instance_ids_by_unit,
                resolved_unit_id: target_ids,
            },
        )

    def with_phase_complete(self, *, skipped_unit_ids: tuple[str, ...] = ()) -> Self:
        if self.active_selection is not None:
            raise GameLifecycleError("Charge completion requires no active selection.")
        if self.move_pending_distance_state() is not None:
            raise GameLifecycleError("Charge completion requires no pending charge movement.")
        skipped_ids = _validate_identifier_tuple("skipped_unit_ids", skipped_unit_ids)
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=True,
            selected_unit_ids=tuple(sorted({*self.selected_unit_ids, *skipped_ids})),
            active_selection=None,
            distance_states=self.distance_states,
            declared_target_unit_instance_ids_by_unit=(
                self.declared_target_unit_instance_ids_by_unit
            ),
        )

    def move_pending_distance_state(self) -> ChargeDistanceState | None:
        if self.active_selection is None:
            return None
        for distance_state in reversed(self.distance_states):
            if (
                distance_state.roll_result.request.unit_instance_id
                == self.active_selection.unit_instance_id
                and distance_state.roll_result.status == CHARGE_MOVE_PENDING_STATUS
            ):
                return distance_state
        return None

    def to_payload(self) -> ChargePhaseStatePayload:
        return {
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "phase_complete": self.phase_complete,
            "selected_unit_ids": list(self.selected_unit_ids),
            "active_selection": (
                None if self.active_selection is None else self.active_selection.to_payload()
            ),
            "distance_states": [distance.to_payload() for distance in self.distance_states],
            "declared_target_unit_instance_ids_by_unit": {
                unit_id: list(target_ids)
                for unit_id, target_ids in sorted(
                    self.declared_target_unit_instance_ids_by_unit.items()
                )
            },
        }

    @classmethod
    def from_payload(cls, payload: ChargePhaseStatePayload) -> Self:
        selection_payload = payload["active_selection"]
        return cls(
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            phase_complete=payload["phase_complete"],
            selected_unit_ids=tuple(payload["selected_unit_ids"]),
            active_selection=(
                None
                if selection_payload is None
                else ChargingUnitSelection.from_payload(selection_payload)
            ),
            distance_states=tuple(
                ChargeDistanceState.from_payload(distance)
                for distance in payload["distance_states"]
            ),
            declared_target_unit_instance_ids_by_unit={
                unit_id: tuple(target_ids)
                for unit_id, target_ids in payload[
                    "declared_target_unit_instance_ids_by_unit"
                ].items()
            },
        )


@dataclass(frozen=True, slots=True)
class ChargePhaseHandler:
    ruleset_descriptor: RulesetDescriptor | None = None
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
        if (
            self.ruleset_descriptor is not None
            and type(self.ruleset_descriptor) is not RulesetDescriptor
        ):
            raise GameLifecycleError(
                "ChargePhaseHandler ruleset_descriptor must be a RulesetDescriptor."
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

    def begin_phase(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus:
        del reaction_queue
        _validate_charge_phase_state(state)
        charge_state = _ensure_charge_phase_state(state=state)
        pending_distance_state = charge_state.move_pending_distance_state()
        if pending_distance_state is not None:
            return _request_charge_move_proposal(
                state=state,
                decisions=decisions,
                charge_state=charge_state,
                roll_result=pending_distance_state.roll_result,
            )
        if charge_state.active_selection is not None:
            raise GameLifecycleError("Charge active_selection requires pending charge movement.")
        move_completed_status = resolve_charge_move_completed_hooks(
            state=state,
            decisions=decisions,
            handler=self,
            movement_action=CHARGE_MOVE_ACTION,
        )
        if move_completed_status is not None:
            return move_completed_status
        if charge_state.phase_complete:
            decisions.event_log.append(
                "charge_phase_completed",
                _charge_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_CHARGE_PHASE_STATUS,
                ),
            )
            return LifecycleStatus.advanced(
                stage=GameLifecycleStage.BATTLE,
                payload=_charge_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_CHARGE_PHASE_STATUS,
                ),
            )

        legal_unit_ids = _legal_charging_unit_ids(
            state=state,
            charge_state=charge_state,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            charge_target_restriction_hooks=self.charge_target_restriction_hooks,
        )
        if not legal_unit_ids:
            state.replace_charge_phase_state(charge_state.with_phase_complete())
            decisions.event_log.append(
                "charge_phase_completed",
                _charge_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_CHARGE_PHASE_STATUS,
                ),
            )
            return LifecycleStatus.advanced(
                stage=GameLifecycleStage.BATTLE,
                payload=_charge_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_CHARGE_PHASE_STATUS,
                ),
            )

        request = DecisionRequest(
            request_id=state.next_decision_request_id(),
            decision_type=SELECT_CHARGING_UNIT_DECISION_TYPE,
            actor_id=_active_player_id(state),
            payload=validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.CHARGE.value,
                    "active_player_id": _active_player_id(state),
                }
            ),
            options=_charging_unit_options(
                state=state,
                unit_ids=legal_unit_ids,
                include_complete=True,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                charge_target_restriction_hooks=self.charge_target_restriction_hooks,
            ),
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "charging_unit_selection_requested",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": _active_player_id(state),
                    "phase": BattlePhase.CHARGE.value,
                    "request_id": request.request_id,
                    "legal_unit_count": len(legal_unit_ids),
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": BattlePhase.CHARGE.value,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "legal_unit_count": len(legal_unit_ids),
            },
        )

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


def invalid_charging_unit_selection_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
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
    if selected_unit_id != result.selected_option_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Charging unit selection payload does not match the selected option.",
            payload={
                "invalid_reason": "invalid_charging_unit_result",
                "field": "unit_instance_id",
            },
        )
    if selected_unit_id not in current_legal_ids:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Charging unit selection is no longer legal.",
            payload={
                "invalid_reason": "invalid_charging_unit_result",
                "field": "unit_instance_id",
            },
        )
    return None


def invalid_charge_move_proposal_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> LifecycleStatus | None:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    parsed = _parse_charge_move_proposal_submission_or_invalid(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if isinstance(parsed, LifecycleStatus):
        return parsed
    submitted_proposal_request, proposal = parsed
    proposal_validation = proposal.validation_result_for_request(submitted_proposal_request)
    if not proposal_validation.is_valid:
        return _reject_invalid_charge_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=proposal_validation,
            message="Charge Move proposal does not match the pending request.",
        )
    charge_state = state.charge_phase_state
    if charge_state is None:
        return _reject_invalid_charge_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="charge_phase_state_missing",
                message="Charge Move proposal has no active charge phase state.",
                field="charge_phase_state",
            ),
            message="Charge Move proposal has no active phase state.",
        )
    pending_distance = charge_state.move_pending_distance_state()
    if pending_distance is None:
        return _reject_invalid_charge_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="charge_distance_state_missing",
                message="Charge Move proposal has no pending charge distance state.",
                field="charge_phase_state",
            ),
            message="Charge Move proposal has no pending distance state.",
        )
    if pending_distance.roll_result.request.unit_instance_id != proposal.unit_instance_id:
        return _reject_invalid_charge_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="proposal_unit_drift",
                message="Charge Move proposal unit does not match the pending charge roll.",
                field="unit_instance_id",
            ),
            message="Charge Move proposal unit drifted.",
        )
    current_reachable = _reachable_charge_target_distances(
        state=state,
        unit_instance_id=proposal.unit_instance_id,
        maximum_distance_inches=pending_distance.roll_result.value,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks
        or ChargeTargetRestrictionHookRegistry.empty(),
    )
    requested_reachable = _payload_distance_map(
        _proposal_context(proposal_request),
        key="reachable_target_distances_inches",
    )
    if current_reachable != requested_reachable:
        return _reject_invalid_charge_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="charge_reachable_targets_drift",
                message="Charge Move reachable target snapshot no longer matches state.",
                field="reachable_target_unit_instance_ids",
                status="stale",
            ),
            message="Charge Move reachable target snapshot is stale.",
        )
    current_required = _required_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=proposal.unit_instance_id,
        reachable_target_unit_instance_ids=tuple(current_reachable),
    )
    requested_required = _payload_optional_identifier_list(
        _proposal_context(proposal_request),
        key=CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
    )
    if current_required != requested_required:
        return _reject_invalid_charge_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="charge_required_targets_drift",
                message="Charge Move required target snapshot no longer matches state.",
                field=CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
                status="stale",
            ),
            message="Charge Move required target snapshot is stale.",
        )
    if proposal.witness is not None:
        witness_validation = _charge_witness_matches_current_unit_status(
            state=state,
            proposal_request=proposal_request,
            proposal=proposal,
        )
        if witness_validation is not None:
            return _reject_invalid_charge_proposal(
                state=state,
                decisions=decisions,
                result=result,
                proposal_validation=witness_validation,
                message="Charge Move witness does not match the current unit.",
            )
    return None


def invalid_charge_declaration_grant_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    charge_declaration_hooks: ChargeDeclarationHookRegistry,
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
                phase_body_status=_COMPLETE_CHARGE_PHASE_STATUS,
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
    selection = ChargingUnitSelection(
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
            selection=selection,
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
    selection: ChargingUnitSelection,
    grant: ChargeDeclarationGrant,
) -> EffectExpiration:
    if grant.unit_effect_expiration == "end_phase":
        return EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=BattlePhaseKind.CHARGE,
            player_id=selection.player_id,
        )
    if grant.unit_effect_expiration == "end_turn":
        return EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=selection.player_id,
        )
    raise GameLifecycleError("Charge declaration grant effect expiration is unsupported.")


def _resolve_charge_roll(
    *,
    state: GameState,
    selection: ChargingUnitSelection,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    unit = _unit_for_selection(state=state, selection=selection)
    roll_modifiers = catalog_charge_roll_modifiers_for_unit(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=_current_model_instance_ids_for_charge_unit(
            state=state,
            unit=unit,
        ),
    )
    roll_modifiers = runtime_modifier_registry.charge_roll_modifiers(
        ChargeRollModifierContext(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            current_roll_modifiers=roll_modifiers,
        )
    )
    roll_request = ChargeRollRequest(
        request_id=f"charge-roll:{selection.result_id}",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=selection.player_id,
        unit_instance_id=selection.unit_instance_id,
        source_decision_request_id=selection.request_id,
        source_decision_result_id=selection.result_id,
        roll_modifiers=roll_modifiers,
    )
    roll_state = DiceRollManager(state.game_id, event_log=decisions.event_log).roll(
        roll_request.spec
    )
    reroll_permission = _charge_reroll_permission_for_unit(
        state=state,
        player_id=selection.player_id,
        unit_instance_id=selection.unit_instance_id,
        ability_index=ability_index,
    )
    if reroll_permission is not None:
        reroll_request = _charge_roll_reroll_request(
            state=state,
            decisions=decisions,
            roll_request=roll_request,
            roll_state=roll_state,
            permission=reroll_permission,
        )
        decisions.request_decision(reroll_request)
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=reroll_request,
            payload={
                "phase": BattlePhase.CHARGE.value,
                "phase_body_status": "charge_roll_reroll_pending",
                "battle_round": state.battle_round,
                "active_player_id": selection.player_id,
                "unit_instance_id": selection.unit_instance_id,
            },
        )
    return _resolve_charge_roll_state(
        state=state,
        selection=selection,
        decisions=decisions,
        roll_request=roll_request,
        roll_state=roll_state,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )


def _resolve_charge_roll_state(
    *,
    state: GameState,
    selection: ChargingUnitSelection,
    decisions: DecisionController,
    roll_request: ChargeRollRequest,
    roll_state: DiceRollState,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    reachable_distances = _reachable_charge_target_distances(
        state=state,
        unit_instance_id=selection.unit_instance_id,
        maximum_distance_inches=roll_state.current_total,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )
    roll_result = ChargeRollResult.from_roll_state(
        request=roll_request,
        roll_state=roll_state,
        reachable_target_distances_inches=reachable_distances,
    )
    charge_state = state.charge_phase_state
    if charge_state is None:
        raise GameLifecycleError("Charge roll requires charge_phase_state.")
    state.replace_charge_phase_state(charge_state.with_charge_roll_result(roll_result))
    decisions.event_log.append(
        "charge_roll_resolved",
        phase15a_charge_roll_payload(roll_result=roll_result),
    )
    if not roll_result.move_available:
        decisions.event_log.append(
            "charge_no_move_possible",
            phase15a_charge_roll_payload(roll_result=roll_result),
        )
        return None
    decisions.event_log.append(
        "charge_move_required",
        phase15a_charge_roll_payload(roll_result=roll_result),
    )
    return _request_charge_move_proposal(
        state=state,
        decisions=decisions,
        charge_state=charge_state,
        roll_result=roll_result,
    )


def _charge_roll_reroll_request(
    *,
    state: GameState,
    decisions: DecisionController,
    roll_request: ChargeRollRequest,
    roll_state: DiceRollState,
    permission: RerollPermission,
) -> DecisionRequest:
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    return manager.build_reroll_request(
        roll_state,
        request_id=state.next_decision_request_id(),
        actor_id=roll_request.player_id,
        permission=permission,
        ignored_reroll_forbidden_rule_ids=(CHARGE_ROLL_COMMAND_REROLL_FORBIDDEN_RULE_ID,),
        extra_payload={
            "charge_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.CHARGE.value,
                "unit_instance_id": roll_request.unit_instance_id,
                "charge_roll_request": validate_json_value(roll_request.to_payload()),
                "charge_roll_state": validate_json_value(roll_state.to_payload()),
            }
        },
    )


def _apply_charge_roll_reroll_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    charge_state = state.charge_phase_state
    if charge_state is None or charge_state.active_selection is None:
        raise GameLifecycleError("Charge reroll requires active charge selection.")
    selection = charge_state.active_selection
    if result.actor_id != selection.player_id:
        raise GameLifecycleError("Charge reroll actor must match charging player.")
    record = decisions.record_for_result(result)
    request_payload = _decision_payload_object(record.request.payload)
    context_payload = _payload_object(request_payload, key="charge_context")
    unit_instance_id = _payload_string(context_payload, key="unit_instance_id")
    if unit_instance_id != selection.unit_instance_id:
        raise GameLifecycleError("Charge reroll unit must match active charge selection.")
    roll_request_payload = _payload_object(context_payload, key="charge_roll_request")
    initial_roll_payload = _payload_object(context_payload, key="charge_roll_state")
    roll_request = ChargeRollRequest.from_payload(
        cast(ChargeRollRequestPayload, roll_request_payload)
    )
    if roll_request.unit_instance_id != selection.unit_instance_id:
        raise GameLifecycleError("Charge reroll request unit drift.")
    initial_roll_state = DiceRollState.from_payload(
        cast(DiceRollStatePayload, initial_roll_payload)
    )
    rerolled_state = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
    ).resolve_reroll(
        initial_roll_state,
        request=record.request,
        result=result,
        record_decision=False,
    )
    return _resolve_charge_roll_state(
        state=state,
        selection=selection,
        decisions=decisions,
        roll_request=roll_request,
        roll_state=rerolled_state,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )


def _request_charge_move_proposal(
    *,
    state: GameState,
    decisions: DecisionController,
    charge_state: ChargePhaseState,
    roll_result: ChargeRollResult,
) -> LifecycleStatus:
    if charge_state.active_selection is None:
        raise GameLifecycleError("Charge Move proposal requires active_selection.")
    required_target_ids = _required_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=roll_result.request.unit_instance_id,
        reachable_target_unit_instance_ids=tuple(roll_result.reachable_target_distances_inches),
    )
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=charge_state.active_player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.CHARGE.value,
        unit_instance_id=roll_result.request.unit_instance_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id=charge_state.active_selection.request_id,
        source_decision_result_id=charge_state.active_selection.result_id,
        movement_phase_action=CHARGE_MOVE_ACTION,
        context={
            "source_selected_option_id": charge_state.active_selection.unit_instance_id,
            "movement_mode": MovementMode.CHARGE.value,
            "maximum_distance_inches": roll_result.value,
            "reachable_target_unit_instance_ids": list(
                roll_result.reachable_target_distances_inches
            ),
            "reachable_target_distances_inches": dict(
                sorted(roll_result.reachable_target_distances_inches.items())
            ),
            CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: list(required_target_ids),
            "charge_roll": validate_json_value(roll_result.to_payload()),
        },
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "charge_move_proposal_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": charge_state.active_player_id,
                "phase": BattlePhase.CHARGE.value,
                "unit_instance_id": roll_result.request.unit_instance_id,
                "movement_phase_action": CHARGE_MOVE_ACTION,
                "movement_mode": MovementMode.CHARGE.value,
                "proposal_kind": ProposalKind.CHARGE_MOVE.value,
                "request_id": request.request_id,
                "source_decision_request_id": charge_state.active_selection.request_id,
                "source_decision_result_id": charge_state.active_selection.result_id,
                "maximum_distance_inches": roll_result.value,
                "reachable_target_unit_instance_ids": list(
                    roll_result.reachable_target_distances_inches
                ),
                CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: list(required_target_ids),
                "phase_body_status": _CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.CHARGE.value,
            "phase_body_status": _CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS,
            "battle_round": state.battle_round,
            "active_player_id": charge_state.active_player_id,
            "unit_instance_id": roll_result.request.unit_instance_id,
            "movement_phase_action": CHARGE_MOVE_ACTION,
            "proposal_kind": ProposalKind.CHARGE_MOVE.value,
            "maximum_distance_inches": roll_result.value,
            "reachable_target_unit_instance_ids": list(
                roll_result.reachable_target_distances_inches
            ),
            CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: list(required_target_ids),
        },
    )


def _request_charge_move_proposal_retry(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal_request: MovementProposalRequest,
    rejected_result: DecisionResult,
) -> DecisionRequest:
    retry_proposal = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.actor_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.CHARGE.value,
        unit_instance_id=proposal_request.unit_instance_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id=proposal_request.source_decision_request_id,
        source_decision_result_id=proposal_request.source_decision_result_id,
        movement_phase_action=CHARGE_MOVE_ACTION,
        context=dict(proposal_request.context or {}),
    )
    request = retry_proposal.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "charge_move_proposal_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": BattlePhase.CHARGE.value,
                "unit_instance_id": proposal_request.unit_instance_id,
                "movement_phase_action": CHARGE_MOVE_ACTION,
                "movement_mode": MovementMode.CHARGE.value,
                "proposal_kind": ProposalKind.CHARGE_MOVE.value,
                "request_id": request.request_id,
                "source_decision_request_id": proposal_request.source_decision_request_id,
                "source_decision_result_id": proposal_request.source_decision_result_id,
                "previous_proposal_request_id": proposal_request.request_id,
                "rejected_result_id": rejected_result.result_id,
                "phase_body_status": _CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS,
            }
        ),
    )
    return request


def _apply_charge_move_proposal_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
    ability_index: AbilityCatalogIndex,
) -> LifecycleStatus | None:
    _validate_charge_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Charge Move proposal actor must be the active player.")
    charge_state = state.charge_phase_state
    if charge_state is None or charge_state.active_selection is None:
        raise GameLifecycleError("Charge Move proposal requires active_selection.")
    record = decisions.record_for_result(result)
    parsed = _parse_charge_move_proposal_submission_or_invalid(
        state=state,
        request=record.request,
        result=result,
        decisions=decisions,
    )
    if isinstance(parsed, LifecycleStatus):
        return parsed
    proposal_request, proposal = parsed
    proposal_validation = proposal.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid:
        return _reject_invalid_charge_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=proposal_validation,
            message="Charge Move proposal does not match the pending request.",
        )
    pending_distance = charge_state.move_pending_distance_state()
    if pending_distance is None:
        raise GameLifecycleError("Charge Move proposal requires pending distance state.")
    if proposal.is_no_move_choice:
        state.replace_charge_phase_state(
            charge_state.with_charge_move_resolved(proposal.unit_instance_id)
        )
        decisions.event_log.append(
            "charge_move_declined",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": BattlePhase.CHARGE.value,
                    "unit_instance_id": proposal.unit_instance_id,
                    "request_id": result.request_id,
                    "result_id": result.result_id,
                    "proposal_request_id": proposal_request.request_id,
                    "phase_body_status": _CHARGE_MOVE_DECLINED_STATUS,
                    "proposal_validation": proposal_validation.to_payload(),
                }
            ),
        )
        return None
    if proposal.witness is None:
        raise GameLifecycleError("Validated Charge Move proposal must include a witness.")
    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(proposal.unit_instance_id)
    resolution = resolve_charge_move(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        selected_target_unit_instance_ids=proposal.charge_target_unit_instance_ids,
        maximum_distance_inches=pending_distance.roll_result.value,
        path_witness=proposal.witness,
        hover_mode_states=tuple(state.hover_mode_states),
        unit_persisting_effects=tuple(state.persisting_effects_for_unit(proposal.unit_instance_id)),
        ability_index=ability_index,
    )
    violation_code = _charge_move_violation_code(
        resolution=resolution,
        ruleset_descriptor=ruleset_descriptor,
        maximum_distance_inches=pending_distance.roll_result.value,
    )
    if violation_code is not None:
        return _reject_invalid_charge_move_resolution(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=proposal_validation,
            resolution=resolution,
            violation_code=violation_code,
            message=_charge_move_invalid_message(violation_code),
        )
    transition_batch = resolution.transition_batch(before=unit_placement)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Charge Move proposal requires battlefield_state.")
    state.replace_battlefield_state(
        battlefield_state.with_unit_placement(resolution.attempted_placement)
    )
    state.replace_charge_phase_state(
        charge_state.with_charge_move_resolved(
            proposal.unit_instance_id,
            selected_target_unit_instance_ids=resolution.selected_target_unit_instance_ids,
        )
    )
    effect = _record_fights_first_effect_if_needed(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        proposal_request=proposal_request,
        result=result,
        unit_instance_id=proposal.unit_instance_id,
    )
    payload = _charge_move_completed_payload(
        state=state,
        result=result,
        proposal_request=proposal_request,
        proposal_validation=proposal_validation,
        resolution=resolution,
        transition_batch=transition_batch,
        persisting_effect=effect,
    )
    decisions.event_log.append("charge_move_completed", payload)
    return None


def resolve_charge_move(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    selected_target_unit_instance_ids: tuple[str, ...],
    maximum_distance_inches: int,
    path_witness: PathWitness,
    hover_mode_states: tuple[HoverModeState, ...] = (),
    terrain: tuple[TerrainVolume, ...] = (),
    unit_persisting_effects: tuple[PersistingEffect, ...] = (),
    ability_index: AbilityCatalogIndex | None = None,
) -> ChargeMoveResolution:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Charge Move requires a BattlefieldScenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Charge Move requires a RulesetDescriptor.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Charge Move unit_placement must be a UnitPlacement.")
    if type(path_witness) is not PathWitness:
        raise GameLifecycleError("Charge Move requires a PathWitness.")
    if type(maximum_distance_inches) is not int:
        raise GameLifecycleError("Charge Move maximum distance must be an int.")
    if maximum_distance_inches < 2 or maximum_distance_inches > 12:
        raise GameLifecycleError("Charge Move maximum distance must be a 2D6 value.")
    target_ids = _validate_identifier_tuple(
        "selected_target_unit_instance_ids",
        selected_target_unit_instance_ids,
    )
    _validate_charge_witness_matches_unit(
        witness=path_witness,
        unit_placement=unit_placement,
    )
    unit = scenario.unit_instance_for_placement(unit_placement)
    aircraft_policy = AircraftMovementPolicy.from_unit(
        unit=unit,
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_state=_hover_mode_state_for_unit(
            hover_mode_states=hover_mode_states,
            unit_instance_id=unit_placement.unit_instance_id,
        ),
    )
    moved_placements: list[ModelPlacement] = []
    for placement in unit_placement.model_placements:
        moved_placements.append(
            placement.with_pose(path_witness.final_pose_for_model(placement.model_instance_id))
        )
    attempted_placement = unit_placement.with_model_placements(tuple(moved_placements))
    terrain_features = scenario.battlefield_state.terrain_features
    terrain_volumes = (*terrain, *_terrain_volumes_for_features(terrain_features))
    path_validation_results: list[PathValidationResult] = []
    terrain_path_legality_results: list[TerrainPathLegalityResult] = []
    model_movements: list[JsonValue] = []
    enemy_vehicle_monster_model_ids = enemy_vehicle_monster_model_ids_for_player(
        scenario=scenario,
        player_id=unit_placement.player_id,
    )
    for placement in unit_placement.model_placements:
        model = scenario.model_instance_for_placement(placement)
        moving_model = geometry_model_for_placement(model=model, placement=placement)
        model_witness = PathWitness.for_paths(
            (
                (
                    placement.model_instance_id,
                    path_witness.poses_for_model(placement.model_instance_id),
                ),
            )
        )
        legality_context = MovementLegalityContext.from_keywords(
            keywords=aircraft_policy.effective_keywords,
            ruleset_descriptor=ruleset_descriptor,
            movement_mode=MovementMode.CHARGE,
            movement_phase_action=None,
            displacement_kind=ModelDisplacementKind.CHARGE_MOVE,
            ability_index=ability_index,
            unit=unit,
            model_instance_id=placement.model_instance_id,
            current_model_instance_ids=tuple(
                model_placement.model_instance_id
                for model_placement in unit_placement.model_placements
            ),
            unit_persisting_effects=unit_persisting_effects,
            owner_player_id=unit_placement.player_id,
        )
        path_context = legality_context.to_path_validation_context(
            moving_model=moving_model,
            witness=model_witness,
            battlefield_width_inches=scenario.battlefield_state.battlefield_width_inches,
            battlefield_depth_inches=scenario.battlefield_state.battlefield_depth_inches,
            friendly_models=_friendly_geometry_models_for_charge_path(
                scenario=scenario,
                unit_placement=unit_placement,
                attempted_placement=attempted_placement,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_models=_enemy_geometry_models_for_player(
                scenario=scenario,
                player_id=unit_placement.player_id,
            ),
            terrain=(),
            friendly_vehicle_monster_model_ids=_friendly_vehicle_monster_model_ids(
                scenario=scenario,
                player_id=unit_placement.player_id,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_vehicle_monster_model_ids=enemy_vehicle_monster_model_ids,
            movement_distance_budget_inches=float(maximum_distance_inches),
        )
        path_result = charge_path_context_with_rule_effect_permissions(
            path_context,
            unit_persisting_effects=unit_persisting_effects,
            owner_player_id=unit_placement.player_id,
            enemy_vehicle_monster_model_ids=enemy_vehicle_monster_model_ids,
        ).validate()
        terrain_result = legality_context.to_terrain_path_legality_context(
            moving_model=moving_model,
            witness=model_witness,
            terrain=terrain_volumes,
            terrain_features=terrain_features,
        ).validate()
        path_validation_results.append(path_result)
        terrain_path_legality_results.append(terrain_result)
        model_movements.append(
            validate_json_value(
                {
                    "model_instance_id": placement.model_instance_id,
                    "movement_mode": MovementMode.CHARGE.value,
                    "maximum_distance_inches": maximum_distance_inches,
                    "start_pose": placement.pose.to_payload(),
                    "end_pose": path_witness.final_pose_for_model(
                        placement.model_instance_id
                    ).to_payload(),
                    "movement_distance_witness": (
                        None
                        if path_result.movement_distance_witness is None
                        else path_result.movement_distance_witness.to_payload()
                    ),
                    "path_validation_result": path_result.to_payload(),
                    "terrain_path_legality_result": terrain_result.to_payload(),
                }
            )
        )
    _, coherency_result, rollback_record = resolve_unit_movement_endpoint_coherency(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        before=unit_placement,
        attempted=attempted_placement,
        displacement_kind=ModelDisplacementKind.CHARGE_MOVE,
    )
    endpoint_witness = _charge_endpoint_witness(
        scenario=scenario,
        before=unit_placement,
        after=attempted_placement,
        selected_target_unit_instance_ids=target_ids,
        ruleset_descriptor=ruleset_descriptor,
    )
    movement_payload = _validate_json_object(
        "ChargeMoveResolution movement_payload",
        {
            "movement_mode": MovementMode.CHARGE.value,
            "maximum_distance_inches": maximum_distance_inches,
            "selected_target_unit_instance_ids": list(target_ids),
            "model_movements": model_movements,
            "path_validation_results": [result.to_payload() for result in path_validation_results],
            "terrain_path_legality_results": [
                result.to_payload() for result in terrain_path_legality_results
            ],
            "coherency_result": coherency_result.to_payload(),
            "endpoint_witness": endpoint_witness.to_payload(),
            "fly_charge_policy": {
                "has_fly": "FLY" in aircraft_policy.effective_keywords,
                "uses_aircraft_rules": aircraft_policy.uses_aircraft_rules,
                "can_declare_charge": aircraft_policy.can_declare_charge,
            },
        },
    )
    if rollback_record is not None:
        movement_payload["rollback_record"] = validate_json_value(rollback_record.to_payload())
    return ChargeMoveResolution(
        unit_instance_id=unit_placement.unit_instance_id,
        selected_target_unit_instance_ids=target_ids,
        attempted_placement=attempted_placement,
        witness=path_witness,
        endpoint_witness=endpoint_witness,
        path_validation_results=tuple(path_validation_results),
        terrain_path_legality_results=tuple(terrain_path_legality_results),
        coherency_result=coherency_result,
        rollback_record=rollback_record,
        movement_payload=movement_payload,
    )


def _legal_charging_unit_ids(
    *,
    state: GameState,
    charge_state: ChargePhaseState,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> tuple[str, ...]:
    active_player_id = _active_player_id(state)
    placed_unit_ids = _active_player_placed_unit_ids(state=state, player_id=active_player_id)
    legal_ids: list[str] = []
    for unit_id in placed_unit_ids:
        ineligible_reason = _charge_unit_ineligibility_reason(
            state=state,
            unit_instance_id=unit_id,
            ruleset_descriptor=ruleset_descriptor,
            charge_state=charge_state,
            ignore_already_selected=False,
            charge_target_restriction_hooks=charge_target_restriction_hooks,
        )
        if ineligible_reason is None:
            legal_ids.append(unit_id)
    return tuple(sorted(legal_ids))


def _charge_unit_ineligibility_reason(
    *,
    state: GameState,
    unit_instance_id: str,
    ruleset_descriptor: RulesetDescriptor,
    charge_state: ChargePhaseState,
    ignore_already_selected: bool,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> str | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    if not ignore_already_selected and requested_unit_id in charge_state.selected_unit_ids:
        return "charge_unit_already_selected"
    if requested_unit_id not in _active_player_placed_unit_ids(
        state=state,
        player_id=charge_state.active_player_id,
    ):
        return "charge_unit_off_battlefield"
    advanced_state = state.advanced_unit_state_for_unit(
        player_id=charge_state.active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=requested_unit_id,
    )
    if (
        advanced_state is not None
        and ruleset_descriptor.charge_policy.forbids_advance
        and not advanced_state.can_declare_charge
        and not charge_after_advance_allowed_by_effects(
            state=state,
            unit_instance_id=requested_unit_id,
        )
    ):
        return "charge_unit_advanced"
    fell_back_state = state.fell_back_unit_state_for_unit(
        player_id=charge_state.active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=requested_unit_id,
    )
    if (
        fell_back_state is not None
        and ruleset_descriptor.charge_policy.forbids_fall_back
        and not fell_back_state.can_declare_charge
        and not _charge_after_fall_back_allowed_by_effects(
            state=state,
            unit_instance_id=requested_unit_id,
        )
    ):
        return "charge_unit_fell_back"
    if not _aircraft_policy_for_charge_unit(
        state=state,
        unit_instance_id=requested_unit_id,
        ruleset_descriptor=ruleset_descriptor,
    ).can_declare_charge:
        return "charge_unit_aircraft"
    if _charge_forbidden_by_effects(state=state, unit_instance_id=requested_unit_id):
        return "charge_unit_forbidden_by_effect"
    if ruleset_descriptor.charge_policy.requires_unengaged_unit and _unit_is_engaged(
        state=state,
        unit_instance_id=requested_unit_id,
        player_id=charge_state.active_player_id,
        ruleset_descriptor=ruleset_descriptor,
    ):
        return "charge_unit_engaged"
    candidates = _charge_target_candidates(
        state=state,
        unit_instance_id=requested_unit_id,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )
    if not any(candidate.is_legal for candidate in candidates):
        return "charge_unit_no_legal_targets"
    return None


def _charge_forbidden_by_effects(*, state: GameState, unit_instance_id: str) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for effect in state.persisting_effects_for_unit(requested_unit_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("charge_forbidden") is True and not (
            type(payload.get("effect_kind")) is str
            and conditional_charge_after_movement_action_allowed(
                state=state,
                rules_unit_instance_id=requested_unit_id,
                movement_action_effect_kind=str(payload["effect_kind"]),
            )
        ):
            return True
    return False


def _charge_after_fall_back_allowed_by_effects(
    *,
    state: GameState,
    unit_instance_id: str,
) -> bool:
    for effect in state.persisting_effects_for_unit(unit_instance_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") == CHARGE_AFTER_FALL_BACK_EFFECT_KIND:
            return True
    return False


def _required_charge_target_unit_instance_ids(
    *,
    state: GameState,
    unit_instance_id: str,
    reachable_target_unit_instance_ids: tuple[str, ...],
) -> tuple[str, ...]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    reachable_ids = set(
        _validate_identifier_tuple(
            "reachable_target_unit_instance_ids",
            reachable_target_unit_instance_ids,
        )
    )
    if not reachable_ids:
        return ()
    required_ids: set[str] = set()
    for effect in state.persisting_effects_for_unit(requested_unit_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        for candidate_payload in _charge_target_requirement_payloads(payload):
            required_ids.update(
                required_id
                for required_id in _payload_identifier_list(
                    candidate_payload,
                    key=CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
                )
                if required_id in reachable_ids
            )
    return tuple(sorted(required_ids))


def _charge_target_requirement_payloads(
    effect_payload: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    payloads: list[Mapping[str, object]] = []
    if CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY in effect_payload:
        payloads.append(effect_payload)
    raw_source_payload = effect_payload.get("source_payload")
    if isinstance(raw_source_payload, dict) and (
        CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY in raw_source_payload
    ):
        payloads.append(cast(Mapping[str, object], raw_source_payload))
    return tuple(payloads)


def _charge_target_restriction(
    *,
    state: GameState,
    charging_unit_instance_id: str,
    target_unit_instance_id: str,
    registry: ChargeTargetRestrictionHookRegistry | None,
) -> TargetRestriction | None:
    if registry is None:
        return None
    if type(registry) is not ChargeTargetRestrictionHookRegistry:
        raise GameLifecycleError("Charge target restriction requires a registry.")
    restrictions = registry.restrictions_for(
        ChargeTargetRestrictionContext(
            state=state,
            player_id=_active_player_id(state),
            battle_round=state.battle_round,
            charging_unit_instance_id=charging_unit_instance_id,
            target_unit_instance_id=target_unit_instance_id,
        )
    )
    return restrictions[0] if restrictions else None


def _charge_target_candidates(
    *,
    state: GameState,
    unit_instance_id: str,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> tuple[ChargeTargetCandidate, ...]:
    scenario = _battlefield_scenario(state)
    max_range = ruleset_descriptor.charge_policy.max_declaration_range_inches
    candidates: list[ChargeTargetCandidate] = []
    for target_id in _enemy_placed_unit_ids(state=state, player_id=_active_player_id(state)):
        distance = _closest_unit_distance_inches(
            scenario=scenario,
            source_unit_instance_id=unit_instance_id,
            target_unit_instance_id=target_id,
        )
        is_legal = distance <= max_range
        restriction = _charge_target_restriction(
            state=state,
            charging_unit_instance_id=unit_instance_id,
            target_unit_instance_id=target_id,
            registry=charge_target_restriction_hooks,
        )
        violation_code: str | None
        if is_legal and restriction is not None:
            is_legal = False
            violation_code = restriction.violation_code
        else:
            violation_code = None if is_legal else "target_out_of_declaration_range"
        candidates.append(
            ChargeTargetCandidate(
                target_unit_instance_id=target_id,
                closest_distance_inches=distance,
                is_legal=is_legal,
                violation_code=violation_code,
            )
        )
    return tuple(sorted(candidates, key=lambda candidate: candidate.target_unit_instance_id))


def _reachable_charge_target_distances(
    *,
    state: GameState,
    unit_instance_id: str,
    maximum_distance_inches: int,
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


def _closest_unit_distance_inches(
    *,
    scenario: BattlefieldScenario,
    source_unit_instance_id: str,
    target_unit_instance_id: str,
) -> float:
    source_models = _geometry_models_for_unit(
        scenario=scenario,
        unit_instance_id=source_unit_instance_id,
    )
    target_models = _geometry_models_for_unit(
        scenario=scenario,
        unit_instance_id=target_unit_instance_id,
    )
    if not source_models or not target_models:
        raise GameLifecycleError("Charge distance requires placed models.")
    return min(
        source_model.range_to(target_model)
        for source_model in source_models
        for target_model in target_models
    )


def _closest_distance_between_model_groups(
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
) -> float:
    if not first_models or not second_models:
        raise GameLifecycleError("Charge distance requires non-empty model groups.")
    return min(
        first_model.range_to(second_model)
        for first_model in first_models
        for second_model in second_models
    )


def _unit_is_engaged(
    *,
    state: GameState,
    unit_instance_id: str,
    player_id: str,
    ruleset_descriptor: RulesetDescriptor,
) -> bool:
    scenario = _battlefield_scenario(state)
    source_models = _geometry_models_for_unit(
        scenario=scenario,
        unit_instance_id=unit_instance_id,
    )
    enemy_models = tuple(
        model
        for enemy_unit_id in _enemy_placed_unit_ids(state=state, player_id=player_id)
        for model in _geometry_models_for_unit(
            scenario=scenario,
            unit_instance_id=enemy_unit_id,
        )
    )
    policy = ruleset_descriptor.engagement_policy
    return any(
        source_model.is_within_engagement_range(
            enemy_model,
            horizontal_inches=policy.horizontal_inches,
            vertical_inches=policy.vertical_inches,
        )
        for source_model in source_models
        for enemy_model in enemy_models
    )


def _aircraft_policy_for_charge_unit(
    *,
    state: GameState,
    unit_instance_id: str,
    ruleset_descriptor: RulesetDescriptor,
) -> AircraftMovementPolicy:
    scenario = _battlefield_scenario(state)
    placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    return AircraftMovementPolicy.from_unit(
        unit=scenario.unit_instance_for_placement(placement),
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_state=_hover_mode_state_for_unit(
            hover_mode_states=tuple(state.hover_mode_states),
            unit_instance_id=unit_instance_id,
        ),
    )


def _hover_mode_state_for_unit(
    *,
    hover_mode_states: tuple[HoverModeState, ...],
    unit_instance_id: str,
) -> HoverModeState | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    found: HoverModeState | None = None
    for hover_mode_state in hover_mode_states:
        if type(hover_mode_state) is not HoverModeState:
            raise GameLifecycleError("hover_mode_states must contain HoverModeState values.")
        if hover_mode_state.unit_instance_id != requested_unit_id:
            continue
        if found is not None:
            raise GameLifecycleError("hover_mode_states must be unique by unit.")
        found = hover_mode_state
    return found if found is not None and found.active else None


def _geometry_models_for_unit(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    try:
        placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError("Charge unit placement is unavailable.") from exc
    unit = scenario.unit_instance_for_placement(placement)
    models: list[GeometryModel] = []
    for model_placement in placement.model_placements:
        model_instance = None
        for model in unit.own_models:
            if model.model_instance_id == model_placement.model_instance_id:
                model_instance = model
                break
        if model_instance is None:
            raise GameLifecycleError("Charge model placement is invalid.")
        models.append(geometry_model_for_placement(model=model_instance, placement=model_placement))
    return tuple(models)


def _geometry_models_for_unit_placement(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> tuple[GeometryModel, ...]:
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for placement in unit_placement.model_placements
    )


def _enemy_geometry_models_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
) -> tuple[GeometryModel, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    enemy_models: list[GeometryModel] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            enemy_models.extend(
                geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(placement),
                    placement=placement,
                )
                for placement in unit_placement.model_placements
            )
    return tuple(enemy_models)


def _friendly_geometry_models_for_charge_path(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    attempted_placement: UnitPlacement,
    moving_model_instance_id: str,
) -> tuple[GeometryModel, ...]:
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    friendly_models: list[GeometryModel] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != unit_placement.player_id:
            continue
        for current_unit_placement in placed_army.unit_placements:
            placements = (
                attempted_placement.model_placements
                if current_unit_placement.unit_instance_id == unit_placement.unit_instance_id
                else current_unit_placement.model_placements
            )
            for placement in placements:
                if placement.model_instance_id == moving_model_id:
                    continue
                friendly_models.append(
                    geometry_model_for_placement(
                        model=scenario.model_instance_for_placement(placement),
                        placement=placement,
                    )
                )
    return tuple(friendly_models)


def _friendly_vehicle_monster_model_ids(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    moving_model_instance_id: str,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    model_ids: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            unit = scenario.unit_instance_for_placement(unit_placement)
            if not unit_has_vehicle_or_monster_keyword(unit.keywords):
                continue
            model_ids.extend(
                placement.model_instance_id
                for placement in unit_placement.model_placements
                if placement.model_instance_id != moving_model_id
            )
    return tuple(sorted(model_ids))


def _charge_endpoint_witness(
    *,
    scenario: BattlefieldScenario,
    before: UnitPlacement,
    after: UnitPlacement,
    selected_target_unit_instance_ids: tuple[str, ...],
    ruleset_descriptor: RulesetDescriptor,
) -> ChargeEndpointWitness:
    target_ids = _validate_identifier_tuple(
        "selected_target_unit_instance_ids",
        selected_target_unit_instance_ids,
    )
    before_models = _geometry_models_for_unit_placement(scenario=scenario, unit_placement=before)
    after_models = _geometry_models_for_unit_placement(scenario=scenario, unit_placement=after)
    target_distances_before: dict[str, float] = {}
    target_distances_after: dict[str, float] = {}
    engaged_target_ids: list[str] = []
    preferred_target_ids: list[str] = []
    policy = ruleset_descriptor.engagement_policy
    for target_id in target_ids:
        target_models = _geometry_models_for_unit(
            scenario=scenario,
            unit_instance_id=target_id,
        )
        target_distances_before[target_id] = _closest_distance_between_model_groups(
            before_models,
            target_models,
        )
        after_distance = _closest_distance_between_model_groups(after_models, target_models)
        target_distances_after[target_id] = after_distance
        if _model_groups_are_engaged(
            first_models=after_models,
            second_models=target_models,
            horizontal_inches=policy.horizontal_inches,
            vertical_inches=policy.vertical_inches,
        ):
            engaged_target_ids.append(target_id)
        if after_distance <= ruleset_descriptor.charge_policy.preferred_target_distance_inches:
            preferred_target_ids.append(target_id)
    non_target_engaged_ids: list[str] = []
    selected_target_set = set(target_ids)
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == after.player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            if unit_placement.unit_instance_id in selected_target_set:
                continue
            enemy_models = _geometry_models_for_unit_placement(
                scenario=scenario,
                unit_placement=unit_placement,
            )
            if _model_groups_are_engaged(
                first_models=after_models,
                second_models=enemy_models,
                horizontal_inches=policy.horizontal_inches,
                vertical_inches=policy.vertical_inches,
            ):
                non_target_engaged_ids.append(unit_placement.unit_instance_id)
    return ChargeEndpointWitness(
        selected_target_unit_instance_ids=target_ids,
        target_distances_before_inches=target_distances_before,
        target_distances_after_inches=target_distances_after,
        engaged_target_unit_instance_ids=tuple(engaged_target_ids),
        preferred_distance_target_unit_instance_ids=tuple(preferred_target_ids),
        non_target_engaged_unit_instance_ids=tuple(non_target_engaged_ids),
    )


def _model_groups_are_engaged(
    *,
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
    horizontal_inches: float,
    vertical_inches: float,
) -> bool:
    return any(
        first_model.is_within_engagement_range(
            second_model,
            horizontal_inches=horizontal_inches,
            vertical_inches=vertical_inches,
        )
        for first_model in first_models
        for second_model in second_models
    )


def _charge_move_transition_batch(
    *,
    before: UnitPlacement,
    after: UnitPlacement,
    witness: PathWitness,
) -> BattlefieldTransitionBatch:
    before_poses = {
        placement.model_instance_id: placement.pose for placement in before.model_placements
    }
    displacement_records: list[ModelDisplacementRecord] = []
    for placement in after.model_placements:
        if placement.model_instance_id not in before_poses:
            raise GameLifecycleError("Charge Move transition references an unknown model.")
        if placement.pose == before_poses[placement.model_instance_id]:
            continue
        model_path = witness.poses_for_model(placement.model_instance_id)
        displacement_records.append(
            ModelDisplacementRecord(
                model_instance_id=placement.model_instance_id,
                displacement_kind=ModelDisplacementKind.CHARGE_MOVE,
                start_pose=before_poses[placement.model_instance_id],
                end_pose=placement.pose,
                path_witness=PathWitness.for_paths(((placement.model_instance_id, model_path),)),
                source_phase=BattlePhase.CHARGE.value,
                source_step=CHARGE_MOVE_ACTION,
                source_rule_id=None,
                source_event_id=None,
            )
        )
    return BattlefieldTransitionBatch(displacements=tuple(displacement_records))


def _charging_unit_options(
    *,
    state: GameState,
    unit_ids: tuple[str, ...],
    include_complete: bool,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    for unit_id in unit_ids:
        unit = _unit_by_id(state=state, unit_instance_id=unit_id)
        target_candidates = _charge_target_candidates(
            state=state,
            unit_instance_id=unit_id,
            ruleset_descriptor=ruleset_descriptor,
            charge_target_restriction_hooks=charge_target_restriction_hooks,
        )
        eligibility_context = ChargeEligibilityContext(
            player_id=_active_player_id(state),
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
            target_candidates=target_candidates,
        )
        options.append(
            DecisionOption(
                option_id=unit_id,
                label=unit.name,
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_CHARGING_UNIT_DECISION_TYPE,
                        "game_id": state.game_id,
                        "battle_round": state.battle_round,
                        "phase": BattlePhase.CHARGE.value,
                        "active_player_id": _active_player_id(state),
                        "unit_instance_id": unit_id,
                        "eligibility_context": eligibility_context.to_payload(),
                    }
                ),
            )
        )
    if include_complete:
        options.append(
            DecisionOption(
                option_id=COMPLETE_CHARGE_PHASE_OPTION_ID,
                label="Complete Charge Phase",
                payload=validate_json_value(
                    {
                        "submission_kind": COMPLETE_CHARGE_PHASE_OPTION_ID,
                        "game_id": state.game_id,
                        "battle_round": state.battle_round,
                        "phase": BattlePhase.CHARGE.value,
                        "active_player_id": state.active_player_id,
                        "phase_body_status": _COMPLETE_CHARGE_PHASE_STATUS,
                        "skipped_unit_ids": list(unit_ids),
                    }
                ),
            )
        )
    return tuple(options)


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
    if charge_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("charge_phase_state active player drift.")


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Charge phase requires battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield_state,
        )
        scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
    except PlacementError as exc:
        raise GameLifecycleError("Charge battlefield scenario is invalid.") from exc
    return scenario


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Charge phase requires active_player_id.")
    return state.active_player_id


def _active_player_placed_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Charge phase requires battlefield_state.")
    placed_army = battlefield_state.placed_army_for_player_or_none(player_id)
    if placed_army is None:
        return ()
    return tuple(sorted(placement.unit_instance_id for placement in placed_army.unit_placements))


def _enemy_placed_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Charge phase requires battlefield_state.")
    unit_ids: list[str] = []
    for placed_army in battlefield_state.placed_armies:
        if placed_army.player_id == player_id:
            continue
        unit_ids.extend(placement.unit_instance_id for placement in placed_army.unit_placements)
    return tuple(sorted(unit_ids))


def _unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return unit
    raise GameLifecycleError("Charge unit_instance_id is unknown.")


def _unit_for_selection(*, state: GameState, selection: ChargingUnitSelection) -> UnitInstance:
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
            decisions=decisions,
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


def _reject_invalid_charge_proposal(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    proposal_validation: ProposalValidationResult,
    message: str,
) -> LifecycleStatus:
    payload = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "phase": BattlePhase.CHARGE.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": proposal_validation.status,
            "proposal_validation": proposal_validation.to_payload(),
        }
    )
    decisions.event_log.append("charge_move_proposal_invalid", payload)
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message=message,
        payload=payload,
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
    effect = PersistingEffect(
        effect_id=f"{result.result_id}:charge:fights-first",
        source_rule_id="core-rules:charge:fights-first",
        owner_player_id=active_player_id,
        target_unit_instance_ids=(unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.CHARGE,
        expiration=EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=active_player_id,
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
    maximum_distance_inches: int,
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
    maximum_distance_inches: int,
) -> str | None:
    for path_result in resolution.path_validation_results:
        if not path_result.is_valid:
            return path_result.violations[0].violation_code
    for terrain_result in resolution.terrain_path_legality_results:
        if not terrain_result.is_valid:
            return terrain_result.violations[0].violation_code
    if resolution.rollback_record is not None:
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


def _charge_endpoint_violation_code(
    *,
    endpoint_witness: ChargeEndpointWitness,
    ruleset_descriptor: RulesetDescriptor,
    maximum_distance_inches: int,
) -> str | None:
    selected = endpoint_witness.selected_target_unit_instance_ids
    if not selected:
        return "charge_target_required"
    if (
        ruleset_descriptor.charge_policy.must_end_closer_to_selected_targets
        and not _charge_ended_closer_to_any_selected_target(endpoint_witness)
    ):
        return "charge_not_closer_to_target"
    if ruleset_descriptor.charge_policy.must_end_engaged_with_every_selected_target:
        missing = set(selected) - set(endpoint_witness.engaged_target_unit_instance_ids)
        if missing:
            return "charge_target_not_engaged"
    if (
        ruleset_descriptor.charge_policy.must_reach_preferred_target_distance_if_possible
        and _charge_preferred_distance_possible(
            endpoint_witness=endpoint_witness,
            preferred_distance_inches=(
                ruleset_descriptor.charge_policy.preferred_target_distance_inches
            ),
            maximum_distance_inches=maximum_distance_inches,
        )
        and not endpoint_witness.preferred_distance_target_unit_instance_ids
    ):
        return "charge_preferred_distance_not_reached"
    if (
        ruleset_descriptor.charge_policy.forbids_non_target_engagement
        and endpoint_witness.non_target_engaged_unit_instance_ids
    ):
        return "charge_non_target_engaged"
    if (
        ruleset_descriptor.charge_policy.must_end_engaged_if_possible
        and not endpoint_witness.engaged_target_unit_instance_ids
    ):
        return "charge_no_model_engaged_target"
    return None


def _charge_ended_closer_to_any_selected_target(endpoint_witness: ChargeEndpointWitness) -> bool:
    return any(
        endpoint_witness.target_distances_after_inches[target_id]
        < endpoint_witness.target_distances_before_inches[target_id]
        for target_id in endpoint_witness.selected_target_unit_instance_ids
    )


def _charge_preferred_distance_possible(
    *,
    endpoint_witness: ChargeEndpointWitness,
    preferred_distance_inches: float,
    maximum_distance_inches: int,
) -> bool:
    return any(
        max(0.0, before_distance - preferred_distance_inches) <= maximum_distance_inches
        for before_distance in endpoint_witness.target_distances_before_inches.values()
    )


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
    if proposal.witness is None:
        return None
    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(proposal.unit_instance_id)
    expected_model_ids = tuple(
        sorted(placement.model_instance_id for placement in unit_placement.model_placements)
    )
    if tuple(sorted(proposal.witness.model_ids())) != expected_model_ids:
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="charge_witness_unit_drift",
            message="Charge Move witness model IDs do not match the selected unit.",
            field="witness",
        )
    for placement in unit_placement.model_placements:
        poses = proposal.witness.poses_for_model(placement.model_instance_id)
        if poses[0] != placement.pose:
            return ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="charge_witness_start_drift",
                message="Charge Move witness does not start at the current model pose.",
                field="witness",
                status="stale",
            )
    return None


def _validate_charge_witness_matches_unit(
    *,
    witness: PathWitness,
    unit_placement: UnitPlacement,
) -> None:
    if type(witness) is not PathWitness:
        raise GameLifecycleError("Charge Move requires a PathWitness.")
    expected_model_ids = tuple(
        sorted(placement.model_instance_id for placement in unit_placement.model_placements)
    )
    if tuple(sorted(witness.model_ids())) != expected_model_ids:
        raise GameLifecycleError("Charge Move witness must match the selected unit models.")


def _terrain_volumes_for_features(
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> tuple[TerrainVolume, ...]:
    volumes: list[TerrainVolume] = []
    for feature in terrain_features:
        if type(feature) is not TerrainFeatureDefinition:
            raise GameLifecycleError("terrain_features must contain TerrainFeatureDefinition.")
        volumes.extend(feature.terrain_volumes())
    return tuple(volumes)


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


def _validate_distance_map(field_name: str, value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    distances: dict[str, float] = {}
    for raw_key, raw_distance in cast(dict[object, object], value).items():
        unit_id = _validate_identifier(field_name, raw_key)
        if type(raw_distance) not in {int, float}:
            raise GameLifecycleError(f"{field_name} values must be numbers.")
        distance = float(cast(int | float, raw_distance))
        if distance < 0.0:
            raise GameLifecycleError(f"{field_name} distances must be non-negative.")
        distances[unit_id] = distance
    return dict(sorted(distances.items()))


def _validate_path_validation_results(
    values: object,
) -> tuple[PathValidationResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("path_validation_results must be a tuple.")
    results: list[PathValidationResult] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not PathValidationResult:
            raise GameLifecycleError(
                "path_validation_results must contain PathValidationResult values."
            )
        results.append(value)
    return tuple(results)


def _validate_terrain_path_legality_results(
    values: object,
) -> tuple[TerrainPathLegalityResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("terrain_path_legality_results must be a tuple.")
    results: list[TerrainPathLegalityResult] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainPathLegalityResult:
            raise GameLifecycleError(
                "terrain_path_legality_results must contain TerrainPathLegalityResult values."
            )
        results.append(value)
    return tuple(results)


def _validate_json_object(field_name: str, value: object) -> dict[str, JsonValue]:
    json_value = validate_json_value(value)
    if not isinstance(json_value, dict):
        raise GameLifecycleError(f"{field_name} must be a JSON object.")
    return json_value


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


def _validate_charge_distance_states(values: object) -> tuple[ChargeDistanceState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("ChargePhaseState distance_states must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    states: list[ChargeDistanceState] = []
    seen: set[str] = set()
    for value in raw_values:
        if type(value) is not ChargeDistanceState:
            raise GameLifecycleError(
                "ChargePhaseState distance_states must contain ChargeDistanceState."
            )
        result_id = value.source_decision_result_id
        if result_id in seen:
            raise GameLifecycleError("ChargePhaseState distance_states duplicate result_id.")
        seen.add(result_id)
        states.append(value)
    return tuple(states)


def _validate_charge_declared_target_map(values: object) -> dict[str, tuple[str, ...]]:
    if type(values) is not dict:
        raise GameLifecycleError(
            "ChargePhaseState declared_target_unit_instance_ids_by_unit must be a dict."
        )
    validated: dict[str, tuple[str, ...]] = {}
    for raw_unit_id, raw_target_ids in cast(dict[object, object], values).items():
        unit_id = _validate_identifier("declared target unit id", raw_unit_id)
        if unit_id in validated:
            raise GameLifecycleError("ChargePhaseState declared target map duplicates unit IDs.")
        if type(raw_target_ids) is not tuple:
            raise GameLifecycleError("ChargePhaseState declared target map values must be tuples.")
        validated[unit_id] = _validate_identifier_tuple(
            "declared target unit ids",
            cast(tuple[object, ...], raw_target_ids),
        )
    return dict(sorted(validated.items()))


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    validated = tuple(_validate_identifier(field_name, value) for value in raw_values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(validated))


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value
