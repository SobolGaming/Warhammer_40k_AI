"""Observe real executor boundaries with native bodies/weapons and fixed misses.

Declaration permission is upstream: these are explicit already-selected-pool
contracts, not a new claim about roster legality or extra-weapon admission.
"""

from dataclasses import replace
from typing import cast

from tests.support.section02_consumers import attack_pool
from tests.support.section02_fixtures import INFRACTORS, LORD_EXULTANT, Section02Definitions
from tests.support.section04_fixtures import add_enemy, combat_state

from warhammer40k_core.core.dice import DiceRollResult
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    apply_attack_weapon_group_decision,
    apply_resolve_target_unit_decision,
    attack_sequence_hit_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.wargear_selections import WargearSelection
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.engine.weapon_instances import (
    EquippedWeaponProfileInstance,
    equipped_weapon_profile_instances_for_model,
)


def completion_boundaries(
    definitions: Section02Definitions,
    *,
    phase: BattlePhase,
    multiple_models: bool,
) -> tuple[
    AttackSequence, list[tuple[AttackSequence, tuple[EventRecord, ...]]], tuple[EventRecord, ...]
]:
    """The observer returns None and never changes selection, state or outcomes."""
    d = definitions
    if multiple_models:
        unit = d.unit(INFRACTORS)
    elif phase is BattlePhase.FIGHT:
        unit = d.unit(LORD_EXULTANT)
    else:
        unit = d.unit(
            LORD_EXULTANT,
            wargear=(
                WargearSelection(
                    f"{LORD_EXULTANT}:phoenix-power-spear-screamer-pistol:option-2",
                    f"{LORD_EXULTANT}:lord-exultant",
                    (f"{LORD_EXULTANT}:screamer-pistol",),
                ),
            ),
        )
    target = d.unit(LORD_EXULTANT, army_id="enemy", identity="target")
    distance = 8 if phase is BattlePhase.SHOOTING else 2.5
    state = combat_state(d, unit, target=target, phase=phase, distance=distance)
    targets = [target]
    if multiple_models:
        targets += [
            add_enemy(d, state, identity=f"target{i}", x=10 + distance, y=10 + 2 * i)
            for i in (1, 2)
        ]
    selected: list[EquippedWeaponProfileInstance] = []
    for model in unit.own_models[:3] if multiple_models else unit.own_models[:1]:
        physical = [
            w
            for w in equipped_weapon_profile_instances_for_model(
                model=model, army_catalog=d.package.army_catalog
            )
            if (w.weapon_profile.range_profile.distance_inches is None)
            is (phase is BattlePhase.FIGHT)
        ]
        # One genuine physical weapon per native model, or all of one model's weapons.
        selected.extend(physical[:1] if multiple_models else physical)
    pools: list[RangedAttackPool] = []
    for index, weapon in enumerate(selected):
        profile = weapon.weapon_profile
        if phase is BattlePhase.FIGHT and not multiple_models and index > 0:
            # Explicit extra-attack permission outcome; do not certify native admission.
            profile = replace(profile, keywords=(*profile.keywords, WeaponKeyword.EXTRA_ATTACKS))
        pools.append(
            replace(
                attack_pool(
                    unit, targets[index] if multiple_models else target, profile, weapon.wargear_id
                ),
                attacker_model_instance_id=weapon.model_instance_id,
                weapon_instance_id=weapon.weapon_instance_id,
            )
        )
    assert len(pools) >= 2
    original = AttackSequence(
        "s04-boundary", "owner", unit.unit_instance_id, tuple(pools), source_phase=phase
    )
    results = tuple(
        DiceRollResult.from_values(
            roll_id=f"boundary:{i}:{attack}",
            spec=attack_sequence_hit_roll_spec(
                weapon_profile_id=pool.weapon_profile_id,
                attack_context_id=f"s04-boundary:pool-{i + 1:03d}:attack-{attack:03d}",
                attacker_player_id="owner",
            ),
            values=(1,),
            source="rng",
        )
        for i, pool in enumerate(pools)
        for attack in range(1, pool.attacks + 1)
    )
    decisions = DecisionController()
    manager = DiceRollManager(
        "s04-boundary", event_log=decisions.event_log, injected_results=results
    )
    snapshots: list[tuple[AttackSequence, tuple[EventRecord, ...]]] = []

    def observe(sequence: AttackSequence) -> LifecycleStatus | None:
        snapshots.append((sequence, decisions.event_log.records))
        return None

    sequence: AttackSequence | None = original
    for _ in range(12):
        assert sequence is not None
        sequence, _, status = resolve_attack_sequence_until_blocked(
            state=state,
            decisions=decisions,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            attack_sequence=sequence,
            already_allocated_model_ids=(),
            dice_manager=manager,
            before_gathering=observe,
        )
        if sequence is None:
            assert status is None
            return original, snapshots, decisions.event_log.records
        request = decisions.queue.peek_next()
        assert request.actor_id == "owner"
        next_index = min(set(range(len(pools))) - set(sequence.used_pool_indices))
        if request.decision_type == "select_resolve_target_unit":
            option = "resolve-target:" + pools[next_index].target_unit_instance_id
        else:
            assert request.decision_type == "select_attack_weapon_group", request
            option = next(
                o.option_id
                for o in request.options
                if cast(
                    dict[str, JsonValue], cast(dict[str, JsonValue], o.payload)["gathered_group"]
                )["pool_indices"]
                == [next_index]
            )
        result = DecisionResult.for_request(
            result_id=request.request_id + ":chosen", request=request, selected_option_id=option
        )
        decisions.submit_result(result)
        sequence = (
            apply_resolve_target_unit_decision
            if request.decision_type == "select_resolve_target_unit"
            else apply_attack_weapon_group_decision
        )(decisions=decisions, attack_sequence=sequence, result=result)
    raise AssertionError("Bounded completion sequence did not finish")
