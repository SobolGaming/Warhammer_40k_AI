# Explicit October 14 checkpoint reconstruction

The owner explicitly authorized recovery of this artifact on October 20, 2026.
The original file remains immutable. Ordinary persistence, server recovery and
replay loaders retain their producing-runtime requirements and do not call this
operation after a failed load.

The one supported profile is
`local-checkpoint:legacy-model-completion:2026-10-14`, bound to exact source bytes
SHA256 `55f23684cedb354050605bb796928bea5971acb73d975ffe54ce230ae2db9370`.
Its retained producer is revision `22a12094cfe3839d8fe8c5296ec0a7e7d32abade`,
runtime fingerprint `3dac52df9bba355343defa9547c58e6b1feb03f8b45e5d6d32031e611075d9bb`.
Those producer identities come from the authenticated retained audit, not an
invented build field in the old local persistence payload. The old payload uses
`local-game-session-persistence-v1`, as does the current local wrapper; that
shared token does not imply compatible attack-history requirements.

The post-exception artifact has 137 events and 18 recorded decisions. Its earlier
replay anchor is accepted by the current normal typed loader. All recorded choices
and automatic records reproduce through the ordinary facade. The engine generates
one additional `attack_sequence_model_completion_state_recorded` event. It is new
evidence from deterministic reconstruction, never labelled original evidence.

Recovery verifies the original closed envelope and every hash, exact initial
anchor, decision inventory and event prefix/tail. It replays those decisions through
the engine without injecting dice or editing live state. It then requires all 137
old events to match exactly after a recorded one-to-one ordinal event-ID mapping.
Gameplay state, choices, complete RNG state and source identity must remain exact.
Only the generated completion event and its event-ID references are added. Derived
runtime-content audits are refreshed at the two declared current/history anchors;
ordinary strict loading recomputes and authenticates them. Missing records, changed
outcomes, unexplained events/state, unknown profile/source and drifted provenance
fail closed. Supporting another source requires a separately reviewed recipe.

The new offline package is `local-checkpoint-reconstruction-v1`: a separate strict
local checkpoint plus deterministic provenance and a canonical package hash. It
records source/destination runtime identities, original input digest, every event
mapping, regenerated evidence and derived audit hashes. Its verification path
requires the original bytes, proves the mapping, uses ordinary strict restore,
and exactly replays the reconstructed representation. It is operator-only data
and is never served in player projections, HTTP responses or session recovery.
No external decision, command, server persistence or released contract family changes.

Example (with the retained project Python and no installs):

```
python scripts/reconstruct_local_checkpoint.py --source ORIGINAL.json --profile local-checkpoint:legacy-model-completion:2026-10-14 --output RECONSTRUCTED.json
python scripts/reconstruct_local_checkpoint.py --source ORIGINAL.json --profile local-checkpoint:legacy-model-completion:2026-10-14 --verify RECONSTRUCTED.json
```

The CLI requires a new output and never overwrites the original or an existing
file. `verify_checkpoint_reconstruction(original_bytes, package)` returns a fresh
normal `LocalGameSession` for legal continuation. Original-byte cross-runtime
replay still differs; exact replay is claimed only for the explicitly reconstructed
checkpoint and its subsequent ordinary continuation. The original source is retained
compressed byte-for-byte for regression; it is not a replacement catalogue/provider.

All current-runtime A32, Emergency Battle-shock, D11, S24 and faction repairs remain
unchanged. This does not generalize native provider admission, Q18-01's constructed
mission-layout limitation, historical compatibility for other saves, malicious-writer
attestation, global coverage, complete CI or full-game performance certification.
