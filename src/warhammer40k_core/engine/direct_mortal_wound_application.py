# pyright: reportPrivateUsage=false

from __future__ import annotations

from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.damage_allocation import (
    DamageApplication,
    DamageKind,
    FeelNoPainResolution,
    MortalWoundApplication,
    apply_damage_to_model,
    resolve_feel_no_pain_rolls,
)
from warhammer40k_core.engine.damage_allocation_validation import validate_positive_int
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseKind,
)
from warhammer40k_core.engine.mortal_wound_application_authority import (
    append_direct_mortal_wound_application_started,
)
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
    pre_removal_model_placement_for_mortal_wound_destruction,
    record_finalized_mortal_wound_application_destructions,
)
from warhammer40k_core.engine.mortal_wound_logical_death import (
    append_mortal_wound_damage_logical_death_event,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    mortal_wound_feel_no_pain_decline_allowed,
    mortal_wound_feel_no_pain_sources,
    mortal_wound_priority_model_ids,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    current_placed_alive_rules_unit_view_for_identity,
    rules_unit_owner_player_id,
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
    remaining = validate_positive_int("mortal_wounds", mortal_wounds)
    if type(spill_over) is not bool:
        raise GameLifecycleError("spill_over must be a bool.")
    canonical_defender_player_id = rules_unit_owner_player_id(
        state=state,
        unit_instance_id=target_unit_instance_id,
    )
    if defender_player_id is not None and defender_player_id != canonical_defender_player_id:
        raise GameLifecycleError("Direct mortal-wound defender player drift.")
    _prevalidate_direct_mortal_wound_route(
        state=state,
        target_unit_instance_id=target_unit_instance_id,
        mortal_wounds=remaining,
        spill_over=spill_over,
        dice_manager=dice_manager,
        defender_player_id=defender_player_id,
    )
    append_direct_mortal_wound_application_started(
        state=state,
        event_log=decisions.event_log,
        application_id=application_id,
        source_rule_id=source_rule_id,
        source_context=source_context,
        target_unit_instance_id=target_unit_instance_id,
        defender_player_id=canonical_defender_player_id,
        mortal_wounds=remaining,
        spill_over=spill_over,
        destruction_evidence=destruction_evidence,
    )
    applications: list[DamageApplication] = []
    feel_no_pain_resolutions: list[FeelNoPainResolution] = []
    ignored_mortal_wounds = 0
    remaining_lost = 0
    destroyed_model_placements: list[ModelPlacement] = []
    logical_death_events: list[EventRecord] = []
    while remaining > 0:
        rules_unit = current_placed_alive_rules_unit_view_for_identity(
            state=state,
            unit_instance_id=target_unit_instance_id,
        )
        if rules_unit is None:
            remaining_lost = remaining
            break
        legal_model_ids = mortal_wound_priority_model_ids(
            state=state,
            target_unit_instance_id=rules_unit.unit_instance_id,
        )
        if not legal_model_ids:
            remaining_lost = remaining
            break
        if len(legal_model_ids) > 1:
            raise GameLifecycleError("Mortal wound model choices require lifecycle routing.")
        model_id = next(iter(legal_model_ids))
        sources = mortal_wound_feel_no_pain_sources(
            state=state,
            model_instance_id=model_id,
        )
        decline_allowed = mortal_wound_feel_no_pain_decline_allowed(
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
            logical_death_events.append(
                append_mortal_wound_damage_logical_death_event(
                    state=state,
                    event_log=decisions.event_log,
                    cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
                    producer_id=application_id,
                    damage_application=damage_application,
                    destroyed_model_placement=pre_removal_placement,
                    placement_retained=False,
                )
            )
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
        logical_death_events=tuple(logical_death_events),
    )
    return mortal_wound_application


def _prevalidate_direct_mortal_wound_route(
    *,
    state: GameState,
    target_unit_instance_id: str,
    mortal_wounds: int,
    spill_over: bool,
    dice_manager: DiceRollManager | None,
    defender_player_id: str | None,
) -> None:
    """Reject every potentially reachable choice before direct routing mutates authority."""

    simulated_state = GameState.from_payload(state.to_payload())
    remaining = mortal_wounds
    while remaining > 0:
        rules_unit = current_placed_alive_rules_unit_view_for_identity(
            state=simulated_state,
            unit_instance_id=target_unit_instance_id,
        )
        if rules_unit is None:
            return
        legal_model_ids = mortal_wound_priority_model_ids(
            state=simulated_state,
            target_unit_instance_id=rules_unit.unit_instance_id,
        )
        if not legal_model_ids:
            return
        if len(legal_model_ids) > 1:
            raise GameLifecycleError("Mortal wound model choices require lifecycle routing.")
        model_id = next(iter(legal_model_ids))
        sources = mortal_wound_feel_no_pain_sources(
            state=simulated_state,
            model_instance_id=model_id,
        )
        decline_allowed = mortal_wound_feel_no_pain_decline_allowed(
            state=simulated_state,
            model_instance_id=model_id,
        )
        if len(sources) > 1 or (sources and decline_allowed):
            raise GameLifecycleError("Mortal wound Feel No Pain choices require lifecycle routing.")
        if sources and (dice_manager is None or defender_player_id is None):
            raise GameLifecycleError(
                "Mortal wound Feel No Pain resolution requires dice manager and defender."
            )
        simulated_damage = apply_damage_to_model(
            state=simulated_state,
            target_unit_instance_id=target_unit_instance_id,
            model_instance_id=model_id,
            damage=1,
            damage_kind=DamageKind.MORTAL,
        )
        remaining -= 1
        if simulated_damage.destroyed and not spill_over:
            return


__all__ = ("apply_direct_mortal_wounds_to_unit",)
