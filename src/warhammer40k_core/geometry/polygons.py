from __future__ import annotations

import math
from typing import cast

from warhammer40k_core.geometry.pose import GeometryError, validate_finite_number

type Point2D = tuple[float, float]

GEOMETRY_EPSILON = 1e-6


def signed_polygon_area(vertices: tuple[Point2D, ...]) -> float:
    points = _validate_polygon_vertices("vertices", vertices)
    return _signed_polygon_area(points)


def _signed_polygon_area(points: tuple[Point2D, ...]) -> float:
    """Area of already validated vertices; public entry points own validation."""
    area = 0.0
    previous = points[-1]
    for current in points:
        area += (previous[0] * current[1]) - (current[0] * previous[1])
        previous = current
    return area / 2.0


def polygon_overlap_area(first: tuple[Point2D, ...], second: tuple[Point2D, ...]) -> float:
    first_triangles = triangulate_polygon(first)
    second_triangles = triangulate_polygon(second)
    total_area = 0.0
    for first_triangle in first_triangles:
        for second_triangle in second_triangles:
            total_area += _validated_convex_polygon_intersection_area(
                first_triangle, second_triangle
            )
    return total_area


def polygon_distance(first: tuple[Point2D, ...], second: tuple[Point2D, ...]) -> float:
    first_points = _validate_polygon_vertices("first", first)
    second_points = _validate_polygon_vertices("second", second)
    first_edges = tuple(zip(first_points, (*first_points[1:], first_points[0]), strict=True))
    second_edges = tuple(zip(second_points, (*second_points[1:], second_points[0]), strict=True))
    if (
        any(
            _segments_intersect(first_start, first_end, second_start, second_end)
            for first_start, first_end in first_edges
            for second_start, second_end in second_edges
        )
        or point_intersects_polygon(first_points[0], second_points)
        or point_intersects_polygon(second_points[0], first_points)
    ):
        return 0.0
    return min(
        *(
            _point_to_segment_distance(point, start, end)
            for point in first_points
            for start, end in second_edges
        ),
        *(
            _point_to_segment_distance(point, start, end)
            for point in second_points
            for start, end in first_edges
        ),
    )


def triangulate_polygon(vertices: tuple[Point2D, ...]) -> tuple[tuple[Point2D, ...], ...]:
    remaining = list(_validate_polygon_vertices("vertices", vertices))
    if _signed_polygon_area(tuple(remaining)) < 0.0:
        remaining.reverse()

    triangles: list[tuple[Point2D, ...]] = []
    guard = len(remaining) * len(remaining)
    while len(remaining) > 3:
        ear_index = _find_ear_index(tuple(remaining))
        if ear_index is None:
            raise GeometryError("Polygon must be simple.")
        previous_point = remaining[ear_index - 1]
        current_point = remaining[ear_index]
        next_point = remaining[(ear_index + 1) % len(remaining)]
        triangles.append((previous_point, current_point, next_point))
        del remaining[ear_index]
        guard -= 1
        if guard <= 0:
            raise GeometryError("Polygon triangulation failed.")
    triangles.append((remaining[0], remaining[1], remaining[2]))
    return tuple(triangles)


def convex_polygon_intersection_area(
    first: tuple[Point2D, ...],
    second: tuple[Point2D, ...],
) -> float:
    first_points = _validate_polygon_vertices("first", first)
    second_points = _validate_polygon_vertices("second", second)
    return _validated_convex_polygon_intersection_area(first_points, second_points)


def _validated_convex_polygon_intersection_area(
    first: tuple[Point2D, ...],
    second: tuple[Point2D, ...],
) -> float:
    """Clip validated inputs, retaining validation of newly calculated coordinates."""
    clipped = list(_ensure_counter_clockwise(first))
    clip_polygon = _ensure_counter_clockwise(second)
    clip_edges = zip(clip_polygon, (*clip_polygon[1:], clip_polygon[0]), strict=True)
    for clip_start, clip_end in clip_edges:
        clipped = _clip_convex_polygon(clipped, clip_start, clip_end)
        if len(clipped) < 3:
            return 0.0
    return abs(signed_polygon_area(tuple(clipped)))


def polygon_bounds(points: tuple[Point2D, ...]) -> tuple[float, float, float, float]:
    polygon = _validate_polygon_vertices("points", points)
    x_values = tuple(point[0] for point in polygon)
    y_values = tuple(point[1] for point in polygon)
    return (min(x_values), min(y_values), max(x_values), max(y_values))


def polygon_self_intersects(points: tuple[Point2D, ...]) -> bool:
    polygon = _validate_polygon_vertices("points", points)
    segment_count = len(polygon)
    for first_index in range(segment_count):
        first_start = polygon[first_index]
        first_end = polygon[(first_index + 1) % segment_count]
        for second_index in range(first_index + 1, segment_count):
            if _segments_are_adjacent(first_index, second_index, segment_count):
                continue
            second_start = polygon[second_index]
            second_end = polygon[(second_index + 1) % segment_count]
            if _segments_intersect(first_start, first_end, second_start, second_end):
                return True
    return False


def point_intersects_polygon(point: Point2D, polygon: tuple[Point2D, ...]) -> bool:
    raw_point_value = cast(object, point)
    if type(raw_point_value) is not tuple:
        raise GeometryError("point must be a Point2D tuple.")
    raw_point_tuple = cast(tuple[object, ...], raw_point_value)
    if len(raw_point_tuple) != 2:
        raise GeometryError("point must be a Point2D tuple.")
    point_x = validate_finite_number("point x", raw_point_tuple[0])
    point_y = validate_finite_number("point y", raw_point_tuple[1])
    target = (point_x, point_y)
    return any(_point_in_triangle(target, triangle) for triangle in triangulate_polygon(polygon))


def _find_ear_index(vertices: tuple[Point2D, ...]) -> int | None:
    for index, current_point in enumerate(vertices):
        previous_index = (index - 1) % len(vertices)
        next_index = (index + 1) % len(vertices)
        previous_point = vertices[previous_index]
        next_point = vertices[next_index]
        if _cross(previous_point, current_point, next_point) <= GEOMETRY_EPSILON:
            continue
        triangle = (previous_point, current_point, next_point)
        if any(
            _point_in_triangle(point, triangle)
            for point_index, point in enumerate(vertices)
            if point_index not in {previous_index, index, next_index}
        ):
            continue
        return index
    return None


def _clip_convex_polygon(
    subject: list[Point2D],
    clip_start: Point2D,
    clip_end: Point2D,
) -> list[Point2D]:
    if not subject:
        return []
    output: list[Point2D] = []
    previous = subject[-1]
    previous_inside = _left_of_or_on_edge(previous, clip_start, clip_end)
    for current in subject:
        current_inside = _left_of_or_on_edge(current, clip_start, clip_end)
        if current_inside:
            if not previous_inside:
                output.append(_line_intersection(previous, current, clip_start, clip_end))
            output.append(current)
        elif previous_inside:
            output.append(_line_intersection(previous, current, clip_start, clip_end))
        previous = current
        previous_inside = current_inside
    return output


def _line_intersection(
    first_start: Point2D,
    first_end: Point2D,
    second_start: Point2D,
    second_end: Point2D,
) -> Point2D:
    first_dx = first_end[0] - first_start[0]
    first_dy = first_end[1] - first_start[1]
    second_dx = second_end[0] - second_start[0]
    second_dy = second_end[1] - second_start[1]
    denominator = (first_dx * second_dy) - (first_dy * second_dx)
    if abs(denominator) <= GEOMETRY_EPSILON:
        return first_end
    numerator = ((second_start[0] - first_start[0]) * second_dy) - (
        (second_start[1] - first_start[1]) * second_dx
    )
    ratio = numerator / denominator
    return (first_start[0] + (ratio * first_dx), first_start[1] + (ratio * first_dy))


def _ensure_counter_clockwise(vertices: tuple[Point2D, ...]) -> tuple[Point2D, ...]:
    if _signed_polygon_area(vertices) < 0.0:
        return tuple(reversed(vertices))
    return vertices


def _point_in_triangle(point: Point2D, triangle: tuple[Point2D, ...]) -> bool:
    first, second, third = triangle
    return (
        _cross(first, second, point) >= -GEOMETRY_EPSILON
        and _cross(second, third, point) >= -GEOMETRY_EPSILON
        and _cross(third, first, point) >= -GEOMETRY_EPSILON
    )


def _left_of_or_on_edge(point: Point2D, edge_start: Point2D, edge_end: Point2D) -> bool:
    return _cross(edge_start, edge_end, point) >= -GEOMETRY_EPSILON


def _segments_are_adjacent(first_index: int, second_index: int, segment_count: int) -> bool:
    return (
        first_index == second_index
        or (first_index + 1) % segment_count == second_index
        or (second_index + 1) % segment_count == first_index
    )


def _segments_intersect(
    first_start: Point2D,
    first_end: Point2D,
    second_start: Point2D,
    second_end: Point2D,
) -> bool:
    first_orientation = _cross(first_start, first_end, second_start)
    second_orientation = _cross(first_start, first_end, second_end)
    third_orientation = _cross(second_start, second_end, first_start)
    fourth_orientation = _cross(second_start, second_end, first_end)
    if (
        first_orientation * second_orientation < -GEOMETRY_EPSILON
        and third_orientation * fourth_orientation < -GEOMETRY_EPSILON
    ):
        return True
    return (
        _point_on_segment(second_start, first_start, first_end)
        or _point_on_segment(second_end, first_start, first_end)
        or _point_on_segment(first_start, second_start, second_end)
        or _point_on_segment(first_end, second_start, second_end)
    )


def _point_on_segment(point: Point2D, start: Point2D, end: Point2D) -> bool:
    orientation = _cross(start, end, point)
    if abs(orientation) > GEOMETRY_EPSILON:
        return False
    return (
        min(start[0], end[0]) - GEOMETRY_EPSILON
        <= point[0]
        <= max(start[0], end[0]) + GEOMETRY_EPSILON
        and min(start[1], end[1]) - GEOMETRY_EPSILON
        <= point[1]
        <= max(start[1], end[1]) + GEOMETRY_EPSILON
    )


def _point_to_segment_distance(point: Point2D, start: Point2D, end: Point2D) -> float:
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    length_squared = (delta_x * delta_x) + (delta_y * delta_y)
    if length_squared <= GEOMETRY_EPSILON * GEOMETRY_EPSILON:
        return math.dist(point, start)
    projection = (
        ((point[0] - start[0]) * delta_x) + ((point[1] - start[1]) * delta_y)
    ) / length_squared
    clamped_projection = min(1.0, max(0.0, projection))
    closest = (
        start[0] + clamped_projection * delta_x,
        start[1] + clamped_projection * delta_y,
    )
    return math.dist(point, closest)


def _cross(first: Point2D, second: Point2D, third: Point2D) -> float:
    return ((second[0] - first[0]) * (third[1] - first[1])) - (
        (second[1] - first[1]) * (third[0] - first[0])
    )


def _validate_polygon_vertices(
    field_name: str,
    values: object,
) -> tuple[Point2D, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    points: list[Point2D] = []
    for index, value in enumerate(cast(tuple[object, ...], values)):
        if type(value) is not tuple:
            raise GeometryError(f"{field_name} must contain Point2D tuples.")
        raw_point_values = cast(tuple[object, ...], value)
        if len(raw_point_values) != 2:
            raise GeometryError(f"{field_name} must contain Point2D tuples.")
        x = validate_finite_number(f"{field_name}[{index}] x", raw_point_values[0])
        y = validate_finite_number(f"{field_name}[{index}] y", raw_point_values[1])
        points.append((x, y))
    if len(points) < 3:
        raise GeometryError(f"{field_name} must contain at least three points.")
    return tuple(points)
