"""Actor-visible tactical inputs for the opt-in Stage 4 development linker."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import cast

from scripts import stage4_benchmark_entry as bench
from warhammer40k_core.adapters.battlefield_projection import BattlefieldModelEntityPayload
from warhammer40k_core.adapters.projection import GameViewPayload, ModelDisplayPayload
from warhammer40k_core.ai.player_policy import PlayerDecisionContext
from warhammer40k_core.core.missions import ObjectiveTerrainAreaDefinitionPayload
from warhammer40k_core.engine.mission_setup import MissionSetupPayload
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    ProposalKind,
)
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    measure_model_to_objective,
)
from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume

TACTICAL_COLUMNS = (
    "visible_contact_oc_margin",
    "acting_unit_gap_inches",
    "other_ally_gap_inches",
    "opponent_gap_inches",
)
FINITE_COLUMNS = ("decision_option_count", *TACTICAL_COLUMNS)
TacticalInputs = tuple[int | None, float | None, float | None, float | None]
UNAVAILABLE: TacticalInputs = (None, None, None, None)


@dataclass(frozen=True, slots=True)
class VisibleModel:
    geometry: Model
    side: str
    objective_control: int | None


def _linked_objectives(view: GameViewPayload) -> tuple[ObjectiveGeometry, ...]:
    mission, battlefield = view["mission_setup"], view["battlefield_view"]
    if not isinstance(mission, dict) or battlefield is None:
        return ()
    links: list[ObjectiveTerrainAreaDefinitionPayload] = cast(MissionSetupPayload, mission)[
        "objective_terrain_areas"
    ]
    areas = battlefield["authoritative"]["terrain_areas_by_id"]
    return tuple(
        ObjectiveGeometry.from_terrain(
            objective_id=link["objective_marker_id"],
            footprint_polygons=tuple(
                tuple(
                    (point["x_inches"], point["y_inches"])
                    for point in areas[area_id]["footprint"]["vertices"]
                )
                for area_id in link["terrain_area_ids"]
            ),
        )
        for link in links
    )


def _model_geometry(
    entity: BattlefieldModelEntityPayload, display: ModelDisplayPayload
) -> Model | None:
    pose = entity["pose"]
    geometry = entity["geometry"]
    shapes = geometry["measurement_shapes"]
    if (
        pose is None
        or len(shapes) != 1
        or display["visible_status"] != "visible"
        or "FRAME" in display["keywords"]
    ):
        return None
    (shape,) = shapes
    center = shape["center"]
    if center is None or center["x_inches"] != 0 or center["y_inches"] != 0:
        return None
    base: BaseShape
    if shape["kind"] == "circle" and shape["radius_inches"] is not None:
        base = CircularBase(shape["radius_inches"])
    elif shape["length_inches"] is not None and shape["width_inches"] is not None:
        length, width = shape["length_inches"], shape["width_inches"]
        if shape["kind"] == "ellipse":
            base = OvalBase(length, width)
        elif shape["kind"] == "rectangle":
            base = RectangularBase(length, width)
        else:
            return None
    else:
        return None
    p = pose["position"]
    return Model(
        entity["model_instance_id"],
        Pose.at(p["x_inches"], p["y_inches"], p["z_inches"], pose["facing_degrees"]),
        base,
        ModelVolume(geometry["height_inches"]),
    )


def tactical_inputs(context: PlayerDecisionContext) -> TacticalInputs:
    """Measure the nearest linked objective at this offer using the detached view."""
    view = context.observation
    request = view["pending_decision"]
    assert request is not None
    route = context.route
    bench.require(
        route.stage == "battle" and route.battle_phase == "movement", "Expected Movement."
    )
    payload = request["payload"]
    if (
        route.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
        and route.proposal_kind == ProposalKind.NORMAL_MOVE
        and isinstance(payload, dict)
    ):
        payload = payload.get("proposal_request")
    else:
        bench.require(
            route.decision_type == bench.MOVE_ACTION and route.proposal_kind is None,
            "Expected a finite movement action or Normal Move child offer.",
        )
    bench.require(
        isinstance(payload, dict) and isinstance(payload.get("unit_instance_id"), str),
        "Movement offer lacks its acting unit.",
    )
    assert isinstance(payload, dict)
    acting_unit = payload["unit_instance_id"]
    board = view["battlefield_view"]
    objectives = _linked_objectives(view)
    if board is None or not objectives:
        return UNAVAILABLE

    models: list[VisibleModel] = []
    for model_id, entity in board["authoritative"]["models_by_id"].items():
        if entity["state"] != "placed":
            continue
        display = view["model_display_by_id"].get(model_id)
        geometry = None if display is None else _model_geometry(entity, display)
        if geometry is None or display is None:
            return UNAVAILABLE
        if entity["owner_player_id"] != route.actor_id:
            side = "opponent"
        elif entity["rules_unit_instance_id"] == acting_unit:
            side = "acting"
        else:
            side = "ally"
        oc = display["current_characteristics"].get("OC")
        visible_oc = None if oc is None or oc["redaction"]["hidden"] else oc["final"]
        models.append(VisibleModel(geometry, side, visible_oc))

    if not any(model.side == "acting" for model in models):
        return UNAVAILABLE
    rows = [_measure_objective(models, objective) for objective in objectives]
    closest = min(row[0] for row in rows)
    nearest = [row for row in rows if row[0] == closest]
    margins = [row[1] for row in nearest]
    return (
        None if None in margins else min(margin for margin in margins if margin is not None),
        round(closest, 4),
        _closest_gap(row[2] for row in nearest),
        _closest_gap(row[3] for row in nearest),
    )


def _measure_objective(
    models: list[VisibleModel], objective: ObjectiveGeometry
) -> tuple[float, int | None, float | None, float | None]:
    gaps: dict[str, list[float]] = {"acting": [], "ally": [], "opponent": []}
    margin: int | None = 0
    for model in models:
        distance = measure_model_to_objective(model=model.geometry, objective=objective)
        gaps[model.side].append(distance.horizontal_distance_inches)
        if distance.within_control_range and margin is not None:
            oc = model.objective_control
            margin = None if oc is None else margin + (-oc if model.side == "opponent" else oc)
    return (
        min(gaps["acting"]),
        margin,
        min(gaps["ally"], default=None),
        min(gaps["opponent"], default=None),
    )


def _closest_gap(values: Iterable[float | None]) -> float | None:
    gap = min((value for value in values if value is not None), default=None)
    return None if gap is None else round(gap, 4)
