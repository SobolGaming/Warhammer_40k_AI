# October Event Companion layout source

This bounded owner covers the page 8 key and all 45 diagrams on pages 9–53 of
the official 14 October 2026 v1.3 PDF. The retained original is pinned by SHA-256
`187253a9b6ea377f5e44d1148454bd042b165b03bb5c45c51a5880762bf56dc2`.
`official-source-observation.json` records the fresh index observation. July
mission-card transcriptions, scoring clauses and model-base rows retain their
historical ownership. This migration does not authenticate them as October.

## Reproduction

Use Python 3.12 with the exact development-only packages in
`tools/event_companion_layout_source/requirements.txt`, then run from the repo:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B tools/extract_event_companion_current_layouts.py --work-dir /tmp/event-layout-observations --check
PYTHONDONTWRITEBYTECODE=1 python -B tools/build_event_companion_battlefields.py --check
```

The first command authenticates both immutable PDFs and the untouched reviewed
July extraction, obtains vector paths, raster image transforms and contact
visibility, derives correspondence, and reproduces the current reviewed JSON
byte for byte. Its work directory holds raw observations and diagnostic fits;
those outputs are not alternate runtime sources. The second command applies
the reviewed physical models and quantization, then checks the canonical artifact.
The source packages do not add PDF/scientific dependencies to engine runtime.

## Identity and modeling conventions

`current_source_correspondence` records every physical footprint's old/current
source sequence, shape-compatible displacement assignment, current components,
objective roles and stable/new IDs, and visible contact associations. These are
project continuity IDs: Games Workshop does not label each physical piece with
a stable identifier. Footprint IDs use shape family and minimum displacement;
component IDs are footprint slots, and changed slot archetypes are explicit.
Existing objective IDs use same-role nearest correspondence. Each Reconnaissance
mirror layout adds `central-02`; the nearest old central retains `central-01`.
These conventions neither broaden the ordinary loader nor the finite A32 recovery.

Current source observations independently cover 720 outlines, 1349 components,
249 objectives and 219 visible contacts. 103 disjoint Single pairs yield 617 logical
areas; Separate pairs remain distinct. Single objective bindings expand to all
physical members of the logical area. Source coordinates and final geometry are
separate: terrain uses 0.05 inch placement, objectives 0.01 inch, final contacts retain
at most 0.05 inch gap and 1e-6 square-inch numerical overlap. Existing shared component
physical dimensions, heights, wall/floor models and printed nominal deployment
templates remain explicit project assumptions; raster artwork is not an exact
physical specification.

`migration-review.json` records every retained/retired fixed-pose table row,
fresh Meatgrinder registration, unchanged board/deployment controls, the p53
paint correction, p47 decorative-border exception, p35 obscured symbol,
historically omitted p11 contacts and the new xref 356 crop midpoint convention.
The old p46 exact-seam exception is retired; unchanged p36 retains its exact
source-ID-bound correction. No placement/contact tolerance was expanded.

Source review is not full-game certification. Final tests, type/quality/coverage,
generated contracts, performance and exact-head remote gates are separate evidence.

Page 10's central marker remains an ordinary point objective: its raw center is
0.054079 and 0.068049 inches outside the two nearest source outlines. The simplified
quantized runtime footprint overlaps it by 0.069997 inches, but no component does.
The supported control-source resolver preserves the ordinary point; it does not
infer a link from nominal terrain-area overlap. The other three source-unbound
markers remain ordinary points too. This bounded model overlay is recorded rather
than changing source binding thresholds or manufacturing a source relationship.
