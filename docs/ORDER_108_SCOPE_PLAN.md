# Order 108 / P13B: terrain movement and Solid openings

This order implements C13-02 only: Exposed traversal, Dense floor crossing,
climbing contact, and Solid visibility/endpoint volumes. It does not certify
all Core Rules or complete-game performance.

## Selected source authority

The complete Game Datamissions observations in
`data/source_audits/order97/selected-sources.json` control under the approved
maintained App mirror policy. Their stable rows and source SHA-256 values are:

| Stable row | Source SHA-256 |
| --- | --- |
| `rule:13:13.06:1` | `3dc8a7351ba5246eb1d88731dd743a87972d3a9aa85427564a778b4d6f34ea24` |
| `rule:13:13.06.01:1` | `79a38af40707f2d30eaba4bd2526cdcd0dd52e0b3c31a0c98b296acd05e96b7a` |
| `rule:13:13.11:1` | `ee4c9d34c130f0ef3d7ef10dc7f76b648af9736c0ded4cdb04fa3e6c7c9a258e` |

The five selected obligations are `13.06-exposed-traversal`,
`13.06-dense-floor-crossing`, `13.06-vertical-contact`,
`13.06.01-solid-endpoint`, and `13.11-solid`. The normalized block 9 of 13.06
retains the half-inch character; the older raw capture's replacement glyph is
not used to invent a distance. The Solid designer note includes ground-level
doors. Original source observations, gap probes and assertion pins are retained.

## Shared owners and consumers

`TerrainAreaClassification` has an explicit `exposed` token. Existing typed
serialization/factory boundaries round-trip it. Exposed and Light share
horizontal/vertical transit permission. Exposed contributes no Dense property
to a logical area containing Light; all-Exposed areas remain Exposed.

`terrain_transit.py` owns continuous climbing contact and Dense floor crossings.
`TerrainPathLegalityContext` applies these predicates to witnessed real moves,
covering ordinary, attached, Charge, Fight and reactive consumers through their
shared movement authority. Fixed-facing translation uses analytic footprint
formulas over the entire segment, with a convex certificate for the common
single-volume case. Rotating witnesses use invariant inner disks, rectangular
support concavity between quadrant boundaries, and exact elliptical face
support minima. Remaining intervals use a conservative translation/rotation
displacement bound. Unresolved boundary calculations raise a domain error,
never sampled acceptance. Ordinary models measure from their support base;
FRAME models retain their all-part measurement rule. Taking to the Skies
exempts climbing contact.

The Dense floor predicate runs before the old thin-volume free-traversal
shortcut. It checks vertical support-base passage through actual floor slabs
and preserves Infantry, Beasts and Swarm permission. Exact interval support
separation proves clearance beside slabs for both fixed and rotating bases;
shrinking midpoint displacement bounds handle remaining rotating intervals. Exposed/Light transit
remains permitted. Existing endpoint support and upper-surface keyword gates
remain authoritative. A path entirely below a physical lintel is clear of it.

`terrain_solid.py` derives enclosed cells in aligned wall surfaces, with ground
closing a door's bottom, and clips them at three inches. Physical floor/ceiling
slabs also close openings within existing wall strips, including a slab narrower
than the wall thickness. Floor boundaries participate in the strip partition;
a slab does not create a new wall surface or fill the space between walls. The
partition follows rectangle boundaries; it does not fill area polygons, open corners, arbitrary
gaps between unrelated features, or the interior of a roofless ruin. Rotated
walls use local axes. Visibility adds these volumes to its continuous LOS
authority, including explicit-volume contexts and feature attribution. Movement
and set-up endpoint owners check every physical model part against the same
Solid geometry, including protrusions with otherwise clear support bases.

Physical transit volumes remain separate from Solid opening volumes. A model
that fits through a doorway may traverse its empty space and finish clear,
although sight and endpoints cannot penetrate the low Solid opening. Adapters
consume engine results. No decision family, proposal field or schema shape
changes. Contract 44.1 already represents classifications as nonempty strings;
the documented supported tokens now include Exposed. Saves/replays stay bound
to the regenerated exact runtime identity.

## Evidence and limits

At base `eebdaa2ccadef14b6115aea7caea3cb1c89eb564`, five focused regressions fail:
Exposed is rejected; an unqualified model crosses a thin Dense floor; a model
climbs outside half-inch contact; sight passes through an enclosed low window;
and its missing Solid volume is observable. The sibling `order108-state`
retains `base-red.xml`, original test bytes and command receipt. Controls cover
keyword/classification permissions, physical door transit, rotated windows and
doors, open/high gaps, protrusions, contact between sparse poses, and normal
facade rejection/retry with pending/completed persistence, both viewers and
exact replay. Fixture API mistakes and intermediate failures are recorded
separately from reproduced gameplay defects.

Older terrain fixtures now describe legal climbs while retaining their
assertions: the raw-container climb starts within half an inch of the surface;
the Event Companion Mobile route ascends and descends outside floor edges
before crossing the wall top. The Order 97 permitted-transit route approaches
horizontally before ascending within contact and descends before leaving it.
The Event Companion traversal diagnostic now identifies the actual ground wall;
the upper wall lies entirely above the model and cannot block that route. The
precise blocker assertion remains. Original `test_phase10i_terrain_movement.py`
bytes from merged Order 97 commit `19f1c507541321b7c1ed04f80e2c1110a1fa786d`
are authenticated by the existing historical resolver. No original assertion
or source pin is repinned.

The mixed-flight distance fixture retains its original paths and every distance
assertion while declaring a nearby wall for its non-FLY members to climb. The
support-alias cache test retains its original conservative proof assertion;
its reachability positive control raises the physical wall above the supported
floor, since a shared support ID cannot permit an endpoint inside Solid.
Original bytes of both test modules remain authenticated Order 97 evidence.
Visibility volume inputs are validated before Solid augmentation, preserving
the existing typed tuple boundary.

Complete covered behavior at 85%, quality/type/lint/contracts, hosted CI and
both clean exact-head reviews remain delivery requirements. The owner's
performance direction selects the serial live smoke and exact-base assessment
for this rules implementation. Historical measurements and live work/cache
checks remain intact; no complete-game certification follows from the smoke.

Order 109 starts in a fresh session only after 108 merges. Update its own roadmap
**How it is currently done** cell to actual implementation before input freeze,
and carry that requirement into each later handoff. Preserve the scoped review
policy; queue coordinated hand-edited-history hardening separately absent a
necessary supported boundary or reproduced normal engine path.
