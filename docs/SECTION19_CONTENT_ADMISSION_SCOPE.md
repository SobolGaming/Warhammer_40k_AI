# SF19-R002: selected content survives casualties in live and restored bundles

The required Epic Challenge dependency reaches a public melee commitment after
earlier successful facade checkpoints. `LocalGameSession` then rejects its own
save because rebuilding the lifecycle changes `runtime_content_audit`. The two
lost records are `gw-11e-core-abilities:datasheet:core-leader` and
`gw-11e-core-abilities:keyword:keyword-infantry`. Complete captured before/after
payloads and the failure are retained externally.

The bounded hydration probe reproduces the same difference on both the exact
accepted Section18 source and the Section19 candidate. This is an incoming
defect, not a regression introduced by the Lone Operative repair. The source
and decisions come from the admitted constructed canonical facade fixture;
no native faction/provider admission or complete-game certification is inferred.

`RuntimeContentActivation` retains selected unit/datasheet/wargear membership
after casualties. The live lifecycle therefore reuses its existing activation
bundle. `build_player_ability_index`, however, filtered selected records using
`UnitInstance.keywords`, which intentionally contains only living model
keywords. A fresh restore consequently dropped selected records after their
models died, making its audit differ from the valid live checkpoint.

The owning admission filter now checks the selected physical model keyword
assignments, just as selected equipment admission uses all owned models. Live
`UnitInstance` and attached-unit keyword queries remain living-only. The ability
execution registry still checks the actual current source keyword gate; stable
content admission grants no action, physical presence or keyword contribution
to destroyed models. Unselected keyword content remains excluded.

This changes neither schema nor loader compatibility. Restore is still strict;
no audit mismatch is ignored or normalized by a shim. Live cache and fresh
restore now derive the same selected content from the same authoritative roster.
The new regression uses native selected units and actual shared casualty
production, with both admission and live-keyword controls. Original Epic
Challenge assertions remain unchanged. Required dependency runs are partitioned
by logical family under the same command timeouts; no case is dropped.
