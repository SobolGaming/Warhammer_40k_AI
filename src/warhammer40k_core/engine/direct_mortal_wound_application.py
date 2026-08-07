# pyright: reportPrivateUsage=false

from __future__ import annotations

from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DamageKind,
    FeelNoPainResolution,
    MortalWoundApplication,
    _state_feel_no_pain_decline_allowed,
    _state_feel_no_pain_sources,
    _validate_positive_int,
    allocation_context_for_unit,
    apply_damage_to_model,
    resolve_feel_no_pain_rolls,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
    pre_removal_model_placement_for_mortal_wound_destruction,
    record_finalized_mortal_wound_application_destructions,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    current_placed_alive_rules_unit_view_for_identity,
)


def apply_direct_mortal_wounds_to_unit(
    *,
    state: GameState,
    decisions: DecisionController,
    application_id: str,
    source_rule_id: str,
    source_context: JsonValue,
    destruction_evidence: MortalWoundDestructionEvidence,
    target_unit_instance_id: str,
    mortal_wounds: int,
    spill_over: bool = True,
    dice_manager: DiceRollManager | None = None,
    defender_player_id: str | None = None,
) -> MortalWoundApplication:
    remaining = _validate_positive_int("mortal_wounds", mortal_wounds)
    if type(spill_over) is not bool:
        raise GameLifecycleError("spill_over must be a bool.")
    applications: list[DamageApplication] = []
    feel_no_pain_resolutions: list[FeelNoPainResolution] = []
    ignored_mortal_wounds = 0
    remaining_lost = 0
    destroyed_model_placements: list[ModelPlacement] = []
    while remaining > 0:
        rules_unit = current_placed_alive_rules_unit_view_for_identity(
            state=state,
            unit_instance_id=target_unit_instance_id,
        )
        if rules_unit is None:
            remaining_lost = remaining
            break
        legal_model_ids = allocation_context_for_unit(
            state=state,
            target_unit_instance_id=rules_unit.unit_instance_id,
        ).legal_model_ids()
        if not legal_model_ids:
            remaining_lost = remaining
            break
        model_id = legal_model_ids[0]
        sources = _state_feel_no_pain_sources(state=state, model_instance_id=model_id)
        decline_allowed = _state_feel_no_pain_decline_allowed(
            state=state,
            model_instance_id=model_id,
        )
        if len(sources) > 0:
            if len(sources) > 1 or decline_allowed:
                raise GameLifecycleError(
                    "Mortal wound Feel No Pain choices require lifecycle routing."
                )
            if dice_manager is None or defender_player_id is None:
                raise GameLifecycleError(
                    "Mortal wound Feel No Pain resolution requires dice manager and defender."
                )
            resolution = resolve_feel_no_pain_rolls(
                manager=dice_manager,
                source=sources[0],
                player_id=defender_player_id,
                model_instance_id=model_id,
                requested_wounds=1,
            )
            feel_no_pain_resolutions.append(resolution)
            if resolution.ignored_wounds == 1:
                ignored_mortal_wounds += 1
                remaining -= 1
                continue
        pre_removal_placement = pre_removal_model_placement_for_mortal_wound_destruction(
            state=state,
            model_instance_id=model_id,
        )
        damage_application = apply_damage_to_model(
            state=state,
            target_unit_instance_id=target_unit_instance_id,
            model_instance_id=model_id,
            damage=1,
            damage_kind=DamageKind.MORTAL,
        )
        applications.append(damage_application)
        if damage_application.destroyed:
            destroyed_model_placements.append(pre_removal_placement)
        remaining -= 1
        if damage_application.destroyed and not spill_over:
            remaining_lost = remaining
            remaining = 0
    mortal_wound_application = MortalWoundApplication(
        target_unit_instance_id=target_unit_instance_id,
        mortal_wounds=mortal_wounds,
        spill_over=spill_over,
        applications=tuple(applications),
        feel_no_pain_resolutions=tuple(feel_no_pain_resolutions),
        ignored_mortal_wounds=ignored_mortal_wounds,
        remaining_mortal_wounds_lost=remaining_lost,
    )
    record_finalized_mortal_wound_application_destructions(
        state=state,
        decisions=decisions,
        application_id=application_id,
        source_rule_id=source_rule_id,
        source_context=source_context,
        application=mortal_wound_application,
        evidence=destruction_evidence,
        destroyed_model_placements=tuple(destroyed_model_placements),
    )
    return mortal_wound_application


__all__ = ("apply_direct_mortal_wounds_to_unit",)
