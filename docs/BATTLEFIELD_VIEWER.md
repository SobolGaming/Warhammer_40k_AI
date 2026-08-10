# Event Companion Battlefield Viewer

The local battlefield viewer renders the canonical
`battlefield-view-v2-phase17n` projection. It does not read PDF images, source
row geometry, or terrain names to reconstruct the board.

Start it from the repository root:

```powershell
uv run python scripts/mock_event_layout_ui.py --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/`, select `Purge the Foe` for both players, and use
Layout A, B, or C. The JSON envelope used by the viewer is available at
`http://127.0.0.1:8765/data.json`. Stop the server with `Ctrl+C`.

## Camera and inspection

- Drag or touch-drag the battlefield to orbit the camera.
- Use the mouse wheel, zoom slider, or `+` and `-` keys to zoom.
- Use the arrow keys to rotate when the battlefield has keyboard focus.
- Press `T` for a top view and `0` for the default isometric view.
- Use the Attacker Edge and Defender Edge presets to inspect the board from the
  corresponding source-defined edge.
- Click terrain, objectives, deployment zones, or regions for their stable ID,
  classification, kind, source, and volume details.

Independent controls show or hide the inch grid, territories and No Man's
Land, deployment zones, terrain areas, component footprints, walls, floors,
and objectives. Dense, Light, Mixed, and Unknown classifications have distinct
colors and hatch directions.

## Data boundary

Every selectable layout is passed through `MissionSetup`, an engine-created
empty deployment battlefield, and `project_battlefield_view(...)`. The viewer
renders these projection fields directly:

- authoritative terrain-area and component footprints;
- component classifications and wall/floor volumes;
- objective positions and dimensions;
- deployment-zone and battlefield-region shapes;
- render-only component asset hints; and
- the authoritative geometry hash and coordinate discriminators.

The camera is presentation-only. It converts the unchanged right-handed,
Z-up, inches-based coordinates to screen pixels. Rules geometry remains the
only source for component placement and dimensions; asset hints affect labels
only. Objective-to-terrain-area links are retained beside the projection in
the viewer-only envelope because that association is mission metadata rather
than part of `battlefield-view-v2-phase17n`.

## Honest scope

Nine of the 45 Event Companion layouts currently have runtime terrain
geometry. The viewer labels the other 36 as terrain-geometry pending and does
not fall back to legacy rectangles or image-derived guesses. It can still show
the objectives and deployment zones that the canonical projection supplies.

The three Purge the Foe versus Purge the Foe / Meatgrinder layouts contain the
complete Phase 17N exact slice: 16 terrain areas, 30 components, 70 wall
volumes, 20 floor volumes, six objectives, two deployment zones, two
territories, and No Man's Land. The result is a schematic geometry inspection
tool, not a photorealistic terrain renderer. Rendered pixels are
non-authoritative.
