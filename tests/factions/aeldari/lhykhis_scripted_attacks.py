"""Predeclared native dice for the Lhykhis casualty and deferred mark tests."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

from tests.support.scripted_attack_rolls import ScriptedAttackRolls
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.ruleset_descriptor import FightEligibilityKind
from warhammer40k_core.engine.attack_sequence import (
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.saves import SaveKind, saving_throw_roll_spec

if TYPE_CHECKING:
    from tests.support.faction_batch01 import Scene
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence

_BROOD_TWAIN = "000003909:brood-twain:standard"
_WEB_SEQUENCE = "attack-sequence:web-declaration"
_WALKER_FEET = "000000612:war-walker-feet:standard"


def _attack_id(sequence_id: str, index: int) -> str:
    return f"{sequence_id}:pool-001:attack-{index:03d}"


@contextmanager
def scripted_walker_lethal_attack(source_id: str) -> Generator[None]:
    """One successful attack from the two native Walkers against wounded Lhykhis."""
    from warhammer40k_core.engine import fight_attack_completion

    executor = resolve_attack_sequence_until_blocked
    plan: ScriptedAttackRolls | None = None

    def resolve(**kwargs: Any) -> Any:
        nonlocal plan
        sequence = kwargs["attack_sequence"]
        if sequence.attacking_unit_instance_id != "foe:walkers":
            return executor(**kwargs)
        assert kwargs.get("dice_manager") is None
        assert sequence.source_phase is BattlePhase.FIGHT
        assert sequence.attacker_player_id == "opponent"
        assert tuple(pool.attacks for pool in sequence.attack_pools) == (3, 3)
        assert {pool.weapon_profile_id for pool in sequence.attack_pools} == {_WALKER_FEET}
        assert {pool.target_unit_instance_id for pool in sequence.attack_pools} == {"own:lhykhis"}
        if plan is None:
            # A four hits, the other five attacks miss, then one wound and failed save kill.
            hits = tuple(
                (
                    attack_sequence_hit_roll_spec(
                        weapon_profile_id=_WALKER_FEET,
                        attack_context_id=_attack_id(sequence.sequence_id, index),
                        attacker_player_id="opponent",
                    ),
                    4 if index == 1 else 1,
                )
                for index in range(1, 7)
            )
            attack_id = _attack_id(sequence.sequence_id, 1)
            wound = attack_sequence_wound_roll_spec(
                weapon_profile_id=_WALKER_FEET,
                attack_context_id=attack_id,
                attacker_player_id="opponent",
            )
            save = saving_throw_roll_spec(
                save_kind=SaveKind.INVULNERABLE,
                player_id="owner",
                allocated_model_id=source_id,
                attack_context_id=attack_id,
            )
            plan = ScriptedAttackRolls((*hits, (wound, 6), (save, 1)))
        return plan.run(executor, kwargs, manager_parameter="dice_manager")

    with patch.object(fight_attack_completion, "resolve_attack_sequence_until_blocked", resolve):
        yield
    assert plan is not None
    plan.assert_consumed()


@contextmanager
def scripted_six_brood_twain_wounds(s: Scene, *, attached_target: bool) -> Generator[None]:
    """Six undiverted Torrent wounds at the selected Brood Twain group only."""
    from warhammer40k_core.engine import (
        attack_sequence_dispatch as dispatch,
    )
    from warhammer40k_core.engine import (
        attack_sequence_group_selection as group_selection,
    )
    from warhammer40k_core.engine import (
        ranged_attack_count_gathering as gathering,
    )
    from warhammer40k_core.engine.attack_sequence_group_selection import (
        _resolve_grouped_current_pool,
    )
    from warhammer40k_core.engine.attack_sequence_grouped_allocation import (
        _continue_after_grouped_allocation_order,
    )

    target_id = "attached-unit:foe:target-body" if attached_target else "foe:walkers"
    victim = s.units["foe:target-body" if attached_target else target_id]
    representative = (
        next(model for model in victim.own_model_ids() if model.endswith(":warp-spiders:001"))
        if attached_target
        else victim.own_model_ids()[0]
    )
    assert sum(model.current_wounds for model in victim.own_models) == 6

    gather = gathering.gather_ranged_attack_counts
    resolve = _resolve_grouped_current_pool
    allocate = _continue_after_grouped_allocation_order
    count_plan: ScriptedAttackRolls | None = None
    attack_ids = tuple(_attack_id(_WEB_SEQUENCE, index) for index in range(1, 7))
    wounds = tuple(
        (
            attack_sequence_wound_roll_spec(
                weapon_profile_id=_BROOD_TWAIN,
                attack_context_id=attack_id,
                attacker_player_id="owner",
            ),
            6,
        )
        for attack_id in attack_ids
    )
    saves = tuple(
        (
            saving_throw_roll_spec(
                save_kind=SaveKind.INVULNERABLE,
                player_id="opponent",
                allocated_model_id=representative,
                attack_context_id=attack_id,
            ),
            1,
        )
        for attack_id in attack_ids
    )
    resolution_plan = ScriptedAttackRolls(wounds if attached_target else (*wounds, *saves))
    allocation_plan = ScriptedAttackRolls(saves) if attached_target else None

    def selected_brood_twain(sequence: AttackSequence) -> bool:
        if (
            sequence.sequence_id != _WEB_SEQUENCE
            or sequence.current_gathered_group is None
            or sequence.current_gathered_group.pool_indices != (0,)
        ):
            return False
        assert sequence.source_phase is BattlePhase.SHOOTING
        assert sequence.attacker_player_id == "owner"
        pool = sequence.attack_pools[0]
        assert pool.weapon_profile_id == _BROOD_TWAIN
        assert pool.target_unit_instance_id == target_id
        return True

    def gather_count(**kwargs: Any) -> Any:
        nonlocal count_plan
        sequence = kwargs["sequence"]
        if not selected_brood_twain(sequence):
            return gather(**kwargs)
        if count_plan is None:
            _, spec = gathering._count_roll_spec(  # pyright: ignore[reportPrivateUsage]
                sequence.sequence_id, sequence.attacker_player_id, 0, sequence.attack_pools[0]
            )
            assert spec.expression == DiceExpression(1, 6, 3)
            count_plan = ScriptedAttackRolls(((spec, 3),))
        return count_plan.run(gather, kwargs, manager_parameter="manager")

    def resolve_wounds(**kwargs: Any) -> Any:
        if not selected_brood_twain(kwargs["attack_sequence"]):
            return resolve(**kwargs)
        return resolution_plan.run(resolve, kwargs, manager_parameter="manager")

    def allocate_saves(**kwargs: Any) -> Any:
        if not selected_brood_twain(kwargs["attack_sequence"]):
            return allocate(**kwargs)
        assert allocation_plan is not None
        assert (
            tuple(entry["attack_context_id"] for entry in kwargs["attack_contexts"]) == attack_ids
        )
        return allocation_plan.run(allocate, kwargs, manager_parameter="manager")

    with ExitStack() as stack:
        stack.enter_context(patch.object(gathering, "gather_ranged_attack_counts", gather_count))
        stack.enter_context(patch.object(dispatch, "_resolve_grouped_current_pool", resolve_wounds))
        if allocation_plan is not None:
            stack.enter_context(
                patch.object(
                    group_selection, "_continue_after_grouped_allocation_order", allocate_saves
                )
            )
        yield
    assert count_plan is not None
    count_plan.assert_consumed()
    resolution_plan.assert_consumed()
    if allocation_plan is not None:
        allocation_plan.assert_consumed()


@contextmanager
def scripted_charged_fangs(s: Scene) -> Generator[None]:
    """Resolve the active charged Fight group's prescribed physical attack dice."""
    from warhammer40k_core.engine import attack_sequence_dispatch as dispatch
    from warhammer40k_core.engine.attack_sequence_group_selection import (
        _resolve_grouped_current_pool,
    )

    profile = "000003909:spiders-fangs:standard"
    target_id = "foe:walkers"
    defender = s.units[target_id].own_model_ids()[0]
    plan: ScriptedAttackRolls | None = None
    sequence_id: str | None = None

    def resolve(**kwargs: Any) -> Any:
        nonlocal plan, sequence_id
        sequence = kwargs["attack_sequence"]
        pool = sequence.current_pool()
        if (
            sequence.source_phase is not BattlePhase.FIGHT
            or sequence.attacking_unit_instance_id != "own:lhykhis"
            or pool.weapon_profile_id != profile
        ):
            return _resolve_grouped_current_pool(**kwargs)

        fight = kwargs["state"].fight_phase_state
        assert fight is not None
        activation = fight.active_activation
        assert activation is not None
        assert activation.player_id == sequence.attacker_player_id
        assert activation.unit_instance_id == sequence.attacking_unit_instance_id
        assert FightEligibilityKind.CHARGED_THIS_TURN in activation.eligibility_reasons
        assert kwargs["state"] is s.state
        assert sequence.attacker_player_id == "owner"
        assert pool.target_unit_instance_id == target_id
        assert pool.attacks == 5
        assert sequence.pool_index == 0
        assert sequence.current_gathered_group is not None
        assert sequence.current_gathered_group.pool_indices == (0,)
        if plan is None:
            sequence_id = sequence.sequence_id
            # A four hits and fails to wound. A five gives one automatic wound and saved attack.
            hits = tuple(
                (
                    attack_sequence_hit_roll_spec(
                        weapon_profile_id=profile,
                        attack_context_id=_attack_id(sequence.sequence_id, index),
                        attacker_player_id="owner",
                    ),
                    face,
                )
                for index, face in enumerate((4, 5, 1, 1, 1), 1)
            )
            wound = attack_sequence_wound_roll_spec(
                weapon_profile_id=profile,
                attack_context_id=_attack_id(sequence.sequence_id, 1),
                attacker_player_id="owner",
            )
            save = saving_throw_roll_spec(
                save_kind=SaveKind.INVULNERABLE,
                player_id="opponent",
                allocated_model_id=defender,
                attack_context_id=_attack_id(sequence.sequence_id, 2),
            )
            plan = ScriptedAttackRolls((*hits, (wound, 1), (save, 6)))
        assert sequence.sequence_id == sequence_id
        return plan.run(_resolve_grouped_current_pool, kwargs, manager_parameter="manager")

    with patch.object(dispatch, "_resolve_grouped_current_pool", resolve):
        yield
    assert plan is not None
    plan.assert_consumed()
