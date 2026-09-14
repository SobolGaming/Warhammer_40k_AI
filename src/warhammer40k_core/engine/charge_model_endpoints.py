"""Per-model Charge obligations evaluated against validated movement queries."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal, cast

import msgspec

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.movement_reachability import (
    MovementGoal,
    MovementReachabilityQuery,
    movement_reachability,
)
from warhammer40k_core.geometry.pathing import (
    PathValidationContext,
    PathWitness,
    PathWitnessPayload,
    TerrainPathLegalityContext,
)
from warhammer40k_core.geometry.volume import Model
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_charge_2026_09 import (
    CHARGE_ENDPOINT_SOURCE_ID,
)

type EndpointReachabilityStatus = Literal[
    "satisfied", "not_required", "not_evaluated", "reachable", "unreachable", "unresolved"
]


class EndpointReachabilityEvidence(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    status: EndpointReachabilityStatus
    distance_lower_bound_inches: float | None
    alternative_witness: PathWitnessPayload | None

    def __post_init__(self) -> None:
        if self.status not in {
            "satisfied",
            "not_required",
            "not_evaluated",
            "reachable",
            "unreachable",
            "unresolved",
        }:
            raise GameLifecycleError("Charge reachability status is invalid.")
        searched = self.status in {"reachable", "unreachable", "unresolved"}
        if searched != (self.distance_lower_bound_inches is not None):
            raise GameLifecycleError("Charge reachability requires a bound exactly when searched.")
        if self.distance_lower_bound_inches is not None and (
            not math.isfinite(self.distance_lower_bound_inches)
            or self.distance_lower_bound_inches < 0
        ):
            raise GameLifecycleError(
                "Charge reachability lower bound must be finite and nonnegative."
            )
        if (self.alternative_witness is not None) != (self.status == "reachable"):
            raise GameLifecycleError("Charge reachable evidence requires its alternative path.")


class ChargeModelEndpointWitness(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_rule_id: str
    model_instance_id: str
    component_unit_instance_id: str
    target_distances_before_inches: dict[str, float]
    target_distances_after_inches: dict[str, float]
    engaged_target_unit_instance_ids: tuple[str, ...]
    preferred_distance_target_unit_instance_ids: tuple[str, ...]
    preferred_reachability: EndpointReachabilityEvidence
    engagement_reachability: EndpointReachabilityEvidence

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], msgspec.to_builtins(self))

    @classmethod
    def from_payload(cls, value: object) -> ChargeModelEndpointWitness:
        try:
            row = msgspec.convert(value, type=cls, strict=True)
        except (msgspec.ValidationError, TypeError) as exc:
            raise GameLifecycleError("Charge model endpoint evidence schema drifted.") from exc
        for distances in (row.target_distances_before_inches, row.target_distances_after_inches):
            if any(not math.isfinite(d) or d < 0 for d in distances.values()):
                raise GameLifecycleError("Charge model endpoint distance is invalid.")
        return row

    @property
    def ended_closer(self) -> bool:
        return any(
            self.target_distances_after_inches[target] < distance
            for target, distance in self.target_distances_before_inches.items()
        )

    def violation(self, ruleset: RulesetDescriptor) -> str | None:
        policy = ruleset.charge_policy
        if policy.must_end_closer_to_selected_targets and not self.ended_closer:
            return "charge_not_closer_to_target"
        for evidence, required, code in (
            (
                self.preferred_reachability,
                policy.must_reach_preferred_target_distance_if_possible,
                "charge_preferred_distance_not_reached",
            ),
            (
                self.engagement_reachability,
                policy.must_end_engaged_if_possible,
                "charge_model_not_engaged_target",
            ),
        ):
            if not required:
                continue
            if evidence.status == "reachable":
                return code
            if evidence.status == "unresolved":
                return "charge_reachability_unresolved"
        return None


@dataclass(frozen=True, slots=True)
class ChargeModelPathContext:
    component_unit_instance_id: str
    query: MovementReachabilityQuery


def charge_model_endpoint_witness(
    *,
    start: Model,
    end: Model,
    targets: dict[str, tuple[Model, ...]],
    ruleset: RulesetDescriptor,
    context: ChargeModelPathContext | None,
    component_unit_instance_id: str,
) -> ChargeModelEndpointWitness:
    policy = ruleset.charge_policy
    before = {key: min(start.range_to(t) for t in models) for key, models in targets.items()}
    after = {key: min(end.range_to(t) for t in models) for key, models in targets.items()}
    engaged = tuple(
        key
        for key, models in targets.items()
        if MovementGoal(
            models=models,
            horizontal_inches=ruleset.engagement_policy.horizontal_inches,
            vertical_inches=ruleset.engagement_policy.vertical_inches,
        ).contains(end)
    )
    preferred = tuple(
        key
        for key, distance in after.items()
        if distance <= policy.preferred_target_distance_inches
    )
    target_models = tuple(t for models in targets.values() for t in models)
    preferred_goal = MovementGoal(
        models=target_models, range_inches=policy.preferred_target_distance_inches
    )
    engagement_goal = MovementGoal(
        models=target_models,
        horizontal_inches=ruleset.engagement_policy.horizontal_inches,
        vertical_inches=ruleset.engagement_policy.vertical_inches,
    )
    return ChargeModelEndpointWitness(
        source_rule_id=CHARGE_ENDPOINT_SOURCE_ID,
        model_instance_id=start.model_id,
        component_unit_instance_id=component_unit_instance_id,
        target_distances_before_inches=before,
        target_distances_after_inches=after,
        engaged_target_unit_instance_ids=engaged,
        preferred_distance_target_unit_instance_ids=preferred,
        preferred_reachability=_reachability(
            context,
            preferred_goal,
            bool(preferred),
            policy.must_reach_preferred_target_distance_if_possible,
        ),
        engagement_reachability=_reachability(
            context,
            engagement_goal,
            bool(engaged),
            policy.must_end_engaged_if_possible,
            # Replacing this model must retain a preferred endpoint it already achieved.
            extra_goals=(preferred_goal,)
            if preferred and policy.must_reach_preferred_target_distance_if_possible
            else (),
        ),
    )


def _reachability(
    context: ChargeModelPathContext | None,
    goal: MovementGoal,
    satisfied: bool,
    required: bool,
    *,
    extra_goals: tuple[MovementGoal, ...] = (),
) -> EndpointReachabilityEvidence:
    if satisfied:
        return EndpointReachabilityEvidence("satisfied", None, None)
    if not required:
        return EndpointReachabilityEvidence("not_required", None, None)
    if context is None:
        return EndpointReachabilityEvidence("not_evaluated", None, None)
    query = replace(
        context.query, goal=goal, required_goals=(*context.query.required_goals, *extra_goals)
    )
    result = movement_reachability(query)
    lower = goal.distance_lower_bound(
        query.path_context.moving_model,
        ignores_vertical_distance=query.path_context.ignores_vertical_distance,
    )
    return EndpointReachabilityEvidence(
        result.status.value,
        lower,
        None if result.witness is None else result.witness.to_payload(),
    )


def validate_charge_model_endpoint_inventory(
    *,
    value: object,
    witness: PathWitness,
    selected_ids: tuple[str, ...],
    ruleset: RulesetDescriptor,
    maximum_distance_inches: float,
) -> tuple[ChargeModelEndpointWitness, ...]:
    if not isinstance(value, list):
        raise GameLifecycleError("Charge model endpoints must be a list.")
    rows = tuple(ChargeModelEndpointWitness.from_payload(row) for row in cast(list[object], value))
    if tuple(row.model_instance_id for row in rows) != witness.model_ids():
        raise GameLifecycleError("Charge model endpoint inventory drifted.")
    for row in rows:
        if (
            row.source_rule_id != CHARGE_ENDPOINT_SOURCE_ID
            or not row.component_unit_instance_id
            or set(row.target_distances_before_inches) != set(selected_ids)
            or set(row.target_distances_after_inches) != set(selected_ids)
            or row.engaged_target_unit_instance_ids
            != tuple(sorted(set(row.engaged_target_unit_instance_ids) & set(selected_ids)))
            or row.preferred_distance_target_unit_instance_ids
            != tuple(
                sorted(set(row.preferred_distance_target_unit_instance_ids) & set(selected_ids))
            )
            or row.violation(ruleset) is not None
        ):
            raise GameLifecycleError("Charge model endpoint authority drifted.")
        for evidence, required, satisfied in (
            (
                row.preferred_reachability,
                ruleset.charge_policy.must_reach_preferred_target_distance_if_possible,
                bool(row.preferred_distance_target_unit_instance_ids),
            ),
            (
                row.engagement_reachability,
                ruleset.charge_policy.must_end_engaged_if_possible,
                bool(row.engaged_target_unit_instance_ids),
            ),
        ):
            if satisfied:
                valid = evidence.status == "satisfied"
            elif not required:
                valid = evidence.status == "not_required"
            else:
                valid = (
                    evidence.status == "unreachable"
                    and evidence.distance_lower_bound_inches is not None
                    and evidence.distance_lower_bound_inches > maximum_distance_inches + 1e-8
                )
            if not valid:
                raise GameLifecycleError("Charge model endpoint feasibility evidence drifted.")
    return rows


def charge_endpoint_query(
    *,
    path_context: PathValidationContext,
    terrain_context: TerrainPathLegalityContext,
    peers: tuple[Model, ...],
    targets: dict[str, tuple[Model, ...]],
    non_targets: tuple[tuple[Model, ...], ...],
    ruleset: RulesetDescriptor,
) -> MovementReachabilityQuery:
    from warhammer40k_core.core.ruleset_descriptor import CoherencyPolicyKind

    if (
        type(path_context) is not PathValidationContext
        or type(terrain_context) is not TerrainPathLegalityContext
    ):
        raise GameLifecycleError("Charge endpoint search requires validated path contexts.")
    engagement = ruleset.engagement_policy

    def goal(models: tuple[Model, ...]) -> MovementGoal:
        return MovementGoal(
            models=models,
            horizontal_inches=engagement.horizontal_inches,
            vertical_inches=engagement.vertical_inches,
        )

    policy = ruleset.coherency_policy
    neighbors = policy.required_neighbors_small_unit
    if (
        policy.large_unit_model_count_threshold is not None
        and len(peers) + 1 >= policy.large_unit_model_count_threshold
    ):
        neighbors = policy.required_neighbors_large_unit
    if policy.policy_kind is CoherencyPolicyKind.NEIGHBOR_COUNT and (
        neighbors is None
        or policy.max_horizontal_inches is None
        or policy.max_vertical_inches is None
    ):
        raise GameLifecycleError("Charge requires complete neighbor coherency policy.")
    return MovementReachabilityQuery(
        path_context=path_context,
        terrain_context=terrain_context,
        goal=goal(tuple(model for group in targets.values() for model in group)),
        required_goals=tuple(
            goal(group)
            for group in targets.values()
            if ruleset.charge_policy.must_end_engaged_with_every_selected_target
            and not any(goal(group).contains(peer) for peer in peers)
        ),
        forbidden_goals=tuple(goal(group) for group in non_targets)
        if ruleset.charge_policy.forbids_non_target_engagement
        else (),
        closer_target_groups=tuple(targets.values())
        if ruleset.charge_policy.must_end_closer_to_selected_targets
        else (),
        coherent_models=peers,
        coherency_neighbor_count=1 if neighbors is None else neighbors,
        coherency_horizontal_inches=0.0
        if policy.max_horizontal_inches is None
        else policy.max_horizontal_inches,
        coherency_vertical_inches=0.0
        if policy.max_vertical_inches is None
        else policy.max_vertical_inches,
        coherency_max_span_inches=policy.max_unit_span_inches,
        coherency_all_models_distance_inches=policy.max_all_models_distance_inches,
    )
