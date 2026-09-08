"""Model-scoped retained attacks hosted by the ordinary shooting executor."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.shooting_model import (
    OutOfPhaseShootingState,
    OutOfPhaseShootingStatePayload,
)
from warhammer40k_core.engine.retained_attack_permissions import RetainedAttackAction
from warhammer40k_core.engine.retained_destruction_state import (
    DestructionOwnerKind,
    RetainedDestructionStage,
    RetainedModelDestruction,
    retained_destruction_for_model,
    retained_destructions,
    validate_retained_placement,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.core.army_catalog import ArmyCatalog
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState

RETAINED_SHOOTING_CONTEXT_KIND = "retained_destruction_shooting"
_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class RetainedShootingExecution:
    cause_id: str
    parent_cause_id: str | None
    model_instance_id: str
    source_id: str
    source_rule_id: str
    source_request_id: str
    source_result_id: str
    suspended_shooting: OutOfPhaseShootingState | None
    attacks_completed: bool = False

    def __post_init__(self) -> None:
        for key in (
            "cause_id",
            "model_instance_id",
            "source_id",
            "source_rule_id",
            "source_request_id",
            "source_result_id",
        ):
            _identifier(key, getattr(self, key))
        if self.parent_cause_id is not None:
            _identifier("parent_cause_id", self.parent_cause_id)
            if self.parent_cause_id == self.cause_id:
                raise GameLifecycleError("Retained shooting cannot be its own parent.")
        if type(self.attacks_completed) is not bool:
            raise GameLifecycleError("Retained shooting completion must be boolean.")
        if (
            self.suspended_shooting is not None
            and type(self.suspended_shooting) is not OutOfPhaseShootingState
        ):
            raise GameLifecycleError("Retained shooting suspended host is invalid.")

    @property
    def effect_id(self) -> str:
        return f"retained-shooting:{self.cause_id}"

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "cause_id": self.cause_id,
                    "parent_cause_id": self.parent_cause_id,
                    "model_instance_id": self.model_instance_id,
                    "source_id": self.source_id,
                    "source_rule_id": self.source_rule_id,
                    "source_request_id": self.source_request_id,
                    "source_result_id": self.source_result_id,
                    "suspended_shooting": None
                    if self.suspended_shooting is None
                    else self.suspended_shooting.to_payload(),
                    "attacks_completed": self.attacks_completed,
                }
            ),
        )

    @classmethod
    def from_payload(cls, payload: JsonValue) -> Self:
        if not isinstance(payload, dict) or set(payload) != {
            "cause_id",
            "parent_cause_id",
            "model_instance_id",
            "source_id",
            "source_rule_id",
            "source_request_id",
            "source_result_id",
            "suspended_shooting",
            "attacks_completed",
        }:
            raise GameLifecycleError("Retained shooting execution fields drift.")
        suspended = payload["suspended_shooting"]
        if suspended is not None and not isinstance(suspended, dict):
            raise GameLifecycleError("Retained shooting suspended state must be an object.")
        completed = payload["attacks_completed"]
        if type(completed) is not bool:
            raise GameLifecycleError("Retained shooting completion must be boolean.")
        return cls(
            cause_id=_identifier("cause_id", payload["cause_id"]),
            parent_cause_id=None
            if payload["parent_cause_id"] is None
            else _identifier("parent_cause_id", payload["parent_cause_id"]),
            model_instance_id=_identifier("model_instance_id", payload["model_instance_id"]),
            source_id=_identifier("source_id", payload["source_id"]),
            source_rule_id=_identifier("source_rule_id", payload["source_rule_id"]),
            source_request_id=_identifier("source_request_id", payload["source_request_id"]),
            source_result_id=_identifier("source_result_id", payload["source_result_id"]),
            suspended_shooting=None
            if suspended is None
            else OutOfPhaseShootingState.from_payload(
                cast(OutOfPhaseShootingStatePayload, suspended)
            ),
            attacks_completed=completed,
        )


def retained_shooting_executions(*, state: GameState) -> tuple[RetainedShootingExecution, ...]:
    """Return the authenticated root-to-child chain, independent of effect inventory order."""
    executions: list[RetainedShootingExecution] = []
    for effect in state.persisting_effects:
        payload = effect.effect_payload
        if (
            not isinstance(payload, dict)
            or payload.get("effect_kind") != RETAINED_SHOOTING_CONTEXT_KIND
        ):
            continue
        if set(payload) != {"effect_kind", "execution"}:
            raise GameLifecycleError("Retained shooting effect fields drift.")
        execution = RetainedShootingExecution.from_payload(payload["execution"])
        if (
            effect.effect_id != execution.effect_id
            or effect.source_rule_id != execution.source_rule_id
        ):
            raise GameLifecycleError("Retained shooting effect identity drift.")
        executions.append(execution)
    if len({execution.cause_id for execution in executions}) != len(executions):
        raise GameLifecycleError("Retained shooting execution is duplicated.")
    children: dict[str | None, RetainedShootingExecution] = {}
    cause_ids = {execution.cause_id for execution in executions}
    for execution in executions:
        if execution.parent_cause_id in children:
            raise GameLifecycleError("Retained shooting parent has multiple children or roots.")
        if execution.parent_cause_id is not None and execution.parent_cause_id not in cause_ids:
            raise GameLifecycleError("Retained shooting execution has a missing parent.")
        children[execution.parent_cause_id] = execution
    ordered: list[RetainedShootingExecution] = []
    parent_id: str | None = None
    while parent_id in children:
        child = children.pop(parent_id)
        ordered.append(child)
        parent_id = child.cause_id
    if children:
        raise GameLifecycleError("Retained shooting parent chain is cyclic or disconnected.")
    return tuple(ordered)


def current_retained_shooter(*, state: GameState) -> RetainedModelDestruction | None:
    host = state.out_of_phase_shooting_state
    if (
        host is None
        or not isinstance(host.source_context, dict)
        or host.source_context.get("context_kind") != RETAINED_SHOOTING_CONTEXT_KIND
    ):
        return None
    context = host.source_context
    if set(context) != {"context_kind", "cause_id", "model_instance_id"}:
        raise GameLifecycleError("Retained shooting source context fields drift.")
    record = retained_destruction_for_model(
        state=state,
        model_instance_id=_identifier("model_instance_id", context["model_instance_id"]),
    )
    if (
        record is None
        or record.selected_action is not RetainedAttackAction.SHOOT
        or record.stage is not RetainedDestructionStage.WAITING
    ):
        raise GameLifecycleError("Retained shooting actor has no waiting shooting entitlement.")
    executions = [
        execution
        for execution in retained_shooting_executions(state=state)
        if execution.cause_id == record.cause_id
    ]
    if len(executions) != 1:
        raise GameLifecycleError("Retained shooting host lacks one execution owner.")
    execution = executions[0]
    source = next(
        source
        for source in record.eligible_sources
        if source.source_id == record.selected_source_id
    )
    view = rules_unit_view_by_id(state=state, unit_instance_id=record.placement.unit_instance_id)
    if (
        execution.attacks_completed
        or context["cause_id"] != record.cause_id
        or execution.model_instance_id != record.model_instance_id
        or execution.source_id != source.source_id
        or execution.source_rule_id != source.source_rule_id
        or host.selected_unit_instance_id != view.unit_instance_id
        or host.player_id != record.placement.player_id
        or host.source_rule_id != source.source_rule_id
        or host.source_decision_request_id != record.request_id
        or execution.source_request_id != record.request_id
        or host.source_decision_result_id != record.result_id
        or execution.source_result_id != record.result_id
        or host.parent_phase is not state.current_battle_phase
        or host.battle_round != state.battle_round
        or host.target_unit_ids is not None
    ):
        raise GameLifecycleError("Retained shooting source, actor or timing authority drift.")
    validate_retained_placement(state=state, record=record)
    return record


def advance_retained_shooting(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.phases.shooting_requests import (
        request_out_of_phase_shooting_declaration,
    )

    executions = retained_shooting_executions(state=state)
    if executions and executions[-1].attacks_completed:
        execution = executions[-1]
        record = retained_destruction_for_model(
            state=state, model_instance_id=execution.model_instance_id
        )
        if record is None:
            state.remove_persisting_effects_by_id((execution.effect_id,))
            state.replace_out_of_phase_shooting_state(execution.suspended_shooting)
            decisions.event_log.append(
                "retained_shooting_resumed_parent",
                {"cause_id": execution.cause_id, "model_instance_id": execution.model_instance_id},
            )
            return LifecycleStatus.advanced(stage=state.stage)
    existing_ids = {execution.cause_id for execution in executions}
    waiting = [
        record
        for record in retained_destructions(state=state)
        if record.selected_action is RetainedAttackAction.SHOOT
        and record.stage is RetainedDestructionStage.WAITING
        and record.cause_id not in existing_ids
    ]
    if not waiting:
        return None
    record = waiting[0]
    source = next(
        source
        for source in record.eligible_sources
        if source.source_id == record.selected_source_id
    )
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Retained shooting requires a battle phase.")
    if record.owner_kind is DestructionOwnerKind.ATTACK:
        _release_parent_attack_destruction(state=state, record=record)
    execution = RetainedShootingExecution(
        cause_id=record.cause_id,
        parent_cause_id=executions[-1].cause_id if executions else None,
        model_instance_id=record.model_instance_id,
        source_id=source.source_id,
        source_rule_id=source.source_rule_id,
        source_request_id=_identifier("request_id", record.request_id),
        source_result_id=_identifier("result_id", record.result_id),
        suspended_shooting=state.out_of_phase_shooting_state,
    )
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=execution.effect_id,
            source_rule_id=source.source_rule_id,
            owner_player_id=record.placement.player_id,
            target_unit_instance_ids=(record.placement.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=phase,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=phase,
                player_id=_identifier("active_player_id", state.active_player_id),
            ),
            effect_payload={
                "effect_kind": RETAINED_SHOOTING_CONTEXT_KIND,
                "execution": execution.to_payload(),
            },
        )
    )
    decisions.event_log.append("retained_shooting_started", execution.to_payload())
    state.replace_out_of_phase_shooting_state(None)
    return request_out_of_phase_shooting_declaration(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        player_id=record.placement.player_id,
        unit_instance_id=record.placement.unit_instance_id,
        parent_phase=phase,
        source_rule_id=source.source_rule_id,
        source_decision_request_id=execution.source_request_id,
        source_decision_result_id=execution.source_result_id,
        source_context={
            "context_kind": RETAINED_SHOOTING_CONTEXT_KIND,
            "cause_id": record.cause_id,
            "model_instance_id": record.model_instance_id,
        },
    )


def complete_retained_shooting(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_state: OutOfPhaseShootingState,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.retained_destruction_cleanup import (
        begin_retained_destruction_cleanup,
    )

    record = current_retained_shooter(state=state)
    if record is None:
        return None
    if state.out_of_phase_shooting_state != completed_state:
        raise GameLifecycleError("Retained shooting completion host drift.")
    executions = retained_shooting_executions(state=state)
    execution = executions[-1]
    if execution.cause_id != record.cause_id:
        raise GameLifecycleError("Retained shooting must complete the innermost executor first.")
    updated = replace(execution, attacks_completed=True)
    effect = next(
        effect for effect in state.persisting_effects if effect.effect_id == execution.effect_id
    )
    replacement = replace(
        effect,
        effect_payload={
            "effect_kind": RETAINED_SHOOTING_CONTEXT_KIND,
            "execution": updated.to_payload(),
        },
    )
    state.remove_persisting_effects_by_id((execution.effect_id,))
    state.record_persisting_effect(replacement)
    decisions.event_log.append(
        "retained_shooting_attacks_completed",
        {
            "cause_id": record.cause_id,
            "model_instance_id": record.model_instance_id,
            "attack_pools": validate_json_value(
                [pool.to_payload() for pool in completed_state.attack_pools]
            ),
        },
    )
    state.replace_out_of_phase_shooting_state(None)
    status = begin_retained_destruction_cleanup(
        state=state,
        decisions=decisions,
        reason="model_shoot_completed",
        unit_instance_id=record.placement.unit_instance_id,
        model_instance_id=record.model_instance_id,
    )
    return LifecycleStatus.advanced(stage=state.stage) if status is None else status


def automatically_pass_retained_shooting_hazardous(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
    weapon_instance_ids: tuple[str, ...],
    weapon_profile_ids: tuple[str, ...],
) -> bool:
    record = current_retained_shooter(state=state)
    if record is None:
        return False
    source = next(
        source
        for source in record.eligible_sources
        if source.source_id == record.selected_source_id
    )
    if (
        not isinstance(source.payload, dict)
        or source.payload.get("shooting_hazardous_tests_automatically_pass") is not True
    ):
        return False
    if any(
        pool.attacker_model_instance_id != record.model_instance_id
        for pool in sequence.attack_pools
    ):
        raise GameLifecycleError("Retained Hazardous permission cannot apply to another model.")
    decisions.event_log.append(
        "retained_shooting_hazardous_automatically_passed",
        {
            "cause_id": record.cause_id,
            "model_instance_id": record.model_instance_id,
            "source_id": source.source_id,
            "source_rule_id": source.source_rule_id,
            "sequence_id": sequence.sequence_id,
            "weapon_instance_ids": list(weapon_instance_ids),
            "weapon_profile_ids": list(weapon_profile_ids),
        },
    )
    return True


def _release_parent_attack_destruction(
    *, state: GameState, record: RetainedModelDestruction
) -> None:
    from warhammer40k_core.engine.retained_destruction_cleanup import (
        attack_sequence_for_retained_destruction,
    )
    from warhammer40k_core.engine.retained_destruction_dispatch import replace_host_attack_sequence

    original = attack_sequence_for_retained_destruction(record)
    candidates = (
        state.out_of_phase_shooting_state,
        state.fight_phase_state,
        state.shooting_phase_state,
    )
    sequences = [
        host.attack_sequence
        for host in candidates
        if host is not None
        and host.attack_sequence is not None
        and host.attack_sequence.sequence_id == original.sequence_id
    ]
    if len(sequences) != 1:
        raise GameLifecycleError("Retained shooting requires its suspended original attack host.")
    sequence = sequences[0]
    pending = sequence.current_pending_attack_destruction
    if (
        pending is not None
        and pending.damage_application.model_instance_id == record.model_instance_id
    ):
        replace_host_attack_sequence(
            state=state,
            original_sequence_id=sequence.sequence_id,
            sequence=sequence.without_current_pending_attack_destruction(),
        )
