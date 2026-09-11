from __future__ import annotations

from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHookRegistry,
)
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.catalog_model_materialization_runtime import (
    CatalogModelMaterializationRuntime,
)
from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplicationProgress,
    continue_mortal_wound_application,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import resolve_mortal_wound_decision
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id


def destroy_horror_models_for_completion_fixture(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
    target_unit_id: str,
    model_ids: tuple[str, ...],
    source_kind: DestructionSourceKind,
    source_step: str,
    event_sequence_matches: bool,
) -> None:
    """Supply completed damage using the real allocation and destruction owners."""
    target = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_id)
    models = {model.model_instance_id: model for model in target.alive_models()}
    pool = sequence.attack_pools[0]
    evidence = (
        MortalWoundDestructionEvidence.for_attack_state(
            state=state,
            destroying_player_id=sequence.attacker_player_id,
            attacking_unit_instance_id=sequence.attacking_unit_instance_id,
            attacking_model_instance_id=pool.attacker_model_instance_id,
            weapon_profile=pool.weapon_profile,
            attack_context_id=f"{sequence.sequence_id}:pool-001:attack-001",
            action_phase=sequence.source_phase,
            source_step=source_step,
        )
        if source_kind is DestructionSourceKind.ATTACK
        else MortalWoundDestructionEvidence.for_non_attack_state(
            state=state,
            destroying_player_id=sequence.attacker_player_id,
            source_rules_unit_instance_id=sequence.attacking_unit_instance_id,
            source_model_instance_id=pool.attacker_model_instance_id,
            destruction_source_kind=source_kind,
            action_phase=sequence.source_phase,
            source_step=source_step,
        )
    )
    identity = f"{sequence.sequence_id}:fixture-damage"
    routed = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id=f"{identity}:request:0",
        progress=MortalWoundApplicationProgress.start(
            application_id=identity,
            source_rule_id="test:horrors:destruction",
            source_context={
                "source_kind": "horror_completion_fixture",
                "sequence_id": (
                    sequence.sequence_id
                    if event_sequence_matches
                    or source_kind
                    in (DestructionSourceKind.ATTACK, DestructionSourceKind.HAZARDOUS)
                    else None
                ),
            },
            destruction_evidence=evidence,
            target_unit_instance_id=target.unit_instance_id,
            defender_player_id=target.owner_player_id,
            mortal_wounds=sum(models[model_id].wounds_remaining for model_id in model_ids),
            spill_over=True,
        ),
    )
    decision_index = 0
    while routed.request is not None:
        request = decisions.request_decision(routed.request)
        selected = next(
            option.option_id for option in request.options if option.option_id in model_ids
        )
        result = DecisionResult.for_request(
            request=request,
            result_id=f"{identity}:result:{decision_index}",
            selected_option_id=selected,
        )
        decisions.submit_result(result)
        decision_index += 1
        routed = resolve_mortal_wound_decision(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            next_request_id=f"{identity}:request:{decision_index}",
        )
    assert routed.application is not None
    assert {
        damage.model_instance_id for damage in routed.application.applications if damage.destroyed
    } == set(model_ids)


def finish_prior_horror_destruction_triggers(
    *, state: GameState, decisions: DecisionController
) -> None:
    from warhammer40k_core.engine.model_destruction_triggers import (
        resolve_model_destruction_trigger,
    )
    from warhammer40k_core.engine.rule_trigger_state import RuleTriggerKind, rule_trigger_history
    from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedHookRegistry

    while ready := rule_trigger_history(decisions).ready():
        if ready[0].kind is not RuleTriggerKind.MODEL_DESTRUCTION:
            break
        assert (
            resolve_model_destruction_trigger(
                state=state,
                decisions=decisions,
                trigger=ready[0],
                registry=UnitDestroyedHookRegistry.empty(),
            )
            is None
        )


def resolve_horror_completion(
    runtime: CatalogModelMaterializationRuntime, context: AttackSequenceCompletedContext
) -> LifecycleStatus | None:
    registry = AttackSequenceCompletedHookRegistry.from_bindings(runtime.bindings())
    for _ in range(32):
        finish_prior_horror_destruction_triggers(state=context.state, decisions=context.decisions)
        status = registry.resolve_completed_sequence(context)
        if status is None or status.status_kind is not LifecycleStatusKind.ADVANCED:
            return status
    raise AssertionError("Horror completion did not finish its deferred rules")
