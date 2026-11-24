"""Small, deterministic ground Charge Move proposal search over the actor view."""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from enum import StrEnum
from itertools import pairwise, zip_longest
from typing import Protocol, cast

from warhammer40k_core.adapters.projection import ModelDisplayPayload
from warhammer40k_core.ai.player_policy import (
    CandidateExhaustedError,
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    PolicyRoute,
    payload_digest,
)
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.charge_phase_state import ChargeTargetSelection
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase
from warhammer40k_core.geometry.model_geometry import ModelGeometry, ModelGeometryPayload
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.polygons import Point2D
from warhammer40k_core.geometry.pose import Point3, Pose, PosePayload
from warhammer40k_core.geometry.shapely_backend import (
    FootprintGeometry,
    footprint_for_base,
    footprint_for_polygon_union,
    footprint_for_terrain,
)
from warhammer40k_core.geometry.terrain import TerrainWallDefinition
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification

GROUND_CHARGE_GENERATOR_ID = "actor-ground-charge-formation-v1"
MAX_RAW_CANDIDATES = 32
MAX_ACCEPTED_CANDIDATES = 16
MAX_GEOMETRY_WORK = 600_000
_GRID_STEP_INCHES = 0.25
_MAX_GRID_RADIUS = 24
_MAX_OBSTACLES = 256
_PREFERRED_GAP_INCHES = 1.0
_MIN_TARGET_GAP_INCHES = 0.025
_COHERENCY_GAP_INCHES = 2.0
_ENDPOINT_TERRAIN_CLEARANCE_INCHES = 0.05
_GROUP_GRID_STEP_INCHES = 0.5
_GROUP_MAX_SPAN_INCHES = 9.0
_MAX_OBJECTIVE_AREA_VERTICES = 256
_MAX_OBJECTIVE_VERTICES = 4096

type _Bounds = tuple[float, float, float, float]


class ChargeSearchStop(StrEnum):
    COMPLETE = "complete"
    RAW_LIMIT = "raw_limit"
    GEOMETRY_LIMIT = "geometry_limit"
    VALIDATION_LIMIT = "validation_limit"
    ACCEPTED_LIMIT = "accepted_limit"
    NATIVE_TIMEOUT = "native_timeout"


@dataclass(frozen=True, slots=True)
class ChargeSearchCounts:
    raw: int = 0
    geometry_work: int = 0
    accepted: int = 0
    rejected: int = 0
    timed_out: int = 0


class GroundChargeExhaustedError(CandidateExhaustedError):
    def __init__(self, reason: ChargeSearchStop, counts: ChargeSearchCounts) -> None:
        self.reason = reason
        self.counts = counts
        super().__init__(f"Ground Charge Move candidates exhausted ({reason}): {asdict(counts)}.")


def ground_charge_route(actor_id: str) -> PolicyRoute:
    return PolicyRoute(
        actor_id, MOVEMENT_PROPOSAL_DECISION_TYPE, "battle", None, "charge", "charge_move"
    )


@dataclass(frozen=True, slots=True)
class GroundChargeCandidate:
    action: PolicyAction
    longest_path_inches: float
    total_path_inches: float
    waypoint_count: int
    objective_reach: int = 0

    @property
    def candidate_id(self) -> str:
        return payload_digest(self.action.proposal_json)


@dataclass(frozen=True, slots=True)
class GroundChargeCandidates:
    candidates: tuple[GroundChargeCandidate, ...]
    geometry_work: int
    stop: ChargeSearchStop


@dataclass(frozen=True, slots=True)
class _Placed:
    model_id: str
    unit_id: str
    pose: Pose
    base: BaseShape
    footprint: FootprintGeometry


@dataclass(frozen=True, slots=True)
class _Path:
    poses: tuple[Pose, ...]
    end: FootprintGeometry
    sweeps: tuple[FootprintGeometry, ...]
    distance: float
    gap: float
    objectives: frozenset[int] = frozenset()


class _HullGeometry(Protocol):
    @property
    def convex_hull(self) -> FootprintGeometry: ...


class _Work:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0

    def step(self, amount: int = 1) -> None:
        if amount > self.limit - self.used:
            self.used = self.limit
            raise GroundChargeExhaustedError(
                ChargeSearchStop.GEOMETRY_LIMIT, ChargeSearchCounts(geometry_work=self.used)
            )
        self.used += amount


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise PolicyError("Ground charge requires structured actor geometry.")
    return value


def _items(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise PolicyError("Ground charge requires an ordered actor geometry list.")
    return value


def _identifier(value: JsonValue) -> str:
    if not isinstance(value, str) or not value:
        raise PolicyError("Ground charge requires visible entity identifiers.")
    return value


def _number(value: JsonValue) -> float:
    if type(value) is not int and type(value) is not float:
        raise PolicyError("Ground charge requires finite distances.")
    try:
        number = float(value)
    except OverflowError as exc:
        raise PolicyError("Ground charge requires finite distances.") from exc
    if not math.isfinite(number):
        raise PolicyError("Ground charge requires finite distances.")
    return number


def _bounded_int(value: int, maximum: int) -> None:
    if type(value) is not int or not 0 <= value <= maximum:
        raise PolicyError(f"Ground charge count limit must be in [0, {maximum}].")


def _model_placements(battlefield: dict[str, JsonValue]) -> tuple[dict[str, JsonValue], ...]:
    placed = tuple(
        _object(model)
        for army in _items(battlefield["placed_armies"])
        for unit in _items(_object(army)["unit_placements"])
        for model in _items(_object(unit)["model_placements"])
    )
    if len(placed) > _MAX_OBSTACLES:
        raise PolicyError("Ground charge visible model inventory exceeds its supported scope.")
    return placed


def _placed_models(
    placed: tuple[dict[str, JsonValue], ...], displays: dict[str, ModelDisplayPayload]
) -> tuple[_Placed, ...]:
    models: list[_Placed] = []
    for model in placed:
        model_id = _identifier(model["model_instance_id"])
        display = displays[model_id]
        if display["geometry"] is None:
            raise PolicyError("Ground charge requires a visible footprint for each placed model.")
        geometry = ModelGeometry.from_payload(cast(ModelGeometryPayload, display["geometry"]))
        if len(geometry.parts) != 1:
            raise PolicyError("Ground charge requires single-part visible model footprints.")
        base = geometry.base_shape()
        pose = Pose.from_payload(cast(PosePayload, model["pose"]))
        models.append(
            _Placed(
                model_id,
                _identifier(model["unit_instance_id"]),
                pose,
                base,
                footprint_for_base(base, pose),
            )
        )
    return tuple(models)


def _blocked(
    shape: FootprintGeometry, obstacles: tuple[FootprintGeometry, ...], work: _Work
) -> bool:
    left, bottom, right, top = shape.bounds
    for obstacle in obstacles:
        work.step()
        x_min, y_min, x_max, y_max = obstacle.bounds
        if right < x_min or x_max < left or top < y_min or y_max < bottom:
            continue
        if shape.intersects(obstacle):
            return True
    return False


def _at(model: _Placed, x: float, y: float) -> Pose:
    return Pose(Point3(x, y, model.pose.position.z), model.pose.facing)


def _waypoints(model: _Placed, end: Pose) -> Iterator[Pose]:
    start = model.pose.position
    dx, dy = end.position.x - start.x, end.position.y - start.y
    distance = math.hypot(dx, dy)
    if distance == 0:
        return
    span = model.base.max_radius()
    for fraction in (0.5, 0.75, 0.875, 0.25):
        for offset in (span, -span, 2 * span, -2 * span):
            yield _at(
                model,
                start.x + fraction * dx - offset * dy / distance,
                start.y + fraction * dy + offset * dx / distance,
            )


def _near_solid_endpoint(bounds: _Bounds, solids: tuple[_Bounds, ...], work: _Work) -> bool:
    left, bottom, right, top = bounds
    clearance = _ENDPOINT_TERRAIN_CLEARANCE_INCHES
    for xmin, ymin, xmax, ymax in solids:
        work.step()
        if (
            left - clearance <= xmax
            and xmin <= right + clearance
            and bottom - clearance <= ymax
            and ymin <= top + clearance
        ):
            return True
    return False


def _feature_bounds(feature: dict[str, JsonValue]) -> _Bounds:
    x = _number(feature["footprint_center_x_inches"])
    y = _number(feature["footprint_center_y_inches"])
    rx = _number(feature["footprint_width_inches"]) / 2
    ry = _number(feature["footprint_depth_inches"]) / 2
    return x - rx, y - ry, x + rx, y + ry


def _local_blockers(
    model: _Placed, blockers: tuple[FootprintGeometry, ...], budget: float, work: _Work
) -> tuple[FootprintGeometry, ...]:
    start_x, start_y = model.pose.position.x, model.pose.position.y
    extent = budget + model.base.max_radius()
    nearby: list[FootprintGeometry] = []
    for obstacle in blockers:
        work.step()
        xmin, ymin, xmax, ymax = obstacle.bounds
        if (
            start_x - extent <= xmax
            and xmin <= start_x + extent
            and start_y - extent <= ymax
            and ymin <= start_y + extent
        ):
            nearby.append(obstacle)
    return tuple(nearby)


def _paths(
    model: _Placed,
    target: _Placed,
    blockers: tuple[FootprintGeometry, ...],
    solid_bounds: tuple[_Bounds, ...],
    width: float,
    depth: float,
    budget: float,
    work: _Work,
) -> tuple[_Path, ...]:
    radius = math.ceil(
        (target.base.max_radius() + model.base.max_radius() + _PREFERRED_GAP_INCHES)
        / _GRID_STEP_INCHES
    )
    if radius > _MAX_GRID_RADIUS:
        raise PolicyError("Ground charge target footprint exceeds the endpoint grid scope.")
    target_x, target_y = target.pose.position.x, target.pose.position.y
    local_blockers = _local_blockers(model, blockers, budget, work)
    options: list[_Path] = []
    for ix in range(-radius, radius + 1):
        for iy in range(-radius, radius + 1):
            work.step()
            end = _at(model, target_x + ix * _GRID_STEP_INCHES, target_y + iy * _GRID_STEP_INCHES)
            direct_distance = model.pose.distance_3d_to(end)
            if not 0 < direct_distance <= budget:
                continue
            footprint = footprint_for_base(model.base, end)
            gap = footprint.distance(target.footprint)
            if not _MIN_TARGET_GAP_INCHES <= gap <= _PREFERRED_GAP_INCHES:
                continue
            xmin, ymin, xmax, ymax = footprint.bounds
            if xmin < 0 or ymin < 0 or xmax > width or ymax > depth:
                continue
            # Prefer a clear landing away from the visible limits of Solid.
            # This cheap screen does not certify terrain legality.
            if _near_solid_endpoint(footprint.bounds, solid_bounds, work):
                continue
            detours = 0
            for waypoint in (None, *_waypoints(model, end)):
                work.step()
                poses: tuple[Pose, ...]
                footprints: tuple[FootprintGeometry, ...]
                if waypoint is None:
                    poses = (model.pose, end)
                    footprints = (model.footprint, footprint)
                    distance = direct_distance
                else:
                    distance = model.pose.distance_3d_to(waypoint) + waypoint.distance_3d_to(end)
                    if distance > budget:
                        continue
                    poses = (model.pose, waypoint, end)
                    middle = footprint_for_base(model.base, waypoint)
                    xmin, ymin, xmax, ymax = middle.bounds
                    if xmin < 0 or ymin < 0 or xmax > width or ymax > depth:
                        continue
                    footprints = (model.footprint, middle, footprint)
                sweeps = tuple(
                    cast(_HullGeometry, left.union(right)).convex_hull
                    for left, right in pairwise(footprints)
                )
                if any(_blocked(sweep, local_blockers, work) for sweep in sweeps):
                    continue
                options.append(_Path(poses, footprint, sweeps, distance, gap))
                if waypoint is not None:
                    detours += 1
                    if detours == 2:
                        break
    return tuple(sorted(options, key=lambda path: (len(path.poses), -path.gap, path.distance)))


def _formations(
    domains: dict[int, tuple[_Path, ...]],
    placed: dict[int, _Path],
    work: _Work,
    *,
    group: bool = False,
) -> Iterator[tuple[_Path, ...]]:
    if not domains:
        formation = tuple(path for _, path in sorted(placed.items()))
        distances: dict[tuple[int, int], float] = {}
        for index, first in enumerate(formation):
            for other_index in range(index + 1, len(formation)):
                if group:
                    work.step()
                distances[index, other_index] = first.end.distance(formation[other_index].end)
        if group:
            if _connected_group(len(formation), distances, work):
                yield formation
            return
        if all(
            any(gap <= _COHERENCY_GAP_INCHES and index in pair for pair, gap in distances.items())
            for index in range(len(formation))
        ):
            yield formation
        return
    index = min(domains, key=lambda slot: (len(domains[slot]), slot))
    for path in domains[index]:
        work.step()
        remaining: dict[int, tuple[_Path, ...]] = {}
        for other_index, other_paths in domains.items():
            if index == other_index:
                continue
            compatible: list[_Path] = []
            for other in other_paths:
                earlier, later = (path, other) if index < other_index else (other, path)
                if not _blocked(earlier.end, later.sweeps, work):
                    compatible.append(other)
            if not compatible:
                break
            remaining[other_index] = tuple(compatible)
        else:
            yield from _formations(remaining, {**placed, index: path}, work, group=group)


def _connected_group(
    model_count: int, distances: dict[tuple[int, int], float], work: _Work
) -> bool:
    if max(distances.values()) > _GROUP_MAX_SPAN_INCHES:
        return False
    connected = {0}
    while True:
        work.step()
        next_connected = connected | {
            index
            for (first, second), gap in distances.items()
            if gap <= _COHERENCY_GAP_INCHES and {first, second} & connected
            for index in (first, second)
        }
        if next_connected == connected:
            return len(connected) == model_count
        connected = next_connected


def _objective_areas(mission_payload: JsonValue, work: _Work) -> tuple[FootprintGeometry, ...]:
    mission = _object(mission_payload)
    definitions = _items(mission["objective_terrain_areas"])
    areas = _items(mission["terrain_areas"])
    message = "Ground charge objective inventory exceeds its supported scope."
    if max(len(definitions), len(areas)) > _MAX_OBSTACLES:
        raise PolicyError(message)
    polygons: dict[str, tuple[Point2D, ...]] = {}
    vertex_count = 0
    for area in map(_object, areas):
        points = _items(area["footprint_polygon"])
        vertex_count += len(points)
        if len(points) > _MAX_OBJECTIVE_AREA_VERTICES or vertex_count > _MAX_OBJECTIVE_VERTICES:
            raise PolicyError(message)
        work.step(1 + len(points))
        polygons[_identifier(area["terrain_area_id"])] = tuple(
            (_number(point["x_inches"]), _number(point["y_inches"]))
            for point in map(_object, points)
        )
    linked: list[tuple[tuple[Point2D, ...], ...]] = []
    linked_vertices = 0
    geometry_work = 0
    for definition in map(_object, definitions):
        keys = _items(definition["terrain_area_ids"])
        if len(keys) > _MAX_OBSTACLES:
            raise PolicyError(message)
        work.step(1 + len(keys))
        if not keys:
            continue
        footprints = tuple(polygons[_identifier(key)] for key in keys)
        vertices = sum(map(len, footprints))
        linked_vertices += vertices
        if linked_vertices > _MAX_OBJECTIVE_VERTICES:
            raise PolicyError(message)
        geometry_work += vertices * vertices
        linked.append(footprints)
    # The footprint backend eagerly checks polygon edges pairwise before union.
    work.step(geometry_work)
    return tuple(footprint_for_polygon_union(footprints) for footprints in linked)


def _group_endpoints(
    model: _Placed, targets: tuple[_Placed, ...], budget: float, work: _Work
) -> Iterator[Pose]:
    step = _GROUP_GRID_STEP_INCHES
    start = model.pose.position
    offsets: set[tuple[int, int]] = set()
    for target in targets:
        center = target.pose.position
        reach = target.base.max_radius() + model.base.max_radius() + _PREFERRED_GAP_INCHES
        for x in range(
            math.ceil(max(-budget, center.x - start.x - reach) / step),
            math.floor(min(budget, center.x - start.x + reach) / step) + 1,
        ):
            for y in range(
                math.ceil(max(-budget, center.y - start.y - reach) / step),
                math.floor(min(budget, center.y - start.y + reach) / step) + 1,
            ):
                work.step()
                offsets.add((x, y))
    for x, y in sorted(offsets):
        if 0 < math.hypot(x * step, y * step) <= budget:
            yield _at(model, start.x + x * step, start.y + y * step)


def _within_board(footprint: FootprintGeometry, width: float, depth: float) -> bool:
    xmin, ymin, xmax, ymax = footprint.bounds
    return xmin >= 0 and ymin >= 0 and xmax <= width and ymax <= depth


def _group_paths(
    model: _Placed,
    targets: tuple[_Placed, ...],
    blockers: tuple[FootprintGeometry, ...],
    objectives: tuple[FootprintGeometry, ...],
    board: tuple[float, float],
    budget: float,
    work: _Work,
) -> tuple[_Path, ...]:
    width, depth = board
    local = _local_blockers(model, blockers, budget, work)
    start_gap = min(model.footprint.distance(target.footprint) for target in targets)
    options: list[_Path] = []
    for end in _group_endpoints(model, targets, budget, work):
        footprint = footprint_for_base(model.base, end)
        if not _within_board(footprint, width, depth):
            continue
        gap = min(footprint.distance(target.footprint) for target in targets)
        if not _MIN_TARGET_GAP_INCHES <= gap <= _PREFERRED_GAP_INCHES or gap >= start_gap:
            continue
        if _blocked(footprint, local, work):
            continue
        reached: set[int] = set()
        for i, objective in enumerate(objectives):
            work.step()
            if footprint.intersects(objective):
                reached.add(i)
        for waypoint in (None, *_waypoints(model, end)):
            work.step()
            poses = (model.pose, end) if waypoint is None else (model.pose, waypoint, end)
            distance = sum(a.distance_3d_to(b) for a, b in pairwise(poses))
            if distance > budget:
                continue
            footprints: tuple[FootprintGeometry, ...] = (model.footprint, footprint)
            if waypoint is not None:
                middle = footprint_for_base(model.base, waypoint)
                if not _within_board(middle, width, depth):
                    continue
                footprints = (model.footprint, middle, footprint)
            sweeps = tuple(
                cast(_HullGeometry, a.union(b)).convex_hull for a, b in pairwise(footprints)
            )
            if not any(_blocked(sweep, local, work) for sweep in sweeps):
                options.append(_Path(poses, footprint, sweeps, distance, gap, frozenset(reached)))
                break
    return tuple(
        sorted(
            options,
            key=lambda path: (
                path.gap > _PREFERRED_GAP_INCHES,
                path.distance,
                path.gap,
            ),
        )
    )


def _group_formations(
    banks: dict[int, tuple[_Path, ...]], work: _Work
) -> Iterator[tuple[_Path, ...]]:
    # Try a distinct one-inch landing region for a mover on a visible objective.
    # Then allow the ordinary finite search when those anchors are unavailable.
    anchors: dict[tuple[int, int, int], _Path] = {}
    for slot, paths in banks.items():
        for path in paths:
            if path.objectives:
                end = path.poses[-1].position
                anchors.setdefault((slot, math.floor(end.x), math.floor(end.y)), path)
    seen: set[tuple[tuple[Pose, ...], ...]] = set()
    for (slot, _, _), path in sorted(
        anchors.items(),
        key=lambda pair: (
            pair[1].distance,
            pair[0],
        ),
    ):
        formation = next(_formations({**banks, slot: (path,)}, {}, work, group=True), None)
        if formation is not None:
            key = tuple(p.poses for p in formation)
            if key not in seen:
                seen.add(key)
                yield formation
    for formation in _formations(banks, {}, work, group=True):
        if tuple(p.poses for p in formation) not in seen:
            yield formation


def _candidate(
    context: PlayerDecisionContext,
    issued: MovementProposalRequest,
    target_id: str,
    movers: tuple[_Placed, ...],
    formation: tuple[_Path, ...],
) -> GroundChargeCandidate:
    witness = PathWitness.for_paths(
        tuple((model.model_id, path.poses) for model, path in zip(movers, formation, strict=True))
    )
    proposal: JsonValue = validate_json_value(
        ChargeMoveProposal(
            issued.request_id,
            ProposalKind.CHARGE_MOVE,
            issued.unit_instance_id,
            "charge_move",
            MovementMode.CHARGE,
            (target_id,),
            witness,
        ).to_payload()
    )
    return GroundChargeCandidate(
        context.propose(proposal),
        max(path.distance for path in formation),
        sum(path.distance for path in formation),
        sum(len(path.poses) > 2 for path in formation),
        len({objective for path in formation for objective in path.objectives}),
    )


def _five_model_candidates(
    context: PlayerDecisionContext,
    issued: MovementProposalRequest,
    target_id: str,
    movers: tuple[_Placed, ...],
    targets: tuple[_Placed, ...],
    static: tuple[FootprintGeometry, ...],
    objectives: tuple[FootprintGeometry, ...],
    board: tuple[float, float],
    budget: float,
    work: _Work,
    raw_limit: int,
) -> GroundChargeCandidates:
    candidates: list[GroundChargeCandidate] = []
    stop = ChargeSearchStop.COMPLETE
    try:
        banks = {
            index: _group_paths(
                model,
                targets,
                (*static, *(later.footprint for later in movers[index + 1 :])),
                objectives,
                board,
                budget,
                work,
            )
            for index, model in enumerate(movers)
        }
        for formation in _group_formations(banks, work):
            candidates.append(_candidate(context, issued, target_id, movers, formation))
            if len(candidates) == raw_limit:
                stop = ChargeSearchStop.RAW_LIMIT
                break
    except GroundChargeExhaustedError:
        stop = ChargeSearchStop.GEOMETRY_LIMIT
    if not candidates:
        raise GroundChargeExhaustedError(stop, ChargeSearchCounts(geometry_work=work.used))
    return GroundChargeCandidates(tuple(candidates), work.used, stop)


def _formation_stage(
    domains: dict[int, tuple[_Path, ...]], work: _Work, *, bounded_direct: bool
) -> Iterator[tuple[_Path, ...]]:
    try:
        yield from _formations(domains, {}, work)
    except GroundChargeExhaustedError:
        if not bounded_direct:
            raise


def _interleave(
    direct: list[GroundChargeCandidate], waypoint: list[GroundChargeCandidate]
) -> tuple[GroundChargeCandidate, ...]:
    return tuple(
        candidate
        for pair in zip_longest(waypoint, direct)
        for candidate in pair
        if candidate is not None
    )


def generate_ground_charge_candidates(
    context: PlayerDecisionContext,
    *,
    raw_limit: int = MAX_RAW_CANDIDATES,
    geometry_limit: int = MAX_GEOMETRY_WORK,
) -> GroundChargeCandidates:
    """Emit ordinary proposals. Geometric screens are only search heuristics."""
    _bounded_int(raw_limit, MAX_RAW_CANDIDATES)
    _bounded_int(geometry_limit, MAX_GEOMETRY_WORK)
    view = context.observation
    request = view["pending_decision"]
    if (
        request is None
        or context.route != ground_charge_route(context.route.actor_id)
        or view["viewer_role"] != "player"
        or view["viewer_player_id"] != context.route.actor_id
    ):
        raise PolicyError("Ground charge requires the pending actor's exact Charge Move view.")
    issued = MovementProposalRequest.from_decision_request_payload(request["payload"])
    if (
        issued.request_id != request["request_id"]
        or issued.actor_id != context.route.actor_id
        or issued.proposal_kind is not ProposalKind.CHARGE_MOVE
        or issued.movement_phase_action != "charge_move"
    ):
        raise PolicyError("Ground charge proposal request binding drifted.")
    details = issued.context
    if details is None or details.get("movement_mode") != MovementMode.CHARGE.value:
        raise PolicyError("Ground charge requires the ordinary ground movement mode.")
    target_selection = ChargeTargetSelection.from_payload(details.get("target_selection"))
    if (
        len(target_selection.target_ids) != 1
        or issued.unit_instance_id != target_selection.unit_instance_id
    ):
        raise PolicyError("Ground charge requires one issued target for the moving unit.")
    target_id = target_selection.target_ids[0]
    budget = _number(details["maximum_distance_inches"])
    if budget <= 0:
        raise PolicyError("Ground charge requires a positive issued distance.")
    if raw_limit == 0:
        raise GroundChargeExhaustedError(ChargeSearchStop.RAW_LIMIT, ChargeSearchCounts())
    work = _Work(geometry_limit)
    if not geometry_limit:
        work.step()
    battlefield = _object(view["battlefield_state"])
    placements = _model_placements(battlefield)
    five_models = sum(row["unit_instance_id"] == issued.unit_instance_id for row in placements) == 5
    objectives = _objective_areas(view["mission_setup"], work) if five_models else ()
    models = _placed_models(placements, view["model_display_by_id"])
    movers = tuple(model for model in models if model.unit_id == issued.unit_instance_id)
    if five_models:
        battlefield_view = view["battlefield_view"]
        if battlefield_view is None:
            raise PolicyError("Ground charge requires projected rules-unit identities.")
        projected = battlefield_view["authoritative"]["models_by_id"]
        targets = tuple(
            model
            for model in models
            if (entity := projected.get(model.model_id)) is not None
            and entity["rules_unit_instance_id"] == target_id
            and entity["state"] == "placed"
        )
    else:
        targets = tuple(model for model in models if model.unit_id == target_id)
    if (len(movers), len(targets)) not in ((6, 1), (5, 5)) or any(
        type(model.base) not in (CircularBase, OvalBase) or model.pose.position.z != 0
        for model in (*movers, *targets)
    ):
        raise PolicyError(
            "Ground charge requires six versus one or five versus five ground models."
        )
    unit_displays = view["unit_display_by_id"]
    mover_display = unit_displays[issued.unit_instance_id]
    if (
        mover_display["owner_player_id"] != context.route.actor_id
        or "FLY" in mover_display["keywords"]
    ):
        raise PolicyError("Ground charge requires an actor-owned ground-only unit.")
    if any(
        view["model_display_by_id"][model.model_id]["wounds_remaining"] in (None, 0)
        for model in (*movers, *targets)
    ):
        raise PolicyError("Ground charge requires visible surviving participants.")
    # Nearest-first physical execution. Stable coordinate keys precede IDs.
    movers = tuple(
        sorted(
            movers,
            key=lambda model: (
                min(model.pose.distance_3d_to(target.pose) for target in targets),
                model.pose.position.x,
                model.pose.position.y,
                model.model_id,
            ),
        )
    )
    features = tuple(map(_object, _items(battlefield["terrain_features"])))
    wall_rows = [
        (feature["feature_id"], wall) for feature in features for wall in _items(feature["walls"])
    ]
    if len(features) > _MAX_OBSTACLES or len(wall_rows) > _MAX_OBSTACLES:
        raise PolicyError("Ground charge visible terrain inventory exceeds its supported scope.")
    walls = [
        TerrainWallDefinition.from_payload(wall).to_terrain_volume(
            feature_id=_identifier(feature_id)
        )
        for feature_id, wall in wall_rows
    ]
    solid_bounds = tuple(
        _feature_bounds(feature)
        for feature in features
        if feature["classification"]
        in (
            TerrainAreaClassification.DENSE.value,
            TerrainAreaClassification.MIXED.value,
        )
    )
    static = tuple(model.footprint for model in models if model not in movers) + tuple(
        footprint_for_terrain(wall) for wall in walls if wall.bottom_center.z == 0
    )
    width = _number(battlefield["battlefield_width_inches"])
    depth = _number(battlefield["battlefield_depth_inches"])
    if five_models:
        return _five_model_candidates(
            context,
            issued,
            target_id,
            movers,
            targets,
            static,
            objectives,
            (width, depth),
            budget,
            work,
            raw_limit,
        )
    target = targets[0]
    direct: list[GroundChargeCandidate] = []
    waypoint: list[GroundChargeCandidate] = []
    stop = ChargeSearchStop.COMPLETE
    try:
        banks = {
            index: _paths(
                model,
                target,
                (*static, *(later.footprint for later in movers[index + 1 :])),
                solid_bounds,
                width,
                depth,
                budget,
                work,
            )
            for index, model in enumerate(movers)
        }
        direct_banks = {
            index: tuple(path for path in bank if len(path.poses) == 2)
            for index, bank in banks.items()
        }
        direct_quota = max(1, raw_limit // 4)
        direct_work = _Work(min(12_000, (geometry_limit - work.used) // 8))
        for use_waypoints, bank, stage_work in (
            (False, direct_banks, direct_work),
            (True, banks, work),
        ):
            if use_waypoints:
                work.used += direct_work.used
            for formation in _formation_stage(bank, stage_work, bounded_direct=not use_waypoints):
                waypoint_count = sum(len(path.poses) == 3 for path in formation)
                if use_waypoints != (waypoint_count > 0):
                    continue
                group = waypoint if use_waypoints else direct
                group.append(_candidate(context, issued, target_id, movers, formation))
                if len(direct) + len(waypoint) == raw_limit:
                    return GroundChargeCandidates(
                        _interleave(direct, waypoint),
                        work.used + (0 if use_waypoints else direct_work.used),
                        ChargeSearchStop.RAW_LIMIT,
                    )
                if not use_waypoints and len(direct) == direct_quota:
                    break
    except GroundChargeExhaustedError:
        stop = ChargeSearchStop.GEOMETRY_LIMIT
    if not direct and not waypoint:
        raise GroundChargeExhaustedError(stop, ChargeSearchCounts(geometry_work=work.used))
    return GroundChargeCandidates(_interleave(direct, waypoint), work.used, stop)
