# Order 72 / P12B — consolidation source resolution

Status: implemented and locally validated. Finding: C12-04.
Base: `5befbb928fb938c4faa2bef8cd52ffc677e6294f` (Order 71, PR #491).
P12 and S-MIRRORS are merged; no other roadmap PR was open at discovery.

## Source resolution and supersession

On 2026-09-21 the repository owner supplied the complete **After moving**
section of 12.08 from their official Warhammer 40,000 App, data version **946**:

> Ongoing Consolidation: Each model that started this move engaged with an enemy unit must still be engaged with that enemy unit.
>
> Engaging Consolidation: Your unit must be engaged with all of the selected enemy units. If one or more enemy units engaged with your unit have not been selected to fight this phase, your opponent must select each of those units, one at a time; when each is selected, it becomes eligible to fight and is selected to fight (12.04).
>
> Objective Consolidation: Your unit must be unengaged and within range of the selected objective.

This resolves the roadmap exception: only Engaging Consolidation grants the
forced enemy Fight response. Ongoing's per-model engagement preservation and
Objective's unengaged/in-range endpoint requirements remain operative. The
supersession is limited to the v931 Ongoing forced-selection clause when running
the selected v946 rules. It does not rewrite v931 history, certify another App
version, or modify Shock Disembark.

The confirmation is an owner-supplied transcription, not an agent-observed App
capture. Device platform, build, locale, original observation time and capture
bytes were not supplied and are not invented. The resolution was recorded at
`2026-09-21T21:50:58+00:00`; its typed, hash-pinned JSON records the complete
transcription, v946 selection, source IDs, supersession scope and structured
`forced_fight_modes`. That timestamp records the repository resolution, not a
claim about when the owner opened the App.

The v946 After moving transcription SHA-256 is
`fdde240dcfcef2fb76864cb27474b5964dfca6786b45e123090e61586ae72d02`;
the resolution observation fingerprint is
`d3a6ae1b0f6b5cd992d292f3f6fa3f6db2182b3ac03971f5dd0f716b7781b71d`.
The current package bytes are pinned as
`df45dfddbb5e851346fa355063b9cd92298c0c68f2491c6b312dc594c8ee15a9`.

The selected text agrees with the retained, unversioned 40k.app rule body:

| Evidence | Identity |
| --- | --- |
| Stable source | `gw-11e-core-fight:consolidation-move` |
| Provider / URL | Non-affiliated [40k.app](https://www.40k.app/rules/12-fight-phase) |
| Original observation | `2026-09-05T18:32:47-04:00`; App version unavailable |
| Complete 12.08 transcription SHA-256 | `cfcace8bd96251a0b11c8eb24ccb20ea64a69f72d33a9a7cc8a6993c17f7ae89` |
| Mirror observation SHA-256 | `25194f1eb4ba53e9bc431353e1dc921d3dd17c40a96d8cc4b3ee91c7e17dcfa3` |
| Audit fingerprint | `8665696b9e9e4e57a4c2c6c4aa7e6dc4a9a4d2f0cfb8e1b6ac471068e6becc1e` |

The live 40k.app body and Game Datamissions v931 selector were rechecked in this
task before the owner resolved the exception. This does not establish their
co-version equivalence. The original mirror records retain their original
version/timestamp identities and observation fingerprints.

`gw-11e-core-fight:ongoing-consolidation-erratum` remains historical evidence
from non-affiliated [Game Datamissions](https://game-datamissions.com/11th/rules/changelog?v=931),
App-data 931. Its transcription hash is
`97f1acc3a1e4eda12ffcb286908efb993ce95800ba33ad0a3d526964cb8aeafd`
and mirror observation hash is
`1f548d6c73dc3b9b2dc329a478b19d3561f0c5f7c1c3cb8049f26b7da40cdeee`.
It remains loaded, with semantic status `not_certified` and no runtime consumers
in the current package. `historical-package-2026-09-05.json` preserves the entire
original package byte-for-byte (SHA-256
`daf37b84e0ca0a7fb653db6ae7b4d6aabf93b180fcb948688aae5fc9fbcf5d7d`).
Its execution metadata describes the historical P12 implementation only.
Official historical Core Rules PDF provenance remains
`f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833`.

## Invariant, ownership and scope

Only a source-authorized consolidation mode may grant or authenticate forced
enemy selection. P12 previously combined an unversioned Engaging clause and the
v931 Ongoing erratum. The new Ongoing facade assertion failed on the base engine:
two enemies received a forced queue after an accepted Ongoing move.

Reviewed source JSON and owner resolution -> typed eager source loader -> shared
mode/source query -> accepted witnessed Fight movement -> engine queue installation
-> existing opponent finite decisions -> ordinary Fight continuation -> shared
viewer redaction, authenticated restore and deterministic replay.

The same-bug-class search found the duplicated mode/source decision in the live
queue and `validate_consolidation_fight_history`. Both now consume the same
structured grant. Restore also inventories response starts, skips and completions
in reverse: Ongoing/Objective responses and orphan movement triggers are invalid.
Existing source, exact-boundary, actor, inventory, selection and continuation
authentication remains in force for Engaging.

The shared physical-presence and rules-unit owners, movement endpoint/path
validation, retained Fight On Death geometry, Normal/Overrun choices, attack
resolution and suspension/resumption algorithms are unchanged. No new handler,
hook registry, decision type, adapter path or out-of-scope content is introduced.

## Contract, regressions and generated artifacts

Both source-player directions cover Ongoing's absence of a response and Engaging's
one-at-a-time enemy selection, with exact checkpoints and historical restore.
The existing Engaging cases cover multiple enemies, already-selected exclusions,
Normal/Overrun eligibility, continuation drift, both viewers and cross-round
replay after turn-scoped effects expire. Forged Ongoing starts/skips/completions
and missing movement triggers are rejected. Source tests prove that the v931
artifact and observation hashes remain unchanged and only Engaging has a grant.

The existing finite/proposal and event envelopes cover this correction. The
adapter contract is updated for the narrowed response boundary. Old saves and
replays remain tied to their original engine build; no compatibility shim or
reinterpretation of historical Ongoing queues is added. Current-build historical
Engaging queues remain authenticated after their phase and round have ended.

The source generator emits the current versioned package and immutable historical
copy; the authority registry authorizes the new package version while retaining
the original observations. Runtime identity and external examples must be
regenerated. Behavioral tests extend existing files, so the eight-shard file
inventory is unchanged. The exact fail-closed shard check remains required.

## Scope audit and validation

The production diff is limited to the consolidation queue/history owners and
their source boundary. The historical-artifact copy, source metadata, generated
identity and contract examples account for the data changes. Independent source
and architecture audits guard the single mode authority and retired runtime ID.

Reproduce sources with `uv run python tools/build_core_fight_source.py --check`.
The active CI workflow also requires exact-base contract compatibility, package
smoke, TypeScript client/unit/conformance checks, lint/type/import checks and both
final Python suites. Results and performance qualifications are recorded in
[performance/order72](performance/order72/README.md).

Final validation passed: 8,730 behavioral tests with 85.1512% coverage and 575
code-quality tests. Lint, type, import, shard, generator, exact-base contract,
installed-wheel and direct Node client checks passed, including 342 live HTTP
conformance assertions. All declared component performance comparisons passed.
The initial report-renderer mismatch and obsolete roadmap-pause assertion were
corrected and their complete affected suites rerun; both attempts remain in the
validation record. npm is unavailable locally, so `npm ci` remains for CI; the
installed TypeScript dependencies passed their direct package-script checks.

PR URL and merge commit: recorded on publication; not merged by this task.
