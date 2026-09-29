# Order 99 / P02J — Leadership, Weapon Skill, and Ballistic Skill bounds

C02-10 left the shared characteristic policy short of the selected 02.02.01
limits. Modified Leadership could resolve to 4+ or 9+, and modified Weapon Skill
and Ballistic Skill had no 6+ ceiling. The retained Order 97 probe observed
Leadership 4 and 9 and Weapon Skill / Ballistic Skill 16.

## Source and scope

The selected Order 97 transcription of `rule:02:02.02.01:1` already contains the
operative limits. This change does not recapture or regenerate that source.
Load and execution status stay as recorded. The historical probe JSON remains
the discovery record.

| Clause | Block | Retained text |
|---|---:|---|
| 02.02.01-obligation-18 | 27 | Ld cannot be 4+ (or better) or 9+ (or worse). |
| 02.02.01-obligation-22 | 31 | WS cannot be 1+ (or better) or 7+ (or worse). |
| 02.02.01-obligation-23 | 32 | BS cannot be 1+ (or better) or 7+ (or worse). |

Those sentences sit under “After all modifiers have been applied.” The existing
algebra still runs first: replacement, multiplication, addition, division,
subtraction, then one upward rounding of the exact intermediate. The shared
`CharacteristicBoundPolicy` then limits Leadership to 5–8 and Weapon Skill and
Ballistic Skill to 2–6. Source operation identifiers stay on the trace. An
in-range result is unchanged. Other characteristic limits are unchanged.

## Authority trace

Source-linked characteristic operations, including generic RuleIR Leadership and
weapon-skill effects, enter `ModifierStack`. `resolve_bounded` keeps the
unbounded arithmetic and applies the policy only to `final`. Leadership tests,
including Command-phase Battle-shock, read that final value. Weapon profiles
built by `rule_ir_modified_weapon_profile` store the same bounded skill, and
the shared hit resolver recomputes it from the raw skill plus the retained
skill operations, including Benefit of Cover. Replay and persistence use the
existing decision and event records; no payload shape or contract version
changes.

## Evidence and retained gates

`tests/unit/test_phase10j1_numeric_rules.py` covers the floors, ceilings,
in-range results, and replacement-multiplication-addition order with source
identifiers and payload restoration. `tests/integration/test_core_modifier_boundaries.py`
runs both Leadership directions through the Command-phase facade, checks the
persisted source operand against the unbounded and bounded results, and replays
both viewers. The same test resolves ranged and melee weapon profiles through
the live hit consumer, including a Ballistic Skill 6+ attack worsened by
Benefit of Cover. No Core Rules or complete-game performance certificate is
claimed. PFINAL remains open.

The Order 97 inventory now binds these clauses to the assertions above. Its
probe file and `observed_gaps_01_08.json` stay the historical Leadership 4/9
and WS/BS 16 observation. The reviewed inventory fingerprint was recomputed
after those evidence, pin, and runtime-manifest changes.

Runtime identity changed, so the existing runtime-bound head reports were
remeasured on this host with the same workloads, baselines, and budgets.
Historical baseline samples were not relabeled. Commands, durations, and
hashes are in
[the refresh record](performance/order99/inherited-refresh.json).
