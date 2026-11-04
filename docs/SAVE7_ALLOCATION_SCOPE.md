# Effective save characteristics in attack allocation

Base: `b01e038f048be87df0c91640f249c800a63104aa`. Order:
`SAVE7-ALLOCATION-20261104`. This is the separately approved consumer repair
following the bounded Daemons source correction; no new source rows or catalog
providers are admitted.

## Invariant and owner

Every admitted effective Sv/InSv profile must remain representable in shared
attack allocation. Sv and InSv are exact integers with minimum 2 and no upper
bound; `None` represents genuine absence. A numeric 7 is a real save characteristic,
including when no unmodified D6 can meet it. AP and permitted modifiers still
consume its value. Preserve 7/8 numerically in profiles, group identities,
allocation options, pending damage, events and persistence.

Before this repair, native ten-model Bloodletters (Sv7/InSv5) reached
`LocalGameSession.submit_parameterized_payload`, normal Shooting/Fight dispatch,
`attack_sequence_group_selection._resolve_grouped_current_pool`, and
`damage_allocation.allocation_groups_for_context`, then failed in
`AllocationGroup.__post_init__` with `AllocationGroup save must be between 2 and 6.`
Both native facade declarations and real UnitFactory/group construction reproduce
on the exact base. This is an ordinary consumer failure, not manually edited history.

The only production changes are a specifically named optional effective-save
validator in `engine/damage_allocation_validation.py` and its two AllocationGroup
consumers in `engine/damage_allocation.py`. Constructor and `from_payload` share
this boundary. The helper's sole consumers were the group's effective Sv/InSv.
Genuine D6 targets, hit/wound thresholds, FNP and invulnerable grants retain their
existing 2..6 boundaries. SaveOption, save resolution, grouping algorithms,
decision dispatch, serializers and schemas already represent the required values.
No wire shape/version change is needed; runtime identity and its generated
contract examples must be refreshed normally.

## Source identity and limits

The independently reviewed follow-up uses these retained governed rows (selected
provider: Game Datamissions):

| Row | SHA-256 |
| --- | --- |
| `rule:02:02.02.01:1` | `b41c116532995553e3e5b5df1a3c970caf452a388f8ab49511fcf64fa0849d17` |
| `rule:05:05.03:1` | `293fb1a63e39b5729c3202915ff7cb98c43ded0422f211aa38f5e757ae2cf521` |
| `rule:05:05.04:1` | `5d9b5a54e5f2eae55cfd5e015ace1625b452c7f63aaf2e8dc881311c4f07c09e` |
| `rule:13:13.08:1` | `d180a0560b9dcee103a3cba6bd3e929086ff4a56f1b6ee4137ab292cdf646dc6` |

The preserved complete Bloodletters App page supports both native profiles'
Sv7/InSv5. Supplementary rendered App captures on 2026-11-04 corroborate the
bounded characteristic-limits subsection of [02.02.01](https://www.40k.app/rules/02-datasheets#02.02.01)
(SHA-256 `ed9a388f70d78c39e9ade21e6c7fd9dffdc4fa4982908b3569764a3d02aabf4b`)
and complete [13.08](https://www.40k.app/rules/13-terrain#13.08)
(`2f2be2db5d6308291b162d1c44e674e3b46a5fc3e06076331196369272bbcbb3`).
These are retained maintained unofficial-mirror rendered observations, not newly
fetched official PDF or network bytes. Their original receipts and independent
plan are preserved outside the checkout in the delivery evidence's `inherited-plan`.
No observation ledger is rewritten. Current 11th Cover worsens ranged BS; the
existing SAVE_BONUS branch is only an explicitly labelled alternate-policy control.

The inherited native60 same-class inventory contains six Sv7 profiles: Flesh
Hounds1112 (flesh-hounds/gore-hound), Bloodletters1114 (bloodletters/bloodreaper),
Plaguebearers1132 (plaguebearers/plagueridden). This inventory is not source
revalidation or complete gameplay certification of those other units.

## Regression boundaries

- `tests/rules/section05/test_allocation_choices.py`: exact constructor/decoder
  types/ranges; genuine native ten-model UnitFactory/UnitInstance/group roundtrip;
  complete native Bloodletters melee and shooting facade declarations, real dice,
  save/damage events and casualties; ten-model native Infractors positive controls.
  Numeric7/8 mixed groups retain their engine-built options and typed selected order.
  A clearly labelled surviving-attached-character Core context on a real Lord body
  covers the character branch; it does not claim native attachment admission.
- `tests/rules/section05/test_saves.py`: every D6 face at AP0/-1/-4, retained armour7
  and InSv5, armour-only impossible saves, actual modifier arithmetic for improvement,
  worsening7->8 and restoration, active Cover BS penalty with unchanged armour,
  alternate SAVE_BONUS control, no-saves and Devastating Wounds distinction, and
  unchanged passive/conditional invulnerable-grant bounds. The conditional descriptor
  is the already admitted Rangers clause in the checked-in Anvanth catalog artifact;
  malformed threshold variants do not admit source data or extend compiler grammar.
- `tests/rules/section04/test_completion_boundaries.py`: an admitted canonical
  session whose predeclared armour3 becomes effective7 through ModifierStack,
  with explicitly constructed Torrent/S20/A3 inputs to reach a real damage choice.
  After initial ordinary runtime-content hydration, all tested decisions and history
  are engine-generated. At the Sv7 pending grouped-damage interruption, verify both
  player projections contain numeric7 and validate the declared game-view schema and
  declared local-checkpoint subschema. Serialize/restore, fork, select the same
  engine-emitted option, complete the attack, compare exact final checkpoints,
  restore the completed checkpoint, and require ReplayRunner reproduction.

Shared setup lives in `tests/save7_allocation_helpers.py`; no tests import another
test module. Existing regression assertions are retained. The three existing test
files keep their shard membership; only their current active member digests change.
Historical native membership, all 260 exact quality deferrals and coverage selection
remain unchanged.

## Native session limitation and disposition

As documented by the preceding source order, the selected native catalog has no
admitted detachments. Its clause-level combat fixture carries EC `mercurial-host`
identity metadata, while GameConfig requires each player's muster request and full
restore remusters through ordinary detachment admission. A native complete-session
restore therefore cannot be certified by this bounded repair. Omitting metadata,
inventing a detachment or relaxing restoration is prohibited.

The coordinator explicitly accepted native facade/component proof together with
an existing admitted canonical effective-Sv7 session for persistence/fork/replay.
The latter is a constructed Core contract, not a newly admitted native granting
provider or a claim of full native Bloodletters army/mission/game playability.

## Performance and delivery

The change retains constant-time type/lower-bound validation. No enumeration,
sorting, geometry/LOS, RNG, cache, save arithmetic or serialization/replay algorithm
changes. The exact-base assessment maps every changed owner and generated input;
no detailed benchmark family is selected. The mandatory serial current-runtime
smoke, unchanged live work/cache/semantic controls, full-package 65% branch coverage,
16-worker local policy, 260 exact deferrals and 720/180/600 timing limits remain.
No historical benchmark, full-game or speed certification is implied.

Before-fix and failed fixture/manifest/static attempts remain in the delivery
receipts. Final aggregate qualification, independent coding review, separate fresh
parent audit, hosted CI and publication are coordinator-owned gates; focused
success is not their replacement. Apply `SEQUENTIAL_REMEDIATION_REVIEW_POLICY.md`:
normal legal-play and genuine engine-generated restore/replay failures block;
unrelated coordinated-history hardening remains separately queued.
