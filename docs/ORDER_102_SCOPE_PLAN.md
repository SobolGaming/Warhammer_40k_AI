# Order 102 / P04F: Fight selection and actual fighting

Finding C04-07, exact implementation base
`ba3e3898e53bce6d8c23570e1ddaa224af59d55c` (the verified V963-SHOCK merge).
This order separates consuming a Fight selection from making melee attacks.
The original Order 97 inventory and earlier diagnostic drafts remain historical.

## Source and acceptance

The selected obligation is `04.03.05-obligation-04`, source row
`rule:04:04.03.05:1`: selection without melee attacks does not mean the unit fought.
The weaponless FAQ `faq:9bfa47ed-be8d-4e11-80de-f3832d507ca1` still permits selection
and the ordinary Fight type sequence. Its retained transcription hash is
`8d4f6b7b01b92637f2848b261fe07f970ef819f1ee867b889e885d1bdcbb1ada`.
The selected 04.03.05 block 4 canonical-JSON value hash is
`a38e104374d7d5c36bb772de309d516234f078028286cdba94d28b4e680faeb7`;
the canonical source-object hash for row `rule:04:04.03.05:1` is
`369202cd0d9cd87f78ec2143d8431868dfc9b53d821eb16bdaaf7de7725438a8`.
These use `core_rules_order84_capture.fingerprint` (UTF-8 canonical JSON),
not file-byte hashes. These observations are retained in the Order 97 source
inventory and the task-local source reconciliation; no new provider/version
equivalence is inferred.

The complete 05.04.05 observation and retained-presence FAQ in
`core_fight_on_death_2026_09` require actual attacks/fighting before early cleanup;
otherwise retention lasts until phase end. The reviewed transcription hash is
`b4398b729037efaade1d9649d8dfff421d118959a46ebcb222f801b79d8ec37a`.
This corrects an earlier draft regression which expected immediate removal after
an empty selection. Its passing test was not proof of legal behavior. The normal
premature-cleanup checkpoint and review finding O102-RULE-002 remain preserved.

Acceptance covers ordinary and retained selections, no extra activation, both
after-fought timing consumers, retained cleanup, normal persistence, both viewers
and exact replay. Engaging Normal/Overrun responses and V963-SHOCK's absence of a
forced Fight queue remain controls. No Order 103, dependency, or other V963 work
is included.

## Shared authority and consumers

`fight_selection_completion` derives the exact activation's declaration boundary
or accepted melee decision and completed executor. A matching executed HIT step
establishes actual fighting, including a miss or automatic hit. Declared pools,
ranged attacks and unrelated sequences do not establish it.

`fight_activation_completion` emits one pre-cleanup `fight_selection_completed`
marker. It emits `unit_has_fought` only with actual melee evidence. Once-only
selection remains owned by the existing Fight order; neither marker grants a new
activation. Counter-offensive and the generic Fight interrupt consume the actual
fought event. Forced response timing exclusions retain their existing authority.

Selection-history reconstruction in `active_player_boundary_history`,
`fight_continuation_checkpoint` and `consolidation_continuation_history` uses the
completion marker. Retained destruction's early-cleanup history still requires
actual `unit_has_fought`. Armed cleanup may pause before the final
`fight_activation_completed`; resuming does not repeat selection, attacks, timing,
or either completion. Empty selections finish normally with retained models still
WAITING, and the existing END_PHASE owner resolves their later destruction rules.

A real armed retained demise/FNP checkpoint exposed a pre-existing restoration
failure (O102-RESTORE-001), also reproduced on the actual base. The executor had
closed its active-player scope while cleanup still held the selection. The narrow
`active_player_scope_history` repair recognizes the exact authenticated completed
sequence instead of requiring that scope to reopen. Live player ownership and
scope order are unchanged; a completed executor with zero HIT likewise remains
closed. No-declaration selections keep their scope until final completion.

The same-bug-class audit found the model-level `requires_not_fought_this_phase`
destruction condition reading selected-unit membership. Its Wraithblades/Total
Carnage source condition is distinct from once-only activation. No normal
same-current-order denial was reproduced in this order. Engaging uses a separate
forced order and does not demonstrate that denial. This source mismatch remains a
separate queued model-predicate investigation; substituting unit-level fought
membership would not establish model participation and is not included here.

## Tests, contract and evidence limits

The facade regressions cover weaponless and armed/no-target empty selections,
misses and automatic hits, both timing consumers, armed retained pending cleanup,
empty retained presence through remaining Fight play and real phase-end cleanup,
normal save/load, viewer projections/event streams, exact replay, and both Engaging
Fight types. Cardinality assertions bind one selection, one selection completion,
at most one actual-fought event and one final completion. Existing synthetic
presence/target-history tests use the authenticated phase-end cleanup boundary;
they do not fabricate attacks or claim to reproduce legal selection.

The older timing and retained-cleanup positive controls previously used ranged-only
infantry. They now equip explicit low-damage melee and require the intended unit
to produce a completed melee executor and HIT attempt before testing those effects.
The original Order97 phase15c assertion file remains byte-for-byte archived at
`data/source_audits/order102/baseline/tests/unit/test_phase15c_fight_order.py.txt`,
from reviewed commit `8007555ef23e85c11d39b294acec02bd83fc3271`. The separate pinned
map preserves the original 305,916-byte input and its existing `0f3d5232...` pin.
It authenticates historical assertions only; the current tests still run normally.
The rule requirement itself remains operative and has not been superseded.

Contract 42.2 documents the new public event and narrower actual-fought semantics.
The event-delta schema already permits named events and arbitrary JSON payloads;
decision/submission validation, mutation authority, visibility and the existing
final completion event remain unchanged. Family schema versions and the immutable
42.0 persistence contract are retained. Exact engine-build matching still applies
to saves and replay; no migration or compatibility shim is introduced.

The v3 performance assessment measures the actual base and current runtime with
one shared bounded Fight reconstruction driver, three samples per operation,
whole histories and unchanged budgets. The old Order 72 test contains an obsolete
empty-fought expectation and cannot be reused unchanged across runtimes. Its
historical end-to-end results are retained. Current component timings do not
refresh those historical claims or establish long-game scalability.

The base rejects its own armed pending-cleanup persistence checkpoint; that
failure is retained separately. A rejected reconstruction is never a successful
paired sample. Successful armed post-cleanup restore and pending replay cover
the shared work, with current-only armed pending restore explicitly unmatched.
All current smoke, semantic/work/cache, generated/contract/package, type, shard,
full covered behavior, full quality, hosted CI and both exact-head independent
reviews remain required. Final receipts are attached to the PR; this document
does not itself claim those gates passed or certify complete games/Core Rules.


The first complete covered run exposed four post-executor fixture declarations
whose source selection IDs differed from their installed selections. The shared
fixture now accepts and checks the typed selection; the Horror interrupt fixture
records that selection before its declaration. Its synthetic executor has no HIT,
so it asserts no actual-fought event while retaining exactly one selection/final
completion, materialization and reaction resumption. The WS13 and Malevolent
controls retain their actual executor, model/FNP routing and replay assertions.
The original 19,339-byte shared declaration helper is also archived under the
Order102 historical map, preserving its original `b6bf5119...` Order97 pin.

The EC chain's original deterministic history completed fourteen retained attacks,
with two wounds both saved and no child casualty. Its expected child reaction was
therefore a positive-fixture mismatch. The corrected fixture uses disjoint 60 mm
bases and a recorded deterministic game ID that reaches both real casualty and
retention branches; weapon profiles, RNG authority, ordinary alternation and
non-nesting assertions are preserved. All original failed histories and candidate
outcomes remain external evidence. No production fallback was added for these
five test failures.

Those regression-only fixtures are not imported by the timed Fight driver, but
they belong to the policy's complete declared input inventory. The initial passed
comparison is preserved with its original hashes; a fresh actual-base/current
serial comparison binds the final inventory. The same eight matched operations,
three samples, unchanged budgets and separately unmatched pending restore remain.
