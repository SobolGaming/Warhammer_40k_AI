# Current Core catalog description correction

Exact base: `b27c5d4e5f75dd7f89353a968a88d1b24b2681a4`.

The current native catalog copied historical global paragraphs for Stealth,
Infiltrators, Scouts, Lone Operative and Fights First. The bounded correction
replaces 35 descriptions across 18 distinct units: 24 in native60 and 11 in
paired27. All 39 current occurrences are enumerated, including four already-current
Stealth descriptions (three paired and Be'lakor in standalone Daemons5).

`tools/core_deadly_demise_catalog_overlay.py` now owns one additional small
five-family adapter. The native generator applies it after its existing unchanged
Deadly Demise adapter. Paired27 inherits it and drops its redundant final Stealth
call. Standalone Daemons generation and its existing Stealth adapter stay unchanged.
The adapter requires reviewed numeric ability IDs, owning datasheets, source-row
IDs, kinds, parameter tuples and complete historical text hashes, and rejects
missing/duplicate/unreviewed occurrences or repeated application. Absent-family
selections remain unchanged. Only descriptions and required provenance change.

The source-only `core_descriptions_2026_11` package admits complete Infiltrators
24.20, Lone Operative 24.24, Scouts 24.31 and the linked Scout Move 24.32 dependency.
Stable existing Core rule IDs are retained; package/version identity is new.
Both reviewed transcription and maintained-mirror evidence are `loaded` and
`not_certified`, with no runtime consumers claimed. New source-catalog and audit
tuples extend the current authority registry; old source bytes/registrations stay
unchanged. Existing Stealth and Fights First source pins remain controlling.

Fresh complete rendered major sections from 40k.app were observed at
`2026-11-03T01:12:44.736Z`. Raw rendered text and transfer checks are retained
in `data/source_audits/core_descriptions_2026_11/reviewed-observations.json`.
The prior 3 November date-precision capture and selected Order97 Game Datamissions
blocks are retained as comparison evidence. Apostrophe/hyphen typography,
control markup, bullet characters, and Scout Move table label/order differences
are explicit. Approved proposed wording/hashes are preserved. No App build,
co-version identity, official-primary authority or network-byte capture is inferred.
The expanded Lone Operative 24.24.01 note is retained as companion evidence;
its execution is not certified by this admission. Fights First deliberately uses
the existing pinned operative sentence; the advisory See 12.04 sentence is omitted.

`catalog-description-delta.json` preserves baseline descriptors, exact package
hashes and complete source/artifact inventories. The regression projection first
authenticates each current descriptor and current provenance, then restores only
approved prose/provenance before comparing the whole original package hash.
Canonical packages sort artifact provenance by name; no extra order delta is
allowed. The PR611 historical comparison authenticates this new projection before
its unchanged Deadly Demise projection; its original expected hashes are unchanged.
Unrelated prose, structured fields, geometry, RuleIR, support flags, defaults,
points and relationships remain protected by whole-package comparison.

Native factory and typed persistence controls preserve Scouts 6/7/9 parameters,
model-complete ability recognition and Lone Operative descriptor identity. Existing
Deadly Demise and Rangers consumer controls remain required. This correction
establishes no full Scouts-alternative, wider Lone Operative visibility, faction,
or full-game certification. Those validation gaps and three unresolved numeric
flying-base diameters remain outside this scope; no defect is inferred from the gaps.
No decision contract, gameplay handler or engine mutation changes.

The performance policy adds one exact-base declaration for the same catalog
generator operation. Its authenticated new layer projects back to the immutable
PR611 policy bytes; old proof files and sensitive-category obligations remain.
The required serial current-runtime smoke and all exact-head local/hosted gates,
65% full-package branch coverage, and separate reviews remain mandatory.
Focused checks are separate evidence and do not imply those final gates passed.
