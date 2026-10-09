# pyright: reportPrivateUsage=false
"""Engine-owned whole-unit Tactical alternatives for Combat admission.

Positive proposals are merely candidates until the complete ordinary owner
accepts them. A failed candidate search cannot authorize Combat: only a sound
continuous negative certificate can do so. There is deliberately no cache keyed
by the narrower physical-proposal hash.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterator
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    UnitPlacement,
)
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.transport_disembark_geometry import (
    DISEMBARK_POLICY,
    geometry_models_for_unit_placement,
)
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    TransportCargoState,
    _disembark_distance_inches,
)
from warhammer40k_core.geometry.pose import GeometryError, Pose
from warhammer40k_core.geometry.tactical_setup_proof import (
    TacticalSetupProofQuery,
    TacticalSupportRegion,
    TacticalSupportSurface,
    tactical_setup_is_excluded,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
        RulesUnitDisembarkResolution,
        RulesUnitDisembarkSelection,
    )


class TacticalSetupOutcome(StrEnum):
    EXISTS = "exists"
    IMPOSSIBLE = "impossible"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class TacticalSetupFeasibility:
    outcome: TacticalSetupOutcome
    context_sha256: str
    reason: str
    witness: RulesUnitDisembarkResolution | None = None


def tactical_setup_feasibility(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    cargo_state: TransportCargoState,
    selection: RulesUnitDisembarkSelection,
    rules_unit: RulesUnitView,
    transport_placement: UnitPlacement,
    objective_markers: tuple[ObjectiveMarker, ...],
) -> TacticalSetupFeasibility:
    from warhammer40k_core.engine.phases.movement_rules_unit_disembark import (
        resolve_rules_unit_disembark,
    )

    selection.attempted_placement.validate_for_view(rules_unit)
    tactical = replace(selection, disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK)
    context = validate_json_value(
        {
            "scenario": scenario.to_payload(),
            "ruleset": ruleset_descriptor.to_payload(),
            "cargo": cargo_state.to_payload(),
            "rules_unit_id": rules_unit.unit_instance_id,
            "components": list(rules_unit.component_unit_instance_ids),
            "retained_model_ids": list(rules_unit.retained_model_ids),
            "player_id": selection.player_id,
            "battle_round": selection.battle_round,
            "transport_placement": transport_placement.to_payload(),
            "movement_status": selection.transport_movement_status.value,
            "restriction_overrides": [row.to_payload() for row in selection.restriction_overrides],
            "objectives": [marker.to_payload() for marker in objective_markers],
        }
    )
    context_hash = hashlib.sha256(canonical_json(context).encode()).hexdigest()
    transports = geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=transport_placement,
    )
    passengers = selection.attempted_placement.geometry_models(scenario)
    for placement in _candidate_placements(
        selection.attempted_placement, scenario, transport_placement
    ):
        result = resolve_rules_unit_disembark(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            cargo_state=cargo_state,
            selection=replace(tactical, attempted_placement=placement),
            rules_unit=rules_unit,
            transport_placement=transport_placement,
            turn_player_id=selection.player_id,
            objective_markers=objective_markers,
        )
        if result.is_valid:
            return TacticalSetupFeasibility(
                TacticalSetupOutcome.EXISTS,
                context_hash,
                "A complete whole-unit Tactical setup passes the authoritative owner.",
                result,
            )
    own_ids = {model.model_id for model in passengers}
    blockers = tuple(
        model for model in scenario.placed_geometry_models() if model.model_id not in own_ids
    )
    enemies = tuple(
        model
        for army in scenario.battlefield_state.placed_armies
        for placement in army.unit_placements
        if placement.player_id != selection.player_id
        for model in geometry_models_for_unit_placement(scenario=scenario, unit_placement=placement)
    )
    query = TacticalSetupProofQuery(
        passengers=passengers,
        transports=transports,
        blockers=blockers,
        enemies=enemies,
        distance_inches=_disembark_distance_inches(DisembarkModeKind.TACTICAL_DISEMBARK),
        oversized_distance_inches=DISEMBARK_POLICY.maximum_base_distance_inches,
        engagement_horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
        engagement_vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
        support_regions=_support_regions(scenario, ruleset_descriptor),
    )
    try:
        impossible = tactical_setup_is_excluded(query)
    except GeometryError as error:
        return TacticalSetupFeasibility(
            TacticalSetupOutcome.UNRESOLVED,
            context_hash,
            f"Tactical setup proof is unresolved: {error}",
        )
    return TacticalSetupFeasibility(
        TacticalSetupOutcome.IMPOSSIBLE if impossible else TacticalSetupOutcome.UNRESOLVED,
        context_hash,
        "No pose in the continuous superset can satisfy Tactical setup."
        if impossible
        else "No complete verified witness or negative proof is available.",
    )


def _support_regions(
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
) -> tuple[TacticalSupportRegion, ...]:
    regions: list[TacticalSupportRegion] = []
    for feature in scenario.battlefield_state.terrain_features:
        policy = ruleset_descriptor.terrain_movement_policy.policy_for_feature_kind(
            feature.feature_kind
        )
        if not policy.no_overhang_required:
            continue
        x0, y0, x1, y1 = feature.bounds()
        points = feature.rules_footprint_points()
        if len(points) != 4 or set(points) != {(x0, y0), (x1, y0), (x1, y1), (x0, y1)}:
            # A general polygon's enclosing box is not its interior.
            continue
        regions.append(
            TacticalSupportRegion(
                bounds=(x0, y0, x1, y1),
                surfaces=tuple(
                    TacticalSupportSurface(surface.bounds(), surface.z_inches)
                    for surface in feature.support_surfaces(no_overhang_required=True)
                ),
            )
        )
    return tuple(regions)


def _candidate_placements(
    placement: RulesUnitPlacement,
    scenario: BattlefieldScenario,
    transport: UnitPlacement,
) -> Iterator[RulesUnitPlacement]:
    """Finite positive accelerators only; never a negative proof domain."""
    yield placement
    models = placement.geometry_models(scenario)
    count = len(models)
    center_x = sum(model.pose.position.x for model in models) / count
    center_y = sum(model.pose.position.y for model in models) / count
    largest_radius = max(model.base.max_radius() for model in models)
    pitch = 2 * largest_radius + 0.01
    for carrier in geometry_models_for_unit_placement(scenario=scenario, unit_placement=transport):
        # A ring is a useful whole-group positive witness for attached cargo;
        # it is still accepted only by the complete shared placement owner.
        ring_radius = carrier.base.max_radius() + largest_radius + 0.01
        if count > 1:
            ring_radius = max(ring_radius, pitch / (2 * math.sin(math.pi / count)))
        ring = {
            model.model_id: Pose.at(
                carrier.pose.position.x + ring_radius * math.cos(i * math.tau / count),
                carrier.pose.position.y + ring_radius * math.sin(i * math.tau / count),
                carrier.pose.position.z,
            )
            for i, model in enumerate(models)
        }
        yield _with_poses(placement, ring)
        for index in range(16):
            angle = index * math.tau / 16
            cosine, sine = math.cos(angle), math.sin(angle)
            radius = carrier.base.max_radius() + largest_radius + 0.01
            anchor_x = carrier.pose.position.x + radius * cosine
            anchor_y = carrier.pose.position.y + radius * sine
            for layout in ("translated", "line", "two_rows"):
                poses: dict[str, Pose] = {}
                for i, model in enumerate(models):
                    if layout == "translated":
                        x = model.pose.position.x - center_x
                        y = model.pose.position.y - center_y
                    elif layout == "line":
                        x, y = 0.0, (i - (count - 1) / 2) * pitch
                    else:
                        x = (i % 2) * pitch
                        y = (i // 2 - (math.ceil(count / 2) - 1) / 2) * pitch
                    poses[model.model_id] = Pose.at(
                        anchor_x + x * cosine - y * sine,
                        anchor_y + x * sine + y * cosine,
                        carrier.pose.position.z,
                        facing_degrees=math.degrees(angle),
                    )
                yield _with_poses(placement, poses)


def _with_poses(placement: RulesUnitPlacement, poses: dict[str, Pose]) -> RulesUnitPlacement:
    return replace(
        placement,
        component_unit_placements=tuple(
            replace(
                component,
                model_placements=tuple(
                    replace(row, pose=poses[row.model_instance_id])
                    for row in component.model_placements
                ),
            )
            for component in placement.component_unit_placements
        ),
    )
