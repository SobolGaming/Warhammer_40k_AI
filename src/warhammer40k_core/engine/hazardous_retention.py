"""Route weapon Hazardous casualties through the shared rule-destruction owner."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplication,
    MortalWoundApplicationPayload,
    MortalWoundApplicationProgress,
    MortalWoundRoutingResult,
)
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.model_destruction_cause_authority import ModelDestructionCauseKind
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.mortal_wound_logical_death import (
    MortalWoundLogicalDeathCauseBinding,
    MortalWoundLogicalDeathRecorder,
    fixed_mortal_wound_logical_death_recorder,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import continue_mortal_wound_application
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.retained_attack_permissions import RETAINED_ATTACK_REACTION_KINDS
from warhammer40k_core.engine.retained_destruction_state import retained_destruction_for_model
from warhammer40k_core.engine.rule_model_destruction_applied_damage import (
    continue_applied_mortal_wound_destruction_with_rule_reactions,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.game_state import GameState

HAZARDOUS_DESTRUCTION_ROUTING_STARTED = "hazardous_destruction_routing_started"
HAZARDOUS_MODEL_DESTRUCTION_COMPLETED = "hazardous_model_destruction_completed"


def validate_retained_hazardous_progress(
    *, state: GameState, progress: MortalWoundApplicationProgress
) -> None:
    from warhammer40k_core.engine.attack_sequence_hazardous import (
        validate_hazardous_mortal_wound_source_context,
    )
    from warhammer40k_core.engine.lifecycle_state_queries import active_attack_sequence_for_state
    from warhammer40k_core.engine.weapon_abilities import HAZARDOUS_RULE_ID

    sequence = active_attack_sequence_for_state(state)
    if (
        sequence is None
        or progress.application_id != f"{sequence.sequence_id}:hazardous:mortal-wounds"
        or progress.target_unit_instance_id != sequence.attacking_unit_instance_id
        or progress.source_rule_id != HAZARDOUS_RULE_ID
        or progress.destruction_evidence is not None
        or progress.logical_death_cause_binding
        != MortalWoundLogicalDeathCauseBinding.fixed(
            cause_kind=ModelDestructionCauseKind.RULE_EFFECT, producer_id=progress.application_id
        )
    ):
        raise GameLifecycleError("Retained Hazardous application source binding drift.")
    validate_hazardous_mortal_wound_source_context(
        state=state,
        attack_sequence=sequence,
        source_context_payload=progress.source_context,
        mortal_wounds=progress.mortal_wounds,
    )


def route_hazardous_damage(
    *,
    state: GameState,
    decisions: DecisionController,
    progress: MortalWoundApplicationProgress,
    manager: DiceRollManager,
) -> MortalWoundRoutingResult:
    view = rules_unit_view_by_id(state=state, unit_instance_id=progress.target_unit_instance_id)
    retains = any(
        source.reaction_kind in RETAINED_ATTACK_REACTION_KINDS
        for model in view.alive_models()
        for source in state.destruction_reaction_sources_for_model(
            model_instance_id=model.model_instance_id
        )
    )
    if retains:
        progress = replace(
            progress,
            destruction_evidence=None,
            logical_death_cause_binding=MortalWoundLogicalDeathCauseBinding.fixed(
                cause_kind=ModelDestructionCauseKind.RULE_EFFECT,
                producer_id=progress.application_id,
            ),
        )
    recorder = hazardous_retention_recorder(state=state, decisions=decisions, progress=progress)
    return continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id=state.next_decision_request_id(),
        progress=progress,
        dice_manager=manager,
        remove_destroyed_models=recorder is None,
        logical_death_recorder=recorder,
    )


def hazardous_retention_recorder(
    *,
    state: GameState,
    decisions: DecisionController,
    progress: MortalWoundApplicationProgress,
) -> MortalWoundLogicalDeathRecorder | None:
    binding = progress.logical_death_cause_binding
    if binding is None or binding.cause_kind is not ModelDestructionCauseKind.RULE_EFFECT:
        return None
    if (
        not isinstance(progress.source_context, dict)
        or progress.source_context.get("source_kind") != "hazardous"
        or progress.destruction_evidence is not None
        or binding
        != MortalWoundLogicalDeathCauseBinding.fixed(
            cause_kind=ModelDestructionCauseKind.RULE_EFFECT, producer_id=progress.application_id
        )
    ):
        raise GameLifecycleError("Retained Hazardous damage binding drift.")
    return fixed_mortal_wound_logical_death_recorder(
        state=state,
        event_log=decisions.event_log,
        binding=binding,
    )


def finish_retained_hazardous_damage(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
    routed: MortalWoundRoutingResult,
) -> LifecycleStatus | None:
    if (
        hazardous_retention_recorder(state=state, decisions=decisions, progress=routed.progress)
        is None
    ):
        return None
    if routed.application is None:
        raise GameLifecycleError("Retained Hazardous destruction requires completed damage.")
    decisions.event_log.append(
        HAZARDOUS_DESTRUCTION_ROUTING_STARTED,
        {
            "game_id": state.game_id,
            "sequence_id": sequence.sequence_id,
            "application_id": routed.progress.application_id,
            "source_rule_id": routed.progress.source_rule_id,
            "source_context": routed.progress.source_context,
            "target_unit_instance_id": routed.progress.target_unit_instance_id,
            "application": validate_json_value(routed.application.to_payload()),
        },
    )
    _started, status = resume_retained_hazardous_destructions(
        state=state,
        decisions=decisions,
        sequence=sequence,
    )
    return status


def resume_retained_hazardous_destructions(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
) -> tuple[bool, LifecycleStatus | None]:
    starts = [
        event
        for event in decisions.event_log.records
        if event.event_type == HAZARDOUS_DESTRUCTION_ROUTING_STARTED
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == sequence.sequence_id
    ]
    if not starts:
        return False, None
    if len(starts) != 1 or not isinstance(starts[0].payload, dict):
        raise GameLifecycleError("Retained Hazardous damage was routed twice.")
    payload = starts[0].payload
    application_id = _identifier(payload.get("application_id"))
    source_rule_id = _identifier(payload.get("source_rule_id"))
    application = MortalWoundApplication.from_payload(
        cast(MortalWoundApplicationPayload, payload.get("application"))
    )
    if application_id != f"{sequence.sequence_id}:hazardous:mortal-wounds":
        raise GameLifecycleError("Retained Hazardous destruction application drift.")
    for damage in application.applications:
        if not damage.destroyed:
            continue
        if (
            retained_destruction_for_model(state=state, model_instance_id=damage.model_instance_id)
            is not None
        ):
            continue
        completed = [
            event
            for event in decisions.event_log.records
            if event.event_type == HAZARDOUS_MODEL_DESTRUCTION_COMPLETED
            and isinstance(event.payload, dict)
            and event.payload.get("application_id") == application_id
            and event.payload.get("model_instance_id") == damage.model_instance_id
        ]
        if len(completed) > 1:
            raise GameLifecycleError("Retained Hazardous casualty completed twice.")
        if completed:
            continue
        outcome = continue_applied_mortal_wound_destruction_with_rule_reactions(
            state=state,
            decisions=decisions,
            damage_application=damage,
            rules_unit_instance_id=application.target_unit_instance_id,
            source_rule_id=source_rule_id,
            source_result_id=application_id,
            completion_event_type=HAZARDOUS_MODEL_DESTRUCTION_COMPLETED,
            completion_event_payload={
                "sequence_id": sequence.sequence_id,
                "application_id": application_id,
                "model_instance_id": damage.model_instance_id,
            },
            destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
                state=state,
                destroying_player_id=sequence.attacker_player_id,
                source_rules_unit_instance_id=sequence.attacking_unit_instance_id,
                source_model_instance_id=None,
                destruction_source_kind=DestructionSourceKind.HAZARDOUS,
                action_phase=sequence.source_phase,
                source_step="hazardous_test",
            ),
        )
        if outcome.status is not None:
            return True, outcome.status
    return True, None


def _identifier(value: JsonValue) -> str:
    if type(value) is not str or not value:
        raise GameLifecycleError("Retained Hazardous routing requires an identifier.")
    return value
