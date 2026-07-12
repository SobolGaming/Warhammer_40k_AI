from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    CoverEffect,
    LineOfSightPolicy,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import (
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    SpatialIndexState,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.shooting_selection_range import (
    attacker_geometry_models as _attacker_geometry_models,
)
from warhammer40k_core.engine.shooting_selection_range import (
    geometry_models_for_unit_placement as _geometry_models_for_unit_placement,
)
from warhammer40k_core.engine.shooting_selection_range import (
    geometry_models_for_unit_placements as _geometry_models_for_unit_placements,
)
from warhammer40k_core.engine.shooting_selection_range import (
    target_in_range_model_ids as _target_in_range_model_ids,
)
from warhammer40k_core.engine.shooting_selection_range import (
    target_within_shooting_selection_range,
)
from warhammer40k_core.engine.shooting_selection_range import (
    unit_placement_or_none as _unit_placement_or_none,
)
from warhammer40k_core.engine.shooting_selection_range import (
    unit_placements_for_rules_unit_or_none as _unit_placements_for_rules_unit_or_none,
)
from warhammer40k_core.engine.shooting_types import ShootingType, validate_shooting_type_tuple
from warhammer40k_core.engine.unit_abilities import unit_has_lone_operative, unit_has_stealth
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import (
    HUNTER_RULE_ID,
    INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
    INDIRECT_FIRE_NO_VISIBLE_RULE_ID,
    has_close_quarters_weapon_keyword,
    has_weapon_keyword,
    hunter_target_allowed,
)
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.visibility import (
    BenefitOfCoverResult,
    LineOfSightWitness,
    LineOfSightWitnessPayload,
    TerrainVisibilityContext,
)
from warhammer40k_core.geometry.volume import Model

BENEFIT_OF_COVER_RULE_ID = "core-rules:benefit-of-cover"
BIG_GUNS_NEVER_TIRE_RULE_ID = "big_guns_never_tire"
FORTIFICATION_ENGAGEMENT_RULE_ID = "core-rules:fortification-engagement"
LONE_OPERATIVE_RULE_ID = "lone_operative"
STEALTH_RULE_ID = "stealth"
PLUNGING_FIRE_RULE_ID = "core-rules:plunging-fire"
PLUNGING_FIRE_TERRAIN_HEIGHT_INCHES = 3.0
PLUNGING_FIRE_TOWERING_RANGE_INCHES = 12.0
_GROUND_LEVEL_EPSILON = 1e-9


class ShootingTargetViolationCode(StrEnum):
    MELEE_WEAPON = "melee_weapon"
    NOT_ENEMY_UNIT = "not_enemy_unit"
    TARGET_NOT_PLACED = "target_not_placed"
    OUT_OF_RANGE = "out_of_range"
    OUTSIDE_DETECTION_RANGE = "outside_detection_range"
    NOT_VISIBLE = "not_visible"
    LONE_OPERATIVE = "lone_operative"
    LOCKED_IN_COMBAT = "locked_in_combat"
    HUNTER_TARGET_KEYWORD_MISMATCH = "hunter_target_keyword_mismatch"
    RUNTIME_TARGET_RESTRICTION = "runtime_target_restriction"


class ShootingTargetCandidatePayload(TypedDict):
    attacker_unit_instance_id: str
    weapon_profile_id: str
    target_unit_instance_id: str
    is_legal: bool
    violation_code: str | None
    message: str | None
    observer_model_id: str | None
    target_visible_model_ids: list[str]
    target_in_range_model_ids: list[str]
    line_of_sight_witness: LineOfSightWitnessPayload | None
    visibility_cache_key: str
    shooting_types: list[str]
    hit_roll_modifier: int
    targeting_rule_ids: list[str]


@dataclass(frozen=True, slots=True)
class ShootingTargetCandidate:
    attacker_unit_instance_id: str
    weapon_profile_id: str
    target_unit_instance_id: str
    is_legal: bool
    violation_code: ShootingTargetViolationCode | None
    message: str | None
    observer_model_id: str | None
    target_visible_model_ids: tuple[str, ...]
    target_in_range_model_ids: tuple[str, ...]
    line_of_sight_witness: LineOfSightWitness | None
    visibility_cache_key: str
    shooting_types: tuple[ShootingType, ...] = ()
    hit_roll_modifier: int = 0
    targeting_rule_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attacker_unit_instance_id",
            _validate_identifier(
                "ShootingTargetCandidate attacker_unit_instance_id",
                self.attacker_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "weapon_profile_id",
            _validate_identifier(
                "ShootingTargetCandidate weapon_profile_id",
                self.weapon_profile_id,
            ),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "ShootingTargetCandidate target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        if type(self.is_legal) is not bool:
            raise GameLifecycleError("ShootingTargetCandidate is_legal must be a bool.")
        object.__setattr__(
            self,
            "violation_code",
            shooting_target_violation_code_from_token(self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_optional_string("ShootingTargetCandidate message", self.message),
        )
        object.__setattr__(
            self,
            "observer_model_id",
            _validate_optional_identifier(
                "ShootingTargetCandidate observer_model_id",
                self.observer_model_id,
            ),
        )
        object.__setattr__(
            self,
            "target_visible_model_ids",
            _validate_identifier_tuple(
                "ShootingTargetCandidate target_visible_model_ids",
                self.target_visible_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "target_in_range_model_ids",
            _validate_identifier_tuple(
                "ShootingTargetCandidate target_in_range_model_ids",
                self.target_in_range_model_ids,
            ),
        )
        if self.line_of_sight_witness is not None and type(self.line_of_sight_witness) is not (
            LineOfSightWitness
        ):
            raise GameLifecycleError(
                "ShootingTargetCandidate line_of_sight_witness must be LineOfSightWitness."
            )
        object.__setattr__(
            self,
            "visibility_cache_key",
            _validate_identifier(
                "ShootingTargetCandidate visibility_cache_key",
                self.visibility_cache_key,
            ),
        )
        object.__setattr__(
            self,
            "shooting_types",
            validate_shooting_type_tuple(
                "ShootingTargetCandidate shooting_types",
                self.shooting_types,
            ),
        )
        if type(self.hit_roll_modifier) is not int:
            raise GameLifecycleError("ShootingTargetCandidate hit_roll_modifier must be an int.")
        object.__setattr__(
            self,
            "targeting_rule_ids",
            _validate_identifier_tuple(
                "ShootingTargetCandidate targeting_rule_ids",
                self.targeting_rule_ids,
            ),
        )
        if self.is_legal and self.violation_code is not None:
            raise GameLifecycleError("Legal ShootingTargetCandidate must not have violation_code.")
        if not self.is_legal and self.violation_code is None:
            raise GameLifecycleError("Illegal ShootingTargetCandidate requires violation_code.")
        if self.is_legal and self.line_of_sight_witness is None:
            raise GameLifecycleError("Legal ShootingTargetCandidate requires LoS evidence.")
        if self.is_legal and not self.shooting_types:
            raise GameLifecycleError("Legal ShootingTargetCandidate requires shooting_types.")
        if not self.is_legal and self.shooting_types:
            raise GameLifecycleError(
                "Illegal ShootingTargetCandidate must not have shooting_types."
            )

    @classmethod
    def legal(
        cls,
        *,
        attacker_unit_instance_id: str,
        weapon_profile_id: str,
        target_unit_instance_id: str,
        observer_model_id: str,
        target_visible_model_ids: tuple[str, ...],
        target_in_range_model_ids: tuple[str, ...],
        line_of_sight_witness: LineOfSightWitness,
        visibility_cache_key: str,
        shooting_types: tuple[ShootingType, ...],
        hit_roll_modifier: int = 0,
        targeting_rule_ids: tuple[str, ...] = (),
    ) -> Self:
        return cls(
            attacker_unit_instance_id=attacker_unit_instance_id,
            weapon_profile_id=weapon_profile_id,
            target_unit_instance_id=target_unit_instance_id,
            is_legal=True,
            violation_code=None,
            message=None,
            observer_model_id=observer_model_id,
            target_visible_model_ids=target_visible_model_ids,
            target_in_range_model_ids=target_in_range_model_ids,
            line_of_sight_witness=line_of_sight_witness,
            visibility_cache_key=visibility_cache_key,
            shooting_types=shooting_types,
            hit_roll_modifier=hit_roll_modifier,
            targeting_rule_ids=targeting_rule_ids,
        )

    @classmethod
    def invalid(
        cls,
        *,
        attacker_unit_instance_id: str,
        weapon_profile_id: str,
        target_unit_instance_id: str,
        violation_code: ShootingTargetViolationCode,
        message: str,
        visibility_cache_key: str,
        target_visible_model_ids: tuple[str, ...] = (),
        target_in_range_model_ids: tuple[str, ...] = (),
        line_of_sight_witness: LineOfSightWitness | None = None,
        observer_model_id: str | None = None,
        hit_roll_modifier: int = 0,
        targeting_rule_ids: tuple[str, ...] = (),
    ) -> Self:
        return cls(
            attacker_unit_instance_id=attacker_unit_instance_id,
            weapon_profile_id=weapon_profile_id,
            target_unit_instance_id=target_unit_instance_id,
            is_legal=False,
            violation_code=violation_code,
            message=message,
            observer_model_id=observer_model_id,
            target_visible_model_ids=target_visible_model_ids,
            target_in_range_model_ids=target_in_range_model_ids,
            line_of_sight_witness=line_of_sight_witness,
            visibility_cache_key=visibility_cache_key,
            hit_roll_modifier=hit_roll_modifier,
            targeting_rule_ids=targeting_rule_ids,
        )

    def to_payload(self) -> ShootingTargetCandidatePayload:
        return {
            "attacker_unit_instance_id": self.attacker_unit_instance_id,
            "weapon_profile_id": self.weapon_profile_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "is_legal": self.is_legal,
            "violation_code": None if self.violation_code is None else self.violation_code.value,
            "message": self.message,
            "observer_model_id": self.observer_model_id,
            "target_visible_model_ids": list(self.target_visible_model_ids),
            "target_in_range_model_ids": list(self.target_in_range_model_ids),
            "line_of_sight_witness": (
                None
                if self.line_of_sight_witness is None
                else self.line_of_sight_witness.to_payload()
            ),
            "visibility_cache_key": self.visibility_cache_key,
            "shooting_types": [shooting_type.value for shooting_type in self.shooting_types],
            "hit_roll_modifier": self.hit_roll_modifier,
            "targeting_rule_ids": list(self.targeting_rule_ids),
        }

    @classmethod
    def from_payload(cls, payload: ShootingTargetCandidatePayload) -> Self:
        witness_payload = payload["line_of_sight_witness"]
        return cls(
            attacker_unit_instance_id=payload["attacker_unit_instance_id"],
            weapon_profile_id=payload["weapon_profile_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            is_legal=payload["is_legal"],
            violation_code=shooting_target_violation_code_from_token(payload["violation_code"]),
            message=payload["message"],
            observer_model_id=payload["observer_model_id"],
            target_visible_model_ids=tuple(payload["target_visible_model_ids"]),
            target_in_range_model_ids=tuple(payload["target_in_range_model_ids"]),
            line_of_sight_witness=(
                None
                if witness_payload is None
                else LineOfSightWitness.from_payload(witness_payload)
            ),
            visibility_cache_key=payload["visibility_cache_key"],
            shooting_types=validate_shooting_type_tuple(
                "ShootingTargetCandidate payload shooting_types",
                tuple(payload["shooting_types"]),
            ),
            hit_roll_modifier=payload["hit_roll_modifier"],
            targeting_rule_ids=tuple(payload["targeting_rule_ids"]),
        )


def shooting_target_violation_code_from_token(
    token: object | None,
) -> ShootingTargetViolationCode | None:
    if token is None:
        return None
    if type(token) is ShootingTargetViolationCode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ShootingTargetViolationCode token must be a string.")
    try:
        return ShootingTargetViolationCode(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported shooting target violation: {token}.") from exc


def shooting_target_candidates_for_unit(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    weapon_profile: WeaponProfile,
    target_unit_ids: tuple[str, ...],
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
    hidden_target_unit_ids: tuple[str, ...] = (),
    target_unit_ids_with_recent_ranged_attacks: tuple[str, ...] = (),
    target_detection_range_bonus_inches_by_unit_id: Mapping[str, int] | None = None,
) -> tuple[ShootingTargetCandidate, ...]:
    _validate_target_query_inputs(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        attacker_unit=attacker_unit,
        weapon_profile=weapon_profile,
        target_unit_ids=target_unit_ids,
        terrain_features=terrain_features,
    )
    hidden_target_ids = _validate_identifier_tuple("hidden_target_unit_ids", hidden_target_unit_ids)
    recent_ranged_attack_target_ids = _validate_identifier_tuple(
        "target_unit_ids_with_recent_ranged_attacks",
        target_unit_ids_with_recent_ranged_attacks,
    )
    detection_range_bonus_by_unit_id = _validate_detection_range_bonus_mapping(
        target_detection_range_bonus_inches_by_unit_id
    )
    canonical_target_unit_ids = _canonical_target_unit_ids(
        scenario=scenario,
        target_unit_ids=target_unit_ids,
    )
    return tuple(
        _target_candidate(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            attacker_unit=attacker_unit,
            attacker_model_instance_id=None,
            weapon_profile=weapon_profile,
            target_unit_id=target_unit_id,
            terrain_features=terrain_features,
            hidden_target_unit_ids=hidden_target_ids,
            target_unit_ids_with_recent_ranged_attacks=recent_ranged_attack_target_ids,
            target_detection_range_bonus_inches=(
                detection_range_bonus_by_unit_id.get(target_unit_id, 0)
            ),
        )
        for target_unit_id in canonical_target_unit_ids
    )


def shooting_target_candidate_for_model(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    attacker_model_instance_id: str,
    weapon_profile: WeaponProfile,
    target_unit_id: str,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
    hidden_target_unit_ids: tuple[str, ...] = (),
    target_unit_ids_with_recent_ranged_attacks: tuple[str, ...] = (),
    target_detection_range_bonus_inches: int = 0,
) -> ShootingTargetCandidate:
    _validate_target_query_inputs(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        attacker_unit=attacker_unit,
        weapon_profile=weapon_profile,
        target_unit_ids=(target_unit_id,),
        terrain_features=terrain_features,
    )
    hidden_target_ids = _validate_identifier_tuple("hidden_target_unit_ids", hidden_target_unit_ids)
    recent_ranged_attack_target_ids = _validate_identifier_tuple(
        "target_unit_ids_with_recent_ranged_attacks",
        target_unit_ids_with_recent_ranged_attacks,
    )
    return _target_candidate(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        attacker_unit=attacker_unit,
        attacker_model_instance_id=_validate_identifier(
            "attacker_model_instance_id",
            attacker_model_instance_id,
        ),
        weapon_profile=weapon_profile,
        target_unit_id=target_unit_id,
        terrain_features=terrain_features,
        hidden_target_unit_ids=hidden_target_ids,
        target_unit_ids_with_recent_ranged_attacks=recent_ranged_attack_target_ids,
        target_detection_range_bonus_inches=_validate_non_negative_int(
            "target_detection_range_bonus_inches",
            target_detection_range_bonus_inches,
        ),
    )


def shooting_visibility_cache_key(
    *,
    scenario: BattlefieldScenario,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
) -> str:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("shooting_visibility_cache_key requires a BattlefieldScenario.")
    if type(terrain_features) is not tuple:
        raise GameLifecycleError("terrain_features must be a tuple.")
    for feature in terrain_features:
        if type(feature) is not TerrainFeatureDefinition:
            raise GameLifecycleError("terrain_features must contain TerrainFeatureDefinition.")
    spatial_state = SpatialIndexState.from_terrain_features(
        terrain_features,
        model_blocker_revision=_model_blocker_revision(scenario.placed_geometry_models()),
    )
    return spatial_state.los_cache_key()


def unit_has_line_of_sight_to_target(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    observing_unit: UnitInstance,
    target_unit_id: str,
    observer_model_instance_id: str | None = None,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
) -> bool:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Line of sight target query requires a BattlefieldScenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Line of sight target query requires a RulesetDescriptor.")
    if type(observing_unit) is not UnitInstance:
        raise GameLifecycleError("Line of sight target query requires a UnitInstance.")
    _validate_identifier("target_unit_id", target_unit_id)
    observer_model_id = _validate_optional_identifier(
        "observer_model_instance_id",
        observer_model_instance_id,
    )
    if type(terrain_features) is not tuple:
        raise GameLifecycleError("terrain_features must be a tuple.")
    for feature in terrain_features:
        if type(feature) is not TerrainFeatureDefinition:
            raise GameLifecycleError("terrain_features must contain TerrainFeatureDefinition.")
    observing_placement = _unit_placement_or_none(scenario, observing_unit.unit_instance_id)
    target_rules_unit = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=target_unit_id,
    )
    target_placements = _unit_placements_for_rules_unit_or_none(
        scenario=scenario,
        rules_unit=target_rules_unit,
    )
    if observing_placement is None or target_placements is None:
        raise GameLifecycleError("Line of sight target query requires placed units.")
    visibility_cache_key = shooting_visibility_cache_key(
        scenario=scenario,
        terrain_features=terrain_features,
    )
    target_models = _geometry_models_for_unit_placements(
        scenario=scenario,
        unit_placements=target_placements,
    )
    blocker_models = _shooting_dynamic_model_blockers(
        scenario=scenario,
        observing_unit_id=observing_unit.unit_instance_id,
        target_unit_id=target_rules_unit.unit_instance_id,
    )
    observer_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=observing_placement,
    )
    if observer_model_id is not None:
        observer_models = tuple(
            model for model in observer_models if model.model_id == observer_model_id
        )
        if not observer_models:
            raise GameLifecycleError("Line of sight target query observer model is not placed.")
    for observer_model in observer_models:
        context = TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=ruleset_descriptor,
            los_cache_key=visibility_cache_key,
            observer_model=observer_model,
            target_models=target_models,
            terrain_features=terrain_features,
            dynamic_model_blockers=blocker_models,
            observer_keywords=observing_unit.keywords,
            target_keywords=target_rules_unit.keywords,
        )
        if context.resolve_line_of_sight().visible_model_ids:
            return True
    return False


def _validate_target_query_inputs(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    weapon_profile: WeaponProfile,
    target_unit_ids: tuple[str, ...],
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> None:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Shooting target query requires a BattlefieldScenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Shooting target query requires a RulesetDescriptor.")
    if type(attacker_unit) is not UnitInstance:
        raise GameLifecycleError("Shooting target query requires a UnitInstance.")
    if type(weapon_profile) is not WeaponProfile:
        raise GameLifecycleError("Shooting target query requires a WeaponProfile.")
    if type(target_unit_ids) is not tuple:
        raise GameLifecycleError("target_unit_ids must be a tuple.")
    for target_unit_id in target_unit_ids:
        _validate_identifier("target_unit_id", target_unit_id)
    if type(terrain_features) is not tuple:
        raise GameLifecycleError("terrain_features must be a tuple.")
    for feature in terrain_features:
        if type(feature) is not TerrainFeatureDefinition:
            raise GameLifecycleError("terrain_features must contain TerrainFeatureDefinition.")


def _target_candidate(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    attacker_model_instance_id: str | None,
    weapon_profile: WeaponProfile,
    target_unit_id: str,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    hidden_target_unit_ids: tuple[str, ...],
    target_unit_ids_with_recent_ranged_attacks: tuple[str, ...],
    target_detection_range_bonus_inches: int,
) -> ShootingTargetCandidate:
    target_rules_unit = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=target_unit_id,
    )
    target_unit_id = target_rules_unit.unit_instance_id
    visibility_cache_key = shooting_visibility_cache_key(
        scenario=scenario,
        terrain_features=terrain_features,
    )
    if weapon_profile.range_profile.kind is RangeProfileKind.MELEE:
        return _invalid_candidate(
            attacker_unit=attacker_unit,
            weapon_profile=weapon_profile,
            target_unit_id=target_unit_id,
            violation_code=ShootingTargetViolationCode.MELEE_WEAPON,
            message="Melee weapon profiles cannot declare ranged shooting targets.",
            visibility_cache_key=visibility_cache_key,
        )
    attacker_owner = _player_id_for_unit(scenario, attacker_unit.unit_instance_id)
    target_owner = target_rules_unit.owner_player_id
    if target_owner == attacker_owner:
        return _invalid_candidate(
            attacker_unit=attacker_unit,
            weapon_profile=weapon_profile,
            target_unit_id=target_unit_id,
            violation_code=ShootingTargetViolationCode.NOT_ENEMY_UNIT,
            message="Shooting targets must be enemy units.",
            visibility_cache_key=visibility_cache_key,
        )

    attacker_placement = _unit_placement_or_none(scenario, attacker_unit.unit_instance_id)
    target_placements = _unit_placements_for_rules_unit_or_none(
        scenario=scenario,
        rules_unit=target_rules_unit,
    )
    if attacker_placement is None or target_placements is None:
        return _invalid_candidate(
            attacker_unit=attacker_unit,
            weapon_profile=weapon_profile,
            target_unit_id=target_unit_id,
            violation_code=ShootingTargetViolationCode.TARGET_NOT_PLACED,
            message="Ranged target selection requires placed attacker and target units.",
            visibility_cache_key=visibility_cache_key,
        )
    hunter_rule_ids: tuple[str, ...] = ()
    if WeaponKeyword.HUNTER in weapon_profile.keywords:
        hunter_rule_ids = (HUNTER_RULE_ID,)
        if not hunter_target_allowed(weapon_profile, target_keywords=target_rules_unit.keywords):
            return _invalid_candidate(
                attacker_unit=attacker_unit,
                weapon_profile=weapon_profile,
                target_unit_id=target_unit_id,
                violation_code=ShootingTargetViolationCode.HUNTER_TARGET_KEYWORD_MISMATCH,
                message="Hunter weapons can only target units with at least one listed keyword.",
                visibility_cache_key=visibility_cache_key,
                targeting_rule_ids=hunter_rule_ids,
            )
    attacker_models = _attacker_geometry_models(
        scenario=scenario,
        attacker_placement=attacker_placement,
        attacker_model_instance_id=attacker_model_instance_id,
    )
    target_models = _geometry_models_for_unit_placements(
        scenario=scenario,
        unit_placements=target_placements,
    )
    range_inches = weapon_profile.range_profile.distance_inches
    if range_inches is None:
        raise GameLifecycleError("Ranged target selection requires a distance range profile.")
    target_in_range_model_ids = _target_in_range_model_ids(
        attacker_models=attacker_models,
        target_models=target_models,
        range_inches=range_inches,
    )
    if not target_in_range_model_ids:
        return _invalid_candidate(
            attacker_unit=attacker_unit,
            weapon_profile=weapon_profile,
            target_unit_id=target_unit_id,
            violation_code=ShootingTargetViolationCode.OUT_OF_RANGE,
            message="No target model is within the weapon's range profile.",
            visibility_cache_key=visibility_cache_key,
        )
    detection_validation = _hidden_target_detection_validation(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        attacker_unit=attacker_unit,
        attacker_models=attacker_models,
        target_rules_unit=target_rules_unit,
        target_models=target_models,
        target_unit_id=target_unit_id,
        visibility_cache_key=visibility_cache_key,
        terrain_features=terrain_features,
        hidden_target_unit_ids=hidden_target_unit_ids,
        target_unit_ids_with_recent_ranged_attacks=target_unit_ids_with_recent_ranged_attacks,
        target_detection_range_bonus_inches=target_detection_range_bonus_inches,
    )
    if detection_validation is not None:
        return _invalid_candidate(
            attacker_unit=attacker_unit,
            weapon_profile=weapon_profile,
            target_unit_id=target_unit_id,
            violation_code=ShootingTargetViolationCode.OUTSIDE_DETECTION_RANGE,
            message=detection_validation,
            visibility_cache_key=visibility_cache_key,
            target_in_range_model_ids=target_in_range_model_ids,
        )

    evidence = _best_line_of_sight_range_evidence(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        attacker_unit=attacker_unit,
        attacker_models=attacker_models,
        target_rules_unit=target_rules_unit,
        target_models=target_models,
        visibility_cache_key=visibility_cache_key,
        range_inches=range_inches,
        terrain_features=terrain_features,
    )
    indirect_no_visible = (
        evidence is not None
        and not evidence.visible_and_in_range_target_model_ids
        and WeaponKeyword.INDIRECT_FIRE in weapon_profile.keywords
        and WeaponKeyword.TORRENT not in weapon_profile.keywords
    )
    if evidence is None or (
        not evidence.visible_and_in_range_target_model_ids and not indirect_no_visible
    ):
        witness = None if evidence is None else evidence.witness
        return _invalid_candidate(
            attacker_unit=attacker_unit,
            weapon_profile=weapon_profile,
            target_unit_id=target_unit_id,
            violation_code=ShootingTargetViolationCode.NOT_VISIBLE,
            message="No target model is both visible to and within range of the attacker.",
            visibility_cache_key=visibility_cache_key,
            target_visible_model_ids=(),
            target_in_range_model_ids=target_in_range_model_ids,
            line_of_sight_witness=witness,
            observer_model_id=None if witness is None else witness.observer_model_id,
        )
    witness = evidence.witness

    locked_context = _locked_in_combat_context(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        attacker_unit=attacker_unit,
        attacker_models=attacker_models,
    )
    target_engagement_context = _target_engagement_context(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        attacker_owner=attacker_owner,
        target_rules_unit=target_rules_unit,
        target_unit_id=target_unit_id,
        target_models=target_models,
    )
    if locked_context.is_locked:
        locked_validation = _locked_in_combat_validation(
            attacker_unit=attacker_unit,
            weapon_profile=weapon_profile,
            target_unit_id=target_unit_id,
            engaged_target_unit_ids=locked_context.engaged_target_unit_ids,
        )
        if locked_validation is not None:
            return _invalid_candidate(
                attacker_unit=attacker_unit,
                weapon_profile=weapon_profile,
                target_unit_id=target_unit_id,
                violation_code=ShootingTargetViolationCode.LOCKED_IN_COMBAT,
                message=locked_validation,
                visibility_cache_key=visibility_cache_key,
                target_visible_model_ids=witness.visible_model_ids,
                target_in_range_model_ids=target_in_range_model_ids,
                line_of_sight_witness=witness,
                observer_model_id=witness.observer_model_id,
            )
    target_engagement_validation = _target_engagement_validation(
        attacker_unit=attacker_unit,
        target_keywords=target_rules_unit.keywords,
        target_unit_id=target_unit_id,
        weapon_profile=weapon_profile,
        locked_context=locked_context,
        target_engagement_context=target_engagement_context,
    )
    if target_engagement_validation is not None:
        return _invalid_candidate(
            attacker_unit=attacker_unit,
            weapon_profile=weapon_profile,
            target_unit_id=target_unit_id,
            violation_code=ShootingTargetViolationCode.LOCKED_IN_COMBAT,
            message=target_engagement_validation,
            visibility_cache_key=visibility_cache_key,
            target_visible_model_ids=evidence.visible_and_in_range_target_model_ids,
            target_in_range_model_ids=evidence.visible_and_in_range_target_model_ids,
            line_of_sight_witness=witness,
            observer_model_id=witness.observer_model_id,
        )

    if _blast_engaged_target_validation(
        weapon_profile=weapon_profile,
        target_unit_id=target_unit_id,
        locked_context=locked_context,
        target_engagement_context=target_engagement_context,
    ):
        return _invalid_candidate(
            attacker_unit=attacker_unit,
            weapon_profile=weapon_profile,
            target_unit_id=target_unit_id,
            violation_code=ShootingTargetViolationCode.LOCKED_IN_COMBAT,
            message="Blast weapons cannot target units that are within Engagement Range.",
            visibility_cache_key=visibility_cache_key,
            target_visible_model_ids=evidence.visible_and_in_range_target_model_ids,
            target_in_range_model_ids=evidence.visible_and_in_range_target_model_ids,
            line_of_sight_witness=witness,
            observer_model_id=witness.observer_model_id,
        )

    if _rules_unit_has_lone_operative(target_rules_unit) and not (
        _lone_operative_target_allowed(
            scenario=scenario,
            attacker_unit=attacker_unit,
            attacker_model_instance_id=attacker_model_instance_id,
            target_rules_unit=target_rules_unit,
        )
    ):
        return _invalid_candidate(
            attacker_unit=attacker_unit,
            weapon_profile=weapon_profile,
            target_unit_id=target_unit_id,
            violation_code=ShootingTargetViolationCode.LONE_OPERATIVE,
            message="Lone Operative target is outside the allowed targeting distance.",
            visibility_cache_key=visibility_cache_key,
            target_visible_model_ids=evidence.visible_and_in_range_target_model_ids,
            target_in_range_model_ids=evidence.visible_and_in_range_target_model_ids,
            line_of_sight_witness=witness,
            observer_model_id=witness.observer_model_id,
            targeting_rule_ids=(LONE_OPERATIVE_RULE_ID,),
        )

    hit_roll_modifier = 0
    targeting_rule_ids: list[str] = list(hunter_rule_ids)
    if indirect_no_visible:
        hit_roll_modifier -= 1
        targeting_rule_ids.extend(
            (
                INDIRECT_FIRE_NO_VISIBLE_RULE_ID,
                INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
            )
        )
    elif (
        evidence.cover_result.has_benefit
        and evidence.cover_result.cover_effect is CoverEffect.ATTACKER_BS_MODIFIER
    ):
        targeting_rule_ids.append(BENEFIT_OF_COVER_RULE_ID)
    if _rules_unit_has_stealth(target_rules_unit):
        hit_roll_modifier -= 1
        targeting_rule_ids.append(STEALTH_RULE_ID)
    if _plunging_fire_applies(
        attacker_unit=attacker_unit,
        attacker_models=attacker_models,
        target_keywords=target_rules_unit.keywords,
        target_models=target_models,
        evidence=evidence,
        terrain_features=terrain_features,
    ):
        targeting_rule_ids.append(PLUNGING_FIRE_RULE_ID)
    if (
        locked_context.is_locked
        and _unit_has_vehicle_or_monster_keyword(attacker_unit)
        and not has_close_quarters_weapon_keyword(weapon_profile)
    ) or (
        target_engagement_context.is_engaged_by_friendly
        and _keywords_include_vehicle_or_monster(target_rules_unit.keywords)
        and not has_close_quarters_weapon_keyword(weapon_profile)
    ):
        hit_roll_modifier -= 1
        targeting_rule_ids.append(BIG_GUNS_NEVER_TIRE_RULE_ID)
    if (
        target_engagement_context.is_engaged_only_by_friendly_fortifications
        and not has_weapon_keyword(weapon_profile, WeaponKeyword.PISTOL)
    ):
        hit_roll_modifier -= 1
        targeting_rule_ids.append(FORTIFICATION_ENGAGEMENT_RULE_ID)

    return ShootingTargetCandidate.legal(
        attacker_unit_instance_id=attacker_unit.unit_instance_id,
        weapon_profile_id=weapon_profile.profile_id,
        target_unit_instance_id=target_unit_id,
        observer_model_id=witness.observer_model_id,
        target_visible_model_ids=(
            () if indirect_no_visible else evidence.visible_and_in_range_target_model_ids
        ),
        target_in_range_model_ids=(
            target_in_range_model_ids
            if indirect_no_visible
            else evidence.visible_and_in_range_target_model_ids
        ),
        line_of_sight_witness=witness,
        visibility_cache_key=visibility_cache_key,
        shooting_types=_shooting_types_for_target_candidate(
            indirect_no_visible=indirect_no_visible,
            locked_context=locked_context,
            target_engagement_context=target_engagement_context,
        ),
        hit_roll_modifier=hit_roll_modifier,
        targeting_rule_ids=tuple(targeting_rule_ids),
    )


def _invalid_candidate(
    *,
    attacker_unit: UnitInstance,
    weapon_profile: WeaponProfile,
    target_unit_id: str,
    violation_code: ShootingTargetViolationCode,
    message: str,
    visibility_cache_key: str,
    target_visible_model_ids: tuple[str, ...] = (),
    target_in_range_model_ids: tuple[str, ...] = (),
    line_of_sight_witness: LineOfSightWitness | None = None,
    observer_model_id: str | None = None,
    hit_roll_modifier: int = 0,
    targeting_rule_ids: tuple[str, ...] = (),
) -> ShootingTargetCandidate:
    return ShootingTargetCandidate.invalid(
        attacker_unit_instance_id=attacker_unit.unit_instance_id,
        weapon_profile_id=weapon_profile.profile_id,
        target_unit_instance_id=target_unit_id,
        violation_code=violation_code,
        message=message,
        visibility_cache_key=visibility_cache_key,
        target_visible_model_ids=target_visible_model_ids,
        target_in_range_model_ids=target_in_range_model_ids,
        line_of_sight_witness=line_of_sight_witness,
        observer_model_id=observer_model_id,
        hit_roll_modifier=hit_roll_modifier,
        targeting_rule_ids=targeting_rule_ids,
    )


def _canonical_target_unit_ids(
    *,
    scenario: BattlefieldScenario,
    target_unit_ids: tuple[str, ...],
) -> tuple[str, ...]:
    canonical_ids: list[str] = []
    seen: set[str] = set()
    for target_unit_id in target_unit_ids:
        canonical_id = rules_unit_view_from_armies(
            armies=scenario.armies,
            unit_instance_id=target_unit_id,
        ).unit_instance_id
        if canonical_id in seen:
            continue
        seen.add(canonical_id)
        canonical_ids.append(canonical_id)
    return tuple(canonical_ids)


def _player_id_for_unit(scenario: BattlefieldScenario, unit_instance_id: str) -> str:
    return rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=unit_instance_id,
    ).owner_player_id


def shooting_dynamic_model_blockers(
    *,
    scenario: BattlefieldScenario,
    observing_unit_id: str,
    target_unit_id: str,
) -> tuple[Model, ...]:
    _validate_identifier("observing_unit_id", observing_unit_id)
    _validate_identifier("target_unit_id", target_unit_id)
    observing_rules_unit = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=observing_unit_id,
    )
    target_rules_unit = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=target_unit_id,
    )
    excluded_unit_ids = {
        *observing_rules_unit.component_unit_instance_ids,
        *target_rules_unit.component_unit_instance_ids,
    }
    blocker_models: list[Model] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            if unit_placement.unit_instance_id in excluded_unit_ids:
                continue
            blocker_models.extend(
                _geometry_models_for_unit_placement(
                    scenario=scenario,
                    unit_placement=unit_placement,
                )
            )
    return tuple(sorted(blocker_models, key=lambda model: model.model_id))


def _shooting_dynamic_model_blockers(
    *,
    scenario: BattlefieldScenario,
    observing_unit_id: str,
    target_unit_id: str,
) -> tuple[Model, ...]:
    return shooting_dynamic_model_blockers(
        scenario=scenario,
        observing_unit_id=observing_unit_id,
        target_unit_id=target_unit_id,
    )


def _hidden_target_detection_validation(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    attacker_models: tuple[Model, ...],
    target_rules_unit: RulesUnitView,
    target_models: tuple[Model, ...],
    target_unit_id: str,
    visibility_cache_key: str,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    hidden_target_unit_ids: tuple[str, ...],
    target_unit_ids_with_recent_ranged_attacks: tuple[str, ...],
    target_detection_range_bonus_inches: int,
) -> str | None:
    if target_unit_id not in hidden_target_unit_ids:
        return None
    visibility_policy = ruleset_descriptor.terrain_visibility_policy
    if not visibility_policy.hidden_supported:
        raise GameLifecycleError("Hidden target state requires hidden visibility support.")
    hidden_detection_range = visibility_policy.hidden_detection_range_inches
    if hidden_detection_range is None:
        raise GameLifecycleError("Hidden target state requires a detection range.")
    target_within_detection = _target_within_effective_hidden_detection_range(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        attacker_unit=attacker_unit,
        attacker_models=attacker_models,
        target_rules_unit=target_rules_unit,
        target_models=target_models,
        visibility_cache_key=visibility_cache_key,
        terrain_features=terrain_features,
        hidden_detection_range_inches=hidden_detection_range,
        target_detection_range_bonus_inches=target_detection_range_bonus_inches,
        target_made_recent_ranged_attacks=(
            target_unit_id in target_unit_ids_with_recent_ranged_attacks
        ),
    )
    if target_within_detection:
        return None
    return "Hidden target is outside the attacker's effective detection range."


def _target_within_effective_hidden_detection_range(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    attacker_models: tuple[Model, ...],
    target_rules_unit: RulesUnitView,
    target_models: tuple[Model, ...],
    visibility_cache_key: str,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    hidden_detection_range_inches: float,
    target_detection_range_bonus_inches: int,
    target_made_recent_ranged_attacks: bool,
) -> bool:
    visibility_policy = ruleset_descriptor.terrain_visibility_policy
    base_detection_range = hidden_detection_range_inches + float(
        target_detection_range_bonus_inches
    )
    blocker_models = _shooting_dynamic_model_blockers(
        scenario=scenario,
        observing_unit_id=attacker_unit.unit_instance_id,
        target_unit_id=target_rules_unit.unit_instance_id,
    )
    for attacker_model in attacker_models:
        for target_model in target_models:
            effective_detection_range = base_detection_range
            if (
                not target_made_recent_ranged_attacks
                and visibility_policy.hidden_gone_to_ground_detection_penalty_inches > 0.0
                and _target_model_has_gone_to_ground_against_attacker(
                    ruleset_descriptor=ruleset_descriptor,
                    attacker_unit=attacker_unit,
                    attacker_model=attacker_model,
                    target_rules_unit=target_rules_unit,
                    target_model=target_model,
                    visibility_cache_key=visibility_cache_key,
                    terrain_features=terrain_features,
                    dynamic_model_blockers=blocker_models,
                )
            ):
                effective_detection_range -= (
                    visibility_policy.hidden_gone_to_ground_detection_penalty_inches
                )
            if attacker_model.range_to(target_model) <= max(0.0, effective_detection_range):
                return True
    return False


def _target_model_has_gone_to_ground_against_attacker(
    *,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    attacker_model: Model,
    target_rules_unit: RulesUnitView,
    target_model: Model,
    visibility_cache_key: str,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    dynamic_model_blockers: tuple[Model, ...],
) -> bool:
    if not _model_within_solid_terrain_feature(
        ruleset_descriptor=ruleset_descriptor,
        model=target_model,
        terrain_features=terrain_features,
    ):
        return False
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset_descriptor,
        los_cache_key=visibility_cache_key,
        observer_model=attacker_model,
        target_models=(target_model,),
        terrain_features=terrain_features,
        dynamic_model_blockers=dynamic_model_blockers,
        observer_keywords=attacker_unit.keywords,
        target_keywords=target_rules_unit.keywords,
    )
    witness = context.resolve_line_of_sight()
    if witness.unit_fully_visible:
        return False
    return any(
        record.blocks_full_visibility
        and record.terrain_feature_kind is not None
        and _terrain_feature_kind_is_solid(
            ruleset_descriptor=ruleset_descriptor,
            feature_kind=record.terrain_feature_kind,
        )
        for record in witness.all_blocker_records()
    )


def _model_within_solid_terrain_feature(
    *,
    ruleset_descriptor: RulesetDescriptor,
    model: Model,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> bool:
    for feature in terrain_features:
        if not _terrain_feature_kind_is_solid(
            ruleset_descriptor=ruleset_descriptor,
            feature_kind=feature.feature_kind,
        ):
            continue
        if _model_footprint_intersects_feature(model=model, feature=feature):
            return True
    return False


def _terrain_feature_kind_is_solid(
    *,
    ruleset_descriptor: RulesetDescriptor,
    feature_kind: TerrainFeatureKind,
) -> bool:
    policy = ruleset_descriptor.terrain_visibility_policy.policy_for_feature_kind(
        feature_kind,
    )
    return policy.line_of_sight_policy is LineOfSightPolicy.DENSE_COVER


def _model_footprint_intersects_feature(
    *,
    model: Model,
    feature: TerrainFeatureDefinition,
) -> bool:
    return shapely_backend.base_footprint_intersects_bounds(
        model.base,
        model.pose,
        feature.bounds(),
    )


def _plunging_fire_applies(
    *,
    attacker_unit: UnitInstance,
    attacker_models: tuple[Model, ...],
    target_keywords: tuple[str, ...],
    target_models: tuple[Model, ...],
    evidence: _LineOfSightRangeEvidence,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> bool:
    if _unit_has_keyword(attacker_unit, "AIRCRAFT") or _keywords_include(
        target_keywords,
        "AIRCRAFT",
    ):
        return False
    if not evidence.visible_and_in_range_target_model_ids:
        return False
    if not _target_unit_contains_ground_level_model(target_models):
        return False
    observer_model = _geometry_model_by_id(attacker_models, evidence.witness.observer_model_id)
    return _attacker_model_on_plunging_fire_terrain(
        attacker_model=observer_model,
        terrain_features=terrain_features,
    ) or (
        _unit_has_keyword(attacker_unit, "TOWERING")
        and _target_unit_within_towering_plunging_fire_range(
            attacker_model=observer_model,
            target_models=target_models,
        )
    )


def _target_unit_contains_ground_level_model(target_models: tuple[Model, ...]) -> bool:
    return any(abs(model.pose.position.z) <= _GROUND_LEVEL_EPSILON for model in target_models)


def _attacker_model_on_plunging_fire_terrain(
    *,
    attacker_model: Model,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> bool:
    for feature in terrain_features:
        for floor in feature.floors:
            if floor.bottom_z_inches < PLUNGING_FIRE_TERRAIN_HEIGHT_INCHES:
                continue
            floor_volume = floor.to_terrain_volume(feature_id=feature.feature_id)
            if floor_volume.intersects_model(attacker_model):
                return True
    return False


def _target_unit_within_towering_plunging_fire_range(
    *,
    attacker_model: Model,
    target_models: tuple[Model, ...],
) -> bool:
    return any(
        attacker_model.range_to(target_model) <= PLUNGING_FIRE_TOWERING_RANGE_INCHES
        for target_model in target_models
    )


def _geometry_model_by_id(models: tuple[Model, ...], model_id: str) -> Model:
    for model in models:
        if model.model_id == model_id:
            return model
    raise GameLifecycleError("Plunging Fire observer model is not in attacker geometry.")


def _best_line_of_sight_range_evidence(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    attacker_models: tuple[Model, ...],
    target_rules_unit: RulesUnitView,
    target_models: tuple[Model, ...],
    visibility_cache_key: str,
    range_inches: int,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> _LineOfSightRangeEvidence | None:
    best_evidence: _LineOfSightRangeEvidence | None = None
    best_blocked_evidence: _LineOfSightRangeEvidence | None = None
    blocker_models = _shooting_dynamic_model_blockers(
        scenario=scenario,
        observing_unit_id=attacker_unit.unit_instance_id,
        target_unit_id=target_rules_unit.unit_instance_id,
    )
    for attacker_model in sorted(attacker_models, key=lambda model: model.model_id):
        in_range_model_ids = _target_in_range_model_ids(
            attacker_models=(attacker_model,),
            target_models=target_models,
            range_inches=range_inches,
        )
        if not in_range_model_ids:
            continue
        context = TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=ruleset_descriptor,
            los_cache_key=visibility_cache_key,
            observer_model=attacker_model,
            target_models=target_models,
            terrain_features=terrain_features,
            dynamic_model_blockers=blocker_models,
            observer_keywords=attacker_unit.keywords,
            target_keywords=target_rules_unit.keywords,
        )
        witness = context.resolve_line_of_sight()
        cover_result = context.benefit_of_cover(witness)
        visible_and_in_range_ids = tuple(
            target_model_id
            for target_model_id in witness.visible_model_ids
            if target_model_id in in_range_model_ids
        )
        evidence = _LineOfSightRangeEvidence(
            witness=witness,
            cover_result=cover_result,
            visible_and_in_range_target_model_ids=visible_and_in_range_ids,
        )
        if not visible_and_in_range_ids:
            if best_blocked_evidence is None:
                best_blocked_evidence = evidence
            continue
        if best_evidence is None:
            best_evidence = evidence
            continue
        if len(visible_and_in_range_ids) > len(best_evidence.visible_and_in_range_target_model_ids):
            best_evidence = evidence
    return best_evidence if best_evidence is not None else best_blocked_evidence


@dataclass(frozen=True, slots=True)
class _LockedInCombatContext:
    is_locked: bool
    engaged_target_unit_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _TargetEngagementContext:
    is_engaged_by_friendly: bool
    engaged_friendly_unit_ids: tuple[str, ...]
    is_engaged_only_by_friendly_fortifications: bool


@dataclass(frozen=True, slots=True)
class _LineOfSightRangeEvidence:
    witness: LineOfSightWitness
    cover_result: BenefitOfCoverResult
    visible_and_in_range_target_model_ids: tuple[str, ...]


def _locked_in_combat_context(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    attacker_models: tuple[Model, ...],
) -> _LockedInCombatContext:
    attacker_owner = _player_id_for_unit(scenario, attacker_unit.unit_instance_id)
    engaged_unit_ids: set[str] = set()
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == attacker_owner:
            continue
        for unit_placement in placed_army.unit_placements:
            enemy_models = _geometry_models_for_unit_placement(
                scenario=scenario,
                unit_placement=unit_placement,
            )
            if _any_models_in_engagement(
                attacker_models=attacker_models,
                target_models=enemy_models,
                ruleset_descriptor=ruleset_descriptor,
            ):
                engaged_unit_ids.add(
                    rules_unit_view_from_armies(
                        armies=scenario.armies,
                        unit_instance_id=unit_placement.unit_instance_id,
                    ).unit_instance_id
                )
    return _LockedInCombatContext(
        is_locked=bool(engaged_unit_ids),
        engaged_target_unit_ids=tuple(sorted(engaged_unit_ids)),
    )


def _target_engagement_context(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_owner: str,
    target_rules_unit: RulesUnitView,
    target_unit_id: str,
    target_models: tuple[Model, ...],
) -> _TargetEngagementContext:
    engaged_friendly_unit_ids: set[str] = set()
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != attacker_owner:
            continue
        for unit_placement in placed_army.unit_placements:
            friendly_models = _geometry_models_for_unit_placement(
                scenario=scenario,
                unit_placement=unit_placement,
            )
            if _any_models_in_engagement(
                attacker_models=friendly_models,
                target_models=target_models,
                ruleset_descriptor=ruleset_descriptor,
            ):
                engaged_friendly_unit_ids.add(
                    rules_unit_view_from_armies(
                        armies=scenario.armies,
                        unit_instance_id=unit_placement.unit_instance_id,
                    ).unit_instance_id
                )
    if target_unit_id in engaged_friendly_unit_ids:
        raise GameLifecycleError("Target engagement context included the target unit.")
    if set(target_rules_unit.component_unit_instance_ids) & engaged_friendly_unit_ids:
        raise GameLifecycleError("Target engagement context included a target component.")
    engaged_only_by_fortifications = bool(engaged_friendly_unit_ids) and all(
        _rules_unit_has_fortification_keyword(
            rules_unit_view_from_armies(
                armies=scenario.armies,
                unit_instance_id=friendly_unit_id,
            )
        )
        for friendly_unit_id in engaged_friendly_unit_ids
    )
    return _TargetEngagementContext(
        is_engaged_by_friendly=bool(engaged_friendly_unit_ids),
        engaged_friendly_unit_ids=tuple(sorted(engaged_friendly_unit_ids)),
        is_engaged_only_by_friendly_fortifications=engaged_only_by_fortifications,
    )


def _any_models_in_engagement(
    *,
    attacker_models: tuple[Model, ...],
    target_models: tuple[Model, ...],
    ruleset_descriptor: RulesetDescriptor,
) -> bool:
    policy = ruleset_descriptor.engagement_policy
    for attacker_model in attacker_models:
        for target_model in target_models:
            if attacker_model.is_within_engagement_range(
                target_model,
                horizontal_inches=policy.horizontal_inches,
                vertical_inches=policy.vertical_inches,
            ):
                return True
    return False


def _target_engagement_validation(
    *,
    attacker_unit: UnitInstance,
    target_keywords: tuple[str, ...],
    target_unit_id: str,
    weapon_profile: WeaponProfile,
    locked_context: _LockedInCombatContext,
    target_engagement_context: _TargetEngagementContext,
) -> str | None:
    if not target_engagement_context.is_engaged_by_friendly:
        return None
    if target_engagement_context.is_engaged_only_by_friendly_fortifications:
        return None
    if _keywords_include_vehicle_or_monster(target_keywords):
        return None
    target_is_engaged_with_attacker = target_unit_id in locked_context.engaged_target_unit_ids
    if target_is_engaged_with_attacker and has_close_quarters_weapon_keyword(weapon_profile):
        return None
    if target_is_engaged_with_attacker and _unit_has_vehicle_or_monster_keyword(attacker_unit):
        return None
    return "Enemy units within Engagement Range of friendly units cannot be selected as targets."


def _locked_in_combat_validation(
    *,
    attacker_unit: UnitInstance,
    weapon_profile: WeaponProfile,
    target_unit_id: str,
    engaged_target_unit_ids: tuple[str, ...],
) -> str | None:
    is_close_quarters = has_close_quarters_weapon_keyword(weapon_profile)
    if is_close_quarters:
        if target_unit_id not in engaged_target_unit_ids:
            return "Close-quarters attacks from locked units must target engaged enemy units."
        return None
    if _unit_has_vehicle_or_monster_keyword(attacker_unit):
        return None
    return "Units locked in combat cannot shoot non-close-quarters ranged weapons."


def _blast_engaged_target_validation(
    *,
    weapon_profile: WeaponProfile,
    target_unit_id: str,
    locked_context: _LockedInCombatContext,
    target_engagement_context: _TargetEngagementContext,
) -> bool:
    if not has_weapon_keyword(weapon_profile, WeaponKeyword.BLAST):
        return False
    return (
        target_unit_id in locked_context.engaged_target_unit_ids
        or target_engagement_context.is_engaged_by_friendly
    )


def _shooting_types_for_target_candidate(
    *,
    indirect_no_visible: bool,
    locked_context: _LockedInCombatContext,
    target_engagement_context: _TargetEngagementContext,
) -> tuple[ShootingType, ...]:
    if indirect_no_visible:
        return (ShootingType.INDIRECT,)
    if locked_context.is_locked or (
        target_engagement_context.is_engaged_by_friendly
        and not target_engagement_context.is_engaged_only_by_friendly_fortifications
    ):
        return (ShootingType.CLOSE_QUARTERS,)
    return (ShootingType.NORMAL,)


def _lone_operative_target_allowed(
    *,
    scenario: BattlefieldScenario,
    attacker_unit: UnitInstance,
    attacker_model_instance_id: str | None,
    target_rules_unit: RulesUnitView,
) -> bool:
    return target_within_shooting_selection_range(
        scenario=scenario,
        attacking_unit_instance_id=attacker_unit.unit_instance_id,
        attacker_model_instance_id=attacker_model_instance_id,
        target_unit_instance_id=target_rules_unit.unit_instance_id,
        max_range_inches=12.0,
    )


def _rules_unit_has_lone_operative(rules_unit: RulesUnitView) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Lone Operative target lookup requires a rules unit.")
    return any(unit_has_lone_operative(component.unit) for component in rules_unit.components)


def _rules_unit_has_stealth(rules_unit: RulesUnitView) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Stealth target lookup requires a rules unit.")
    return any(unit_has_stealth(component.unit) for component in rules_unit.components)


def _rules_unit_has_fortification_keyword(rules_unit: RulesUnitView) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Fortification target lookup requires a rules unit.")
    return all(
        _unit_has_keyword(component.unit, "FORTIFICATION") for component in rules_unit.components
    )


def _unit_has_vehicle_or_monster_keyword(unit: UnitInstance) -> bool:
    return _unit_has_keyword(unit, "VEHICLE") or _unit_has_keyword(unit, "MONSTER")


def _keywords_include_vehicle_or_monster(keywords: tuple[str, ...]) -> bool:
    return _keywords_include(keywords, "VEHICLE") or _keywords_include(keywords, "MONSTER")


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return canonical in {_canonical_keyword(unit_keyword) for unit_keyword in unit.keywords}


def _keywords_include(keywords: tuple[str, ...], keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return canonical in {_canonical_keyword(unit_keyword) for unit_keyword in keywords}


def _canonical_keyword(keyword: str) -> str:
    return keyword.strip().upper().replace(" ", "_").replace("-", "_")


def _model_blocker_revision(models: tuple[Model, ...]) -> int:
    payload = [
        {
            "model_id": model.model_id,
            "pose": model.pose.to_payload(),
            "base": model.base.to_payload(),
            "volume": model.volume.to_payload(),
        }
        for model in sorted(models, key=lambda item: item.model_id)
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_optional_string(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    validated = tuple(_validate_identifier(field_name, value) for value in raw_values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return validated


def _validate_detection_range_bonus_mapping(
    value: object,
) -> Mapping[str, int]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise GameLifecycleError("target_detection_range_bonus_inches_by_unit_id must map units.")
    validated: dict[str, int] = {}
    raw_mapping = cast(Mapping[object, object], value)
    for raw_unit_id, raw_bonus in raw_mapping.items():
        unit_id = _validate_identifier("target_detection_range_bonus unit id", raw_unit_id)
        if unit_id in validated:
            raise GameLifecycleError("target_detection_range_bonus unit IDs must be unique.")
        validated[unit_id] = _validate_non_negative_int(
            "target_detection_range_bonus inches",
            raw_bonus,
        )
    return validated


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value
