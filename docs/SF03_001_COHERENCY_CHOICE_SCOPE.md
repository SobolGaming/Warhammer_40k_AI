# SF03-001 / D13: controlling-player coherency casualties

The retained adopted rule `rule:03:03.03:1`, block 5, has SHA256
`3565208bcdcb7d6d5a78e120c429e143822c1096221cd68927043242c77ee7aa`.
At either player's turn end, each controlling player removes models of their
choice from broken units, one at a time until coherent. These count as destroyed
without triggering destroyed-model rules. This is the retained source authority;
no new live official-source observation is claimed.

Previously the cleanup resolver selected an offending model automatically,
preferring a model whose removal immediately restored physical-unit coherency.
It did not ask the owner and did not use attached rules-unit membership.

The native turn-end flow now suspends for `select_coherency_casualty`, a finite
owner decision listing every currently placed model across that player's broken
rules units. Shared group geometry is recomputed after each accepted casualty. A request
binds the current phase, turn, descriptor, physical models, group and placements;
stale, wrong-actor, foreign-model, payload and geometry drift fail before queue
consumption. Physical ownership and the existing no-reaction destruction owner
remain authoritative.

Each accepted casualty has its own typed cleanup record and causally preceding
decision receipt. Mission physical-departure evidence is recorded immediately,
so a further pending choice can restore. The ordinary turn cleanup ID records
completion only after every group is coherent; it has no additional casualties.
The typed `completes_boundary` Boolean distinguishes it from individual casualty records for
effect expiry, base contact, restore coherency and scoring checkpoint consumers.
The earlier frozen turn-end control record remains unchanged.

The newly legal physical Leader casualty exposed a live-versus-frozen health
disagreement in secondary occupancy. After same-boundary coherency removals, the
live secondary context now reads occupancy from the existing boundary checkpoint,
matching its independent authority; current model-casualty history still includes
the destroyed Leader. This is confined to that cleanup boundary. The restore
coherency assertion also uses the complete rules unit, so a living Leader can
legitimately bridge physical Bodyguard members without weakening distances.
The original physical-unit setup assertion is unchanged. A separate grouped
assertion applies at lifecycle restore. Two canonical test fixture builders now
place attached members in an actually coherent formation before checkpointing;
their existing behavioral assertions are retained.

This is Core turn-boundary orchestration and finite decision dispatch. It adds
no named RuleIR/content handler, faction provider, speculative hook or registry
exception; existing handler budgets are unchanged.

Persistence retains the existing typed cleanup/decision/event containers and
strict runtime identity. Cleanup payloads require the explicit completion marker;
the loader never infers it from an ID or fills a missing historical field.
Old artifacts require their producing runtime; no
compatibility migration is supplied. Test kernels use fresh native units and
reusable selected definitions. Clause-level fixture admissions and constructed
formation contracts are qualified in the delivery report.

Completion timing remains the independently reviewed prerequisite. Qualified
Command-end sequencing, Stealth, Epic Challenge and Deadly Demise are deferred.
This repair does not certify the full rules engine or authorize publication.
