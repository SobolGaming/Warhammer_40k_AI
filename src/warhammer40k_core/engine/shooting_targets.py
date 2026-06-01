from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    SpatialIndexState,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import (
    INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
    INDIRECT_FIRE_NO_VISIBLE_RULE_ID,
)
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.visibility import (
    LineOfSightWitness,
    LineOfSightWitnessPayload,
    TerrainVisibilityContext,
)
from warhammer40k_core.geometry.volume import Model

BIG_GUNS_NEVER_TIRE_RULE_ID = "big_guns_never_tire"
LONE_OPERATIVE_RULE_ID = "lone_operative"


class ShootingTargetViolationCode(StrEnum):
    MELEE_WEAPON = "melee_weapon"
    NOT_ENEMY_UNIT = "not_enemy_unit"
    TARGET_NOT_PLACED = "target_not_placed"
    OUT_OF_RANGE = "out_of_range"
    NOT_VISIBLE = "not_visible"
    LONE_OPERATIVE = "lone_operative"
    LOCKED_IN_COMBAT = "locked_in_combat"


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
) -> tuple[ShootingTargetCandidate, ...]:
    _validate_target_query_inputs(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        attacker_unit=attacker_unit,
        weapon_profile=weapon_profile,
        target_unit_ids=target_unit_ids,
        terrain_features=terrain_features,
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
        )
        for target_unit_id in target_unit_ids
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
) -> ShootingTargetCandidate:
    _validate_target_query_inputs(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        attacker_unit=attacker_unit,
        weapon_profile=weapon_profile,
        target_unit_ids=(target_unit_id,),
        terrain_features=terrain_features,
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
) -> ShootingTargetCandidate:
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
    target_owner = _player_id_for_unit(scenario, target_unit_id)
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
    target_placement = _unit_placement_or_none(scenario, target_unit_id)
    if attacker_placement is None or target_placement is None:
        return _invalid_candidate(
            attacker_unit=attacker_unit,
            weapon_profile=weapon_profile,
            target_unit_id=target_unit_id,
            violation_code=ShootingTargetViolationCode.TARGET_NOT_PLACED,
            message="Ranged target selection requires placed attacker and target units.",
            visibility_cache_key=visibility_cache_key,
        )
    target_unit = scenario.army_by_id(target_placement.army_id).unit_by_id(target_unit_id)
    attacker_models = _attacker_geometry_models(
        scenario=scenario,
        attacker_placement=attacker_placement,
        attacker_model_instance_id=attacker_model_instance_id,
    )
    target_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=target_placement,
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

    evidence = _best_line_of_sight_range_evidence(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        attacker_unit=attacker_unit,
        attacker_models=attacker_models,
        target_unit=target_unit,
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
        target_unit=target_unit,
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

    if _unit_has_keyword(target_unit, "LONE_OPERATIVE") and not _lone_operative_target_allowed(
        scenario=scenario,
        attacker_unit=attacker_unit,
        target_unit=target_unit,
        target_unit_id=target_unit_id,
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
    targeting_rule_ids: list[str] = []
    if indirect_no_visible:
        hit_roll_modifier -= 1
        targeting_rule_ids.extend(
            (
                INDIRECT_FIRE_NO_VISIBLE_RULE_ID,
                INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
            )
        )
    if (
        locked_context.is_locked
        and _unit_has_vehicle_or_monster_keyword(attacker_unit)
        and WeaponKeyword.PISTOL not in weapon_profile.keywords
    ) or (
        target_engagement_context.is_engaged_by_friendly
        and _unit_has_vehicle_or_monster_keyword(target_unit)
        and WeaponKeyword.PISTOL not in weapon_profile.keywords
    ):
        hit_roll_modifier -= 1
        targeting_rule_ids.append(BIG_GUNS_NEVER_TIRE_RULE_ID)

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


def _unit_placement_or_none(
    scenario: BattlefieldScenario,
    unit_instance_id: str,
) -> UnitPlacement | None:
    try:
        return scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    except PlacementError:
        return None


def _player_id_for_unit(scenario: BattlefieldScenario, unit_instance_id: str) -> str:
    for army in scenario.armies:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return army.player_id
    raise GameLifecycleError("Shooting target unit_instance_id is unknown.")


def _geometry_models_for_unit_placement(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> tuple[Model, ...]:
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in unit_placement.model_placements
    )


def _attacker_geometry_models(
    *,
    scenario: BattlefieldScenario,
    attacker_placement: UnitPlacement,
    attacker_model_instance_id: str | None,
) -> tuple[Model, ...]:
    models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=attacker_placement,
    )
    if attacker_model_instance_id is None:
        return models
    selected = tuple(model for model in models if model.model_id == attacker_model_instance_id)
    if not selected:
        raise GameLifecycleError("Selected attacker model is not placed in the attacker unit.")
    return selected


def shooting_dynamic_model_blockers(
    *,
    scenario: BattlefieldScenario,
    observing_unit_id: str,
    target_unit_id: str,
) -> tuple[Model, ...]:
    _validate_identifier("observing_unit_id", observing_unit_id)
    _validate_identifier("target_unit_id", target_unit_id)
    excluded_unit_ids = {observing_unit_id, target_unit_id}
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


def _target_in_range_model_ids(
    *,
    attacker_models: tuple[Model, ...],
    target_models: tuple[Model, ...],
    range_inches: int,
) -> tuple[str, ...]:
    ids: set[str] = set()
    for attacker_model in attacker_models:
        for target_model in target_models:
            if attacker_model.range_to(target_model) <= float(range_inches):
                ids.add(target_model.model_id)
    return tuple(sorted(ids))


def _best_line_of_sight_range_evidence(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    attacker_models: tuple[Model, ...],
    target_unit: UnitInstance,
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
        target_unit_id=target_unit.unit_instance_id,
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
            target_keywords=target_unit.keywords,
        )
        witness = context.resolve_line_of_sight()
        visible_and_in_range_ids = tuple(
            target_model_id
            for target_model_id in witness.visible_model_ids
            if target_model_id in in_range_model_ids
        )
        evidence = _LineOfSightRangeEvidence(
            witness=witness,
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


@dataclass(frozen=True, slots=True)
class _LineOfSightRangeEvidence:
    witness: LineOfSightWitness
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
                engaged_unit_ids.add(unit_placement.unit_instance_id)
    return _LockedInCombatContext(
        is_locked=bool(engaged_unit_ids),
        engaged_target_unit_ids=tuple(sorted(engaged_unit_ids)),
    )


def _target_engagement_context(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_owner: str,
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
                engaged_friendly_unit_ids.add(unit_placement.unit_instance_id)
    if target_unit_id in engaged_friendly_unit_ids:
        raise GameLifecycleError("Target engagement context included the target unit.")
    return _TargetEngagementContext(
        is_engaged_by_friendly=bool(engaged_friendly_unit_ids),
        engaged_friendly_unit_ids=tuple(sorted(engaged_friendly_unit_ids)),
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
    target_unit: UnitInstance,
    target_unit_id: str,
    weapon_profile: WeaponProfile,
    locked_context: _LockedInCombatContext,
    target_engagement_context: _TargetEngagementContext,
) -> str | None:
    if not target_engagement_context.is_engaged_by_friendly:
        return None
    if _unit_has_vehicle_or_monster_keyword(target_unit):
        return None
    target_is_engaged_with_attacker = target_unit_id in locked_context.engaged_target_unit_ids
    if target_is_engaged_with_attacker and WeaponKeyword.PISTOL in weapon_profile.keywords:
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
    is_pistol = WeaponKeyword.PISTOL in weapon_profile.keywords
    if is_pistol:
        if target_unit_id not in engaged_target_unit_ids:
            return "Pistol attacks from locked units must target engaged enemy units."
        return None
    if _unit_has_vehicle_or_monster_keyword(attacker_unit):
        return None
    return "Units locked in combat cannot shoot non-Pistol ranged weapons."


def _lone_operative_target_allowed(
    *,
    scenario: BattlefieldScenario,
    attacker_unit: UnitInstance,
    target_unit: UnitInstance,
    target_unit_id: str,
) -> bool:
    target_distance = _closest_distance_between_units(
        scenario=scenario,
        first_unit_id=attacker_unit.unit_instance_id,
        second_unit_id=target_unit_id,
    )
    if target_distance > 12.0:
        return False
    attacker_owner = _player_id_for_unit(scenario, attacker_unit.unit_instance_id)
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == attacker_owner:
            continue
        for unit_placement in placed_army.unit_placements:
            if unit_placement.unit_instance_id == target_unit.unit_instance_id:
                continue
            other_distance = _closest_distance_between_units(
                scenario=scenario,
                first_unit_id=attacker_unit.unit_instance_id,
                second_unit_id=unit_placement.unit_instance_id,
            )
            if other_distance + 1e-9 < target_distance:
                return False
    return True


def _closest_distance_between_units(
    *,
    scenario: BattlefieldScenario,
    first_unit_id: str,
    second_unit_id: str,
) -> float:
    first_placement = scenario.battlefield_state.unit_placement_by_id(first_unit_id)
    second_placement = scenario.battlefield_state.unit_placement_by_id(second_unit_id)
    first_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=first_placement,
    )
    second_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=second_placement,
    )
    distances = tuple(
        DistanceMeasurementContext.from_models(first_model, second_model).closest_distance_inches()
        for first_model in first_models
        for second_model in second_models
    )
    if not distances:
        raise GameLifecycleError("Distance between units requires placed models.")
    return min(distances)


def _unit_has_vehicle_or_monster_keyword(unit: UnitInstance) -> bool:
    return _unit_has_keyword(unit, "VEHICLE") or _unit_has_keyword(unit, "MONSTER")


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return canonical in {_canonical_keyword(unit_keyword) for unit_keyword in unit.keywords}


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


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


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
