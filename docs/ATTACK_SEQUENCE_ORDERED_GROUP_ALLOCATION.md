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
