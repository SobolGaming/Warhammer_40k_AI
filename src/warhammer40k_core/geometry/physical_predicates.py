"""Continuous physical-footprint predicates shared by collisions and certificates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from itertools import pairwise

from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.exact_contact import ExactDisk
from warhammer40k_core.geometry.exact_coordinate import rational_coordinate
from warhammer40k_core.geometry.exact_path import ExactDiskSweep
from warhammer40k_core.geometry.placement_predicates import Footprint, PlacementPredicates, rational
from warhammer40k_core.geometry.pose import GeometryError, Pose
from warhammer40k_core.geometry.visibility_algebra import Formula, both, decide, term
from warhammer40k_core.geometry.visibility_shapes import rational_rotation

_OVERLAP_TOLERANCE = Fraction(1, 1_000_000_000)
_MOTION_RESOLUTION_INCHES = 1e-10
_DIRECTION_RESOLUTION_INCHES = 1e-11
_ROUNDING_PAD_INCHES = 1e-12
_WAYPOINT_ROUNDING_TOLERANCE = 1e-12


def nonoverlapping(predicates: PlacementPredicates, first: Footprint, second: Footprint) -> Formula:
    if first.kind == second.kind == "circle":
        return ((first.x - second.x) ** 2 + (first.y - second.y) ** 2).ge(
            (first.a + second.a - _OVERLAP_TOLERANCE) ** 2
        )
    nx, ny, a, b = (predicates.scalar() for _ in range(4))
    return both(
        (nx * nx + ny * ny).eq(1),
        first.support_at_most(nx, ny, a),
        second.support_at_most(nx, ny, b),
        ((second.x - first.x) * nx + (second.y - first.y) * ny).ge(a + b - _OVERLAP_TOLERANCE),
    )


@lru_cache(maxsize=4096)
def physical_footprints_overlap(
    first: BaseShape, first_pose: Pose, second: BaseShape, second_pose: Pose
) -> bool:
    if type(first) is CircularBase and type(second) is CircularBase:
        return first_pose.distance_2d_to(second_pose) < first.radius + second.radius - 1e-9
    predicates = PlacementPredicates(prefix="physical_separation")
    return not decide(
        nonoverlapping(
            predicates, Footprint.fixed(first, first_pose), Footprint.fixed(second, second_pose)
        ),
        tuple(predicates.names),
    )


def planar_motion_segments(poses: tuple[Pose, ...]) -> tuple[tuple[Pose, Pose], ...]:
    """Coalesce equivalent waypoints before the bounded projected sweep."""
    retained: list[Pose] = []
    for pose in poses:
        while len(retained) >= 2 and _subdivides_motion(retained[-2], retained[-1], pose):
            retained.pop()
        retained.append(pose)
    return tuple(pairwise(retained))


def _subdivides_motion(start: Pose, middle: Pose, end: Pose) -> bool:
    a, b, c = start.position, middle.position, end.position
    first_turn = _shortest_turn(start, middle)
    entire_turn = _shortest_turn(start, end)
    if not math.isclose(
        first_turn + _shortest_turn(middle, end),
        entire_turn,
        abs_tol=_WAYPOINT_ROUNDING_TOLERANCE,
        rel_tol=0,
    ):
        return False
    partial = (b.x - a.x, b.y - a.y, b.z - a.z, first_turn)
    whole = (c.x - a.x, c.y - a.y, c.z - a.z, entire_turn)
    largest = max(range(len(whole)), key=lambda axis: abs(whole[axis]))
    if whole[largest] == 0:
        return middle == start
    t = partial[largest] / whole[largest]
    return 0 <= t <= 1 and all(
        math.isclose(offset, t * total, abs_tol=_WAYPOINT_ROUNDING_TOLERANCE, rel_tol=0)
        for offset, total in zip(partial, whole, strict=True)
    )


def _shortest_turn(start: Pose, end: Pose) -> float:
    # The sign of the authored endpoint difference breaks the half-turn tie.
    delta = end.facing.degrees - start.facing.degrees
    if delta > 180:
        return delta - 360
    if delta < -180:
        return delta + 360
    return delta


def _round_footprint(base: BaseShape) -> BaseShape:
    if isinstance(base, OvalBase) and base.length == base.width:
        return CircularBase(base.length / 2)
    return base


def moving_footprint_crosses(
    first: BaseShape, start: Pose, end: Pose, second: BaseShape, obstacle: Pose
) -> bool:
    """Detect strict overlap along linear translation and the signed shortest turn.

    Only XY footprints enter the check. A conservative support bound prunes
    whole intervals. A pose must actually overlap at the ordinary physical
    tolerance to count as crossing. At the motion resolution, any unwitnessed
    penetration can exceed that tolerance by at most 0.1 nanoinch.
    """
    first, second = _round_footprint(first), _round_footprint(second)
    turn = 0.0 if isinstance(first, CircularBase) else _shortest_turn(start, end)
    if start.position == end.position and turn == 0:
        return False

    radius = first.max_radius()
    limit = rational(radius) + rational(second.max_radius()) - _OVERLAP_TOLERANCE
    if isinstance(first, CircularBase) and isinstance(second, CircularBase):
        return _disk_path_crosses(start, end, obstacle, limit)

    # Circumscribed disks enclose every orientation and provide a planar
    # broad phase even when the model's height changes.
    if not _disk_path_crosses(start, end, obstacle, limit + rational(_ROUNDING_PAD_INCHES)):
        return False
    blocker = _FootprintSupport.at(second, obstacle)
    first_pose, last_pose = _FootprintSupport.at(first, start), _FootprintSupport.at(first, end)
    if (
        _separating_direction(first_pose, blocker) is None
        or _separating_direction(last_pose, blocker) is None
    ):
        return True

    # Reserve at most the 52 binary64 fractional bits for a segment.
    # Native movement reaches the spatial resolution well before this limit.
    intervals = [(start, end, turn, 52)]
    while intervals:
        left, right, angle, remaining = intervals.pop()
        radians = abs(math.radians(angle))
        middle = Pose.at(
            left.position.x + (right.position.x - left.position.x) / 2,
            left.position.y + (right.position.y - left.position.y) / 2,
            facing_degrees=left.facing.degrees + angle / 2,
        )
        normal = _separating_direction(_FootprintSupport.at(first, middle), blocker)
        if normal is None:
            return True

        # A material point follows a circular arc around its translating
        # center. Its deviation from the endpoint chord is at most max |p''|/8.
        # The same axis clears the entire interval when the endpoint
        # projections leave room for the sag and the rounding bound.
        # Accept the small directional uncertainty here as well, so a whole
        # path grazing the tolerance can be excluded without refining it.
        sag = radius * radians**2 / 8
        if (
            max(
                _gap(_FootprintSupport.at(first, left), blocker, normal),
                _gap(_FootprintSupport.at(first, right), blocker, normal),
            )
            + sag
            + _ROUNDING_PAD_INCHES
            <= float(_OVERLAP_TOLERANCE) + _DIRECTION_RESOLUTION_INCHES
        ):
            continue

        motion = (left.distance_2d_to(right) + radius * radians) / 2
        if remaining and motion > _MOTION_RESOLUTION_INCHES - _DIRECTION_RESOLUTION_INCHES:
            half = angle / 2
            intervals.extend(
                ((middle, right, half, remaining - 1), (left, middle, half, remaining - 1))
            )
    return False


def _disk_path_crosses(start: Pose, end: Pose, obstacle: Pose, limit: Fraction) -> bool:
    if limit <= 0:
        return False
    reach = math.nextafter(float(limit), math.inf)
    o = obstacle.position
    a, b = start.position, end.position
    if (
        o.x < min(a.x, b.x) - reach
        or o.x > max(a.x, b.x) + reach
        or o.y < min(a.y, b.y) - reach
        or o.y > max(a.y, b.y) + reach
    ):
        return False
    # Normalize by the actual radius sum to use the exact sweep without
    # snapping a native pose or catalog base to a milli-inch grid.
    origin_x, origin_y = rational(o.x), rational(o.y)

    def normalized(pose: Pose) -> ExactDisk:
        return ExactDisk(
            (
                rational_coordinate((rational(pose.position.x) - origin_x) / limit),
                rational_coordinate((rational(pose.position.y) - origin_y) / limit),
            ),
            1000,
        )

    return not ExactDiskSweep(normalized(start), normalized(end)).clears(normalized(obstacle))


_Vector2 = tuple[float, float]


@dataclass(frozen=True, slots=True)
class _FootprintSupport:
    center: _Vector2
    length_axis: _Vector2
    width_axis: _Vector2
    radius: float
    rectangular: bool

    @classmethod
    def at(cls, base: BaseShape, pose: Pose) -> _FootprintSupport:
        center = (pose.position.x, pose.position.y)
        if isinstance(base, CircularBase):
            radius = base.radius
            return cls(center, (radius, 0.0), (0.0, radius), radius, False)
        if not isinstance(base, OvalBase | RectangularBase):
            raise GeometryError("A projected sweep requires a circle, oval, or rectangle.")
        cos_angle, sin_angle = map(float, rational_rotation(pose.facing.degrees))
        a, b = base.length / 2, base.width / 2
        return cls(
            center,
            (a * cos_angle, a * sin_angle),
            (-b * sin_angle, b * cos_angle),
            base.max_radius(),
            isinstance(base, RectangularBase),
        )

    def extreme(self, normal: _Vector2) -> _Vector2:
        a, b = _dot(self.length_axis, normal), _dot(self.width_axis, normal)
        if self.rectangular:
            u, v = math.copysign(1.0, a), math.copysign(1.0, b)
        else:
            magnitude = math.hypot(a, b)
            u, v = a / magnitude, b / magnitude
        return (
            self.length_axis[0] * u + self.width_axis[0] * v,
            self.length_axis[1] * u + self.width_axis[1] * v,
        )


def _dot(a: _Vector2, b: _Vector2) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _minkowski_extreme(
    first: _FootprintSupport, second: _FootprintSupport, normal: _Vector2
) -> _Vector2:
    a, b = first.extreme(normal), second.extreme(normal)
    return (
        a[0] + b[0] + (first.center[0] - second.center[0]),
        a[1] + b[1] + (first.center[1] - second.center[1]),
    )


def _gap(first: _FootprintSupport, second: _FootprintSupport, normal: _Vector2) -> float:
    return _dot(_minkowski_extreme(first, second, normal), normal)


def _normal(angle: float) -> _Vector2:
    return math.cos(angle), math.sin(angle)


def _separating_direction(first: _FootprintSupport, second: _FootprintSupport) -> _Vector2 | None:
    """Return a candidate separating axis, or prove overlap in every direction."""
    dx, dy = second.center[0] - first.center[0], second.center[1] - first.center[1]
    bearing = math.atan2(dy, dx)
    extent = first.radius + second.radius + math.hypot(dx, dy)
    cutoff = float(_OVERLAP_TOLERANCE) + _ROUNDING_PAD_INCHES
    direction = _normal(bearing)
    if _gap(first, second, direction) <= cutoff:
        return direction

    quarter = math.pi / 2
    sectors = [(bearing + i * quarter, bearing + (i + 1) * quarter) for i in range(4)]
    while sectors:
        left, right = sectors.pop()
        middle = (left + right) / 2
        direction = _normal(middle)
        support = _minkowski_extreme(first, second, direction)
        if _dot(support, direction) <= cutoff:
            return direction

        # This one support point lower-bounds the true support throughout the
        # sector. Interior unit normals are positive combinations of the
        # endpoint normals with weights summing to at least one.
        if min(_dot(support, _normal(left)), _dot(support, _normal(right))) > cutoff:
            continue
        # Support is Lipschitz in the normal angle with constant at most
        # extent. Any unresolved contact differs from the physical threshold
        # by less than the directional resolution here.
        if (
            middle in (left, right)
            or extent * (right - left) / 2 <= _DIRECTION_RESOLUTION_INCHES - _ROUNDING_PAD_INCHES
        ):
            return direction
        sectors.extend(((middle, right), (left, middle)))
    return None


@lru_cache(maxsize=4096)
def physical_footprints_within(
    first: BaseShape, first_pose: Pose, second: BaseShape, second_pose: Pose, distance: float
) -> bool:
    predicates = PlacementPredicates(prefix="physical_proximity")
    return decide(
        predicates.near(
            Footprint.fixed(first, first_pose),
            Footprint.fixed(second, second_pose),
            term(rational(distance)),
        ),
        tuple(predicates.names),
    )
