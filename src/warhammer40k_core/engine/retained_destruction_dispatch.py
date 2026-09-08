from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.damage_allocation import (
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    SELECT_MORTAL_WOUND_MODEL_DECISION_TYPE,
    is_mortal_wound_resolution_request,
    mortal_wound_resolution_source_context,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.retained_destruction_cleanup import (
    attack_sequence_for_retained_destruction,
    complete_removed_retained_destructions,
    continue_retained_transport_cleanup,
    record_retained_attack_progress,
)
from warhammer40k_core.engine.retained_destruction_state import (
    RetainedModelDestruction,
    retained_destruction_for_model,
    retained_destructions,
)

if TYPE_CHECKING:
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def resume_declined_attack_collateral(
    *, state: GameState, decisions: DecisionController, record: RetainedModelDestruction
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.retained_destruction_attack import (
        resume_retained_attack_collateral,
    )

    cause = next(
        value
        for value in state.model_destruction_cause_authorities
        if value.cause_id == record.cause_id
    )
    parents = tuple(
        value
        for value in retained_destructions(state=state)
        if value.cause_id in cause.parent_cause_ids
    )
    if len(parents) > 1:
        raise GameLifecycleError("Declined collateral has ambiguous retained parents.")
    original_sequence = attack_sequence_for_retained_destruction(record)
    sequence, status = resume_retained_attack_collateral(
        state=state, decisions=decisions, record=record, attack_sequence=original_sequence
    )
    if parents:
        if status is not None:
            current = retained_destruction_for_model(
                state=state, model_instance_id=parents[0].model_instance_id
            )
            if current is None or sequence is None:
                raise GameLifecycleError("Declined collateral lost its parent continuation.")
            record_retained_attack_progress(
                state=state,
                decisions=decisions,
                record=current,
                sequence=sequence,
            )
    else:
        replace_host_attack_sequence(
            state=state, original_sequence_id=original_sequence.sequence_id, sequence=sequence
        )
    if status is None:
        complete_removed_retained_destructions(state=state, decisions=decisions)
    return status


def replace_host_attack_sequence(
    *, state: GameState, original_sequence_id: str, sequence: AttackSequence | None
) -> None:
    out_of_phase = state.out_of_phase_shooting_state
    if (
        out_of_phase is not None
        and out_of_phase.attack_sequence is not None
        and out_of_phase.attack_sequence.sequence_id == original_sequence_id
    ):
        state.replace_out_of_phase_shooting_state(
            out_of_phase.with_attack_sequence_update(
                attack_sequence=sequence,
                allocated_model_ids=out_of_phase.allocated_model_ids,
            )
        )
        return
    fight = state.fight_phase_state
    if (
        fight is not None
        and fight.attack_sequence is not None
        and fight.attack_sequence.sequence_id == original_sequence_id
    ):
        state.replace_fight_phase_state(
            fight.with_attack_sequence_update(
                attack_sequence=sequence,
                allocated_model_ids_this_phase=fight.allocated_model_ids_this_phase,
            )
        )
        return
    shooting = state.shooting_phase_state
    if (
        shooting is not None
        and shooting.attack_sequence is not None
        and shooting.attack_sequence.sequence_id == original_sequence_id
    ):
        state.replace_shooting_phase_state(
            shooting.with_attack_sequence_update(
                attack_sequence=sequence,
                allocated_model_ids_this_phase=shooting.allocated_model_ids_this_phase,
            )
        )
        return
    raise GameLifecycleError("Retained collateral lost its original attack host.")


def apply_retained_attack_destruction_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    record: RetainedModelDestruction,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.attack_sequence import (
        apply_destroyed_transport_disembark_proposal_decision,
        apply_destruction_reaction_decision,
        apply_feel_no_pain_decision,
        is_destroyed_transport_disembark_proposal_request,
    )

    sequence = attack_sequence_for_retained_destruction(record)
    updated_sequence: AttackSequence | None
    request = decisions.record_for_result(result).request
    source_context = (
        mortal_wound_resolution_source_context(request)
        if is_mortal_wound_resolution_request(request)
        else None
    )
    from warhammer40k_core.engine.transports import (
        TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
        apply_transport_hazard_mortal_wound_feel_no_pain_decision,
    )

    if (
        isinstance(source_context, dict)
        and source_context.get("source_kind") == TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND
    ):
        status = apply_transport_hazard_mortal_wound_feel_no_pain_decision(
            state=state,
            decisions=decisions,
            result=result,
        )
        updated_sequence = sequence
        if status is None:
            updated_sequence, status = continue_retained_transport_cleanup(
                state=state,
                decisions=decisions,
                sequence=sequence,
            )
    elif is_destroyed_transport_disembark_proposal_request(request):
        updated_sequence, _allocated_model_ids, status = (
            apply_destroyed_transport_disembark_proposal_decision(
                state=state,
                decisions=decisions,
                ruleset_descriptor=ruleset_descriptor,
                attack_sequence=sequence,
                result=result,
                already_allocated_model_ids=(),
            )
        )
    else:
        if result.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE:
            applier = apply_destruction_reaction_decision
        elif result.decision_type in (
            SELECT_FEEL_NO_PAIN_DECISION_TYPE,
            SELECT_MORTAL_WOUND_MODEL_DECISION_TYPE,
        ):
            applier = apply_feel_no_pain_decision
        else:
            raise GameLifecycleError("Retained destruction received an unsupported continuation.")
        updated_sequence, _allocated_model_ids, status = applier(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=sequence,
            result=result,
            already_allocated_model_ids=(),
            runtime_modifier_registry=runtime_modifier_registry,
        )
    current = retained_destruction_for_model(
        state=state, model_instance_id=record.model_instance_id
    )
    if current is None:
        raise GameLifecycleError("Retained destruction lost its active owner.")
    if status is not None:
        if updated_sequence is None:
            raise GameLifecycleError("Retained destruction decision lost its attack sequence.")
        record_retained_attack_progress(
            state=state,
            decisions=decisions,
            record=current,
            sequence=updated_sequence,
        )
        return status
    complete_removed_retained_destructions(state=state, decisions=decisions)
    return None
