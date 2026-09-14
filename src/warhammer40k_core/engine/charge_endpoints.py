from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
)
from warhammer40k_core.engine.charge_model_endpoints import (
    ChargeModelEndpointWitness,
    ChargeModelPathContext,
    charge_model_endpoint_witness,
)
from warhammer40k_core.engine.charge_move_geometry import (
    _closest_distance_between_model_groups,
    _geometry_models_for_unit,
    _geometry_models_for_unit_placement,
    _model_groups_are_engaged,
    _validate_distance_map,
)
from warhammer40k_core.engine.charge_movement_source import ChargePlacement, charge_placement_id
from warhammer40k_core.engine.charge_phase_state import (
    _validate_identifier_tuple,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    scenario_physical_enemy_rules_unit_ids,
)
from warhammer40k_core.geometry.volume import Model as GeometryModel

_validate_identifier = IdentifierValidator(GameLifecycleError)
CHARGE_MOVE_ACTION = "charge_move"


class ChargeEndpointWitnessPayload(TypedDict):
    model_endpoints: list[dict[str, JsonValue]]
    selected_target_unit_instance_ids: list[str]
    target_distances_before_inches: dict[str, float]
    target_distances_after_inches: dict[str, float]
    engaged_target_unit_instance_ids: list[str]
    preferred_distance_target_unit_instance_ids: list[str]
    non_target_engaged_unit_instance_ids: list[str]


@dataclass(frozen=True, slots=True)
class ChargeEndpointWitness:
    model_endpoints: tuple[ChargeModelEndpointWitness, ...]
    selected_target_unit_instance_ids: tuple[str, ...]
    target_distances_before_inches: dict[str, float]
    target_distances_after_inches: dict[str, float]
    engaged_target_unit_instance_ids: tuple[str, ...]
    preferred_distance_target_unit_instance_ids: tuple[str, ...]
    non_target_engaged_unit_instance_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.model_endpoints) is not tuple or any(
            type(row) is not ChargeModelEndpointWitness for row in self.model_endpoints
        ):
            raise GameLifecycleError("Charge endpoint requires typed model evidence.")
        model_ids = tuple(row.model_instance_id for row in self.model_endpoints)
        if model_ids != tuple(sorted(set(model_ids))):
            raise GameLifecycleError("Charge model endpoint identities must be sorted and unique.")
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
            "model_endpoints": [row.to_payload() for row in self.model_endpoints],
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


def _charge_endpoint_witness(
    *,
    scenario: BattlefieldScenario,
    before: ChargePlacement,
    after: ChargePlacement,
    selected_target_unit_instance_ids: tuple[str, ...],
    ruleset_descriptor: RulesetDescriptor,
    model_contexts: dict[str, ChargeModelPathContext],
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
    targets: dict[str, tuple[GeometryModel, ...]] = {}
    for target_id in target_ids:
        target_models = _geometry_models_for_unit(
            scenario=scenario,
            unit_instance_id=target_id,
        )
        targets[target_id] = target_models
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
    for enemy_unit_id in scenario_physical_enemy_rules_unit_ids(
        scenario=scenario,
        unit_instance_id=charge_placement_id(after),
    ):
        if enemy_unit_id in selected_target_set:
            continue
        if _model_groups_are_engaged(
            first_models=after_models,
            second_models=_geometry_models_for_unit(
                scenario=scenario,
                unit_instance_id=enemy_unit_id,
            ),
            horizontal_inches=policy.horizontal_inches,
            vertical_inches=policy.vertical_inches,
        ):
            non_target_engaged_ids.append(enemy_unit_id)
    contexts = model_contexts
    if (
        (
            ruleset_descriptor.charge_policy.must_end_engaged_with_every_selected_target
            and set(engaged_target_ids) != set(target_ids)
        )
        or (
            ruleset_descriptor.charge_policy.forbids_non_target_engagement
            and non_target_engaged_ids
        )
        or (
            ruleset_descriptor.charge_policy.must_end_closer_to_selected_targets
            and any(
                not any(
                    min(final.range_to(t) for t in group) < min(start.range_to(t) for t in group)
                    for group in targets.values()
                )
                for start, final in zip(before_models, after_models, strict=True)
            )
        )
    ):
        contexts = {}
    rows = tuple(
        charge_model_endpoint_witness(
            start=start,
            end=final,
            targets=targets,
            ruleset=ruleset_descriptor,
            context=contexts.get(start.model_id),
            component_unit_instance_id=placement.unit_instance_id,
        )
        for placement, start, final in zip(
            before.model_placements, before_models, after_models, strict=True
        )
        if targets
    )
    return ChargeEndpointWitness(
        model_endpoints=tuple(sorted(rows, key=lambda row: row.model_instance_id)),
        selected_target_unit_instance_ids=target_ids,
        target_distances_before_inches=target_distances_before,
        target_distances_after_inches=target_distances_after,
        engaged_target_unit_instance_ids=tuple(engaged_target_ids),
        preferred_distance_target_unit_instance_ids=tuple(preferred_target_ids),
        non_target_engaged_unit_instance_ids=tuple(non_target_engaged_ids),
    )


def _charge_endpoint_violation_code(
    *,
    endpoint_witness: ChargeEndpointWitness,
    ruleset_descriptor: RulesetDescriptor,
    maximum_distance_inches: float,
) -> str | None:
    selected = endpoint_witness.selected_target_unit_instance_ids
    if not selected:
        return "charge_target_required"
    rows = endpoint_witness.model_endpoints
    if not rows:
        raise GameLifecycleError("Charge endpoint requires its complete model evidence.")
    if ruleset_descriptor.charge_policy.must_end_closer_to_selected_targets and any(
        not row.ended_closer for row in rows
    ):
        return "charge_not_closer_to_target"
    if ruleset_descriptor.charge_policy.must_end_engaged_with_every_selected_target and (
        set(selected) - set(endpoint_witness.engaged_target_unit_instance_ids)
    ):
        return "charge_target_not_engaged"
    if (
        ruleset_descriptor.charge_policy.forbids_non_target_engagement
        and endpoint_witness.non_target_engaged_unit_instance_ids
    ):
        return "charge_non_target_engaged"
    for row in rows:
        violation = row.violation(ruleset_descriptor)
        if violation is not None:
            return violation
    return None


__all__ = (
    "ChargeEndpointWitness",
    "ChargeEndpointWitnessPayload",
    "_charge_endpoint_violation_code",
    "_charge_endpoint_witness",
)
