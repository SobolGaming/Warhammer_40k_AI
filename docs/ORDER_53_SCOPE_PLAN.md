# Order 53 — Super-Heavy Walker (P24E / C24-05)

## Required invariant and source

For each Normal, Advance or Fall Back move, an eligible rules unit can transit
non-Titanic models and move horizontally through terrain sections at most four
inches high. Before moving, its owner may give every model MOBILE for that move.
Choosing this option requires one D6 after completion; a one directly makes the
unit Battle-shocked. This is not a Leadership test. Ordinary endpoint, engagement,
distance and coherency requirements continue to apply.

Reviewed official Core Rules page 85, section 24.35, and the complete 40k.app
search-index text on 2026-09-16. Direct retrieval returned 403. No successful
direct retrieval or second-provider comparison is asserted.

## Ownership and acceptance

Source-backed movement descriptors supply the transit and optional keyword grant.
Existing finite Movement and triggered-movement options commit the choice; their
proposals, retries and rerolls retain the original decision authority. Shared
rules-unit geometry applies the permissions to attached models. Move-completion
sequencing owns the mandatory post-move roll. The Battle-shock state owner applies
direct status changes, without manufacturing a failed Leadership test or triggering
rules that require such a failure. Historical authority authenticates the choice,
completion, dice and status mutation on restore.

The bug-class audit covers ordinary and triggered movement, finite path candidates,
mixed/attached models, Titanic blockers, per-section terrain heights, vertical
transit, denied endpoints, Charge/Surge exclusion, retries, restore and replay.
No new named handler, faction gate or adapter mutation path is required.

## Implementation and scope audit

The reviewed JSON artifact and eager hash-pinned loader provide source-linked
movement descriptors, explicit load status and separate executable-runtime status.
Canonical ability IDs or catalog-carried keyword tokens activate the descriptor;
display names and rule text never gate runtime behavior. The Core descriptor
consumption registry records its runtime consumers.

Ordinary actions, reactive unit choices and finite reactive paths commit the same
all-model choice. Pre-pop validation binds proposals and distance rerolls to the
original finite record, canonical owner/unit and living membership. Deleting both
a copied choice and its source identifiers is rejected. Retries preserve the
commitment. Every attached component receives the temporary movement keywords.

Shared capabilities supply non-Titanic model passage and horizontal four-inch
terrain passage. Reactive paths use the same friendly/enemy keyword blocker
queries as ordinary movement. Independent broader permissions remain effective.
Terrain traversal retains endpoint and vertical rules, evaluates the crossed
section, and reuses existing MOBILE Dense-terrain semantics. Pure pose measurements
were extracted before extending the oversized pathing module; no import exception
was added. Surge's separate move kind suppresses this Normal-mode permission.

A generic source-linked completion binding uses the existing timing batch. Its
single D6 and direct status update are authenticated against the choice, historical
membership, exact dice event and deterministic RNG reconstruction. A completed
participant cannot lose its required roll. The shared Battle-shock owner and
history reconstruction apply status without failed-Leadership-test events;
existing cleanup remains authoritative. No named handler was added.

The audit covered every ordinary/triggered choice and proposal constructor,
finite paths, retries/rerolls, attached components, friendly/enemy Titanic blockers,
alternative transit sources, completion callbacks, status history, checkpoint
restore, replay and shared viewer APIs. The production diff is confined to this
invariant and required contract/identity artifacts.

Contract 24 / persistence 16 / replay 18 explicitly version required choice,
completion and horizontal-terrain evidence. Prior compatibility baselines remain
unchanged. The [migration](../contracts/migrations/23-to-24.md) and adapter contract
record public shapes and visibility.

## Validation

Focused regressions cover Normal/Advance/Fall Back, finite and parameterized
reactive paths, accepted/declined distance rerolls, rejected-path retries, attached
membership, native descriptors with arbitrary display names, terrain boundaries,
vertical passage, endpoints, friendly/enemy Titanic exclusions, Surge/Charge/Fight
exclusion, pre-pop tampering, direct Battle-shock, exact restore/replay and both
players' public events. Matched component evidence and its limits are in
[the performance report](performance/order53/README.md). Final gate results,
coverage and representative JUnit hashes are in
[the validation record](performance/order53/validation.json).
