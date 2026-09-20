# Order 65 / P24B: Firing Deck passenger shooting restrictions

Finding: C24-02. Base: `ca2eea9f` (Order 64, PR #484).

The violated invariant is that every unit embarked when Firing Deck resolves is
ineligible to shoot until that turn ends, independently of weapon contribution,
later disembarkation and phase-local shooting history. The previous implementation
marked only contributing units as having shot in the current Shooting phase.

## Source and ownership

The complete 24.14 text is retained from the 40k.app search-index observation on
2026-09-20. Direct page retrieval returned HTTP 403; no App-data version or
co-version agreement is claimed. This is the owner-approved maintained App-data
mirror policy, not a claim of official GW hosting. The reviewed package and audit
retain provider, URL, observation time, exact transcription hash and immutable
observation fingerprint; historical official PDF provenance remains preserved.
Regenerate with `uv run python tools/build_core_firing_deck_source.py --check`.

The authoritative path is structured Firing Deck ability and Transport cargo ->
engine declaration request snapshot -> existing parameterized proposal validation
-> accepted declaration and persistent effect -> shared shooting eligibility ->
actual turn-end expiration -> event/checkpoint validation, restore and replay.

The existing Firing Deck resolver was extracted from the frozen oversized
Transport module before extending it; its legacy line cap shrinks from 3,131
to the remaining 2,592 lines. Its result snapshots all cargo, including
noncontributors. Zero selected weapons still resolves the ability. Invalid
selections produce no restriction. The declaration request retains the full
snapshot so changes to noncontributing cargo also reject before queue pop.

The engine records one source-linked persistent effect with the cargo component
IDs. Shared rules-unit queries resolve canonical attached identity from those
components. Its lifetime belongs to the actual owning
turn. Shared eligibility covers ordinary and out-of-phase shooting and existing
Stratagem consumers. Weapon ownership remains with the Transport. The cargo
snapshot does not change when passengers leave or when the Transport disappears.

Passengers are not actual shooters. `shot_unit_ids` and the mission-boundary
shooting-history reconstruction now record only the declaring Transport. This
second instance was found by searching every `ineligible_unit_instance_ids`
consumer and exercising a complete turn with subsequent restore.

## Contract and scope audit

Contract 31 introduces the required Firing Deck request cargo snapshot and the
persistent-effect semantic boundary; replay is v25 and persistence v23. Existing
finite and parameterized submissions remain authoritative. No new decision family,
named handler, generic hook registry, faction branch or adapter mutation path is
introduced. The existing shared viewer redaction continues to own visibility.
See [migration 30 to 31](../contracts/migrations/30-to-31.md) and the adapter
contract's Order 65 section.

Production changes are limited to the Firing Deck resolver, its declaration
integration, shared eligibility, persistence validation and actual-shooter history.
Core source artifacts and generated runtime/contract identities are required
consequences. Aircraft and later roadmap orders remain separate.

## Validation

Focused regressions cover all-cargo and zero-contributor restrictions, attached
identity, invalid/stale cargo, malformed selections, phase and cargo changes,
correct turn expiry, a complete facade-driven turn, exact save/restore and
persistence replay, viewer projection equality and forged restriction rejection.
The focused shooting and Firing Deck run passed all 95 tests. The four retained
shooting regressions also pass. Required source-count and schema-version fixtures
advance with the registered source package and deliberate contract migration;
combat assertions and RNG are unchanged. The aggregate run exposed one shared
post-attack fixture missing the existing `firing_deck_value` field. The fixture
now derives that field from its real rules unit and records the required request
metadata, including the actual parent phase for out-of-phase declarations.
Deterministic scenario identities were reselected to preserve
their original dice-dependent branches after this history correction.

| Required behavior | Regression / authority |
| --- | --- |
| Every passenger, including zero contributors | `test_all_cargo_is_restricted_even_with_zero_contributors` and the existing Firing Deck declaration integration regression |
| Canonical attached-unit identity | `test_attached_cargo_restricts_canonical_unit_and_both_components` |
| Later cargo/phase changes and owning turn expiry | `test_restriction_survives_phase_and_cargo_changes_and_expires_at_turn_end` |
| Actual engine turn-end cleanup and replay | `test_engine_turn_boundary_expires_restriction_and_restores_exactly` |
| Noncontributor cargo drift rejects before queue pop | `test_noncontributor_cargo_drift_rejects_before_queue_pop_or_mutation` |
| Shared out-of-phase eligibility | `test_out_of_phase_entry_rejects_restricted_noncontributor_before_mutation` |
| Complete source/cargo/duration restore authentication | Pending-snapshot and forged-effect parametrized regressions in `test_order65_firing_deck.py` |
| Public cargo snapshot in both viewer paths | Facade pending views, event deltas and exact persistence replay in the all-cargo test |
| No passenger-as-shooter aliases or history-scanning query | Static and live profile checks in `tests/code_quality/test_order65_firing_deck.py` |

All 1,147 consumers of the corrected shared fixture pass with their original
assertions.

Two full parallel quality attempts exposed inconsistent in-process cProfile
accounting in the existing Order 64 reconstruction guard: five restorations
instead of four, despite focused serial and parallel passes. A caller diagnostic
also recorded two fork calls for one invocation. Each guard now profiles one real
reconstruction in a fresh subprocess, matching the standalone evidence context;
all authentication assertions and numeric budgets remain unchanged. The ten
focused guard tests pass with this isolation. No runtime code changed for it.

The qualified [component assessment](performance/order65/README.md) compares
base and head on the same provisional host with unchanged declared budgets.
The mandatory Order 64 restore/fork evidence is refreshed for this engine build.
Gameplay-slice and complete-game performance are not certified. Final aggregate
results are recorded in `docs/performance/order65/validation.json`.

Final local validation passed 8,484 behavioral tests at 85.12% coverage and all 549 code-quality tests. The required lint, type, shard, import, generated-contract, TypeScript conformance and installed-wheel checks passed.
