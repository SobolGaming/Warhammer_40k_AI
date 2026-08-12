# Event Companion Battlefield Viewer

The local battlefield viewer renders the canonical
`battlefield-view-v3-phase17n` projection. It does not read PDF images, source
row geometry, or terrain names to reconstruct the board.

Start it from the repository root:

```powershell
uv run python scripts/mock_event_layout_ui.py --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`, select any supported player and opponent Force
Disposition pairing, and use Layout A, B, or C. All 15 pairings and all 45
layout variants are available. The JSON envelope used by the viewer is
available at `http://127.0.0.1:8765/data.json`. Stop the server with `Ctrl+C`.

## Camera and inspection

- Drag or touch-drag the battlefield to orbit the camera.
- Use the mouse wheel, zoom slider, or `+` and `-` keys to zoom.
- Use the arrow keys to rotate when the battlefield has keyboard focus.
- Press `T` for a top view and `0` for the default isometric view.
- Use the Attacker Edge and Defender Edge presets to inspect the board from the
  corresponding source-defined edge.
- Click terrain, source-linked objective footprints, deployment zones, or
  regions for their stable ID, classification, kind, source, and volume
  details. Objective identity labels remain presentation-only and are never
  converted into inferred selectable disks.

Independent controls show or hide the inch grid, territories and No Man's
Land, deployment zones, terrain areas, component footprints, walls, floors,
and source-linked objective footprints and labels. Dense, Light, Mixed, and
Unknown classifications have distinct colors and hatch directions. On the
terrain-area layer, a blue joined-circle glyph marks two physical footprint
pieces that page 8 defines as one logical terrain area; a red split-circle
glyph marks adjoining pieces that remain separate terrain areas.

## Data boundary

Every selectable layout is passed through `MissionSetup`, an engine-created
empty deployment battlefield, and `project_battlefield_view(...)`. The viewer
renders these projection fields directly:

- authoritative terrain-area and component footprints;
- component classifications and wall/floor volumes;
- source-linked objective terrain-area footprints and presentation-only
  objective identity labels;
- deployment-zone and battlefield-region shapes;
- render-only component asset hints; and
- the authoritative geometry hash and coordinate discriminators.

The closed battlefield projection retains all 720 physical terrain-area
footprints and the authoritative `logical_terrain_area_id` of each placement;
those IDs participate in its geometry hash. Single/Separate contact records
and their layout-page source icon coordinates live beside it in the viewer-only
envelope. The viewer fails closed if the projected IDs disagree with a Single
or Separate source contact interpreted using the page-8 legend.

The camera is presentation-only. It converts the unchanged right-handed,
Z-up, inches-based coordinates to screen pixels. Rules geometry remains the
only source for component placement and dimensions; asset hints affect labels
only. Polygons and grid segments that cross the camera near plane are clipped
before projection so supported close-camera settings retain their visible
geometry. Hatch generation intersects those projected bounds with the canvas
viewport, keeping per-frame drawing work bounded even when near-plane clipping
produces far-off-screen vertices. Objective-to-terrain-area links are retained
beside the projection in the viewer-only envelope because that association is
mission metadata rather than part of `battlefield-view-v3-phase17n`. The viewer
never converts the objective identity record's marker diameter into a
standalone rules or selection footprint.

## Coverage and authority

All 45 Event Companion layouts have source-hashed executable battlefield
packages. Every package contains 16 terrain-area footprint pieces, explicit
physical component placements, source-linked objective-to-terrain-area
bindings, two deployment zones, two territories, and No Man's Land. The 720
physical footprint pieces form 608 logical rules areas: 112 source-declared
two-piece Single joins plus 496 singletons. The package also contains 1,349
physical components. The page 9 Take and Hold versus Take and Hold Layout A
diagram contains one source-backed exception: it has 29 components because one
downed hovercraft has no tall-crate companion. Every other layout has 30
components.

The canonical generated artifact has SHA-256
`88ba6d7390eab060d6b0c53eb60afbfb1a6813dd80715e3d42562dd0c89128d9`
and package hash
`e6671232c7c298befccaf6c6f3000dfc21353830f6ae1a6ca5d10140b344a924`.
Its reviewed page-8 key plus pages-9-53 layout extraction has SHA-256
`a3e9392adeb52696902a016e3c3529933d1e99f3bfd67069d607410d8e1c137f`;
the generator also pins the stable runtime identity map at
`742ab841d1ec1e696f4a5c0e3f2e8c251203d510bf1da85fb30af88023cb64f3`.

All 224 layout-page contact glyphs are retained at 0.05-inch source precision
and interpreted using the page-8 legend: 112 Single and 112 Separate. Final
runtime footprint polygons preserve at most one 0.05-inch placement quantum of
source-fit residual and permit at most `0.000001` square inches of numerical
overlap. Of the 224 declared contacts, 43 have zero recorded gap and 181 retain
a source-fit open sliver no wider than 0.05 inches: 80 Single and 101 Separate.
Of those 43 zero-gap contacts, 41 also have zero overlap. Two page-12 Single
pairs have `0.00000087` square inches of overlap after six-decimal geometry
quantization; every other pair has zero recorded overlap.
Single joins share one rules identity and Separate pairs remain distinct, while
both preserve source-drawn open board between physical polygons. Two repeated
Single joins on pages 36 and 46 require one explicit
`0.011834688335`-inch exact normal correction after their 0.05-inch source
placement; those joins close with zero gap and zero overlap. The source anchors
remain separately recorded, and the strict artifact permits no other sub-grid
pose. Neither label invents rules footprint in source-drawn open board between
physical polygons. Each measured runtime gap and overlap is retained in the
generated artifact and validated by the viewer; source-measured
pre-finalization gaps remain separate provenance.
Objective centers retain the source vectors' finer 0.01-inch precision.
When a source-linked objective falls on one physical member of a Single pair,
its runtime terrain-objective binding expands to every physical member of that
logical terrain area; open-field objectives remain unbound.

The 14 shared terrain archetypes define recurring component footprints and
wall/floor geometry once for reuse by every layout. The page 9 exception has 69
wall volumes and 20 floor volumes; the other layouts each have 70 wall volumes
and 20 floor volumes. Objective counts follow the source layout and therefore
vary between five and six.

Battlefield availability does not imply that every associated Primary Mission
scoring rule is executable. Meatgrinder and the other explicitly
engine-implemented Primary Missions retain their existing scoring support;
non-Meatgrinder missions recorded as `source_known_engine_pending` remain
fail-closed until their missing choices, state, actions, and scoring conditions
are implemented. See [Mission Implementation Status](MISSION_IMPLEMENTATION_STATUS.md).

The viewer is a schematic geometry inspection tool, not a photorealistic
terrain renderer. Rendered pixels are non-authoritative, and no layout falls
back to legacy rectangles or image-derived guesses.
