"""Witnessed, symmetric deemed contact, distinct from geometric measurements.

Only the engine supplies a source rule and a completed legal movement query.
Unresolved feasibility remains an error; a failed search is never a certificate.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from typing import TypedDict

from warhammer40k_core.geometry.base_contact_proof import (
    closer_body_endpoint_exists,
    contact_constraints_exclude_endpoint,
)
from warhammer40k_core.geometry.endpoint_support import endpoint_support_elevations
from warhammer40k_core.geometry.movement_query_payloads import (
    MovementQueryPayload,
    query_from_payload,
    query_payload,
)
from warhammer40k_core.geometry.movement_reachability import (
    MovementGoal,
    MovementReachabilityQuery,
    MovementReachabilityStatus,
    movement_reachability,
)
from warhammer40k_core.geometry.pathing import PathWitness, PathWitnessPayload
from warhammer40k_core.geometry.physical_model import (
    model_parts_within,
    models_overlap_physically,
)
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.validation import IdentifierValidator
from warhammer40k_core.geometry.volume import Model

_EPSILON = 1e-8


class BaseContactUnresolved(GeometryError):
    """The ordinary movement solver could not certify an overhang condition."""


class DeemedBaseContactPayload(TypedDict):
    source_rule_id: str
    enemy_model_id: str
    movement_query: MovementQueryPayload
    without_overhang_witness: PathWitnessPayload


def supported_elevations(query: MovementReachabilityQuery) -> tuple[float, ...]:
    return endpoint_support_elevations(
        terrain=query.terrain_context.terrain, features=query.terrain_context.terrain_features
    )


@dataclass(frozen=True, slots=True)
class DeemedBaseContact:
    source_rule_id: str
    enemy_model_id: str
    movement_query: MovementReachabilityQuery
    without_overhang_witness: PathWitness

    def __post_init__(self) -> None:
        validator = IdentifierValidator(GeometryError)
        validator("deemed base contact source_rule_id", self.source_rule_id)
        validator("deemed base contact enemy_model_id", self.enemy_model_id)
        if (
            type(self.movement_query) is not MovementReachabilityQuery
            or type(self.without_overhang_witness) is not PathWitness
        ):
            raise GeometryError("Deemed base contact requires typed movement evidence.")

    @property
    def moving_model_id(self) -> str:
        return self.movement_query.path_context.moving_model.model_id

    @property
    def pair(self) -> frozenset[str]:
        return frozenset((self.moving_model_id, self.enemy_model_id))

    def to_payload(self) -> DeemedBaseContactPayload:
        return {
            "source_rule_id": self.source_rule_id,
            "enemy_model_id": self.enemy_model_id,
            "movement_query": query_payload(self.movement_query),
            "without_overhang_witness": self.without_overhang_witness.to_payload(),
        }

    @classmethod
    def from_payload(cls, raw: DeemedBaseContactPayload) -> DeemedBaseContact:
        if frozenset(raw) != DeemedBaseContactPayload.__required_keys__:
            raise GeometryError("Deemed base contact evidence fields drifted.")
        result = cls(
            source_rule_id=raw["source_rule_id"],
            enemy_model_id=raw["enemy_model_id"],
            movement_query=query_from_payload(raw["movement_query"]),
            without_overhang_witness=PathWitness.from_payload(raw["without_overhang_witness"]),
        )
        if result != establish_deemed_base_contact(
            query=result.movement_query,
            enemy_model_id=result.enemy_model_id,
            source_rule_id=result.source_rule_id,
        ):
            raise GeometryError("Deemed base contact evidence does not prove its conditions.")
        return result

    def continues(
        self, first: Model, second: Model, *, current_query: MovementReachabilityQuery | None = None
    ) -> bool:
        if frozenset((first.model_id, second.model_id)) != self.pair:
            return False
        mover, enemy = (
            (first, second) if first.model_id == self.moving_model_id else (second, first)
        )
        query = self.movement_query
        original = query.path_context.moving_model
        original_enemy = next(
            m for m in query.path_context.enemy_models if m.model_id == self.enemy_model_id
        )
        if (
            replace(mover, pose=original.pose) != original
            or replace(enemy, pose=original_enemy.pose) != original_enemy
        ):
            raise GeometryError("Deemed base contact model geometry drifted.")
        if not model_parts_within(mover, enemy, 1.0) or models_overlap_physically(mover, enemy):
            return False
        budget = query.path_context.movement_distance_budget_inches
        if budget is None:
            raise GeometryError("Deemed base contact budget is absent.")
        evidence = query if current_query is None else current_query
        if not closer_body_endpoint_exists(
            mover, enemy, budget, mover.range_to(enemy), supported_elevations(evidence)
        ):
            return True
        if current_query is None:
            raise BaseContactUnresolved("Continuing contact requires current battlefield evidence.")
        if current_query.path_context.moving_model != mover or enemy not in (
            current_query.path_context.enemy_models
        ):
            raise GeometryError("Continuing contact geometry differs from its current query.")
        closer = movement_reachability(
            replace(
                current_query,
                goal=MovementGoal(
                    models=(enemy,), range_inches=max(0.0, mover.range_to(enemy) - _EPSILON)
                ),
                maximum_target_range_inches=mover.range_to(enemy) - _EPSILON,
            )
        )
        if closer.status is MovementReachabilityStatus.UNRESOLVED:
            raise BaseContactUnresolved("Continuing closest overhang endpoint is unresolved.")
        return closer.status is not MovementReachabilityStatus.REACHABLE


@lru_cache(maxsize=512)
def establish_deemed_base_contact(
    *,
    query: MovementReachabilityQuery,
    enemy_model_id: str,
    source_rule_id: str,
) -> DeemedBaseContact | None:
    source = query.path_context.moving_model
    enemies = {m.model_id: m for m in query.path_context.enemy_models}
    if enemy_model_id not in enemies:
        raise GeometryError("Deemed base contact requires an enemy in the actual movement query.")
    enemy = enemies[enemy_model_id]
    end = replace(source, pose=query.path_context.witness.final_pose_for_model(source.model_id))
    if (
        not query.path_context.may_end_in_enemy_engagement
        or not enemy.body_parts
        or end.range_to(enemy) <= _EPSILON
        or not model_parts_within(end, enemy, 1.0)
    ):
        return None
    if not query.path_context.validate().is_valid or not query.terrain_context.validate().is_valid:
        raise GeometryError("Deemed base contact requires a valid actual PathWitness.")
    budget = query.path_context.movement_distance_budget_inches
    if budget is None:
        raise GeometryError("Deemed base contact requires its move budget.")
    # Base contact necessarily engages its enemy. Source-forbidden targets can
    # never supply a legal counterfactual, including Objective Consolidation.
    if any(enemy_model_id in {m.model_id for m in g.models} for g in query.forbidden_goals):
        return None
    bare_enemy = replace(enemy, body_parts=())
    counterfactual = replace(
        query,
        path_context=replace(
            query.path_context,
            enemy_models=tuple(
                bare_enemy if m.model_id == enemy_model_id else m
                for m in query.path_context.enemy_models
            ),
        ),
        goal=MovementGoal(models=(bare_enemy,), range_inches=1e-9),
        maximum_target_range_inches=None,
    )
    if contact_constraints_exclude_endpoint(counterfactual):
        return None
    reachable = movement_reachability(counterfactual)
    if reachable.status in {
        MovementReachabilityStatus.UNREACHABLE,
        MovementReachabilityStatus.ENDPOINT_UNREACHABLE,
    }:
        return None
    if reachable.witness is None:
        raise BaseContactUnresolved("Without-overhang base contact reachability is unresolved.")
    distance = end.range_to(enemy)
    if closer_body_endpoint_exists(source, enemy, budget, distance, supported_elevations(query)):
        closer = movement_reachability(
            replace(
                query,
                goal=MovementGoal(models=(enemy,), range_inches=max(0.0, distance - _EPSILON)),
                maximum_target_range_inches=distance - _EPSILON,
            )
        )
        if closer.status is MovementReachabilityStatus.REACHABLE:
            return None
        if closer.status is MovementReachabilityStatus.UNRESOLVED:
            raise BaseContactUnresolved("Closest overhang endpoint reachability is unresolved.")
    return DeemedBaseContact(source_rule_id, enemy_model_id, query, reachable.witness)


def models_in_base_contact(
    first: Model,
    second: Model,
    contacts: tuple[DeemedBaseContact, ...] = (),
    *,
    epsilon: float = 1e-9,
) -> bool:
    return first.range_to(second) <= epsilon or any(c.continues(first, second) for c in contacts)
