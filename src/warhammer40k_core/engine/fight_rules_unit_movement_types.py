from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    movement_mode_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelPlacement,
    UnitPlacement,
    UnitPlacementPayload,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_resolution import (
    FightMovementEndpointPayload,
    FightMovementResolution,
)
from warhammer40k_core.engine.movement_proposals import (
    ProposalKind,
    proposal_kind_from_token,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    current_rules_unit_views_for_canonical_identity,
    current_rules_unit_views_for_identity,
)
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyResult,
    UnitCoherencyResultPayload,
)
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathValidationResultPayload,
    PathWitness,
    PathWitnessPayload,
    TerrainPathLegalityResult,
    TerrainPathLegalityResultPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class FightRulesUnitPlacementPayload(TypedDict):
    rules_unit_instance_id: str
    component_unit_placements: list[UnitPlacementPayload]


@dataclass(frozen=True, slots=True)
class FightRulesUnitPlacement:
    """Present physical components for one canonical attached Fight rules unit."""

    rules_unit_instance_id: str
    component_unit_placements: tuple[UnitPlacement, ...]

    def __post_init__(self) -> None:
        rules_unit_id = _validate_identifier("rules_unit_instance_id", self.rules_unit_instance_id)
        object.__setattr__(self, "rules_unit_instance_id", rules_unit_id)
        if not rules_unit_id.startswith("attached-unit:"):
            raise GameLifecycleError(
                "FightRulesUnitPlacement requires a canonical attached-unit identity."
            )
        if type(self.component_unit_placements) is not tuple:
            raise GameLifecycleError("Fight rules-unit component placements must be a tuple.")
        if not self.component_unit_placements:
            raise GameLifecycleError("Fight rules-unit placement requires present components.")
        components: list[UnitPlacement] = []
        component_ids: set[str] = set()
        model_ids: set[str] = set()
        army_id: str | None = None
        player_id: str | None = None
        for component in self.component_unit_placements:
            if type(component) is not UnitPlacement:
                raise GameLifecycleError("Fight rules-unit components must be UnitPlacement.")
            if component.unit_instance_id in component_ids:
                raise GameLifecycleError("Fight rules-unit component IDs must be unique.")
            component_ids.add(component.unit_instance_id)
            if army_id is None:
                army_id = component.army_id
                player_id = component.player_id
            elif component.army_id != army_id or component.player_id != player_id:
                raise GameLifecycleError("Fight rules-unit components must share one owner.")
            for model in component.model_placements:
                if model.model_instance_id in model_ids:
                    raise GameLifecycleError("Fight rules-unit model IDs must be unique.")
                model_ids.add(model.model_instance_id)
            components.append(component)
        object.__setattr__(
            self,
            "component_unit_placements",
            tuple(sorted(components, key=lambda placement: placement.unit_instance_id)),
        )

    @property
    def component_unit_instance_ids(self) -> tuple[str, ...]:
        return tuple(placement.unit_instance_id for placement in self.component_unit_placements)

    @property
    def model_placements(self) -> tuple[ModelPlacement, ...]:
        return tuple(
            model
            for component in self.component_unit_placements
            for model in component.model_placements
        )

    def to_payload(self) -> FightRulesUnitPlacementPayload:
        return {
            "rules_unit_instance_id": self.rules_unit_instance_id,
            "component_unit_placements": [
                component.to_payload() for component in self.component_unit_placements
            ],
        }

    @classmethod
    def from_payload(cls, payload: FightRulesUnitPlacementPayload) -> Self:
        return cls(
            rules_unit_instance_id=payload["rules_unit_instance_id"],
            component_unit_placements=tuple(
                UnitPlacement.from_payload(component)
                for component in payload["component_unit_placements"]
            ),
        )


class RulesUnitMovementRollbackRecordPayload(TypedDict):
    unit_instance_id: str
    displacement_kind: str
    before_rules_unit_placement: FightRulesUnitPlacementPayload
    attempted_rules_unit_placement: FightRulesUnitPlacementPayload
    coherency_result: UnitCoherencyResultPayload


class RulesUnitFightMovementResolutionPayload(TypedDict):
    movement_mode: str
    movement_phase_action: str
    maximum_distance_inches: float
    rules_unit_instance_id: str
    component_unit_instance_ids: list[str]
    before_rules_unit_placement: FightRulesUnitPlacementPayload
    attempted_rules_unit_placement: FightRulesUnitPlacementPayload
    witness: PathWitnessPayload | None
    endpoint_witness: FightMovementEndpointPayload
    path_validation_results: list[JsonValue]
    terrain_path_legality_results: list[JsonValue]
    coherency_result: JsonValue
    rollback_record: JsonValue | None


@dataclass(frozen=True, slots=True)
class RulesUnitMovementRollbackRecord:
    unit_instance_id: str
    displacement_kind: ModelDisplacementKind
    before_rules_unit_placement: FightRulesUnitPlacement
    attempted_rules_unit_placement: FightRulesUnitPlacement
    coherency_result: UnitCoherencyResult

    def __post_init__(self) -> None:
        unit_id = _validate_identifier("unit_instance_id", self.unit_instance_id)
        object.__setattr__(self, "unit_instance_id", unit_id)
        if type(self.displacement_kind) is not ModelDisplacementKind:
            raise GameLifecycleError(
                "Rules-unit movement rollback displacement_kind must be typed."
            )
        if type(self.before_rules_unit_placement) is not FightRulesUnitPlacement:
            raise GameLifecycleError(
                "Rules-unit movement rollback before placement must be grouped."
            )
        if type(self.attempted_rules_unit_placement) is not FightRulesUnitPlacement:
            raise GameLifecycleError(
                "Rules-unit movement rollback attempted placement must be grouped."
            )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise GameLifecycleError("Rules-unit movement rollback coherency result must be typed.")
        before = self.before_rules_unit_placement
        attempted = self.attempted_rules_unit_placement
        if before.rules_unit_instance_id != unit_id or attempted.rules_unit_instance_id != unit_id:
            raise GameLifecycleError("Rules-unit movement rollback identity drift.")
        if before.component_unit_instance_ids != attempted.component_unit_instance_ids:
            raise GameLifecycleError("Rules-unit movement rollback component identity drift.")
        if _model_ids(before) != _model_ids(attempted):
            raise GameLifecycleError("Rules-unit movement rollback model identity drift.")
        if self.coherency_result.unit_instance_id != unit_id:
            raise GameLifecycleError("Rules-unit movement rollback coherency identity drift.")
        if self.coherency_result.model_instance_ids != _model_ids(attempted):
            raise GameLifecycleError("Rules-unit movement rollback coherency model identity drift.")
        if self.coherency_result.is_coherent:
            raise GameLifecycleError("Rules-unit movement rollback requires broken coherency.")

    def to_payload(self) -> RulesUnitMovementRollbackRecordPayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "displacement_kind": self.displacement_kind.value,
            "before_rules_unit_placement": self.before_rules_unit_placement.to_payload(),
            "attempted_rules_unit_placement": (self.attempted_rules_unit_placement.to_payload()),
            "coherency_result": self.coherency_result.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: RulesUnitMovementRollbackRecordPayload) -> Self:
        return cls(
            unit_instance_id=payload["unit_instance_id"],
            displacement_kind=ModelDisplacementKind(payload["displacement_kind"]),
            before_rules_unit_placement=FightRulesUnitPlacement.from_payload(
                payload["before_rules_unit_placement"]
            ),
            attempted_rules_unit_placement=FightRulesUnitPlacement.from_payload(
                payload["attempted_rules_unit_placement"]
            ),
            coherency_result=UnitCoherencyResult.from_payload(payload["coherency_result"]),
        )


@dataclass(frozen=True, slots=True)
class RulesUnitFightMovementResolution:
    unit_instance_id: str
    proposal_kind: ProposalKind
    movement_phase_action: str
    movement_mode: MovementMode
    maximum_distance_inches: float
    before_rules_unit_placement: FightRulesUnitPlacement
    attempted_rules_unit_placement: FightRulesUnitPlacement
    witness: PathWitness | None
    endpoint_witness: FightMovementEndpointPayload
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult | None
    rollback_record: RulesUnitMovementRollbackRecord | None

    def __post_init__(self) -> None:
        unit_id = _validate_identifier("unit_instance_id", self.unit_instance_id)
        object.__setattr__(self, "unit_instance_id", unit_id)
        proposal_kind = _fight_proposal_kind(self.proposal_kind)
        object.__setattr__(self, "proposal_kind", proposal_kind)
        if type(self.movement_phase_action) is not str or not self.movement_phase_action:
            raise GameLifecycleError("Rules-unit Fight movement action must be a string.")
        if type(self.movement_mode) is not MovementMode:
            raise GameLifecycleError("Rules-unit Fight movement mode must be typed.")
        if (
            self.movement_phase_action != proposal_kind.value
            or self.movement_mode is not _movement_mode_for_proposal_kind(proposal_kind)
        ):
            raise GameLifecycleError("Rules-unit Fight movement action/mode context drift.")
        if (
            type(self.maximum_distance_inches) is not int
            and type(self.maximum_distance_inches) is not float
        ):
            raise GameLifecycleError("Rules-unit Fight movement distance must be numeric.")
        distance = float(self.maximum_distance_inches)
        if distance <= 0.0:
            raise GameLifecycleError("Rules-unit Fight movement distance must be positive.")
        object.__setattr__(self, "maximum_distance_inches", distance)
        before = self.before_rules_unit_placement
        attempted = self.attempted_rules_unit_placement
        if (
            type(before) is not FightRulesUnitPlacement
            or type(attempted) is not FightRulesUnitPlacement
        ):
            raise GameLifecycleError("Rules-unit Fight movement placements must be grouped.")
        if before.rules_unit_instance_id != unit_id or attempted.rules_unit_instance_id != unit_id:
            raise GameLifecycleError("Rules-unit Fight movement placement identity drift.")
        if before.component_unit_instance_ids != attempted.component_unit_instance_ids:
            raise GameLifecycleError("Rules-unit Fight movement component identity drift.")
        if _model_ids(before) != _model_ids(attempted):
            raise GameLifecycleError("Rules-unit Fight movement model identity drift.")
        endpoint_witness, moved_model_ids = _validated_fight_movement_endpoint_witness(
            self.endpoint_witness,
            context="Grouped",
        )
        object.__setattr__(self, "endpoint_witness", endpoint_witness)
        before_poses = {
            placement.model_instance_id: placement.pose for placement in before.model_placements
        }
        changed_model_ids = tuple(
            sorted(
                placement.model_instance_id
                for placement in attempted.model_placements
                if placement.pose != before_poses[placement.model_instance_id]
            )
        )
        if moved_model_ids != changed_model_ids:
            raise GameLifecycleError(
                "Grouped Fight movement endpoint witness model identity drift."
            )
        if self.witness is not None and type(self.witness) is not PathWitness:
            raise GameLifecycleError("Rules-unit Fight movement witness must be typed.")
        _validate_grouped_fight_movement_witness(
            witness=self.witness,
            before=before,
            attempted=attempted,
            moved_model_ids=changed_model_ids,
        )
        if type(self.path_validation_results) is not tuple or any(
            type(result) is not PathValidationResult for result in self.path_validation_results
        ):
            raise GameLifecycleError("Rules-unit Fight path results must be typed.")
        if type(self.terrain_path_legality_results) is not tuple or any(
            type(result) is not TerrainPathLegalityResult
            for result in self.terrain_path_legality_results
        ):
            raise GameLifecycleError("Rules-unit Fight terrain results must be typed.")
        if (
            self.coherency_result is not None
            and type(self.coherency_result) is not UnitCoherencyResult
        ):
            raise GameLifecycleError("Rules-unit Fight coherency result must be typed.")
        if (
            self.rollback_record is not None
            and type(self.rollback_record) is not RulesUnitMovementRollbackRecord
        ):
            raise GameLifecycleError("Rules-unit Fight rollback record must be typed.")
        _validate_grouped_fight_movement_coherency(
            unit_instance_id=unit_id,
            proposal_kind=proposal_kind,
            before=before,
            attempted=attempted,
            moved_model_ids=changed_model_ids,
            coherency_result=self.coherency_result,
            rollback_record=self.rollback_record,
        )

    @property
    def is_valid(self) -> bool:
        return (
            all(result.is_valid for result in self.path_validation_results)
            and all(result.is_valid for result in self.terrain_path_legality_results)
            and self.rollback_record is None
        )

    def transition_batch(self) -> BattlefieldTransitionBatch:
        if not self.is_valid:
            raise GameLifecycleError("Invalid rules-unit Fight movement has no transition.")
        before_poses = {
            placement.model_instance_id: placement.pose
            for placement in self.before_rules_unit_placement.model_placements
        }
        displacements: list[ModelDisplacementRecord] = []
        for placement in self.attempted_rules_unit_placement.model_placements:
            start_pose = before_poses[placement.model_instance_id]
            if placement.pose == start_pose:
                continue
            if self.witness is None:
                raise GameLifecycleError("Fight movement displacement requires a witness.")
            model_path = self.witness.poses_for_model(placement.model_instance_id)
            displacements.append(
                ModelDisplacementRecord(
                    model_instance_id=placement.model_instance_id,
                    displacement_kind=_displacement_kind(self.proposal_kind),
                    start_pose=start_pose,
                    end_pose=placement.pose,
                    path_witness=PathWitness.for_paths(
                        ((placement.model_instance_id, model_path),)
                    ),
                    source_phase=BattlePhase.FIGHT.value,
                    source_step=self.movement_phase_action,
                    source_rule_id=None,
                    source_event_id=None,
                )
            )
        return BattlefieldTransitionBatch(displacements=tuple(displacements))

    def to_payload(self) -> RulesUnitFightMovementResolutionPayload:
        return {
            "movement_mode": self.movement_mode.value,
            "movement_phase_action": self.movement_phase_action,
            "maximum_distance_inches": self.maximum_distance_inches,
            "rules_unit_instance_id": self.unit_instance_id,
            "component_unit_instance_ids": list(
                self.before_rules_unit_placement.component_unit_instance_ids
            ),
            "before_rules_unit_placement": self.before_rules_unit_placement.to_payload(),
            "attempted_rules_unit_placement": (self.attempted_rules_unit_placement.to_payload()),
            "witness": None if self.witness is None else self.witness.to_payload(),
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

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise GameLifecycleError("Grouped Fight movement resolution must be an object.")
        raw_payload = cast(dict[str, object], payload)
        if frozenset(raw_payload) != _GROUPED_FIGHT_RESOLUTION_KEYS:
            raise GameLifecycleError("Grouped Fight movement resolution shape drifted.")
        witness_payload = raw_payload["witness"]
        coherency_payload = raw_payload["coherency_result"]
        rollback_payload = raw_payload["rollback_record"]
        if witness_payload is not None and not isinstance(witness_payload, dict):
            raise GameLifecycleError("Rules-unit Fight witness payload must be an object.")
        if not isinstance(raw_payload["component_unit_instance_ids"], list):
            raise GameLifecycleError("Rules-unit Fight component payload must be a list.")
        if not isinstance(raw_payload["path_validation_results"], list):
            raise GameLifecycleError("Rules-unit Fight path results payload must be a list.")
        if not isinstance(raw_payload["terrain_path_legality_results"], list):
            raise GameLifecycleError("Rules-unit Fight terrain results payload must be a list.")
        if coherency_payload is not None and not isinstance(coherency_payload, dict):
            raise GameLifecycleError("Rules-unit Fight coherency payload must be an object.")
        if rollback_payload is not None and not isinstance(rollback_payload, dict):
            raise GameLifecycleError("Rules-unit Fight rollback payload must be an object.")
        typed_payload = cast(RulesUnitFightMovementResolutionPayload, raw_payload)
        resolution = cls(
            unit_instance_id=typed_payload["rules_unit_instance_id"],
            proposal_kind=_proposal_kind_for_movement_mode(typed_payload["movement_mode"]),
            movement_phase_action=typed_payload["movement_phase_action"],
            movement_mode=movement_mode_from_token(typed_payload["movement_mode"]),
            maximum_distance_inches=typed_payload["maximum_distance_inches"],
            before_rules_unit_placement=FightRulesUnitPlacement.from_payload(
                typed_payload["before_rules_unit_placement"]
            ),
            attempted_rules_unit_placement=FightRulesUnitPlacement.from_payload(
                typed_payload["attempted_rules_unit_placement"]
            ),
            witness=(
                None
                if witness_payload is None
                else PathWitness.from_payload(cast(PathWitnessPayload, witness_payload))
            ),
            endpoint_witness=typed_payload["endpoint_witness"],
            path_validation_results=tuple(
                PathValidationResult.from_payload(cast(PathValidationResultPayload, result))
                for result in typed_payload["path_validation_results"]
            ),
            terrain_path_legality_results=tuple(
                TerrainPathLegalityResult.from_payload(
                    cast(TerrainPathLegalityResultPayload, result)
                )
                for result in typed_payload["terrain_path_legality_results"]
            ),
            coherency_result=(
                None
                if coherency_payload is None
                else UnitCoherencyResult.from_payload(
                    cast(UnitCoherencyResultPayload, coherency_payload)
                )
            ),
            rollback_record=(
                None
                if rollback_payload is None
                else RulesUnitMovementRollbackRecord.from_payload(
                    cast(RulesUnitMovementRollbackRecordPayload, rollback_payload)
                )
            ),
        )
        if typed_payload["component_unit_instance_ids"] != list(
            resolution.before_rules_unit_placement.component_unit_instance_ids
        ):
            raise GameLifecycleError("Rules-unit Fight resolution component payload drift.")
        return resolution


type FightRulesUnitMovementResolution = FightMovementResolution | RulesUnitFightMovementResolution
type FightMovementCompletedEndpoint = UnitPlacement | FightRulesUnitPlacement

_STANDALONE_FIGHT_RESOLUTION_KEYS = frozenset(
    {
        "movement_mode",
        "movement_phase_action",
        "maximum_distance_inches",
        "endpoint_witness",
        "path_validation_results",
        "terrain_path_legality_results",
        "coherency_result",
        "rollback_record",
    }
)
_GROUPED_FIGHT_RESOLUTION_KEYS = frozenset(
    {
        "movement_mode",
        "movement_phase_action",
        "maximum_distance_inches",
        "rules_unit_instance_id",
        "component_unit_instance_ids",
        "before_rules_unit_placement",
        "attempted_rules_unit_placement",
        "witness",
        "endpoint_witness",
        "path_validation_results",
        "terrain_path_legality_results",
        "coherency_result",
        "rollback_record",
    }
)
_FIGHT_MOVEMENT_ENDPOINT_WITNESS_KEYS = frozenset(
    {
        "target_unit_instance_ids",
        "objective_id",
        "moved_model_instance_ids",
        "engaged_before_unit_ids",
        "engaged_after_unit_ids",
    }
)


def fight_rules_unit_movement_endpoint_from_completed_event(
    *,
    payload: Mapping[str, JsonValue],
    component_unit_instance_ids: tuple[str, ...],
) -> FightMovementCompletedEndpoint:
    """Return exact grouped endpoints while preserving the completed event's outer ID."""
    event_unit_id = _validate_identifier(
        "fight movement completed unit_instance_id",
        payload.get("unit_instance_id"),
    )
    if type(component_unit_instance_ids) is not tuple:
        raise GameLifecycleError("Fight movement event component identities must be a tuple.")
    component_ids = tuple(
        sorted(
            _validate_identifier("component_unit_instance_id", component_id)
            for component_id in component_unit_instance_ids
        )
    )
    if not component_ids or len(component_ids) != len(set(component_ids)):
        raise GameLifecycleError(
            "Fight movement event component identities must be non-empty and unique."
        )
    raw_resolution = payload.get("resolution")
    if not isinstance(raw_resolution, dict):
        raise GameLifecycleError("Fight movement completed resolution must be an object.")
    if "rules_unit_instance_id" not in raw_resolution:
        if len(component_ids) > 1:
            raise GameLifecycleError(
                "Attached Fight movement completion requires grouped endpoint evidence."
            )
        if component_ids != (event_unit_id,):
            raise GameLifecycleError(
                "Standalone Fight movement completion component identity drift."
            )
        return _standalone_fight_movement_endpoint_from_completed_event(
            payload=payload,
            event_unit_instance_id=event_unit_id,
            raw_resolution=raw_resolution,
        )
    if "movement_endpoint_placement" in payload:
        raise GameLifecycleError("Grouped Fight movement endpoint evidence shape drifted.")
    resolution = RulesUnitFightMovementResolution.from_payload(
        cast(RulesUnitFightMovementResolutionPayload, raw_resolution)
    )
    if not resolution.is_valid:
        raise GameLifecycleError("Fight movement completed resolution must be valid.")
    if resolution.unit_instance_id != event_unit_id:
        raise GameLifecycleError("Fight movement completed rules-unit identity drift.")
    if resolution.before_rules_unit_placement.component_unit_instance_ids != component_ids:
        raise GameLifecycleError("Fight movement completed component identity drift.")
    outer_proposal_kind = _fight_proposal_kind(
        proposal_kind_from_token(payload.get("proposal_kind"))
    )
    if resolution.proposal_kind is not outer_proposal_kind:
        raise GameLifecycleError("Grouped Fight movement resolution context drifted.")
    raw_transition = payload.get("transition_batch")
    if not isinstance(raw_transition, dict):
        raise GameLifecycleError("Fight movement completed transition batch must be an object.")
    transition = BattlefieldTransitionBatch.from_payload(
        cast(BattlefieldTransitionBatchPayload, raw_transition)
    )
    if transition != resolution.transition_batch():
        raise GameLifecycleError("Fight movement completed transition evidence drift.")
    return resolution.attempted_rules_unit_placement


def _standalone_fight_movement_endpoint_from_completed_event(
    *,
    payload: Mapping[str, JsonValue],
    event_unit_instance_id: str,
    raw_resolution: dict[str, JsonValue],
) -> UnitPlacement:
    if frozenset(raw_resolution) != _STANDALONE_FIGHT_RESOLUTION_KEYS:
        raise GameLifecycleError("Standalone Fight movement resolution shape drifted.")
    raw_endpoint = payload.get("movement_endpoint_placement")
    if not isinstance(raw_endpoint, dict):
        raise GameLifecycleError(
            "Standalone Fight movement completion requires event-time endpoint evidence."
        )
    endpoint = UnitPlacement.from_payload(cast(UnitPlacementPayload, raw_endpoint))
    if endpoint.unit_instance_id != event_unit_instance_id:
        raise GameLifecycleError("Standalone Fight movement endpoint identity drifted.")

    proposal_kind = _fight_proposal_kind(proposal_kind_from_token(payload.get("proposal_kind")))
    expected_mode = (
        MovementMode.PILE_IN if proposal_kind is ProposalKind.PILE_IN else MovementMode.CONSOLIDATE
    )
    movement_mode = movement_mode_from_token(raw_resolution.get("movement_mode"))
    movement_action = raw_resolution.get("movement_phase_action")
    maximum_distance = raw_resolution.get("maximum_distance_inches")
    if movement_mode is not expected_mode or movement_action != proposal_kind.value:
        raise GameLifecycleError("Standalone Fight movement resolution context drifted.")
    if type(maximum_distance) is not int and type(maximum_distance) is not float:
        raise GameLifecycleError("Standalone Fight movement distance evidence is invalid.")
    if float(maximum_distance) <= 0.0:
        raise GameLifecycleError("Standalone Fight movement distance evidence is invalid.")
    if raw_resolution.get("rollback_record") is not None:
        raise GameLifecycleError("Fight movement completed resolution must be valid.")

    path_results = _path_validation_results(raw_resolution.get("path_validation_results"))
    terrain_results = _terrain_path_legality_results(
        raw_resolution.get("terrain_path_legality_results")
    )
    if not all(result.is_valid for result in path_results) or not all(
        result.is_valid for result in terrain_results
    ):
        raise GameLifecycleError("Fight movement completed resolution must be valid.")
    _validate_standalone_coherency_result(
        raw_resolution.get("coherency_result"),
        event_unit_instance_id=event_unit_instance_id,
    )

    _endpoint_witness, moved_model_ids = _validated_fight_movement_endpoint_witness(
        raw_resolution.get("endpoint_witness"),
        context="Standalone",
    )

    raw_transition = payload.get("transition_batch")
    if not isinstance(raw_transition, dict):
        raise GameLifecycleError("Fight movement completed transition batch must be an object.")
    transition = BattlefieldTransitionBatch.from_payload(
        cast(BattlefieldTransitionBatchPayload, raw_transition)
    )
    _validate_standalone_transition_endpoint(
        transition=transition,
        endpoint=endpoint,
        moved_model_ids=moved_model_ids,
        proposal_kind=proposal_kind,
    )
    return endpoint


def _path_validation_results(value: JsonValue | None) -> tuple[PathValidationResult, ...]:
    if not isinstance(value, list):
        raise GameLifecycleError("Standalone Fight path results must be a list.")
    return tuple(
        PathValidationResult.from_payload(cast(PathValidationResultPayload, result))
        for result in value
    )


def _terrain_path_legality_results(
    value: JsonValue | None,
) -> tuple[TerrainPathLegalityResult, ...]:
    if not isinstance(value, list):
        raise GameLifecycleError("Standalone Fight terrain results must be a list.")
    return tuple(
        TerrainPathLegalityResult.from_payload(cast(TerrainPathLegalityResultPayload, result))
        for result in value
    )


def _validate_standalone_coherency_result(
    value: JsonValue | None,
    *,
    event_unit_instance_id: str,
) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise GameLifecycleError("Standalone Fight coherency result must be an object.")
    coherency = UnitCoherencyResult.from_payload(cast(UnitCoherencyResultPayload, value))
    if not coherency.is_coherent or coherency.unit_instance_id != event_unit_instance_id:
        raise GameLifecycleError("Standalone Fight coherency evidence drifted.")


def _validate_standalone_transition_endpoint(
    *,
    transition: BattlefieldTransitionBatch,
    endpoint: UnitPlacement,
    moved_model_ids: tuple[str, ...],
    proposal_kind: ProposalKind,
) -> None:
    if transition.placements or transition.removals:
        raise GameLifecycleError("Standalone Fight movement transition shape drifted.")
    displacement_ids = tuple(
        sorted(displacement.model_instance_id for displacement in transition.displacements)
    )
    if displacement_ids != moved_model_ids:
        raise GameLifecycleError("Standalone Fight movement transition model identity drifted.")
    endpoint_by_model_id = {
        placement.model_instance_id: placement for placement in endpoint.model_placements
    }
    expected_kind = _displacement_kind(proposal_kind)
    for displacement in transition.displacements:
        placement = endpoint_by_model_id.get(displacement.model_instance_id)
        if placement is None or placement.pose != displacement.end_pose:
            raise GameLifecycleError("Standalone Fight movement transition endpoint drifted.")
        if (
            displacement.displacement_kind is not expected_kind
            or displacement.source_phase != BattlePhase.FIGHT.value
            or displacement.source_step != proposal_kind.value
            or displacement.source_rule_id is not None
            or displacement.source_event_id is not None
            or displacement.path_witness is None
        ):
            raise GameLifecycleError("Standalone Fight movement displacement context drifted.")
        path = displacement.path_witness.poses_for_model(displacement.model_instance_id)
        if path[0] != displacement.start_pose or path[-1] != displacement.end_pose:
            raise GameLifecycleError("Standalone Fight movement displacement path drifted.")


def _validated_fight_movement_endpoint_witness(
    value: object,
    *,
    context: str,
) -> tuple[FightMovementEndpointPayload, tuple[str, ...]]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{context} Fight movement endpoint witness shape drifted.")
    raw_value = cast(dict[str, object], value)
    if frozenset(raw_value) != _FIGHT_MOVEMENT_ENDPOINT_WITNESS_KEYS:
        raise GameLifecycleError(f"{context} Fight movement endpoint witness shape drifted.")
    moved_model_ids = _identifier_list(
        raw_value.get("moved_model_instance_ids"),
        label=f"{context} Fight movement moved model IDs",
    )
    for key in (
        "target_unit_instance_ids",
        "engaged_before_unit_ids",
        "engaged_after_unit_ids",
    ):
        _identifier_list(raw_value.get(key), label=f"{context} Fight movement {key}")
    objective_id = raw_value.get("objective_id")
    if objective_id is not None:
        _validate_identifier(f"{context} Fight movement objective_id", objective_id)
    return cast(FightMovementEndpointPayload, validate_json_value(raw_value)), moved_model_ids


def _validate_grouped_fight_movement_witness(
    *,
    witness: PathWitness | None,
    before: FightRulesUnitPlacement,
    attempted: FightRulesUnitPlacement,
    moved_model_ids: tuple[str, ...],
) -> None:
    if not moved_model_ids:
        if witness is not None:
            raise GameLifecycleError("Grouped Fight no-move resolution must not include a witness.")
        return
    if witness is None:
        raise GameLifecycleError("Grouped Fight movement requires a witness.")
    expected_model_ids = _model_ids(before)
    if witness.model_ids() != expected_model_ids:
        raise GameLifecycleError("Grouped Fight movement witness model inventory drifted.")
    before_poses = {
        placement.model_instance_id: placement.pose for placement in before.model_placements
    }
    attempted_poses = {
        placement.model_instance_id: placement.pose for placement in attempted.model_placements
    }
    for model_id in expected_model_ids:
        path = witness.poses_for_model(model_id)
        if path[0] != before_poses[model_id]:
            raise GameLifecycleError("Grouped Fight movement witness start pose drifted.")
        if path[-1] != attempted_poses[model_id]:
            raise GameLifecycleError("Grouped Fight movement witness endpoint pose drifted.")


def _validate_grouped_fight_movement_coherency(
    *,
    unit_instance_id: str,
    proposal_kind: ProposalKind,
    before: FightRulesUnitPlacement,
    attempted: FightRulesUnitPlacement,
    moved_model_ids: tuple[str, ...],
    coherency_result: UnitCoherencyResult | None,
    rollback_record: RulesUnitMovementRollbackRecord | None,
) -> None:
    if not moved_model_ids:
        if coherency_result is not None:
            raise GameLifecycleError(
                "Grouped Fight no-move resolution must not include coherency evidence."
            )
        if rollback_record is not None:
            raise GameLifecycleError(
                "Grouped Fight no-move resolution must not include a rollback record."
            )
        return
    if coherency_result is None:
        raise GameLifecycleError("Grouped Fight movement requires coherency evidence.")
    if coherency_result.unit_instance_id != unit_instance_id:
        raise GameLifecycleError("Grouped Fight movement coherency identity drifted.")
    if coherency_result.model_instance_ids != _model_ids(attempted):
        raise GameLifecycleError("Grouped Fight movement coherency model identity drifted.")
    if coherency_result.is_coherent:
        if rollback_record is not None:
            raise GameLifecycleError(
                "Coherent grouped Fight movement must not include a rollback record."
            )
        return
    if rollback_record is None:
        raise GameLifecycleError(
            "Broken grouped Fight movement coherency requires a rollback record."
        )
    if (
        rollback_record.unit_instance_id != unit_instance_id
        or rollback_record.displacement_kind is not _displacement_kind(proposal_kind)
        or rollback_record.before_rules_unit_placement != before
        or rollback_record.attempted_rules_unit_placement != attempted
        or rollback_record.coherency_result != coherency_result
    ):
        raise GameLifecycleError("Grouped Fight movement rollback evidence drifted.")


def _identifier_list(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GameLifecycleError(f"{label} must be a list.")
    identifiers = tuple(_validate_identifier(label, item) for item in cast(list[object], value))
    if identifiers != tuple(sorted(set(identifiers))):
        raise GameLifecycleError(f"{label} must be sorted and unique.")
    return identifiers


def rules_unit_views_for_completed_move_event(
    *,
    state: GameState,
    event_type: str,
    unit_instance_id: str,
) -> tuple[RulesUnitView, ...]:
    """Resolve strict grouped Fight identities and legacy physical move aliases."""
    if event_type == "fight_movement_completed":
        return current_rules_unit_views_for_canonical_identity(
            state=state,
            unit_instance_id=unit_instance_id,
        )
    return current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=unit_instance_id,
    )


def _model_ids(placement: FightRulesUnitPlacement) -> tuple[str, ...]:
    return tuple(sorted(model.model_instance_id for model in placement.model_placements))


def _fight_proposal_kind(value: ProposalKind) -> ProposalKind:
    kind = proposal_kind_from_token(value)
    if kind not in {ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE}:
        raise GameLifecycleError("Rules-unit Fight movement proposal kind is unsupported.")
    return kind


def _proposal_kind_for_movement_mode(value: object) -> ProposalKind:
    mode = movement_mode_from_token(value)
    if mode is MovementMode.PILE_IN:
        return ProposalKind.PILE_IN
    if mode is MovementMode.CONSOLIDATE:
        return ProposalKind.CONSOLIDATE
    raise GameLifecycleError("Rules-unit Fight movement payload mode is unsupported.")


def _movement_mode_for_proposal_kind(proposal_kind: ProposalKind) -> MovementMode:
    if proposal_kind is ProposalKind.PILE_IN:
        return MovementMode.PILE_IN
    if proposal_kind is ProposalKind.CONSOLIDATE:
        return MovementMode.CONSOLIDATE
    raise GameLifecycleError("Rules-unit Fight movement proposal kind is unsupported.")


def _displacement_kind(proposal_kind: ProposalKind) -> ModelDisplacementKind:
    if proposal_kind is ProposalKind.PILE_IN:
        return ModelDisplacementKind.PILE_IN
    if proposal_kind is ProposalKind.CONSOLIDATE:
        return ModelDisplacementKind.CONSOLIDATE
    raise GameLifecycleError("Fight movement displacement kind is unsupported.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
