# Explicit October 14 checkpoint reconstruction

The owner explicitly authorized recovery of this artifact on October 20, 2026,
and its finite private-RNG metadata reconstruction on November 6, 2026.
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
`local-game-session-persistence-v1`; the current local wrapper uses
`local-game-session-persistence-v2-private-rng`. Old saves remain usable with
their original runtime; normal loaders do not infer a seed or migrate them.

The post-exception artifact has 137 events and 18 recorded decisions. Its earlier
replay anchor receives the explicit metadata mapping below before the current
normal typed loader accepts it. All recorded choices
and automatic records reproduce through the ordinary facade. The engine generates
one additional `attack_sequence_model_completion_state_recorded` event. It is new
evidence from deterministic reconstruction, never labelled original evidence.

Recovery verifies the original closed envelope and every hash, exact initial
anchor, decision inventory and event prefix/tail. It replays those decisions through
the engine without injecting dice or editing live state. It then requires all 137
old events to match exactly after the recorded one-to-one ordinal event-ID mapping
and the three derived setup checkpoint hash mappings described below.
Gameplay outcomes, choices, RNG history and draw count remain exact. RNG seed
metadata changes explicitly. Eight source-identity fields remain exact; the
Chapter import hash and config hash have the finite mappings below.
Only the generated completion event and its event-ID references are added. Derived
runtime-content audits are refreshed at the two declared current/history anchors;
ordinary strict loading recomputes and authenticates them. Missing records, changed
outcomes, unexplained events/state, unknown profile/source and drifted provenance
fail closed. Supporting another source requires a separately reviewed recipe.

The required explicit Chapter `secondary_vp_cap_scope=player_turn` field changes
its derived import hash from
`009a47e19b7e619f6a9bcd75a5294497ac1becb2aee4c320ffcd0a393c57399d` to
`8f76fcf275397bd2ffabf16d3e127f059fb476e0144654bd54e550f5dd16faa1`.
For this same authenticated source/profile only, reconstruction prepares an
in-memory replay-artifact copy with that exact `mission_source_package_hash`
transition and sends the copy through the unchanged strict replay loader. The
current target and `PLAYER_TURN` scope are pinned; removing only the added field
must recover the authenticated original scoring-row hash
`b408ac7e759b3000d2c1a611624e28ba4ddb8e8f80c2a85589f89cd79927fedf`.
Both original initial/final VP ledgers are empty and remain so under exact
gameplay-state comparison. This converts no Event scoring history. The output
records the exact path, old/new values, reason and
`recorded-decision-reconstruction-v3-audit-rng` recipe revision. Unknown
pack/hash changes and older reconstruction output schemas fail closed.

The v3 recipe adds the audit seed
`6ba138bd8d5aeb37661f9d0aa6c6377ef433beefc39b43ed5f8943424e8d16a0`,
SHA256 of UTF-8 `a32-exact-artifact-reconstruction-v3:3223`, to config and state
at the root and `modifier_evaluation_history_origin` anchors. At the final
checkpoint it also maps `psychic_modifier_history_origin` and that anchor's
nested `modifier_evaluation_history_origin`. Each state receives tactical draw
sequence zero: this exact historical artifact contains no tactical draws.
No arbitrary nested object is searched or rewritten.

The replay input explicitly changes from `replay-artifact-v36-target-aware-attack-groups`
to `replay-artifact-v37-private-rng`. Its initial RNG seed and the final RNG seed
change from the recorded public game ID to the audit seed. The config hash is
recomputed solely for the added seed. All five natural engine dice faces remain
`4, 4, 2, 1, 2`; no result is injected. Full RNG history and draw count five are
compared independently of the seed. Setup events 38 and 39 contain three state
hashes: two references to the pre-battle state and one to the post-battle state.
These exact old/new hash pairs are pinned in the recipe. A passive regression
observer checks the real engine state at both checkpoints: removing only the
new seed and counter must reproduce the original hashes, while the complete
current payload must reproduce the new hashes. Every other original event field
still compares exactly under the event-ID mapping. Provenance records each
metadata transition and does
not claim the original RNG metadata was preserved.

**The reconstructed artifact is not suitable for secret competitive RNG.** Its
seed is public, reproducible audit entropy selected to preserve this finite
recorded sequence. Subsequent continuation is deterministic under that known
seed; it does not claim the old runtime's future random sequence. This is an
explicit operator reconstruction, not automatic reseeding or a general legacy
RNG compatibility epoch. Unknown sources and older reconstruction packages remain
unsupported.

The new offline package is `local-checkpoint-reconstruction-v3-audit-rng`: a separate strict
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
