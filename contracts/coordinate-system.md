# Battlefield coordinate and geometry contract

Version: `battlefield-coordinate-v1`

Wire coordinate space: `battlefield_inches_right_handed_z_up`

This document is normative for `battlefield-view-v3-phase17n`, movement/placement
proposals, and battlefield rendering. The JSON Schema is
`schemas/battlefield-view.schema.json`.

## World frame and units

CORE V2 uses a camera-independent, right-handed Cartesian world frame:

- `x` increases from the battlefield origin along the battlefield width;
- `y` increases along battlefield depth in the battlefield plane;
- `z` increases above the battlefield plane;
- `(0, 0, 0)` is the lower-left corner of the battlefield when viewed from
  positive `z` with positive `y` pointing up;
- battlefield bounds are closed in `x` and `y`, start at zero, and use the
  emitted `max_x_inches` and `max_y_inches` values.

All battlefield positions and lengths named `*_inches` are inches. Source and
catalog dimensions named `*_mm` remain millimetres; a client must not mix them
with battlefield coordinates without an explicit `25.4 mm = 1 inch`
conversion. JSON numbers must be finite. Clients preserve emitted numeric
values and do not round or snap authoritative geometry.

Angles are degrees in the half-open interval `[0, 360)`. Zero degrees points
along positive `x`; positive rotation is counter-clockwise toward positive `y`
when viewed from above. Circle, ellipse, and rectangle shapes always have a
point-valued `center`; `null` is invalid for those kinds. For ellipses and
rectangles, `length_inches` is the full extent along the shape's local `x`
axis and `width_inches` is the full extent along its local `y` axis.

Model shape centers are local offsets from the model pose and rotate with the
model pose. Their world-axis rotation is
`(pose.facing_degrees + shape.rotation_degrees) mod 360`: the center offset is
rotated by model facing, then the shape rotates about that translated center.
For non-model shapes, `rotation_degrees` is an absolute world rotation about
the emitted center. Terrain volume `bottom_center` positions are absolute
world coordinates and their `rotation_degrees` is likewise an absolute world
rotation. Polygon vertices are already absolute world coordinates, have no
separate pivot or local frame, and therefore require
`rotation_degrees = 0` and `center = null`.

## Polygon representation and tolerance

Polygons are unclosed arrays of at least three vertices. Exterior rings are
counter-clockwise. Holes are represented as explicit circle or polygon
cutouts, never inferred from winding. The first vertex is not repeated at the
end, and array order is stable replay data.

The engine owns numerical tolerances for collision, range, visibility,
coherency, placement, and path validation. A client must not expand or shrink
geometry by its own epsilon and must treat interaction/render geometry as
advisory presentation data. Equality shown by the payload does not grant rule
legality; only an accepted engine submission does.

## Three geometry classes

`battlefield-view-v3-phase17n` deliberately separates:

1. `authoritative`: engine/source-owned model measurement footprints and
   heights, model poses and physical states, terrain footprints/volumes,
   terrain areas, objectives, deployment zones, and battlefield regions.
   These fields participate in `authoritative_geometry_hash`.
2. `interaction`: engine-authored selected-or-acting entity references, engine-emitted legal
   decision-option references, measurement overlays, and typed line-segment
   path overlays. These help construct a submission but never authorize it.
3. `render`: hit regions and asset hints. They can change without changing
   collision, movement, visibility, range, engagement, coherency, placement,
   objective control, or any other authoritative rule result.

The frontend never derives rules geometry from sprites, meshes, textures,
images, hit regions, or asset dimensions. A render or interaction payload is
not an executable instruction.

## Models, hulls, and support bases

Model entities expose one or more local measurement shapes and a representative
height. `measurement_basis = base` means the measurement shapes are based
footprints. `measurement_basis = hull` means they are accepted hull footprints.
Circular, oval, rectangular, and accepted hull parts are expressed as typed
circle, ellipse, rectangle, or polygon shapes. Multiple shapes represent a
composite footprint.

Model measurement geometry also carries its geometry and height source kinds
and source IDs. Those provenance fields participate in the authoritative hash,
so a source-identity change is drift even when the resulting dimensions happen
to match.

`support_shape` records the physical support base independently of the rules
measurement footprint. A flying model can therefore expose an accepted hull
for measurement and collision while retaining its circular or oval support
base for presentation. Clients must not substitute the support shape for an
authoritative hull or infer a hull from the support base.

Model `state` is explicit: `placed`, `destroyed`, `embarked`, `reserves`,
`removed`, or `undeployed`. A pose is present only while authoritative
battlefield state still retains that model's placement; this can include a
destroyed model retained temporarily for engine-owned destruction reactions.
Viewer-scoped projections omit hidden enemy model entities entirely; an absent
entity is not evidence of reserves, embarkation, destruction, or roster size.

## Terrain, objectives, and regions

Terrain feature footprints and volumes are authoritative collision/visibility
inputs. Terrain hit regions and asset IDs are separate render data. Terrain
areas are typed source-backed physical polygons. Each carries a required
`logical_terrain_area_id`: isolated footprints use their physical ID, while
source-defined multi-piece terrain areas share a distinct logical ID. Clients
render the physical polygons and apply terrain-area rules to the logical group;
the grouping participates in `authoritative_geometry_hash`. Shared logical
identity does not fill or interpolate open board between disjoint physical
polygons; containment and visibility use the physical polygon union. A logical
terrain area is indivisible when linked to an objective: every
`objective_terrain_areas[*].terrain_area_ids` entry that references one physical
member must contain every physical member carrying that logical ID. Layout,
mission-setup, create-session, replay, and objective-control validation reject
partial membership before authoritative state is created or scored. A logical
identity supplied by a client is not self-authenticating: source-backed setup
geometry requires its `battlefield_layout_id` and is reconciled with the
canonical mission-pack layout, so removing a member and relabelling the survivor
as a singleton is also invalid. State-backed objective-control contexts must
use the exact terrain-area inventory carried by their authoritative mission
setup. A logical
group with one known member classification retains it; differing known member
classifications aggregate to `mixed`, and `unknown` cannot mix with a known
classification. Objectives expose an inches-based world position and marker
diameter; source/package artifacts retain any original
millimetre dimensions outside this battlefield wire payload.
Deployment zones and battlefield regions use one or more exterior polygons plus
explicit cutouts.

## Paths and placement

Physical movement is a path, not an endpoint. Movement, Charge Move, Pile In,
Consolidate, disembark, reserve placement, and reactive movement submissions
carry their proposal context and the required `PathWitness` or placement
witness. Only rules explicitly modelled as set-up or teleport placement may
omit a continuous path.

Battlefield path overlays use ordered straight `line` segments with start and
end poses. They are explanations or editing aids; the submitted witness remains
the validation input. Clients preserve segment and witness order and never
replace a required path with its final pose.

## Hashes, visibility, and client responsibilities

`authoritative_geometry_hash` covers the coordinate-spec version, battlefield
bounds, and complete viewer-visible authoritative entity payload. The outer
projection hash also covers interaction and render data. Movement and shared
placement proposal requests carry an opaque engine-owned
`spatial_context_hash` over authoritative placements, terrain, mission
geometry, model physical state, dimensions, and geometry provenance. The
engine recomputes and validates that token before queue pop; source identity
drift is stale even when dimensions are unchanged. The viewer-scoped
`authoritative_geometry_hash` is informational and is never validation
authority. Neither hash is permission for a client to mutate state.

Clients may transform world coordinates into camera/screen coordinates for
display, but submissions and cached authoritative entities remain in the world
frame above. Clients must preserve stable entity IDs, array order, coordinate
precision, viewer redaction, and engine-emitted legal option references. They
must not infer hidden positions or create candidate IDs that the engine did not
emit.
