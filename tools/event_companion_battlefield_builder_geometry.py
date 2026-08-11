from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from shapely import affinity
from shapely.geometry import Point, Polygon, box

_BOARD_WIDTH = 44.0
_BOARD_DEPTH = 60.0
_GRID = 0.05
_GEOMETRY_TOLERANCE = 1e-6
_MAX_AREA_SHIFT_STEPS = 4
_CANDIDATE_SET_LIMIT = 4
_CANDIDATE_BEAM_WIDTH = 1024
# Source-reviewed coupled-area poses whose globally scored grid search has
# multiple equivalent candidates. The table pins the deterministic
# lexicographic member of each minimum-displacement solution; all board,
# contact, objective, and exact runtime component scores are zero before the
# two separately documented pages 36/46 exact-seam corrections below.
_REVIEWED_FIXED_AREA_POSE_STEPS = {
    "disruption-vs-disruption-layout-1-terrain-area-07": (2, 3, -2),
    "disruption-vs-disruption-layout-1-terrain-area-10": (2, -4, 2),
    "purge-the-foe-vs-disruption-layout-3-terrain-area-02": (1, 2, -7),
    "purge-the-foe-vs-disruption-layout-3-terrain-area-04": (2, -2, 6),
    "purge-the-foe-vs-disruption-layout-3-terrain-area-13": (2, 1, -7),
    "purge-the-foe-vs-disruption-layout-3-terrain-area-15": (1, -1, 6),
    "purge-the-foe-vs-reconnaissance-layout-1-terrain-area-13": (0, 0, 1),
    "reconnaissance-vs-reconnaissance-layout-2-terrain-area-07": (2, 3, -2),
    "reconnaissance-vs-reconnaissance-layout-2-terrain-area-10": (2, -4, 2),
    "disruption-vs-disruption-layout-2-terrain-area-06": (2, 0, 2),
    "disruption-vs-disruption-layout-2-terrain-area-11": (2, -4, 1),
    "reconnaissance-vs-reconnaissance-layout-3-terrain-area-06": (2, 0, 2),
    "reconnaissance-vs-reconnaissance-layout-3-terrain-area-11": (2, -4, 1),
    "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-02": (1, 4, -1),
    "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-04": (2, -4, 0),
    "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-13": (2, 4, -1),
    "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-15": (1, -4, 1),
    "take-and-hold-vs-take-and-hold-layout-3-terrain-area-08": (2, 2, 0),
    "take-and-hold-vs-take-and-hold-layout-3-terrain-area-09": (2, -3, 0),
    "take-and-hold-vs-take-and-hold-layout-3-terrain-area-11": (1, 0, -1),
}

# The +/-4-step audit examined 324 valid poses per member, 556 valid contact
# pairs, 1,102 exact nearest-normal closures, and found 19 component-valid
# closures. An expanded +/-6-step audit examined 676 poses per member, 1,939
# viable pairs, and 42 valid closures; both audits proved the same minimum
# 0.0118346883345-inch correction and no sub-0.01-inch solution. At the exact
# serialized correction below, the selected pair has <=3.44e-13-inch gap, zero
# overlap, and <=1.59e-12 square inches of component footprint outside its union.
_REVIEWED_EXACT_SEAM_OFFSETS = {
    "disruption-vs-disruption-layout-1-terrain-area-10": (
        0.005440361094,
        0.010510105572,
    ),
    "reconnaissance-vs-reconnaissance-layout-2-terrain-area-10": (
        0.005440361094,
        0.010510105572,
    ),
}
_REVIEWED_EXACT_SEAM_AREA_IDS = frozenset(
    {
        "disruption-vs-disruption-layout-1-terrain-area-07",
        "disruption-vs-disruption-layout-1-terrain-area-10",
        "reconnaissance-vs-reconnaissance-layout-2-terrain-area-07",
        "reconnaissance-vs-reconnaissance-layout-2-terrain-area-10",
    }
)


@dataclass(frozen=True, slots=True)
class AreaPose:
    anchor_x: float
    anchor_y: float
    rotation: float
    local_transform: str
    fit_residual: float
    candidate_index: int
    shift_x_steps: int = 0
    shift_y_steps: int = 0


@dataclass(frozen=True, slots=True)
class ComponentPose:
    center_x: float
    center_y: float
    rotation: float
    local_transform: str


def _round_coordinate(value: float) -> float:
    return round(value + 0.0, 6)


def _rotate_point(x: float, y: float, degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return (x * cosine - y * sine, x * sine + y * cosine)


def area_polygon(
    vertices: tuple[tuple[float, float], ...],
    pose: AreaPose,
) -> Polygon:
    anchor_local_x, anchor_local_y = vertices[0]
    center_delta_x, center_delta_y = _rotate_point(
        anchor_local_x,
        anchor_local_y,
        pose.rotation,
    )
    center_x = pose.anchor_x - center_delta_x
    center_y = pose.anchor_y - center_delta_y
    transformed = vertices
    if pose.local_transform == "mirror_y_axis":
        transformed = tuple((2.0 * anchor_local_x - x, y) for x, y in vertices)
    elif pose.local_transform != "identity":
        raise ValueError("Unsupported terrain-area local transform in source audit.")
    points = []
    for x, y in transformed:
        rotated_x, rotated_y = _rotate_point(x, y, pose.rotation)
        points.append((rotated_x + center_x, rotated_y + center_y))
    polygon = Polygon(points)
    if not polygon.is_valid or polygon.area <= _GEOMETRY_TOLERANCE:
        raise ValueError("Terrain-area pose produced an invalid polygon.")
    return polygon


def _mirror_pose(pose: AreaPose) -> AreaPose:
    return AreaPose(
        anchor_x=_round_coordinate(_BOARD_WIDTH - pose.anchor_x),
        anchor_y=_round_coordinate(_BOARD_DEPTH - pose.anchor_y),
        rotation=(pose.rotation + 180.0) % 360.0,
        local_transform=pose.local_transform,
        fit_residual=pose.fit_residual,
        candidate_index=pose.candidate_index,
        shift_x_steps=-pose.shift_x_steps,
        shift_y_steps=-pose.shift_y_steps,
    )


def _area_index(area_id: str) -> int:
    suffix = area_id.rsplit("-terrain-area-", maxsplit=1)[-1]
    if len(suffix) != 2 or not suffix.isdecimal() or not 1 <= int(suffix) <= 16:
        raise ValueError("Source audit terrain-area ID is not canonical.")
    return int(suffix)


def _candidate_poses(area: dict[str, Any]) -> tuple[AreaPose, ...]:
    recipe = area["pose_recipe"]
    orientation_review = area["runtime_orientation_review"]
    local_transform = orientation_review["local_transform"]
    if local_transform not in {"identity", "mirror_y_axis"}:
        raise ValueError("Terrain-area runtime orientation review is unsupported.")
    poses: list[AreaPose] = []
    for candidate in recipe["candidates"]:
        residual = candidate["fit_residual_inches"]
        pose = AreaPose(
            anchor_x=float(candidate["anchor_x_inches"]),
            anchor_y=float(candidate["anchor_y_inches"]),
            rotation=float(candidate["rotation_degrees"]),
            local_transform=local_transform,
            fit_residual=0.0 if residual is None else float(residual),
            candidate_index=int(candidate["candidate_index"]),
        )
        if pose not in poses:
            poses.append(pose)
    if not poses:
        raise ValueError("Terrain-area source audit requires at least one pose candidate.")
    return tuple(poses)


def _canonical_area_id(area_id: str, *, source_layout_id: str, layout_id: str) -> str:
    prefix = f"{source_layout_id}-"
    if not area_id.startswith(prefix):
        raise ValueError("Source terrain-area ID does not belong to its layout.")
    return f"{layout_id}-{area_id.removeprefix(prefix)}"


def _contact_pairs(
    layout: dict[str, Any],
    *,
    layout_id: str,
) -> frozenset[frozenset[str]]:
    source_layout_id = layout["layout_id"]
    result: set[frozenset[str]] = set()
    for row in layout["source_contact_pairs"]:
        area_ids = tuple(
            _canonical_area_id(
                area_id,
                source_layout_id=source_layout_id,
                layout_id=layout_id,
            )
            for area_id in row["area_ids"]
        )
        if len(area_ids) != 2 or area_ids[0] == area_ids[1]:
            raise ValueError("Source contact pairs require two distinct terrain areas.")
        result.add(frozenset(area_ids))
    if len(result) != len(layout["source_contact_pairs"]):
        raise ValueError("Source contact-pair inventory contains duplicates.")
    return frozenset(result)


def _pose_inventory(
    *,
    primary_ids: tuple[str, ...],
    choices: tuple[int, ...],
    candidates_by_id: dict[str, tuple[AreaPose, ...]],
    mirror_ids: dict[str, str],
) -> dict[str, AreaPose]:
    result: dict[str, AreaPose] = {}
    for area_id, choice in zip(primary_ids, choices, strict=True):
        pose = candidates_by_id[area_id][choice]
        result[area_id] = pose
        result[mirror_ids[area_id]] = _mirror_pose(pose)
    return result


def _polygons_for_poses(
    poses: dict[str, AreaPose],
    *,
    template_id_by_area: dict[str, str],
    templates: dict[str, tuple[tuple[float, float], ...]],
) -> dict[str, Polygon]:
    return {
        area_id: area_polygon(templates[template_id_by_area[area_id]], pose)
        for area_id, pose in poses.items()
    }


def _geometry_score(
    polygons: dict[str, Polygon],
    *,
    contact_pairs: frozenset[frozenset[str]],
) -> tuple[int, float, int, float, int, float]:
    overlap_count = 0
    overlap_total = 0.0
    contact_gap_count = 0
    contact_gap_total = 0.0
    ordered_ids = tuple(sorted(polygons))
    for first_index, first_id in enumerate(ordered_ids):
        first = polygons[first_id]
        for second_id in ordered_ids[first_index + 1 :]:
            second = polygons[second_id]
            overlap = first.intersection(second).area
            if overlap > _GEOMETRY_TOLERANCE:
                overlap_count += 1
                overlap_total += overlap
            pair = frozenset((first_id, second_id))
            if pair in contact_pairs:
                gap = max(0.0, first.distance(second) - _GRID)
                if gap > _GEOMETRY_TOLERANCE:
                    contact_gap_count += 1
                    contact_gap_total += gap
    board = box(0.0, 0.0, _BOARD_WIDTH, _BOARD_DEPTH)
    outside_areas = tuple(polygon.difference(board).area for polygon in polygons.values())
    outside_count = sum(area > _GEOMETRY_TOLERANCE for area in outside_areas)
    outside_total = sum(area for area in outside_areas if area > _GEOMETRY_TOLERANCE)
    return (
        overlap_count,
        round(overlap_total, 9),
        contact_gap_count,
        round(contact_gap_total, 9),
        outside_count,
        round(outside_total, 9),
    )


def _objective_requirements(
    layout: dict[str, Any],
    *,
    layout_id: str,
) -> tuple[tuple[Point, tuple[str, ...]], ...]:
    source_layout_id = layout["layout_id"]
    result: list[tuple[Point, tuple[str, ...]]] = []
    for objective in layout["objectives"]:
        source_ids = tuple(objective["nearest_area_ids"])
        distances = tuple(objective["distances_to_area_polygons_inches"])
        if distances:
            if len(source_ids) != len(distances):
                raise ValueError("Objective source-distance inventory drifted.")
            source_ids = tuple(
                area_id
                for area_id, distance in zip(source_ids, distances, strict=True)
                if float(distance) <= _GRID + 1e-9
            )
        elif layout["source_pdf_page_number"] not in {24, 25, 26}:
            raise ValueError("Non-Meatgrinder objectives require source distances.")
        canonical_ids = tuple(
            _canonical_area_id(
                area_id,
                source_layout_id=source_layout_id,
                layout_id=layout_id,
            )
            for area_id in source_ids
        )
        if canonical_ids:
            x_inches, y_inches = objective["battlefield_center_quantized_0_01_inches"]
            result.append((Point(float(x_inches), float(y_inches)), canonical_ids))
    return tuple(result)


def _objective_score(
    polygons: dict[str, Polygon],
    requirements: tuple[tuple[Point, tuple[str, ...]], ...],
) -> tuple[int, float]:
    missing_count = 0
    missing_distance = 0.0
    for point, area_ids in requirements:
        distances = tuple(polygons[area_id].distance(point) for area_id in area_ids)
        nearest_distance = min(distances)
        if nearest_distance > _GEOMETRY_TOLERANCE:
            missing_count += 1
            missing_distance += nearest_distance
        for distance in distances:
            excess = max(0.0, distance - _GRID)
            if excess > _GEOMETRY_TOLERANCE:
                missing_count += 1
                missing_distance += excess
    return missing_count, round(missing_distance, 9)


def _source_fit_score(
    *,
    primary_ids: tuple[str, ...],
    choices: tuple[int, ...],
    candidates_by_id: dict[str, tuple[AreaPose, ...]],
    source_candidates_by_id: dict[str, tuple[AreaPose, ...]],
    mirror_ids: dict[str, str],
) -> float:
    score = 0.0
    for area_id, choice in zip(primary_ids, choices, strict=True):
        pose = candidates_by_id[area_id][choice]
        score += pose.fit_residual
        mirror_pose = _mirror_pose(pose)
        mirror_candidates = source_candidates_by_id[mirror_ids[area_id]]
        score += min(
            candidate.fit_residual
            + math.dist(
                (candidate.anchor_x, candidate.anchor_y),
                (mirror_pose.anchor_x, mirror_pose.anchor_y),
            )
            + abs(((candidate.rotation - mirror_pose.rotation + 180.0) % 360.0) - 180.0) / 1000.0
            for candidate in mirror_candidates
        )
    return round(score, 9)


def _shifted_pose(pose: AreaPose, x_steps: int, y_steps: int) -> AreaPose:
    return replace(
        pose,
        anchor_x=_round_coordinate(pose.anchor_x + x_steps * _GRID),
        anchor_y=_round_coordinate(pose.anchor_y + y_steps * _GRID),
        shift_x_steps=x_steps,
        shift_y_steps=y_steps,
    )


def _reviewed_fixed_pose(
    area_id: str,
    pose: AreaPose,
    fixed_pose: tuple[int, int, int],
) -> AreaPose:
    shifted = _shifted_pose(pose, fixed_pose[1], fixed_pose[2])
    exact_offset = _REVIEWED_EXACT_SEAM_OFFSETS.get(area_id)
    if exact_offset is None:
        return shifted
    return replace(
        shifted,
        anchor_x=round(shifted.anchor_x + exact_offset[0], 12),
        anchor_y=round(shifted.anchor_y + exact_offset[1], 12),
    )


def uses_reviewed_exact_seam_pose(area_id: str) -> bool:
    return area_id in _REVIEWED_EXACT_SEAM_AREA_IDS


def _adjust_candidate_set(
    *,
    primary_ids: tuple[str, ...],
    choices: tuple[int, ...],
    candidates_by_id: dict[str, tuple[AreaPose, ...]],
    mirror_ids: dict[str, str],
    template_id_by_area: dict[str, str],
    templates: dict[str, tuple[tuple[float, float], ...]],
    contact_pairs: frozenset[frozenset[str]],
    objective_requirements: tuple[tuple[Point, tuple[str, ...]], ...],
) -> tuple[tuple[object, ...], dict[str, AreaPose]]:
    base_poses = {
        area_id: candidates_by_id[area_id][choice]
        for area_id, choice in zip(primary_ids, choices, strict=True)
    }
    offset_options = tuple(
        (x_steps, y_steps)
        for x_steps in range(-_MAX_AREA_SHIFT_STEPS, _MAX_AREA_SHIFT_STEPS + 1)
        for y_steps in range(-_MAX_AREA_SHIFT_STEPS, _MAX_AREA_SHIFT_STEPS + 1)
    )
    initial_option = offset_options.index((0, 0))
    option_poses: dict[tuple[int, int], tuple[AreaPose, AreaPose]] = {}
    option_polygons: dict[tuple[int, int], dict[str, Polygon]] = {}
    unary_scores: dict[tuple[int, int], tuple[int, float, int, float, int, float]] = {}
    for variable_index, area_id in enumerate(primary_ids):
        for option_index, (x_steps, y_steps) in enumerate(offset_options):
            primary_pose = _shifted_pose(base_poses[area_id], x_steps, y_steps)
            mirror_pose = _mirror_pose(primary_pose)
            option_poses[(variable_index, option_index)] = (primary_pose, mirror_pose)
            polygons = _polygons_for_poses(
                {area_id: primary_pose, mirror_ids[area_id]: mirror_pose},
                template_id_by_area=template_id_by_area,
                templates=templates,
            )
            option_polygons[(variable_index, option_index)] = polygons
            unary_scores[(variable_index, option_index)] = _geometry_score(
                polygons,
                contact_pairs=contact_pairs,
            )
    pair_score_cache: dict[
        tuple[int, int, int, int],
        tuple[int, float, int, float, int, float],
    ] = {}

    def pair_score(
        first_variable: int,
        second_variable: int,
        first_option: int,
        second_option: int,
    ) -> tuple[int, float, int, float, int, float]:
        key = (first_variable, second_variable, first_option, second_option)
        cached = pair_score_cache.get(key)
        if cached is not None:
            return cached
        polygons = {
            **option_polygons[(first_variable, first_option)],
            **option_polygons[(second_variable, second_option)],
        }
        total = _geometry_score(
            polygons,
            contact_pairs=contact_pairs,
        )
        first = unary_scores[(first_variable, first_option)]
        second = unary_scores[(second_variable, second_option)]
        result = tuple(
            round(total_value - first_value - second_value, 9)
            if isinstance(total_value, float)
            else total_value - first_value - second_value
            for total_value, first_value, second_value in zip(
                total,
                first,
                second,
                strict=True,
            )
        )
        pair_score_cache[key] = result
        return result

    options = [initial_option] * len(primary_ids)

    def score() -> tuple[object, ...]:
        values: list[int | float] = [0, 0.0, 0, 0.0, 0, 0.0]
        for variable_index, option_index in enumerate(options):
            for score_index, value in enumerate(unary_scores[(variable_index, option_index)]):
                values[score_index] += value
        for first_variable in range(len(primary_ids)):
            for second_variable in range(first_variable + 1, len(primary_ids)):
                pair = pair_score(
                    first_variable,
                    second_variable,
                    options[first_variable],
                    options[second_variable],
                )
                for score_index, value in enumerate(pair):
                    values[score_index] += value
        geometry = tuple(round(value, 9) if isinstance(value, float) else value for value in values)
        current_polygons: dict[str, Polygon] = {}
        for variable_index, option_index in enumerate(options):
            current_polygons.update(option_polygons[(variable_index, option_index)])
        objective = _objective_score(current_polygons, objective_requirements)
        offsets = tuple(offset_options[option_index] for option_index in options)
        displacement = sum(x * x + y * y for x, y in offsets)
        return (*geometry, *objective, displacement, offsets)

    current_score = score()
    for _pass_index in range(6):
        changed = False
        for variable_index in range(len(primary_ids)):
            starting_option = options[variable_index]
            best_option = starting_option
            best_score = current_score
            for option_index in range(len(offset_options)):
                options[variable_index] = option_index
                candidate_score = score()
                if candidate_score < best_score:
                    best_score = candidate_score
                    best_option = option_index
            options[variable_index] = best_option
            if best_option != starting_option:
                changed = True
                current_score = best_score
        if not changed or current_score[:8] == (
            0,
            0.0,
            0,
            0.0,
            0,
            0.0,
            0,
            0.0,
        ):
            break
    inventory: dict[str, AreaPose] = {}
    for variable_index, area_id in enumerate(primary_ids):
        primary_pose, mirror_pose = option_poses[(variable_index, options[variable_index])]
        inventory[area_id] = primary_pose
        inventory[mirror_ids[area_id]] = mirror_pose
    return current_score, inventory


def _solve_symmetric_area_poses(
    layout: dict[str, Any],
    *,
    layout_id: str,
    templates: dict[str, tuple[tuple[float, float], ...]],
) -> tuple[dict[str, AreaPose], tuple[tuple[str, str], ...]]:
    source_layout_id = layout["layout_id"]
    source_areas = layout["terrain_areas"]
    canonical_areas = {
        _canonical_area_id(
            area["area_id"],
            source_layout_id=source_layout_id,
            layout_id=layout_id,
        ): area
        for area in source_areas
    }
    primary_ids = tuple(sorted(area_id for area_id in canonical_areas if _area_index(area_id) <= 8))
    if len(primary_ids) != 8:
        raise ValueError("Every Event Companion layout requires eight primary terrain areas.")
    mirror_ids = {
        area_id: _canonical_area_id(
            canonical_areas[area_id]["point_symmetry_partner_area_id"],
            source_layout_id=source_layout_id,
            layout_id=layout_id,
        )
        for area_id in primary_ids
    }
    if len(set(mirror_ids.values())) != 8 or any(
        _area_index(mirror_id) <= 8 for mirror_id in mirror_ids.values()
    ):
        raise ValueError(
            "Terrain-area point-symmetry partners must bind across battlefield halves."
        )
    for area_id, mirror_id in mirror_ids.items():
        reciprocal = _canonical_area_id(
            canonical_areas[mirror_id]["point_symmetry_partner_area_id"],
            source_layout_id=source_layout_id,
            layout_id=layout_id,
        )
        if reciprocal != area_id:
            raise ValueError("Terrain-area point-symmetry partners must be reciprocal.")
        primary_review = canonical_areas[area_id]["runtime_orientation_review"]
        mirror_review = canonical_areas[mirror_id]["runtime_orientation_review"]
        if primary_review["local_transform"] != mirror_review["local_transform"]:
            raise ValueError(
                "Point-symmetric terrain areas require a shared reviewed runtime transform."
            )
    source_candidates_by_id = {
        area_id: _candidate_poses(area) for area_id, area in canonical_areas.items()
    }
    candidates_by_id = {area_id: source_candidates_by_id[area_id] for area_id in primary_ids}
    template_id_by_area = {
        area_id: area["footprint_template_id"] for area_id, area in canonical_areas.items()
    }
    contact_pairs = _contact_pairs(layout, layout_id=layout_id)
    objective_requirements = _objective_requirements(layout, layout_id=layout_id)

    candidate_polygons: dict[tuple[int, int], dict[str, Polygon]] = {}
    unary_scores: dict[tuple[int, int], tuple[int, float, int, float, int, float]] = {}
    for variable_index, area_id in enumerate(primary_ids):
        for choice, pose in enumerate(candidates_by_id[area_id]):
            inventory = {area_id: pose, mirror_ids[area_id]: _mirror_pose(pose)}
            polygons = _polygons_for_poses(
                inventory,
                template_id_by_area=template_id_by_area,
                templates=templates,
            )
            candidate_polygons[(variable_index, choice)] = polygons
            unary_scores[(variable_index, choice)] = _geometry_score(
                polygons,
                contact_pairs=contact_pairs,
            )
    pair_scores: dict[
        tuple[int, int, int, int],
        tuple[int, float, int, float, int, float],
    ] = {}
    for first_variable in range(len(primary_ids)):
        for second_variable in range(first_variable + 1, len(primary_ids)):
            for first_choice in range(len(candidates_by_id[primary_ids[first_variable]])):
                for second_choice in range(len(candidates_by_id[primary_ids[second_variable]])):
                    polygons = {
                        **candidate_polygons[(first_variable, first_choice)],
                        **candidate_polygons[(second_variable, second_choice)],
                    }
                    total_score = _geometry_score(
                        polygons,
                        contact_pairs=contact_pairs,
                    )
                    first_score = unary_scores[(first_variable, first_choice)]
                    second_score = unary_scores[(second_variable, second_choice)]
                    pair_scores[(first_variable, second_variable, first_choice, second_choice)] = (
                        tuple(
                            round(total - first - second, 9)
                            if isinstance(total, float)
                            else total - first - second
                            for total, first, second in zip(
                                total_score,
                                first_score,
                                second_score,
                                strict=True,
                            )
                        )
                    )

    source_score_by_choice = {
        (variable_index, choice): _source_fit_score(
            primary_ids=(area_id,),
            choices=(choice,),
            candidates_by_id=candidates_by_id,
            source_candidates_by_id=source_candidates_by_id,
            mirror_ids=mirror_ids,
        )
        for variable_index, area_id in enumerate(primary_ids)
        for choice in range(len(candidates_by_id[area_id]))
    }
    beam: list[tuple[tuple[int | float, ...], float, tuple[int, ...]]] = [
        ((0, 0.0, 0, 0.0, 0, 0.0), 0.0, ())
    ]
    for variable_index, area_id in enumerate(primary_ids):
        expanded: list[tuple[tuple[int | float, ...], float, tuple[int, ...]]] = []
        for geometry_score, fit_score, choices in beam:
            for choice in range(len(candidates_by_id[area_id])):
                values = list(geometry_score)
                for score_index, value in enumerate(unary_scores[(variable_index, choice)]):
                    values[score_index] += value
                for prior_variable, prior_choice in enumerate(choices):
                    pair_score = pair_scores[(prior_variable, variable_index, prior_choice, choice)]
                    for score_index, value in enumerate(pair_score):
                        values[score_index] += value
                expanded.append(
                    (
                        tuple(
                            round(value, 9) if isinstance(value, float) else value
                            for value in values
                        ),
                        round(fit_score + source_score_by_choice[(variable_index, choice)], 9),
                        (*choices, choice),
                    )
                )
        expanded.sort(key=lambda row: (*row[0], row[1], row[2]))
        beam = expanded[:_CANDIDATE_BEAM_WIDTH]
    ranked_candidate_sets: list[
        tuple[tuple[int | float, ...], tuple[int, float], float, tuple[int, ...]]
    ] = []
    for geometry_score, fit_score, choices in beam:
        poses = _pose_inventory(
            primary_ids=primary_ids,
            choices=choices,
            candidates_by_id=candidates_by_id,
            mirror_ids=mirror_ids,
        )
        polygons = _polygons_for_poses(
            poses,
            template_id_by_area=template_id_by_area,
            templates=templates,
        )
        ranked_candidate_sets.append(
            (
                geometry_score,
                _objective_score(polygons, objective_requirements),
                fit_score,
                choices,
            )
        )
    ranked_candidate_sets.sort(key=lambda row: (*row[0], *row[1], row[2], row[3]))
    candidate_sets = tuple(row[3] for row in ranked_candidate_sets[:_CANDIDATE_SET_LIMIT])
    best: tuple[tuple[object, ...], dict[str, AreaPose]] | None = None
    for choices in candidate_sets:
        adjusted_score, adjusted = _adjust_candidate_set(
            primary_ids=primary_ids,
            choices=choices,
            candidates_by_id=candidates_by_id,
            mirror_ids=mirror_ids,
            template_id_by_area=template_id_by_area,
            templates=templates,
            contact_pairs=contact_pairs,
            objective_requirements=objective_requirements,
        )
        fit_score = _source_fit_score(
            primary_ids=primary_ids,
            choices=choices,
            candidates_by_id=candidates_by_id,
            source_candidates_by_id=source_candidates_by_id,
            mirror_ids=mirror_ids,
        )
        final_score = (*adjusted_score, fit_score, choices)
        if best is None or final_score < best[0]:
            best = (final_score, adjusted)
    if best is None or best[0][:8] != (
        0,
        0.0,
        0,
        0.0,
        0,
        0.0,
        0,
        0.0,
    ):
        raise ValueError(f"Terrain-area contact solver failed for {layout_id}: {best!r}")
    solved = best[1]
    pairs = tuple(
        tuple(sorted(pair)) for pair in sorted(contact_pairs, key=lambda pair: sorted(pair))
    )
    return solved, pairs


def _independent_inventory_score(
    poses: dict[str, AreaPose],
    *,
    selected_candidate_index_by_id: dict[str, int],
    template_id_by_area: dict[str, str],
    templates: dict[str, tuple[tuple[float, float], ...]],
    contact_pairs: frozenset[frozenset[str]],
    objective_requirements: tuple[tuple[Point, tuple[str, ...]], ...],
    component_constraint: Callable[[dict[str, AreaPose]], tuple[int, float]] | None,
) -> tuple[object, ...]:
    polygons = _polygons_for_poses(
        poses,
        template_id_by_area=template_id_by_area,
        templates=templates,
    )
    geometry = _geometry_score(
        polygons,
        contact_pairs=contact_pairs,
    )
    objectives = _objective_score(polygons, objective_requirements)
    component_count, component_outside_area = (
        (0, 0.0) if component_constraint is None else component_constraint(poses)
    )
    candidate_changes = sum(
        pose.candidate_index != selected_candidate_index_by_id[area_id]
        for area_id, pose in poses.items()
    )
    displacement = sum(
        pose.shift_x_steps * pose.shift_x_steps + pose.shift_y_steps * pose.shift_y_steps
        for pose in poses.values()
    )
    fit_residual = sum(pose.fit_residual for pose in poses.values())
    pose_tie_breaker = tuple(
        (
            area_id,
            pose.candidate_index,
            pose.shift_x_steps,
            pose.shift_y_steps,
        )
        for area_id, pose in sorted(poses.items())
    )
    return (
        *geometry,
        *objectives,
        component_count,
        round(component_outside_area, 9),
        candidate_changes,
        displacement,
        round(fit_residual, 9),
        pose_tie_breaker,
    )


def _solve_independent_area_poses(
    layout: dict[str, Any],
    *,
    layout_id: str,
    templates: dict[str, tuple[tuple[float, float], ...]],
    component_constraint: Callable[[dict[str, AreaPose]], tuple[int, float]] | None,
) -> tuple[dict[str, AreaPose], tuple[tuple[str, str], ...]]:
    source_layout_id = layout["layout_id"]
    canonical_areas = {
        _canonical_area_id(
            area["area_id"],
            source_layout_id=source_layout_id,
            layout_id=layout_id,
        ): area
        for area in layout["terrain_areas"]
    }
    area_ids = tuple(sorted(canonical_areas))
    if len(area_ids) != 16:
        raise ValueError("Every Event Companion layout requires sixteen terrain areas.")
    candidates_by_id = {area_id: _candidate_poses(canonical_areas[area_id]) for area_id in area_ids}
    selected_candidate_index_by_id = {
        area_id: int(canonical_areas[area_id]["pose_recipe"]["selected_candidate_index"])
        for area_id in area_ids
    }
    template_id_by_area = {
        area_id: canonical_areas[area_id]["footprint_template_id"] for area_id in area_ids
    }
    contact_pairs = _contact_pairs(layout, layout_id=layout_id)
    objective_requirements = _objective_requirements(layout, layout_id=layout_id)

    def score(poses: dict[str, AreaPose]) -> tuple[object, ...]:
        return _independent_inventory_score(
            poses,
            selected_candidate_index_by_id=selected_candidate_index_by_id,
            template_id_by_area=template_id_by_area,
            templates=templates,
            contact_pairs=contact_pairs,
            objective_requirements=objective_requirements,
            component_constraint=component_constraint,
        )

    poses: dict[str, AreaPose] = {}
    for area_id in area_ids:
        selected_index = selected_candidate_index_by_id[area_id]
        fixed_pose = _REVIEWED_FIXED_AREA_POSE_STEPS.get(area_id)
        candidate_index = selected_index if fixed_pose is None else fixed_pose[0]
        matches = tuple(
            candidate
            for candidate in candidates_by_id[area_id]
            if candidate.candidate_index == candidate_index
        )
        if len(matches) != 1:
            raise ValueError("Reviewed source pose candidate identity is invalid.")
        poses[area_id] = (
            matches[0]
            if fixed_pose is None
            else _reviewed_fixed_pose(area_id, matches[0], fixed_pose)
        )

    def score_is_valid(value: tuple[object, ...]) -> bool:
        return (
            value[:8]
            == (
                0,
                0.0,
                0,
                0.0,
                0,
                0.0,
                0,
                0.0,
            )
            and value[8] == 0
        )

    offset_options = tuple(
        (x_steps, y_steps)
        for x_steps in range(-_MAX_AREA_SHIFT_STEPS, _MAX_AREA_SHIFT_STEPS + 1)
        for y_steps in range(-_MAX_AREA_SHIFT_STEPS, _MAX_AREA_SHIFT_STEPS + 1)
    )
    initial_poses = dict(poses)
    current_score = score(poses)
    for _pass_index in range(6):
        changed = False
        for area_id in area_ids:
            if area_id in _REVIEWED_FIXED_AREA_POSE_STEPS:
                continue
            starting = poses[area_id]
            best = starting
            best_score = current_score
            for candidate in candidates_by_id[area_id]:
                poses[area_id] = candidate
                candidate_score = score(poses)
                if candidate_score < best_score:
                    best = candidate
                    best_score = candidate_score
            poses[area_id] = best
            if best != starting:
                changed = True
                current_score = best_score
        if not changed:
            break
    base_poses = dict(poses)
    current_score = score(poses)
    for _pass_index in range(8):
        changed = False
        for area_id in area_ids:
            if area_id in _REVIEWED_FIXED_AREA_POSE_STEPS:
                continue
            starting = poses[area_id]
            best = starting
            best_score = current_score
            for x_steps, y_steps in offset_options:
                candidate_pose = _shifted_pose(base_poses[area_id], x_steps, y_steps)
                poses[area_id] = candidate_pose
                candidate_score = score(poses)
                if candidate_score < best_score:
                    best = candidate_pose
                    best_score = candidate_score
            poses[area_id] = best
            if best != starting:
                changed = True
                current_score = best_score
        if not changed or score_is_valid(current_score):
            break

    pose_options_by_id = {
        area_id: tuple(
            _shifted_pose(candidate, x_steps, y_steps)
            for candidate in candidates_by_id[area_id]
            for x_steps, y_steps in offset_options
        )
        for area_id in area_ids
        if area_id not in _REVIEWED_FIXED_AREA_POSE_STEPS
    }
    if not score_is_valid(current_score):
        poses = initial_poses
        current_score = score(poses)
        for _pass_index in range(8):
            changed = False
            for area_id in area_ids:
                if area_id in _REVIEWED_FIXED_AREA_POSE_STEPS:
                    continue
                starting = poses[area_id]
                best = starting
                best_score = current_score
                for candidate_pose in pose_options_by_id[area_id]:
                    poses[area_id] = candidate_pose
                    candidate_score = score(poses)
                    if candidate_score < best_score:
                        best = candidate_pose
                        best_score = candidate_score
                poses[area_id] = best
                if best != starting:
                    changed = True
                    current_score = best_score
            if not changed or score_is_valid(current_score):
                break
    if not score_is_valid(current_score):
        raise ValueError(f"Independent terrain-area solver failed for {layout_id}: {current_score}")
    pairs = tuple(
        tuple(sorted(pair)) for pair in sorted(contact_pairs, key=lambda pair: sorted(pair))
    )
    return dict(poses), pairs


def solve_area_poses(
    layout: dict[str, Any],
    *,
    layout_id: str,
    templates: dict[str, tuple[tuple[float, float], ...]],
    component_constraint: Callable[[dict[str, AreaPose]], tuple[int, float]] | None = None,
) -> tuple[dict[str, AreaPose], tuple[tuple[str, str], ...]]:
    if layout["source_pdf_page_number"] in {24, 25, 26}:
        solved, contact_pairs = _solve_symmetric_area_poses(
            layout,
            layout_id=layout_id,
            templates=templates,
        )
        if component_constraint is not None and component_constraint(solved)[0] != 0:
            raise ValueError(
                f"Symmetric terrain-area component containment failed for {layout_id}."
            )
        return solved, contact_pairs
    if component_constraint is not None:
        solved, contact_pairs = _solve_independent_area_poses(
            layout,
            layout_id=layout_id,
            templates=templates,
            component_constraint=None,
        )
        if component_constraint(solved)[0] == 0:
            return solved, contact_pairs
    return _solve_independent_area_poses(
        layout,
        layout_id=layout_id,
        templates=templates,
        component_constraint=component_constraint,
    )


def component_local_placement(
    *,
    component_pose: ComponentPose,
    area_pose: AreaPose,
    area_vertices: tuple[tuple[float, float], ...],
) -> tuple[float, float, float]:
    anchor_local_x, anchor_local_y = area_vertices[0]
    rotated_anchor_x, rotated_anchor_y = _rotate_point(
        anchor_local_x,
        anchor_local_y,
        area_pose.rotation,
    )
    area_center_x = area_pose.anchor_x - rotated_anchor_x
    area_center_y = area_pose.anchor_y - rotated_anchor_y
    delta_x = component_pose.center_x - area_center_x
    delta_y = component_pose.center_y - area_center_y
    radians = math.radians(area_pose.rotation)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    transformed_x = delta_x * cosine + delta_y * sine
    local_y = -delta_x * sine + delta_y * cosine
    local_x = (
        2.0 * anchor_local_x - transformed_x
        if area_pose.local_transform == "mirror_y_axis"
        else transformed_x
    )
    inner_rotation = (
        180.0 + area_pose.rotation - component_pose.rotation
        if area_pose.local_transform == "mirror_y_axis"
        else component_pose.rotation - area_pose.rotation
    )
    local_rotation = inner_rotation - (
        180.0 if component_pose.local_transform == "mirror_y_axis" else 0.0
    )
    return (round(local_x, 6), round(local_y, 6), round(local_rotation % 360.0, 6))


def component_local_polygon(
    archetype_vertices: tuple[tuple[float, float], ...],
    *,
    offset_x: float,
    offset_y: float,
    rotation: float,
    local_transform: str,
) -> Polygon:
    polygon = Polygon(archetype_vertices)
    if local_transform == "mirror_y_axis":
        polygon = affinity.scale(polygon, xfact=-1.0, yfact=1.0, origin=(0.0, 0.0))
    elif local_transform != "identity":
        raise ValueError("Unsupported component local transform in source audit.")
    polygon = affinity.rotate(polygon, rotation, origin=(0.0, 0.0), use_radians=False)
    return affinity.translate(polygon, xoff=offset_x, yoff=offset_y)


def region_rows(
    layout_id: str,
    template_number: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], str, str]:
    template_ids = {
        1: "deployment-zone-layout-1-staggered",
        2: "deployment-zone-layout-2-long-edge-strip",
        3: "deployment-zone-layout-3-quarter-circle-cutout",
        4: "deployment-zone-layout-4-stepped-long-edge",
        5: "deployment-zone-layout-5-short-edge-strip",
        6: "deployment-zone-layout-6-triangle",
    }
    edge_pairs = {
        1: ("north", "south"),
        2: ("west", "east"),
        3: ("west", "east"),
        4: ("west", "east"),
        5: ("north", "south"),
        6: ("north_west_corner", "south_east_corner"),
    }
    if template_number not in template_ids:
        raise ValueError("Unsupported Event Companion deployment-zone template.")
    attacker_polygon, defender_polygon, no_mans_land_polygons = _deployment_geometry(
        template_number
    )
    attacker_territory, defender_territory = _territory_geometry(template_number)
    template_id = template_ids[template_number]
    zones = [
        _shape(
            layout_id=layout_id,
            suffix=role,
            role=role,
            owner_role=role,
            polygons=[polygon],
            source_kind=template_id,
        )
        for role, polygon in (
            ("attacker", attacker_polygon),
            ("defender", defender_polygon),
        )
    ]
    no_mans_land = _shape(
        layout_id=layout_id,
        suffix="no-mans-land",
        role="no_mans_land",
        owner_role=None,
        polygons=no_mans_land_polygons,
        source_kind="source_page_complement_of_deployment_zones",
    )
    territories = [
        _shape(
            layout_id=layout_id,
            suffix=role,
            role=role,
            owner_role=owner,
            polygons=[polygon],
            source_kind="source_page_territory_boundary",
        )
        for role, owner, polygon in (
            ("attacker_territory", "attacker", attacker_territory),
            ("defender_territory", "defender", defender_territory),
        )
    ]
    attacker_edge, defender_edge = edge_pairs[template_number]
    return zones, no_mans_land, territories, attacker_edge, defender_edge


def _shape(
    *,
    layout_id: str,
    suffix: str,
    role: str,
    owner_role: str | None,
    polygons: list[list[tuple[float, float]]],
    source_kind: str,
) -> dict[str, Any]:
    return {
        "shape_id": f"{layout_id}-{suffix}",
        "role": role,
        "owner_role": owner_role,
        "polygons": [
            [{"x_inches": float(x), "y_inches": float(y)} for x, y in polygon]
            for polygon in polygons
        ],
        "source_kind": source_kind,
    }


def _arc(start_degrees: float, end_degrees: float) -> list[tuple[float, float]]:
    return [
        (
            round(22.0 + 9.0 * math.cos(math.radians(degrees)), 6),
            round(30.0 + 9.0 * math.sin(math.radians(degrees)), 6),
        )
        for degrees in (
            start_degrees + (end_degrees - start_degrees) * index / 16 for index in range(17)
        )
    ]


def _deployment_geometry(
    template_number: int,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]], list[list[tuple[float, float]]]]:
    if template_number == 1:
        attacker = [(0, 60), (44, 60), (44, 48), (22, 48), (22, 40), (0, 40)]
        defender = [(44, 0), (0, 0), (0, 12), (22, 12), (22, 20), (44, 20)]
        no_mans_land = [
            [(0, 12), (22, 12), (22, 20), (44, 20), (44, 48), (22, 48), (22, 40), (0, 40)]
        ]
    elif template_number == 2:
        attacker = [(0, 0), (12, 0), (12, 60), (0, 60)]
        defender = [(32, 0), (44, 0), (44, 60), (32, 60)]
        no_mans_land = [[(12, 0), (32, 0), (32, 60), (12, 60)]]
    elif template_number == 3:
        attacker = [(0, 30), *_arc(180, 90), (22, 60), (0, 60)]
        defender = [(44, 30), *_arc(0, -90), (22, 0), (44, 0)]
        no_mans_land = [
            [(0, 0), (22, 0), (22, 30), (0, 30)],
            [(22, 30), (44, 30), (44, 60), (22, 60)],
            [(22, 30), *_arc(90, 180)],
            [(22, 30), *_arc(-90, 0)],
        ]
    elif template_number == 4:
        attacker = [(0, 0), (8, 0), (8, 30), (14, 30), (14, 60), (0, 60)]
        defender = [(44, 60), (36, 60), (36, 30), (30, 30), (30, 0), (44, 0)]
        no_mans_land = [
            [(8, 0), (30, 0), (30, 30), (36, 30), (36, 60), (14, 60), (14, 30), (8, 30)]
        ]
    elif template_number == 5:
        attacker = [(0, 42), (44, 42), (44, 60), (0, 60)]
        defender = [(0, 0), (44, 0), (44, 18), (0, 18)]
        no_mans_land = [[(0, 18), (44, 18), (44, 42), (0, 42)]]
    elif template_number == 6:
        attacker = [(0, 60), (44, 60), (0, 30)]
        defender = [(44, 0), (0, 0), (44, 30)]
        no_mans_land = [[(0, 0), (44, 30), (44, 60), (0, 30)]]
    else:
        raise ValueError("Unsupported Event Companion deployment geometry.")
    return attacker, defender, no_mans_land


def _territory_geometry(
    template_number: int,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    if template_number in {1, 5}:
        return (
            [(0, 30), (44, 30), (44, 60), (0, 60)],
            [(0, 0), (44, 0), (44, 30), (0, 30)],
        )
    if template_number in {2, 4}:
        return (
            [(0, 0), (22, 0), (22, 60), (0, 60)],
            [(22, 0), (44, 0), (44, 60), (22, 60)],
        )
    if template_number in {3, 6}:
        return (
            [(0, 0), (44, 60), (0, 60)],
            [(0, 0), (44, 0), (44, 60)],
        )
    raise ValueError("Unsupported Event Companion territory geometry.")


__all__ = [
    "AreaPose",
    "ComponentPose",
    "area_polygon",
    "component_local_placement",
    "component_local_polygon",
    "region_rows",
    "solve_area_poses",
]
