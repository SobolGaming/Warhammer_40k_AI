from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset import RulesetEdition, RulesetError, ruleset_edition_from_token
from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
    RulesetDescriptorError,
    TerrainMovementPolicy,
    TerrainMovementPolicyPayload,
)
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    AbilityHandlerRegistry,
    movement_capability_flags_from_index,
)
from warhammer40k_core.engine.ability_catalog import eleventh_edition_ability_index
from warhammer40k_core.engine.battlefield_state import (
    ModelDisplacementKind,
    model_displacement_kind_from_token,
)
from warhammer40k_core.geometry.pathing import (
    PathValidationContext,
    PathWitness,
    TerrainPathLegalityContext,
)
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.volume import Model


class MovementLegalityError(ValueError):
    """Raised when movement legality inputs violate CORE V2 invariants."""


class MovementLegalityStatus(StrEnum):
    LEGAL = "legal"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


class MovementCapabilitySetPayload(TypedDict):
    ruleset_descriptor_hash: str
    keywords: list[str]
    has_fly: bool
    is_titanic: bool
    is_infantry: bool
    is_beast: bool
    is_vehicle: bool
    is_monster: bool
    is_walker: bool
    is_aircraft: bool
    is_hover: bool
    can_traverse_ruins_walls: bool
    can_move_through_models: bool
    can_move_through_terrain: bool
    ignores_vertical_distance: bool
    blocks_friendly_vehicle_monster_pass_through: bool


class EngagementMovementPolicyPayload(TypedDict):
    ruleset_descriptor_hash: str
    ruleset_edition: str
    movement_mode: str
    horizontal_inches: float
    vertical_inches: float
    may_transit_enemy_engagement: bool
    may_end_in_enemy_engagement: bool
    requires_charge_target: bool


class MovementLegalityContextPayload(TypedDict):
    ruleset_descriptor_hash: str
    movement_phase_action: str | None
    displacement_kind: str
    movement_mode: str
    capabilities: MovementCapabilitySetPayload
    engagement_policy: EngagementMovementPolicyPayload
    terrain_movement_policy: TerrainMovementPolicyPayload


class MovementLegalityResultPayload(TypedDict):
    status: str
    violation_code: str | None
    message: str | None


_FLY_TRANSIT_MOVEMENT_MODES = frozenset(
    {
        MovementMode.NORMAL,
        MovementMode.ADVANCE,
        MovementMode.FALL_BACK,
        MovementMode.FLY_TAKE_TO_SKIES,
    }
)

_VEHICLE_MONSTER_ENEMY_TRANSIT_MOVEMENT_MODES = frozenset(
    {
        MovementMode.NORMAL,
        MovementMode.ADVANCE,
    }
)


@dataclass(frozen=True, slots=True)
class MovementCapabilitySet:
    ruleset_descriptor_hash: str
    keywords: tuple[str, ...]
    has_fly: bool
    is_titanic: bool
    is_infantry: bool
    is_beast: bool
    is_vehicle: bool
    is_monster: bool
    is_walker: bool
    is_aircraft: bool
    is_hover: bool
    can_traverse_ruins_walls: bool
    can_move_through_models: bool
    can_move_through_terrain: bool
    ignores_vertical_distance: bool
    blocks_friendly_vehicle_monster_pass_through: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "MovementCapabilitySet ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "keywords",
            _validate_keyword_tuple("MovementCapabilitySet keywords", self.keywords),
        )
        for field_name, value in (
            ("has_fly", self.has_fly),
            ("is_titanic", self.is_titanic),
            ("is_infantry", self.is_infantry),
            ("is_beast", self.is_beast),
            ("is_vehicle", self.is_vehicle),
            ("is_monster", self.is_monster),
            ("is_walker", self.is_walker),
            ("is_aircraft", self.is_aircraft),
            ("is_hover", self.is_hover),
            ("can_traverse_ruins_walls", self.can_traverse_ruins_walls),
            ("can_move_through_models", self.can_move_through_models),
            ("can_move_through_terrain", self.can_move_through_terrain),
            ("ignores_vertical_distance", self.ignores_vertical_distance),
            (
                "blocks_friendly_vehicle_monster_pass_through",
                self.blocks_friendly_vehicle_monster_pass_through,
            ),
        ):
            _validate_bool(f"MovementCapabilitySet {field_name}", value)

    @classmethod
    def from_keywords(
        cls,
        keywords: tuple[str, ...],
        *,
        ruleset_descriptor: object,
        ability_index: AbilityCatalogIndex | None = None,
        ability_registry: AbilityHandlerRegistry | None = None,
    ) -> Self:
        descriptor = _validate_ruleset_descriptor(ruleset_descriptor)
        normalized_keywords = _validate_keyword_tuple(
            "MovementCapabilitySet keywords",
            keywords,
        )
        resolved_ability_index = (
            eleventh_edition_ability_index() if ability_index is None else ability_index
        )
        flags = set(
            movement_capability_flags_from_index(
                index=resolved_ability_index,
                keywords=normalized_keywords,
                registry=ability_registry,
            )
        )
        has_fly = "has_fly" in flags
        is_titanic = "is_titanic" in flags
        is_infantry = "is_infantry" in flags
        is_beast = "is_beast" in flags
        is_vehicle = "is_vehicle" in flags
        is_monster = "is_monster" in flags
        can_traverse_ruins_walls = "can_traverse_ruins_walls" in flags
        can_move_through_models = has_fly and descriptor.fly_policy.may_move_through_models
        can_move_through_terrain = can_traverse_ruins_walls or (
            has_fly and descriptor.fly_policy.may_move_through_terrain
        )
        ignores_vertical_distance = has_fly and descriptor.fly_policy.ignores_vertical_distance
        return cls(
            ruleset_descriptor_hash=descriptor.descriptor_hash,
            keywords=normalized_keywords,
            has_fly=has_fly,
            is_titanic=is_titanic,
            is_infantry=is_infantry,
            is_beast=is_beast,
            is_vehicle=is_vehicle,
            is_monster=is_monster,
            is_walker="is_walker" in flags,
            is_aircraft="is_aircraft" in flags,
            is_hover="is_hover" in flags,
            can_traverse_ruins_walls=can_traverse_ruins_walls,
            can_move_through_models=can_move_through_models,
            can_move_through_terrain=can_move_through_terrain,
            ignores_vertical_distance=ignores_vertical_distance,
            blocks_friendly_vehicle_monster_pass_through=(
                "blocks_friendly_vehicle_monster_pass_through" in flags
            ),
        )

    def to_payload(self) -> MovementCapabilitySetPayload:
        return {
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "keywords": list(self.keywords),
            "has_fly": self.has_fly,
            "is_titanic": self.is_titanic,
            "is_infantry": self.is_infantry,
            "is_beast": self.is_beast,
            "is_vehicle": self.is_vehicle,
            "is_monster": self.is_monster,
            "is_walker": self.is_walker,
            "is_aircraft": self.is_aircraft,
            "is_hover": self.is_hover,
            "can_traverse_ruins_walls": self.can_traverse_ruins_walls,
            "can_move_through_models": self.can_move_through_models,
            "can_move_through_terrain": self.can_move_through_terrain,
            "ignores_vertical_distance": self.ignores_vertical_distance,
            "blocks_friendly_vehicle_monster_pass_through": (
                self.blocks_friendly_vehicle_monster_pass_through
            ),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise MovementLegalityError("MovementCapabilitySet payload must be a mapping.")
        raw_payload = cast(MovementCapabilitySetPayload, payload)
        return cls(
            ruleset_descriptor_hash=raw_payload["ruleset_descriptor_hash"],
            keywords=tuple(raw_payload["keywords"]),
            has_fly=raw_payload["has_fly"],
            is_titanic=raw_payload["is_titanic"],
            is_infantry=raw_payload["is_infantry"],
            is_beast=raw_payload["is_beast"],
            is_vehicle=raw_payload["is_vehicle"],
            is_monster=raw_payload["is_monster"],
            is_walker=raw_payload["is_walker"],
            is_aircraft=raw_payload["is_aircraft"],
            is_hover=raw_payload["is_hover"],
            can_traverse_ruins_walls=raw_payload["can_traverse_ruins_walls"],
            can_move_through_models=raw_payload["can_move_through_models"],
            can_move_through_terrain=raw_payload["can_move_through_terrain"],
            ignores_vertical_distance=raw_payload["ignores_vertical_distance"],
            blocks_friendly_vehicle_monster_pass_through=raw_payload[
                "blocks_friendly_vehicle_monster_pass_through"
            ],
        )


@dataclass(frozen=True, slots=True)
class EngagementMovementPolicy:
    ruleset_descriptor_hash: str
    ruleset_edition: RulesetEdition
    movement_mode: MovementMode
    horizontal_inches: float
    vertical_inches: float
    may_transit_enemy_engagement: bool
    may_end_in_enemy_engagement: bool
    requires_charge_target: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "EngagementMovementPolicy ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        if type(self.ruleset_edition) is not RulesetEdition:
            raise MovementLegalityError(
                "EngagementMovementPolicy ruleset_edition must be a RulesetEdition."
            )
        object.__setattr__(self, "movement_mode", movement_mode_from_token(self.movement_mode))
        object.__setattr__(
            self,
            "horizontal_inches",
            _validate_non_negative_number(
                "EngagementMovementPolicy horizontal_inches",
                self.horizontal_inches,
            ),
        )
        object.__setattr__(
            self,
            "vertical_inches",
            _validate_non_negative_number(
                "EngagementMovementPolicy vertical_inches",
                self.vertical_inches,
            ),
        )
        _validate_bool(
            "EngagementMovementPolicy may_transit_enemy_engagement",
            self.may_transit_enemy_engagement,
        )
        _validate_bool(
            "EngagementMovementPolicy may_end_in_enemy_engagement",
            self.may_end_in_enemy_engagement,
        )
        _validate_bool(
            "EngagementMovementPolicy requires_charge_target", self.requires_charge_target
        )

    @classmethod
    def from_ruleset_descriptor(
        cls,
        ruleset_descriptor: object,
        *,
        movement_mode: object,
    ) -> Self:
        descriptor = _validate_ruleset_descriptor(ruleset_descriptor)
        mode = movement_mode_from_token(movement_mode)
        try:
            movement_policy = descriptor.movement_policy.policy_for_mode(mode)
        except RulesetDescriptorError as exc:
            raise MovementLegalityError(
                f"RulesetDescriptor does not define movement legality for {mode.value}."
            ) from exc
        return cls(
            ruleset_descriptor_hash=descriptor.descriptor_hash,
            ruleset_edition=descriptor.ruleset_id.edition,
            movement_mode=mode,
            horizontal_inches=descriptor.engagement_policy.horizontal_inches,
            vertical_inches=descriptor.engagement_policy.vertical_inches,
            may_transit_enemy_engagement=movement_policy.may_transit_enemy_engagement,
            may_end_in_enemy_engagement=movement_policy.may_end_in_enemy_engagement,
            requires_charge_target=movement_policy.requires_charge_target,
        )

    def enemy_engagement_at(
        self,
        *,
        horizontal_inches: object,
        vertical_inches: object,
    ) -> bool:
        horizontal = _validate_non_negative_number(
            "EngagementMovementPolicy horizontal distance",
            horizontal_inches,
        )
        vertical = _validate_non_negative_number(
            "EngagementMovementPolicy vertical distance",
            vertical_inches,
        )
        return horizontal <= self.horizontal_inches and vertical <= self.vertical_inches

    def to_payload(self) -> EngagementMovementPolicyPayload:
        return {
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "ruleset_edition": self.ruleset_edition.value,
            "movement_mode": self.movement_mode.value,
            "horizontal_inches": self.horizontal_inches,
            "vertical_inches": self.vertical_inches,
            "may_transit_enemy_engagement": self.may_transit_enemy_engagement,
            "may_end_in_enemy_engagement": self.may_end_in_enemy_engagement,
            "requires_charge_target": self.requires_charge_target,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise MovementLegalityError("EngagementMovementPolicy payload must be a mapping.")
        raw_payload = cast(EngagementMovementPolicyPayload, payload)
        return cls(
            ruleset_descriptor_hash=raw_payload["ruleset_descriptor_hash"],
            ruleset_edition=ruleset_edition_from_token_for_movement_legality(
                raw_payload["ruleset_edition"]
            ),
            movement_mode=movement_mode_from_token(raw_payload["movement_mode"]),
            horizontal_inches=raw_payload["horizontal_inches"],
            vertical_inches=raw_payload["vertical_inches"],
            may_transit_enemy_engagement=raw_payload["may_transit_enemy_engagement"],
            may_end_in_enemy_engagement=raw_payload["may_end_in_enemy_engagement"],
            requires_charge_target=raw_payload["requires_charge_target"],
        )


@dataclass(frozen=True, slots=True)
class MovementLegalityContext:
    ruleset_descriptor_hash: str
    movement_phase_action: str | None
    displacement_kind: ModelDisplacementKind
    movement_mode: MovementMode
    capabilities: MovementCapabilitySet
    engagement_policy: EngagementMovementPolicy
    terrain_movement_policy: TerrainMovementPolicy

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "MovementLegalityContext ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "movement_phase_action",
            _validate_optional_movement_phase_action(self.movement_phase_action),
        )
        object.__setattr__(
            self,
            "displacement_kind",
            model_displacement_kind_from_token(self.displacement_kind),
        )
        object.__setattr__(self, "movement_mode", movement_mode_from_token(self.movement_mode))
        if type(self.capabilities) is not MovementCapabilitySet:
            raise MovementLegalityError(
                "MovementLegalityContext capabilities must be a MovementCapabilitySet."
            )
        if type(self.engagement_policy) is not EngagementMovementPolicy:
            raise MovementLegalityError(
                "MovementLegalityContext engagement_policy must be an EngagementMovementPolicy."
            )
        if type(self.terrain_movement_policy) is not TerrainMovementPolicy:
            raise MovementLegalityError(
                "MovementLegalityContext terrain_movement_policy must be a TerrainMovementPolicy."
            )
        if self.capabilities.ruleset_descriptor_hash != self.ruleset_descriptor_hash:
            raise MovementLegalityError(
                "MovementLegalityContext capabilities must match ruleset_descriptor_hash."
            )
        if self.engagement_policy.ruleset_descriptor_hash != self.ruleset_descriptor_hash:
            raise MovementLegalityError(
                "MovementLegalityContext engagement_policy must match ruleset_descriptor_hash."
            )
        if self.engagement_policy.movement_mode is not self.movement_mode:
            raise MovementLegalityError(
                "MovementLegalityContext engagement_policy must match movement_mode."
            )

    @classmethod
    def from_keywords(
        cls,
        *,
        keywords: tuple[str, ...],
        ruleset_descriptor: object,
        movement_mode: object,
        movement_phase_action: object | None,
        displacement_kind: object,
        ability_index: AbilityCatalogIndex | None = None,
        ability_registry: AbilityHandlerRegistry | None = None,
    ) -> Self:
        descriptor = _validate_ruleset_descriptor(ruleset_descriptor)
        mode = movement_mode_from_token(movement_mode)
        return cls(
            ruleset_descriptor_hash=descriptor.descriptor_hash,
            movement_phase_action=_validate_optional_movement_phase_action(movement_phase_action),
            displacement_kind=model_displacement_kind_from_token(displacement_kind),
            movement_mode=mode,
            capabilities=MovementCapabilitySet.from_keywords(
                keywords,
                ruleset_descriptor=descriptor,
                ability_index=ability_index,
                ability_registry=ability_registry,
            ),
            engagement_policy=EngagementMovementPolicy.from_ruleset_descriptor(
                descriptor,
                movement_mode=mode,
            ),
            terrain_movement_policy=descriptor.terrain_movement_policy,
        )

    def validate_end_position_enemy_engagement(
        self,
        *,
        enemy_horizontal_distance_inches: object,
        enemy_vertical_distance_inches: object,
    ) -> MovementLegalityResult:
        if not self.engagement_policy.enemy_engagement_at(
            horizontal_inches=enemy_horizontal_distance_inches,
            vertical_inches=enemy_vertical_distance_inches,
        ):
            return MovementLegalityResult.legal()
        if self.engagement_policy.may_end_in_enemy_engagement:
            return MovementLegalityResult.legal()
        return MovementLegalityResult.invalid(
            violation_code="enemy_engagement_range_end_forbidden",
            message=(
                f"{self.movement_mode.value} cannot end within enemy Engagement Range "
                f"under {self.engagement_policy.ruleset_edition.value} policy."
            ),
        )

    def validate_path_transits_enemy_engagement(
        self,
        *,
        enemy_horizontal_distance_inches: object,
        enemy_vertical_distance_inches: object,
    ) -> MovementLegalityResult:
        if not self.engagement_policy.enemy_engagement_at(
            horizontal_inches=enemy_horizontal_distance_inches,
            vertical_inches=enemy_vertical_distance_inches,
        ):
            return MovementLegalityResult.legal()
        if self.engagement_policy.may_transit_enemy_engagement or self._fly_transit_applies():
            return MovementLegalityResult.legal()
        return MovementLegalityResult.invalid(
            violation_code="enemy_engagement_range_transit_forbidden",
            message=(
                f"{self.movement_mode.value} cannot move through enemy Engagement Range "
                f"under {self.engagement_policy.ruleset_edition.value} policy."
            ),
        )

    def to_path_validation_context(
        self,
        *,
        moving_model: Model,
        witness: PathWitness,
        battlefield_width_inches: float,
        battlefield_depth_inches: float,
        friendly_models: tuple[Model, ...] = (),
        enemy_models: tuple[Model, ...] = (),
        terrain: tuple[TerrainVolume, ...] = (),
        friendly_vehicle_monster_model_ids: tuple[str, ...] = (),
        enemy_vehicle_monster_model_ids: tuple[str, ...] = (),
        aircraft_model_ids: tuple[str, ...] = (),
        sample_interval_inches: float = 0.5,
        movement_distance_budget_inches: float | None = None,
    ) -> PathValidationContext:
        fly_transit_applies = self._fly_transit_applies()
        vehicle_monster_enemy_transit_applies = (
            self.capabilities.is_vehicle or self.capabilities.is_monster
        ) and self.movement_mode in _VEHICLE_MONSTER_ENEMY_TRANSIT_MOVEMENT_MODES
        may_transit_enemy_models = (
            (self.capabilities.can_move_through_models and fly_transit_applies)
            or self.movement_mode is MovementMode.FALL_BACK
            or vehicle_monster_enemy_transit_applies
        )
        may_transit_enemy_engagement = (
            self.engagement_policy.may_transit_enemy_engagement or fly_transit_applies
        )
        friendly_vehicle_monster_blockers = friendly_vehicle_monster_model_ids
        if not self.capabilities.blocks_friendly_vehicle_monster_pass_through or (
            fly_transit_applies and self.capabilities.can_move_through_models
        ):
            friendly_vehicle_monster_blockers = ()
        enemy_vehicle_monster_blockers: tuple[str, ...] = ()
        if vehicle_monster_enemy_transit_applies and not (
            fly_transit_applies and self.capabilities.can_move_through_models
        ):
            enemy_vehicle_monster_blockers = enemy_vehicle_monster_model_ids
        return PathValidationContext(
            moving_model=moving_model,
            witness=witness,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
            friendly_models=friendly_models,
            enemy_models=enemy_models,
            terrain=terrain,
            friendly_vehicle_monster_model_ids=friendly_vehicle_monster_blockers,
            enemy_vehicle_monster_model_ids=enemy_vehicle_monster_blockers,
            aircraft_model_ids=aircraft_model_ids,
            may_transit_enemy_models=may_transit_enemy_models,
            may_transit_enemy_engagement=may_transit_enemy_engagement,
            may_end_in_enemy_engagement=self.engagement_policy.may_end_in_enemy_engagement,
            enemy_engagement_horizontal_inches=self.engagement_policy.horizontal_inches,
            enemy_engagement_vertical_inches=self.engagement_policy.vertical_inches,
            sample_interval_inches=sample_interval_inches,
            movement_distance_budget_inches=movement_distance_budget_inches,
        )

    def to_terrain_path_legality_context(
        self,
        *,
        moving_model: Model,
        witness: PathWitness,
        terrain: tuple[TerrainVolume, ...] = (),
        terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
        contact_footprint_available: bool = True,
        sample_interval_inches: float = 0.5,
    ) -> TerrainPathLegalityContext:
        return TerrainPathLegalityContext(
            moving_model=moving_model,
            witness=witness,
            terrain=terrain,
            terrain_movement_policy=self.terrain_movement_policy,
            terrain_features=terrain_features,
            movement_keywords=self.capabilities.keywords,
            contact_footprint_available=contact_footprint_available,
            can_traverse_ruins_walls=self.capabilities.can_traverse_ruins_walls,
            can_move_through_terrain=self.capabilities.can_move_through_terrain,
            has_fly=self.capabilities.has_fly,
            sample_interval_inches=sample_interval_inches,
        )

    def _fly_transit_applies(self) -> bool:
        return self.capabilities.has_fly and self.movement_mode in _FLY_TRANSIT_MOVEMENT_MODES

    def to_payload(self) -> MovementLegalityContextPayload:
        return {
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "movement_phase_action": self.movement_phase_action,
            "displacement_kind": self.displacement_kind.value,
            "movement_mode": self.movement_mode.value,
            "capabilities": self.capabilities.to_payload(),
            "engagement_policy": self.engagement_policy.to_payload(),
            "terrain_movement_policy": self.terrain_movement_policy.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise MovementLegalityError("MovementLegalityContext payload must be a mapping.")
        raw_payload = cast(MovementLegalityContextPayload, payload)
        return cls(
            ruleset_descriptor_hash=raw_payload["ruleset_descriptor_hash"],
            movement_phase_action=raw_payload["movement_phase_action"],
            displacement_kind=model_displacement_kind_from_token(raw_payload["displacement_kind"]),
            movement_mode=movement_mode_from_token(raw_payload["movement_mode"]),
            capabilities=MovementCapabilitySet.from_payload(raw_payload["capabilities"]),
            engagement_policy=EngagementMovementPolicy.from_payload(
                raw_payload["engagement_policy"]
            ),
            terrain_movement_policy=TerrainMovementPolicy.from_payload(
                raw_payload["terrain_movement_policy"]
            ),
        )


@dataclass(frozen=True, slots=True)
class MovementLegalityResult:
    status: MovementLegalityStatus
    violation_code: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", movement_legality_status_from_token(self.status))
        object.__setattr__(
            self,
            "violation_code",
            _validate_optional_identifier(
                "MovementLegalityResult violation_code",
                self.violation_code,
            ),
        )
        object.__setattr__(
            self,
            "message",
            _validate_optional_identifier("MovementLegalityResult message", self.message),
        )
        if self.status is MovementLegalityStatus.LEGAL and (
            self.violation_code is not None or self.message is not None
        ):
            raise MovementLegalityError("Legal MovementLegalityResult must not include violations.")
        if self.status is not MovementLegalityStatus.LEGAL and self.violation_code is None:
            raise MovementLegalityError("Invalid movement legality results require violation_code.")

    @classmethod
    def legal(cls) -> Self:
        return cls(status=MovementLegalityStatus.LEGAL)

    @classmethod
    def invalid(cls, *, violation_code: str, message: str) -> Self:
        return cls(
            status=MovementLegalityStatus.INVALID,
            violation_code=violation_code,
            message=message,
        )

    @classmethod
    def unsupported(cls, *, violation_code: str, message: str) -> Self:
        return cls(
            status=MovementLegalityStatus.UNSUPPORTED,
            violation_code=violation_code,
            message=message,
        )

    @property
    def is_legal(self) -> bool:
        return self.status is MovementLegalityStatus.LEGAL

    def to_payload(self) -> MovementLegalityResultPayload:
        return {
            "status": self.status.value,
            "violation_code": self.violation_code,
            "message": self.message,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise MovementLegalityError("MovementLegalityResult payload must be a mapping.")
        raw_payload = cast(MovementLegalityResultPayload, payload)
        return cls(
            status=movement_legality_status_from_token(raw_payload["status"]),
            violation_code=raw_payload["violation_code"],
            message=raw_payload["message"],
        )


def movement_mode_from_token(token: object) -> MovementMode:
    if type(token) is MovementMode:
        return token
    if type(token) is not str:
        raise MovementLegalityError("MovementMode token must be a string.")
    try:
        return MovementMode(token)
    except ValueError as exc:
        raise MovementLegalityError(f"Unsupported MovementMode token: {token}.") from exc


def movement_legality_status_from_token(token: object) -> MovementLegalityStatus:
    if type(token) is MovementLegalityStatus:
        return token
    if type(token) is not str:
        raise MovementLegalityError("MovementLegalityStatus token must be a string.")
    try:
        return MovementLegalityStatus(token)
    except ValueError as exc:
        raise MovementLegalityError(f"Unsupported MovementLegalityStatus token: {token}.") from exc


def ruleset_edition_from_token_for_movement_legality(token: object) -> RulesetEdition:
    try:
        return ruleset_edition_from_token(token)
    except RulesetError as exc:
        raise MovementLegalityError("Unsupported ruleset edition token.") from exc


def _validate_ruleset_descriptor(value: object) -> RulesetDescriptor:
    if type(value) is not RulesetDescriptor:
        raise MovementLegalityError("Movement legality requires an explicit RulesetDescriptor.")
    return value


def _validate_optional_movement_phase_action(value: object | None) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        value = getattr(value, "value", None)
    if type(value) is not str:
        raise MovementLegalityError("movement_phase_action must be None or a string token.")
    action = value.strip()
    if action not in {"remain_stationary", "normal_move", "advance", "fall_back"}:
        raise MovementLegalityError(f"Unsupported movement_phase_action token: {value}.")
    return action


def _validate_keyword_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise MovementLegalityError(f"{field_name} must be a tuple.")
    keywords: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        keyword = _validate_keyword(f"{field_name} keyword", value)
        if keyword in seen:
            raise MovementLegalityError(f"{field_name} must not contain duplicate keywords.")
        seen.add(keyword)
        keywords.append(keyword)
    return tuple(sorted(keywords))


def _validate_keyword(field_name: str, value: object) -> str:
    identifier = _validate_identifier(field_name, value)
    return identifier.upper().replace(" ", "_").replace("-", "_")


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise MovementLegalityError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise MovementLegalityError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_bool(field_name: str, value: object) -> None:
    if type(value) is not bool:
        raise MovementLegalityError(f"{field_name} must be a bool.")


def _validate_non_negative_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise MovementLegalityError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise MovementLegalityError(f"{field_name} must be finite.")
    if number < 0.0:
        raise MovementLegalityError(f"{field_name} must not be negative.")
    return number
