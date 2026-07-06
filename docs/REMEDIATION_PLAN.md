# CORE V2 Remediation Plan (2026-07 design review)

**Status: archived — complete.** Archived on 2026-07-06 after WS1-WS15 landed on
`main`, with WS15 closing in PR #277. This document is retained as the historical
implementation record for the July 2026 design-review remediation; it is no
longer an active execution plan.

This archived plan records the findings of the July 2026 design review and the
workstreams used to remediate them. The original execution guidance is preserved
below for auditability.

## Ground rules for the implementing agent

- Follow every AGENTS.md invariant. This plan never authorizes weakening one.
- Behavior-preserving refactors must be guarded by the existing replay tests
  (`tests/replay/`) and the full test suite. If a refactor changes any replay
  hash, event payload, or DecisionRecord shape, stop and report.
- Every bug fix follows the AGENTS.md bug-fix policy: name the violated
  invariant, search for the same bug class elsewhere, share the fix, add a
  regression test, and add a static/code-quality audit when feasible.
- Run before each PR:
  `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy src tests`, `uv run pyright`, `uv run pytest tests/`,
  `uv run lint-imports`, `uv run pre-commit run --all-files`.
  If a command cannot be run, say so; do not claim it passed.
- Do not start a later workstream while an earlier one in the same track is
  half-merged, except where marked independent.

## Pre-approved decisions (do not stop-and-ask for these)

The project owner has approved:

1. Treating `warhammer40k_core.profiling` as an adapter-level package
   (may import `engine`; nothing imports it) and adding import-linter
   contracts for it (WS3).
2. Fixing the network server secret-metadata leak, including changing the
   assertions in `tests/unit/test_phase18e_server_api.py` that currently
   encode the leak as expected behavior (WS1).
3. Introducing a central decision-handler registry inside the engine to
   replace the `submit_decision` if/elif ladder, provided the external
   decision contract, DecisionRecord payloads, and replay output are
   unchanged (WS6).
4. Updating `docs/ADAPTER_DECISION_CONTRACT.md` in the same PRs where
   adapter-visible behavior changes (WS1, WS5).
5. **Phase 17G scaling strategy: IR-first.** The generic Rule IR path
   (Phase 17C/17D) is the default execution vehicle for faction, detachment,
   enhancement, and Stratagem semantics. Named handlers become the audited
   exception, reserved for rules the IR provably cannot express. Do not
    write new hand-authored 17G detachment slices beyond in-flight work;
    follow the completed WS14 IR-first runbook instead. Rationale: content
    updates arrive monthly
   (codexes, dataslates, points); under the named-handler pattern each
   update is a coding project, under IR-first it is a data-pipeline run
   whose coverage report isolates the residue needing handlers.
6. **AGENTS.md amendments.** The "AGENTS.md amendment" subsections embedded
   in WS1, WS2, WS3, WS4, WS6, WS9, WS11, WS12, and WS13 below are approved.
   Sequencing rule: each amendment lands in the same PR as (or a PR after)
   the workstream change that makes the codebase compliant with it — never
   before, so the repository is never in a state where its own governance
   file fails its own gates.
7. **WS12 data-artifact migration: approved.** Generated content moves from
   Python modules to versioned JSON artifacts plus typed fail-fast loaders,
   with deliberate package-hash migration as specified in WS12.
8. **Nested weapon-ability decision model: keep and document.** The nested
   pattern is sanctioned; do not promote it to a top-level decision type.
   WS6 step 4 documents it in `docs/ADAPTER_DECISION_CONTRACT.md` and the
   WS6 code-quality allowlist carries exactly this one entry. Replay
   contract stays unchanged.
9. **Secret pending decisions in server responses: placeholder.** Non-actor
   server status responses represent hidden pending decisions with the same
   `hidden_decision` placeholder the projections use (WS1 step 3), so
   clients can poll without leaking.
10. **InterfaceIntent: deferred.** Do not implement the adapter surface now.
    Mark the `docs/ADAPTER_DECISION_CONTRACT.md` section explicitly
    deferred with Phase 18D as the owning phase (WS5).

All decision gates from the original plan are now resolved; nothing at the
bottom of this document requires further owner input.

## Archive closeout

- WS1-WS15 are complete and merged to `main`.
- The final workstream, WS15, merged on 2026-07-06 in PR #277.
- Follow-up work for Phase 19 or routine faction-content maintenance should be
  tracked in new planning documents or issues instead of appending to this
  archived plan.

---

## Track A — Correctness and invariant violations (do first)

### WS1: Viewer-scoped server status and centralized redaction

Violated invariant: hidden pending decisions must remain viewer-scoped and
must not leak through payloads, metadata, or counts.

Findings:

- `src/warhammer40k_core/adapters/server.py`, `_status_summary` (~lines
  481–501) returns `pending_request_id`, `decision_type`, and `actor_id` for
  the pending decision in every mutation response, regardless of the caller.
  `select_secondary_missions` requests are emitted with `"secret": True`
  (`engine/setup_flow.py` ~852), so any client learns the opponent is on a
  secret step and which step it is.
- `tests/unit/test_phase18e_server_api.py` (~193–201) asserts the leaked
  fields as expected behavior. Fix the test with the code.
- The hidden-decision-type set is duplicated:
  `adapters/projection.py` `_redacted_decision_type` (~1061) and
  `adapters/event_stream.py` `_redact_decision_type_for_hidden_viewer`
  (~296).

Steps:

1. Create one shared redaction module (suggested:
   `adapters/redaction.py`). Prefer deriving "hidden from this viewer" from
   the request's own secrecy metadata (the `secret` payload flag and
   actor scoping) over hardcoded decision-type sets. If a hardcoded set must
   remain for legacy types, it must exist in exactly one place.
2. Route `projection.py` and `event_stream.py` through the shared module.
3. Make server responses viewer-scoped: `_status_summary` must take the
   requesting viewer identity and redact `pending_request_id`,
   `decision_type`, and `actor_id` when the pending decision is hidden from
   that viewer. Resolved (pre-approved decision 9): non-actors see the same
   `"hidden_decision"` placeholder the projections use, keeping server and
   projection behavior consistent.
4. Update `docs/ADAPTER_DECISION_CONTRACT.md` in the same PR.

Tests:

- Regression: non-actor mutation/status responses expose no secret pending
  metadata; actor responses unchanged.
- Bug-class audit: a code-quality test asserting projection, event stream,
  and server all use the shared redaction module (no local hidden-type sets).
- Round-trip: replay and DecisionRecord output unchanged.

AGENTS.md amendment (land with this workstream): append to the
"Adapter decision contract policy" section:

> Hidden-information redaction logic must live in exactly one shared
> adapters module; projection, event-stream, and server code must consume
> it rather than defining local hidden-type sets. HTTP responses, status
> summaries, error payloads, and all other transport-level metadata are
> adapter-visible payloads and must be viewer-scoped exactly like
> projections and event deltas.

### WS2: Eliminate the `PlacementError` silent-fallback bug class

Violated invariant: no catching an error and returning a default value to
keep going; engine core is fail-fast.

Findings — `except PlacementError:` followed by `return ()` / `return False`
in at least:

- `engine/battle_shock.py` `_current_battlefield_model_ids` (~860)
- `engine/phases/movement.py` (~9333)
- `engine/phases/shooting.py` (~6893)
- `engine/fight_resolution.py` `_unit_is_placed` (~3140)
- `engine/attack_sequence.py` objective-range check (~7760)

Steps:

1. Audit each call site. "Not placed" is a legal state for units in
   Strategic Reserves, embarked cargo, and destroyed units — for those,
   exception-driven control flow must be replaced with an explicit presence
   query, not a raise.
2. Add explicit APIs on `BattlefieldRuntimeState` (or extend existing ones):
   an `is_unit_placed(unit_instance_id) -> bool` style predicate and a
   `unit_placement_or_none(...)` accessor with documented legal-absence
   semantics, alongside the existing raising accessor.
3. Convert every call site: if absence is legal in that rules context, use
   the explicit query and handle the absent case with intent-revealing code;
   if absence would indicate corrupted state (unit believed on the
   battlefield), let the typed error propagate.
4. Search the whole engine for further instances of the same pattern with
   other domain error types (`except <DomainError>: return <default>`), and
   fix them under the same policy.

Tests:

- Regression tests for at least one legal-absence path (reserves/embarked)
  and one corrupted-state path (must raise).
- Static audit: code-quality test forbidding `except PlacementError` (and a
  configurable list of domain errors) whose handler body is only a default
  `return` in `src/warhammer40k_core/engine`.

AGENTS.md amendment (land with this workstream): add to the forbidden list
in the "Exception and fallback policy" section:

> - catching a typed domain error and returning an empty, `False`, or
>   `None` default to keep going. Where absence is a legal domain state
>   (Strategic Reserves, embarked cargo, destroyed units), use an explicit
>   presence-query API on the owning state object; exceptions are not
>   control flow.

### WS3: Close the layering-enforcement gaps

Findings:

- `profiling/movement_pathing.py` imports
  `engine.movement_legality.MovementLegalityContext`; no import-linter
  contract mentions `profiling` at all.
- `rules/rule_parser.py` (~49–51, ~478–480) imports a specific edition's
  generated lexicon module from `rules/source_packages`, hard-wiring the
  generic parser to one edition.

Steps:

1. Add import-linter contracts in `pyproject.toml`:
   - `profiling` may import `core`, `geometry`, `rules`, `engine`;
     `core`/`geometry`/`rules`/`engine`/`adapters` must not import
     `profiling`.
   - `rules` must not import `engine` or `adapters` (make the existing
     prose rule enforceable).
   - `interfaces` may import `adapters`/`engine` only.
2. Invert the `rule_parser` lexicon dependency: the parser takes the keyword
   lexicon as an input (injected by the build/compile entrypoints that
   already know the edition), instead of importing
   `datasheet_keyword_lexicon_2026_06_14` directly. Keep output identical;
   compare compiled IR hashes before/after.

AGENTS.md amendment (land with this workstream): extend the dependency
direction list in the "Architecture boundaries" section:

> - `profiling` and `interfaces` may import `engine`; no package under
>   `src/warhammer40k_core` may import `profiling` or `interfaces`
> - `rules` must not import `engine` or `adapters`
> - every package under `src/warhammer40k_core` must be covered by an
>   import-linter contract; adding a package without a contract fails the
>   quality gate

### WS4: Remove runtime string parsing reintroduced past the boundary

Violated invariant: runtime engine code consumes structured descriptors, not
ad hoc string parsing.

Findings:

- `engine/catalog_rule_consumption.py`: pipe-delimited `roll_types` strings
  split at runtime (~4087); free-text weapon-scope normalization
  `_generic_weapon_scope_from_token` (~5301).
- Implemented faction handlers match on ability display names and keyword
  strings, e.g. `faction_content/warhammer_40000_11th/orks/army_rule.py`
  `_unit_has_waaagh` (~513) normalizes and compares the literal ability name
  `"Waaagh!"`; `space_marines/army_rule.py` uses a chapter-name frozenset
  (~35). Similar patterns in `astra_militarum`, `world_eaters`,
  `imperial_knights/bondsman.py`, `adeptus_custodes`.

Steps:

1. For catalog parameters: move the split/normalize step into catalog
   compile time (Phase 17B/17D tooling) so runtime receives typed lists and
   enum tokens. Add schema validation that rejects the raw string forms at
   bundle load.
2. For faction handlers: match on stable source rule IDs / descriptor IDs
   already carried by the catalog (`phase17f:` / `phase17g:` source IDs,
   datasheet ability descriptor IDs) instead of display-name normalization.
   Keyword gates should use canonical keyword tokens from the catalog, not
   locally normalized strings.
3. Static audit: extend the existing code-quality tests to flag
   `.split("|")` on descriptor parameter values and name-normalization
   helpers (`_normalise_rule_token`-style comparisons against string
   literals) inside `engine/` runtime modules.

AGENTS.md amendment (land with this workstream): append to the
"Non-negotiable invariants" section, directly after the existing
structured-descriptor invariant:

> - Runtime code must not gate behavior on rule or ability display names,
>   normalized rule-text tokens, or locally re-normalized keyword strings.
>   Behavior gates use stable source rule IDs, descriptor IDs, or canonical
>   keyword tokens carried by the catalog.

### WS5: Adapter-boundary hygiene (small, independent)

- `adapters/decisions.py` (~69) reads
  `lifecycle.decision_controller.queue.pending_requests`. Add a public
  lifecycle-level pending-request accessor and use it; keep the static audit
  that forbids thin producers from doing the same.
- `interfaces/cli.py` renders raw `DecisionRequest`s. Route CLI prompts
  through the viewer-scoped projection
  (`session.view(viewer_player_id=...)`) per
  `docs/ADAPTER_DECISION_CONTRACT.md` (~1986).
- `scripts/export_ui_contract_fixtures.py` reads `session.lifecycle.state`
  directly (~594). Move the needed data behind projection APIs or explicitly
  exempt the script in the audit with a comment naming why.
- `docs/ADAPTER_DECISION_CONTRACT.md` documents `InterfaceIntent` adapter
  capture that has no adapter implementation. Resolved (pre-approved
  decision 10): mark the section explicitly deferred with Phase 18D as the
  owning phase; do not implement the adapter surface now.

---

## Track B — Structural refactors (behavior-preserving)

### WS6: Decision-handler registry for `GameLifecycle.submit_decision`

Findings: `engine/lifecycle.py` `submit_decision` is ~1,380 lines (651–2034)
of per-type pre-validation followed by a second dispatch ladder over ~55–60
string `*_DECISION_TYPE` constants, ending in a catch-all raise.
`WEAPON_ABILITY_SELECTION_DECISION_TYPE` (`engine/weapon_abilities.py`) is a
top-level constant that is never dispatched — selections are nested inside
shooting-declaration payloads (`engine/phases/shooting.py` ~3027).

Steps:

1. Introduce a typed registry: `decision_type -> (pre_validator, applier)`,
   registered explicitly at lifecycle construction (no import side effects).
   Registration must be deterministic and complete; an unregistered type
   raises the same `GameLifecycleError` text as today.
2. Migrate branch-by-branch in small PRs (suggested grouping: movement,
   shooting, charge/fight, setup/deployment, stratagems/mission, faction
   grants). After each PR the full suite and replay goldens must pass with
   identical output.
3. Add a code-quality test: every `*_DECISION_TYPE` constant defined in
   `engine/` is either registered in the dispatch registry or explicitly
   listed in a documented nested-decision allowlist (which should contain
   exactly the weapon-ability selection case, with a comment referencing the
   contract doc). This makes the orphan-type class impossible to reintroduce
   silently.
4. Update `docs/ADAPTER_DECISION_CONTRACT.md` to document the nested
   weapon-ability decision model explicitly. Resolved (pre-approved
   decision 8): the nested pattern is sanctioned and stays; do not promote
   it to a top-level decision type.

AGENTS.md amendment (land after the final WS6 migration PR): append to the
"Decision/replay policy" section:

> Every `*_DECISION_TYPE` constant defined in `engine/` must be registered
> in the engine decision dispatch registry or appear in the documented
> nested-decision allowlist in `docs/ADAPTER_DECISION_CONTRACT.md`. Orphan
> decision types fail the quality gate. New decision types register their
> validator and applier in the same PR that defines the constant.

### WS7: Unified lifecycle-hook registry

Findings: 22 `engine/*_hooks.py` modules plus grant registries and the
`RuntimeContentContribution` bag in `engine/faction_content/bundle.py`
(~30 binding tuple fields, 1,951 lines) form ~35 parallel extension
surfaces, each with copy-pasted binding/registry boilerplate and its own
handler signature.

Steps (staged; do not attempt in one PR):

1. Introduce shared generic machinery: one `HookBinding[EventT, HandlerT]`
   shape (`hook_id`, `source_id`, handler) and one generic registry with
   deterministic ordering, duplicate-id rejection, and payload
   serialization, parameterized by a typed lifecycle-event enum.
2. Migrate hook modules onto the shared machinery one at a time, preserving
   the existing per-hook handler Protocols (signatures stay typed and
   distinct; only the registry/binding boilerplate is unified).
3. Collapse `RuntimeContentContribution` to a single
   `tuple[AnyHookBinding, ...]` plus catalog records, keyed by the event
   enum, with a compatibility constructor during migration so faction
   modules can migrate incrementally. Regenerate scaffolds with
   `tools/generate_faction_content_scaffold.py` once the new shape lands.
4. Acceptance: adding a hypothetical new timing window requires touching the
   event enum and the emitting engine site only — no new registry class, no
   new bundle field.

### WS8: GameState mutation discipline

Findings: `engine/game_state.py` is 6,955 lines with ~50 mutable fields and
~40 `record_*` methods, but phase modules also assign fields directly
(`state.shooting_phase_state = ...` 12+ sites, `state.movement_phase_state =
...` 15+ sites) and `engine/enhancement_effects.py` (~441) mutates
`state.army_definitions` directly.

Steps:

1. Add narrow mutator methods for the phase-state fields (e.g.
   `replace_shooting_phase_state(...)`) that can enforce invariants and
   event-logging expectations in one place.
2. Convert all external assignments to the mutator methods; fix
   `enhancement_effects.py`.
3. Static audit: code-quality test forbidding attribute assignment on
   `GameState` instances outside `game_state.py` (AST-based: any
   `<name>.<field> = ...` where the annotation/type resolves to `GameState`
   in `engine/` modules other than `game_state.py`).

### WS9: God-module decomposition

Targets, largest first, split along existing seams; every split is
behavior-preserving with replay goldens as the guard:

- `engine/attack_sequence.py` (9,926 lines / ~304 defs): extract
  (a) hit/wound/save resolution, (b) allocation-group bridging into
  `damage_allocation.py`, (c) destroyed-transport emergency-disembark
  orchestration into `transports.py`, (d) psychic/weapon-ability modifier
  application.
- `engine/phases/movement.py` (9,721): extract proposal parsing/validation,
  transport embark/disembark flows, reserve/reinforcement arrival, and
  desperate-escape resolution into sibling modules.
- `engine/phases/shooting.py` (6,779): extract declaration
  parsing/validation (the ~4,500-line proposal surface) from phase
  orchestration.
- `engine/stratagems.py` (6,590): extract Fire Overwatch and tactical
  secondary handling; keep eligibility/CP ledger core.
- `engine/game_state.py` (6,955): after WS8, move serialization payload
  types into a sibling module.
- `core/missions.py` (3,362): move the polygon triangulation / convex
  clipping / overlap-area code (~3326–3469) into `geometry/` and have
  missions consume it; `core` should not contain a second computational-
  geometry implementation (the first lives in `core/terrain_areas.py`
  ~423–686 — unify them in `geometry/`).

Rule of thumb: no extracted module exceeds ~1,500 lines; extraction PRs move
code without editing logic.

AGENTS.md amendment (land after the WS9 splits, together with the enforcing
code-quality test): add a new "Module size policy" subsection under
"Architecture boundaries":

> New modules must stay under 1,500 lines (generated faction-content
> modules keep their existing 2,000-line cap). Files above the budget are
> frozen to their current responsibilities: extract before extending. The
> budget is enforced by a code-quality test with a legacy allowlist that
> may only shrink; adding a file to the allowlist is forbidden.

### WS10: Determinism and duplication hardening (small, independent)

- `engine/rule_execution.py`: `binding_for_clause` / `binding_for_effect`
  (~535–560) iterate dict values in insertion order and `to_payload()`
  (~572) serializes in dict order. Sort by `binding_id` in both lookup
  tie-breaking and serialization. Add a regression test that shuffles
  registration order and asserts identical resolution and payload bytes.
- `MAX_LIFECYCLE_TRANSITIONS = 128` in `engine/lifecycle.py`: add a
  regression test exercising a reaction-heavy turn near the limit, and make
  the guard value part of `GameConfig` provenance so replay records capture
  it. Raising the value is fine; silent unbounded loops are not.
- Engagement/coherency constants: `geometry/movement_envelope.py`
  (~445–449), `geometry/pathing.py` (~385–386), `geometry/volume.py`
  (~103–104) hardcode 2.0"/5.0" defaults that duplicate
  `core/ruleset_descriptor.py` canonical values, and
  `profiling/movement_pathing.py` (~990) builds envelopes without passing
  descriptor values. Remove the numeric defaults (make the parameters
  required) so every caller passes descriptor-sourced values; fix the
  profiling harness.
- `_validate_identifier` is copied ~40+ times across core, geometry, rules,
  engine, profiling, and faction content. Create one shared utility in
  `core` and migrate mechanically. Add an audit forbidding new local
  redefinitions.
- `core/attached_unit.py` (~71–75) and `core/unit_group.py` (~96–100)
  duplicate model-aggregation methods; share one implementation.
- Weapon-profile suffix regex duplicated in `rules/catalog_generation.py`
  (~84) and `rules/wahapedia_bridge.py` (~126); share it.
- `engine/movement_legality.py` (~777–783) uses
  `getattr(value, "value", None)` to tolerate enum-like objects; require the
  typed token at the boundary instead.

---

## Track C — Content pipeline and scale

### WS11: Honest faction-content status and cheaper CI

Findings: ~790 of 826 agent-owned semantic files under
`engine/faction_content` are placeholders, but the manifest reports
`RuntimeContentSupportStatus.SUPPORTED` (meaning "importable", per
`faction_content/manifest.py` ~24–31). Five factions (Blood Angels, Dark
Angels, Deathwatch, Imperial Agents, Space Wolves) have placeholder army
rules. `tests/code_quality/test_faction_content_runtime_structure.py`
imports the entire ~800-module scaffold tree every CI run.

Steps:

1. Split the status vocabulary: keep load-support status, add a distinct
   `semantic_status` (e.g. `placeholder` / `partial` / `implemented`)
   derived mechanically from the scaffold-placeholder marker by the
   generator. Expose it in the manifest and the Phase 17F/17I coverage
   reports so "supported" can never be read as "plays correctly".
2. Emit a coverage artifact (JSON) counting implemented vs placeholder per
   faction/detachment; wire it into the Phase 17I audit outputs.
3. CI cost: keep the full-tree import test but mark it `slow`, and add a
   fast structural check that validates the generated manifest against the
   file tree without importing every module.
4. Extract the copy-pasted per-faction helpers (`_payload_object`, army
   lookup helpers, keyword canonicalization) into a shared
   `faction_content/common` module and migrate implemented handlers.
   (Ability-name matching removal is WS4.)

AGENTS.md amendment (land with this workstream): append to the
"Non-negotiable invariants" section:

> Load-support status and semantic-execution status are distinct recorded
> fields for all runtime content. No manifest, coverage report, or
> documentation may present a placeholder or load-only module as
> implemented gameplay support.

### WS12: Generated data as data artifacts (approved — pre-approved decision 7)

Findings: `rules/source_packages` is ~114k lines of generated Python
(`mfm_2026_06/*.py` at 3k–6.8k lines each,
`event_companion_base_size_rows.py` at 8,671 lines);
`engine/faction_content` adds ~52k lines that are ~96% generated
boilerplate. These inflate ruff/mypy/pyright/pytest-collection time and repo
churn while providing no type-level benefit (they are constant payloads).

Steps:

1. Change the generators (`tools/import_mfm_points.py`, base-size row
   import, scaffold generator where applicable) to emit versioned JSON
   artifacts plus a small typed loader per package. Loaders validate
   eagerly and fail fast (jsonschema is already a dev dependency; runtime
   validation should be msgspec/typed constructors consistent with existing
   payload validation style).
2. Package hashing/provenance must be preserved: hash the JSON artifacts
   exactly as module payloads are hashed today; catalog package IDs and
   hashes must not silently change — record a deliberate hash-migration note
   if they do.
3. Keep the static audit that engine runtime cannot import raw
   mirror/patch/parser tooling; extend it to forbid engine runtime reading
   the JSON files directly (only via the loaders in `rules/`).

AGENTS.md amendment (land with the migration): append to the rule-text /
data-boundary invariants:

> Generated content is committed as versioned data artifacts (JSON) plus
> typed fail-fast loaders, not as Python modules. Generators emit data;
> loaders validate eagerly and preserve package hashes and provenance.

### WS13: Test-suite health

Findings: 157 files / ~154k lines; 74% unit by file count with mega-files
(`test_phase13b_shooting_declarations.py` 17,294 lines); only 6 integration
and 2 replay tests; most tests call `GameLifecycle.submit_decision` directly
instead of the `LocalGameSession` facade; 4 files replace
`lifecycle.decision_controller` outright (e.g.
`test_phase10s_triggered_movement.py` ~605); 30+ files import `_`-private
symbols across test modules; the `stubbed` marker is defined but never used.

Steps:

1. Add facade-driven integration coverage: at least one full-game
   integration test per phase family driven exclusively through
   `LocalGameSession` (`submit_option` / `submit_parameterized_payload`),
   asserting on projections and event deltas rather than engine internals.
2. Forbid `lifecycle.decision_controller = ...` assignment in tests via a
   code-quality audit; rewrite the 4 offending files to emit requests
   through real phase/host paths or canonical fixtures.
3. Extract the shared battle-state fixture builders that Phase 17G tests
   copy per faction into `tests/` shared helpers; stop importing private
   helpers from other test modules (move them into the shared helpers with
   public names).
4. Split the mega test files along their class/section seams; mark the
   expensive end-to-end sections `slow` so local iteration stays fast
   (CI still runs everything).
5. Either apply the `stubbed` marker where the policy requires it or delete
   the marker and the policy text; a defined-but-unused policy is worse than
   none. Replace the substring-based `SimpleNamespace(`/`Mock(` grep in
   `test_stub_policies.py` with an AST check.

AGENTS.md amendment (land with this workstream, after steps 1–3 make the
suite compliant): append to the "Test policy" section:

> Tests must not construct, replace, or reach into `DecisionController`,
> decision queues, or other lifecycle internals directly; requests are
> emitted through real phase/host paths or canonical fixtures. Tests must
> not import underscore-private symbols from other test modules; shared
> setup lives in named shared helpers. Each phase family must have at least
> one full-game test driven exclusively through `AdapterGameSession`.

### WS14: IR-first faction execution pivot (complete; resolves the 17G scaling gate)

Owner decision: **approved — IR-first** (pre-approved decision 5). Context:
per `FACTION_INTEGRATION.md`, 2,061 of 2,140 Phase 17F execution rows are
`blocked_structured_semantics_required` while only ~51 have named handlers,
and single hand-written detachment slices already cost 1,000+ lines (e.g.
`aeldari/detachments/corsair_coterie/stratagems.py` at 1,333 lines). Named
handlers do not scale to 29 factions x ~294 detachments under a monthly
content-update cadence; the generic Rule IR executor must carry the default
load.

Status: **complete for WS14 acceptance.** The IR-first path now has completed
previously blocked detachment demonstrations through generated/static RuleIR
payloads, lifecycle-scoped runtime bundles, public lifecycle decision
entrypoints, runtime source-boundary guardrails, and generated support
reporting. More Dakka! proved the first full generic detachment slice; Spectacle
of Slaughter adds a page-scoped detachment rule, two enhancements, and three
Stratagems from the Emperor's Children PDF page 4. Future template widening is
continuing faction-content maintenance, not an open WS14 acceptance blocker.

Steps:

1. **Measure the gap first.** Build a classification report over the 2,061
   blocked rows: for each row, which existing IR language templates
   (Phase 17C: keyword gates, timing windows, distance predicates, dice-roll
   modifiers, rerolls, characteristic/movement modifiers, CP/VP changes,
   ability/weapon-ability grants, placement clauses, Auras, destruction
   triggers, once-per-scope) would express it, and which rows need templates
   that do not exist yet. Group missing capability by template family and
   frequency. This report drives all later prioritization and becomes a
   Phase 17I artifact.
2. **Widen templates by frequency.** Implement the highest-frequency missing
   template families in the Phase 17C parser/compiler and the corresponding
   `RuleExecutionRegistry` executors (Phase 17D), one family per PR, each
   with compile-time golden IR fixtures and runtime execution tests through
   the standard decision path. Every family implemented should flip a
   measurable batch of blocked rows to generic-supported in the Phase 17F
   execution package.
3. **Named-handler budget.** A row may get a named handler only when the
   classification report marks it inexpressible in IR and the row carries an
   approved reason. Track the named-handler count as a ratcheting budget in
   the Phase 17I audit: the count may grow only with an explicit
   justification entry, and rows migrated from handler to IR must delete the
   handler.
4. **Migrate existing handlers opportunistically.** When a new template
   family lands, migrate any of the ~51 existing named-handler rows it can
   express (delete the handler, keep the tests, assert identical decision
   and event output). Do not do a big-bang rewrite of working slices.
5. **Update the scaffold generator.** New detachment scaffolds should stop
   presuming hand-written `rule.py`/`enhancements.py`/`stratagems.py`
   semantics as the default; the generated manifest should bind
   IR-compiled rows automatically and only leave agent-owned files where the
   classification report demands a named handler. Coordinate with WS11's
   `semantic_status` so IR-covered rows report their status mechanically.
6. **Content-drop runbook.** Document the steady-state update loop in
   `FACTION_INTEGRATION.md`: ingest new PDF -> patch package -> recompile IR
   -> diff the coverage/execution report -> implement only the flagged
   residue -> run the WS15 policy-evaluation gate. The measure of success
   for this workstream is that a typical monthly dataslate requires zero new
   Python and a typical codex requires only a handful of named handlers.

Acceptance:

- Complete: the Phase 17F execution package showed strictly increasing
  generic-supported row counts across the WS14 template-family PRs.
- Complete: runtime guardrails keep source text and RuleIR compilation out of
  the engine execution path, and named-handler additions remain budgeted.
- Complete: previously blocked detachment slices now bring detachment
  rules/enhancements/Stratagems to executable status through static RuleIR
  payloads and play them through the lifecycle-scoped runtime bundle in
  integration tests, including public `GameLifecycle.submit_decision(...)`
  Stratagem submissions.

### WS15: Phase 19 preparation — policy versioning and unit representation

Purpose: bind the future AI layer (Phases 19B-19E) to contracts that survive
monthly content churn, before any training corpus or policy artifact exists.
These are requirements to encode now in `ARCHITECTURE_V2.md` Phase 19
sections, the Phase 19E training-data schema, and supporting engine/adapters
plumbing where cheap.

Requirements:

1. **Policy-artifact provenance.** Every trained policy artifact (General,
   Commander, Ranker, evaluation function) must record the exact catalog
   package IDs and hashes, ruleset descriptor identity, engine version, and
   reward-profile version it was trained against. Loading a policy against a
   game whose catalog/ruleset hashes differ from the artifact's provenance
   is a typed, fail-fast mismatch (`PolicyProvenanceError`-style), never a
   silent quality degradation. An explicit override flag may permit
   cross-version play for evaluation runs, and that override must be
   recorded in the self-play summary and DecisionRecord corpus metadata.
2. **Characteristics-based unit representation.** Policy input features must
   be derived from catalog descriptors — statlines, keywords, weapon
   profiles, points, ability IR components — not from one-hot unit,
   datasheet, or faction identity encodings. Identity IDs may appear only as
   provenance/debug metadata, never as learned-model input features. This
   makes points rebalances a feature-value change and lets policies
   generalize to unseen datasheets. Encode this as a Phase 19E schema
   invariant with a validation check on exported training rows.
3. **Search-plus-learned-evaluation as the default ranker shape.** Phase 19C
   rankers should default to bounded, deterministic, budgeted lookahead
   using the headless engine for candidate outcome simulation, with the
   learned component scoring resulting states rather than memorizing
   action-to-value mappings. Rules and points changes then propagate through
   the engine immediately; only the state-evaluation function needs
   retraining. Pure learned policies remain allowed as an optimization, but
   the evaluation gate (item 4) decides when they are trustworthy after a
   content drop.
4. **Content-drop evaluation gate.** The Phase 19E evaluation harness is the
   regression gate for content updates: after each ingest (dataslate, codex,
   MFM), run fixed-seed, fixed-matchup policy-vs-policy batches and diff win
   rates, VP distributions, and illegal-candidate/mask statistics against
   the pre-update baseline. A stale-policy drift beyond a configured
    threshold blocks promotion of the old artifacts to the new catalog hash
    (they must be fine-tuned or retrained). Wire this into the IR-first
    content-drop runbook.
5. **Corpus metadata.** Self-play DecisionRecord corpora must tag every game
   with catalog package hashes, layout/mission identity, policy artifact
   IDs, and reward-profile version so training pipelines can filter or
   reweight across content versions instead of silently mixing metas.

Deliverables:

- Amendments to the Phase 19B/19C/19D/19E invariant lists in
  `ARCHITECTURE_V2.md` capturing items 1-5.
- A `PolicyProvenance` payload type and validation stub in the engine or a
  new `ai/` module boundary (typed, JSON-safe, replay-consistent), with
  round-trip tests, so the contract exists before Phase 19 implementation
  starts.
- Training-row schema draft for Phase 19E with the
  characteristics-not-identity validation rule expressed as a schema check.

---

## Archived decision gates

All gates were resolved before archive; see pre-approved decisions 5–10. There
is nothing in this archived plan that requires stopping to ask the project owner,
except the
standing AGENTS.md stop-and-ask triggers for situations this plan does not
already cover (e.g. a refactor that would change replay output, or a new
invariant conflict discovered during implementation).

## Completed PR sequence

The original sequence is retained as the historical completion map.

1. WS1 (redaction/server) — 1–2 PRs.
2. WS2 (PlacementError class) — 1–2 PRs.
3. WS3 + WS5 + WS10 items — several small independent PRs; parallelizable.
4. WS4 (runtime string parsing) — 2 PRs (catalog compile-time move; faction
   handler ID matching).
5. WS14 step 1 (blocked-row classification report) — complete; the report
   continues to guide future template prioritization.
6. WS6 (decision registry) — 4–6 PRs, one branch group each.
7. WS8 (GameState mutators) — 2 PRs.
8. WS7 (hook unification) — staged PRs, after WS6 to avoid churn overlap.
9. WS9 (god-module splits) — one module per PR, after WS6/WS8 so the
   extraction boundaries are stable.
10. WS14 steps 2–6 (IR template widening) — complete for WS14 acceptance;
    future template-family PRs are normal faction-content maintenance.
11. WS15 (Phase 19 preparation) — completed before Phase 19 implementation.
12. WS11, WS13 — completed as independent tracks.
13. WS12 — completed after the correctness tracks so the loaders inherited the
    hardened validation patterns.
