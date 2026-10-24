# Section24 inherited test corrections

The incoming Section23 source and accepted review remain preserved. Three
inherited test files differ in this delivery; there is no runtime change. The
original files and function/assertion inventories are retained under
`superseded-17ac59c6/original-tests/` and `original-test-assertions.json` in the
delivery evidence. The original Windows timeout and four WSL failures remain
uncredited in `runs/r1-final-attack-lifecycle-dependencies/` and
`linux-results-r1/attack-lifecycle-dependencies/`, with exact input snapshots.

## Lethal Hits deterministic decision identity

`test_choices_devastating_sustained_restore_and_replay` retains every original
assertion, including an original declined Lethal Hit producing a critical wound,
Devastating Wounds, restored equality, both viewers and exact replay. The adopted
Section24.23 source offers a choice for each eligible Critical Hit before rolling
to wound; it does not promise a particular attack ordinal or result ID.

The old pinned `attack-014` decision is absent from the current valid generated
Shooting history. Decisions005,008 and009 are generated instead. The fixture now
uses the actual009 decision with legal deterministic result identity suffix
`section24-original-critical:8`. `lethal-valid-checkpoint.json` and
`lethal-seed-search.json` preserve the engine-generated checkpoint and bounded
experiments. A normal persistence round-trip and public submissions produce
original wound faces1/5/6, exercising the original critical-wound assertion.
The game ID, runtime RNG, decision controller and strength/target premises are
unchanged. This is deterministic fixture selection, not a runtime RNG repair or
an edited historical checkpoint. All four phase/choice combinations are required
in final bounded validation.

## Firing Deck declaration versus completion

`test_all_cargo_is_restricted_even_with_zero_contributors` previously asserted
that the transport had shot immediately after accepting its declaration, while
physical attacks were still pending. The accepted SF04 source requires a unit
to resolve its attacks before it has shot. Exact adopted references are
`rule:04:04.03.04:1` blocks2/3 and `rule:04:04.03.05:1` block2, whose retained
hashes are respectively
`f760ee7e3ce11ab4f7d3ec58d36e410caf3629e1a5e38fde86b03c98500a20a7`,
`f104b31c655f1eb2cba4aee921b7bb2570f6332aaf37937fa33061c56d45762d`
and `ec1500b998410b5921b8cd8229270f4cfb73aab463d48393ba09be1fc42e5a66`.
`docs/SF04_COMPLETION_REPAIR.md` records the adopted distinction: selection is
consumed at selection; nonempty attacks enter shot inventory after all physical
attacks including deferred mortals resolve; cargo restrictions start at declaration.

The one obsolete assertion is preserved verbatim in the original file. It is
replaced at that same checkpoint with two stricter source-correct assertions:
the transport is selected and has not yet shot. Every cargo snapshot, restriction,
restore, persistence, event and viewer assertion remains unchanged. The existing
Section04 native declaration and physical completion controls are additionally
selected as explicit acceptance dependencies; completion is not discarded merely
because its old assertion was at the wrong checkpoint.

## Public Firing Deck helper holds the intended phase

`test_public_firing_deck_history._session` adds one ordinary canonical observer
unit that remains selectable. Previously the prior-shot variant could complete
all friendly selections, automatically cross turn end, and reach opponent
Movement. The adopted Section24.14 restriction lasts until end of turn, so its
expiry there is correct. The original failed-event receipt preserves this phase
transition. Holding a live Shooting checkpoint restores this test's stated
premise without changing expiry semantics or any original assertion.

All five test functions using the helper, including nine invalid/retry cases,
pending drift, five phase-context cases and redaction, are required in bounded
validation. The separate restriction-expiry test remains unchanged. These
constructed canonical checkpoints do not certify native roster/provider admission.

No skip, xfail, assertion suppression or numerical deadline increase is used.
Coordinated edited-history hardening, including SF16-R004, remains separately queued.
