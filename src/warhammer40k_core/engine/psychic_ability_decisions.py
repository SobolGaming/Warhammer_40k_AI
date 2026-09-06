"""Pre-pop Psychic use validation shared by existing finite activation families."""

from __future__ import annotations

from warhammer40k_core.engine.abilities import ability_record_is_active_generic_rule_ir
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.psychic_ability_usage import psychic_source_unavailable_reason
from warhammer40k_core.engine.rule_execution import scoped_rule_ir_from_execution_payload
from warhammer40k_core.rules.psychic_ability_identity import psychic_ability_level


def invalid_psychic_activation_status(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    bundle: RuntimeContentBundle | None,
) -> LifecycleStatus | None:
    payload = result.payload
    if bundle is None or not isinstance(payload, dict) or payload.get("activate") is not True:
        return None
    record_id = payload.get("catalog_record_id")
    if type(record_id) is not str:
        return None
    if request.actor_id is None:
        raise GameLifecycleError("Catalog activation requires an owning player.")
    records = tuple(
        record
        for record in bundle.ability_indexes_by_player_id[request.actor_id].all_records()
        if record.record_id == record_id
    )
    if len(records) != 1:
        raise GameLifecycleError("Ability activation requires one authoritative catalog record.")
    if not ability_record_is_active_generic_rule_ir(records[0]):
        return None
    rule_ir = scoped_rule_ir_from_execution_payload(records[0].definition.replay_payload)
    if psychic_ability_level(rule_ir) is None:
        return None
    source_id = payload.get("source_unit_instance_id")
    model_id = payload.get("source_model_instance_id")
    reason: str | None
    if type(source_id) is not str or (model_id is not None and type(model_id) is not str):
        reason = "psychic_ability_source_evidence_malformed"
    else:
        reason = psychic_source_unavailable_reason(
            rule_ir=rule_ir,
            state=state,
            event_log=decisions.event_log,
            player_id=request.actor_id,
            source_unit_instance_id=source_id,
            source_model_instance_id=model_id,
        )
    if reason is None:
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Psychic ability activation is unavailable.",
        payload={"invalid_reason": reason},
    )
