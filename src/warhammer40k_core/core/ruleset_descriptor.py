from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.objectives import ObjectiveAnchorKind
from warhammer40k_core.core.ruleset import RulesetId, RulesetIdPayload


class RulesetDescriptorError(ValueError):
    """Raised when ruleset descriptor data violates CORE V2 invariants."""


class MovementMode(StrEnum):
    NORMAL = "normal"
    ADVANCE = "advance"
    FALL_BACK = "fall_back"
    CHARGE = "charge"
    FLY_TAKE_TO_SKIES = "fly_take_to_skies"


class ChargeTargetSelectionTiming(StrEnum):
    BEFORE_ROLL = "before_roll"
    AFTER_ROLL = "after_roll"


class ChargeEndpointRequirement(StrEnum):
    DECLARED_TARGET_ENGAGEMENT = "declared_target_engagement"
    SELECTED_TARGET_ENGAGEMENT = "selected_target_engagement"
    SELECTED_TARGET_BASE_CONTACT = "selected_target_base_contact"
    ANY_ENEMY_ENGAGEMENT = "any_enemy_engagement"
    UNSUPPORTED = "unsupported"


class TerrainObjectiveControlPolicy(StrEnum):
    UNSUPPORTED = "unsupported"
    TERRAIN_AREA_OCCUPANCY = "terrain_area_occupancy"


class TerrainFeatureKind(StrEnum):
    RUINS = "ruins"
    WOODS = "woods"
    CRATER_AND_RUBBLE = "crater_and_rubble"
    BARRICADE_AND_FUEL_PIPES = "barricade_and_fuel_pipes"
    DEBRIS_AND_STATUARY = "debris_and_statuary"
    BATTLEFIELD_DEBRIS_AND_STATUARY = "battlefield_debris_and_statuary"
    HILLS_AND_SEALED_BUILDINGS = "hills_and_sealed_buildings"
    HILLS = "hills"
    INDUSTRIAL_STRUCTURES = "industrial_structures"
    SEALED_BUILDINGS = "sealed_buildings"
    ARMOURED_CONTAINERS = "armoured_containers"


class TerrainEndpointSupportPolicy(StrEnum):
    NOT_ALLOWED_ON_TOP = "not_allowed_on_top"
    ALLOWED_ON_TOP_WITH_NO_OVERHANG = "allowed_on_top_with_no_overhang"
    ALLOWED_ON_GROUND_FLOOR_ONLY = "allowed_on_ground_floor_only"
    ALLOWED_ON_ANY_FLOOR_WITH_NO_OVERHANG = "allowed_on_any_floor_with_no_overhang"


class TerrainTraversalMode(StrEnum):
    BLOCKED = "blocked"
    FREELY_TRAVERSABLE = "freely_traversable"
    CLIMB = "climb"
    THROUGH_FEATURE = "through_feature"
    AIR_PATH = "air_path"


class CoverEffect(StrEnum):
    SAVE_BONUS = "save_bonus"
    ATTACKER_BS_MODIFIER = "attacker_bs_modifier"
    UNSUPPORTED = "unsupported"


class LineOfSightPolicy(StrEnum):
    TRUE_LINE_OF_SIGHT = "true_line_of_sight"
    AREA_OBSCURING = "area_obscuring"
    DENSE_COVER = "dense_cover"


class MissionDeploymentZoneSource(StrEnum):
    MISSION = "mission"
    RULESET = "ruleset"
    UNSUPPORTED = "unsupported"


class ReserveDestructionTimingKind(StrEnum):
    END_OF_BATTLE = "end_of_battle"
    END_OF_BATTLE_ROUND_N = "end_of_battle_round_n"


class CoherencyPolicyKind(StrEnum):
    NEIGHBOR_COUNT = "neighbor_count"
    ALL_MODELS_WITHIN_DISTANCE = "all_models_within_distance"


class SetupStepKind(StrEnum):
    MUSTER_ARMIES = "muster_armies"
    SELECT_MISSION = "select_mission"
    CREATE_BATTLEFIELD = "create_battlefield"
    DETERMINE_ATTACKER_DEFENDER = "determine_attacker_defender"
    SELECT_SECONDARY_MISSIONS = "select_secondary_missions"
    DECLARE_BATTLE_FORMATIONS = "declare_battle_formations"
    DEPLOY_ARMIES = "deploy_armies"
    REDEPLOY_UNITS = "redeploy_units"
    RESOLVE_PREBATTLE_ACTIONS = "resolve_prebattle_actions"
    DETERMINE_FIRST_TURN = "determine_first_turn"


class BattlePhaseKind(StrEnum):
    COMMAND = "command"
    MOVEMENT = "movement"
    SHOOTING = "shooting"
    CHARGE = "charge"
    FIGHT = "fight"


class EngagementPolicyDescriptorPayload(TypedDict):
    horizontal_inches: float
    vertical_inches: float


class MovementModePolicyPayload(TypedDict):
    movement_mode: str
    may_transit_enemy_engagement: bool
    may_end_in_enemy_engagement: bool
    requires_charge_target: bool
    ignores_vertical_distance: bool
    ignores_models: bool
    ignores_terrain: bool
    movement_distance_modifier: float


class MovementPolicyDescriptorPayload(TypedDict):
    movement_modes: list[MovementModePolicyPayload]


class ChargePolicyDescriptorPayload(TypedDict):
    target_selection_timing: str
    endpoint_requirement: str


class TerrainFeatureMovementPolicyPayload(TypedDict):
    terrain_feature_kind: str
    can_move_over: bool
    can_move_through: bool
    freely_moved_over_height_inches: float | None
    endpoint_support_policy: str
    no_overhang_required: bool
    upper_floor_allowed_keywords: list[str]
    through_terrain_allowed_keywords: list[str]
    ground_floor_only_unless_keyword: bool


class TerrainMovementPolicyPayload(TypedDict):
    freely_traversable_height_threshold_inches: float
    climb_vertical_distance_counts: bool
    may_end_mid_climb: bool
    requires_permission_to_move_through_features: bool
    infantry_beast_ruins_wall_traversal_mode: str
    fly_traversal_mode: str
    fly_uses_air_path_measurement: bool
    feature_policies: list[TerrainFeatureMovementPolicyPayload]


class TerrainVisibilityPolicyDescriptorPayload(TypedDict):
    hidden_supported: bool
    hidden_detection_range_inches: float | None
    hidden_requires_keywords: list[str]
    hidden_requires_terrain_area_occupancy: bool
    hidden_lost_after_shooting: bool
    cover_effect: str
    cover_policy: CoverPolicyDescriptorPayload
    feature_policies: list[TerrainFeatureVisibilityPolicyPayload]


class CoverPolicyDescriptorPayload(TypedDict):
    cover_effect: str
    grants_benefit_of_cover: bool
    non_stacking: bool
    requires_visible_target: bool
    requires_not_fully_visible: bool
    ap_zero_save_bonus_excluded_for_save_3_plus_or_better: bool


class TerrainFeatureVisibilityPolicyPayload(TypedDict):
    terrain_feature_kind: str
    line_of_sight_policy: str
    blocks_model_visibility_through_footprint: bool
    blocks_full_visibility_through_footprint: bool
    uses_true_los_when_observer_wholly_within_feature: bool
    uses_true_los_when_target_intersects_feature: bool
    aircraft_uses_true_los_through_feature: bool
    towering_uses_true_los_through_feature: bool
    towering_uses_true_los_when_wholly_within_feature: bool
    cover_policy: CoverPolicyDescriptorPayload


class ObjectivePolicyDescriptorPayload(TypedDict):
    supported_anchor_kinds: list[str]
    default_point_control_radius_inches: float | None
    terrain_objective_control_policy: str


class CoherencyPolicyDescriptorPayload(TypedDict):
    policy_kind: str
    required_neighbors_small_unit: int | None
    required_neighbors_large_unit: int | None
    large_unit_model_count_threshold: int | None
    max_horizontal_inches: float | None
    max_vertical_inches: float | None
    max_all_models_distance_inches: float | None
    max_unit_span_inches: float | None


class FlyPolicyDescriptorPayload(TypedDict):
    take_to_the_skies_supported: bool
    movement_penalty_inches: float
    ignores_vertical_distance: bool
    may_move_through_models: bool
    may_move_through_terrain: bool


class MissionPolicyDescriptorPayload(TypedDict):
    fixed_objective_missions_supported: bool
    terrain_objective_missions_supported: bool
    deployment_zone_source: str
    reserves_arrival_blocked_battle_rounds: list[int]
    reserves_arrival_excludes_during_battle_strategic_reserves: bool
    reserve_destruction_timing: str
    reserve_destruction_battle_round: int | None
    reserve_destruction_excludes_during_battle_strategic_reserves: bool
    reserve_destruction_only_declare_battle_formations: bool


class SetupSequenceDescriptorPayload(TypedDict):
    steps: list[str]


class BattlePhaseSequenceDescriptorPayload(TypedDict):
    phases: list[str]


class RulesetDescriptorPayload(TypedDict):
    ruleset_id: RulesetIdPayload
    source_date: str
    descriptor_version: str
    descriptor_hash: str
    engagement_policy: EngagementPolicyDescriptorPayload
    movement_policy: MovementPolicyDescriptorPayload
    charge_policy: ChargePolicyDescriptorPayload
    terrain_movement_policy: TerrainMovementPolicyPayload
    terrain_visibility_policy: TerrainVisibilityPolicyDescriptorPayload
    objective_policy: ObjectivePolicyDescriptorPayload
    coherency_policy: CoherencyPolicyDescriptorPayload
    fly_policy: FlyPolicyDescriptorPayload
    mission_policy: MissionPolicyDescriptorPayload
    setup_sequence: SetupSequenceDescriptorPayload
    battle_phase_sequence: BattlePhaseSequenceDescriptorPayload


@dataclass(frozen=True, slots=True)
class SetupSequenceDescriptor:
    steps: tuple[SetupStepKind, ...]

    def __post_init__(self) -> None:
        if type(self.steps) is not tuple:
            raise RulesetDescriptorError("SetupSequenceDescriptor steps must be a tuple.")
        steps = tuple(setup_step_kind_from_token(step) for step in self.steps)
        if not steps:
            raise RulesetDescriptorError("SetupSequenceDescriptor steps must not be empty.")
        _validate_unique_setup_steps(steps)
        object.__setattr__(self, "steps", steps)

    @classmethod
    def warhammer_40000_eleventh_default(cls) -> Self:
        return cls(
            steps=(
                SetupStepKind.MUSTER_ARMIES,
                SetupStepKind.SELECT_MISSION,
                SetupStepKind.CREATE_BATTLEFIELD,
                SetupStepKind.DETERMINE_ATTACKER_DEFENDER,
                SetupStepKind.SELECT_SECONDARY_MISSIONS,
                SetupStepKind.DECLARE_BATTLE_FORMATIONS,
                SetupStepKind.DEPLOY_ARMIES,
                SetupStepKind.REDEPLOY_UNITS,
                SetupStepKind.DETERMINE_FIRST_TURN,
                SetupStepKind.RESOLVE_PREBATTLE_ACTIONS,
            )
        )

    def to_payload(self) -> SetupSequenceDescriptorPayload:
        return {"steps": [step.value for step in self.steps]}

    @classmethod
    def from_payload(cls, payload: SetupSequenceDescriptorPayload) -> Self:
        return cls(steps=tuple(setup_step_kind_from_token(step) for step in payload["steps"]))


@dataclass(frozen=True, slots=True)
class BattlePhaseSequenceDescriptor:
    phases: tuple[BattlePhaseKind, ...]

    def __post_init__(self) -> None:
        if type(self.phases) is not tuple:
            raise RulesetDescriptorError("BattlePhaseSequenceDescriptor phases must be a tuple.")
        phases = tuple(battle_phase_kind_from_token(phase) for phase in self.phases)
        if not phases:
            raise RulesetDescriptorError("BattlePhaseSequenceDescriptor phases must not be empty.")
        _validate_unique_battle_phases(phases)
        object.__setattr__(self, "phases", phases)

    @classmethod
    def warhammer_40000_eleventh_default(cls) -> Self:
        return cls(
            phases=(
                BattlePhaseKind.COMMAND,
                BattlePhaseKind.MOVEMENT,
                BattlePhaseKind.SHOOTING,
                BattlePhaseKind.CHARGE,
                BattlePhaseKind.FIGHT,
            )
        )

    def to_payload(self) -> BattlePhaseSequenceDescriptorPayload:
        return {"phases": [phase.value for phase in self.phases]}

    @classmethod
    def from_payload(cls, payload: BattlePhaseSequenceDescriptorPayload) -> Self:
        return cls(phases=tuple(battle_phase_kind_from_token(phase) for phase in payload["phases"]))


@dataclass(frozen=True, slots=True)
class EngagementPolicyDescriptor:
    horizontal_inches: float
    vertical_inches: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "horizontal_inches",
            _validate_non_negative_number(
                "EngagementPolicyDescriptor horizontal_inches",
                self.horizontal_inches,
            ),
        )
        object.__setattr__(
            self,
            "vertical_inches",
            _validate_non_negative_number(
                "EngagementPolicyDescriptor vertical_inches",
                self.vertical_inches,
            ),
        )

    def to_payload(self) -> EngagementPolicyDescriptorPayload:
        return {
            "horizontal_inches": self.horizontal_inches,
            "vertical_inches": self.vertical_inches,
        }

    def contains_distance(
        self,
        *,
        horizontal_inches: object,
        vertical_inches: object,
    ) -> bool:
        horizontal = _validate_non_negative_number(
            "EngagementPolicyDescriptor horizontal distance",
            horizontal_inches,
        )
        vertical = _validate_non_negative_number(
            "EngagementPolicyDescriptor vertical distance",
            vertical_inches,
        )
        return horizontal <= self.horizontal_inches and vertical <= self.vertical_inches

    @classmethod
    def from_payload(cls, payload: EngagementPolicyDescriptorPayload) -> Self:
        return cls(
            horizontal_inches=payload["horizontal_inches"],
            vertical_inches=payload["vertical_inches"],
        )


@dataclass(frozen=True, slots=True)
class MovementModePolicy:
    movement_mode: MovementMode
    may_transit_enemy_engagement: bool
    may_end_in_enemy_engagement: bool
    requires_charge_target: bool
    ignores_vertical_distance: bool
    ignores_models: bool
    ignores_terrain: bool
    movement_distance_modifier: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "movement_mode", movement_mode_from_token(self.movement_mode))
        _validate_bool(
            "MovementModePolicy may_transit_enemy_engagement",
            self.may_transit_enemy_engagement,
        )
        _validate_bool(
            "MovementModePolicy may_end_in_enemy_engagement",
            self.may_end_in_enemy_engagement,
        )
        _validate_bool("MovementModePolicy requires_charge_target", self.requires_charge_target)
        _validate_bool(
            "MovementModePolicy ignores_vertical_distance",
            self.ignores_vertical_distance,
        )
        _validate_bool("MovementModePolicy ignores_models", self.ignores_models)
        _validate_bool("MovementModePolicy ignores_terrain", self.ignores_terrain)
        object.__setattr__(
            self,
            "movement_distance_modifier",
            _validate_finite_number(
                "MovementModePolicy movement_distance_modifier",
                self.movement_distance_modifier,
            ),
        )

    def to_payload(self) -> MovementModePolicyPayload:
        return {
            "movement_mode": self.movement_mode.value,
            "may_transit_enemy_engagement": self.may_transit_enemy_engagement,
            "may_end_in_enemy_engagement": self.may_end_in_enemy_engagement,
            "requires_charge_target": self.requires_charge_target,
            "ignores_vertical_distance": self.ignores_vertical_distance,
            "ignores_models": self.ignores_models,
            "ignores_terrain": self.ignores_terrain,
            "movement_distance_modifier": self.movement_distance_modifier,
        }

    @classmethod
    def from_payload(cls, payload: MovementModePolicyPayload) -> Self:
        return cls(
            movement_mode=movement_mode_from_token(payload["movement_mode"]),
            may_transit_enemy_engagement=payload["may_transit_enemy_engagement"],
            may_end_in_enemy_engagement=payload["may_end_in_enemy_engagement"],
            requires_charge_target=payload["requires_charge_target"],
            ignores_vertical_distance=payload["ignores_vertical_distance"],
            ignores_models=payload["ignores_models"],
            ignores_terrain=payload["ignores_terrain"],
            movement_distance_modifier=payload["movement_distance_modifier"],
        )


@dataclass(frozen=True, slots=True)
class MovementPolicyDescriptor:
    movement_modes: tuple[MovementModePolicy, ...]

    def __post_init__(self) -> None:
        if type(self.movement_modes) is not tuple:
            raise RulesetDescriptorError("MovementPolicyDescriptor movement_modes must be a tuple.")
        movement_modes = tuple(
            _validate_movement_mode_policy("movement_mode", movement_mode)
            for movement_mode in self.movement_modes
        )
        if not movement_modes:
            raise RulesetDescriptorError(
                "MovementPolicyDescriptor movement_modes must not be empty."
            )
        _validate_unique_movement_modes(movement_modes)
        object.__setattr__(
            self,
            "movement_modes",
            tuple(sorted(movement_modes, key=lambda policy: policy.movement_mode.value)),
        )

    def policy_for_mode(self, movement_mode: MovementMode) -> MovementModePolicy:
        requested_mode = movement_mode_from_token(movement_mode)
        for policy in self.movement_modes:
            if policy.movement_mode is requested_mode:
                return policy
        raise RulesetDescriptorError(
            f"MovementPolicyDescriptor does not define {requested_mode.value}."
        )

    def to_payload(self) -> MovementPolicyDescriptorPayload:
        return {
            "movement_modes": [movement_mode.to_payload() for movement_mode in self.movement_modes]
        }

    @classmethod
    def from_payload(cls, payload: MovementPolicyDescriptorPayload) -> Self:
        return cls(
            movement_modes=tuple(
                MovementModePolicy.from_payload(movement_mode)
                for movement_mode in payload["movement_modes"]
            )
        )


@dataclass(frozen=True, slots=True)
class ChargePolicyDescriptor:
    target_selection_timing: ChargeTargetSelectionTiming
    endpoint_requirement: ChargeEndpointRequirement

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_selection_timing",
            charge_target_selection_timing_from_token(self.target_selection_timing),
        )
        object.__setattr__(
            self,
            "endpoint_requirement",
            charge_endpoint_requirement_from_token(self.endpoint_requirement),
        )

    def to_payload(self) -> ChargePolicyDescriptorPayload:
        return {
            "target_selection_timing": self.target_selection_timing.value,
            "endpoint_requirement": self.endpoint_requirement.value,
        }

    @classmethod
    def from_payload(cls, payload: ChargePolicyDescriptorPayload) -> Self:
        return cls(
            target_selection_timing=charge_target_selection_timing_from_token(
                payload["target_selection_timing"]
            ),
            endpoint_requirement=charge_endpoint_requirement_from_token(
                payload["endpoint_requirement"]
            ),
        )


@dataclass(frozen=True, slots=True)
class TerrainFeatureMovementPolicy:
    terrain_feature_kind: TerrainFeatureKind
    can_move_over: bool
    can_move_through: bool
    freely_moved_over_height_inches: float | None
    endpoint_support_policy: TerrainEndpointSupportPolicy
    no_overhang_required: bool
    upper_floor_allowed_keywords: tuple[str, ...] = ()
    through_terrain_allowed_keywords: tuple[str, ...] = ()
    ground_floor_only_unless_keyword: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "terrain_feature_kind",
            terrain_feature_kind_from_token(self.terrain_feature_kind),
        )
        _validate_bool("TerrainFeatureMovementPolicy can_move_over", self.can_move_over)
        _validate_bool("TerrainFeatureMovementPolicy can_move_through", self.can_move_through)
        object.__setattr__(
            self,
            "freely_moved_over_height_inches",
            _validate_optional_positive_number(
                "TerrainFeatureMovementPolicy freely_moved_over_height_inches",
                self.freely_moved_over_height_inches,
            ),
        )
        object.__setattr__(
            self,
            "endpoint_support_policy",
            terrain_endpoint_support_policy_from_token(self.endpoint_support_policy),
        )
        _validate_bool(
            "TerrainFeatureMovementPolicy no_overhang_required",
            self.no_overhang_required,
        )
        object.__setattr__(
            self,
            "upper_floor_allowed_keywords",
            _validate_keyword_tuple(
                "TerrainFeatureMovementPolicy upper_floor_allowed_keywords",
                self.upper_floor_allowed_keywords,
            ),
        )
        object.__setattr__(
            self,
            "through_terrain_allowed_keywords",
            _validate_keyword_tuple(
                "TerrainFeatureMovementPolicy through_terrain_allowed_keywords",
                self.through_terrain_allowed_keywords,
            ),
        )
        _validate_bool(
            "TerrainFeatureMovementPolicy ground_floor_only_unless_keyword",
            self.ground_floor_only_unless_keyword,
        )
        if (
            self.endpoint_support_policy
            in {
                TerrainEndpointSupportPolicy.ALLOWED_ON_TOP_WITH_NO_OVERHANG,
                TerrainEndpointSupportPolicy.ALLOWED_ON_ANY_FLOOR_WITH_NO_OVERHANG,
            }
            and not self.no_overhang_required
        ):
            raise RulesetDescriptorError(
                "TerrainFeatureMovementPolicy no-overhang endpoint policy requires "
                "no_overhang_required."
            )

    def to_payload(self) -> TerrainFeatureMovementPolicyPayload:
        return {
            "terrain_feature_kind": self.terrain_feature_kind.value,
            "can_move_over": self.can_move_over,
            "can_move_through": self.can_move_through,
            "freely_moved_over_height_inches": self.freely_moved_over_height_inches,
            "endpoint_support_policy": self.endpoint_support_policy.value,
            "no_overhang_required": self.no_overhang_required,
            "upper_floor_allowed_keywords": list(self.upper_floor_allowed_keywords),
            "through_terrain_allowed_keywords": list(self.through_terrain_allowed_keywords),
            "ground_floor_only_unless_keyword": self.ground_floor_only_unless_keyword,
        }

    @classmethod
    def from_payload(cls, payload: TerrainFeatureMovementPolicyPayload) -> Self:
        return cls(
            terrain_feature_kind=terrain_feature_kind_from_token(payload["terrain_feature_kind"]),
            can_move_over=payload["can_move_over"],
            can_move_through=payload["can_move_through"],
            freely_moved_over_height_inches=payload["freely_moved_over_height_inches"],
            endpoint_support_policy=terrain_endpoint_support_policy_from_token(
                payload["endpoint_support_policy"]
            ),
            no_overhang_required=payload["no_overhang_required"],
            upper_floor_allowed_keywords=tuple(payload["upper_floor_allowed_keywords"]),
            through_terrain_allowed_keywords=tuple(payload["through_terrain_allowed_keywords"]),
            ground_floor_only_unless_keyword=payload["ground_floor_only_unless_keyword"],
        )


@dataclass(frozen=True, slots=True)
class TerrainMovementPolicy:
    freely_traversable_height_threshold_inches: float
    climb_vertical_distance_counts: bool
    may_end_mid_climb: bool
    requires_permission_to_move_through_features: bool
    infantry_beast_ruins_wall_traversal_mode: TerrainTraversalMode
    fly_traversal_mode: TerrainTraversalMode
    fly_uses_air_path_measurement: bool
    feature_policies: tuple[TerrainFeatureMovementPolicy, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "freely_traversable_height_threshold_inches",
            _validate_positive_number(
                "TerrainMovementPolicy freely_traversable_height_threshold_inches",
                self.freely_traversable_height_threshold_inches,
            ),
        )
        _validate_bool(
            "TerrainMovementPolicy climb_vertical_distance_counts",
            self.climb_vertical_distance_counts,
        )
        _validate_bool("TerrainMovementPolicy may_end_mid_climb", self.may_end_mid_climb)
        _validate_bool(
            "TerrainMovementPolicy requires_permission_to_move_through_features",
            self.requires_permission_to_move_through_features,
        )
        object.__setattr__(
            self,
            "infantry_beast_ruins_wall_traversal_mode",
            terrain_traversal_mode_from_token(self.infantry_beast_ruins_wall_traversal_mode),
        )
        object.__setattr__(
            self,
            "fly_traversal_mode",
            terrain_traversal_mode_from_token(self.fly_traversal_mode),
        )
        _validate_bool(
            "TerrainMovementPolicy fly_uses_air_path_measurement",
            self.fly_uses_air_path_measurement,
        )
        if (
            self.fly_uses_air_path_measurement
            and self.fly_traversal_mode is not TerrainTraversalMode.AIR_PATH
        ):
            raise RulesetDescriptorError(
                "TerrainMovementPolicy fly air-path measurement requires AIR_PATH mode."
            )
        object.__setattr__(
            self,
            "feature_policies",
            _validate_terrain_feature_movement_policy_tuple(self.feature_policies),
        )

    @classmethod
    def warhammer_40000_eleventh_default(cls) -> Self:
        return cls(
            freely_traversable_height_threshold_inches=2.0,
            climb_vertical_distance_counts=True,
            may_end_mid_climb=False,
            requires_permission_to_move_through_features=True,
            infantry_beast_ruins_wall_traversal_mode=TerrainTraversalMode.THROUGH_FEATURE,
            fly_traversal_mode=TerrainTraversalMode.AIR_PATH,
            fly_uses_air_path_measurement=True,
            feature_policies=_terrain_feature_movement_policies_for_eleventh(),
        )

    def policy_for_feature_kind(
        self,
        feature_kind: object,
    ) -> TerrainFeatureMovementPolicy:
        kind = terrain_feature_kind_from_token(feature_kind)
        for policy in self.feature_policies:
            if policy.terrain_feature_kind is kind:
                return policy
        raise RulesetDescriptorError(
            f"TerrainMovementPolicy does not define {kind.value} terrain movement."
        )

    def to_payload(self) -> TerrainMovementPolicyPayload:
        return {
            "freely_traversable_height_threshold_inches": (
                self.freely_traversable_height_threshold_inches
            ),
            "climb_vertical_distance_counts": self.climb_vertical_distance_counts,
            "may_end_mid_climb": self.may_end_mid_climb,
            "requires_permission_to_move_through_features": (
                self.requires_permission_to_move_through_features
            ),
            "infantry_beast_ruins_wall_traversal_mode": (
                self.infantry_beast_ruins_wall_traversal_mode.value
            ),
            "fly_traversal_mode": self.fly_traversal_mode.value,
            "fly_uses_air_path_measurement": self.fly_uses_air_path_measurement,
            "feature_policies": [policy.to_payload() for policy in self.feature_policies],
        }

    @classmethod
    def from_payload(cls, payload: TerrainMovementPolicyPayload) -> Self:
        return cls(
            freely_traversable_height_threshold_inches=payload[
                "freely_traversable_height_threshold_inches"
            ],
            climb_vertical_distance_counts=payload["climb_vertical_distance_counts"],
            may_end_mid_climb=payload["may_end_mid_climb"],
            requires_permission_to_move_through_features=payload[
                "requires_permission_to_move_through_features"
            ],
            infantry_beast_ruins_wall_traversal_mode=terrain_traversal_mode_from_token(
                payload["infantry_beast_ruins_wall_traversal_mode"]
            ),
            fly_traversal_mode=terrain_traversal_mode_from_token(payload["fly_traversal_mode"]),
            fly_uses_air_path_measurement=payload["fly_uses_air_path_measurement"],
            feature_policies=tuple(
                TerrainFeatureMovementPolicy.from_payload(policy)
                for policy in payload["feature_policies"]
            ),
        )


@dataclass(frozen=True, slots=True)
class CoverPolicyDescriptor:
    cover_effect: CoverEffect
    grants_benefit_of_cover: bool = True
    non_stacking: bool = True
    requires_visible_target: bool = True
    requires_not_fully_visible: bool = True
    ap_zero_save_bonus_excluded_for_save_3_plus_or_better: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "cover_effect", cover_effect_from_token(self.cover_effect))
        _validate_bool(
            "CoverPolicyDescriptor grants_benefit_of_cover",
            self.grants_benefit_of_cover,
        )
        _validate_bool("CoverPolicyDescriptor non_stacking", self.non_stacking)
        _validate_bool(
            "CoverPolicyDescriptor requires_visible_target",
            self.requires_visible_target,
        )
        _validate_bool(
            "CoverPolicyDescriptor requires_not_fully_visible",
            self.requires_not_fully_visible,
        )
        _validate_bool(
            "CoverPolicyDescriptor ap_zero_save_bonus_excluded_for_save_3_plus_or_better",
            self.ap_zero_save_bonus_excluded_for_save_3_plus_or_better,
        )
        if self.cover_effect is CoverEffect.UNSUPPORTED and self.grants_benefit_of_cover:
            raise RulesetDescriptorError(
                "CoverPolicyDescriptor cannot grant unsupported Benefit of Cover."
            )

    @classmethod
    def warhammer_40000_eleventh_default(cls) -> Self:
        return cls(cover_effect=CoverEffect.SAVE_BONUS)

    def to_payload(self) -> CoverPolicyDescriptorPayload:
        return {
            "cover_effect": self.cover_effect.value,
            "grants_benefit_of_cover": self.grants_benefit_of_cover,
            "non_stacking": self.non_stacking,
            "requires_visible_target": self.requires_visible_target,
            "requires_not_fully_visible": self.requires_not_fully_visible,
            "ap_zero_save_bonus_excluded_for_save_3_plus_or_better": (
                self.ap_zero_save_bonus_excluded_for_save_3_plus_or_better
            ),
        }

    @classmethod
    def from_payload(cls, payload: CoverPolicyDescriptorPayload) -> Self:
        return cls(
            cover_effect=cover_effect_from_token(payload["cover_effect"]),
            grants_benefit_of_cover=payload["grants_benefit_of_cover"],
            non_stacking=payload["non_stacking"],
            requires_visible_target=payload["requires_visible_target"],
            requires_not_fully_visible=payload["requires_not_fully_visible"],
            ap_zero_save_bonus_excluded_for_save_3_plus_or_better=payload[
                "ap_zero_save_bonus_excluded_for_save_3_plus_or_better"
            ],
        )


@dataclass(frozen=True, slots=True)
class TerrainFeatureVisibilityPolicy:
    terrain_feature_kind: TerrainFeatureKind
    line_of_sight_policy: LineOfSightPolicy
    blocks_model_visibility_through_footprint: bool
    blocks_full_visibility_through_footprint: bool
    uses_true_los_when_observer_wholly_within_feature: bool
    uses_true_los_when_target_intersects_feature: bool
    aircraft_uses_true_los_through_feature: bool
    towering_uses_true_los_through_feature: bool
    towering_uses_true_los_when_wholly_within_feature: bool
    cover_policy: CoverPolicyDescriptor = field(
        default_factory=CoverPolicyDescriptor.warhammer_40000_eleventh_default
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "terrain_feature_kind",
            terrain_feature_kind_from_token(self.terrain_feature_kind),
        )
        object.__setattr__(
            self,
            "line_of_sight_policy",
            line_of_sight_policy_from_token(self.line_of_sight_policy),
        )
        _validate_bool(
            "TerrainFeatureVisibilityPolicy blocks_model_visibility_through_footprint",
            self.blocks_model_visibility_through_footprint,
        )
        _validate_bool(
            "TerrainFeatureVisibilityPolicy blocks_full_visibility_through_footprint",
            self.blocks_full_visibility_through_footprint,
        )
        _validate_bool(
            "TerrainFeatureVisibilityPolicy uses_true_los_when_observer_wholly_within_feature",
            self.uses_true_los_when_observer_wholly_within_feature,
        )
        _validate_bool(
            "TerrainFeatureVisibilityPolicy uses_true_los_when_target_intersects_feature",
            self.uses_true_los_when_target_intersects_feature,
        )
        _validate_bool(
            "TerrainFeatureVisibilityPolicy aircraft_uses_true_los_through_feature",
            self.aircraft_uses_true_los_through_feature,
        )
        _validate_bool(
            "TerrainFeatureVisibilityPolicy towering_uses_true_los_through_feature",
            self.towering_uses_true_los_through_feature,
        )
        _validate_bool(
            "TerrainFeatureVisibilityPolicy towering_uses_true_los_when_wholly_within_feature",
            self.towering_uses_true_los_when_wholly_within_feature,
        )
        if type(self.cover_policy) is not CoverPolicyDescriptor:
            raise RulesetDescriptorError(
                "TerrainFeatureVisibilityPolicy cover_policy must be a CoverPolicyDescriptor."
            )
        if (
            self.blocks_model_visibility_through_footprint
            and not self.blocks_full_visibility_through_footprint
        ):
            raise RulesetDescriptorError(
                "TerrainFeatureVisibilityPolicy model-visibility blocking must also block "
                "full visibility."
            )

    def to_payload(self) -> TerrainFeatureVisibilityPolicyPayload:
        return {
            "terrain_feature_kind": self.terrain_feature_kind.value,
            "line_of_sight_policy": self.line_of_sight_policy.value,
            "blocks_model_visibility_through_footprint": (
                self.blocks_model_visibility_through_footprint
            ),
            "blocks_full_visibility_through_footprint": (
                self.blocks_full_visibility_through_footprint
            ),
            "uses_true_los_when_observer_wholly_within_feature": (
                self.uses_true_los_when_observer_wholly_within_feature
            ),
            "uses_true_los_when_target_intersects_feature": (
                self.uses_true_los_when_target_intersects_feature
            ),
            "aircraft_uses_true_los_through_feature": (self.aircraft_uses_true_los_through_feature),
            "towering_uses_true_los_through_feature": (self.towering_uses_true_los_through_feature),
            "towering_uses_true_los_when_wholly_within_feature": (
                self.towering_uses_true_los_when_wholly_within_feature
            ),
            "cover_policy": self.cover_policy.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: TerrainFeatureVisibilityPolicyPayload) -> Self:
        return cls(
            terrain_feature_kind=terrain_feature_kind_from_token(payload["terrain_feature_kind"]),
            line_of_sight_policy=line_of_sight_policy_from_token(payload["line_of_sight_policy"]),
            blocks_model_visibility_through_footprint=payload[
                "blocks_model_visibility_through_footprint"
            ],
            blocks_full_visibility_through_footprint=payload[
                "blocks_full_visibility_through_footprint"
            ],
            uses_true_los_when_observer_wholly_within_feature=payload[
                "uses_true_los_when_observer_wholly_within_feature"
            ],
            uses_true_los_when_target_intersects_feature=payload[
                "uses_true_los_when_target_intersects_feature"
            ],
            aircraft_uses_true_los_through_feature=payload[
                "aircraft_uses_true_los_through_feature"
            ],
            towering_uses_true_los_through_feature=payload[
                "towering_uses_true_los_through_feature"
            ],
            towering_uses_true_los_when_wholly_within_feature=payload[
                "towering_uses_true_los_when_wholly_within_feature"
            ],
            cover_policy=CoverPolicyDescriptor.from_payload(payload["cover_policy"]),
        )


@dataclass(frozen=True, slots=True)
class TerrainVisibilityPolicyDescriptor:
    hidden_supported: bool
    hidden_detection_range_inches: float | None
    hidden_requires_keywords: tuple[str, ...] = ()
    hidden_requires_terrain_area_occupancy: bool = False
    hidden_lost_after_shooting: bool = False
    cover_effect: CoverEffect = CoverEffect.SAVE_BONUS
    cover_policy: CoverPolicyDescriptor = field(
        default_factory=CoverPolicyDescriptor.warhammer_40000_eleventh_default
    )
    feature_policies: tuple[TerrainFeatureVisibilityPolicy, ...] = ()

    def __post_init__(self) -> None:
        _validate_bool(
            "TerrainVisibilityPolicyDescriptor hidden_supported",
            self.hidden_supported,
        )
        object.__setattr__(
            self,
            "hidden_detection_range_inches",
            _validate_optional_positive_number(
                "TerrainVisibilityPolicyDescriptor hidden_detection_range_inches",
                self.hidden_detection_range_inches,
            ),
        )
        object.__setattr__(
            self,
            "hidden_requires_keywords",
            _validate_identifier_tuple(
                "TerrainVisibilityPolicyDescriptor hidden_requires_keywords",
                self.hidden_requires_keywords,
            ),
        )
        _validate_bool(
            "TerrainVisibilityPolicyDescriptor hidden_requires_terrain_area_occupancy",
            self.hidden_requires_terrain_area_occupancy,
        )
        _validate_bool(
            "TerrainVisibilityPolicyDescriptor hidden_lost_after_shooting",
            self.hidden_lost_after_shooting,
        )
        object.__setattr__(self, "cover_effect", cover_effect_from_token(self.cover_effect))
        if type(self.cover_policy) is not CoverPolicyDescriptor:
            raise RulesetDescriptorError(
                "TerrainVisibilityPolicyDescriptor cover_policy must be a CoverPolicyDescriptor."
            )
        if self.cover_policy.cover_effect is not self.cover_effect:
            raise RulesetDescriptorError(
                "TerrainVisibilityPolicyDescriptor cover_policy must match cover_effect."
            )
        object.__setattr__(
            self,
            "feature_policies",
            _validate_terrain_feature_visibility_policy_tuple(self.feature_policies),
        )

    def policy_for_feature_kind(
        self,
        terrain_feature_kind: TerrainFeatureKind,
    ) -> TerrainFeatureVisibilityPolicy:
        feature_kind = terrain_feature_kind_from_token(terrain_feature_kind)
        for policy in self.feature_policies:
            if policy.terrain_feature_kind is feature_kind:
                return policy
        raise RulesetDescriptorError(
            f"TerrainVisibilityPolicyDescriptor does not define {feature_kind.value}."
        )

    def to_payload(self) -> TerrainVisibilityPolicyDescriptorPayload:
        return {
            "hidden_supported": self.hidden_supported,
            "hidden_detection_range_inches": self.hidden_detection_range_inches,
            "hidden_requires_keywords": list(self.hidden_requires_keywords),
            "hidden_requires_terrain_area_occupancy": (self.hidden_requires_terrain_area_occupancy),
            "hidden_lost_after_shooting": self.hidden_lost_after_shooting,
            "cover_effect": self.cover_effect.value,
            "cover_policy": self.cover_policy.to_payload(),
            "feature_policies": [policy.to_payload() for policy in self.feature_policies],
        }

    @classmethod
    def from_payload(cls, payload: TerrainVisibilityPolicyDescriptorPayload) -> Self:
        return cls(
            hidden_supported=payload["hidden_supported"],
            hidden_detection_range_inches=payload["hidden_detection_range_inches"],
            hidden_requires_keywords=tuple(payload["hidden_requires_keywords"]),
            hidden_requires_terrain_area_occupancy=payload[
                "hidden_requires_terrain_area_occupancy"
            ],
            hidden_lost_after_shooting=payload["hidden_lost_after_shooting"],
            cover_effect=cover_effect_from_token(payload["cover_effect"]),
            cover_policy=CoverPolicyDescriptor.from_payload(payload["cover_policy"]),
            feature_policies=tuple(
                TerrainFeatureVisibilityPolicy.from_payload(policy)
                for policy in payload["feature_policies"]
            ),
        )


@dataclass(frozen=True, slots=True)
class ObjectivePolicyDescriptor:
    supported_anchor_kinds: tuple[ObjectiveAnchorKind, ...]
    default_point_control_radius_inches: float | None
    terrain_objective_control_policy: TerrainObjectiveControlPolicy

    def __post_init__(self) -> None:
        if type(self.supported_anchor_kinds) is not tuple:
            raise RulesetDescriptorError(
                "ObjectivePolicyDescriptor supported_anchor_kinds must be a tuple."
            )
        supported_anchor_kinds = tuple(
            objective_anchor_kind_from_token(anchor_kind)
            for anchor_kind in self.supported_anchor_kinds
        )
        if not supported_anchor_kinds:
            raise RulesetDescriptorError(
                "ObjectivePolicyDescriptor supported_anchor_kinds must not be empty."
            )
        _validate_unique_anchor_kinds(supported_anchor_kinds)
        object.__setattr__(
            self,
            "supported_anchor_kinds",
            tuple(sorted(supported_anchor_kinds, key=lambda anchor_kind: anchor_kind.value)),
        )
        object.__setattr__(
            self,
            "default_point_control_radius_inches",
            _validate_optional_positive_number(
                "ObjectivePolicyDescriptor default_point_control_radius_inches",
                self.default_point_control_radius_inches,
            ),
        )
        object.__setattr__(
            self,
            "terrain_objective_control_policy",
            terrain_objective_control_policy_from_token(self.terrain_objective_control_policy),
        )

    def to_payload(self) -> ObjectivePolicyDescriptorPayload:
        return {
            "supported_anchor_kinds": [
                anchor_kind.value for anchor_kind in self.supported_anchor_kinds
            ],
            "default_point_control_radius_inches": self.default_point_control_radius_inches,
            "terrain_objective_control_policy": self.terrain_objective_control_policy.value,
        }

    @classmethod
    def from_payload(cls, payload: ObjectivePolicyDescriptorPayload) -> Self:
        return cls(
            supported_anchor_kinds=tuple(
                objective_anchor_kind_from_token(anchor_kind)
                for anchor_kind in payload["supported_anchor_kinds"]
            ),
            default_point_control_radius_inches=payload["default_point_control_radius_inches"],
            terrain_objective_control_policy=terrain_objective_control_policy_from_token(
                payload["terrain_objective_control_policy"]
            ),
        )


@dataclass(frozen=True, slots=True)
class CoherencyPolicyDescriptor:
    policy_kind: CoherencyPolicyKind
    required_neighbors_small_unit: int | None = None
    required_neighbors_large_unit: int | None = None
    large_unit_model_count_threshold: int | None = None
    max_horizontal_inches: float | None = None
    max_vertical_inches: float | None = None
    max_all_models_distance_inches: float | None = None
    max_unit_span_inches: float | None = None

    def __post_init__(self) -> None:
        policy_kind = coherency_policy_kind_from_token(self.policy_kind)
        object.__setattr__(self, "policy_kind", policy_kind)
        object.__setattr__(
            self,
            "required_neighbors_small_unit",
            _validate_optional_positive_int(
                "CoherencyPolicyDescriptor required_neighbors_small_unit",
                self.required_neighbors_small_unit,
            ),
        )
        object.__setattr__(
            self,
            "required_neighbors_large_unit",
            _validate_optional_positive_int(
                "CoherencyPolicyDescriptor required_neighbors_large_unit",
                self.required_neighbors_large_unit,
            ),
        )
        object.__setattr__(
            self,
            "large_unit_model_count_threshold",
            _validate_optional_positive_int(
                "CoherencyPolicyDescriptor large_unit_model_count_threshold",
                self.large_unit_model_count_threshold,
            ),
        )
        if (self.required_neighbors_large_unit is None) != (
            self.large_unit_model_count_threshold is None
        ):
            raise RulesetDescriptorError(
                "CoherencyPolicyDescriptor large-unit neighbor fields must both be set or unset."
            )
        object.__setattr__(
            self,
            "max_horizontal_inches",
            _validate_optional_positive_number(
                "CoherencyPolicyDescriptor max_horizontal_inches",
                self.max_horizontal_inches,
            ),
        )
        object.__setattr__(
            self,
            "max_vertical_inches",
            _validate_optional_positive_number(
                "CoherencyPolicyDescriptor max_vertical_inches",
                self.max_vertical_inches,
            ),
        )
        object.__setattr__(
            self,
            "max_all_models_distance_inches",
            _validate_optional_positive_number(
                "CoherencyPolicyDescriptor max_all_models_distance_inches",
                self.max_all_models_distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "max_unit_span_inches",
            _validate_optional_positive_number(
                "CoherencyPolicyDescriptor max_unit_span_inches",
                self.max_unit_span_inches,
            ),
        )
        if policy_kind is CoherencyPolicyKind.NEIGHBOR_COUNT:
            if (
                self.required_neighbors_small_unit is None
                or self.max_horizontal_inches is None
                or self.max_vertical_inches is None
            ):
                raise RulesetDescriptorError(
                    "NEIGHBOR_COUNT coherency requires small-unit neighbors and distances."
                )
            if self.max_all_models_distance_inches is not None:
                raise RulesetDescriptorError(
                    "NEIGHBOR_COUNT coherency must not set all-model distance fields."
                )
        if policy_kind is CoherencyPolicyKind.ALL_MODELS_WITHIN_DISTANCE:
            if self.max_all_models_distance_inches is None:
                raise RulesetDescriptorError(
                    "ALL_MODELS_WITHIN_DISTANCE coherency requires max_all_models_distance_inches."
                )
            if (
                self.required_neighbors_small_unit is not None
                or self.required_neighbors_large_unit is not None
                or self.large_unit_model_count_threshold is not None
                or self.max_horizontal_inches is not None
                or self.max_vertical_inches is not None
                or self.max_unit_span_inches is not None
            ):
                raise RulesetDescriptorError(
                    "ALL_MODELS_WITHIN_DISTANCE coherency must not set neighbor-count fields."
                )

    def to_payload(self) -> CoherencyPolicyDescriptorPayload:
        return {
            "policy_kind": self.policy_kind.value,
            "required_neighbors_small_unit": self.required_neighbors_small_unit,
            "required_neighbors_large_unit": self.required_neighbors_large_unit,
            "large_unit_model_count_threshold": self.large_unit_model_count_threshold,
            "max_horizontal_inches": self.max_horizontal_inches,
            "max_vertical_inches": self.max_vertical_inches,
            "max_all_models_distance_inches": self.max_all_models_distance_inches,
            "max_unit_span_inches": self.max_unit_span_inches,
        }

    @classmethod
    def from_payload(cls, payload: CoherencyPolicyDescriptorPayload) -> Self:
        return cls(
            policy_kind=coherency_policy_kind_from_token(payload["policy_kind"]),
            required_neighbors_small_unit=payload["required_neighbors_small_unit"],
            required_neighbors_large_unit=payload["required_neighbors_large_unit"],
            large_unit_model_count_threshold=payload["large_unit_model_count_threshold"],
            max_horizontal_inches=payload["max_horizontal_inches"],
            max_vertical_inches=payload["max_vertical_inches"],
            max_all_models_distance_inches=payload["max_all_models_distance_inches"],
            max_unit_span_inches=payload["max_unit_span_inches"],
        )


@dataclass(frozen=True, slots=True)
class FlyPolicyDescriptor:
    take_to_the_skies_supported: bool
    movement_penalty_inches: float
    ignores_vertical_distance: bool
    may_move_through_models: bool
    may_move_through_terrain: bool

    def __post_init__(self) -> None:
        _validate_bool(
            "FlyPolicyDescriptor take_to_the_skies_supported",
            self.take_to_the_skies_supported,
        )
        object.__setattr__(
            self,
            "movement_penalty_inches",
            _validate_non_negative_number(
                "FlyPolicyDescriptor movement_penalty_inches",
                self.movement_penalty_inches,
            ),
        )
        _validate_bool(
            "FlyPolicyDescriptor ignores_vertical_distance",
            self.ignores_vertical_distance,
        )
        _validate_bool(
            "FlyPolicyDescriptor may_move_through_models",
            self.may_move_through_models,
        )
        _validate_bool(
            "FlyPolicyDescriptor may_move_through_terrain",
            self.may_move_through_terrain,
        )

    def to_payload(self) -> FlyPolicyDescriptorPayload:
        return {
            "take_to_the_skies_supported": self.take_to_the_skies_supported,
            "movement_penalty_inches": self.movement_penalty_inches,
            "ignores_vertical_distance": self.ignores_vertical_distance,
            "may_move_through_models": self.may_move_through_models,
            "may_move_through_terrain": self.may_move_through_terrain,
        }

    @classmethod
    def from_payload(cls, payload: FlyPolicyDescriptorPayload) -> Self:
        return cls(
            take_to_the_skies_supported=payload["take_to_the_skies_supported"],
            movement_penalty_inches=payload["movement_penalty_inches"],
            ignores_vertical_distance=payload["ignores_vertical_distance"],
            may_move_through_models=payload["may_move_through_models"],
            may_move_through_terrain=payload["may_move_through_terrain"],
        )


@dataclass(frozen=True, slots=True)
class MissionPolicyDescriptor:
    fixed_objective_missions_supported: bool
    terrain_objective_missions_supported: bool
    deployment_zone_source: MissionDeploymentZoneSource
    reserves_arrival_blocked_battle_rounds: tuple[int, ...] = ()
    reserves_arrival_excludes_during_battle_strategic_reserves: bool = False
    reserve_destruction_timing: ReserveDestructionTimingKind = (
        ReserveDestructionTimingKind.END_OF_BATTLE
    )
    reserve_destruction_battle_round: int | None = None
    reserve_destruction_excludes_during_battle_strategic_reserves: bool = False
    reserve_destruction_only_declare_battle_formations: bool = False

    def __post_init__(self) -> None:
        _validate_bool(
            "MissionPolicyDescriptor fixed_objective_missions_supported",
            self.fixed_objective_missions_supported,
        )
        _validate_bool(
            "MissionPolicyDescriptor terrain_objective_missions_supported",
            self.terrain_objective_missions_supported,
        )
        object.__setattr__(
            self,
            "deployment_zone_source",
            mission_deployment_zone_source_from_token(self.deployment_zone_source),
        )
        object.__setattr__(
            self,
            "reserves_arrival_blocked_battle_rounds",
            _validate_positive_int_tuple(
                "MissionPolicyDescriptor reserves_arrival_blocked_battle_rounds",
                self.reserves_arrival_blocked_battle_rounds,
            ),
        )
        _validate_bool(
            "MissionPolicyDescriptor reserves_arrival_excludes_during_battle_strategic_reserves",
            self.reserves_arrival_excludes_during_battle_strategic_reserves,
        )
        timing = reserve_destruction_timing_kind_from_token(self.reserve_destruction_timing)
        object.__setattr__(self, "reserve_destruction_timing", timing)
        object.__setattr__(
            self,
            "reserve_destruction_battle_round",
            _validate_optional_positive_int(
                "MissionPolicyDescriptor reserve_destruction_battle_round",
                self.reserve_destruction_battle_round,
            ),
        )
        _validate_bool(
            "MissionPolicyDescriptor reserve_destruction_excludes_during_battle_strategic_reserves",
            self.reserve_destruction_excludes_during_battle_strategic_reserves,
        )
        _validate_bool(
            "MissionPolicyDescriptor reserve_destruction_only_declare_battle_formations",
            self.reserve_destruction_only_declare_battle_formations,
        )
        if (
            timing is ReserveDestructionTimingKind.END_OF_BATTLE
            and self.reserve_destruction_battle_round is not None
        ):
            raise RulesetDescriptorError(
                "END_OF_BATTLE reserve destruction must not set a battle round."
            )
        if (
            timing is ReserveDestructionTimingKind.END_OF_BATTLE_ROUND_N
            and self.reserve_destruction_battle_round is None
        ):
            raise RulesetDescriptorError(
                "END_OF_BATTLE_ROUND_N reserve destruction requires a battle round."
            )

    @classmethod
    def core_rules_default(cls) -> Self:
        return cls(
            fixed_objective_missions_supported=True,
            terrain_objective_missions_supported=False,
            deployment_zone_source=MissionDeploymentZoneSource.MISSION,
            reserves_arrival_blocked_battle_rounds=(),
            reserves_arrival_excludes_during_battle_strategic_reserves=False,
            reserve_destruction_timing=ReserveDestructionTimingKind.END_OF_BATTLE,
            reserve_destruction_battle_round=None,
            reserve_destruction_excludes_during_battle_strategic_reserves=False,
            reserve_destruction_only_declare_battle_formations=False,
        )

    @classmethod
    def chapter_approved_2025_26(cls) -> Self:
        return cls(
            fixed_objective_missions_supported=True,
            terrain_objective_missions_supported=True,
            deployment_zone_source=MissionDeploymentZoneSource.MISSION,
            reserves_arrival_blocked_battle_rounds=(1,),
            reserves_arrival_excludes_during_battle_strategic_reserves=True,
            reserve_destruction_timing=ReserveDestructionTimingKind.END_OF_BATTLE_ROUND_N,
            reserve_destruction_battle_round=3,
            reserve_destruction_excludes_during_battle_strategic_reserves=True,
            reserve_destruction_only_declare_battle_formations=True,
        )

    def to_payload(self) -> MissionPolicyDescriptorPayload:
        return {
            "fixed_objective_missions_supported": self.fixed_objective_missions_supported,
            "terrain_objective_missions_supported": self.terrain_objective_missions_supported,
            "deployment_zone_source": self.deployment_zone_source.value,
            "reserves_arrival_blocked_battle_rounds": list(
                self.reserves_arrival_blocked_battle_rounds
            ),
            "reserves_arrival_excludes_during_battle_strategic_reserves": (
                self.reserves_arrival_excludes_during_battle_strategic_reserves
            ),
            "reserve_destruction_timing": self.reserve_destruction_timing.value,
            "reserve_destruction_battle_round": self.reserve_destruction_battle_round,
            "reserve_destruction_excludes_during_battle_strategic_reserves": (
                self.reserve_destruction_excludes_during_battle_strategic_reserves
            ),
            "reserve_destruction_only_declare_battle_formations": (
                self.reserve_destruction_only_declare_battle_formations
            ),
        }

    @classmethod
    def from_payload(cls, payload: MissionPolicyDescriptorPayload) -> Self:
        return cls(
            fixed_objective_missions_supported=payload["fixed_objective_missions_supported"],
            terrain_objective_missions_supported=payload["terrain_objective_missions_supported"],
            deployment_zone_source=mission_deployment_zone_source_from_token(
                payload["deployment_zone_source"]
            ),
            reserves_arrival_blocked_battle_rounds=tuple(
                payload["reserves_arrival_blocked_battle_rounds"]
            ),
            reserves_arrival_excludes_during_battle_strategic_reserves=payload[
                "reserves_arrival_excludes_during_battle_strategic_reserves"
            ],
            reserve_destruction_timing=reserve_destruction_timing_kind_from_token(
                payload["reserve_destruction_timing"]
            ),
            reserve_destruction_battle_round=payload["reserve_destruction_battle_round"],
            reserve_destruction_excludes_during_battle_strategic_reserves=payload[
                "reserve_destruction_excludes_during_battle_strategic_reserves"
            ],
            reserve_destruction_only_declare_battle_formations=payload[
                "reserve_destruction_only_declare_battle_formations"
            ],
        )


@dataclass(frozen=True, slots=True)
class RulesetDescriptor:
    ruleset_id: RulesetId
    source_date: str | date
    descriptor_version: str
    engagement_policy: EngagementPolicyDescriptor
    movement_policy: MovementPolicyDescriptor
    charge_policy: ChargePolicyDescriptor
    terrain_movement_policy: TerrainMovementPolicy
    terrain_visibility_policy: TerrainVisibilityPolicyDescriptor
    objective_policy: ObjectivePolicyDescriptor
    coherency_policy: CoherencyPolicyDescriptor
    fly_policy: FlyPolicyDescriptor
    mission_policy: MissionPolicyDescriptor
    setup_sequence: SetupSequenceDescriptor
    battle_phase_sequence: BattlePhaseSequenceDescriptor
    descriptor_hash: str = ""

    def __post_init__(self) -> None:
        if type(self.ruleset_id) is not RulesetId:
            raise RulesetDescriptorError("RulesetDescriptor ruleset_id must be a RulesetId.")
        object.__setattr__(self, "source_date", _validate_source_date(self.source_date))
        object.__setattr__(
            self,
            "descriptor_version",
            _validate_identifier("RulesetDescriptor descriptor_version", self.descriptor_version),
        )
        _validate_descriptor_part(
            "RulesetDescriptor engagement_policy",
            self.engagement_policy,
            EngagementPolicyDescriptor,
        )
        _validate_descriptor_part(
            "RulesetDescriptor movement_policy",
            self.movement_policy,
            MovementPolicyDescriptor,
        )
        _validate_descriptor_part(
            "RulesetDescriptor charge_policy",
            self.charge_policy,
            ChargePolicyDescriptor,
        )
        _validate_descriptor_part(
            "RulesetDescriptor terrain_movement_policy",
            self.terrain_movement_policy,
            TerrainMovementPolicy,
        )
        _validate_descriptor_part(
            "RulesetDescriptor terrain_visibility_policy",
            self.terrain_visibility_policy,
            TerrainVisibilityPolicyDescriptor,
        )
        _validate_descriptor_part(
            "RulesetDescriptor objective_policy",
            self.objective_policy,
            ObjectivePolicyDescriptor,
        )
        _validate_descriptor_part(
            "RulesetDescriptor coherency_policy",
            self.coherency_policy,
            CoherencyPolicyDescriptor,
        )
        _validate_descriptor_part(
            "RulesetDescriptor fly_policy",
            self.fly_policy,
            FlyPolicyDescriptor,
        )
        _validate_descriptor_part(
            "RulesetDescriptor mission_policy",
            self.mission_policy,
            MissionPolicyDescriptor,
        )
        _validate_descriptor_part(
            "RulesetDescriptor setup_sequence",
            self.setup_sequence,
            SetupSequenceDescriptor,
        )
        _validate_descriptor_part(
            "RulesetDescriptor battle_phase_sequence",
            self.battle_phase_sequence,
            BattlePhaseSequenceDescriptor,
        )

        expected_hash = _descriptor_hash(self._payload_without_hash())
        if self.descriptor_hash:
            descriptor_hash = _validate_descriptor_hash(self.descriptor_hash)
            if descriptor_hash != expected_hash:
                raise RulesetDescriptorError("RulesetDescriptor descriptor_hash does not match.")
        object.__setattr__(self, "descriptor_hash", expected_hash)

    @classmethod
    def warhammer_40000_eleventh(
        cls,
        source_date: str | date = "2026-06-01",
        descriptor_version: str = "core-v2-phase14a",
    ) -> Self:
        return cls(
            ruleset_id=RulesetId.warhammer_40000_eleventh(version=descriptor_version),
            source_date=source_date,
            descriptor_version=descriptor_version,
            engagement_policy=EngagementPolicyDescriptor(
                horizontal_inches=2.0,
                vertical_inches=5.0,
            ),
            movement_policy=_movement_policy_for_eleventh(),
            charge_policy=ChargePolicyDescriptor(
                target_selection_timing=ChargeTargetSelectionTiming.BEFORE_ROLL,
                endpoint_requirement=ChargeEndpointRequirement.DECLARED_TARGET_ENGAGEMENT,
            ),
            terrain_movement_policy=TerrainMovementPolicy.warhammer_40000_eleventh_default(),
            terrain_visibility_policy=TerrainVisibilityPolicyDescriptor(
                hidden_supported=False,
                hidden_detection_range_inches=None,
                hidden_requires_keywords=(),
                hidden_requires_terrain_area_occupancy=False,
                hidden_lost_after_shooting=False,
                cover_effect=CoverEffect.SAVE_BONUS,
                cover_policy=CoverPolicyDescriptor.warhammer_40000_eleventh_default(),
                feature_policies=_terrain_feature_visibility_policies_for_eleventh(),
            ),
            objective_policy=ObjectivePolicyDescriptor(
                supported_anchor_kinds=(ObjectiveAnchorKind.POINT, ObjectiveAnchorKind.TERRAIN),
                default_point_control_radius_inches=3.0,
                terrain_objective_control_policy=(
                    TerrainObjectiveControlPolicy.TERRAIN_AREA_OCCUPANCY
                ),
            ),
            coherency_policy=CoherencyPolicyDescriptor(
                policy_kind=CoherencyPolicyKind.NEIGHBOR_COUNT,
                required_neighbors_small_unit=1,
                required_neighbors_large_unit=None,
                large_unit_model_count_threshold=None,
                max_horizontal_inches=2.0,
                max_vertical_inches=5.0,
                max_all_models_distance_inches=None,
                max_unit_span_inches=9.0,
            ),
            fly_policy=FlyPolicyDescriptor(
                take_to_the_skies_supported=True,
                movement_penalty_inches=2.0,
                ignores_vertical_distance=True,
                may_move_through_models=True,
                may_move_through_terrain=True,
            ),
            mission_policy=MissionPolicyDescriptor.core_rules_default(),
            setup_sequence=SetupSequenceDescriptor.warhammer_40000_eleventh_default(),
            battle_phase_sequence=BattlePhaseSequenceDescriptor.warhammer_40000_eleventh_default(),
        )

    @classmethod
    def warhammer_40000_eleventh_chapter_approved_2025_26(
        cls,
        source_date: str | date = "2025-06-01",
        descriptor_version: str = "core-v2-phase14a-ca2025-26",
    ) -> Self:
        core = cls.warhammer_40000_eleventh(
            source_date=source_date,
            descriptor_version=descriptor_version,
        )
        return cls(
            ruleset_id=core.ruleset_id,
            source_date=core.source_date,
            descriptor_version=core.descriptor_version,
            engagement_policy=core.engagement_policy,
            movement_policy=core.movement_policy,
            charge_policy=core.charge_policy,
            terrain_movement_policy=core.terrain_movement_policy,
            terrain_visibility_policy=core.terrain_visibility_policy,
            objective_policy=core.objective_policy,
            coherency_policy=core.coherency_policy,
            fly_policy=core.fly_policy,
            mission_policy=MissionPolicyDescriptor.chapter_approved_2025_26(),
            setup_sequence=core.setup_sequence,
            battle_phase_sequence=core.battle_phase_sequence,
        )

    def to_payload(self) -> RulesetDescriptorPayload:
        payload = self._payload_without_hash()
        payload["descriptor_hash"] = self.descriptor_hash
        return payload

    @classmethod
    def from_payload(cls, payload: RulesetDescriptorPayload) -> Self:
        return cls(
            ruleset_id=RulesetId.from_payload(payload["ruleset_id"]),
            source_date=payload["source_date"],
            descriptor_version=payload["descriptor_version"],
            descriptor_hash=payload["descriptor_hash"],
            engagement_policy=EngagementPolicyDescriptor.from_payload(payload["engagement_policy"]),
            movement_policy=MovementPolicyDescriptor.from_payload(payload["movement_policy"]),
            charge_policy=ChargePolicyDescriptor.from_payload(payload["charge_policy"]),
            terrain_movement_policy=TerrainMovementPolicy.from_payload(
                payload["terrain_movement_policy"]
            ),
            terrain_visibility_policy=TerrainVisibilityPolicyDescriptor.from_payload(
                payload["terrain_visibility_policy"]
            ),
            objective_policy=ObjectivePolicyDescriptor.from_payload(payload["objective_policy"]),
            coherency_policy=CoherencyPolicyDescriptor.from_payload(payload["coherency_policy"]),
            fly_policy=FlyPolicyDescriptor.from_payload(payload["fly_policy"]),
            mission_policy=MissionPolicyDescriptor.from_payload(payload["mission_policy"]),
            setup_sequence=SetupSequenceDescriptor.from_payload(payload["setup_sequence"]),
            battle_phase_sequence=BattlePhaseSequenceDescriptor.from_payload(
                payload["battle_phase_sequence"]
            ),
        )

    def _payload_without_hash(self) -> RulesetDescriptorPayload:
        return {
            "ruleset_id": self.ruleset_id.to_payload(),
            "source_date": str(self.source_date),
            "descriptor_version": self.descriptor_version,
            "descriptor_hash": "",
            "engagement_policy": self.engagement_policy.to_payload(),
            "movement_policy": self.movement_policy.to_payload(),
            "charge_policy": self.charge_policy.to_payload(),
            "terrain_movement_policy": self.terrain_movement_policy.to_payload(),
            "terrain_visibility_policy": self.terrain_visibility_policy.to_payload(),
            "objective_policy": self.objective_policy.to_payload(),
            "coherency_policy": self.coherency_policy.to_payload(),
            "fly_policy": self.fly_policy.to_payload(),
            "mission_policy": self.mission_policy.to_payload(),
            "setup_sequence": self.setup_sequence.to_payload(),
            "battle_phase_sequence": self.battle_phase_sequence.to_payload(),
        }


def movement_mode_from_token(token: object) -> MovementMode:
    if type(token) is MovementMode:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("MovementMode token must be a string.")
    try:
        return MovementMode(token)
    except ValueError as exc:
        raise RulesetDescriptorError(f"Unsupported MovementMode token: {token}.") from exc


def charge_target_selection_timing_from_token(token: object) -> ChargeTargetSelectionTiming:
    if type(token) is ChargeTargetSelectionTiming:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("ChargeTargetSelectionTiming token must be a string.")
    try:
        return ChargeTargetSelectionTiming(token)
    except ValueError as exc:
        raise RulesetDescriptorError(
            f"Unsupported ChargeTargetSelectionTiming token: {token}."
        ) from exc


def charge_endpoint_requirement_from_token(token: object) -> ChargeEndpointRequirement:
    if type(token) is ChargeEndpointRequirement:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("ChargeEndpointRequirement token must be a string.")
    try:
        return ChargeEndpointRequirement(token)
    except ValueError as exc:
        raise RulesetDescriptorError(
            f"Unsupported ChargeEndpointRequirement token: {token}."
        ) from exc


def terrain_objective_control_policy_from_token(
    token: object,
) -> TerrainObjectiveControlPolicy:
    if type(token) is TerrainObjectiveControlPolicy:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("TerrainObjectiveControlPolicy token must be a string.")
    try:
        return TerrainObjectiveControlPolicy(token)
    except ValueError as exc:
        raise RulesetDescriptorError(
            f"Unsupported TerrainObjectiveControlPolicy token: {token}."
        ) from exc


def terrain_feature_kind_from_token(token: object) -> TerrainFeatureKind:
    if type(token) is TerrainFeatureKind:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("TerrainFeatureKind token must be a string.")
    try:
        return TerrainFeatureKind(token)
    except ValueError as exc:
        raise RulesetDescriptorError(f"Unsupported TerrainFeatureKind token: {token}.") from exc


def terrain_endpoint_support_policy_from_token(token: object) -> TerrainEndpointSupportPolicy:
    if type(token) is TerrainEndpointSupportPolicy:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("TerrainEndpointSupportPolicy token must be a string.")
    try:
        return TerrainEndpointSupportPolicy(token)
    except ValueError as exc:
        raise RulesetDescriptorError(
            f"Unsupported TerrainEndpointSupportPolicy token: {token}."
        ) from exc


def terrain_traversal_mode_from_token(token: object) -> TerrainTraversalMode:
    if type(token) is TerrainTraversalMode:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("TerrainTraversalMode token must be a string.")
    try:
        return TerrainTraversalMode(token)
    except ValueError as exc:
        raise RulesetDescriptorError(f"Unsupported TerrainTraversalMode token: {token}.") from exc


def cover_effect_from_token(token: object) -> CoverEffect:
    if type(token) is CoverEffect:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("CoverEffect token must be a string.")
    try:
        return CoverEffect(token)
    except ValueError as exc:
        raise RulesetDescriptorError(f"Unsupported CoverEffect token: {token}.") from exc


def line_of_sight_policy_from_token(token: object) -> LineOfSightPolicy:
    if type(token) is LineOfSightPolicy:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("LineOfSightPolicy token must be a string.")
    try:
        return LineOfSightPolicy(token)
    except ValueError as exc:
        raise RulesetDescriptorError(f"Unsupported LineOfSightPolicy token: {token}.") from exc


def mission_deployment_zone_source_from_token(token: object) -> MissionDeploymentZoneSource:
    if type(token) is MissionDeploymentZoneSource:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("MissionDeploymentZoneSource token must be a string.")
    try:
        return MissionDeploymentZoneSource(token)
    except ValueError as exc:
        raise RulesetDescriptorError(
            f"Unsupported MissionDeploymentZoneSource token: {token}."
        ) from exc


def reserve_destruction_timing_kind_from_token(token: object) -> ReserveDestructionTimingKind:
    if type(token) is ReserveDestructionTimingKind:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("ReserveDestructionTimingKind token must be a string.")
    try:
        return ReserveDestructionTimingKind(token)
    except ValueError as exc:
        raise RulesetDescriptorError(
            f"Unsupported ReserveDestructionTimingKind token: {token}."
        ) from exc


def coherency_policy_kind_from_token(token: object) -> CoherencyPolicyKind:
    if type(token) is CoherencyPolicyKind:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("CoherencyPolicyKind token must be a string.")
    try:
        return CoherencyPolicyKind(token)
    except ValueError as exc:
        raise RulesetDescriptorError(f"Unsupported CoherencyPolicyKind token: {token}.") from exc


def objective_anchor_kind_from_token(token: object) -> ObjectiveAnchorKind:
    if type(token) is ObjectiveAnchorKind:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("ObjectiveAnchorKind token must be a string.")
    try:
        return ObjectiveAnchorKind(token)
    except ValueError as exc:
        raise RulesetDescriptorError(f"Unsupported ObjectiveAnchorKind token: {token}.") from exc


def setup_step_kind_from_token(token: object) -> SetupStepKind:
    if type(token) is SetupStepKind:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("SetupStepKind token must be a string.")
    try:
        return SetupStepKind(token)
    except ValueError as exc:
        raise RulesetDescriptorError(f"Unsupported SetupStepKind token: {token}.") from exc


def battle_phase_kind_from_token(token: object) -> BattlePhaseKind:
    if type(token) is BattlePhaseKind:
        return token
    if type(token) is not str:
        raise RulesetDescriptorError("BattlePhaseKind token must be a string.")
    try:
        return BattlePhaseKind(token)
    except ValueError as exc:
        raise RulesetDescriptorError(f"Unsupported BattlePhaseKind token: {token}.") from exc


def _movement_policy_for_eleventh() -> MovementPolicyDescriptor:
    return MovementPolicyDescriptor(
        movement_modes=(
            MovementModePolicy(
                movement_mode=MovementMode.NORMAL,
                may_transit_enemy_engagement=False,
                may_end_in_enemy_engagement=False,
                requires_charge_target=False,
                ignores_vertical_distance=False,
                ignores_models=False,
                ignores_terrain=False,
            ),
            MovementModePolicy(
                movement_mode=MovementMode.ADVANCE,
                may_transit_enemy_engagement=False,
                may_end_in_enemy_engagement=False,
                requires_charge_target=False,
                ignores_vertical_distance=False,
                ignores_models=False,
                ignores_terrain=False,
            ),
            MovementModePolicy(
                movement_mode=MovementMode.FALL_BACK,
                may_transit_enemy_engagement=True,
                may_end_in_enemy_engagement=False,
                requires_charge_target=False,
                ignores_vertical_distance=False,
                ignores_models=False,
                ignores_terrain=False,
            ),
            MovementModePolicy(
                movement_mode=MovementMode.CHARGE,
                may_transit_enemy_engagement=True,
                may_end_in_enemy_engagement=True,
                requires_charge_target=True,
                ignores_vertical_distance=False,
                ignores_models=False,
                ignores_terrain=False,
            ),
            MovementModePolicy(
                movement_mode=MovementMode.FLY_TAKE_TO_SKIES,
                may_transit_enemy_engagement=True,
                may_end_in_enemy_engagement=False,
                requires_charge_target=False,
                ignores_vertical_distance=True,
                ignores_models=True,
                ignores_terrain=True,
                movement_distance_modifier=-2.0,
            ),
        )
    )


def _terrain_feature_movement_policies_for_eleventh() -> tuple[TerrainFeatureMovementPolicy, ...]:
    unrestricted_keywords: tuple[str, ...] = ()
    ruins_through_keywords = (
        "BEAST",
        "BELISARIUS_CAWL",
        "IMPERIUM_PRIMARCH",
        "INFANTRY",
    )
    ruins_upper_floor_keywords = (
        "BEAST",
        "BELISARIUS_CAWL",
        "FLY",
        "IMPERIUM_PRIMARCH",
        "INFANTRY",
    )
    freely_moved_over_height_inches = 2.0
    return (
        TerrainFeatureMovementPolicy(
            terrain_feature_kind=TerrainFeatureKind.BARRICADE_AND_FUEL_PIPES,
            can_move_over=True,
            can_move_through=False,
            freely_moved_over_height_inches=freely_moved_over_height_inches,
            endpoint_support_policy=TerrainEndpointSupportPolicy.NOT_ALLOWED_ON_TOP,
            no_overhang_required=False,
            upper_floor_allowed_keywords=unrestricted_keywords,
            through_terrain_allowed_keywords=unrestricted_keywords,
            ground_floor_only_unless_keyword=False,
        ),
        TerrainFeatureMovementPolicy(
            terrain_feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
            can_move_over=True,
            can_move_through=False,
            freely_moved_over_height_inches=freely_moved_over_height_inches,
            endpoint_support_policy=TerrainEndpointSupportPolicy.NOT_ALLOWED_ON_TOP,
            no_overhang_required=False,
            upper_floor_allowed_keywords=unrestricted_keywords,
            through_terrain_allowed_keywords=unrestricted_keywords,
            ground_floor_only_unless_keyword=False,
        ),
        TerrainFeatureMovementPolicy(
            terrain_feature_kind=TerrainFeatureKind.CRATER_AND_RUBBLE,
            can_move_over=True,
            can_move_through=False,
            freely_moved_over_height_inches=freely_moved_over_height_inches,
            endpoint_support_policy=TerrainEndpointSupportPolicy.ALLOWED_ON_GROUND_FLOOR_ONLY,
            no_overhang_required=False,
            upper_floor_allowed_keywords=unrestricted_keywords,
            through_terrain_allowed_keywords=unrestricted_keywords,
            ground_floor_only_unless_keyword=False,
        ),
        TerrainFeatureMovementPolicy(
            terrain_feature_kind=TerrainFeatureKind.DEBRIS_AND_STATUARY,
            can_move_over=True,
            can_move_through=False,
            freely_moved_over_height_inches=freely_moved_over_height_inches,
            endpoint_support_policy=TerrainEndpointSupportPolicy.NOT_ALLOWED_ON_TOP,
            no_overhang_required=False,
            upper_floor_allowed_keywords=unrestricted_keywords,
            through_terrain_allowed_keywords=unrestricted_keywords,
            ground_floor_only_unless_keyword=False,
        ),
        TerrainFeatureMovementPolicy(
            terrain_feature_kind=TerrainFeatureKind.HILLS,
            can_move_over=True,
            can_move_through=False,
            freely_moved_over_height_inches=freely_moved_over_height_inches,
            endpoint_support_policy=TerrainEndpointSupportPolicy.ALLOWED_ON_TOP_WITH_NO_OVERHANG,
            no_overhang_required=True,
            upper_floor_allowed_keywords=unrestricted_keywords,
            through_terrain_allowed_keywords=unrestricted_keywords,
            ground_floor_only_unless_keyword=False,
        ),
        TerrainFeatureMovementPolicy(
            terrain_feature_kind=TerrainFeatureKind.HILLS_AND_SEALED_BUILDINGS,
            can_move_over=True,
            can_move_through=False,
            freely_moved_over_height_inches=freely_moved_over_height_inches,
            endpoint_support_policy=TerrainEndpointSupportPolicy.ALLOWED_ON_TOP_WITH_NO_OVERHANG,
            no_overhang_required=True,
            upper_floor_allowed_keywords=unrestricted_keywords,
            through_terrain_allowed_keywords=unrestricted_keywords,
            ground_floor_only_unless_keyword=False,
        ),
        TerrainFeatureMovementPolicy(
            terrain_feature_kind=TerrainFeatureKind.INDUSTRIAL_STRUCTURES,
            can_move_over=True,
            can_move_through=False,
            freely_moved_over_height_inches=freely_moved_over_height_inches,
            endpoint_support_policy=TerrainEndpointSupportPolicy.ALLOWED_ON_TOP_WITH_NO_OVERHANG,
            no_overhang_required=True,
            upper_floor_allowed_keywords=unrestricted_keywords,
            through_terrain_allowed_keywords=unrestricted_keywords,
            ground_floor_only_unless_keyword=False,
        ),
        TerrainFeatureMovementPolicy(
            terrain_feature_kind=TerrainFeatureKind.ARMOURED_CONTAINERS,
            can_move_over=True,
            can_move_through=False,
            freely_moved_over_height_inches=freely_moved_over_height_inches,
            endpoint_support_policy=TerrainEndpointSupportPolicy.ALLOWED_ON_TOP_WITH_NO_OVERHANG,
            no_overhang_required=True,
            upper_floor_allowed_keywords=unrestricted_keywords,
            through_terrain_allowed_keywords=unrestricted_keywords,
            ground_floor_only_unless_keyword=False,
        ),
        TerrainFeatureMovementPolicy(
            terrain_feature_kind=TerrainFeatureKind.SEALED_BUILDINGS,
            can_move_over=True,
            can_move_through=False,
            freely_moved_over_height_inches=freely_moved_over_height_inches,
            endpoint_support_policy=TerrainEndpointSupportPolicy.ALLOWED_ON_TOP_WITH_NO_OVERHANG,
            no_overhang_required=True,
            upper_floor_allowed_keywords=unrestricted_keywords,
            through_terrain_allowed_keywords=unrestricted_keywords,
            ground_floor_only_unless_keyword=False,
        ),
        TerrainFeatureMovementPolicy(
            terrain_feature_kind=TerrainFeatureKind.RUINS,
            can_move_over=True,
            can_move_through=False,
            freely_moved_over_height_inches=freely_moved_over_height_inches,
            endpoint_support_policy=(
                TerrainEndpointSupportPolicy.ALLOWED_ON_ANY_FLOOR_WITH_NO_OVERHANG
            ),
            no_overhang_required=True,
            upper_floor_allowed_keywords=ruins_upper_floor_keywords,
            through_terrain_allowed_keywords=ruins_through_keywords,
            ground_floor_only_unless_keyword=True,
        ),
        TerrainFeatureMovementPolicy(
            terrain_feature_kind=TerrainFeatureKind.WOODS,
            can_move_over=True,
            can_move_through=False,
            freely_moved_over_height_inches=freely_moved_over_height_inches,
            endpoint_support_policy=TerrainEndpointSupportPolicy.ALLOWED_ON_GROUND_FLOOR_ONLY,
            no_overhang_required=False,
            upper_floor_allowed_keywords=unrestricted_keywords,
            through_terrain_allowed_keywords=unrestricted_keywords,
            ground_floor_only_unless_keyword=False,
        ),
    )


def _terrain_feature_visibility_policies_for_eleventh(
    cover_policy: CoverPolicyDescriptor | None = None,
) -> tuple[TerrainFeatureVisibilityPolicy, ...]:
    resolved_cover_policy = (
        CoverPolicyDescriptor.warhammer_40000_eleventh_default()
        if cover_policy is None
        else cover_policy
    )
    physical_policy = tuple(
        TerrainFeatureVisibilityPolicy(
            terrain_feature_kind=feature_kind,
            line_of_sight_policy=LineOfSightPolicy.TRUE_LINE_OF_SIGHT,
            blocks_model_visibility_through_footprint=False,
            blocks_full_visibility_through_footprint=False,
            uses_true_los_when_observer_wholly_within_feature=False,
            uses_true_los_when_target_intersects_feature=False,
            aircraft_uses_true_los_through_feature=False,
            towering_uses_true_los_through_feature=False,
            towering_uses_true_los_when_wholly_within_feature=False,
            cover_policy=resolved_cover_policy,
        )
        for feature_kind in TerrainFeatureKind
        if feature_kind not in {TerrainFeatureKind.RUINS, TerrainFeatureKind.WOODS}
    )
    ruins_policy = TerrainFeatureVisibilityPolicy(
        terrain_feature_kind=TerrainFeatureKind.RUINS,
        line_of_sight_policy=LineOfSightPolicy.AREA_OBSCURING,
        blocks_model_visibility_through_footprint=True,
        blocks_full_visibility_through_footprint=True,
        uses_true_los_when_observer_wholly_within_feature=True,
        uses_true_los_when_target_intersects_feature=True,
        aircraft_uses_true_los_through_feature=True,
        towering_uses_true_los_through_feature=False,
        towering_uses_true_los_when_wholly_within_feature=True,
        cover_policy=resolved_cover_policy,
    )
    woods_policy = TerrainFeatureVisibilityPolicy(
        terrain_feature_kind=TerrainFeatureKind.WOODS,
        line_of_sight_policy=LineOfSightPolicy.DENSE_COVER,
        blocks_model_visibility_through_footprint=False,
        blocks_full_visibility_through_footprint=True,
        uses_true_los_when_observer_wholly_within_feature=True,
        uses_true_los_when_target_intersects_feature=False,
        aircraft_uses_true_los_through_feature=True,
        towering_uses_true_los_through_feature=True,
        towering_uses_true_los_when_wholly_within_feature=False,
        cover_policy=resolved_cover_policy,
    )
    return tuple(
        sorted(
            (*physical_policy, ruins_policy, woods_policy),
            key=lambda policy: policy.terrain_feature_kind.value,
        )
    )


def _descriptor_hash(payload: RulesetDescriptorPayload) -> str:
    clean_payload = dict(payload)
    clean_payload["descriptor_hash"] = ""
    encoded = json.dumps(clean_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_descriptor_hash(value: object) -> str:
    if type(value) is not str:
        raise RulesetDescriptorError("RulesetDescriptor descriptor_hash must be a string.")
    stripped = value.strip()
    if len(stripped) != 64:
        raise RulesetDescriptorError(
            "RulesetDescriptor descriptor_hash must be a SHA-256 hex digest."
        )
    if any(character not in "0123456789abcdef" for character in stripped):
        raise RulesetDescriptorError(
            "RulesetDescriptor descriptor_hash must be a lowercase SHA-256 hex digest."
        )
    return stripped


def _validate_descriptor_part(
    field_name: str,
    value: object,
    expected_type: type[object],
) -> None:
    if type(value) is not expected_type:
        raise RulesetDescriptorError(f"{field_name} must be {expected_type.__name__}.")


def _validate_movement_mode_policy(field_name: str, value: object) -> MovementModePolicy:
    if type(value) is not MovementModePolicy:
        raise RulesetDescriptorError(f"{field_name} must be a MovementModePolicy.")
    return value


def _validate_unique_movement_modes(movement_modes: tuple[MovementModePolicy, ...]) -> None:
    seen: set[MovementMode] = set()
    for movement_mode in movement_modes:
        if movement_mode.movement_mode in seen:
            raise RulesetDescriptorError("MovementPolicyDescriptor movement_modes must be unique.")
        seen.add(movement_mode.movement_mode)


def _validate_unique_anchor_kinds(anchor_kinds: tuple[ObjectiveAnchorKind, ...]) -> None:
    seen: set[ObjectiveAnchorKind] = set()
    for anchor_kind in anchor_kinds:
        if anchor_kind in seen:
            raise RulesetDescriptorError(
                "ObjectivePolicyDescriptor supported_anchor_kinds must be unique."
            )
        seen.add(anchor_kind)


def _validate_unique_setup_steps(steps: tuple[SetupStepKind, ...]) -> None:
    seen: set[SetupStepKind] = set()
    for step in steps:
        if step in seen:
            raise RulesetDescriptorError("SetupSequenceDescriptor steps must be unique.")
        seen.add(step)


def _validate_unique_battle_phases(phases: tuple[BattlePhaseKind, ...]) -> None:
    seen: set[BattlePhaseKind] = set()
    for phase in phases:
        if phase in seen:
            raise RulesetDescriptorError("BattlePhaseSequenceDescriptor phases must be unique.")
        seen.add(phase)


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise RulesetDescriptorError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise RulesetDescriptorError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))


def _validate_keyword_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise RulesetDescriptorError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in values:
        keyword = _validate_identifier(f"{field_name} value", value).upper()
        keyword = keyword.replace(" ", "_").replace("-", "_")
        if keyword in seen:
            raise RulesetDescriptorError(f"{field_name} must not contain duplicates.")
        seen.add(keyword)
        validated.append(keyword)
    return tuple(sorted(validated))


def _validate_terrain_feature_movement_policy_tuple(
    values: object,
) -> tuple[TerrainFeatureMovementPolicy, ...]:
    if type(values) is not tuple:
        raise RulesetDescriptorError("TerrainMovementPolicy feature_policies must be a tuple.")
    policies = tuple(
        _validate_terrain_feature_movement_policy("TerrainMovementPolicy feature_policy", value)
        for value in cast(tuple[object, ...], values)
    )
    if not policies:
        raise RulesetDescriptorError("TerrainMovementPolicy feature_policies must not be empty.")
    seen: set[TerrainFeatureKind] = set()
    for policy in policies:
        if policy.terrain_feature_kind in seen:
            raise RulesetDescriptorError("TerrainMovementPolicy feature_policies must be unique.")
        seen.add(policy.terrain_feature_kind)
    return tuple(sorted(policies, key=lambda policy: policy.terrain_feature_kind.value))


def _validate_terrain_feature_movement_policy(
    field_name: str,
    value: object,
) -> TerrainFeatureMovementPolicy:
    if type(value) is not TerrainFeatureMovementPolicy:
        raise RulesetDescriptorError(f"{field_name} must be a TerrainFeatureMovementPolicy.")
    return value


def _validate_terrain_feature_visibility_policy_tuple(
    values: object,
) -> tuple[TerrainFeatureVisibilityPolicy, ...]:
    if type(values) is not tuple:
        raise RulesetDescriptorError(
            "TerrainVisibilityPolicyDescriptor feature_policies must be a tuple."
        )
    policies = tuple(
        _validate_terrain_feature_visibility_policy(
            "TerrainVisibilityPolicyDescriptor feature_policy",
            value,
        )
        for value in cast(tuple[object, ...], values)
    )
    if not policies:
        raise RulesetDescriptorError(
            "TerrainVisibilityPolicyDescriptor feature_policies must not be empty."
        )
    seen: set[TerrainFeatureKind] = set()
    for policy in policies:
        if policy.terrain_feature_kind in seen:
            raise RulesetDescriptorError(
                "TerrainVisibilityPolicyDescriptor feature_policies must be unique."
            )
        seen.add(policy.terrain_feature_kind)
    return tuple(sorted(policies, key=lambda policy: policy.terrain_feature_kind.value))


def _validate_terrain_feature_visibility_policy(
    field_name: str,
    value: object,
) -> TerrainFeatureVisibilityPolicy:
    if type(value) is not TerrainFeatureVisibilityPolicy:
        raise RulesetDescriptorError(f"{field_name} must be a TerrainFeatureVisibilityPolicy.")
    return value


def _validate_source_date(value: object) -> str:
    if type(value) is date:
        return value.isoformat()
    return _validate_identifier("RulesetDescriptor source_date", value)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise RulesetDescriptorError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise RulesetDescriptorError(f"{field_name} must not be empty.")
    return stripped


def _validate_bool(field_name: str, value: object) -> None:
    if type(value) is not bool:
        raise RulesetDescriptorError(f"{field_name} must be a bool.")


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise RulesetDescriptorError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise RulesetDescriptorError(f"{field_name} must be finite.")
    return number


def _validate_non_negative_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number < 0.0:
        raise RulesetDescriptorError(f"{field_name} must not be negative.")
    return number


def _validate_positive_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number <= 0.0:
        raise RulesetDescriptorError(f"{field_name} must be greater than 0.")
    return number


def _validate_optional_positive_number(field_name: str, value: object | None) -> float | None:
    if value is None:
        return None
    number = _validate_finite_number(field_name, value)
    if number <= 0.0:
        raise RulesetDescriptorError(f"{field_name} must be greater than 0.")
    return number


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise RulesetDescriptorError(f"{field_name} must be an integer.")
    if value < 1:
        raise RulesetDescriptorError(f"{field_name} must be at least 1.")
    return value


def _validate_positive_int_tuple(field_name: str, values: object) -> tuple[int, ...]:
    if type(values) is not tuple:
        raise RulesetDescriptorError(f"{field_name} must be a tuple.")
    validated = tuple(
        _validate_positive_int(f"{field_name} value", value)
        for value in cast(tuple[object, ...], values)
    )
    seen: set[int] = set()
    for value in validated:
        if value in seen:
            raise RulesetDescriptorError(f"{field_name} must not contain duplicates.")
        seen.add(value)
    return tuple(sorted(validated))


def _validate_optional_positive_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_positive_int(field_name, value)
