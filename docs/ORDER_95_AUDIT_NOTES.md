# Order 95 audit: evidence, repairs and limits

This is the owner-approved **negative audit** of runtime
`bb2bbf7e` (Order 94, PR #516). After a reproducible Shooting gap was found,
the owner chose: “Finish the full audit, record all gaps, and schedule repair
orders before PFINAL.” This PR completes that survey and records the repair
backlog; it changes no runtime gameplay, source package, decision contract or
engine identity. It does not close CAUDIT-01 or claim full Core compliance.

The [generated report](ORDER_95_AUDIT_REPORT.md) and
[immutable inventory](../data/source_audits/order95/audit.json) cover all 25
categories, all 59 FAQs, all 12 observed changelog versions, 85 changes and six
provider notes. Two gameplay repairs occupy Orders 95–96; PFINAL becomes Order
98, after the Order 97 clause-evidence prerequisite. Historical Order 84 findings
stay historical, with separate current reviews
of the eleven merged repairs. Orders 87 and 92 retain their expressly provisional
owner conventions for mixed random Movement and random melee commitment timing.

## What the source inventory establishes

The September 28 GDM Core asset exactly reproduces the September 24 asset and
its 345 rule/update/FAQ rows and 1,424 blocks. Immutable row fingerprints resolve
to the complete block lists in the retained Order 84 artifact. Each current row
has a selected observation, category owner/regression references and an explicit
open certification disposition. Both 09.07.01 headings, untitled 24.37.01, the
Universal Updates section, tables, supplemental Stratagem text and callouts
remain represented. No title or section-number deduplication discards evidence.

The complete 40k.app 15.11 observation retained by Order 94 replaces the known
truncated GDM Heroic Intervention body for source selection. The old GDM blocks
remain preserved as historical evidence. Neither observation has an App-data
version; selecting v946 on a changelog does not version the live Core body.
No official-App whole-corpus capture or co-versioned mirror comparison is claimed.

The older changelog is independently captured from public server-rendered JSON
literals. The extractor executes no downloaded JavaScript. Every change and
provider note has an ordinal, exact fingerprint and disposition. All operative
Core updates link to selected current rule/FAQ rows, including the older Heavy
vertical-distance FAQ, control-first clause and once-per-phase Normal Move.
Mission-document changes and translation-only updates remain explicit metadata
outside this Core audit's semantic claim. The duplicate v931 splitting entry
and erratum remain two observations of one obligation; the historical Ongoing
consolidation erratum is superseded by the owner's official-App v946 resolution.

All 52 current Core packages retain exact artifact/package/transcription hashes,
source IDs, runtime consumer IDs and **separate** load and execution statuses.
Those are recorded provenance and implementation declarations, not proof that a
loaded or executable row satisfies every observed clause. The selected mirror
body has not been certified text-equivalent to every package transcription.

An inventory row or rendered block is not necessarily a single operative clause.
All individual-clause certification flags therefore remain open. The remaining
CAUDIT-02 / PEVIDENCE work is an explicit Order 97 prerequisite before PFINAL: split compound requirements as needed, establish exact
source equivalence, and bind each operative requirement to assertions through
the appropriate engine owner and facade, including invalid input, replay and
viewer scope. A category regression family is only a trace anchor. This audit
must not be relabeled as a positive certificate after its repairs merge.

## Reproduced findings and shared consumer search

| Finding | Source requirement | Observed at the audited runtime | Required repair owner |
|---|---|---|---|
| C04-06 | 04.02.01 permits a model to decline ranged targets | After selecting an eligible unit and Normal Shooting with a reachable target, the only option submits a declaration. An empty declaration is schema-invalid. The same live request accepts the nonempty control. | P04E / Order 95 |
| C24-11 | 24.38 permits the player to reroll a wound roll | Each facade attack host resolves eight Twin-linked rerolls without any corresponding submitted decision, among twelve wound rolls. The helper also excludes successful wounds before requesting anything. | P24K / Order 96 |

The [probe results](../data/source_audits/order95/probe-results.json) use real
canonical catalog/domain fixtures and `LocalGameSession` submissions. No engine
objects or controllers are patched. The rejected Shooting attempt preserves all
authoritative state. Twin-linked reproduces through both Shooting and Fight;
exact persistence, both viewer projections/event streams and replay agree.
**Deterministically replaying the automatic choice does not make it legal.**
The successful-wound exclusion is a direct consumer trace, not a separately
submitted successful-reroll counterexample. Retained Shooting shares the
nonempty declaration boundary, but is not a separately replayed counterexample.

The target-selection search covered ordinary, retained and out-of-phase request
builders, proposal parsing, empty-shooting completion, target replacement,
physical weapon instances and post-selection restrictions. P04E must distinguish
weapons selected from attacks actually made so that optional target omission
does not suppress source-required Hazardous checks or One Shot consumption.
That is required repair scope, not an additional claimed reproduction. Existing
no-weapon/no-legal-target completion from Order 91 remains valid and is not
reopened wholesale.

The reroll search covered all engine calls using `record_decision=False` and
both automatic single-option reroll selectors. Command Re-roll's component
resolution follows a submitted Stratagem choice; existing movement, Charge,
Battle-shock and source-backed attack rerolls consume their submitted decisions.
Twin-linked instead builds an optional request locally, invents its selected
result and embeds it in an event. P24K must use the existing generic reroll
services and audit every shared attack host, source overlap, once-per-die rules,
overrides, declines, successful rolls and pending restore.

## CAUDIT-02: clause evidence is a separate prerequisite

Independent review identified that leaving the complete clause inventory inside
PFINAL would leave a known evidence gap without the requested prior repair order.
Order 97 / PEVIDENCE now owns that work. Its acceptance criteria require complete
clause and FAQ decomposition/classification, source equivalence and supersession
review, exact engine owners and assertion-bearing regressions, including missing
Heavy movement-to-attack and Category 07 facade proofs. The two gameplay repairs
must merge first; newly discovered gaps receive their own prerequisite repairs.
This is an evidence defect, not a claim of 345 additional gameplay defects.
PFINAL remains the subsequent fresh audit after those prerequisites merge.

The same review found the README's current status still pointed to Order 84 and
PFINAL 95. Its current status and certification reference now match the roadmap;
historical implementation notes remain historical.

## Mandatory cross-category revalidation

The inventory names exact regression nodes for Normal Move occurrence,
objective-control-first, Action movement interruption, Flight/Heavy, Category 07
phase order and owner resolutions. It preserves all 20 September 10 review
dispositions, rather than treating them as replaced by recent changelog deltas.

C12-04 remains Engaging-only under the owner-confirmed App v946 interpretation
in [Order 72](ORDER_72_SCOPE_PLAN.md). C18-07 remains passenger post-placement
engagement under [Order 62](ORDER_62_SCOPE_PLAN.md); passengers do not inherit
Transport engagements. No fresh ambiguity was found that would reopen either.

The Heavy evidence has an explicit limit: Flight choice/history is facade-tested,
while the per-model vertical-distance Heavy test directly exercises real engine
state. It is not a combined facade attack certificate. The lifecycle phase-order
checks likewise include engine-level fixtures. Category 07 has current
revalidation evidence but remains open for the final clause-specific certificate.
Aircraft departure checks objective event ordering only; Aircraft source-dash OC
does not supply a numerical scoring counterexample.

## Reproduction and validation

```sh
uv run --no-sync python -m tools.core_rules_order95_audit --check
uv run --no-sync python -m tools.core_rules_40k_app_audit --check
uv run --no-sync python -m tools.core_rules_order95_probes
# Optional: use the exact assets identified in audit.json, not a later live page.
uv run --no-sync python -m tools.core_rules_order95_audit --check \
  --verify-core-capture /path/to/core-page.js \
  --verify-changelog-capture /path/to/changelog.html
```

The source capture checks compare raw identities before extracting; changed
sources require a new observation. The offline validator independently pins the
whole audit, checks retained artifacts and reference resolution, and requires
all three repair owners in PFINAL's expanded prerequisites. New regressions reject
missing, duplicated or rewritten inventories and false certification claims.
They were written before the tool; the initial collection failed because the
module did not yet exist. No behavioral test file was added or moved, so shard
regeneration is unnecessary; the exact inventory check is still required.

Final local results are retained in the [validation record](../data/source_audits/order95/validation.json):
9,756 behavioral tests passed with 85.20% coverage, followed by
762 code-quality tests without coverage. Both final suites used 18 xdist
workers and work stealing; the behavioral command included the required Node
PATH prefix. Ruff, formatting, mypy, pyright, import boundaries, shard inventory
and all-files pre-commit passed. Engine identity, base-ref external contract,
installed-wheel smoke, five TypeScript tests and 342 HTTP conformance assertions
passed. This host has no npm executable; its package scripts were invoked directly
with bundled Node and locked existing dependencies, as recorded in the JSON.

An earlier aggregate attempt was invalidated while review changes were being
applied: one worker retained the earlier comparison module. The code-quality
scan also matched a retired-edition token inside a provider FAQ UUID. The human
report now uses observed FAQ ordinals; exact IDs remain in the JSON inventory.
Both focused failures passed after correction. The final suites were then rerun
on frozen code; no extra final behavioral run without coverage was performed.
The record preserves the failed attempt as well as the successful final gates.
Independent re-review approved the prerequisite/status fixes and the FAQ display
change with no remaining actionable findings.

Complete-game performance remains separately uncertified: no full-game samples,
unknown arithmetic mean and maximum. This audit changes no runtime algorithms,
data structures, caches or gameplay orchestration. It adds no speculative game
driver and makes no claim that the deferred performance budgets passed.
