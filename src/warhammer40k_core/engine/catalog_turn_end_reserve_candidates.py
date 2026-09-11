# pyright: reportPrivateUsage=false
from __future__ import annotations

from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_turn_end_reserves import (
    CatalogTurnEndReserveRuntime,
    _active_player_id,
    _unit_can_enter_strategic_reserves,
    catalog_turn_end_reserve_option,
    decision_recorded_this_turn,
    turn_end_reserve_candidates,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndRequestContext,
)


def candidates(
    runtime: CatalogTurnEndReserveRuntime, context: TurnEndRequestContext
) -> tuple[TimingRuleCandidate, ...]:
    candidates: list[TimingRuleCandidate] = []
    if type(context) is not TurnEndRequestContext:
        raise GameLifecycleError("Catalog turn-end reserves require request context.")
    if context.completed_phase is not BattlePhase.FIGHT:
        return tuple(candidates)
    active_player_id = _active_player_id(context)
    for army in runtime.armies:
        index = runtime.ability_indexes_by_player_id[army.player_id]
        for unit, record, rule_ir in turn_end_reserve_candidates(
            index=index, army=army, active_player_id=active_player_id, state=context.state
        ):
            if decision_recorded_this_turn(
                context, catalog_record_id=record.record_id, unit_instance_id=unit.unit_instance_id
            ):
                continue
            if not _unit_can_enter_strategic_reserves(
                context.state, unit_instance_id=unit.unit_instance_id
            ):
                continue
            candidates.append(
                timing_candidate_for_request(
                    template=DecisionRequest(
                        request_id="template:turn-end-rule",
                        decision_type=SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
                        actor_id=army.player_id,
                        payload={
                            "game_id": context.state.game_id,
                            "battle_round": context.state.battle_round,
                            "active_player_id": active_player_id,
                            "phase": context.completed_phase.value,
                            "source_rule_id": record.definition.source_id,
                            "hook_id": CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
                            "catalog_record_id": record.record_id,
                            "ability_id": record.definition.ability_id,
                            "ability_name": record.definition.name,
                            "datasheet_id": record.datasheet_id,
                            "source_kind": record.source_kind.value,
                            "target_unit_instance_id": unit.unit_instance_id,
                            "rule_ir_hash": rule_ir.ir_hash(),
                        },
                        options=(
                            catalog_turn_end_reserve_option(
                                player_id=army.player_id,
                                record=record,
                                unit_instance_id=unit.unit_instance_id,
                                use_ability=True,
                            ),
                            catalog_turn_end_reserve_option(
                                player_id=army.player_id,
                                record=record,
                                unit_instance_id=unit.unit_instance_id,
                                use_ability=False,
                            ),
                        ),
                    ),
                    participant_id=f"{record.record_id}:{unit.unit_instance_id}",
                    source_rule_id=record.definition.source_id,
                    requirement=SequencingRequirement.OPTIONAL,
                    next_request_id=context.state.next_decision_request_id,
                )
            )
    return tuple(candidates)
