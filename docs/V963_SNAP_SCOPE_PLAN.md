# V963-SNAP - ordinary Snap hits and independent Critical Wounds

The owner approved this dedicated prerequisite after Order114 / PR #554 and
before Order115. Exact base: `d6989dd266abc0e5d8e8f7de90020f9eddace1a7`, tree
`2cc74fdbf35e7ec6e2e09c17f813867e467bda89`. Order115 remains unstarted.
Apply the scoped review policy in `SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`.

## Controlling source

The complete 15.09 record is selected from the already retained English Core
body observed at `2026-10-01T12:04:31.127429+00:00`, at
`https://game-datamissions.com/11th/rules/core-rules`. Its retained asset is
`data/source_audits/v963_shock/captures/core-page.js`, SHA-256
`8b7e7a4004f8a55b17305013f181bf25933dff763e6737af407da254c5656026`.
The literal record and flattened transcription are reproduced offline by
`tools/build_core_critical_hits_source.py --check`; the selected source audit
is `data/source_audits/v963_snap/source.audit.json`.

15.09 requires an unmodified six irrespective of BS or modifiers, forbids hit
rerolls, and states that those hits are not critical hits. V963's September 30
changelog identifies the added restriction; the live body is timestamped and
has no asserted App-data version. The handoff separately records that v972's
October 2 changelog has no Core or FAQ changes. Game Datamissions is a
non-affiliated maintained mirror under the existing project authority policy;
this selection does not assert independent official GW corroboration.

The two complete v931 critical-hit FAQs remain byte-identical in the package
and observation audit. Their hit-threshold exceptions do not override the new
critical prohibition. An explicit hit-success permission remains distinct from
a critical-only threshold: the latter cannot grant hits when critical hits are
forbidden. Historical Order43 / PR #463 and Order97 facts remain historical.
Four exact Git-authenticated archives preserve the superseded source package
and original cited tests/helper; the Order97 resolver fails on missing or
corrupt copies. Its inventory stays unchanged and is not current certification.

## Ownership and consumers

`hit_thresholds.resolve_hit_thresholds` binds Snap and Fire Overwatch to the
selected stable source ID. `classify_hit_roll` is the shared execution and
`HitRoll` reconstruction authority. It preserves exact-six success independently
of skill/modifiers, vetoes critical classification, and ignores critical-only
threshold grants in Snap. The existing serialized source IDs carry that
authority without adding a field or adapter-specific path.

The consumer audit covers fixed and random attack counts; fixed and D3
Sustained Hits; Lethal Hits choices and history; critical-hit events;
source-backed dice-result trigger contexts; and generic/custom post-roll weapon
profile contexts. They consume the shared hit flag, so Snap produces no
critical-hit trigger, extra Sustained hit, D3 generation roll, or Lethal choice.
Torrent remains an automatic ordinary hit. Assigned effective dice values keep
Order84 semantics: six hits in ordinary Snap; seven does not.

Critical Wounds use their separate existing resolver. Anti-keyword and generic
critical-wound thresholds, critical-wound events and Devastating Wounds remain
possible after an ordinary Snap hit. No wound-stage production owner changes.
Ordinary Shooting and Fight critical-hit behavior remains covered positively.

## Contract and validation

Contract 44.3.1 records the current-source correction. Existing finite and
parameterized requests, envelopes, event/view payload shapes, visibility,
persistence and replay families cover it without a schema migration. Old saves
and replays require their original runtime; no compatibility shim is introduced.
Released baselines stay immutable. Exact-base bundle/client/conformance checks
and installed-wheel smoke remain required.

The regressions use canonical real fixtures and facade submissions. They cover
all D6 faces, modifiers, generic and explicitly scoped thresholds, fixed/D3
Sustained effects, fixed/random attacks, actual wound/damage completion,
Anti/generic Critical Wounds and Devastating Wounds. Legal pending/completed JSON
persistence, both viewer projections/event deltas, isolated fork continuation,
and exact replay use the same engine authority. The old Snap Lethal-choice
regression now requires its absence. Static audits protect shared classification
and complete source selection. The existing Damage Command Re-roll fixture now
rolls the Snap hit's real wound, declines the distinct wound reroll through the
lifecycle, and proves the failed save and subsequent Damage reroll window.
Failures and command receipts are retained in
the task's `v963-snap-state` directory.

This is a bounded source-backed rule correction, with no deliberate performance
change or demonstrated serious regression. The exact-base assessment and quiet
serial current-runtime smoke apply; historical reports and live semantic/work/cache
checks remain intact. No detailed-budget or complete-game certification is claimed.
Full covered inventory at 85% combined coverage, complete quality/type/lint/import
gates, both distinct exact-head reviews, hosted CI and protected merge are required.
