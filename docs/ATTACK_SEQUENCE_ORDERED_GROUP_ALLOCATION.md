# Attack Sequence Ordered Group Allocation

This diagram summarizes the CORE V2 pooled attack sequence for ordered group
allocation. Normal damage and mortal wounds share the same engine-owned
decision/replay path, but normal damage walks sorted save dice through ordered
allocation groups before resolving model damage. Mortal wounds bypass saving
throws and route directly to mortal-wound allocation and model damage
resolution.

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
    resolve_normal["Resolve Damage for Model: normal damage"]
    model_destroyed{Current model destroyed?}
    group_exhausted{Current group exhausted?}
    next_model["Damage Allocation: shift to next model in current group"]
    next_group["Damage Allocation: advance to next ordered group"]
    next_die{More failed save dice?}
    mortal_packet["Damage Allocation: mortal wound packet"]
    mortal_model["Damage Allocation: current mortal wound model"]
    resolve_mortal["Resolve Damage for Model: mortal wounds"]
    mortal_remaining{More mortal wounds?}
    fnp{Feel No Pain choice or roll?}
    reaction{Destruction reaction or Deadly Demise?}
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
    normal_damage --> resolve_normal
    resolve_normal --> fnp
    fnp --> reaction
    reaction --> model_destroyed
    model_destroyed -- "Yes" --> group_exhausted
    model_destroyed -- "No" --> next_die
    group_exhausted -- "No" --> next_model
    group_exhausted -- "Yes" --> next_group
    next_model --> next_die
    next_group --> next_die
    next_die -- "Yes" --> save_walk
    next_die -- "No" --> done

    devastating -- "Mortal wounds" --> mortal_packet
    mortal_packet --> mortal_model
    mortal_model --> resolve_mortal
    resolve_mortal --> fnp
    fnp --> mortal_remaining
    mortal_remaining -- "Yes" --> mortal_model
    mortal_remaining -- "No" --> reaction
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
- Mortal wounds do not create save choices; optional Feel No Pain and
  destruction reactions still use the same lifecycle decision path.
