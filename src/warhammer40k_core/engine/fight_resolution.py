from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.objectives import ObjectiveMarker, ObjectiveMarkerPayload
from warhammer40k_core.core.ruleset_descriptor import (
    ConsolidationModeKind,
    MovementMode,
    RulesetDescriptor,
    consolidation_mode_kind_from_token,
    movement_mode_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelPlacement,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_request import (
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND,
    FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
)
from warhammer40k_core.engine.fight_geometry import (
    closest_fight_unit_distance_inches as _closest_unit_distance_inches,
)
from warhammer40k_core.engine.fight_geometry import (
    closest_model_distance_to_units as _closest_model_distance_to_units,
)
from warhammer40k_core.engine.fight_geometry import (
    enemy_fight_unit_ids_within_distance as _enemy_unit_ids_within_distance,
)
from warhammer40k_core.engine.fight_geometry import (
    enemy_geometry_models_for_player as _enemy_geometry_models_for_player,
)
from warhammer40k_core.engine.fight_geometry import (
    enemy_unit_ids_for_fight_placement as _enemy_unit_ids_for_placement,
)
from warhammer40k_core.engine.fight_geometry import (
    geometry_model_for_fight_model_pose as _geometry_model_for_model_pose,
)
from warhammer40k_core.engine.fight_geometry import (
    geometry_model_for_fight_unit_model as _geometry_model_for_unit_model,
)
from warhammer40k_core.engine.fight_geometry import (
    geometry_models_for_fight_unit as _geometry_models_for_unit,
)
from warhammer40k_core.engine.fight_geometry import (
    geometry_models_for_fight_unit_placement as _geometry_models_for_unit_placement,
)
from warhammer40k_core.engine.fight_geometry import (
    model_engaged_with_any as _model_engaged_with_any,
)
from warhammer40k_core.engine.fight_geometry import (
    model_in_base_contact_with_enemy as _model_in_base_contact_with_enemy,
)
from warhammer40k_core.engine.fight_geometry import (
    unit_id_for_fight_model as _unit_id_for_model,
)
from warhammer40k_core.engine.fight_on_death import model_is_present_on_battlefield
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
    ProposalValidationResult,
    proposal_kind_from_token,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    UnitCoherencyResult,
    resolve_unit_movement_endpoint_coherency,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import (
    LANCE_RULE_ID,
    cleave_attack_bonus,
    cleave_rule_id,
    has_weapon_keyword,
)
from warhammer40k_core.engine.weapon_declaration import (
    RangedAttackPool,
    WeaponDeclaration,
    attacks_for_profile,
)
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathWitness,
    PathWitnessPayload,
    TerrainPathLegalityResult,
    is_degenerate_endpoint_only_real_movement_path,
)
from warhammer40k_core.geometry.pose import GeometryError, Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState, OneShotWeaponUseRecord

PILE_IN_ACTION = "pile_in"
CONSOLIDATE_ACTION = "consolidate"
PILE_IN_DISTANCE_INCHES = 3.0
CONSOLIDATE_DISTANCE_INCHES = 3.0
PILE_IN_TARGET_DISTANCE_INCHES = 5.0
CONSOLIDATE_ENEMY_DISTANCE_INCHES = 3.0
SUBMIT_MELEE_DECLARATION_DECISION_TYPE = "submit_melee_declaration"
MELEE_DECLARATION_PROPOSAL_KIND = "melee_declaration"
MELEE_TARGETING_RULE_ID = "fight_phase_melee"
_BASE_CONTACT_EPSILON = 1e-9
_CLOSER_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class _FightActivationMeleeTargetingEffect:
    source_rule_id: str
    model_proximity_inches: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "model_proximity_inches",
            _validate_positive_float("model_proximity_inches", self.model_proximity_inches),
        )


class FightMovementProposalPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    unit_instance_id: str
    movement_phase_action: str
    movement_mode: str
    pile_in_target_unit_instance_ids: NotRequired[list[str]]
    consolidation_mode: NotRequired[str]
    consolidate_target_unit_instance_ids: NotRequired[list[str]]
    objective_id: NotRequired[str | None]
    witness: NotRequired[PathWitnessPayload]


class FightMovementEndpointPayload(TypedDict):
    target_unit_instance_ids: list[str]
    objective_id: str | None
    moved_model_instance_ids: list[str]
    engaged_before_unit_ids: list[str]
    engaged_after_unit_ids: list[str]


class FightMovementResolutionPayload(TypedDict):
    movement_mode: str
    movement_phase_action: str
    maximum_distance_inches: float
    endpoint_witness: FightMovementEndpointPayload
    path_validation_results: list[JsonValue]
    terrain_path_legality_results: list[JsonValue]
    coherency_result: JsonValue
    rollback_record: JsonValue | None


class MeleeTargetAllocationPayload(TypedDict):
    target_unit_instance_id: str
    attacks: NotRequired[int]


class MeleeWeaponDeclarationPayload(TypedDict):
    attacker_model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    target_allocations: list[MeleeTargetAllocationPayload]


class MeleeDeclarationProposalPayload(TypedDict):
    proposal_request_id: str
    proposal_kind: str
    player_id: str
    battle_round: int
    unit_instance_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    declarations: list[MeleeWeaponDeclarationPayload]


class MeleeDeclarationProposalRequestPayload(TypedDict):
    request_id: str
    decision_type: str
    actor_id: str
    game_id: str
    battle_round: int
    phase: str
    active_player_id: str
    unit_instance_id: str
    proposal_kind: str
    source_decision_request_id: str
    source_decision_result_id: str
    ruleset_descriptor_hash: str
    available_weapons: list[JsonValue]
    target_unit_instance_ids: list[str]


@dataclass(frozen=True, slots=True)
class FightMovementProposal:
    proposal_request_id: str
    proposal_kind: ProposalKind
    unit_instance_id: str
    movement_phase_action: str
    movement_mode: MovementMode
    pile_in_target_unit_instance_ids: tuple[str, ...] = ()
    consolidation_mode: ConsolidationModeKind | None = None
    consolidate_target_unit_instance_ids: tuple[str, ...] = ()
    objective_id: str | None = None
    witness: PathWitness | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_request_id",
            _validate_identifier(
                "FightMovementProposal proposal_request_id",
                self.proposal_request_id,
            ),
        )
        proposal_kind = _fight_movement_proposal_kind(self.proposal_kind)
        object.__setattr__(self, "proposal_kind", proposal_kind)
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("FightMovementProposal unit_instance_id", self.unit_instance_id),
        )
        action = _fight_movement_action(self.movement_phase_action)
        object.__setattr__(self, "movement_phase_action", action)
        mode = _fight_movement_mode(self.movement_mode)
        object.__setattr__(self, "movement_mode", mode)
        if proposal_kind is ProposalKind.PILE_IN and (
            action != PILE_IN_ACTION or mode is not MovementMode.PILE_IN
        ):
            raise GameLifecycleError("Pile In proposal action/mode drift.")
        if proposal_kind is ProposalKind.CONSOLIDATE and (
            action != CONSOLIDATE_ACTION or mode is not MovementMode.CONSOLIDATE
        ):
            raise GameLifecycleError("Consolidate proposal action/mode drift.")
        object.__setattr__(
            self,
            "pile_in_target_unit_instance_ids",
            _validate_identifier_tuple(
                "FightMovementProposal pile_in_target_unit_instance_ids",
                self.pile_in_target_unit_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "consolidate_target_unit_instance_ids",
            _validate_identifier_tuple(
                "FightMovementProposal consolidate_target_unit_instance_ids",
                self.consolidate_target_unit_instance_ids,
            ),
        )
        if self.consolidation_mode is not None:
            object.__setattr__(
                self,
                "consolidation_mode",
                consolidation_mode_kind_from_token(self.consolidation_mode),
            )
        object.__setattr__(
            self,
            "objective_id",
            _validate_optional_identifier("FightMovementProposal objective_id", self.objective_id),
        )
        if self.witness is not None and type(self.witness) is not PathWitness:
            raise GameLifecycleError("FightMovementProposal witness must be a PathWitness.")

    @property
    def target_unit_instance_ids(self) -> tuple[str, ...]:
        if self.proposal_kind is ProposalKind.PILE_IN:
            return self.pile_in_target_unit_instance_ids
        return self.consolidate_target_unit_instance_ids

    @property
    def is_no_move_choice(self) -> bool:
        return (
            not self.pile_in_target_unit_instance_ids
            and not self.consolidate_target_unit_instance_ids
            and self.objective_id is None
        )

    def validation_result_for_request(
        self,
        request: MovementProposalRequest,
    ) -> ProposalValidationResult:
        if type(request) is not MovementProposalRequest:
            raise GameLifecycleError("Fight movement proposal validation requires a request.")
        if self.proposal_request_id != request.request_id:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="stale_proposal_request",
                message="Fight movement proposal request_id does not match the pending request.",
                field="proposal_request_id",
                status="stale",
            )
        if self.proposal_kind is not request.proposal_kind:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_kind_drift",
                message="Fight movement proposal kind does not match the pending request.",
                field="proposal_kind",
            )
        if self.unit_instance_id != request.unit_instance_id:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_unit_drift",
                message="Fight movement proposal unit does not match the pending request.",
                field="unit_instance_id",
            )
        if request.phase != BattlePhase.FIGHT.value:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_phase_drift",
                message="Fight movement proposal request is not a Fight phase request.",
                field="phase",
            )
        if self.movement_phase_action != request.movement_phase_action:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_action_drift",
                message="Fight movement proposal action does not match the pending request.",
                field="movement_phase_action",
            )
        expected_mode = _payload_string(_proposal_context(request), key="movement_mode")
        if self.movement_mode.value != expected_mode:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="proposal_movement_mode_drift",
                message="Fight movement proposal mode does not match the pending request.",
                field="movement_mode",
            )
        if self.is_no_move_choice:
            if self.witness is not None:
                return ProposalValidationResult.invalid(
                    proposal_request_id=request.request_id,
                    proposal_kind=request.proposal_kind,
                    violation_code="no_move_witness_forbidden",
                    message="Fight movement no-move submissions must not include a witness.",
                    field="witness",
                )
            return ProposalValidationResult.valid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
            )
        if self.witness is None:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="fight_movement_witness_required",
                message="Fight movement target submissions require a PathWitness.",
                field="witness",
            )
        endpoint_only_model_id = _endpoint_only_model_id(self.witness)
        if endpoint_only_model_id is not None:
            return ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=request.proposal_kind,
                violation_code="endpoint_only_path",
                message="Fight movement PathWitness must not repeat only endpoint poses.",
                field="witness",
            )
        return ProposalValidationResult.valid(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
        )

    def to_payload(self) -> FightMovementProposalPayload:
        payload: FightMovementProposalPayload = {
            "proposal_request_id": self.proposal_request_id,
            "proposal_kind": self.proposal_kind.value,
            "unit_instance_id": self.unit_instance_id,
            "movement_phase_action": self.movement_phase_action,
            "movement_mode": self.movement_mode.value,
        }
        if self.pile_in_target_unit_instance_ids:
            payload["pile_in_target_unit_instance_ids"] = list(
                self.pile_in_target_unit_instance_ids
            )
        if self.consolidation_mode is not None:
            payload["consolidation_mode"] = self.consolidation_mode.value
        if self.consolidate_target_unit_instance_ids:
            payload["consolidate_target_unit_instance_ids"] = list(
                self.consolidate_target_unit_instance_ids
            )
        if self.objective_id is not None:
            payload["objective_id"] = self.objective_id
        if self.witness is not None:
            payload["witness"] = self.witness.to_payload()
        return payload

    @classmethod
    def from_payload(cls, payload: FightMovementProposalPayload) -> Self:
        witness_payload = payload.get("witness")
        consolidation_mode_payload = payload.get("consolidation_mode")
        return cls(
            proposal_request_id=payload["proposal_request_id"],
            proposal_kind=proposal_kind_from_token(payload["proposal_kind"]),
            unit_instance_id=payload["unit_instance_id"],
            movement_phase_action=payload["movement_phase_action"],
            movement_mode=movement_mode_from_token(payload["movement_mode"]),
            pile_in_target_unit_instance_ids=tuple(
                payload.get("pile_in_target_unit_instance_ids", ())
            ),
            consolidation_mode=(
                None
                if consolidation_mode_payload is None
                else consolidation_mode_kind_from_token(consolidation_mode_payload)
            ),
            consolidate_target_unit_instance_ids=tuple(
                payload.get("consolidate_target_unit_instance_ids", ())
            ),
            objective_id=payload.get("objective_id"),
            witness=(
                None if witness_payload is None else PathWitness.from_payload(witness_payload)
            ),
        )


@dataclass(frozen=True, slots=True)
class FightMovementResolution:
    unit_instance_id: str
    proposal_kind: ProposalKind
    movement_phase_action: str
    movement_mode: MovementMode
    maximum_distance_inches: float
    attempted_placement: UnitPlacement
    witness: PathWitness | None
    endpoint_witness: FightMovementEndpointPayload
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult | None
    rollback_record: MovementRollbackRecord | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("FightMovementResolution unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(self, "proposal_kind", _fight_movement_proposal_kind(self.proposal_kind))
        object.__setattr__(
            self, "movement_phase_action", _fight_movement_action(self.movement_phase_action)
        )
        object.__setattr__(self, "movement_mode", _fight_movement_mode(self.movement_mode))
        object.__setattr__(
            self,
            "maximum_distance_inches",
            _validate_positive_float(
                "FightMovementResolution maximum_distance_inches",
                self.maximum_distance_inches,
            ),
        )
        if type(self.attempted_placement) is not UnitPlacement:
            raise GameLifecycleError(
                "FightMovementResolution attempted_placement must be UnitPlacement."
            )
        if self.witness is not None and type(self.witness) is not PathWitness:
            raise GameLifecycleError("FightMovementResolution witness must be PathWitness.")
        object.__setattr__(
            self,
            "endpoint_witness",
            _validate_json_object(
                "FightMovementResolution endpoint_witness", self.endpoint_witness
            ),
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
        if (
            self.coherency_result is not None
            and type(self.coherency_result) is not UnitCoherencyResult
        ):
            raise GameLifecycleError(
                "FightMovementResolution coherency_result must be UnitCoherencyResult."
            )
        if (
            self.rollback_record is not None
            and type(self.rollback_record) is not MovementRollbackRecord
        ):
            raise GameLifecycleError(
                "FightMovementResolution rollback_record must be MovementRollbackRecord."
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
            raise GameLifecycleError("Invalid fight movement cannot emit displacement records.")
        return _fight_movement_transition_batch(
            before=before,
            after=self.attempted_placement,
            witness=self.witness,
            displacement_kind=_displacement_kind_for_proposal_kind(self.proposal_kind),
            source_step=self.movement_phase_action,
        )

    def to_payload(self) -> FightMovementResolutionPayload:
        return {
            "movement_mode": self.movement_mode.value,
            "movement_phase_action": self.movement_phase_action,
            "maximum_distance_inches": self.maximum_distance_inches,
            "endpoint_witness": self.endpoint_witness,
            "path_validation_results": [
                validate_json_value(result.to_payload()) for result in self.path_validation_results
            ],
            "terrain_path_legality_results": [
                validate_json_value(result.to_payload())
                for result in self.terrain_path_legality_results
            ],
            "coherency_result": (
                None
                if self.coherency_result is None
                else validate_json_value(self.coherency_result.to_payload())
            ),
            "rollback_record": (
                None
                if self.rollback_record is None
                else validate_json_value(self.rollback_record.to_payload())
            ),
        }


@dataclass(frozen=True, slots=True)
class MeleeDeclarationProposalRequest:
    request_id: str
    actor_id: str
    game_id: str
    battle_round: int
    active_player_id: str
    unit_instance_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    ruleset_descriptor_hash: str
    available_weapons: tuple[JsonValue, ...]
    target_unit_instance_ids: tuple[str, ...]
    proposal_kind: str = MELEE_DECLARATION_PROPOSAL_KIND

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _validate_identifier("request_id", self.request_id))
        object.__setattr__(self, "actor_id", _validate_identifier("actor_id", self.actor_id))
        object.__setattr__(self, "game_id", _validate_identifier("game_id", self.game_id))
        object.__setattr__(
            self, "battle_round", _validate_positive_int("battle_round", self.battle_round)
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_identifier("source_decision_request_id", self.source_decision_request_id),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_identifier("source_decision_result_id", self.source_decision_result_id),
        )
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier("ruleset_descriptor_hash", self.ruleset_descriptor_hash),
        )
        if self.proposal_kind != MELEE_DECLARATION_PROPOSAL_KIND:
            raise GameLifecycleError("Melee declaration proposal_kind drift.")
        object.__setattr__(
            self,
            "available_weapons",
            tuple(validate_json_value(value) for value in self.available_weapons),
        )
        object.__setattr__(
            self,
            "target_unit_instance_ids",
            _validate_identifier_tuple(
                "target_unit_instance_ids",
                self.target_unit_instance_ids,
            ),
        )

    def to_payload(self) -> MeleeDeclarationProposalRequestPayload:
        return {
            "request_id": self.request_id,
            "decision_type": SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
            "actor_id": self.actor_id,
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "phase": BattlePhase.FIGHT.value,
            "active_player_id": self.active_player_id,
            "unit_instance_id": self.unit_instance_id,
            "proposal_kind": self.proposal_kind,
            "source_decision_request_id": self.source_decision_request_id,
            "source_decision_result_id": self.source_decision_result_id,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "available_weapons": list(self.available_weapons),
            "target_unit_instance_ids": list(self.target_unit_instance_ids),
        }

    @classmethod
    def from_decision_request(cls, request: DecisionRequest) -> Self:
        if request.decision_type != SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
            raise GameLifecycleError("Melee declaration request has wrong decision_type.")
        payload = _json_object("Melee declaration DecisionRequest payload", request.payload)
        raw_request = _json_object("Melee proposal_request", payload.get("proposal_request"))
        request_payload = cast(MeleeDeclarationProposalRequestPayload, raw_request)
        return cls(
            request_id=request_payload["request_id"],
            actor_id=request_payload["actor_id"],
            game_id=request_payload["game_id"],
            battle_round=request_payload["battle_round"],
            active_player_id=request_payload["active_player_id"],
            unit_instance_id=request_payload["unit_instance_id"],
            source_decision_request_id=request_payload["source_decision_request_id"],
            source_decision_result_id=request_payload["source_decision_result_id"],
            ruleset_descriptor_hash=request_payload["ruleset_descriptor_hash"],
            available_weapons=tuple(request_payload["available_weapons"]),
            target_unit_instance_ids=tuple(request_payload["target_unit_instance_ids"]),
            proposal_kind=request_payload["proposal_kind"],
        )


@dataclass(frozen=True, slots=True)
class MeleeTargetAllocation:
    target_unit_instance_id: str
    attacks: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "MeleeTargetAllocation target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        if self.attacks is not None:
            object.__setattr__(
                self,
                "attacks",
                _validate_positive_int("MeleeTargetAllocation attacks", self.attacks),
            )

    def to_payload(self) -> MeleeTargetAllocationPayload:
        payload: MeleeTargetAllocationPayload = {
            "target_unit_instance_id": self.target_unit_instance_id
        }
        if self.attacks is not None:
            payload["attacks"] = self.attacks
        return payload

    @classmethod
    def from_payload(cls, payload: MeleeTargetAllocationPayload) -> Self:
        return cls(
            target_unit_instance_id=payload["target_unit_instance_id"],
            attacks=payload.get("attacks"),
        )


@dataclass(frozen=True, slots=True)
class MeleeWeaponDeclaration:
    attacker_model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    target_allocations: tuple[MeleeTargetAllocation, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier(
                "MeleeWeaponDeclaration attacker_model_instance_id",
                self.attacker_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "wargear_id",
            _validate_identifier("MeleeWeaponDeclaration wargear_id", self.wargear_id),
        )
        object.__setattr__(
            self,
            "weapon_profile_id",
            _validate_identifier(
                "MeleeWeaponDeclaration weapon_profile_id",
                self.weapon_profile_id,
            ),
        )
        object.__setattr__(
            self,
            "target_allocations",
            _validate_melee_target_allocations(self.target_allocations),
        )

    @property
    def weapon_key(self) -> tuple[str, str, str]:
        return (
            self.attacker_model_instance_id,
            self.wargear_id,
            self.weapon_profile_id,
        )

    @property
    def target_unit_instance_ids(self) -> tuple[str, ...]:
        return tuple(allocation.target_unit_instance_id for allocation in self.target_allocations)

    def to_payload(self) -> MeleeWeaponDeclarationPayload:
        return {
            "attacker_model_instance_id": self.attacker_model_instance_id,
            "wargear_id": self.wargear_id,
            "weapon_profile_id": self.weapon_profile_id,
            "target_allocations": [
                allocation.to_payload() for allocation in self.target_allocations
            ],
        }

    @classmethod
    def from_payload(cls, payload: MeleeWeaponDeclarationPayload) -> Self:
        return cls(
            attacker_model_instance_id=payload["attacker_model_instance_id"],
            wargear_id=payload["wargear_id"],
            weapon_profile_id=payload["weapon_profile_id"],
            target_allocations=tuple(
                MeleeTargetAllocation.from_payload(allocation)
                for allocation in payload["target_allocations"]
            ),
        )


@dataclass(frozen=True, slots=True)
class MeleeDeclarationProposal:
    proposal_request_id: str
    proposal_kind: str
    player_id: str
    battle_round: int
    unit_instance_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    declarations: tuple[MeleeWeaponDeclaration, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_request_id",
            _validate_identifier("proposal_request_id", self.proposal_request_id),
        )
        if self.proposal_kind != MELEE_DECLARATION_PROPOSAL_KIND:
            raise GameLifecycleError("Melee declaration proposal_kind drift.")
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self, "battle_round", _validate_positive_int("battle_round", self.battle_round)
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_identifier("source_decision_request_id", self.source_decision_request_id),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_identifier("source_decision_result_id", self.source_decision_result_id),
        )
        if type(self.declarations) is not tuple:
            raise GameLifecycleError("MeleeDeclarationProposal declarations must be a tuple.")
        object.__setattr__(
            self,
            "declarations",
            _validate_melee_weapon_declarations(self.declarations),
        )

    def validation_result_for_request(
        self,
        request: MeleeDeclarationProposalRequest,
    ) -> ProposalValidationResult:
        if self.proposal_request_id != request.request_id:
            return _invalid_melee_validation(
                request=request,
                violation_code="stale_proposal_request",
                message="Melee declaration proposal request_id does not match.",
                field="proposal_request_id",
                status="stale",
            )
        if self.player_id != request.actor_id:
            return _invalid_melee_validation(
                request=request,
                violation_code="proposal_player_drift",
                message="Melee declaration player does not match the pending request.",
                field="player_id",
            )
        if self.battle_round != request.battle_round:
            return _invalid_melee_validation(
                request=request,
                violation_code="proposal_battle_round_drift",
                message="Melee declaration battle round does not match the pending request.",
                field="battle_round",
            )
        if self.unit_instance_id != request.unit_instance_id:
            return _invalid_melee_validation(
                request=request,
                violation_code="proposal_unit_drift",
                message="Melee declaration unit does not match the pending request.",
                field="unit_instance_id",
            )
        if self.source_decision_request_id != request.source_decision_request_id:
            return _invalid_melee_validation(
                request=request,
                violation_code="source_decision_request_drift",
                message="Melee declaration source request does not match.",
                field="source_decision_request_id",
            )
        if self.source_decision_result_id != request.source_decision_result_id:
            return _invalid_melee_validation(
                request=request,
                violation_code="source_decision_result_drift",
                message="Melee declaration source result does not match.",
                field="source_decision_result_id",
            )
        return ProposalValidationResult.valid(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.MELEE_DECLARATION,
        )

    def to_payload(self) -> MeleeDeclarationProposalPayload:
        return {
            "proposal_request_id": self.proposal_request_id,
            "proposal_kind": self.proposal_kind,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "source_decision_request_id": self.source_decision_request_id,
            "source_decision_result_id": self.source_decision_result_id,
            "declarations": [declaration.to_payload() for declaration in self.declarations],
        }

    @classmethod
    def from_payload(cls, payload: MeleeDeclarationProposalPayload) -> Self:
        return cls(
            proposal_request_id=payload["proposal_request_id"],
            proposal_kind=payload["proposal_kind"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            source_decision_request_id=payload["source_decision_request_id"],
            source_decision_result_id=payload["source_decision_result_id"],
            declarations=tuple(
                MeleeWeaponDeclaration.from_payload(declaration)
                for declaration in payload["declarations"]
            ),
        )


def build_fight_movement_request(
    *,
    state_game_id: str,
    battle_round: int,
    active_player_id: str,
    request_id: str,
    actor_id: str,
    unit_instance_id: str,
    proposal_kind: ProposalKind,
    source_decision_request_id: str,
    source_decision_result_id: str,
    context: dict[str, JsonValue],
) -> DecisionRequest:
    kind = _fight_movement_proposal_kind(proposal_kind)
    action = PILE_IN_ACTION if kind is ProposalKind.PILE_IN else CONSOLIDATE_ACTION
    mode = MovementMode.PILE_IN if kind is ProposalKind.PILE_IN else MovementMode.CONSOLIDATE
    request = MovementProposalRequest(
        request_id=request_id,
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=actor_id,
        game_id=state_game_id,
        battle_round=battle_round,
        phase=BattlePhase.FIGHT.value,
        unit_instance_id=unit_instance_id,
        proposal_kind=kind,
        source_decision_request_id=source_decision_request_id,
        source_decision_result_id=source_decision_result_id,
        movement_phase_action=action,
        context={
            "active_player_id": active_player_id,
            "movement_mode": mode.value,
            **context,
        },
    )
    return request.to_decision_request()


def build_melee_declaration_request(
    *,
    request_id: str,
    game_id: str,
    battle_round: int,
    active_player_id: str,
    actor_id: str,
    unit_instance_id: str,
    source_decision_request_id: str,
    source_decision_result_id: str,
    ruleset_descriptor: RulesetDescriptor,
    available_weapons: tuple[JsonValue, ...],
    target_unit_instance_ids: tuple[str, ...],
) -> DecisionRequest:
    proposal_request = MeleeDeclarationProposalRequest(
        request_id=request_id,
        actor_id=actor_id,
        game_id=game_id,
        battle_round=battle_round,
        active_player_id=active_player_id,
        unit_instance_id=unit_instance_id,
        source_decision_request_id=source_decision_request_id,
        source_decision_result_id=source_decision_result_id,
        ruleset_descriptor_hash=ruleset_descriptor.descriptor_hash,
        available_weapons=available_weapons,
        target_unit_instance_ids=target_unit_instance_ids,
    )
    return DecisionRequest(
        request_id=request_id,
        decision_type=SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
        actor_id=actor_id,
        payload=validate_json_value({"proposal_request": proposal_request.to_payload()}),
        options=(parameterized_decision_option(),),
    )


def fight_movement_proposal_from_payload(payload: object) -> FightMovementProposal:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Fight movement proposal payload must be an object.")
    return FightMovementProposal.from_payload(cast(FightMovementProposalPayload, payload))


def melee_declaration_proposal_from_payload(payload: object) -> MeleeDeclarationProposal:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Melee declaration proposal payload must be an object.")
    return MeleeDeclarationProposal.from_payload(cast(MeleeDeclarationProposalPayload, payload))


def fight_movement_proposal_payload_parse_failure(
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
            message=f"Fight movement proposal payload missing required field: {missing}.",
            field=missing,
        )
    return ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code="proposal_payload_malformed",
        message=f"Fight movement proposal payload is malformed: {error}",
        field="payload",
    )


def resolve_fight_movement(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal: FightMovementProposal,
    maximum_distance_inches: float | None = None,
    state: GameState | None = None,
) -> FightMovementResolution:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Fight movement requires a BattlefieldScenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Fight movement requires a RulesetDescriptor.")
    distance_budget_inches = (
        _maximum_distance_for_proposal_kind(proposal.proposal_kind)
        if maximum_distance_inches is None
        else _validate_positive_float("maximum_distance_inches", maximum_distance_inches)
    )
    unit_placement = scenario.battlefield_state.unit_placement_by_id(proposal.unit_instance_id)
    if proposal.is_no_move_choice:
        return FightMovementResolution(
            unit_instance_id=proposal.unit_instance_id,
            proposal_kind=proposal.proposal_kind,
            movement_phase_action=proposal.movement_phase_action,
            movement_mode=proposal.movement_mode,
            maximum_distance_inches=distance_budget_inches,
            attempted_placement=unit_placement,
            witness=None,
            endpoint_witness=_endpoint_witness(
                scenario=scenario,
                before=unit_placement,
                after=unit_placement,
                target_unit_instance_ids=(),
                objective_id=None,
                ruleset_descriptor=ruleset_descriptor,
                state=state,
            ),
            path_validation_results=(),
            terrain_path_legality_results=(),
            coherency_result=None,
            rollback_record=None,
        )
    witness = proposal.witness
    if witness is None:
        raise GameLifecycleError("Fight movement requires a PathWitness.")
    _validate_fight_witness_matches_unit(witness=witness, unit_placement=unit_placement)
    attempted_placement = _attempted_placement_from_witness(
        unit_placement=unit_placement,
        witness=witness,
    )
    path_validation_results, terrain_path_legality_results = _validate_fight_paths(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        before=unit_placement,
        after=attempted_placement,
        witness=witness,
        movement_mode=proposal.movement_mode,
        displacement_kind=_displacement_kind_for_proposal(proposal),
        distance_budget_inches=distance_budget_inches,
    )
    _, coherency_result, rollback_record = resolve_unit_movement_endpoint_coherency(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        before=unit_placement,
        attempted=attempted_placement,
        displacement_kind=_displacement_kind_for_proposal(proposal),
    )
    endpoint_witness = _endpoint_witness(
        scenario=scenario,
        before=unit_placement,
        after=attempted_placement,
        target_unit_instance_ids=proposal.target_unit_instance_ids,
        objective_id=proposal.objective_id,
        ruleset_descriptor=ruleset_descriptor,
        state=state,
    )
    return FightMovementResolution(
        unit_instance_id=proposal.unit_instance_id,
        proposal_kind=proposal.proposal_kind,
        movement_phase_action=proposal.movement_phase_action,
        movement_mode=proposal.movement_mode,
        maximum_distance_inches=distance_budget_inches,
        attempted_placement=attempted_placement,
        witness=witness,
        endpoint_witness=endpoint_witness,
        path_validation_results=path_validation_results,
        terrain_path_legality_results=terrain_path_legality_results,
        coherency_result=coherency_result,
        rollback_record=rollback_record,
    )


def fight_movement_rule_validation(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
    eligible_unit_ids: tuple[str, ...],
    state: GameState | None = None,
) -> ProposalValidationResult:
    if proposal.unit_instance_id not in eligible_unit_ids:
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="fight_movement_unit_not_eligible",
            message="Fight movement proposal unit is not eligible for this step.",
            field="unit_instance_id",
        )
    if proposal.is_no_move_choice:
        return ProposalValidationResult.valid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
        )
    if proposal.proposal_kind is ProposalKind.PILE_IN:
        return _pile_in_rule_validation(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            proposal_request=proposal_request,
            proposal=proposal,
            state=state,
        )
    return _consolidate_rule_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        proposal_request=proposal_request,
        proposal=proposal,
        state=state,
    )


def fight_movement_resolution_violation(
    *,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
    resolution: FightMovementResolution,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    state: GameState | None = None,
) -> ProposalValidationResult | None:
    for path_result in resolution.path_validation_results:
        if not path_result.is_valid:
            path_violation = path_result.violations[0]
            return ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code=path_violation.violation_code,
                message=path_violation.message,
                field="witness",
            )
    for terrain_result in resolution.terrain_path_legality_results:
        if not terrain_result.is_valid:
            terrain_violation = terrain_result.violations[0]
            return ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code=terrain_violation.violation_code,
                message=terrain_violation.message,
                field="witness",
            )
    if resolution.rollback_record is not None:
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="unit_coherency_invalid",
            message="Fight movement endpoint violates unit coherency.",
            field="witness",
        )
    if proposal.is_no_move_choice:
        return None
    if proposal.proposal_kind is ProposalKind.PILE_IN:
        return _pile_in_endpoint_validation(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            proposal_request=proposal_request,
            proposal=proposal,
            after=resolution.attempted_placement,
            state=state,
        )
    return _consolidate_endpoint_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        proposal_request=proposal_request,
        proposal=proposal,
        after=resolution.attempted_placement,
        state=state,
    )


def legal_pile_in_target_unit_ids(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
    state: GameState | None = None,
) -> tuple[str, ...]:
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    engaged = _engaged_enemy_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        state=state,
    )
    if engaged:
        return engaged
    return tuple(
        enemy_id
        for enemy_id in _enemy_unit_ids_for_placement(
            scenario=scenario,
            unit_placement=unit_placement,
        )
        if _closest_unit_distance_inches(
            scenario=scenario,
            first_unit_instance_id=unit_instance_id,
            second_unit_instance_id=enemy_id,
            state=state,
        )
        <= PILE_IN_TARGET_DISTANCE_INCHES
    )


def legal_consolidation_modes(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
    objective_markers: tuple[ObjectiveMarker, ...],
    state: GameState | None = None,
) -> tuple[ConsolidationModeKind, ...]:
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    if _engaged_enemy_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        state=state,
    ):
        return (ConsolidationModeKind.ONGOING,)
    if _enemy_unit_ids_within_distance(
        scenario=scenario,
        unit_placement=unit_placement,
        distance_inches=CONSOLIDATE_ENEMY_DISTANCE_INCHES,
        state=state,
    ):
        return (ConsolidationModeKind.ENGAGING,)
    if _objective_markers_within_distance(
        unit_placement=unit_placement,
        objective_markers=objective_markers,
        distance_inches=CONSOLIDATE_DISTANCE_INCHES,
    ):
        return (ConsolidationModeKind.OBJECTIVE,)
    return ()


def fight_movement_maximum_distance_inches(
    *,
    state: GameState,
    unit_instance_id: str,
    proposal_kind: ProposalKind,
) -> float:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    resolved_kind = _fight_movement_proposal_kind(proposal_kind)
    maximum_distance = _maximum_distance_for_proposal_kind(resolved_kind)
    for effect in state.persisting_effects:
        if requested_unit_id not in effect.target_unit_instance_ids:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") != FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND:
            continue
        if payload.get("source_id") != effect.source_rule_id:
            raise GameLifecycleError("Fight activation movement distance source_id drift.")
        if resolved_kind is ProposalKind.PILE_IN:
            effect_distance = _validate_positive_float(
                "pile_in_distance_inches",
                payload.get("pile_in_distance_inches"),
            )
        else:
            effect_distance = _validate_positive_float(
                "consolidate_distance_inches",
                payload.get("consolidate_distance_inches"),
            )
        maximum_distance = max(maximum_distance, effect_distance)
    return maximum_distance


def melee_target_unit_ids(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
    state: GameState | None = None,
) -> tuple[str, ...]:
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    return _engaged_enemy_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        state=state,
    )


def available_melee_weapons_payloads(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    state: GameState | None = None,
    source_decision_result_id: str | None = None,
) -> tuple[JsonValue, ...]:
    return tuple(
        validate_json_value(
            {
                "model_instance_id": weapon["model_instance_id"],
                "wargear_id": weapon["wargear_id"],
                "weapon_profile_id": weapon["weapon_profile"].profile_id,
                "weapon_profile": weapon["weapon_profile"].to_payload(),
                "is_extra_attacks": _is_extra_attacks_weapon(weapon["weapon_profile"]),
                "maximum_declared_targets": _maximum_attacks_for_profile(weapon["weapon_profile"]),
                "fixed_attacks": weapon["weapon_profile"].attack_profile.fixed_attacks,
                "engaged_target_unit_instance_ids": list(
                    _melee_target_unit_ids_for_model(
                        scenario=scenario,
                        ruleset_descriptor=ruleset_descriptor,
                        unit_instance_id=unit.unit_instance_id,
                        model_instance_id=weapon["model_instance_id"],
                        state=state,
                        source_decision_result_id=source_decision_result_id,
                    )
                ),
            }
        )
        for weapon in _available_melee_weapons_for_unit(
            unit=unit,
            army_catalog=army_catalog,
            state=state,
        )
    )


def validate_melee_declaration_rules(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    request: MeleeDeclarationProposalRequest,
    proposal: MeleeDeclarationProposal,
    army_catalog: ArmyCatalog,
    state: GameState | None = None,
) -> ProposalValidationResult:
    if ruleset_descriptor.descriptor_hash != request.ruleset_descriptor_hash:
        return _invalid_melee_validation(
            request=request,
            violation_code="ruleset_descriptor_hash_drift",
            message="Melee declaration request ruleset descriptor hash drifted.",
            field="ruleset_descriptor_hash",
            status="stale",
        )
    if proposal.proposal_kind != request.proposal_kind:
        return _invalid_melee_validation(
            request=request,
            violation_code="proposal_kind_drift",
            message="Melee declaration proposal_kind does not match the pending request.",
            field="proposal_kind",
        )
    if not proposal.declarations:
        return _invalid_melee_validation(
            request=request,
            violation_code="melee_declaration_required",
            message="A fighting unit must declare melee attacks when it has legal attacks.",
            field="declarations",
        )
    unit = _unit_by_id(scenario=scenario, unit_instance_id=proposal.unit_instance_id)
    available = _available_melee_weapons_by_key(
        unit=unit,
        army_catalog=army_catalog,
        state=state,
    )
    required_primary_model_ids = _required_primary_melee_model_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit=unit,
        available=available,
        state=state,
        source_decision_result_id=request.source_decision_result_id,
    )
    declared_primary_model_ids: set[str] = set()
    declared_weapon_keys: set[tuple[str, str, str]] = set()
    for declaration in proposal.declarations:
        key = declaration.weapon_key
        if key in declared_weapon_keys:
            return _invalid_melee_validation(
                request=request,
                violation_code="duplicate_melee_weapon_declaration",
                message="Each model/wargear/profile melee declaration may be used once.",
                field="declarations",
            )
        declared_weapon_keys.add(key)
        profile = available.get(key)
        if profile is None:
            return _invalid_melee_validation(
                request=request,
                violation_code="melee_weapon_not_available",
                message="Melee declaration selected a weapon that is not available.",
                field="declarations",
            )
        if profile.range_profile.kind is not RangeProfileKind.MELEE:
            return _invalid_melee_validation(
                request=request,
                violation_code="melee_weapon_not_melee",
                message="Melee declaration selected a non-melee weapon profile.",
                field="weapon_profile_id",
            )
        engaged_target_ids = _melee_target_unit_ids_for_model(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_instance_id=proposal.unit_instance_id,
            model_instance_id=declaration.attacker_model_instance_id,
            state=state,
            source_decision_result_id=request.source_decision_result_id,
        )
        if not engaged_target_ids:
            return _invalid_melee_validation(
                request=request,
                violation_code="melee_model_not_engaged",
                message="Declared melee model is not engaged with any enemy unit.",
                field="attacker_model_instance_id",
            )
        target_count_validation = _validate_melee_target_count_limit(
            request=request,
            declaration=declaration,
            profile=profile,
        )
        if target_count_validation is not None:
            return target_count_validation
        for allocation in declaration.target_allocations:
            if allocation.target_unit_instance_id not in engaged_target_ids:
                return _invalid_melee_validation(
                    request=request,
                    violation_code="melee_target_not_engaged_with_model",
                    message="Melee declaration target is not engaged with the attacking model.",
                    field="target_allocations",
                )
        attack_allocation_validation = _validate_melee_target_allocation_counts(
            request=request,
            declaration=declaration,
            profile=profile,
            scenario=scenario,
        )
        if attack_allocation_validation is not None:
            return attack_allocation_validation
        if _is_extra_attacks_weapon(profile):
            continue
        if declaration.attacker_model_instance_id in declared_primary_model_ids:
            return _invalid_melee_validation(
                request=request,
                violation_code="melee_model_declared_multiple_weapons",
                message="A melee model cannot declare more than one non-extra-attack weapon.",
                field="attacker_model_instance_id",
            )
        declared_primary_model_ids.add(declaration.attacker_model_instance_id)
    missing_primary = required_primary_model_ids - declared_primary_model_ids
    if missing_primary:
        return _invalid_melee_validation(
            request=request,
            violation_code="melee_primary_weapon_required",
            message="Each fighting model must select one non-extra melee weapon.",
            field="declarations",
        )
    return ProposalValidationResult.valid(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.MELEE_DECLARATION,
    )


def melee_attack_sequence_from_proposal(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal: MeleeDeclarationProposal,
    army_catalog: ArmyCatalog,
    dice_manager: DiceRollManager,
    sequence_id: str,
    state: GameState | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> AttackSequence:
    unit = _unit_by_id(scenario=scenario, unit_instance_id=proposal.unit_instance_id)
    available = _available_melee_weapons_by_key(
        unit=unit,
        army_catalog=army_catalog,
        state=state,
    )
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    pools: list[RangedAttackPool] = []
    for declaration_index, declaration in enumerate(proposal.declarations):
        profile = available[declaration.weapon_key]
        profile = _epic_challenge_profile_if_applicable(
            state=state,
            unit_instance_id=proposal.unit_instance_id,
            attacker_model_instance_id=declaration.attacker_model_instance_id,
            profile=profile,
        )
        resolved_attacks = attacks_for_profile(
            profile,
            manager=dice_manager,
            scope_id=(
                f"{sequence_id}:declaration-{declaration_index:03d}:"
                f"{declaration.attacker_model_instance_id}:{declaration.wargear_id}:"
                f"{declaration.weapon_profile_id}:attacks"
            ),
            actor_id=proposal.player_id,
        )
        single_target = len(declaration.target_allocations) == 1
        if not single_target:
            declared_total = sum(
                _require_declared_melee_attacks(allocation)
                for allocation in declaration.target_allocations
            )
            if declared_total != resolved_attacks:
                raise GameLifecycleError("Melee split attack total drifted after validation.")
        for allocation in declaration.target_allocations:
            pool_profile = _modified_melee_weapon_profile(
                state=state,
                runtime_modifier_registry=runtime_modifiers,
                attacking_unit_instance_id=proposal.unit_instance_id,
                attacker_model_instance_id=declaration.attacker_model_instance_id,
                target_unit_instance_id=allocation.target_unit_instance_id,
                profile=profile,
            )
            cleave_bonus = _cleave_attack_bonus_for_target(
                scenario=scenario,
                profile=pool_profile,
                single_target=single_target,
                target_unit_instance_id=allocation.target_unit_instance_id,
            )
            attacks = (
                resolved_attacks + cleave_bonus
                if single_target
                else _require_declared_melee_attacks(allocation)
            )
            targeting_rule_ids = _melee_targeting_rule_ids(
                profile=pool_profile,
                cleave_bonus=cleave_bonus,
                unit_made_charge_move=_unit_made_charge_move(
                    state=state,
                    unit_instance_id=proposal.unit_instance_id,
                ),
                extra_rule_ids=_melee_targeting_permission_sources_for_model_target(
                    scenario=scenario,
                    target_unit_instance_id=allocation.target_unit_instance_id,
                    attacker_model_instance_id=declaration.attacker_model_instance_id,
                    state=state,
                    source_decision_result_id=proposal.source_decision_result_id,
                ),
            )
            target_model_ids = _target_model_ids_for_melee_attack(
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                unit_instance_id=proposal.unit_instance_id,
                model_instance_id=declaration.attacker_model_instance_id,
                target_unit_instance_id=allocation.target_unit_instance_id,
                state=state,
                source_decision_result_id=proposal.source_decision_result_id,
            )
            pools.append(
                RangedAttackPool.from_declaration(
                    declaration=WeaponDeclaration(
                        attacker_model_instance_id=declaration.attacker_model_instance_id,
                        wargear_id=declaration.wargear_id,
                        weapon_profile_id=declaration.weapon_profile_id,
                        target_unit_instance_id=allocation.target_unit_instance_id,
                        shooting_type=ShootingType.NORMAL,
                    ),
                    weapon_profile=pool_profile,
                    attacks=attacks,
                    target_visible_model_ids=target_model_ids,
                    target_in_range_model_ids=target_model_ids,
                    hit_roll_modifier=0,
                    targeting_rule_ids=targeting_rule_ids,
                )
            )
    return AttackSequence(
        sequence_id=sequence_id,
        source_phase=BattlePhase.FIGHT,
        attacker_player_id=proposal.player_id,
        attacking_unit_instance_id=proposal.unit_instance_id,
        attack_pools=tuple(pools),
    )


def record_one_shot_melee_weapon_uses(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    proposal: MeleeDeclarationProposal,
    army_catalog: ArmyCatalog,
    result_id: str,
) -> tuple[OneShotWeaponUseRecord, ...]:
    unit = _unit_by_id(scenario=scenario, unit_instance_id=proposal.unit_instance_id)
    available = _available_melee_weapons_by_key(
        unit=unit,
        army_catalog=army_catalog,
        state=None,
    )
    records: list[OneShotWeaponUseRecord] = []
    for declaration_index, declaration in enumerate(proposal.declarations, start=1):
        profile = available.get(declaration.weapon_key)
        if profile is None:
            raise GameLifecycleError("Accepted melee declaration references an unknown weapon.")
        if not has_weapon_keyword(profile, WeaponKeyword.ONE_SHOT):
            continue
        records.append(
            state.record_one_shot_weapon_selected(
                model_instance_id=declaration.attacker_model_instance_id,
                wargear_id=declaration.wargear_id,
                weapon_profile_id=declaration.weapon_profile_id,
                source_phase=BattlePhase.FIGHT,
                selection_id=f"{result_id}:one-shot-melee-{declaration_index:03d}",
            )
        )
    return tuple(records)


def _epic_challenge_profile_if_applicable(
    *,
    state: GameState | None,
    unit_instance_id: str,
    attacker_model_instance_id: str,
    profile: WeaponProfile,
) -> WeaponProfile:
    if state is None:
        return profile
    model_id = _validate_identifier("attacker_model_instance_id", attacker_model_instance_id)
    unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for effect in state.persisting_effects:
        if unit_id not in effect.target_unit_instance_ids:
            continue
        effect_payload = effect.effect_payload
        if not isinstance(effect_payload, dict):
            continue
        if effect_payload.get("effect_kind") != "epic_challenge_precision":
            continue
        if effect_payload.get("model_instance_id") != model_id:
            continue
        if WeaponKeyword.PRECISION in profile.keywords:
            return profile
        return replace(
            profile,
            keywords=tuple(sorted((*profile.keywords, WeaponKeyword.PRECISION))),
        )
    return profile


def _modified_melee_weapon_profile(
    *,
    state: GameState | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str,
    target_unit_instance_id: str,
    profile: WeaponProfile,
) -> WeaponProfile:
    if state is None:
        return profile
    return runtime_modifier_registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=attacking_unit_instance_id,
            attacker_model_instance_id=attacker_model_instance_id,
            target_unit_instance_id=target_unit_instance_id,
            weapon_profile=profile,
        )
    )


def _runtime_modifier_registry(
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> RuntimeModifierRegistry:
    if runtime_modifier_registry is None:
        return RuntimeModifierRegistry.empty()
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Fight resolution runtime modifiers must be a registry.")
    return runtime_modifier_registry


def _pile_in_rule_validation(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
    state: GameState | None,
) -> ProposalValidationResult:
    legal_targets = legal_pile_in_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_instance_id=proposal.unit_instance_id,
        state=state,
    )
    if not legal_targets:
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="pile_in_no_legal_targets",
            message="Pile In proposal has no legal target units.",
            field="pile_in_target_unit_instance_ids",
        )
    selected = proposal.pile_in_target_unit_instance_ids
    if not selected:
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="pile_in_target_required",
            message="Pile In movement requires one or more target units.",
            field="pile_in_target_unit_instance_ids",
        )
    if set(selected) != set(legal_targets) and _unit_is_engaged(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_instance_id=proposal.unit_instance_id,
    ):
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="pile_in_engaged_targets_must_be_complete",
            message="An engaged unit must select every engaged enemy as pile-in targets.",
            field="pile_in_target_unit_instance_ids",
        )
    if set(selected) - set(legal_targets):
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="pile_in_target_not_legal",
            message="Pile In selected a target outside legal target units.",
            field="pile_in_target_unit_instance_ids",
        )
    return ProposalValidationResult.valid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
    )


def _consolidate_rule_validation(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
    state: GameState | None,
) -> ProposalValidationResult:
    if proposal.consolidation_mode is None:
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="consolidation_mode_required",
            message="Consolidation movement requires a consolidation mode.",
            field="consolidation_mode",
        )
    unit_placement = scenario.battlefield_state.unit_placement_by_id(proposal.unit_instance_id)
    engaged = _engaged_enemy_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        state=state,
    )
    if engaged:
        if proposal.consolidation_mode is not ConsolidationModeKind.ONGOING:
            return _invalid_consolidation_mode(proposal_request, "ongoing")
        if set(proposal.consolidate_target_unit_instance_ids) != set(engaged):
            return ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="ongoing_consolidation_targets_must_be_complete",
                message="Ongoing Consolidation must select every engaged enemy unit.",
                field="consolidate_target_unit_instance_ids",
            )
        return ProposalValidationResult.valid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
        )
    enemies_within_3 = _enemy_unit_ids_within_distance(
        scenario=scenario,
        unit_placement=unit_placement,
        distance_inches=CONSOLIDATE_ENEMY_DISTANCE_INCHES,
        state=state,
    )
    if enemies_within_3:
        if proposal.consolidation_mode is not ConsolidationModeKind.ENGAGING:
            return _invalid_consolidation_mode(proposal_request, "engaging")
        selected = set(proposal.consolidate_target_unit_instance_ids)
        if not selected or selected - set(enemies_within_3):
            return ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="engaging_consolidation_target_not_legal",
                message=(
                    "Engaging Consolidation requires one or more enemy targets within 3 inches."
                ),
                field="consolidate_target_unit_instance_ids",
            )
        return ProposalValidationResult.valid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
        )
    objective_ids = {
        marker.objective_marker_id
        for marker in _objective_markers_from_context(proposal_request)
        if _unit_within_objective_marker(
            unit_placement=unit_placement,
            objective_marker=marker,
        )
    }
    if objective_ids:
        if proposal.consolidation_mode is not ConsolidationModeKind.OBJECTIVE:
            return _invalid_consolidation_mode(proposal_request, "objective")
        if proposal.objective_id not in objective_ids:
            return ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="objective_consolidation_target_not_legal",
                message="Objective Consolidation requires one objective marker within range.",
                field="objective_id",
            )
        return ProposalValidationResult.valid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
        )
    return ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code="consolidation_no_legal_mode",
        message="Consolidation proposal has no legal mode.",
        field="consolidation_mode",
    )


def _pile_in_endpoint_validation(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
    after: UnitPlacement,
    state: GameState | None,
) -> ProposalValidationResult | None:
    before = scenario.battlefield_state.unit_placement_by_id(proposal.unit_instance_id)
    base_contact_violation = _base_contact_movement_violation(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        before=before,
        after=after,
        state=state,
    )
    if base_contact_violation is not None:
        return _endpoint_invalid(proposal_request, base_contact_violation, "witness")
    closer_violation = _moved_models_closer_to_targets_violation(
        scenario=scenario,
        before=before,
        after=after,
        target_unit_instance_ids=proposal.pile_in_target_unit_instance_ids,
        state=state,
    )
    if closer_violation is not None:
        return _endpoint_invalid(proposal_request, closer_violation, "witness")
    if not _unit_is_engaged_with_any(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=after,
        target_unit_instance_ids=proposal.pile_in_target_unit_instance_ids,
        state=state,
    ):
        return _endpoint_invalid(proposal_request, "pile_in_unit_not_engaged_after", "witness")
    continuing_violation = _continuing_engagement_violation(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        before=before,
        after=after,
        state=state,
    )
    if continuing_violation is not None:
        return _endpoint_invalid(proposal_request, continuing_violation, "witness")
    return None


def _consolidate_endpoint_validation(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
    after: UnitPlacement,
    state: GameState | None,
) -> ProposalValidationResult | None:
    before = scenario.battlefield_state.unit_placement_by_id(proposal.unit_instance_id)
    if proposal.consolidation_mode in {
        ConsolidationModeKind.ONGOING,
        ConsolidationModeKind.ENGAGING,
    }:
        base_contact_violation = _base_contact_movement_violation(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            before=before,
            after=after,
            state=state,
        )
        if base_contact_violation is not None:
            return _endpoint_invalid(proposal_request, base_contact_violation, "witness")
        closer_violation = _moved_models_closer_to_targets_violation(
            scenario=scenario,
            before=before,
            after=after,
            target_unit_instance_ids=proposal.consolidate_target_unit_instance_ids,
            state=state,
        )
        if closer_violation is not None:
            return _endpoint_invalid(proposal_request, closer_violation, "witness")
        if proposal.consolidation_mode is ConsolidationModeKind.ONGOING:
            continuing_violation = _continuing_engagement_violation(
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                before=before,
                after=after,
                state=state,
            )
            if continuing_violation is not None:
                return _endpoint_invalid(proposal_request, continuing_violation, "witness")
        if proposal.consolidation_mode is ConsolidationModeKind.ENGAGING:
            for target_id in proposal.consolidate_target_unit_instance_ids:
                if not _unit_is_engaged_with_any(
                    scenario=scenario,
                    ruleset_descriptor=ruleset_descriptor,
                    unit_placement=after,
                    target_unit_instance_ids=(target_id,),
                    state=state,
                ):
                    return _endpoint_invalid(
                        proposal_request,
                        "engaging_consolidation_target_not_engaged_after",
                        "witness",
                    )
    if proposal.consolidation_mode is ConsolidationModeKind.OBJECTIVE:
        marker = _objective_marker_by_id(
            proposal_request=proposal_request,
            objective_id=proposal.objective_id,
        )
        if not _unit_within_objective_marker(unit_placement=after, objective_marker=marker):
            return _endpoint_invalid(
                proposal_request, "objective_consolidation_not_in_range", "witness"
            )
    return None


def _validate_fight_paths(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    before: UnitPlacement,
    after: UnitPlacement,
    witness: PathWitness,
    movement_mode: MovementMode,
    displacement_kind: ModelDisplacementKind,
    distance_budget_inches: float,
) -> tuple[tuple[PathValidationResult, ...], tuple[TerrainPathLegalityResult, ...]]:
    path_results: list[PathValidationResult] = []
    terrain_results: list[TerrainPathLegalityResult] = []
    terrain_features = scenario.battlefield_state.terrain_features
    terrain_volumes = _terrain_volumes_for_features(terrain_features)
    unit = scenario.unit_instance_for_placement(before)
    for placement in before.model_placements:
        moving_model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        model_witness = PathWitness.for_paths(
            ((placement.model_instance_id, witness.poses_for_model(placement.model_instance_id)),)
        )
        legality_context = MovementLegalityContext.from_keywords(
            keywords=unit.keywords,
            ruleset_descriptor=ruleset_descriptor,
            movement_mode=movement_mode,
            movement_phase_action=None,
            displacement_kind=displacement_kind,
        )
        path_results.append(
            legality_context.to_path_validation_context(
                moving_model=moving_model,
                witness=model_witness,
                battlefield_width_inches=scenario.battlefield_state.battlefield_width_inches,
                battlefield_depth_inches=scenario.battlefield_state.battlefield_depth_inches,
                friendly_models=_friendly_geometry_models_for_path(
                    scenario=scenario,
                    unit_placement=before,
                    attempted_placement=after,
                    moving_model_instance_id=placement.model_instance_id,
                ),
                enemy_models=_enemy_geometry_models_for_player(
                    scenario=scenario,
                    player_id=before.player_id,
                ),
                terrain=(),
                movement_distance_budget_inches=distance_budget_inches,
            ).validate()
        )
        terrain_results.append(
            legality_context.to_terrain_path_legality_context(
                moving_model=moving_model,
                witness=model_witness,
                terrain=terrain_volumes,
                terrain_features=terrain_features,
            ).validate()
        )
    return (tuple(path_results), tuple(terrain_results))


def _fight_movement_transition_batch(
    *,
    before: UnitPlacement,
    after: UnitPlacement,
    witness: PathWitness | None,
    displacement_kind: ModelDisplacementKind,
    source_step: str,
) -> BattlefieldTransitionBatch:
    before_poses = {
        placement.model_instance_id: placement.pose for placement in before.model_placements
    }
    records: list[ModelDisplacementRecord] = []
    for placement in after.model_placements:
        start_pose = before_poses[placement.model_instance_id]
        if placement.pose == start_pose:
            continue
        if witness is None:
            raise GameLifecycleError("Fight movement displacement requires witness.")
        model_path = witness.poses_for_model(placement.model_instance_id)
        records.append(
            ModelDisplacementRecord(
                model_instance_id=placement.model_instance_id,
                displacement_kind=displacement_kind,
                start_pose=start_pose,
                end_pose=placement.pose,
                path_witness=PathWitness.for_paths(((placement.model_instance_id, model_path),)),
                source_phase=BattlePhase.FIGHT.value,
                source_step=source_step,
                source_rule_id=None,
                source_event_id=None,
            )
        )
    return BattlefieldTransitionBatch(displacements=tuple(records))


def _attempted_placement_from_witness(
    *,
    unit_placement: UnitPlacement,
    witness: PathWitness,
) -> UnitPlacement:
    placements: list[ModelPlacement] = []
    for placement in unit_placement.model_placements:
        placements.append(
            placement.with_pose(witness.final_pose_for_model(placement.model_instance_id))
        )
    return unit_placement.with_model_placements(tuple(placements))


def _endpoint_witness(
    *,
    scenario: BattlefieldScenario,
    before: UnitPlacement,
    after: UnitPlacement,
    target_unit_instance_ids: tuple[str, ...],
    objective_id: str | None,
    ruleset_descriptor: RulesetDescriptor,
    state: GameState | None,
) -> FightMovementEndpointPayload:
    moved_model_ids = tuple(
        placement.model_instance_id
        for placement in after.model_placements
        if placement.pose != _model_pose(before, placement.model_instance_id)
    )
    return {
        "target_unit_instance_ids": list(target_unit_instance_ids),
        "objective_id": objective_id,
        "moved_model_instance_ids": list(moved_model_ids),
        "engaged_before_unit_ids": list(
            _engaged_enemy_unit_ids(
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                unit_placement=before,
                state=state,
            )
        ),
        "engaged_after_unit_ids": list(
            _engaged_enemy_unit_ids(
                scenario=_scenario_with_unit_placement(scenario=scenario, placement=after),
                ruleset_descriptor=ruleset_descriptor,
                unit_placement=after,
                state=state,
            )
        ),
    }


def _scenario_with_unit_placement(
    *,
    scenario: BattlefieldScenario,
    placement: UnitPlacement,
) -> BattlefieldScenario:
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.with_unit_placement(placement),
        present_destroyed_model_ids=scenario.present_destroyed_model_ids,
    )


def _base_contact_movement_violation(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    before: UnitPlacement,
    after: UnitPlacement,
    state: GameState | None,
) -> str | None:
    after_by_id = {
        placement.model_instance_id: placement.pose for placement in after.model_placements
    }
    for model in _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=before,
        state=state,
    ):
        if not _model_in_base_contact_with_enemy(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            model=model,
            player_id=before.player_id,
            base_contact_epsilon=_BASE_CONTACT_EPSILON,
            state=state,
        ):
            continue
        if after_by_id[model.model_id] != model.pose:
            return "base_contact_model_moved"
    return None


def _moved_models_closer_to_targets_violation(
    *,
    scenario: BattlefieldScenario,
    before: UnitPlacement,
    after: UnitPlacement,
    target_unit_instance_ids: tuple[str, ...],
    state: GameState | None,
) -> str | None:
    if not target_unit_instance_ids:
        return "target_unit_required"
    after_scenario = _scenario_with_unit_placement(scenario=scenario, placement=after)
    for placement in after.model_placements:
        before_pose = _model_pose(before, placement.model_instance_id)
        if placement.pose == before_pose:
            continue
        before_distance = _closest_model_distance_to_units(
            scenario=scenario,
            model_instance_id=placement.model_instance_id,
            model_pose=before_pose,
            target_unit_instance_ids=target_unit_instance_ids,
            state=state,
        )
        after_distance = _closest_model_distance_to_units(
            scenario=after_scenario,
            model_instance_id=placement.model_instance_id,
            model_pose=placement.pose,
            target_unit_instance_ids=target_unit_instance_ids,
            state=state,
        )
        if not after_distance < before_distance - _CLOSER_EPSILON:
            return "moved_model_not_closer_to_target"
    return None


def _continuing_engagement_violation(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    before: UnitPlacement,
    after: UnitPlacement,
    state: GameState | None,
) -> str | None:
    after_scenario = _scenario_with_unit_placement(scenario=scenario, placement=after)
    for before_model in _geometry_models_for_unit_placement(
        scenario=scenario, unit_placement=before, state=state
    ):
        for enemy_unit_id in _enemy_unit_ids_for_placement(
            scenario=scenario,
            unit_placement=before,
        ):
            enemy_models = _geometry_models_for_unit(
                scenario=scenario,
                unit_instance_id=enemy_unit_id,
                state=state,
            )
            if not _model_engaged_with_any(
                model=before_model,
                target_models=enemy_models,
                ruleset_descriptor=ruleset_descriptor,
            ):
                continue
            after_model = _geometry_model_for_model_pose(
                scenario=after_scenario,
                unit_placement=after,
                model_instance_id=before_model.model_id,
                pose=_model_pose(after, before_model.model_id),
            )
            after_enemy_models = _geometry_models_for_unit(
                scenario=after_scenario,
                unit_instance_id=enemy_unit_id,
                state=state,
            )
            if not _model_engaged_with_any(
                model=after_model,
                target_models=after_enemy_models,
                ruleset_descriptor=ruleset_descriptor,
            ):
                return "started_engaged_model_not_engaged_after"
    return None


def _unit_is_engaged_with_any(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    target_unit_instance_ids: tuple[str, ...],
    state: GameState | None,
) -> bool:
    source_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=unit_placement,
        state=state,
    )
    target_models = tuple(
        model
        for target_id in target_unit_instance_ids
        for model in _geometry_models_for_unit(
            scenario=scenario,
            unit_instance_id=target_id,
            state=state,
        )
    )
    return any(
        model.is_within_engagement_range(
            target,
            horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
            vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
        )
        for model in source_models
        for target in target_models
    )


def _unit_is_engaged(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
) -> bool:
    placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    return bool(
        _engaged_enemy_unit_ids(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=placement,
        )
    )


def _engaged_enemy_unit_ids(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    state: GameState | None = None,
) -> tuple[str, ...]:
    source_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=unit_placement,
        state=state,
    )
    engaged: list[str] = []
    for enemy_unit_id in _enemy_unit_ids_for_placement(
        scenario=scenario,
        unit_placement=unit_placement,
    ):
        enemy_models = _geometry_models_for_unit(
            scenario=scenario,
            unit_instance_id=enemy_unit_id,
            state=state,
        )
        if any(
            source_model.is_within_engagement_range(
                enemy_model,
                horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
            )
            for source_model in source_models
            for enemy_model in enemy_models
        ):
            engaged.append(enemy_unit_id)
    return tuple(sorted(engaged))


def _engaged_enemy_unit_ids_for_model(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
    model_instance_id: str,
    state: GameState | None = None,
) -> tuple[str, ...]:
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    source_model = _geometry_model_for_unit_model(
        scenario=scenario,
        unit_placement=unit_placement,
        model_instance_id=model_instance_id,
    )
    engaged: list[str] = []
    for enemy_unit_id in _enemy_unit_ids_for_placement(
        scenario=scenario,
        unit_placement=unit_placement,
    ):
        enemy_models = _geometry_models_for_unit(
            scenario=scenario,
            unit_instance_id=enemy_unit_id,
            state=state,
        )
        if _model_engaged_with_any(
            model=source_model,
            target_models=enemy_models,
            ruleset_descriptor=ruleset_descriptor,
        ):
            engaged.append(enemy_unit_id)
    return tuple(sorted(engaged))


def _melee_target_unit_ids_for_model(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
    model_instance_id: str,
    state: GameState | None,
    source_decision_result_id: str | None,
) -> tuple[str, ...]:
    engaged = _engaged_enemy_unit_ids_for_model(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_instance_id=unit_instance_id,
        model_instance_id=model_instance_id,
        state=state,
    )
    extended = _extended_melee_target_unit_ids_for_model(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_instance_id=unit_instance_id,
        model_instance_id=model_instance_id,
        state=state,
        source_decision_result_id=source_decision_result_id,
    )
    return tuple(sorted({*engaged, *extended}))


def _extended_melee_target_unit_ids_for_model(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
    model_instance_id: str,
    state: GameState | None,
    source_decision_result_id: str | None,
) -> tuple[str, ...]:
    effects = _fight_activation_melee_targeting_effects(
        state=state,
        unit_instance_id=unit_instance_id,
        source_decision_result_id=source_decision_result_id,
    )
    if not effects:
        return ()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    source_model = _geometry_model_for_unit_model(
        scenario=scenario,
        unit_placement=unit_placement,
        model_instance_id=model_instance_id,
    )
    engaged_unit_ids = _engaged_enemy_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        state=state,
    )
    extended: list[str] = []
    for enemy_unit_id in engaged_unit_ids:
        enemy_models = _geometry_models_for_unit(
            scenario=scenario,
            unit_instance_id=enemy_unit_id,
            state=state,
        )
        if any(
            source_model.range_to(enemy_model) <= effect.model_proximity_inches
            for enemy_model in enemy_models
            for effect in effects
        ):
            extended.append(enemy_unit_id)
    return tuple(sorted(extended))


def _engaged_model_ids_for_model_and_target_unit_or_empty(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
    model_instance_id: str,
    target_unit_instance_id: str,
    state: GameState | None,
) -> tuple[str, ...]:
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    source_model = _geometry_model_for_unit_model(
        scenario=scenario,
        unit_placement=unit_placement,
        model_instance_id=model_instance_id,
    )
    target_models = _geometry_models_for_unit(
        scenario=scenario,
        unit_instance_id=target_unit_instance_id,
        state=state,
    )
    return tuple(
        target_model.model_id
        for target_model in target_models
        if source_model.is_within_engagement_range(
            target_model,
            horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
            vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
        )
    )


def _target_model_ids_for_melee_attack(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
    model_instance_id: str,
    target_unit_instance_id: str,
    state: GameState | None,
    source_decision_result_id: str | None,
) -> tuple[str, ...]:
    engaged_model_ids = _engaged_model_ids_for_model_and_target_unit_or_empty(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_instance_id=unit_instance_id,
        model_instance_id=model_instance_id,
        target_unit_instance_id=target_unit_instance_id,
        state=state,
    )
    if engaged_model_ids:
        return engaged_model_ids
    effects = _fight_activation_melee_targeting_effects(
        state=state,
        unit_instance_id=unit_instance_id,
        source_decision_result_id=source_decision_result_id,
    )
    if not effects:
        raise GameLifecycleError("Melee attack pool target engagement drifted.")
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    source_model = _geometry_model_for_unit_model(
        scenario=scenario,
        unit_placement=unit_placement,
        model_instance_id=model_instance_id,
    )
    target_model_ids = tuple(
        target_model.model_id
        for target_model in _geometry_models_for_unit(
            scenario=scenario,
            unit_instance_id=target_unit_instance_id,
            state=state,
        )
        if any(
            source_model.range_to(target_model) <= effect.model_proximity_inches
            for effect in effects
        )
    )
    if not target_model_ids:
        raise GameLifecycleError("Melee attack pool target engagement drifted.")
    return target_model_ids


def _melee_targeting_permission_sources_for_model_target(
    *,
    scenario: BattlefieldScenario,
    target_unit_instance_id: str,
    attacker_model_instance_id: str,
    state: GameState | None,
    source_decision_result_id: str | None,
) -> tuple[str, ...]:
    unit_instance_id = _unit_id_for_model(
        scenario=scenario,
        model_instance_id=attacker_model_instance_id,
    )
    effects = _fight_activation_melee_targeting_effects(
        state=state,
        unit_instance_id=unit_instance_id,
        source_decision_result_id=source_decision_result_id,
    )
    if not effects:
        return ()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    source_model = _geometry_model_for_unit_model(
        scenario=scenario,
        unit_placement=unit_placement,
        model_instance_id=attacker_model_instance_id,
    )
    target_models = _geometry_models_for_unit(
        scenario=scenario,
        unit_instance_id=target_unit_instance_id,
        state=state,
    )
    return tuple(
        sorted(
            {
                effect.source_rule_id
                for effect in effects
                if any(
                    source_model.range_to(target_model) <= effect.model_proximity_inches
                    for target_model in target_models
                )
            }
        )
    )


def _fight_activation_melee_targeting_effects(
    *,
    state: GameState | None,
    unit_instance_id: str,
    source_decision_result_id: str | None,
) -> tuple[_FightActivationMeleeTargetingEffect, ...]:
    if state is None or source_decision_result_id is None:
        return ()
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_activation_result_id = _validate_identifier(
        "source_decision_result_id",
        source_decision_result_id,
    )
    effects: list[_FightActivationMeleeTargetingEffect] = []
    for effect in state.persisting_effects:
        if requested_unit_id not in effect.target_unit_instance_ids:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") != FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND:
            continue
        if payload.get("activation_result_id") != requested_activation_result_id:
            continue
        if payload.get("source_id") != effect.source_rule_id:
            raise GameLifecycleError("Fight activation melee targeting source_id drift.")
        model_proximity_inches = _validate_positive_float(
            "model_proximity_inches",
            payload.get("model_proximity_inches"),
        )
        effects.append(
            _FightActivationMeleeTargetingEffect(
                source_rule_id=effect.source_rule_id,
                model_proximity_inches=model_proximity_inches,
            )
        )
    return tuple(sorted(effects, key=lambda stored: stored.source_rule_id))


def _required_primary_melee_model_ids(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit: UnitInstance,
    available: dict[tuple[str, str, str], WeaponProfile],
    state: GameState | None = None,
    source_decision_result_id: str | None = None,
) -> set[str]:
    model_ids_with_primary: set[str] = set()
    for weapon_key, profile in available.items():
        if not _is_extra_attacks_weapon(profile):
            model_ids_with_primary.add(weapon_key[0])
    required: set[str] = set()
    for model in unit.own_models:
        if model.model_instance_id not in model_ids_with_primary:
            continue
        if state is None and not model.is_alive:
            continue
        if state is not None and not model_is_present_on_battlefield(
            state=state,
            model_instance_id=model.model_instance_id,
        ):
            continue
        if _melee_target_unit_ids_for_model(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            state=state,
            source_decision_result_id=source_decision_result_id,
        ):
            required.add(model.model_instance_id)
    return required


def _objective_markers_within_distance(
    *,
    unit_placement: UnitPlacement,
    objective_markers: tuple[ObjectiveMarker, ...],
    distance_inches: float,
) -> tuple[str, ...]:
    return tuple(
        marker.objective_marker_id
        for marker in objective_markers
        if _unit_distance_to_objective_marker(
            unit_placement=unit_placement,
            objective_marker=marker,
        )
        <= distance_inches
    )


def _unit_within_objective_marker(
    *,
    unit_placement: UnitPlacement,
    objective_marker: ObjectiveMarker,
) -> bool:
    return (
        _unit_distance_to_objective_marker(
            unit_placement=unit_placement,
            objective_marker=objective_marker,
        )
        <= objective_marker.control_horizontal_inches
    )


def _unit_distance_to_objective_marker(
    *,
    unit_placement: UnitPlacement,
    objective_marker: ObjectiveMarker,
) -> float:
    return min(
        placement.pose.position.distance_2d_to(
            Pose.at(objective_marker.x_inches, objective_marker.y_inches).position
        )
        for placement in unit_placement.model_placements
    )


def _objective_marker_by_id(
    *,
    proposal_request: MovementProposalRequest,
    objective_id: str | None,
) -> ObjectiveMarker:
    requested_id = _validate_identifier("objective_id", objective_id)
    for marker in _objective_markers_from_context(proposal_request):
        if marker.objective_marker_id == requested_id:
            return marker
    raise GameLifecycleError("Consolidation objective_id is not in request context.")


def _objective_markers_from_context(
    proposal_request: MovementProposalRequest,
) -> tuple[ObjectiveMarker, ...]:
    context = _proposal_context(proposal_request)
    markers = context.get("objective_markers")
    if not isinstance(markers, list):
        return ()
    return tuple(
        ObjectiveMarker.from_payload(cast(ObjectiveMarkerPayload, marker)) for marker in markers
    )


def _available_melee_weapons_by_key(
    *,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    state: GameState | None = None,
) -> dict[tuple[str, str, str], WeaponProfile]:
    return {
        (
            weapon["model_instance_id"],
            weapon["wargear_id"],
            weapon["weapon_profile"].profile_id,
        ): weapon["weapon_profile"]
        for weapon in _available_melee_weapons_for_unit(
            unit=unit,
            army_catalog=army_catalog,
            state=state,
        )
    }


class _AvailableMeleeWeapon(TypedDict):
    model_instance_id: str
    wargear_id: str
    weapon_profile: WeaponProfile


def _available_melee_weapons_for_unit(
    *,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    state: GameState | None = None,
) -> tuple[_AvailableMeleeWeapon, ...]:
    weapons: list[_AvailableMeleeWeapon] = []
    for model in unit.own_models:
        if state is None and not model.is_alive:
            continue
        if state is not None and not model_is_present_on_battlefield(
            state=state,
            model_instance_id=model.model_instance_id,
        ):
            continue
        for selection in unit.wargear_selections:
            if selection.model_profile_id != model.model_profile_id:
                continue
            for wargear_id in selection.wargear_ids:
                wargear = _wargear_by_id(army_catalog=army_catalog, wargear_id=wargear_id)
                for profile in wargear.weapon_profiles:
                    if profile.range_profile.kind is not RangeProfileKind.MELEE:
                        continue
                    if (
                        state is not None
                        and has_weapon_keyword(profile, WeaponKeyword.ONE_SHOT)
                        and not state.one_shot_weapon_available(
                            model_instance_id=model.model_instance_id,
                            wargear_id=wargear_id,
                            weapon_profile_id=profile.profile_id,
                        )
                    ):
                        continue
                    weapons.append(
                        {
                            "model_instance_id": model.model_instance_id,
                            "wargear_id": wargear_id,
                            "weapon_profile": profile,
                        }
                    )
    return tuple(weapons)


def _wargear_by_id(*, army_catalog: ArmyCatalog, wargear_id: str) -> Wargear:
    requested_wargear_id = _validate_identifier("wargear_id", wargear_id)
    for wargear in army_catalog.wargear:
        if wargear.wargear_id == requested_wargear_id:
            return wargear
    raise GameLifecycleError("Melee wargear_id is not in the ArmyCatalog.")


def _validate_melee_target_allocations(
    values: object,
) -> tuple[MeleeTargetAllocation, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("MeleeWeaponDeclaration target_allocations must be a tuple.")
    allocations: list[MeleeTargetAllocation] = []
    target_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not MeleeTargetAllocation:
            raise GameLifecycleError(
                "MeleeWeaponDeclaration target_allocations must contain melee allocations."
            )
        if value.target_unit_instance_id in target_ids:
            raise GameLifecycleError(
                "MeleeWeaponDeclaration target_allocations must not duplicate target units."
            )
        target_ids.add(value.target_unit_instance_id)
        allocations.append(value)
    if not allocations:
        raise GameLifecycleError("MeleeWeaponDeclaration requires at least one target allocation.")
    return tuple(allocations)


def _validate_melee_weapon_declarations(
    values: object,
) -> tuple[MeleeWeaponDeclaration, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("MeleeDeclarationProposal declarations must be a tuple.")
    declarations: list[MeleeWeaponDeclaration] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not MeleeWeaponDeclaration:
            raise GameLifecycleError(
                "MeleeDeclarationProposal declarations must contain melee declarations."
            )
        declarations.append(value)
    return tuple(declarations)


def _is_extra_attacks_weapon(profile: WeaponProfile) -> bool:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("_is_extra_attacks_weapon requires a WeaponProfile.")
    return WeaponKeyword.EXTRA_ATTACKS in profile.keywords


def _maximum_attacks_for_profile(profile: WeaponProfile) -> int:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("_maximum_attacks_for_profile requires a WeaponProfile.")
    fixed_attacks = profile.attack_profile.fixed_attacks
    if fixed_attacks is not None:
        return _validate_positive_int("WeaponProfile fixed_attacks", fixed_attacks)
    dice_expression = profile.attack_profile.dice_expression
    if dice_expression is None:
        raise GameLifecycleError("Weapon attack profile requires attacks.")
    maximum = dice_expression.quantity * dice_expression.sides + dice_expression.modifier
    return _validate_positive_int("WeaponProfile maximum attacks", maximum)


def _require_declared_melee_attacks(allocation: MeleeTargetAllocation) -> int:
    if type(allocation) is not MeleeTargetAllocation:
        raise GameLifecycleError("_require_declared_melee_attacks requires an allocation.")
    attacks = allocation.attacks
    if attacks is None:
        raise GameLifecycleError("Split melee attack allocation is missing attacks.")
    return attacks


def _validate_melee_target_allocation_counts(
    *,
    request: MeleeDeclarationProposalRequest,
    declaration: MeleeWeaponDeclaration,
    profile: WeaponProfile,
    scenario: BattlefieldScenario,
) -> ProposalValidationResult | None:
    target_count_validation = _validate_melee_target_count_limit(
        request=request,
        declaration=declaration,
        profile=profile,
    )
    if target_count_validation is not None:
        return target_count_validation
    target_count = len(declaration.target_allocations)
    fixed_attacks = profile.attack_profile.fixed_attacks
    if target_count == 1:
        declared_attacks = declaration.target_allocations[0].attacks
        expected_attacks = fixed_attacks
        if expected_attacks is not None:
            expected_attacks += _cleave_attack_bonus_for_target(
                scenario=scenario,
                profile=profile,
                single_target=True,
                target_unit_instance_id=declaration.target_allocations[0].target_unit_instance_id,
            )
        if (
            declared_attacks is not None
            and expected_attacks is not None
            and declared_attacks != expected_attacks
        ):
            return _invalid_melee_validation(
                request=request,
                violation_code="melee_attack_count_drift",
                message="Single-target melee declaration must allocate every weapon attack.",
                field="target_allocations",
            )
        if declared_attacks is not None and fixed_attacks is None:
            return _invalid_melee_validation(
                request=request,
                violation_code="random_melee_single_target_count_declared",
                message="Single-target random Attacks melee declarations must omit attacks.",
                field="target_allocations",
            )
        return None
    if fixed_attacks is None:
        return _invalid_melee_validation(
            request=request,
            violation_code="random_melee_split_unsupported",
            message="Splitting random Attacks melee weapons requires a fixed attack count first.",
            field="target_allocations",
        )
    if any(allocation.attacks is None for allocation in declaration.target_allocations):
        return _invalid_melee_validation(
            request=request,
            violation_code="split_melee_attack_count_required",
            message="Split melee declarations require attacks for every target.",
            field="target_allocations",
        )
    declared_total = sum(
        _require_declared_melee_attacks(allocation) for allocation in declaration.target_allocations
    )
    if declared_total != fixed_attacks:
        return _invalid_melee_validation(
            request=request,
            violation_code="split_melee_attack_count_drift",
            message="Split melee declarations must allocate exactly the weapon Attacks.",
            field="target_allocations",
        )
    return None


def _validate_melee_target_count_limit(
    *,
    request: MeleeDeclarationProposalRequest,
    declaration: MeleeWeaponDeclaration,
    profile: WeaponProfile,
) -> ProposalValidationResult | None:
    maximum_attacks = _maximum_attacks_for_profile(profile)
    if len(declaration.target_allocations) > maximum_attacks:
        return _invalid_melee_validation(
            request=request,
            violation_code="melee_target_count_exceeds_attacks",
            message="Melee declaration cannot select more target units than weapon Attacks.",
            field="target_allocations",
        )
    return None


def _cleave_attack_bonus_for_target(
    *,
    scenario: BattlefieldScenario,
    profile: WeaponProfile,
    single_target: bool,
    target_unit_instance_id: str,
) -> int:
    target_unit = _unit_by_id(scenario=scenario, unit_instance_id=target_unit_instance_id)
    return cleave_attack_bonus(
        profile,
        single_target=single_target,
        target_model_count=len(target_unit.alive_own_models()),
        target_keywords=target_unit.keywords,
    )


def _melee_targeting_rule_ids(
    *,
    profile: WeaponProfile,
    cleave_bonus: int,
    unit_made_charge_move: bool,
    extra_rule_ids: tuple[str, ...] = (),
) -> tuple[str, ...]:
    rule_ids: list[str] = [MELEE_TARGETING_RULE_ID]
    if cleave_bonus > 0:
        rule_ids.append(cleave_rule_id(cleave_bonus))
    if unit_made_charge_move and has_weapon_keyword(profile, WeaponKeyword.LANCE):
        rule_ids.append(LANCE_RULE_ID)
    rule_ids.extend(_validate_identifier("extra_rule_id", rule_id) for rule_id in extra_rule_ids)
    return tuple(dict.fromkeys(rule_ids))


def _unit_made_charge_move(
    *,
    state: GameState | None,
    unit_instance_id: str,
) -> bool:
    if state is None:
        return False
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for effect in state.persisting_effects:
        if requested_unit_id not in effect.target_unit_instance_ids:
            continue
        effect_payload = effect.effect_payload
        if not isinstance(effect_payload, dict):
            continue
        if effect_payload.get("effect_kind") == "charge_grants_fights_first":
            return True
    return False


def _invalid_melee_validation(
    *,
    request: MeleeDeclarationProposalRequest,
    violation_code: str,
    message: str,
    field: str | None,
    status: str = "invalid",
) -> ProposalValidationResult:
    return ProposalValidationResult.invalid(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.MELEE_DECLARATION,
        violation_code=violation_code,
        message=message,
        field=field,
        status=status,
    )


def _invalid_consolidation_mode(
    proposal_request: MovementProposalRequest,
    expected_mode: str,
) -> ProposalValidationResult:
    return ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code="consolidation_mode_drift",
        message=f"Consolidation mode must be {expected_mode}.",
        field="consolidation_mode",
    )


def _endpoint_invalid(
    proposal_request: MovementProposalRequest,
    violation_code: str,
    field: str,
) -> ProposalValidationResult:
    return ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code=violation_code,
        message=f"Fight movement endpoint violates {violation_code}.",
        field=field,
    )


def _displacement_kind_for_proposal(proposal: FightMovementProposal) -> ModelDisplacementKind:
    return _displacement_kind_for_proposal_kind(proposal.proposal_kind)


def _displacement_kind_for_proposal_kind(
    proposal_kind: ProposalKind,
) -> ModelDisplacementKind:
    if proposal_kind is ProposalKind.PILE_IN:
        return ModelDisplacementKind.PILE_IN
    if proposal_kind is ProposalKind.CONSOLIDATE:
        return ModelDisplacementKind.CONSOLIDATE
    raise GameLifecycleError("Unsupported fight movement proposal kind.")


def _maximum_distance_for_proposal_kind(proposal_kind: ProposalKind) -> float:
    if proposal_kind is ProposalKind.PILE_IN:
        return PILE_IN_DISTANCE_INCHES
    if proposal_kind is ProposalKind.CONSOLIDATE:
        return CONSOLIDATE_DISTANCE_INCHES
    raise GameLifecycleError("Unsupported fight movement proposal kind.")


def _friendly_geometry_models_for_path(
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


def _unit_by_id(*, scenario: BattlefieldScenario, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in scenario.armies:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Fight unit was not found.")


def _model_pose(unit_placement: UnitPlacement, model_instance_id: str) -> Pose:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for placement in unit_placement.model_placements:
        if placement.model_instance_id == requested_model_id:
            return placement.pose
    raise GameLifecycleError("Fight movement model pose was not found.")


def _validate_fight_witness_matches_unit(
    *,
    witness: PathWitness,
    unit_placement: UnitPlacement,
) -> None:
    expected_model_ids = tuple(
        sorted(placement.model_instance_id for placement in unit_placement.model_placements)
    )
    if tuple(sorted(witness.model_ids())) != expected_model_ids:
        raise GameLifecycleError("Fight movement witness must match selected unit models.")
    for placement in unit_placement.model_placements:
        if witness.poses_for_model(placement.model_instance_id)[0] != placement.pose:
            raise GameLifecycleError("Fight movement witness must start at current model poses.")


def _endpoint_only_model_id(witness: PathWitness) -> str | None:
    for model_id in witness.model_ids():
        path = witness.poses_for_model(model_id)
        if is_degenerate_endpoint_only_real_movement_path(path):
            return model_id
    return None


def _terrain_volumes_for_features(
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> tuple[TerrainVolume, ...]:
    volumes: list[TerrainVolume] = []
    for feature in terrain_features:
        if type(feature) is not TerrainFeatureDefinition:
            raise GameLifecycleError("terrain_features must contain TerrainFeatureDefinition.")
        volumes.extend(feature.terrain_volumes())
    return tuple(volumes)


def _proposal_context(request: MovementProposalRequest) -> dict[str, JsonValue]:
    if type(request) is not MovementProposalRequest:
        raise GameLifecycleError("Proposal context requires a MovementProposalRequest.")
    return dict(request.context or {})


def _fight_movement_proposal_kind(value: object) -> ProposalKind:
    kind = proposal_kind_from_token(value)
    if kind not in {ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE}:
        raise GameLifecycleError("Fight movement proposal kind must be pile_in or consolidate.")
    return kind


def _fight_movement_action(value: object) -> str:
    action = _validate_identifier("movement_phase_action", value)
    if action not in {PILE_IN_ACTION, CONSOLIDATE_ACTION}:
        raise GameLifecycleError("Fight movement action must be pile_in or consolidate.")
    return action


def _fight_movement_mode(value: object) -> MovementMode:
    mode = movement_mode_from_token(value)
    if mode not in {MovementMode.PILE_IN, MovementMode.CONSOLIDATE}:
        raise GameLifecycleError("Fight movement mode must be pile_in or consolidate.")
    return mode


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"{key} must be a string.")
    return value


def _json_object(field_name: str, value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return cast(dict[str, JsonValue], value)


def _validate_json_object(field_name: str, value: object) -> dict[str, JsonValue]:
    payload = validate_json_value(value)
    if not isinstance(payload, dict):
        raise GameLifecycleError(f"{field_name} must be a JSON object.")
    return payload


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_positive_float(field_name: str, value: object) -> float:
    if type(value) is int:
        converted = float(value)
    elif type(value) is float:
        converted = value
    else:
        raise GameLifecycleError(f"{field_name} must be a number.")
    if converted <= 0.0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return converted


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    return tuple(
        sorted(
            _validate_identifier(f"{field_name} item", value)
            for value in cast(tuple[object, ...], values)
        )
    )


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value


def _validate_path_validation_results(
    values: object,
) -> tuple[PathValidationResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Path validation results must be a tuple.")
    results = cast(tuple[object, ...], values)
    for value in results:
        if type(value) is not PathValidationResult:
            raise GameLifecycleError("Path validation results must contain PathValidationResult.")
    return cast(tuple[PathValidationResult, ...], results)


def _validate_terrain_path_legality_results(
    values: object,
) -> tuple[TerrainPathLegalityResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Terrain path legality results must be a tuple.")
    results = cast(tuple[object, ...], values)
    for value in results:
        if type(value) is not TerrainPathLegalityResult:
            raise GameLifecycleError(
                "Terrain path legality results must contain TerrainPathLegalityResult."
            )
    return cast(tuple[TerrainPathLegalityResult, ...], results)


def _key_error_field(error: KeyError) -> str:
    raw = error.args[0]
    if type(raw) is str:
        return raw
    return "payload"
