"""Native physical weapon identity with fixed dice at the real sequence owner."""

from dataclasses import replace
from typing import cast

from tests.support.section02_consumers import attack_pool
from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section04_fixtures import combat_state

from warhammer40k_core.core.dice import DiceRollResult
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.saves import SaveKind, saving_throw_roll_spec
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_instances import (
    equipped_weapon_profile_instances_for_model,
)


def native_sequence(
    d: Section02Definitions,
    *,
    target: UnitInstance | None = None,
    attacks: int = 1,
    distance: float = 8,
    melee: bool = False,
) -> tuple[GameState, UnitInstance, AttackSequence]:
    unit = d.unit(LORD_EXULTANT)
    enemy = target or d.unit(LORD_EXULTANT, army_id="enemy", identity="target")
    physical = next(
        w
        for w in equipped_weapon_profile_instances_for_model(
            model=unit.own_models[0], army_catalog=d.package.army_catalog
        )
        if w.wargear_id == f"{LORD_EXULTANT}:" + ("close-combat-weapon" if melee else "bolt-pistol")
    )
    pool = replace(
        attack_pool(unit, enemy, physical.weapon_profile, physical.wargear_id),
        weapon_instance_id=physical.weapon_instance_id,
        attacks=attacks,
    )
    # attacks>1 is an explicit pooled-count Core contract, not native bolt-pistol A.
    phase = BattlePhase.FIGHT if melee else BattlePhase.SHOOTING
    return (
        combat_state(d, unit, target=enemy, distance=distance, phase=phase),
        enemy,
        AttackSequence("s05", "owner", unit.unit_instance_id, (pool,), source_phase=phase),
    )


def fixed_sequence_dice(
    sequence: AttackSequence,
    target: UnitInstance,
    hits: tuple[int, ...],
    wounds: tuple[int, ...],
    saves: tuple[int, ...],
) -> tuple[DiceRollResult, ...]:
    pool = sequence.attack_pools[0]
    dice = DiceRollManager("physical")
    results: list[DiceRollResult] = []
    hit_indices = tuple(i for i, v in enumerate(hits, 1) if v >= 2)
    wound_indices = tuple(i for i, v in zip(hit_indices, wounds, strict=True) if v >= 4)
    inv = any(
        v.characteristic.value == "invulnerable_save" and v.final > 0
        for v in target.own_models[0].characteristics
    )
    for factory, indices, faces in (
        (attack_sequence_hit_roll_spec, tuple(range(1, len(hits) + 1)), hits),
        (attack_sequence_wound_roll_spec, hit_indices, wounds),
    ):
        for i, face in zip(indices, faces, strict=True):
            spec = factory(
                weapon_profile_id=pool.weapon_profile_id,
                attack_context_id=f"s05:pool-001:attack-{i:03d}",
                attacker_player_id="owner",
            )
            results.append(dice.roll_fixed(spec, (face,)).original_result)
    for i, face in zip(wound_indices, saves, strict=True):
        spec = saving_throw_roll_spec(
            save_kind=SaveKind.INVULNERABLE if inv else SaveKind.ARMOUR,
            player_id="opponent",
            allocated_model_id=target.own_model_ids()[0],
            attack_context_id=f"s05:pool-001:attack-{i:03d}",
        )
        results.append(dice.roll_fixed(spec, (face,)).original_result)
    return tuple(results)


def resolve(
    state: GameState,
    sequence: AttackSequence,
    results: tuple[DiceRollResult, ...],
    *,
    registry: RuntimeModifierRegistry | None = None,
) -> tuple[DecisionController, AttackSequence | None, LifecycleStatus | None]:
    decisions = DecisionController()
    remaining, _, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        runtime_modifier_registry=registry,
        dice_manager=DiceRollManager(
            "s05", event_log=decisions.event_log, injected_results=results
        ),
    )
    return decisions, remaining, status


def payloads(decisions: DecisionController, event_type: str) -> list[dict[str, JsonValue]]:
    return [
        cast(dict[str, JsonValue], e.payload)
        for e in decisions.event_log.records
        if e.event_type == event_type
    ]
