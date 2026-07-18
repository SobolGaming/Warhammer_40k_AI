# Coordinate system

CORE V2 battlefield coordinates use inches and a right-handed Cartesian frame:

- `x`: horizontal battlefield axis;
- `y`: vertical battlefield axis in the battlefield plane;
- `z`: height above the battlefield plane;
- origin: `(0, 0, 0)` at the scenario-defined battlefield origin.

Distances and positions are finite JSON numbers. A model pose contains a
three-dimensional position and `facing.degrees`. Facing is normalized to the
half-open interval `[0, 360)`. Zero degrees points along positive `x`; positive
angles rotate counter-clockwise toward positive `y` when viewed from above.

Lengths named `*_inches` are inches. Catalog base dimensions named `*_mm` are
millimetres and must not be mixed with battlefield coordinates without an
explicit conversion. Angles are degrees unless a field explicitly says
otherwise.

Physical movement is a path, not an endpoint. Movement, Charge Move, Pile In,
Consolidate, disembark, reserve placement, and reactive movement submissions
carry the proposal context and the required `PathWitness`/placement witness.
Only rules explicitly modelled as set-up or teleport placement may omit a
continuous path. The engine is the authority for collision, range, visibility,
coherency, and path validation.

Arrays are ordered when their schema or source object gives them replay meaning.
Clients must preserve emitted order and must not round coordinates, reorder
witness samples, or infer hidden positions.
