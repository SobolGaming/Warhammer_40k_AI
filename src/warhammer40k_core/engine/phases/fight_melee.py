# pyright: reportPrivateUsage=false
"""Fight's declaration boundary, shared by ordinary, forced and retained hosts."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.engine.melee_weapon_commitment import (
    COMMITMENT_KEY,
    budgets_from_commitment,
    commitment_for_activation,
    object_payload,
    prepare_melee_commitment,
)
from warhammer40k_core.engine.phase import LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.core.army_catalog import ArmyCatalog
    from warhammer40k_core.core.ruleset_descriptor import FightPolicyDescriptor, RulesetDescriptor
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.fight import FightPhaseHandler
    from warhammer40k_core.engine.reaction_queue import ReactionQueue
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def _advance_active_fight_activation(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    from warhammer40k_core.core.ruleset_descriptor import FightTypeKind
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.fight_activation_units import active_fight_activation_rules_unit
    from warhammer40k_core.engine.fight_resolution import (
        MELEE_DECLARATION_PROPOSAL_KIND,
        build_melee_declaration_request,
    )
    from warhammer40k_core.engine.fight_rules_unit_melee import (
        rules_unit_available_melee_weapons_payloads,
        rules_unit_melee_target_unit_ids,
    )
    from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
    from warhammer40k_core.engine.phases.fight import (
        _MELEE_DECLARATION_REQUIRED_STATUS,
        _army_catalog_for_handler,
        _battlefield_scenario,
        _complete_active_fight_activation_without_melee_declaration,
        _request_epic_challenge_if_available,
        _request_fight_activation_ability_if_available,
        _request_selected_to_fight_stratagem_if_available,
        _ruleset_descriptor_for_handler,
        require_fight_state,
    )
    from warhammer40k_core.engine.phases.fight_movement_lifecycle import request_overrun_pile_in

    fight_state = require_fight_state(state)
    activation = fight_state.active_activation
    if activation is None:
        raise GameLifecycleError("Active fight activation advance requires selection.")
    melee_rules_unit = active_fight_activation_rules_unit(
        state=state,
        activation=activation,
    )
    if melee_rules_unit is None:
        return _complete_active_fight_activation_without_melee_declaration(
            handler=handler,
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            policy=policy,
            activation=activation,
            target_unit_instance_ids=(),
            available_weapon_count=0,
        )
    if (
        activation.fight_type is FightTypeKind.OVERRUN
        and not fight_state.overrun_pile_in_is_completed(
            activation_result_id=activation.result_id,
        )
    ):
        if not melee_rules_unit.alive_models():
            state.replace_fight_phase_state(
                fight_state.with_overrun_pile_in_completed(
                    activation_result_id=activation.result_id,
                )
            )
            decisions.event_log.append(
                "overrun_pile_in_not_available",
                validate_json_value(
                    {
                        "game_id": state.game_id,
                        "battle_round": state.battle_round,
                        "phase": BattlePhase.FIGHT.value,
                        "phase_body_status": "overrun_pile_in_not_available",
                        "activation_selection": activation.to_payload(),
                        "reason": "no_living_movable_models",
                    }
                ),
            )
            return None
        return request_overrun_pile_in(
            state=state,
            decisions=decisions,
            activation=activation,
        )
    scenario = _battlefield_scenario(state)
    target_ids = rules_unit_melee_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
        rules_unit=melee_rules_unit,
        state=state,
    )
    available_weapons = rules_unit_available_melee_weapons_payloads(
        runtime_modifier_registry=handler.runtime_modifier_registry,
        scenario=scenario,
        ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
        rules_unit=melee_rules_unit,
        army_catalog=_army_catalog_for_handler(handler),
        state=state,
        source_decision_result_id=activation.result_id,
    )
    if not target_ids or not available_weapons:
        return _complete_active_fight_activation_without_melee_declaration(
            handler=handler,
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            policy=policy,
            activation=activation,
            target_unit_instance_ids=target_ids,
            available_weapon_count=len(available_weapons),
        )
    ability_status = _request_fight_activation_ability_if_available(
        handler=handler,
        state=state,
        decisions=decisions,
        fight_state=fight_state,
        activation=activation,
        target_unit_instance_ids=target_ids,
    )
    if ability_status is not None:
        return ability_status
    epic_status = _request_epic_challenge_if_available(
        handler=handler,
        state=state,
        decisions=decisions,
        activation=activation,
    )
    if epic_status is not None:
        return epic_status
    selected_to_fight_stratagem_status = _request_selected_to_fight_stratagem_if_available(
        handler=handler,
        state=state,
        decisions=decisions,
        activation=activation,
    )
    if selected_to_fight_stratagem_status is not None:
        return selected_to_fight_stratagem_status
    from warhammer40k_core.engine.melee_pool_authority import commitment_inventory

    available_weapons = commitment_inventory(available_weapons, state)
    commitment_status = prepare_melee_commitment(
        state=state, decisions=decisions, activation=activation, rows=available_weapons
    )
    if commitment_status is not None:
        return commitment_status
    commitment = commitment_for_activation(decisions, activation.result_id)
    if commitment is not None:
        budgets = budgets_from_commitment(commitment)
        if not budgets:
            return _complete_active_fight_activation_without_melee_declaration(
                handler=handler,
                state=state,
                decisions=decisions,
                reaction_queue=reaction_queue,
                policy=policy,
                activation=activation,
                target_unit_instance_ids=target_ids,
                available_weapon_count=0,
            )
        available_weapons = tuple(
            row
            for row in available_weapons
            if object_payload(row)["weapon_instance_id"] in budgets
            and object_payload(row)["weapon_profile_id"]
            == budgets[str(object_payload(row)["weapon_instance_id"])].weapon_profile_id
        )
    request = build_melee_declaration_request(
        request_id=state.next_decision_request_id(),
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=fight_state.active_player_id,
        actor_id=activation.player_id,
        unit_instance_id=melee_rules_unit.unit_instance_id,
        source_decision_request_id=activation.request_id,
        source_decision_result_id=activation.result_id,
        ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
        available_weapons=available_weapons,
        target_unit_instance_ids=target_ids,
    )
    if commitment is not None:
        request = replace(
            request, payload={**object_payload(request.payload), COMMITMENT_KEY: commitment}
        )
    decisions.request_decision(request)
    decisions.event_log.append(
        "melee_declaration_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": _MELEE_DECLARATION_REQUIRED_STATUS,
                "request_id": request.request_id,
                "activation_selection": activation.to_payload(),
                "target_unit_instance_ids": list(target_ids),
                "available_weapon_count": len(available_weapons),
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": _MELEE_DECLARATION_REQUIRED_STATUS,
            "unit_instance_id": melee_rules_unit.unit_instance_id,
            "proposal_kind": MELEE_DECLARATION_PROPOSAL_KIND,
        },
    )


def invalid_melee_declaration_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    decisions: DecisionController | None = None,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
    from warhammer40k_core.engine.fight_rules_unit_melee import (
        validate_rules_unit_melee_declaration,
    )
    from warhammer40k_core.engine.phases.fight import (
        _battlefield_scenario,
        _parse_melee_declaration_or_invalid,
        _reject_invalid_fight_proposal,
    )

    proposal_request = MeleeDeclarationProposalRequest.from_decision_request(request)
    parsed = _parse_melee_declaration_or_invalid(
        state=state,
        proposal_request=proposal_request,
        result=result,
    )
    if isinstance(parsed, LifecycleStatus):
        return parsed
    proposal = parsed
    proposal_validation = proposal.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid:
        return _reject_invalid_fight_proposal(
            state=state,
            proposal_validation=proposal_validation,
            message="Melee declaration proposal does not match the pending request.",
        )
    from warhammer40k_core.engine.melee_commitment_dispatch import validate_declaration_commitment
    from warhammer40k_core.engine.phase import GameLifecycleError

    try:
        budgets = validate_declaration_commitment(
            decisions=decisions, request=request, proposal=proposal
        )
    except GameLifecycleError as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message=str(exc),
            payload={"invalid_reason": "melee_commitment_drift"},
        )
    rule_validation = validate_rules_unit_melee_declaration(
        committed_budgets=budgets,
        runtime_modifier_registry=runtime_modifier_registry,
        scenario=_battlefield_scenario(state),
        ruleset_descriptor=ruleset_descriptor,
        request=proposal_request,
        proposal=proposal,
        army_catalog=army_catalog,
        state=state,
    )
    if not rule_validation.is_valid:
        return _reject_invalid_fight_proposal(
            state=state,
            proposal_validation=rule_validation,
            message="Melee declaration proposal is not currently legal.",
        )
    return None


def _apply_melee_declaration_decision(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:

    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.fight_resolution import (
        MeleeDeclarationProposalRequest,
        melee_declaration_proposal_from_payload,
    )
    from warhammer40k_core.engine.fight_rules_unit_melee import (
        record_rules_unit_one_shot_melee_weapon_uses,
        rules_unit_melee_attack_sequence_from_proposal,
    )
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.phases.fight import (
        _MELEE_DECLARATION_ACCEPTED_STATUS,
        _army_catalog_for_handler,
        _battlefield_scenario,
        _ruleset_descriptor_for_handler,
        require_fight_state,
    )
    from warhammer40k_core.engine.random_weapon_profiles import random_melee_pool_evidence

    record = decisions.record_for_result(result)
    proposal_request = MeleeDeclarationProposalRequest.from_decision_request(record.request)
    proposal = melee_declaration_proposal_from_payload(result.payload)
    sequence_id = (
        f"melee-sequence:{state.game_id}:round-{state.battle_round:02d}:"
        f"{proposal.unit_instance_id}:{result.result_id}"
    )
    commitment = commitment_for_activation(decisions, proposal.source_decision_result_id)
    attack_sequence = rules_unit_melee_attack_sequence_from_proposal(
        committed_budgets=None if commitment is None else budgets_from_commitment(commitment),
        scenario=_battlefield_scenario(state),
        ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
        proposal=proposal,
        army_catalog=_army_catalog_for_handler(handler),
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        sequence_id=sequence_id,
        state=state,
        runtime_modifier_registry=handler.runtime_modifier_registry,
    )
    one_shot_records = record_rules_unit_one_shot_melee_weapon_uses(
        state=state,
        scenario=_battlefield_scenario(state),
        proposal=proposal,
        army_catalog=_army_catalog_for_handler(handler),
        result_id=result.result_id,
    )
    fight_state = require_fight_state(state)
    state.replace_fight_phase_state(
        fight_state.with_attack_sequence_update(
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=fight_state.allocated_model_ids_this_phase,
        )
    )
    decisions.event_log.append(
        "melee_declaration_accepted",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": _MELEE_DECLARATION_ACCEPTED_STATUS,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "proposal_request": proposal_request.to_payload(),
                "proposal": proposal.to_payload(),
                "attack_sequence_id": attack_sequence.sequence_id,
                **(
                    {"attack_pools": [pool.to_payload() for pool in attack_sequence.attack_pools]}
                    if commitment is not None
                    else random_melee_pool_evidence(attack_sequence.attack_pools, state=state)
                ),
                "one_shot_weapon_use_records": [record.to_payload() for record in one_shot_records],
            }
        ),
    )
    return None


__all__ = (
    "_advance_active_fight_activation",
    "_apply_melee_declaration_decision",
    "invalid_melee_declaration_status",
)
