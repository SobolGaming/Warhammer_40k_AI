# Order132: inclusive disembark distance

Selected scope is P18K/C18-12, `18.04-rapid-tactical-distance`, Core row
`rule:18:18.04:1`, Game Datamissions source SHA256
`ed5ace0412d4f87e7f436e64eb56f5081325cbc6b3c0a1dda347562c890144b9`.
Literal blocks 7 and 15 give Rapid/Tactical three inches and require every
model wholly within the transport's setup distance. The complete original row,
fingerprints, acceptance and protected inputs are retained in the
[source audit](../data/source_audits/order132/source.audit.json).

Baseline is main `f054b52fe912875bfe425cf875de3756294b5c7b`, tree
`4454ef00daae431c83460ff9be6741fb0b63ed57`; all 5,632 canonical blobs match
reviewed Order131 `b44c40ed2dbcc680d4a7bda133c205849048a016`.

Previously the shared whole-distance query buffered polygon approximations and
rejected analytically exact circular boundaries. Circular pairs now use center
distance plus passenger radius against transport radius plus allowed distance.
The inclusive comparison includes eight coordinate/length ULPs for translated
trigonometric pose arithmetic, capped at 32 measured-length ULPs so large
coordinates cannot authorize a material exterior gap. Exterior offsets of 0.01 and 0.0000001 inches
remain invalid; polygon resolution cannot change this circular result.

The same query owns ordinary circular measurement, single-source circular FRAME
parts and marker setup. FRAME targets retain every-part and full-height semantics;
ordinary targets retain their support-base/closest-height semantics. Disembark's
shared endpoint, physical group, eligibility, oversized-base, battlefield,
coherency, overlap and engagement owners are preserved. Existing three-inch
Rapid/Tactical/Assault/Shock/Destroyed and six-inch Combat/Emergency modes keep
their original bands and policies. Cult Ambush consumes the shared marker query.
Noncircular geometry and cooperating source unions remain qualified by their
existing implementation and tests; this order makes no universal geometry claim.

Acceptance controls retain the original 2.99/3.01 assertions and negative probe
byte-exact. New controls exercise exact, interior and exterior boundaries,
translated/angled geometry, ordinary and FRAME contexts, both existing bands,
multiple transport models and marker contexts. Real facade Rapid play first moves
the transport through a complete witness. Both modes cover stale-input rejection,
physical atomicity on invalid setup, legal reselection/retry, pending and completed
checkpoints, JSON persistence, independent forks, both players and every viewer
role, event streams, exact replay and subsequent legal Movement continuation.

Apply [the sequential review policy](SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md).
Block on reproduced rule errors, normal legal-play failures, genuine valid-state
persistence/replay failures and required supported boundaries. Queue coordinated
hand-edited-history hardening separately absent a necessary supported boundary.
No named-provider, whole-faction, full-game, universal history-tamper or complete
performance certification is claimed. The current-runtime serial smoke and
exact-base assessment apply; original histories, budgets and live controls remain.
