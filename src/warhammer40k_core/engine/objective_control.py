from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.objectives import (
    DEFAULT_OBJECTIVE_CONTROL_VERTICAL_INCHES,
    Objective,
    ObjectiveAnchorKind,
    ObjectiveMarker,
    TerrainObjectiveAnchor,
)
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
    TerrainObjectiveControlPolicy,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.spatial_index import SpatialIndex
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class ObjectiveControlTiming(StrEnum):
    PHASE_END = "phase_end"
    TURN_END = "turn_end"


class ObjectiveControlStatus(StrEnum):
    CONTROLLED = "controlled"
    CONTESTED = "contested"
    UNCONTROLLED = "uncontrolled"
    UNSUPPORTED = "unsupported"


class ObjectiveControlScorePayload(TypedDict):
    player_id: str
    score: int


class ObjectiveControlContributionPayload(TypedDict):
    player_id: str
    unit_instance_id: str
    model_instance_id: str
    objective_control: int
    effective_objective_control: int
    battle_shocked: bool
    horizontal_distance_inches: float
    vertical_gap_inches: float


class ObjectiveControlResultPayload(TypedDict):
    objective_id: str
    status: str
    controlled_by_player_id: str | None
    scores: list[ObjectiveControlScorePayload]
    contributors: list[ObjectiveControlContributionPayload]
    unsupported_reason: str | None
    retained_control_source_id: str | None


class ObjectiveMarkerEndpointViolationPayload(TypedDict):
    objective_marker_id: str
    model_instance_id: str
    unit_instance_id: str
    player_id: str
    violation_code: str


class ObjectiveControlRecordPayload(TypedDict):
    record_id: str
    game_id: str
    battle_round: int
    active_player_id: str
    timing: str
    phase: str
    battlefield_id: str
    results: list[ObjectiveControlResultPayload]


@dataclass(frozen=True, slots=True)
class ObjectiveControlScore:
    player_id: str
    score: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(self, "score", _validate_non_negative_int("score", self.score))

    def to_payload(self) -> ObjectiveControlScorePayload:
        return {
            "player_id": self.player_id,
            "score": self.score,
        }

    @classmethod
    def from_payload(cls, payload: ObjectiveControlScorePayload) -> Self:
        return cls(player_id=payload["player_id"], score=payload["score"])


@dataclass(frozen=True, slots=True)
class ObjectiveControlContribution:
    player_id: str
    unit_instance_id: str
    model_instance_id: str
    objective_control: int
    effective_objective_control: int
    battle_shocked: bool
    horizontal_distance_inches: float
    vertical_gap_inches: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier("model_instance_id", self.model_instance_id),
        )
        object.__setattr__(
            self,
            "objective_control",
            _validate_non_negative_int("objective_control", self.objective_control),
        )
        object.__setattr__(
            self,
            "effective_objective_control",
            _validate_non_negative_int(
                "effective_objective_control",
                self.effective_objective_control,
            ),
        )
        if type(self.battle_shocked) is not bool:
            raise GameLifecycleError("ObjectiveControlContribution battle_shocked must be a bool.")
        object.__setattr__(
            self,
            "horizontal_distance_inches",
            _validate_non_negative_float(
                "horizontal_distance_inches",
                self.horizontal_distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "vertical_gap_inches",
            _validate_non_negative_float("vertical_gap_inches", self.vertical_gap_inches),
        )

    def to_payload(self) -> ObjectiveControlContributionPayload:
        return {
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "model_instance_id": self.model_instance_id,
            "objective_control": self.objective_control,
            "effective_objective_control": self.effective_objective_control,
            "battle_shocked": self.battle_shocked,
            "horizontal_distance_inches": self.horizontal_distance_inches,
            "vertical_gap_inches": self.vertical_gap_inches,
        }

    @classmethod
    def from_payload(cls, payload: ObjectiveControlContributionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            model_instance_id=payload["model_instance_id"],
            objective_control=payload["objective_control"],
            effective_objective_control=payload["effective_objective_control"],
            battle_shocked=payload["battle_shocked"],
            horizontal_distance_inches=payload["horizontal_distance_inches"],
            vertical_gap_inches=payload["vertical_gap_inches"],
        )


@dataclass(frozen=True, slots=True)
class ObjectiveControlResult:
    objective_id: str
    status: ObjectiveControlStatus
    controlled_by_player_id: str | None
    scores: tuple[ObjectiveControlScore, ...]
    contributors: tuple[ObjectiveControlContribution, ...] = ()
    unsupported_reason: str | None = None
    retained_control_source_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "objective_id",
            _validate_identifier("ObjectiveControlResult objective_id", self.objective_id),
        )
        object.__setattr__(self, "status", objective_control_status_from_token(self.status))
        object.__setattr__(
            self,
            "controlled_by_player_id",
            _validate_optional_identifier(
                "ObjectiveControlResult controlled_by_player_id",
                self.controlled_by_player_id,
            ),
        )
        object.__setattr__(
            self,
            "scores",
            _validate_score_tuple("ObjectiveControlResult scores", self.scores),
        )
        object.__setattr__(
            self,
            "contributors",
            _validate_contribution_tuple(
                "ObjectiveControlResult contributors",
                self.contributors,
            ),
        )
        object.__setattr__(
            self,
            "unsupported_reason",
            _validate_optional_identifier(
                "ObjectiveControlResult unsupported_reason",
                self.unsupported_reason,
            ),
        )
        object.__setattr__(
            self,
            "retained_control_source_id",
            _validate_optional_identifier(
                "ObjectiveControlResult retained_control_source_id",
                self.retained_control_source_id,
            ),
        )
        _validate_result_status(self)

    @classmethod
    def from_contributors(
        cls,
        *,
        objective_id: str,
        contributors: tuple[ObjectiveControlContribution, ...],
    ) -> Self:
        contribution_tuple = _validate_contribution_tuple("contributors", contributors)
        scores_by_player: dict[str, int] = {}
        for contribution in contribution_tuple:
            if contribution.effective_objective_control == 0:
                continue
            scores_by_player[contribution.player_id] = (
                scores_by_player.get(contribution.player_id, 0)
                + contribution.effective_objective_control
            )
        scores = tuple(
            ObjectiveControlScore(player_id=player_id, score=score)
            for player_id, score in sorted(scores_by_player.items(), key=lambda item: item[0])
        )
        if not scores:
            return cls(
                objective_id=objective_id,
                status=ObjectiveControlStatus.UNCONTROLLED,
                controlled_by_player_id=None,
                scores=(),
                contributors=contribution_tuple,
            )
        highest_score = max(score.score for score in scores)
        controlling_players = tuple(
            score.player_id for score in scores if score.score == highest_score
        )
        if len(controlling_players) != 1:
            return cls(
                objective_id=objective_id,
                status=ObjectiveControlStatus.CONTESTED,
                controlled_by_player_id=None,
                scores=scores,
                contributors=contribution_tuple,
            )
        return cls(
            objective_id=objective_id,
            status=ObjectiveControlStatus.CONTROLLED,
            controlled_by_player_id=controlling_players[0],
            scores=scores,
            contributors=contribution_tuple,
        )

    @classmethod
    def unsupported(cls, *, objective_id: str, unsupported_reason: str) -> Self:
        return cls(
            objective_id=objective_id,
            status=ObjectiveControlStatus.UNSUPPORTED,
            controlled_by_player_id=None,
            scores=(),
            contributors=(),
            unsupported_reason=unsupported_reason,
        )

    def to_payload(self) -> ObjectiveControlResultPayload:
        return {
            "objective_id": self.objective_id,
            "status": self.status.value,
            "controlled_by_player_id": self.controlled_by_player_id,
            "scores": [score.to_payload() for score in self.scores],
            "contributors": [contribution.to_payload() for contribution in self.contributors],
            "unsupported_reason": self.unsupported_reason,
            "retained_control_source_id": self.retained_control_source_id,
        }

    @classmethod
    def from_payload(cls, payload: ObjectiveControlResultPayload) -> Self:
        return cls(
            objective_id=payload["objective_id"],
            status=objective_control_status_from_token(payload["status"]),
            controlled_by_player_id=payload["controlled_by_player_id"],
            scores=tuple(ObjectiveControlScore.from_payload(score) for score in payload["scores"]),
            contributors=tuple(
                ObjectiveControlContribution.from_payload(contribution)
                for contribution in payload["contributors"]
            ),
            unsupported_reason=payload["unsupported_reason"],
            retained_control_source_id=payload["retained_control_source_id"],
        )


@dataclass(frozen=True, slots=True)
class ObjectiveMarkerEndpointViolation:
    objective_marker_id: str
    model_instance_id: str
    unit_instance_id: str
    player_id: str
    violation_code: str = "objective_marker_endpoint_overlap"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "objective_marker_id",
            _validate_identifier("objective_marker_id", self.objective_marker_id),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier("model_instance_id", self.model_instance_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "violation_code",
            _validate_identifier("violation_code", self.violation_code),
        )

    def to_payload(self) -> ObjectiveMarkerEndpointViolationPayload:
        return {
            "objective_marker_id": self.objective_marker_id,
            "model_instance_id": self.model_instance_id,
            "unit_instance_id": self.unit_instance_id,
            "player_id": self.player_id,
            "violation_code": self.violation_code,
        }

    @classmethod
    def from_payload(cls, payload: ObjectiveMarkerEndpointViolationPayload) -> Self:
        return cls(
            objective_marker_id=payload["objective_marker_id"],
            model_instance_id=payload["model_instance_id"],
            unit_instance_id=payload["unit_instance_id"],
            player_id=payload["player_id"],
            violation_code=payload["violation_code"],
        )


@dataclass(frozen=True, slots=True)
class ObjectiveControlContext:
    game_id: str
    scenario: BattlefieldScenario
    objective_markers: tuple[ObjectiveMarker, ...]
    battle_shocked_unit_ids: tuple[str, ...]
    timing: ObjectiveControlTiming
    phase: str
    battle_round: int
    active_player_id: str
    ruleset_descriptor: RulesetDescriptor | None = None
    terrain_objectives: tuple[Objective, ...] = ()
    terrain_features: tuple[TerrainFeatureDefinition, ...] = ()
    state: GameState | None = None
    runtime_modifier_registry: RuntimeModifierRegistry = field(
        default_factory=RuntimeModifierRegistry.empty
    )

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        object.__setattr__(self, "game_id", _validate_identifier("game_id", self.game_id))
        if type(self.scenario) is not BattlefieldScenario:
            raise GameLifecycleError(
                "ObjectiveControlContext scenario must be a BattlefieldScenario."
            )
        if self.ruleset_descriptor is not None and type(self.ruleset_descriptor) is not (
            RulesetDescriptor
        ):
            raise GameLifecycleError(
                "ObjectiveControlContext ruleset_descriptor must be a RulesetDescriptor."
            )
        object.__setattr__(
            self,
            "objective_markers",
            _validate_objective_marker_tuple(
                "ObjectiveControlContext objective_markers",
                self.objective_markers,
            ),
        )
        object.__setattr__(
            self,
            "battle_shocked_unit_ids",
            _validate_identifier_tuple(
                "ObjectiveControlContext battle_shocked_unit_ids",
                self.battle_shocked_unit_ids,
            ),
        )
        object.__setattr__(self, "timing", objective_control_timing_from_token(self.timing))
        object.__setattr__(self, "phase", _validate_identifier("phase", self.phase))
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(
            self,
            "terrain_objectives",
            _validate_objective_tuple(
                "ObjectiveControlContext terrain_objectives",
                self.terrain_objectives,
            ),
        )
        object.__setattr__(
            self,
            "terrain_features",
            _validate_terrain_feature_tuple(
                "ObjectiveControlContext terrain_features",
                self.terrain_features,
            ),
        )
        if self.terrain_objectives and self.ruleset_descriptor is None:
            raise GameLifecycleError("Terrain objective control requires a RulesetDescriptor.")
        if self.state is not None and type(self.state) is not GameState:
            raise GameLifecycleError("ObjectiveControlContext state must be GameState.")
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError(
                "ObjectiveControlContext runtime_modifier_registry must be a registry."
            )

    @classmethod
    def from_game_state(
        cls,
        state: object,
        *,
        timing: ObjectiveControlTiming,
        phase: BattlePhase | str,
        ruleset_descriptor: RulesetDescriptor | None = None,
        terrain_objectives: tuple[Objective, ...] = (),
        runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    ) -> Self:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("ObjectiveControlContext requires a GameState.")
        if state.battlefield_state is None:
            raise GameLifecycleError("Objective control requires battlefield_state.")
        if state.mission_setup is None:
            raise GameLifecycleError("Objective control requires MissionSetup objective markers.")
        if state.active_player_id is None:
            raise GameLifecycleError("Objective control requires an active player.")
        objective_markers = tuple(
            marker.to_objective_marker() for marker in state.mission_setup.objective_markers
        )
        terrain_features = state.battlefield_state.terrain_features
        objective_markers, resolved_terrain_objectives = _objective_control_sources_for_ruleset(
            objective_markers=objective_markers,
            terrain_features=terrain_features,
            ruleset_descriptor=ruleset_descriptor,
            explicit_terrain_objectives=terrain_objectives,
        )
        return cls(
            game_id=state.game_id,
            scenario=BattlefieldScenario(
                armies=tuple(state.army_definitions),
                battlefield_state=state.battlefield_state,
            ),
            objective_markers=objective_markers,
            battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
            timing=timing,
            phase=_battle_phase_value(phase),
            battle_round=state.battle_round,
            active_player_id=state.active_player_id,
            ruleset_descriptor=ruleset_descriptor,
            terrain_objectives=resolved_terrain_objectives,
            terrain_features=terrain_features,
            state=state,
            runtime_modifier_registry=(
                RuntimeModifierRegistry.empty()
                if runtime_modifier_registry is None
                else runtime_modifier_registry
            ),
        )


@dataclass(frozen=True, slots=True)
class ObjectiveControlRecord:
    record_id: str
    game_id: str
    battle_round: int
    active_player_id: str
    timing: ObjectiveControlTiming
    phase: str
    battlefield_id: str
    results: tuple[ObjectiveControlResult, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", _validate_identifier("record_id", self.record_id))
        object.__setattr__(self, "game_id", _validate_identifier("game_id", self.game_id))
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "timing", objective_control_timing_from_token(self.timing))
        object.__setattr__(self, "phase", _validate_identifier("phase", self.phase))
        object.__setattr__(
            self,
            "battlefield_id",
            _validate_identifier("battlefield_id", self.battlefield_id),
        )
        object.__setattr__(
            self,
            "results",
            _validate_result_tuple("ObjectiveControlRecord results", self.results),
        )

    def result_by_objective_id(self, objective_id: str) -> ObjectiveControlResult:
        requested_id = _validate_identifier("objective_id", objective_id)
        for result in self.results:
            if result.objective_id == requested_id:
                return result
        raise GameLifecycleError("ObjectiveControlRecord objective_id was not found.")

    def to_payload(self) -> ObjectiveControlRecordPayload:
        return {
            "record_id": self.record_id,
            "game_id": self.game_id,
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "timing": self.timing.value,
            "phase": self.phase,
            "battlefield_id": self.battlefield_id,
            "results": [result.to_payload() for result in self.results],
        }

    @classmethod
    def from_payload(cls, payload: ObjectiveControlRecordPayload) -> Self:
        return cls(
            record_id=payload["record_id"],
            game_id=payload["game_id"],
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            timing=objective_control_timing_from_token(payload["timing"]),
            phase=payload["phase"],
            battlefield_id=payload["battlefield_id"],
            results=tuple(
                ObjectiveControlResult.from_payload(result) for result in payload["results"]
            ),
        )


def resolve_objective_control(context: ObjectiveControlContext) -> ObjectiveControlRecord:
    if type(context) is not ObjectiveControlContext:
        raise GameLifecycleError("resolve_objective_control requires an ObjectiveControlContext.")
    scenario = context.scenario
    spatial_index = scenario.spatial_index()
    placement_by_model_id = _model_placement_by_id(scenario)
    model_instance_by_id = _model_instance_by_id(scenario)
    results: list[ObjectiveControlResult] = []
    for marker in context.objective_markers:
        contributors = tuple(
            _objective_control_contribution(
                marker=marker,
                geometry_model=geometry_model,
                placement=placement_by_model_id[geometry_model.model_id],
                model_instance=model_instance_by_id[geometry_model.model_id],
                battle_shocked_unit_ids=context.battle_shocked_unit_ids,
                state=context.state,
                runtime_modifier_registry=context.runtime_modifier_registry,
            )
            for geometry_model in spatial_index.models_controlling_objective_marker(marker)
            if model_instance_by_id[geometry_model.model_id].is_alive
        )
        results.append(
            ObjectiveControlResult.from_contributors(
                objective_id=marker.objective_marker_id,
                contributors=contributors,
            )
        )
    for objective in context.terrain_objectives:
        results.append(_terrain_objective_result(context=context, objective=objective))
    return ObjectiveControlRecord(
        record_id=_record_id_for_context(context),
        game_id=context.game_id,
        battle_round=context.battle_round,
        active_player_id=context.active_player_id,
        timing=context.timing,
        phase=context.phase,
        battlefield_id=scenario.battlefield_state.battlefield_id,
        results=tuple(sorted(results, key=lambda result: result.objective_id)),
    )


def objective_marker_endpoint_violations(
    *,
    scenario: BattlefieldScenario,
    objective_markers: tuple[ObjectiveMarker, ...],
    unit_placement: UnitPlacement | None = None,
) -> tuple[ObjectiveMarkerEndpointViolation, ...]:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("objective marker endpoint validation requires a scenario.")
    markers = _validate_objective_marker_tuple("objective_markers", objective_markers)
    if unit_placement is not None and type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("unit_placement must be a UnitPlacement when supplied.")
    placement_by_model_id = _model_placement_by_id_for_endpoint_query(
        scenario=scenario,
        unit_placement=unit_placement,
    )
    spatial_index = _spatial_index_for_endpoint_query(
        scenario=scenario,
        unit_placement=unit_placement,
    )
    violations: list[ObjectiveMarkerEndpointViolation] = []
    for marker in markers:
        if not marker.blocks_placement:
            continue
        for geometry_model in spatial_index.models_overlapping_objective_marker_endpoint(marker):
            placement = placement_by_model_id[geometry_model.model_id]
            violations.append(
                ObjectiveMarkerEndpointViolation(
                    objective_marker_id=marker.objective_marker_id,
                    model_instance_id=placement.model_instance_id,
                    unit_instance_id=placement.unit_instance_id,
                    player_id=placement.player_id,
                )
            )
    return tuple(
        sorted(
            violations,
            key=lambda violation: (violation.objective_marker_id, violation.model_instance_id),
        )
    )


def objective_control_timing_from_token(token: object) -> ObjectiveControlTiming:
    if type(token) is ObjectiveControlTiming:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ObjectiveControlTiming token must be a string.")
    try:
        return ObjectiveControlTiming(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported ObjectiveControlTiming token: {token}.") from exc


def objective_control_status_from_token(token: object) -> ObjectiveControlStatus:
    if type(token) is ObjectiveControlStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ObjectiveControlStatus token must be a string.")
    try:
        return ObjectiveControlStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported ObjectiveControlStatus token: {token}.") from exc


def _battle_phase_value(phase: BattlePhase | str) -> str:
    if type(phase) is BattlePhase:
        return phase.value
    if type(phase) is not str:
        raise GameLifecycleError("phase must be a BattlePhase token.")
    try:
        return BattlePhase(phase).value
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported battle phase token: {phase}.") from exc


def _objective_control_contribution(
    *,
    marker: ObjectiveMarker,
    geometry_model: GeometryModel,
    placement: ModelPlacement,
    model_instance: ModelInstance,
    battle_shocked_unit_ids: tuple[str, ...],
    state: GameState | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> ObjectiveControlContribution:
    context = DistanceMeasurementContext.from_objective_marker_to_model(
        marker_id=marker.objective_marker_id,
        marker_pose=Pose.at(marker.x_inches, marker.y_inches, marker.z_inches),
        model=geometry_model,
        marker_diameter_inches=marker.marker_diameter_inches,
    )
    battle_shocked = placement.unit_instance_id in battle_shocked_unit_ids
    objective_control_characteristic = model_objective_control_characteristic(
        model_instance,
        battle_shocked=False,
        state=state,
        unit_instance_id=placement.unit_instance_id,
        runtime_modifier_registry=runtime_modifier_registry,
        model_instance_id=placement.model_instance_id,
    )
    effective_objective_control_characteristic = model_objective_control_characteristic(
        model_instance,
        battle_shocked=battle_shocked,
        state=state,
        unit_instance_id=placement.unit_instance_id,
        runtime_modifier_registry=runtime_modifier_registry,
        model_instance_id=placement.model_instance_id,
    )
    return ObjectiveControlContribution(
        player_id=placement.player_id,
        unit_instance_id=placement.unit_instance_id,
        model_instance_id=placement.model_instance_id,
        objective_control=objective_control_characteristic.final,
        effective_objective_control=effective_objective_control_characteristic.final,
        battle_shocked=battle_shocked,
        horizontal_distance_inches=context.horizontal_distance_inches(),
        vertical_gap_inches=context.vertical_gap_inches(),
    )


def _terrain_objective_result(
    *,
    context: ObjectiveControlContext,
    objective: Objective,
) -> ObjectiveControlResult:
    if type(objective) is not Objective:
        raise GameLifecycleError("terrain_objectives must contain Objective values.")
    if objective.anchor.kind is not ObjectiveAnchorKind.TERRAIN:
        raise GameLifecycleError("terrain_objectives must contain terrain-anchored objectives.")
    if context.ruleset_descriptor is None:
        raise GameLifecycleError("Terrain objective control requires a RulesetDescriptor.")
    policy = context.ruleset_descriptor.objective_policy.terrain_objective_control_policy
    if policy is TerrainObjectiveControlPolicy.UNSUPPORTED:
        return ObjectiveControlResult.unsupported(
            objective_id=objective.objective_id,
            unsupported_reason="terrain_objective_control_policy_unsupported",
        )
    if policy is not TerrainObjectiveControlPolicy.TERRAIN_AREA_OCCUPANCY:
        raise GameLifecycleError("Unsupported terrain objective control policy.")
    if type(objective.anchor) is not TerrainObjectiveAnchor:
        raise GameLifecycleError("terrain_objectives must contain terrain-anchored objectives.")
    feature = _terrain_feature_by_id(
        context.terrain_features,
        terrain_id=objective.anchor.terrain_id,
    )
    scenario = context.scenario
    placement_by_model_id = _model_placement_by_id(scenario)
    model_instance_by_id = _model_instance_by_id(scenario)
    contributors = tuple(
        contribution
        for geometry_model in scenario.placed_geometry_models()
        if model_instance_by_id[geometry_model.model_id].is_alive
        for contribution in (
            _terrain_objective_contribution(
                objective=objective,
                feature=feature,
                geometry_model=geometry_model,
                placement=placement_by_model_id[geometry_model.model_id],
                model_instance=model_instance_by_id[geometry_model.model_id],
                battle_shocked_unit_ids=context.battle_shocked_unit_ids,
                state=context.state,
                runtime_modifier_registry=context.runtime_modifier_registry,
            ),
        )
        if contribution is not None
    )
    return ObjectiveControlResult.from_contributors(
        objective_id=objective.objective_id,
        contributors=contributors,
    )


def _terrain_objective_contribution(
    *,
    objective: Objective,
    feature: TerrainFeatureDefinition,
    geometry_model: GeometryModel,
    placement: ModelPlacement,
    model_instance: ModelInstance,
    battle_shocked_unit_ids: tuple[str, ...],
    state: GameState | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> ObjectiveControlContribution | None:
    horizontal_distance = shapely_backend.base_footprint_distance_to_bounds(
        geometry_model.base,
        geometry_model.pose,
        feature.bounds(),
    )
    vertical_gap = _vertical_gap_to_terrain_area(geometry_model)
    if horizontal_distance > 0.0:
        return None
    if vertical_gap > DEFAULT_OBJECTIVE_CONTROL_VERTICAL_INCHES:
        return None
    battle_shocked = placement.unit_instance_id in battle_shocked_unit_ids
    objective_control_characteristic = model_objective_control_characteristic(
        model_instance,
        battle_shocked=False,
        state=state,
        unit_instance_id=placement.unit_instance_id,
        runtime_modifier_registry=runtime_modifier_registry,
        model_instance_id=placement.model_instance_id,
    )
    effective_objective_control_characteristic = model_objective_control_characteristic(
        model_instance,
        battle_shocked=battle_shocked,
        state=state,
        unit_instance_id=placement.unit_instance_id,
        runtime_modifier_registry=runtime_modifier_registry,
        model_instance_id=placement.model_instance_id,
    )
    return ObjectiveControlContribution(
        player_id=placement.player_id,
        unit_instance_id=placement.unit_instance_id,
        model_instance_id=placement.model_instance_id,
        objective_control=objective_control_characteristic.final,
        effective_objective_control=effective_objective_control_characteristic.final,
        battle_shocked=battle_shocked,
        horizontal_distance_inches=horizontal_distance,
        vertical_gap_inches=vertical_gap,
    )


def _vertical_gap_to_terrain_area(model: GeometryModel) -> float:
    bottom, top = model.volume.vertical_interval(model.pose)
    if top < 0.0:
        return abs(top)
    if bottom > 0.0:
        return bottom
    return 0.0


def _terrain_feature_by_id(
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    *,
    terrain_id: str,
) -> TerrainFeatureDefinition:
    requested_id = _validate_identifier("terrain_id", terrain_id)
    for feature in terrain_features:
        if feature.feature_id == requested_id:
            return feature
    raise GameLifecycleError("Terrain objective references an unknown terrain feature.")


def _objective_control_sources_for_ruleset(
    *,
    objective_markers: tuple[ObjectiveMarker, ...],
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    ruleset_descriptor: RulesetDescriptor | None,
    explicit_terrain_objectives: tuple[Objective, ...],
) -> tuple[tuple[ObjectiveMarker, ...], tuple[Objective, ...]]:
    markers = _validate_objective_marker_tuple("objective_markers", objective_markers)
    features = _validate_terrain_feature_tuple("terrain_features", terrain_features)
    terrain_objectives = _validate_objective_tuple(
        "terrain_objectives",
        explicit_terrain_objectives,
    )
    if terrain_objectives or ruleset_descriptor is None:
        return markers, terrain_objectives
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("ruleset_descriptor must be a RulesetDescriptor.")
    if not ruleset_descriptor.mission_policy.terrain_objective_missions_supported:
        return markers, terrain_objectives
    if (
        ObjectiveAnchorKind.TERRAIN
        not in ruleset_descriptor.objective_policy.supported_anchor_kinds
    ):
        return markers, terrain_objectives
    if (
        ruleset_descriptor.objective_policy.terrain_objective_control_policy
        is TerrainObjectiveControlPolicy.UNSUPPORTED
    ):
        return markers, terrain_objectives
    fallback_markers: list[ObjectiveMarker] = []
    derived_objectives: list[Objective] = []
    for marker in markers:
        matching_features = tuple(
            feature for feature in features if _terrain_feature_contains_marker(feature, marker)
        )
        if len(matching_features) > 1:
            raise GameLifecycleError("Objective marker coincides with multiple terrain areas.")
        if not matching_features:
            fallback_markers.append(marker)
            continue
        derived_objectives.append(
            Objective.terrain(
                objective_id=marker.objective_marker_id,
                name=marker.name,
                terrain_id=matching_features[0].feature_id,
            )
        )
    return tuple(fallback_markers), tuple(
        sorted(derived_objectives, key=lambda objective: objective.objective_id)
    )


def _terrain_feature_contains_marker(
    feature: TerrainFeatureDefinition,
    marker: ObjectiveMarker,
) -> bool:
    min_x, min_y, max_x, max_y = feature.bounds()
    return min_x <= marker.x_inches <= max_x and min_y <= marker.y_inches <= max_y


def _record_id_for_context(context: ObjectiveControlContext) -> str:
    return (
        "objective-control:"
        f"round-{context.battle_round:02d}:"
        f"{context.active_player_id}:"
        f"{context.phase}:"
        f"{context.timing.value}"
    )


def _model_placement_by_id(scenario: BattlefieldScenario) -> dict[str, ModelPlacement]:
    placements: dict[str, ModelPlacement] = {}
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            for placement in unit_placement.model_placements:
                placements[placement.model_instance_id] = placement
    return placements


def _model_instance_by_id(scenario: BattlefieldScenario) -> dict[str, ModelInstance]:
    return {
        model.model_instance_id: model
        for army in scenario.armies
        for unit in army.units
        for model in unit.own_models
    }


def _model_placement_by_id_for_endpoint_query(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement | None,
) -> dict[str, ModelPlacement]:
    if unit_placement is None:
        return _model_placement_by_id(scenario)
    return {placement.model_instance_id: placement for placement in unit_placement.model_placements}


def _spatial_index_for_endpoint_query(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement | None,
) -> SpatialIndex:
    if unit_placement is None:
        return scenario.spatial_index()
    models = tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for placement in unit_placement.model_placements
    )
    return SpatialIndex(models=models)


def model_objective_control_characteristic(
    model: ModelInstance,
    *,
    battle_shocked: bool,
    state: GameState | None = None,
    unit_instance_id: str | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    model_instance_id: str | None = None,
) -> CharacteristicValue:
    if type(model) is not ModelInstance:
        raise GameLifecycleError("Objective control requires a ModelInstance.")
    if type(battle_shocked) is not bool:
        raise GameLifecycleError("battle_shocked must be a bool.")
    if battle_shocked:
        return CharacteristicValue.replacement_dash(
            Characteristic.OBJECTIVE_CONTROL,
            applied_modifier_ids=("battle_shock",),
        )
    for characteristic in model.characteristics:
        if characteristic.characteristic is Characteristic.OBJECTIVE_CONTROL:
            if state is None:
                return characteristic
            if unit_instance_id is None:
                raise GameLifecycleError("Objective control modifier requires unit_instance_id.")
            resolved_model_id = (
                model.model_instance_id if model_instance_id is None else model_instance_id
            )
            runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
            modified = runtime_modifiers.modified_objective_control(
                ObjectiveControlModifierContext(
                    state=state,
                    unit_instance_id=unit_instance_id,
                    model_instance_id=resolved_model_id,
                    base_objective_control=characteristic.final,
                    current_objective_control=characteristic.final,
                )
            )
            if modified == characteristic.final:
                return characteristic
            return CharacteristicValue(
                characteristic=Characteristic.OBJECTIVE_CONTROL,
                raw=characteristic.raw,
                base=characteristic.base,
                final=modified,
                applied_modifier_ids=characteristic.applied_modifier_ids,
                value_kind=characteristic.value_kind,
            )
    raise GameLifecycleError("ModelInstance is missing Objective Control.")


def _runtime_modifier_registry(
    registry: RuntimeModifierRegistry | None,
) -> RuntimeModifierRegistry:
    if registry is None:
        return RuntimeModifierRegistry.empty()
    if type(registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Objective control runtime modifier registry is invalid.")
    return registry


def _validate_result_status(result: ObjectiveControlResult) -> None:
    if result.status is ObjectiveControlStatus.UNSUPPORTED:
        if result.controlled_by_player_id is not None or result.scores or result.contributors:
            raise GameLifecycleError("Unsupported objective control results must be empty.")
        if result.unsupported_reason is None:
            raise GameLifecycleError("Unsupported objective control requires a reason.")
        if result.retained_control_source_id is not None:
            raise GameLifecycleError("Unsupported objective control cannot retain control.")
        return
    if result.unsupported_reason is not None:
        raise GameLifecycleError("Supported objective control results must not include a reason.")
    if result.status is ObjectiveControlStatus.UNCONTROLLED:
        if result.controlled_by_player_id is not None or result.scores:
            raise GameLifecycleError("Uncontrolled objective results must not have scores.")
        if result.retained_control_source_id is not None:
            raise GameLifecycleError("Uncontrolled objective results cannot retain control.")
        return
    if result.status is ObjectiveControlStatus.CONTESTED:
        if result.controlled_by_player_id is not None:
            raise GameLifecycleError("Contested objective results cannot have a controller.")
        if result.retained_control_source_id is not None:
            raise GameLifecycleError("Contested objective results cannot retain control.")
        if len(result.scores) < 2:
            raise GameLifecycleError("Contested objective results require at least two scores.")
        highest_score = max(score.score for score in result.scores)
        if sum(1 for score in result.scores if score.score == highest_score) < 2:
            raise GameLifecycleError("Contested objective results require a high-score tie.")
        return
    if result.status is ObjectiveControlStatus.CONTROLLED:
        if result.controlled_by_player_id is None:
            raise GameLifecycleError("Controlled objective results require a controller.")
        if result.controlled_by_player_id not in {score.player_id for score in result.scores}:
            raise GameLifecycleError("Controlled objective controller must have a score.")
        highest_score = max(score.score for score in result.scores)
        controller_score = tuple(
            score.score
            for score in result.scores
            if score.player_id == result.controlled_by_player_id
        )
        if controller_score != (highest_score,):
            raise GameLifecycleError("Controlled objective controller score must be highest.")
        if result.retained_control_source_id is not None:
            return
        if sum(1 for score in result.scores if score.score == highest_score) != 1:
            raise GameLifecycleError("Controlled objective requires a unique highest score.")
        return
    raise GameLifecycleError("Unsupported objective control status.")


def _validate_score_tuple(
    field_name: str,
    values: object,
) -> tuple[ObjectiveControlScore, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    scores: list[ObjectiveControlScore] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ObjectiveControlScore:
            raise GameLifecycleError(f"{field_name} must contain ObjectiveControlScore values.")
        if value.player_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate players.")
        seen.add(value.player_id)
        scores.append(value)
    return tuple(sorted(scores, key=lambda score: score.player_id))


def _validate_contribution_tuple(
    field_name: str,
    values: object,
) -> tuple[ObjectiveControlContribution, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    contributions: list[ObjectiveControlContribution] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ObjectiveControlContribution:
            raise GameLifecycleError(
                f"{field_name} must contain ObjectiveControlContribution values."
            )
        if value.model_instance_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate models.")
        seen.add(value.model_instance_id)
        contributions.append(value)
    return tuple(sorted(contributions, key=lambda contribution: contribution.model_instance_id))


def _validate_result_tuple(
    field_name: str,
    values: object,
) -> tuple[ObjectiveControlResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    results: list[ObjectiveControlResult] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ObjectiveControlResult:
            raise GameLifecycleError(f"{field_name} must contain ObjectiveControlResult values.")
        if value.objective_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate objectives.")
        seen.add(value.objective_id)
        results.append(value)
    if not results:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return tuple(sorted(results, key=lambda result: result.objective_id))


def _validate_objective_marker_tuple(
    field_name: str,
    values: object,
) -> tuple[ObjectiveMarker, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    markers: list[ObjectiveMarker] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ObjectiveMarker:
            raise GameLifecycleError(f"{field_name} must contain ObjectiveMarker values.")
        if value.objective_marker_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(value.objective_marker_id)
        markers.append(value)
    return tuple(sorted(markers, key=lambda marker: marker.objective_marker_id))


def _validate_objective_tuple(field_name: str, values: object) -> tuple[Objective, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    objectives: list[Objective] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not Objective:
            raise GameLifecycleError(f"{field_name} must contain Objective values.")
        if value.objective_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate objectives.")
        seen.add(value.objective_id)
        objectives.append(value)
    return tuple(sorted(objectives, key=lambda objective: objective.objective_id))


def _validate_terrain_feature_tuple(
    field_name: str,
    values: object,
) -> tuple[TerrainFeatureDefinition, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    features: list[TerrainFeatureDefinition] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainFeatureDefinition:
            raise GameLifecycleError(f"{field_name} must contain TerrainFeatureDefinition values.")
        if value.feature_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(value.feature_id)
        features.append(value)
    return tuple(sorted(features, key=lambda feature: feature.feature_id))


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
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
    return tuple(sorted(identifiers))


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_float(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise GameLifecycleError(f"{field_name} must be finite.")
    if number < 0.0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return number
