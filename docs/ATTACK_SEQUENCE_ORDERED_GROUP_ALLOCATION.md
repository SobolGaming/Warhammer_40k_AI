# Attack Sequence Ordered Group Allocation

This document summarizes the CORE V2 ranged attack sequence. Phase 14L adds the
rulebook Select Enemy Unit and Gather Attack Dice layer before the existing
ordered group allocation resolver. The gathered attack group then feeds the same
engine-owned hit, wound, allocation, save, damage, mortal-wound, and destruction
reaction path shown in the second diagram.

```mermaid
flowchart TD
    start([Ranged attack sequence starts])
    target_count{Unresolved pools target<br/>two or more enemy units?}
    select_target["Select Enemy Unit<br/>select_resolve_target_unit"]
    auto_target["Auto-record only remaining target unit"]
    group_count{Selected target has<br/>two or more identical-attack groups?}
    select_group["Gather Attack Dice<br/>select_attack_weapon_group"]
    auto_group["Auto-record only remaining gathered group"]
    resolve["Resolve Attack Dice<br/>existing ordered group allocation subgraph"]
    same_target{Unused weapons remain<br/>for the same target?}
    other_target{Unused weapons remain<br/>for another target?}
    done([Attack sequence complete])

    start --> target_count
    target_count -- "Yes" --> select_target
    target_count -- "No" --> auto_target
    select_target --> group_count
    auto_target --> group_count
    group_count -- "Yes" --> select_group
    group_count -- "No" --> auto_group
    select_group --> resolve
    auto_group --> resolve
    resolve --> same_target
    same_target -- "Yes" --> group_count
    same_target -- "No" --> other_target
    other_target -- "Yes" --> target_count
    other_target -- "No" --> done
```

The Gather Attack Dice step groups unresolved ranged pools for the selected
target only when their deterministic identical-attack signature matches. The
signature includes hit basis, hit/wound modifiers, Strength, AP, Damage,
applicable structured weapon abilities/keywords, targeting rule IDs, shooting
type, attacker model ID, wargear/profile IDs, visible and in-range target model
IDs, and optional Firing Deck source unit/model IDs. These provenance fields are
part of the signature because the current resolver turns a gathered group into a
single synthetic `RangedAttackPool`; the copied pool identity must therefore be
identical across every contribution before hit/wound attribution, Precision
visibility, cover/LOS, save, damage, event attribution, or Firing Deck/source
attribution can run through that synthetic pool. It deliberately excludes only
the Attacks count and raw weapon range value; per-contribution attack counts
remain replay evidence in the gathered group payload. Melee attack splitting and
melee identical-attack gathering remain Phase 15 Fight-phase work.

The following diagram is the Resolve Attack Dice subgraph for one gathered group.
Normal damage and mortal wounds share the same engine-owned decision/replay path,
but normal damage walks sorted save dice through ordered allocation groups before
resolving model damage. Mortal wounds bypass saving throws and route directly to
mortal-wound allocation and model damage resolution.

```mermaid
flowchart TD
    start([Attack pool starts])
    hit["To Hit"]
    hit_result{Any hit successful?}
    wound["To Wound"]
    wound_result{Any wound successful?}
    devastating{Devastating Wounds or other mortal wound source?}
    order["Damage Allocation: build ordered allocation groups"]
    save_roll["Save: roll pooled save dice"]
    save_walk["Save: walk dice low to high"]
    save_result{Save successful?}
    normal_damage["Damage Allocation: current ordered group and model"]
    normal_fnp["Resolve Feel No Pain (if applicable)"]
    resolve_normal["Apply remaining normal damage to model"]
    model_destroyed{Current model destroyed?}
    normal_destruction["Resolve destruction window: mandatory Deadly Demise chains, then optional reactions"]
    group_exhausted{Current group exhausted?}
    next_model["Damage Allocation: shift to next model in current group"]
    next_group["Damage Allocation: advance to next ordered group"]
    next_die{More failed save dice?}
    mortal_packet["Damage Allocation: mortal wound packet"]
    mortal_model["Damage Allocation: current mortal wound model"]
    mortal_fnp["Resolve Feel No Pain (if applicable)"]
    resolve_mortal["Apply remaining mortal wound to model"]
    mortal_destroyed{Current mortal-wound model destroyed?}
    mortal_destruction["Resolve destruction window: mandatory Deadly Demise chains, then optional reactions"]
    mortal_remaining{More mortal wounds?}
    done([Attack pool resolved])

    start --> hit
    hit --> hit_result
    hit_result -- "No" --> done
    hit_result -- "Yes" --> wound
    wound --> wound_result
    wound_result -- "No" --> done
    wound_result -- "Yes" --> devastating

    devastating -- "Normal damage" --> order
    order --> save_roll
    save_roll --> save_walk
    save_walk --> save_result
    save_result -- "Saved" --> next_die
    save_result -- "Failed" --> normal_damage
    normal_damage --> normal_fnp
    normal_fnp --> resolve_normal
    resolve_normal --> model_destroyed
    model_destroyed -- "Yes" --> normal_destruction
    model_destroyed -- "No" --> next_die
    normal_destruction --> group_exhausted
    group_exhausted -- "No" --> next_model
    group_exhausted -- "Yes" --> next_group
    next_model --> next_die
    next_group --> next_die
    next_die -- "Yes" --> save_walk
    next_die -- "No" --> done

    devastating -- "Mortal wounds" --> mortal_packet
    mortal_packet --> mortal_model
    mortal_model --> mortal_fnp
    mortal_fnp --> resolve_mortal
    resolve_mortal --> mortal_destroyed
    mortal_destroyed -- "Yes" --> mortal_destruction
    mortal_destroyed -- "No" --> mortal_remaining
    mortal_destruction --> mortal_remaining
    mortal_remaining -- "Yes" --> mortal_model
    mortal_remaining -- "No" --> done
```

Key constraints:

- The engine owns every mutation after `DecisionResult` validation.
- Allocation order is a finite engine-emitted decision only when multiple legal
  same-tier group orders exist.
- Normal damage rolls all pooled saving throw dice before applying normal
  damage, then resolves save events while walking the sorted dice. A real armour
  or invulnerable save with a target above 6 remains a saving throw; an effect
  that permits no saving throw may use an internal
  `attack_sequence.allocation_order.no_save` die only for deterministic ordering.
- Normal damage stays on the current model until that model is destroyed. If
  the current ordered group still has eligible models, allocation shifts to the
  next model in that group; it advances to the next ordered group only after
  the current group is exhausted.
- Feel No Pain is resolved, declined, or auto-applied at the lost-wound stage
  before any remaining damage is applied to the model.
- Destruction windows are opened only after damage leaves a model destroyed.
  Mandatory destruction reactions such as Deadly Demise resolve before removal
  and can recursively route mortal wounds that destroy additional models with
  their own mandatory destruction reactions. Optional destruction reactions are
  then emitted through the lifecycle decision path when the rules provide a
  choice.
- Mortal wounds do not create save choices; optional Feel No Pain and
  destruction reactions still use the same lifecycle decision path.
