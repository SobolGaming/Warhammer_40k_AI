"""Resolve gathered dice by rule step, retaining physical roll and choice identities."""

from dataclasses import replace
from typing import TYPE_CHECKING, Literal

from warhammer40k_core.engine.attack_sequence_dice_rerolls import (
    _roll_hit_and_wound,
    _roll_hit_step,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_modifier_evaluation import WoundModifierEvaluation
    from warhammer40k_core.engine.attack_sequence_model import (
        AttackResolutionContextPayload,
        AttackSequenceHooks,
        HitRoll,
        PsychicAttackModifierIgnoreSelection,
        WoundRoll,
    )
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phase import LifecycleStatus
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


def resolve_gathered_attack_dice(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    hooks: AttackSequenceHooks,
    stratagem_index: StratagemCatalogIndex | None,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[
    tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    LifecycleStatus | None,
]:
    """Reconstruct progress from the original roll/decision journal on every resume.

    A return at a choice never advances another rule step. Re-entering reuses
    exact roll specs, accepted choices and unique step events; it neither rolls
    again nor trusts a client-supplied attack cursor.
    """
    pool = attack_sequence.current_pool()
    originals = tuple(replace(attack_sequence, attack_index=index) for index in range(pool.attacks))
    wound_sequences: list[tuple[AttackSequence, HitRoll]] = []
    stages: tuple[Literal["prepare", "roll", "resolve"], ...] = (
        "prepare",
        "roll",
        "resolve",
    )
    # Reuse only within this callback-free invocation. Any player choice returns
    # immediately, so the next submission rebuilds preparation and roll authority.
    prepared_hits: (
        dict[
            str,
            tuple[RangedAttackPool, PsychicAttackModifierIgnoreSelection | None, tuple[str, ...]],
        ]
        | None
    ) = None if hooks.handlers else {}
    rolled_hits: dict[str, HitRoll] | None = None if hooks.handlers else {}
    for stage in stages:
        for current in originals:
            hit, status = _roll_hit_step(
                state=state,
                decisions=decisions,
                manager=manager,
                attack_sequence=current,
                hooks=hooks,
                stratagem_index=stratagem_index,
                stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
                runtime_modifier_registry=runtime_modifier_registry,
                hit_stage=stage,
                gathered_pool=pool,
                prepared_hits=prepared_hits,
                rolled_hits=rolled_hits,
            )
            if status is not None:
                return (), status
            if stage == "prepare":
                continue
            if hit is None:
                raise GameLifecycleError("Gathered Hit step lost its original roll.")
            if stage == "roll" or not hit.successful:
                continue
            while True:
                wound_sequences.append((current, hit))
                if current.generated_hit_index + 1 >= hit.generated_hits:
                    break
                current = current.advanced_after_generated_hit(hit)

    wounded_contexts: list[tuple[AttackSequence, AttackResolutionContextPayload]] = []
    # Custom event callbacks may affect later evaluations. Reuse preparations
    # only when this invocation has no callbacks, and discard them on every pause.
    prepared_wounds: dict[str, tuple[WoundModifierEvaluation, tuple[str, ...]]] | None = (
        None if hooks.handlers else {}
    )
    rolled_wounds: dict[str, WoundRoll] | None = None if hooks.handlers else {}
    for stage in stages:
        for current, hit in wound_sequences:
            context, status = _roll_hit_and_wound(
                state=state,
                decisions=decisions,
                manager=manager,
                attack_sequence=current,
                hooks=hooks,
                stratagem_index=stratagem_index,
                stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
                runtime_modifier_registry=runtime_modifier_registry,
                wound_stage=stage,
                gathered_pool=pool,
                finalized_hit=hit,
                prepared_wounds=prepared_wounds,
                rolled_wounds=rolled_wounds,
            )
            if status is not None:
                return (), status
            if stage == "resolve":
                if context is None:
                    raise GameLifecycleError("Gathered Wound step lost its successful Hit.")
                if context["wound_roll"]["successful"]:
                    wounded_contexts.append((current, context))
    return tuple(wounded_contexts), None
